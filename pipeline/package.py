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

# 平台曲库里的搜索方向，按情绪标签给
_BGM_KEYWORDS = {
    "cold": "极寒 / 风声 / 空旷 / ambient cold",
    "tension": "悬疑 / 低频推进 / 心跳 / dark tension",
    "grief": "哀悼 / 弦乐收束 / 钢琴独奏 / melancholy",
    "archive": "纪录片 / 档案 / 克制 / documentary neutral",
}


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


def write_assets_todo(script: CaseScript, out_dir: Path) -> Path:
    """生成配图任务单骨架。

    只生成骨架，不填内容 —— 检索与授权核验由会话完成（见 archive-case 技能）。
    代码不该假装自己核实过授权。
    """
    blocks = []
    for i, page in enumerate(script.pages, start=1):
        if not (page.image_query or page.image_caption):
            continue
        blocks.append(
            f"""### 第 {i} 页

- 图注：{page.image_caption or '（无）'}
- 检索关键词：`{page.image_query}`
- 候选：
- 原始页面：
- 授权：
- 授权依据（在哪看到的）：
- 为什么选它：
- 存为：`topics/assets/{script.slug}/p{i:02d}.jpg`
"""
        )
    content = f"""# 配图任务单 · {script.case_title}

云端会话搜得到、读得到授权信息，但**下载不了文件** —— 实测所有图片站
（upload.wikimedia.org、archive.org、pexels 等）均被出网策略拦截，只有 GitHub 可达。

所以流程是 **git 中转**：你在本地照单下载 → 提交进仓库 → 云端 pull 下来渲染。

## 下载方法

Commons 用 `Special:FilePath` 取文件，不需要知道哈希路径；
带 `?width=` 还会把 SVG 自动栅格化成 PNG：

```bash
mkdir -p topics/assets/{script.slug}
curl -L -o topics/assets/{script.slug}/p0N.jpg \\
  "https://commons.wikimedia.org/wiki/Special:FilePath/<文件名>?width=1600"
```

下完提交推送，云端就能用：

```bash
git add topics/assets/{script.slug}/ && git commit -m "CASE 素材" && git push
```

## 授权判断规则

只收 Public Domain、CC0、CC BY、CC BY-SA。**逐张点开原始页面核对**，
不要只信搜索结果里的标注 —— Commons 的授权字段是上传者自己填的，存在填错的情况，
也存在文件页自己挂着「possible wrong license」的情况。

CC BY / CC BY-SA 需要署名，署名信息一并记进 `assets.yaml`。

下载完成后在 `topics/assets/{script.slug}/assets.yaml` 逐张登记，
否则 `python cli.py verify` 不会放行。

{''.join(blocks)}"""
    path = out_dir / "assets_todo.md"
    path.write_text(content, encoding="utf-8")
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

## 配乐

情绪标签：`{script.bgm_mood}`

**默认做法：成片出无声轨，发布时在 App 内选配乐。**

平台曲库是平台自己买的一揽子授权，你在 App 里选曲完全合法；
把 mp3 烧进视频再上传则不在该授权范围内 —— 观众看着一样，法律上是两回事。
用自家曲库还有流量倾斜。

App 内搜索方向：{_BGM_KEYWORDS.get(script.bgm_mood, '氛围 / 纪录片 / 低频')}

只有公众号长图那条线用不上平台曲库，或需要跨平台统一听感时，
才从 `assets/bgm/{script.bgm_mood}/` 取曲并 `--bgm` 指过去 ——
该目录只放你确认过商用授权的曲子，见 `assets/bgm/README.md`。

## 发布前清单

- [ ] 每页配图均来自公有领域或已获授权，来源已记入 topics/assets/{script.slug}/assets.yaml
- [ ] 图注中的时间、地点、机构与史料一致
- [ ] 文案无主观推测、无因果结论、未指控任何在世个人
- [ ] 发布时勾选平台的「内容由 AI 生成」声明
- [ ] 配乐在 App 内从平台曲库选择，未把外部音频烧进成片
- [ ] 封面钩子未使用事件学名
"""
    path = out_dir / "copy.md"
    path.write_text(content, encoding="utf-8")
    return path
