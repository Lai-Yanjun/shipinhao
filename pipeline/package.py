"""一次内容，三个平台的成品包。

视频号/抖音吃视频，小红书吃图文轮播（零额外成本，直接复用 PNG），
公众号吃纵向长图 —— 公众号是后期真正的变现主阵地，别漏。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from .models import CaseScript


def build_carousel(pngs: list[Path], out_dir: Path) -> Path:
    """小红书图文轮播：页面 PNG 原样复用，不做二次加工。"""
    carousel = out_dir / "xiaohongshu"
    carousel.mkdir(parents=True, exist_ok=True)
    for i, png in enumerate(pngs, start=1):
        shutil.copy2(png, carousel / f"{i:02d}.png")
    return carousel


def build_longpic(pngs: list[Path], out_dir: Path) -> Path:
    """公众号长图：所有页面纵向拼接成一张。"""
    images = [Image.open(p).convert("RGB") for p in pngs]
    width = max(im.width for im in images)
    canvas = Image.new("RGB", (width, sum(im.height for im in images)), "#FAFAF8")
    y = 0
    for im in images:
        canvas.paste(im, (0, y))
        y += im.height
    path = out_dir / "wechat_longpic.jpg"
    canvas.save(path, quality=88, optimize=True)
    return path


def write_copy(script: CaseScript, cfg: dict[str, Any], case_no: int, out_dir: Path) -> Path:
    brand = cfg["brand"]
    topics = " ".join(f"#{t}" for t in script.topics)
    facts = "\n".join(f"- {n}" for n in script.fact_notes)
    risks = "\n".join(f"- {r}" for r in script.risk_flags)

    content = f"""# CASE {case_no:02d} · {script.case_title}

栏目：{brand['masthead']} · {brand['column']} · ISSUE {brand['issue']:02d}
封面钩子：**{script.hook_title}**

## 视频号 / 抖音

标题（封面已含钩子，此处填标题栏）：
{script.hook_title}｜{script.meta_line}

文案区：
{script.feed_caption}

{topics}

## 小红书

标题：{script.xhs_title}

正文：
{script.feed_caption}

{topics}

## 事实核查底稿

{facts}

## 合规自检

{risks}

## 发布前清单

- [ ] 每页配图均来自公有领域或已获授权，来源已记入 topics/assets/{script.slug}/assets.yaml
- [ ] 图注中的时间、地点、机构与史料一致
- [ ] 文案无主观推测、无因果结论、未指控任何在世个人
- [ ] 发布时勾选平台的「内容由 AI 生成」声明
- [ ] 封面钩子未使用事件学名
"""
    path = out_dir / "copy.md"
    path.write_text(content, encoding="utf-8")
    return path
