"""PNG 序列 → 翻页视频。

刻意不做长图滚动：多页之后滚动会让用户失去节奏控制，且竖屏里必然出现半页状态。
翻页每页停留时长可精确控制，页内再叠一层极缓慢的推镜避免画面死板。
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any


def _segment_filter(idx: int, dur: float, cfg: dict[str, Any]) -> str:
    v = cfg["video"]
    w, h, fps, amp = v["width"], v["height"], v["fps"], v["ken_burns"]
    frames = max(int(round(dur * fps)) - 1, 1)
    zoom = f"min(1+{amp}*on/{frames},{1 + amp})" if amp > 0 else "1"
    return (
        f"[{idx}:v]scale={w * 2}:{h * 2}:flags=lanczos,"
        f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d=1:s={w}x{h}:fps={fps},setsar=1,format=yuv420p[v{idx}]"
    )


def page_durations(script: Any, cfg: dict[str, Any]) -> list[float]:
    """按页面字数推算停留时长。

    固定时长在这里行不通：同一套模板里，一页可能 4 行也可能 8 行，
    给短页太久拖完播率，给长页太短根本读不完。
    """
    v = cfg["video"]
    out = [float(v["cover_sec"])]
    for page in script.pages[1:]:
        chars = len(page.headline) + sum(len(line) for line in page.body_lines)
        out.append(max(v["page_min_sec"], round(chars / v["reading_cps"] + v["page_pad_sec"], 2)))
    return out


def build_video(
    pngs: list[Path],
    out_path: Path,
    cfg: dict[str, Any],
    bgm: Path | None = None,
    durations: list[float] | None = None,
) -> Path:
    if not pngs:
        raise ValueError("没有可合成的页面")

    v = cfg["video"]
    fps, trans = v["fps"], v["transition_sec"]
    if durations is None:
        durations = [float(v["cover_sec"])] * len(pngs)
    if len(durations) != len(pngs):
        raise ValueError("时长数量与页面数量不一致")
    total = sum(durations) - trans * (len(pngs) - 1)

    cmd: list[str] = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for png, dur in zip(pngs, durations):
        cmd += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(png)]

    audio_idx = len(pngs)
    if bgm is not None:
        cmd += ["-i", str(bgm)]
    else:
        cmd += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]

    steps = [_segment_filter(i, d, cfg) for i, d in enumerate(durations)]

    # xfade 链：第 k 次转场的 offset = 前 k 段时长之和 - k × 转场时长
    current = "[v0]"
    elapsed = 0.0
    for k in range(1, len(pngs)):
        elapsed += durations[k - 1]
        offset = elapsed - k * trans
        label = f"[x{k}]"
        steps.append(
            f"{current}[v{k}]xfade=transition=fade:duration={trans}:"
            f"offset={offset:.3f}{label}"
        )
        current = label

    steps.append(f"{current}format=yuv420p[vout]")
    audio_filter = f"[{audio_idx}:a]afade=t=out:st={max(total - 2.0, 0):.3f}:d=2[aout]"
    steps.append(audio_filter)

    cmd += [
        "-filter_complex", ";".join(steps),
        "-map", "[vout]", "-map", "[aout]",
        "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 合成失败：\n{result.stderr.strip()}\n命令：{shlex.join(cmd)}"
        )
    return out_path
