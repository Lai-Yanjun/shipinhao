#!/usr/bin/env python3
"""从 B 站视频抓取口播文案，供风格蒸馏使用。

**必须在你自己的机器上跑。** 云端会话的出网策略拦截了 bilibili.com 与
huggingface.co，字幕和语音模型都取不到。

两级策略：先试字幕（快、准、免费），没有字幕再落到语音转写。

    pip install yt-dlp
    pip install faster-whisper          # 只有需要语音转写时才装

    # 优先：有字幕的情况
    python scripts/fetch_transcript.py "https://www.bilibili.com/video/BVxxxx" \
        --cookies-from-browser chrome

    # 没字幕：转写音频
    python scripts/fetch_transcript.py "https://www.bilibili.com/video/BVxxxx" --asr

找「最多播放」的视频：浏览器打开 space.bilibili.com/<uid>/video?order=click，
排序后复制前几条的链接。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "styles" / "raw"
# 钩子段。蒸馏真正要看的是开头怎么把人拽住，不是全文。
HOOK_SECONDS = 90


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(url: str, cookies: list[str]) -> dict:
    result = run(["yt-dlp", "-J", "--no-playlist", *cookies, url])
    if result.returncode != 0:
        raise RuntimeError(f"取不到视频信息：{result.stderr.strip()[:400]}")
    return json.loads(result.stdout)


def parse_vtt(text: str) -> list[tuple[float, str]]:
    """解析 VTT，返回 (起始秒, 文本)。去掉重复行 —— 自动字幕常把同一句滚动重复。"""
    cues: list[tuple[float, str]] = []
    stamp = re.compile(r"(\d+):(\d+):([\d.]+)\s*-->")
    current: float | None = None
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        match = stamp.search(line)
        if match:
            h, m, s = match.groups()
            current = int(h) * 3600 + int(m) * 60 + float(s)
            continue
        if not line or line.startswith(("WEBVTT", "NOTE", "Kind:", "Language:")):
            continue
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean not in seen and current is not None:
            seen.add(clean)
            cues.append((current, clean))
    return cues


def try_subtitles(url: str, cookies: list[str], workdir: Path) -> list[tuple[float, str]] | None:
    result = run([
        "yt-dlp", "--skip-download",
        "--write-subs", "--write-auto-subs", "--sub-langs", "zh.*,ai-zh",
        "--sub-format", "vtt/srt/best", "--convert-subs", "vtt",
        "-o", str(workdir / "sub"), *cookies, url,
    ])
    files = sorted(workdir.glob("sub*.vtt"))
    if not files:
        detail = result.stderr.strip().splitlines()[-1:] or [""]
        print(f"  未找到字幕（{detail[0][:120]}）", file=sys.stderr)
        return None
    return parse_vtt(files[0].read_text(encoding="utf-8", errors="ignore"))


def transcribe(url: str, cookies: list[str], workdir: Path, model_size: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("需要语音转写请先 pip install faster-whisper")

    audio = workdir / "audio.m4a"
    result = run([
        "yt-dlp", "-f", "bestaudio", "--no-playlist",
        "-o", str(audio), *cookies, url,
    ])
    if result.returncode != 0 or not audio.exists():
        raise RuntimeError(f"音频下载失败：{result.stderr.strip()[:400]}")

    print(f"  转写中（模型 {model_size}，首次运行要下载模型）…", file=sys.stderr)
    model = WhisperModel(model_size, device="auto", compute_type="int8")
    segments, _ = model.transcribe(str(audio), language="zh", vad_filter=True)
    return [(seg.start, seg.text.strip()) for seg in segments if seg.text.strip()]


def write_markdown(info: dict, cues: list[tuple[float, str]], source: str, out_dir: Path) -> Path:
    title = info.get("title", "未命名")
    safe = re.sub(r"[^\w一-鿿-]+", "-", title)[:48].strip("-") or "untitled"
    hook = [text for start, text in cues if start < HOOK_SECONDS]
    body = [text for start, text in cues if start >= HOOK_SECONDS]

    views = info.get("view_count")
    hook_text = "\n".join(hook) or "（无）"
    body_text = "\n".join(body) or "（无）"
    content = f"""# {title}

- UP主：{info.get('uploader', '未知')}
- 链接：{info.get('webpage_url', '')}
- 时长：{int(info.get('duration') or 0) // 60} 分钟
- 播放：{views if views is not None else '未知'}
- 文案来源：{source}

## 钩子段（前 {HOOK_SECONDS} 秒）

蒸馏主要看这一段：开头是怎么把人拽住的。

{hook_text}

## 正文

{body_text}
"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{safe}.md"
    path.write_text(content, encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取 B 站视频口播文案")
    parser.add_argument("urls", nargs="+", help="B 站视频链接")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--cookies-from-browser", default=None,
                        help="chrome / firefox / edge —— B站的 AI 字幕需要登录态")
    parser.add_argument("--asr", action="store_true", help="没有字幕时转写音频")
    parser.add_argument("--model", default="medium", help="Whisper 模型：small/medium/large-v3")
    args = parser.parse_args()

    cookies = (
        ["--cookies-from-browser", args.cookies_from_browser]
        if args.cookies_from_browser else []
    )
    out_dir = Path(args.out)
    failures = 0

    for url in args.urls:
        print(f"\n处理 {url}", file=sys.stderr)
        try:
            info = probe(url, cookies)
            with tempfile.TemporaryDirectory() as tmp:
                workdir = Path(tmp)
                cues = try_subtitles(url, cookies, workdir)
                source = "字幕"
                if not cues:
                    if not args.asr:
                        print("  无字幕。加 --asr 转写音频，或换一条有字幕的。", file=sys.stderr)
                        failures += 1
                        continue
                    cues = transcribe(url, cookies, workdir, args.model)
                    source = f"语音转写（whisper {args.model}，可能有错字）"
                path = write_markdown(info, cues, source, out_dir)
            print(f"  已写入 {path}", file=sys.stderr)
        except Exception as exc:
            print(f"  失败：{exc}", file=sys.stderr)
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
