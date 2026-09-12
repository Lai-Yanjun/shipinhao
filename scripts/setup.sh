#!/usr/bin/env bash
# 环境准备。渲染依赖三样东西：
#   1. ffmpeg（含 libx264）—— 合成翻页视频
#   2. Chromium —— Playwright 截取档案页
#   3. 思源黑体 Noto Sans CJK —— 没有它中文会渲染成豆腐块
#
# macOS 需要先装 Homebrew；Windows 请在 WSL 里跑这个脚本。
set -euo pipefail

OS="$(uname -s)"

install_linux() {
  local sudo_cmd=""
  [ "$(id -u)" -ne 0 ] && sudo_cmd="sudo"
  $sudo_cmd apt-get update -qq
  command -v ffmpeg >/dev/null 2>&1 || $sudo_cmd apt-get install -y ffmpeg
  # 本地与云端必须装同一套中文字体，否则排版会漂移
  fc-list :lang=zh 2>/dev/null | grep -qi noto || $sudo_cmd apt-get install -y fonts-noto-cjk
}

install_macos() {
  if ! command -v brew >/dev/null 2>&1; then
    echo "需要 Homebrew：https://brew.sh" >&2
    exit 1
  fi
  command -v ffmpeg >/dev/null 2>&1 || brew install ffmpeg
  # macOS 自带的苹方能正常渲染中文，但与云端字体不同会导致换行位置差异，
  # 装上思源黑体保证两边一致
  brew list --cask font-noto-sans-cjk-sc >/dev/null 2>&1 || brew install --cask font-noto-sans-cjk-sc
}

case "$OS" in
  Linux)  install_linux ;;
  Darwin) install_macos ;;
  *) echo "不支持的系统：$OS。Windows 请在 WSL 里运行。" >&2; exit 1 ;;
esac

pip install -r requirements.txt

# 云端镜像通常已预置 Chromium；本地需要下载一次
if [ -z "${PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD:-}" ]; then
  python3 -m playwright install chromium
fi

echo
echo "自检："
command -v ffmpeg >/dev/null && echo "  ffmpeg  $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f3)" || echo "  ffmpeg  缺失"
python3 -c "import playwright, PIL, yaml, pydantic; print('  python 依赖 ok')"
fc-list :lang=zh 2>/dev/null | grep -qi noto && echo "  中文字体 ok" || echo "  中文字体 缺失 —— 中文会渲染成豆腐块"
echo
echo "环境就绪。跑一遍样例验证："
echo "  mkdir -p out/demo && cp samples/dyatlov-pass-v4.json out/demo/script.json"
echo "  python cli.py build --slug demo --case-no 1"
