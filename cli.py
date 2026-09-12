#!/usr/bin/env python3
"""极地档案内容工厂的管道部分。

内容由 Claude 会话产出（见 .claude/skills/archive-case/SKILL.md），
这里只负责确定性的环节：渲染、合成、校验、编号、归档。

    python cli.py build  --slug <slug>
    python cli.py verify --slug <slug>
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

import yaml

from pipeline import archive, verify
from pipeline.config import ROOT, load_config
from pipeline.models import CaseScript
from pipeline.package import build_carousel, build_longpic, write_assets_todo, write_copy
from pipeline.render import render_case
from pipeline.video import build_video, page_durations

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

    bgm = _pick_bgm(script, args.bgm)

    video = build_video(pngs, out_dir / "video_9x16.mp4", cfg, bgm,
                        page_durations(script, cfg))
    carousel = build_carousel(pngs, out_dir)
    longpic = build_longpic(pngs, out_dir)
    copy = write_copy(script, cfg, case_no, out_dir)
    todo = write_assets_todo(script, out_dir)

    print(f"视频号/抖音：{video}")
    print(f"小红书轮播：{carousel}")
    print(f"公众号长图：{longpic}")
    print(f"文案与清单：{copy}")
    print(f"配图任务单：{todo}")

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


AUDIO_EXTS = (".mp3", ".m4a", ".wav", ".ogg")


def _pick_bgm(script: CaseScript, explicit: str | None) -> Path | None:
    """选配乐：显式指定优先，否则按情绪标签从曲库里取。"""
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path
        print(f"BGM 不存在：{path}", file=sys.stderr)
        return None

    folder = ROOT / "assets" / "bgm" / script.bgm_mood
    candidates = sorted(p for p in folder.glob("*") if p.suffix.lower() in AUDIO_EXTS)
    if candidates:
        return candidates[0]
    print(f"曲库里没有 {script.bgm_mood} 情绪的配乐，出无声轨。", file=sys.stderr)
    print(f"  生成一条：python scripts/make_bgm.py --mood {script.bgm_mood}", file=sys.stderr)
    return None


def _load(slug: str) -> CaseScript:
    path = _script_path(slug)
    if not path.exists():
        raise SystemExit(f"找不到文案：{path}，先跑 write")
    return CaseScript.model_validate_json(path.read_text(encoding="utf-8"))


def cmd_verify(args: argparse.Namespace) -> int:
    script = _load(args.slug)
    assets_dir = ASSETS / args.slug
    report = verify.run(script, assets_dir)

    print(f"\n校验 {script.case_title}（{args.slug}）\n")
    for check in report.checks:
        if check.needs_human:
            print(f"  [需人工确认] {check.name}")
        else:
            print(f"  [{'通过' if check.passed else '未通过'}] {check.name}")
        if check.detail:
            print(f"      {check.detail}" if "\n" not in check.detail else check.detail)

    if report.blocking:
        print(f"\n{len(report.blocking)} 项未通过，未分配编号。修完重跑。")
        return 1

    if args.yes:
        verified_by = "auto"
        print("\n已用 --yes 跳过人工确认 —— 台账会记为 auto，事实与合规风险由你自己承担。")
    else:
        print("\n以上两项机器判断不了，必须你自己看过。")
        answer = input("全部确认无误？(yes/N) ").strip().lower()
        if answer != "yes":
            print("未确认，不分配编号。")
            return 1
        verified_by = "human"

    case, created = archive.register(
        args.slug, script.case_title, script.hook_title, verified_by
    )
    case_no = case["case_no"]
    if not created:
        print(f"\n该期已在台账中，编号 CASE {case_no:02d}，沿用原编号。")

    # 编号定下来才重渲染 —— 页面上的 CASE 号必须与台账一致
    cfg = load_config()
    out_dir = OUT / args.slug
    pngs = render_case(script, cfg, case_no, assets_dir, out_dir)
    build_video(pngs, out_dir / "video_9x16.mp4", cfg,
                _pick_bgm(script, args.bgm), page_durations(script, cfg))
    build_carousel(pngs, out_dir)
    build_longpic(pngs, out_dir)
    write_copy(script, cfg, case_no, out_dir)

    dest = archive.case_dir(case_no, args.slug)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for item in ("video_9x16.mp4", "wechat_longpic.jpg", "copy.md", "script.json"):
        src = out_dir / item
        if src.exists():
            shutil.copy2(src, dest / item)
    shutil.copytree(out_dir / "xiaohongshu", dest / "xiaohongshu")
    shutil.copy2(pngs[0], dest / "cover.png")

    print(f"\nCASE {case_no:02d} 已归档：{dest}")
    print(f"台账：{archive.INDEX}")
    print(f"\n发布后回填记录：")
    print(f"  python cli.py publish --slug {args.slug} --platform 视频号 --url <链接>")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    index = archive.load_index()
    if not index["cases"]:
        print("台账为空。")
        return 0
    for case in index["cases"]:
        platforms = "、".join(p["platform"] for p in case["published"]) or "未发布"
        mark = "人工" if case["verified_by"] == "human" else "auto"
        print(f"CASE {case['case_no']:02d}  {case['case_title']}")
        print(f"          钩子：{case['hook_title']}")
        print(f"          校验：{case['verified_at']}（{mark}）  发布：{platforms}")
    print(f"\n下一个编号：CASE {index['next_case_no']:02d}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    case = archive.record_publish(
        args.slug, args.platform, args.url, args.at or date.today().isoformat()
    )
    print(f"已记录 CASE {case['case_no']:02d} 在 {args.platform} 的发布。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="极地档案内容工厂")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出选题池")
    p_list.set_defaults(func=cmd_list)

    p_build = sub.add_parser("build", help="渲染页面并产出三平台成品包")
    p_build.add_argument("--slug", required=True)
    p_build.add_argument("--case-no", type=int, default=None)
    p_build.add_argument("--bgm", default=None)
    p_build.set_defaults(func=cmd_build)

    p_verify = sub.add_parser("verify", help="发布前校验，通过则分配 CASE 编号并归档")
    p_verify.add_argument("--slug", required=True)
    p_verify.add_argument("--bgm", default=None)
    p_verify.add_argument("--yes", action="store_true",
                          help="跳过人工确认，台账记为 auto（不建议）")
    p_verify.set_defaults(func=cmd_verify)

    p_status = sub.add_parser("status", help="查看归档台账")
    p_status.set_defaults(func=cmd_status)

    p_publish = sub.add_parser("publish", help="回填发布记录")
    p_publish.add_argument("--slug", required=True)
    p_publish.add_argument("--platform", required=True)
    p_publish.add_argument("--url", required=True)
    p_publish.add_argument("--at", default=None)
    p_publish.set_defaults(func=cmd_publish)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
