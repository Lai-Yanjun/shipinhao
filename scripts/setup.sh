#!/usr/bin/env bash
# 云端/新机器一键环境准备。本项目的渲染依赖三样东西：
#   1. ffmpeg（含 libx264）—— 合成翻页视频
#   2. Chromium —— Playwright 截取档案页
#   3. 思源黑体 Noto Sans CJK —— 没有它中文会渲染成豆腐块
set -euo pipefail

if ! command -v ffmpeg >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y ffmpeg
fi

# 中文字体：排版一致性的前提，本地与云端必须装同一套
fc-list :lang=zh 2>/dev/null | grep -qi "noto" || apt-get install -y fonts-noto-cjk

pip install -r requirements.txt

# Playwright 浏览器：云端镜像通常已预置（PLAYWRIGHT_BROWSERS_PATH），跳过重复下载
if [ -z "${PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD:-}" ]; then
  python3 -m playwright install chromium
fi

echo "环境就绪。"
