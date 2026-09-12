#!/usr/bin/env python3
"""合成一段铺底音 —— 这是兜底占位，不是配乐。

产出就是正弦加噪声的嗡鸣，听感谈不上音乐。它存在的意义只有一个：
一首真曲子都没有、又需要成片带音轨时顶一下。

正经配乐请放 assets/bgm/<情绪>/，来源见该目录的 README。

    python scripts/make_bgm.py --mood cold --duration 90

产出 assets/bgm/<mood>/<mood>-<duration>s.mp3。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 每种情绪由两个低频正弦的音程关系决定，噪声层做"风声"。
# 音程是情绪的来源：纯五度空旷，小二度不安，小三度哀伤。
MOODS: dict[str, dict] = {
    "cold": {
        "tones": [(55.00, 0.30), (82.41, 0.18)],   # A1 + E2，纯五度：空旷
        "noise": ("brown", 500, 0.10),
        "tremolo": (0.12, 0.35),
        "desc": "极寒、空旷",
    },
    "tension": {
        "tones": [(55.00, 0.30), (58.27, 0.20)],   # A1 + A#1，小二度拍频：不安
        "noise": ("brown", 700, 0.12),
        "tremolo": (0.25, 0.45),
        "desc": "悬疑推进",
    },
    "grief": {
        "tones": [(110.00, 0.24), (130.81, 0.16)],  # A2 + C3，小三度：哀伤
        "noise": ("pink", 400, 0.07),
        "tremolo": (0.10, 0.25),
        "desc": "哀悼收束",
    },
    "archive": {
        "tones": [(55.00, 0.22)],                   # 单音，几乎不动
        "noise": ("brown", 350, 0.09),
        "tremolo": (0.10, 0.18),
        "desc": "档案、克制",
    },
}


def build(mood: str, duration: float, out: Path) -> Path:
    spec = MOODS[mood]
    fade = min(5.0, duration / 6)

    cmd = ["ffmpeg", "-y", "-v", "error"]
    for freq, _ in spec["tones"]:
        cmd += ["-f", "lavfi", "-i", f"sine=f={freq}:d={duration}:r=44100"]
    color, cutoff, level = spec["noise"]
    cmd += ["-f", "lavfi", "-i", f"anoisesrc=d={duration}:c={color}:a=1:r=44100"]

    steps = [f"[{i}:a]volume={vol}[s{i}]" for i, (_, vol) in enumerate(spec["tones"])]
    noise_idx = len(spec["tones"])
    steps.append(f"[{noise_idx}:a]lowpass=f={cutoff},volume={level}[n]")

    inputs = "".join(f"[s{i}]" for i in range(len(spec["tones"]))) + "[n]"
    trem_f, trem_d = spec["tremolo"]
    steps.append(f"{inputs}amix=inputs={noise_idx + 1}:duration=longest:normalize=0[mix]")
    steps.append(
        f"[mix]tremolo=f={trem_f}:d={trem_d},"
        # 两段延迟制造空间感，不用真混响也够
        "aecho=0.8:0.9:600|1200:0.25|0.15,"
        "highpass=f=30,lowpass=f=3000,"
        # 压到 -22 LUFS：配乐要垫在画面下面，不能抢
        "loudnorm=I=-22:TP=-2,"
        f"afade=t=in:st=0:d={fade:.2f},"
        f"afade=t=out:st={max(duration - fade, 0):.2f}:d={fade:.2f}[out]"
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    cmd += ["-filter_complex", ";".join(steps), "-map", "[out]",
            "-c:a", "libmp3lame", "-b:a", "128k", "-ac", "2", str(out)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"合成失败：{result.stderr.strip()[:400]}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="合成配乐床")
    parser.add_argument("--mood", choices=sorted(MOODS), default=None,
                        help="省略则四种全做")
    parser.add_argument("--duration", type=float, default=90.0)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    moods = [args.mood] if args.mood else sorted(MOODS)
    for mood in moods:
        out = (Path(args.out) if args.out
               else ROOT / "assets" / "bgm" / mood / f"{mood}-{int(args.duration)}s.mp3")
        build(mood, args.duration, out)
        print(f"{mood:9s} {MOODS[mood]['desc']:8s} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
