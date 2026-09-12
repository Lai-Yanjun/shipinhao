"""到 Wikimedia Commons 检索公版配图。

只做到「自动检索 + 自动过滤 + 生成候选」，最后一步定稿必须人来点。
原因很直接：Commons 上的授权字段是上传者自己填的，存在填错的情况。
自动信任一个陌生人填的授权，等于把侵权风险外包出去。

注意：需要能访问 commons.wikimedia.org。云端环境常有 egress 限制，
这一步和发布一样，应当在你自己的机器上跑。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = "polar-archive/0.1 (content pipeline; contact via repository)"

# 只接受这些授权。宁可漏，不可错。
ALLOWED_PREFIXES = ("pd", "cc0", "cc-by")
ALLOWED_KEYWORDS = ("public domain", "cc0", "cc by")
DENY_KEYWORDS = ("fair use", "non-free", "nonfree", "unknown")


@dataclass
class Candidate:
    title: str
    file_url: str
    thumb_url: str
    license: str
    author: str
    taken: str
    descr_url: str

    @property
    def acceptable(self) -> bool:
        text = self.license.lower()
        if any(bad in text for bad in DENY_KEYWORDS):
            return False
        return any(k in text for k in ALLOWED_KEYWORDS) or text.startswith(ALLOWED_PREFIXES)


def _strip_html(value: str) -> str:
    out, depth = [], 0
    for ch in value:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(depth - 1, 0)
        elif depth == 0:
            out.append(ch)
    return " ".join("".join(out).split())


def _api(params: dict[str, str]) -> dict:
    url = f"{API}?{urllib.parse.urlencode({**params, 'format': 'json'})}"
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def search(query: str, limit: int = 8, thumb_width: int = 900) -> list[Candidate]:
    """按关键词检索，返回通过授权过滤的候选。网络不可达时抛 ConnectionError。"""
    try:
        data = _api({
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",           # 6 = File 命名空间
            "gsrlimit": str(limit * 2),    # 过滤会砍掉一批，多取一些
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": str(thumb_width),
        })
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ConnectionError(
            f"连不上 Wikimedia Commons：{exc}。"
            "云端环境通常有出网限制，这一步请在本地机器上跑。"
        ) from exc

    pages = (data.get("query") or {}).get("pages", {})
    candidates: list[Candidate] = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        if not info.get("mime", "").startswith("image/"):
            continue
        meta = info.get("extmetadata", {})
        get = lambda key: _strip_html((meta.get(key) or {}).get("value", ""))
        candidate = Candidate(
            title=page.get("title", "").removeprefix("File:"),
            file_url=info.get("url", ""),
            thumb_url=info.get("thumburl") or info.get("url", ""),
            license=get("LicenseShortName") or (meta.get("License") or {}).get("value", ""),
            author=get("Artist") or "未署名",
            taken=get("DateTimeOriginal")[:40],
            descr_url=info.get("descriptionurl", ""),
        )
        if candidate.acceptable:
            candidates.append(candidate)
        if len(candidates) >= limit:
            break
    return candidates


def download(url: str, dest: Path) -> Path:
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=60) as response:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(response.read())
    return dest


def contact_sheet(groups: dict[int, list[Candidate]], review_dir: Path) -> Path:
    """候选图九宫格，用浏览器打开后挑选。授权与作者直接标在图下，方便你终审。"""
    blocks = []
    for page_no, candidates in sorted(groups.items()):
        cards = "".join(
            f'<figure><img src="p{page_no:02d}/{i}.jpg">'
            f"<figcaption><b>选择 {i}</b><br>{c.license}<br>{c.author[:60]}<br>"
            f'<span>{c.taken}</span><br><a href="{c.descr_url}">原始页面</a></figcaption></figure>'
            for i, c in enumerate(candidates, start=1)
        )
        blocks.append(
            f"<section><h2>第 {page_no} 页</h2><div class=grid>{cards}</div>"
            f"<p class=cmd>选定后执行：<code>python cli.py pick --slug &lt;slug&gt; "
            f"--page {page_no} --choice N</code></p></section>"
        )
    html = f"""<!doctype html><meta charset="utf-8"><title>候选配图</title>
<style>
body{{font-family:system-ui,sans-serif;margin:40px;background:#fafaf8;color:#141414}}
h2{{border-bottom:3px solid #1B6B8C;padding-bottom:8px;margin-top:48px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:24px}}
figure{{margin:0;background:#fff;padding:12px;border:1px solid #e4e4de}}
img{{width:100%;height:220px;object-fit:cover}}
figcaption{{font-size:13px;line-height:1.6;margin-top:8px;color:#555}}
figcaption span{{color:#8a8a85}}
.cmd{{background:#fff;border-left:4px solid #1B6B8C;padding:12px 16px;font-size:14px}}
</style>
<h1>候选配图 — 授权需你终审</h1>
<p>Commons 的授权字段由上传者填写，可能有误。点「原始页面」核对后再选。</p>
{''.join(blocks)}"""
    path = review_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path
