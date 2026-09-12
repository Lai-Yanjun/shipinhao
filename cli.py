#!/usr/bin/env python3
"""极地档案内容工厂。

典型流程（write 与 build 分开是刻意的 —— 中间那步人工校订不能省）：

    python cli.py write --topic "富兰克林远征" --case-no 2
    # 人工校订 out/<slug>/script.json：核事实、调钩子、删掉任何推测句
    python cli.py build --slug <slug>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from pipeline.config import ROOT, load_config
from pipeline.models import CaseScript
from pipeline.package import build_carousel, build_longpic, write_copy
from pipeline.render import render_case
from pipeline.video import build_video

OUT = ROOT / "out"
ASSETS = ROOT / "topics" / "assets"


def _script_path(slug: str) -> Path:
    return OUT / slug / "script.json"


def cmd_list(_: argparse.Namespace) -> int:
    backlog = yaml.safe_load((ROOT / "topics" / "backlog.yaml").read_text(encoding="utf-8"))
    for item in backlog["topics"]:
        print(f"[{item['risk']}] {item['title']}  ({item['year']} · {item['region']})")
        print(f"        {item['note']}")
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    from pipeline.script_gen import RefusalError, generate

    try:
        script = generate(args.topic, args.case_no, args.note)
    except RefusalError as exc:
        print(f"生成被拒：{exc}", file=sys.stderr)
        return 2

    out_dir = OUT / script.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "script.json"
    path.write_text(
        json.dumps(script.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "case_no").write_text(str(args.case_no), encoding="utf-8")

    print(f"文案已生成：{path}")
    print(f"封面钩子：{script.hook_title}")
    print("\n合规自检：")
    for flag in script.risk_flags:
        print(f"  - {flag}")
    print(f"\n下一步：校订 {path}，把配图放进 {ASSETS / script.slug}/ 后执行")
    print(f"  python cli.py build --slug {script.slug}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    cfg = load_config()
    path = _script_path(args.slug)
    if not path.exists():
        print(f"找不到文案：{path}，先跑 write", file=sys.stderr)
        return 2

    script = CaseScript.model_validate_json(path.read_text(encoding="utf-8"))
    out_dir = path.parent
    case_no_file = out_dir / "case_no"
    case_no = args.case_no or (
        int(case_no_file.read_text().strip()) if case_no_file.exists() else 1
    )

    assets_dir = ASSETS / script.slug
    assets_dir.mkdir(parents=True, exist_ok=True)

    pngs = render_case(script, cfg, case_no, assets_dir, out_dir)
    print(f"页面已渲染：{len(pngs)} 页 → {out_dir / 'pages'}")

    bgm = Path(args.bgm) if args.bgm else None
    if bgm is not None and not bgm.exists():
        print(f"BGM 不存在：{bgm}，改出无声轨", file=sys.stderr)
        bgm = None

    video = build_video(pngs, out_dir / "video_9x16.mp4", cfg, bgm)
    carousel = build_carousel(pngs, out_dir)
    longpic = build_longpic(pngs, out_dir)
    copy = write_copy(script, cfg, case_no, out_dir)

    print(f"视频号/抖音：{video}")
    print(f"小红书轮播：{carousel}")
    print(f"公众号长图：{longpic}")
    print(f"文案与清单：{copy}")

    # cta 等页面本就不配图，只检查声明了配图需求的页
    missing = [
        i
        for i, page in enumerate(script.pages, start=1)
        if (page.image_query or page.image_caption)
        and not any(
            (assets_dir / f"p{i:02d}{e}").exists()
            for e in (".jpg", ".jpeg", ".png", ".webp")
        )
    ]
    if missing:
        print(f"\n注意：第 {missing} 页尚无配图，已渲染成占位框。")
        print(f"      把公版图片按 p02.jpg 这样的命名放进 {assets_dir}/ 后重跑 build。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="极地档案内容工厂")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出选题池")
    p_list.set_defaults(func=cmd_list)

    p_write = sub.add_parser("write", help="用 Claude 生成一期文案")
    p_write.add_argument("--topic", required=True)
    p_write.add_argument("--case-no", type=int, required=True)
    p_write.add_argument("--note", default="无")
    p_write.set_defaults(func=cmd_write)

    p_build = sub.add_parser("build", help="渲染页面并产出三平台成品包")
    p_build.add_argument("--slug", required=True)
    p_build.add_argument("--case-no", type=int, default=None)
    p_build.add_argument("--bgm", default=None)
    p_build.set_defaults(func=cmd_build)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
