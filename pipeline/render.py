"""把文案渲染成页面 PNG 序列。

PNG 序列是整条流水线的中间产物，三个平台的成品全部从它派生：
翻页视频（视频号/抖音）、图文轮播（小红书）、纵向长图（公众号）。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from .models import CaseScript, Page

TEMPLATES = Path(__file__).resolve().parent / "templates"
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
AI_MARK = "本内容由 AI 辅助生成"

# 做旧噪点：纯 SVG 生成，不依赖任何素材文件
NOISE_SVG = (
    '<svg class="noise" xmlns="http://www.w3.org/2000/svg">'
    '<filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.82" '
    'numOctaves="4" stitchTiles="stitch"/></filter>'
    '<rect width="100%" height="100%" filter="url(#n)" opacity="{opacity}"/></svg>'
)


def _chromium_executable() -> str | None:
    """定位 Chromium。

    云端镜像常把浏览器预置在 PLAYWRIGHT_BROWSERS_PATH 下，而 pip 装的 playwright
    可能期待另一个构建号，直接 launch 会报找不到可执行文件。这里优先用显式配置，
    其次扫描预置目录，都没有才交回 Playwright 自己解析。
    """
    explicit = os.environ.get("CHROMIUM_EXECUTABLE")
    if explicit and Path(explicit).exists():
        return explicit

    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"))
    if root.is_dir():
        for candidate in sorted(root.glob("chromium-*/chrome-linux/chrome"), reverse=True):
            if candidate.exists():
                return str(candidate)
    return None


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def find_asset(assets_dir: Path, index: int) -> Path | None:
    """按页码约定查找素材：p02.jpg 对应第 2 页。找不到返回 None，渲染成缺图占位框。"""
    for ext in IMAGE_EXTS:
        candidate = assets_dir / f"p{index:02d}{ext}"
        if candidate.exists():
            return candidate
    return None


def _figure_html(page: Page, asset: Path | None) -> str:
    if not page.image_caption and not page.image_query:
        return ""
    if asset is None:
        inner = (
            '<div class="img-missing">'
            '<div class="label">档案图待补</div>'
            f'<div class="query">检索关键词：{_esc(page.image_query)}</div>'
            "</div>"
        )
    else:
        inner = f'<img src="{_esc(asset.name)}">'
    caption = (
        f"<figcaption>{_esc(page.image_caption)}</figcaption>" if page.image_caption else ""
    )
    return f"<figure>{inner}{caption}</figure>"


def build_cover_html(script: CaseScript, cfg: dict[str, Any], asset: Path | None) -> str:
    brand = cfg["brand"]
    cover_page = script.pages[0]
    if asset is not None:
        photo = (
            '<div class="photo">'
            f'<img src="{_esc(asset.name)}">'
            f'<div class="stamp">CASE {script.slug.upper()[:14]}</div>'
            "</div>"
        )
    else:
        photo = (
            '<div class="photo empty">'
            '<div class="label">封面档案图待补</div>'
            f'<div class="query">检索关键词：{_esc(cover_page.image_query)}</div>'
            "</div>"
        )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<style>{_css(cfg)}</style></head>
<body><div class="cover">
  {NOISE_SVG.format(opacity="0.22")}
  <div class="brandline">{_esc(brand['masthead'])} · {_esc(brand['column'])}</div>
  <div class="hook">{_esc(script.hook_title)}</div>
  <div class="caseline">{_esc(script.meta_line)}</div>
  <div class="divider"></div>
  {photo}
  <div class="footerbar"><span class="dot"></span>{_esc(brand['masthead'])}</div>
  <div class="ai-mark">{AI_MARK}</div>
</div></body></html>"""


def build_page_html(
    script: CaseScript,
    page: Page,
    index: int,
    total: int,
    case_no: int,
    cfg: dict[str, Any],
    asset: Path | None,
) -> str:
    brand = cfg["brand"]
    body = "".join(f"<p>{_esc(line)}</p>" for line in page.body_lines)
    headline = f'<h1 class="headline">{_esc(page.headline)}</h1>' if page.headline else ""
    rule = '<div class="rule"></div>' if page.headline else ""
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<style>{_css(cfg)}</style></head>
<body><div class="page {page.kind}">
  <header class="masthead">
    <span class="mark"></span><span class="brand">{_esc(brand['masthead'])}</span>
    <span class="column">{_esc(brand['column'])}</span>
  </header>
  <div class="caseline">CASE {case_no:02d} · {_esc(script.meta_line)}</div>
  {headline}{rule}
  <div class="body">{body}</div>
  {_figure_html(page, asset)}
  <footer>
    <span>{_esc(brand['masthead'])} · {_esc(brand['masthead_en'])} · ISSUE {brand['issue']:02d}</span>
    <span class="pageno">{index:02d} / {total:02d}</span>
  </footer>
  <div class="ai-mark">{AI_MARK}</div>
</div></body></html>"""


def _css(cfg: dict[str, Any]) -> str:
    v = cfg["visual"]
    variables = (
        ":root{"
        f"--paper:{v['paper']};--ink:{v['ink']};--accent:{v['accent']};"
        f"--muted:{v['muted']};--cover-bg:{v['cover_bg']};"
        "}"
    )
    return variables + (TEMPLATES / "base.css").read_text(encoding="utf-8")


def render_case(
    script: CaseScript,
    cfg: dict[str, Any],
    case_no: int,
    assets_dir: Path,
    out_dir: Path,
) -> list[Path]:
    """渲染全部页面，返回按顺序排列的 PNG 路径。"""
    html_dir = out_dir / "html"
    pages_dir = out_dir / "pages"
    for directory in (html_dir, pages_dir):
        directory.mkdir(parents=True, exist_ok=True)

    total = len(script.pages)
    width = cfg["video"]["width"]
    height = cfg["video"]["height"]

    html_files: list[Path] = []
    for i, page in enumerate(script.pages, start=1):
        asset = find_asset(assets_dir, i)
        # 图片与 HTML 必须同目录，file:// 下相对路径才解析得到
        if asset is not None:
            shutil.copy2(asset, html_dir / asset.name)
        if page.kind == "cover":
            html = build_cover_html(script, cfg, asset)
        else:
            html = build_page_html(script, page, i, total, case_no, cfg, asset)
        path = html_dir / f"p{i:02d}.html"
        path.write_text(html, encoding="utf-8")
        html_files.append(path)

    png_files: list[Path] = []
    launch_kwargs: dict[str, Any] = {"args": ["--no-sandbox", "--font-render-hinting=none"]}
    executable = _chromium_executable()
    if executable:
        launch_kwargs["executable_path"] = executable

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        page_ctx = browser.new_page(viewport={"width": width, "height": height})
        for i, html_path in enumerate(html_files, start=1):
            page_ctx.goto(html_path.as_uri())
            page_ctx.wait_for_timeout(120)  # 给字体与滤镜一点落地时间
            png = pages_dir / f"p{i:02d}.png"
            page_ctx.screenshot(path=str(png))
            png_files.append(png)
        browser.close()

    return png_files
