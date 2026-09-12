"""到公版图库检索配图候选。

只做到「自动检索 + 自动过滤 + 生成候选」，最后一步定稿必须人来点。
原因很直接：Commons 上的授权字段是上传者自己填的，存在填错的情况。
自动信任一个陌生人填的授权，等于把侵权风险外包出去。

检索策略（按命中质量从高到低，全部跑一遍再合并去重）：

1. **维基百科条目用图** —— 精度最高。条目编辑者已经替你挑过一轮，
   而且**必须带上事发国语言的条目**：历史照片的文件名常是当地语言
   （如 `Фото членов тургруппы Игоря Дятлова.jpg`），英文关键词永远搜不到它。
2. **Commons 分类** —— 比关键词检索准得多，一个分类就是一个事件的全部素材。
3. **Commons 关键词检索** —— 兜底。注意全文检索对词做 AND，
   5 个词以上通常一条都匹配不到，所以 query 要短。
4. **NASA 图像库** —— 只对地貌/航拍/卫星这类空镜有用，公有领域。

拿到候选后还要过一道「这张图能不能看」：档案馆里大量是卷宗扫描件，
授权干净但作为竖屏视频配图毫无用处。判别见 `looks_like_photo`。
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
NASA_API = "https://images-api.nasa.gov/search"
UA = "polar-archive/0.1 (https://github.com/Lai-Yanjun/shipinhao; content pipeline)"

# 只接受这些授权。宁可漏，不可错。
ALLOWED_KEYWORDS = ("public domain", "cc0", "cc by")
DENY_KEYWORDS = ("fair use", "non-free", "nonfree", "unknown")

# 进片格式：find_asset 只认这几种
RASTER_MIMES = ("image/jpeg", "image/png", "image/webp")
# SVG 不直接进片，但 Commons 的 Special:FilePath 带 ?width= 会栅格化成 PNG，
# 所以矢量地图不该丢 —— 一个事件分类里常有十几张现成的地形/路线图。
VECTOR_MIMES = ("image/svg+xml",)
FILEPATH = "https://commons.wikimedia.org/wiki/Special:FilePath/"


def rasterized(title: str, width: int = 1600) -> str:
    """把 Commons 文件名转成栅格化 URL。SVG 会被服务端渲染成 PNG。"""
    return f"{FILEPATH}{urllib.parse.quote(title.replace(' ', '_'))}?width={width}"

# 维基条目里的界面元件与地图挂件，不是配图
JUNK_PATTERNS = (
    "commons-logo", "oojs", "notification-icon", "wikiquote", "wikidata",
    "image-silk", "images.png", "pog.svg", "location map", "pozkarta",
    "relief-", "locator", "flag of", "coat of arms", "youtube",
    "edit-ltr", "ambox", "question_book", "wiki letter",
)

# 节流按域名分开：API 有限流，图片 CDN 没有。
# 早先一刀切成 1.1 秒，几十张缩略图就白等几十秒。
_last_request: dict[str, float] = {}
API_INTERVAL = 1.1      # Commons/维基 API：匿名约 1 次/秒，快了就 429
CDN_INTERVAL = 0.05     # upload.wikimedia.org 等图片 CDN，不限流
API_HOSTS = ("commons.wikimedia.org", "images-api.nasa.gov")


def _interval(host: str) -> float:
    if host.endswith(".wikipedia.org") or host in API_HOSTS:
        return API_INTERVAL
    return CDN_INTERVAL


def _ssl_context() -> ssl.SSLContext:
    """python.org 版 macOS Python 默认不挂系统根证书，握手会直接失败。
    有 certifi 就用 certifi，没有就退回默认（Linux/Homebrew 上本来就是好的）。"""
    try:
        import certifi
    except ModuleNotFoundError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


SSL_CONTEXT = _ssl_context()


@dataclass
class Candidate:
    title: str
    file_url: str
    thumb_url: str
    license: str
    author: str
    taken: str
    descr_url: str
    source: str = "commons"          # 来源标记，写进 assets.yaml 备查
    mime: str = ""
    width: int = 0
    height: int = 0
    kind: str = "photo"              # photo | map，两者的判别与用途都不同
    notes: list[str] = field(default_factory=list)   # 过滤过程中的观察，展示给人看

    @property
    def acceptable(self) -> bool:
        text = self.license.lower()
        if any(bad in text for bad in DENY_KEYWORDS):
            return False
        return any(k in text for k in ALLOWED_KEYWORDS)

    @property
    def share_alike(self) -> bool:
        """CC BY-SA 有传染性：用在视频里，理论上要求成品也按 SA 授权。
        不拦，但必须让人看见 —— 上一版把它混在 `cc by` 里静默放行了。"""
        return "-sa" in self.license.lower() or "share" in self.license.lower()

    @property
    def needs_attribution(self) -> bool:
        return "cc by" in self.license.lower()


def _get(url: str, headers: dict[str, str] | None = None, tries: int = 4) -> bytes:
    """带节流与 429 退避的 GET。429 是限流不是出网限制，要分开报。"""
    host = urllib.parse.urlparse(url).netloc
    interval = _interval(host)
    for attempt in range(tries):
        wait = interval - (time.monotonic() - _last_request.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=45, context=SSL_CONTEXT) as response:
                _last_request[host] = time.monotonic()
                return response.read()
        except urllib.error.HTTPError as exc:
            _last_request[host] = time.monotonic()
            if exc.code in (429, 503) and attempt < tries - 1:
                time.sleep(2 ** attempt * 3)
                continue
            raise ConnectionError(f"HTTP {exc.code} {exc.reason} — {url[:90]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            _last_request[host] = time.monotonic()
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, ssl.SSLCertVerificationError):
                raise ConnectionError(
                    "本机 Python 找不到 CA 根证书。装一下 certifi：pip install certifi，"
                    "或跑 Install Certificates.command"
                ) from exc
            if attempt < tries - 1:
                time.sleep(2 ** attempt)
                continue
            raise ConnectionError(
                f"连不上 {urllib.parse.urlparse(url).netloc}：{exc}。"
                "云端环境通常有出网限制，这一步请在本地机器上跑。"
            ) from exc
    raise ConnectionError(f"重试 {tries} 次仍失败：{url[:90]}")


def _api(base: str, params: dict[str, str]) -> dict:
    url = f"{base}?{urllib.parse.urlencode({**params, 'format': 'json'})}"
    return json.loads(_get(url))


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


def _is_junk(title: str) -> bool:
    low = title.lower()
    return any(pattern in low for pattern in JUNK_PATTERNS)


def _to_candidate(page: dict, source: str) -> Candidate | None:
    info = (page.get("imageinfo") or [{}])[0]
    mime = info.get("mime", "")
    title = page.get("title", "")
    for prefix in ("File:", "Файл:", "Datei:", "Fichier:"):
        title = title.removeprefix(prefix)
    if _is_junk(title):
        return None
    meta = info.get("extmetadata", {})
    get = lambda key: _strip_html((meta.get(key) or {}).get("value", ""))
    is_vector = mime in VECTOR_MIMES
    return Candidate(
        title=title,
        file_url=rasterized(title) if is_vector else info.get("url", ""),
        thumb_url=(rasterized(title, 900) if is_vector
                   else info.get("thumburl") or info.get("url", "")),
        license=get("LicenseShortName") or (meta.get("License") or {}).get("value", ""),
        author=get("Artist") or "未署名",
        taken=get("DateTimeOriginal")[:40] or get("DateTime")[:40],
        descr_url=info.get("descriptionurl", ""),
        source=source,
        mime=mime,
        width=info.get("width", 0),
        height=info.get("height", 0),
        kind="map" if is_vector else "photo",
    )


def _harvest(base: str, params: dict[str, str], source: str, thumb_width: int) -> list[Candidate]:
    data = _api(base, {
        **params,
        "action": "query",
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime|size",
        "iiurlwidth": str(thumb_width),
    })
    pages = (data.get("query") or {}).get("pages", {})
    out = []
    for page in pages.values():
        candidate = _to_candidate(page, source)
        if candidate is not None:
            out.append(candidate)
    return out


# ---------------------------------------------------------------- 各来源

def wiki_article_images(ref: str, thumb_width: int = 900) -> list[Candidate]:
    """维基百科条目里用到的图。ref 格式 `en:Dyatlov Pass incident`。

    精度最高的一路：条目编辑者已经挑过一轮，而且本国语言条目会带出
    英文检索永远搜不到的当地语言文件名。
    """
    lang, _, title = ref.partition(":")
    if not title:
        lang, title = "en", ref
    base = f"https://{lang}.wikipedia.org/w/api.php"
    return _harvest(
        base,
        {"generator": "images", "titles": title, "gimlimit": "60"},
        f"wiki:{lang}",
        thumb_width,
    )


def commons_category(category: str, limit: int = 60, thumb_width: int = 900) -> list[Candidate]:
    """Commons 分类下的全部文件。比关键词检索准得多。"""
    return _harvest(
        COMMONS_API,
        {
            "generator": "categorymembers",
            "gcmtitle": f"Category:{category}",
            "gcmtype": "file",
            "gcmlimit": str(limit),
        },
        "commons:category",
        thumb_width,
    )


# 检索词里这些词不具区分度，判相关性时不算数
STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "and", "photo", "photos",
    "photograph", "photographs", "image", "images", "picture", "map",
    "site", "camp", "view", "scene", "last", "first",
}


def _relevant(title: str, words: list[str]) -> bool:
    """全文检索会把只在文件描述里蹭到词的东西也返回来 ——
    实测查「Dyatlov Pass last photographs February 1959 camp」
    返回了 1941 年的《共青团真理报》版面。要求文件名里至少出现一个
    有区分度的检索词，把这类蹭词结果挡掉。"""
    key = [w.lower() for w in words if w.lower() not in STOPWORDS and len(w) > 2]
    if not key:
        return True
    low = title.lower()
    return any(w in low for w in key)


def commons_search(query: str, limit: int = 20, thumb_width: int = 900) -> list[Candidate]:
    """Commons 全文检索。**query 要短** —— 全文检索对词做 AND，
    5 个词以上通常返回 0 条。词多了自动退化重试。
    结果再过一道文件名相关性，挡掉蹭词的无关素材。"""
    words = query.split()
    for attempt in (words, words[:4], words[:3], words[:2]):
        if not attempt:
            break
        found = _harvest(
            COMMONS_API,
            {
                "generator": "search",
                "gsrsearch": " ".join(attempt),
                "gsrnamespace": "6",
                "gsrlimit": str(limit),
            },
            "commons:search",
            thumb_width,
        )
        if found:
            relevant = [c for c in found if _relevant(c.title, attempt)]
            if len(attempt) < len(words):
                for c in relevant:
                    c.notes.append(f"原 query 无结果，退化为「{' '.join(attempt)}」")
            if relevant:
                return relevant
    return []


def nasa_search(query: str, limit: int = 8) -> list[Candidate]:
    """NASA 图像库，公有领域。只对地貌/航拍/卫星空镜有用。"""
    url = f"{NASA_API}?{urllib.parse.urlencode({'q': query, 'media_type': 'image'})}"
    try:
        items = json.loads(_get(url))["collection"]["items"][:limit]
    except (ConnectionError, KeyError, json.JSONDecodeError):
        return []
    out = []
    for item in items:
        data = (item.get("data") or [{}])[0]
        links = item.get("links") or [{}]
        thumb = links[0].get("href", "")
        if not thumb:
            continue
        out.append(Candidate(
            title=data.get("title", "")[:80],
            file_url=thumb,
            thumb_url=thumb,
            license="Public domain",       # NASA 影像默认公有领域，仍需逐条看说明
            author=data.get("center", "NASA"),
            taken=(data.get("date_created") or "")[:10],
            descr_url=f"https://images.nasa.gov/details/{data.get('nasa_id', '')}",
            source="nasa",
            mime="image/jpeg",
            notes=["NASA 影像默认公有领域，但仍需看说明页确认无第三方权利"],
        ))
    return out


# ---------------------------------------------------------------- 能不能看

def looks_like_photo(path: Path, kind: str = "photo") -> tuple[bool, str]:
    """判断这张图是不是「能看的照片」，而不是卷宗扫描件。

    档案馆里大量是手写文书扫描件：授权干净，但竖屏视频里观众看不清也看不懂。
    判别式是「纸是白的」—— 平均亮度高且几乎没有暗部。

    **不要用饱和度判别**：历史照片多是黑白的，实测那张 1959 年帐篷现场
    饱和度只有 7.7，是全场最低，用饱和度会把最该留的那张杀掉。
    """
    try:
        from PIL import Image, ImageStat
    except ModuleNotFoundError:
        return True, "未装 Pillow，跳过图像判别"

    with Image.open(path) as im:
        im = im.convert("RGB")
        width, height = im.size
        grey = im.convert("L")
        luma = ImageStat.Stat(grey).mean[0]
        histogram = grey.histogram()
        dark = sum(histogram[:90]) / max(sum(histogram), 1)

    if width < 400 or height < 400:
        return False, f"尺寸过小 {width}×{height}"
    if kind == "map":
        # 地图本来就是白底线稿，「纸是白的」这条对它不成立 —— 用它判会全军覆没
        return True, f"矢量地图，已栅格化 {width}×{height}"
    if luma > 170 and dark < 0.20:
        return False, f"疑似文书扫描件（亮度 {luma:.0f}，暗部仅 {dark:.0%}）"
    return True, f"{width}×{height}，亮度 {luma:.0f}，暗部 {dark:.0%}"


# ---------------------------------------------------------------- 汇总

def collect(
    queries: list[str],
    wiki_refs: list[str] | None = None,
    categories: list[str] | None = None,
    use_nasa: bool = False,
    thumb_width: int = 900,
    max_searches: int = 3,
) -> tuple[list[Candidate], list[str]]:
    """按精度从高到低跑各来源，按授权与格式过滤，去重后返回候选池与一份日志。

    关键词检索放在最后且**限量跑**：实测维基条目 + 分类贡献 19 张，
    9 条关键词 query 只贡献 2 张，却占了绝大部分请求量并因此触发 429。
    限到 max_searches 条，既拿到长尾又不把配额烧在重复结果上。
    """
    log: list[str] = []
    pool: dict[str, Candidate] = {}

    def take(items: list[Candidate], label: str) -> None:
        kept = 0
        for c in items:
            if c.mime and c.mime not in RASTER_MIMES + VECTOR_MIMES:
                continue
            if not c.acceptable:
                continue
            if c.title not in pool:
                pool[c.title] = c
                kept += 1
        log.append(f"  {label:<38} 返回 {len(items):>3} → 新增 {kept}")

    for ref in wiki_refs or []:
        try:
            take(wiki_article_images(ref, thumb_width), f"维基条目 {ref}")
        except ConnectionError as exc:
            log.append(f"  维基条目 {ref} 失败：{exc}")

    for cat in categories or []:
        try:
            take(commons_category(cat, thumb_width=thumb_width), f"Commons 分类 {cat}")
        except ConnectionError as exc:
            log.append(f"  Commons 分类 {cat} 失败：{exc}")

    distinct = list(dict.fromkeys(q for q in queries if q))
    for query in distinct[:max_searches]:
        try:
            take(commons_search(query, thumb_width=thumb_width), f"Commons 检索「{query}」")
        except ConnectionError as exc:
            log.append(f"  Commons 检索「{query}」失败：{exc}")
    if len(distinct) > max_searches:
        log.append(
            f"  其余 {len(distinct) - max_searches} 条关键词检索跳过 "
            f"（限 {max_searches} 条，避免触发 Commons 限流）"
        )

    if use_nasa:
        for query in dict.fromkeys(q for q in queries if q):
            try:
                take(nasa_search(query), f"NASA「{query}」")
            except ConnectionError as exc:
                log.append(f"  NASA「{query}」失败：{exc}")

    return list(pool.values()), log


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_get(url))
    return dest


def contact_sheet(candidates: list[Candidate], review_dir: Path, slug: str) -> Path:
    """候选图一览，用浏览器打开后挑选。

    授权、作者、来源直接标在图下，SA 与署名义务单独高亮 —— 这些是你终审要看的东西。
    """
    cards = []
    for i, c in enumerate(candidates, start=1):
        flags = []
        if c.share_alike:
            flags.append('<b class="warn">SA 传染性</b>')
        if c.needs_attribution:
            flags.append('<b class="warn">需署名</b>')
        notes = "".join(f"<div class=note>{n}</div>" for n in c.notes)
        cards.append(
            f'<figure><img src="thumbs/{i:03d}.jpg" loading="lazy">'
            f'<figcaption><b>#{i}</b> <span class=src>{c.source}</span><br>'
            f'<span class=t>{c.title[:60]}</span><br>'
            f'{c.license} · {c.author[:40]}<br>'
            f'<span class=dim>{c.taken}</span>{" ".join(flags)}{notes}<br>'
            f'<a href="{c.descr_url}" target="_blank">原始页面</a></figcaption></figure>'
        )
    html = f"""<!doctype html><meta charset="utf-8"><title>候选配图 · {slug}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:40px;background:#fafaf8;color:#141414}}
h1{{border-bottom:3px solid #1B6B8C;padding-bottom:10px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:22px;margin-top:24px}}
figure{{margin:0;background:#fff;padding:12px;border:1px solid #e4e4de}}
img{{width:100%;height:210px;object-fit:cover;background:#eee}}
figcaption{{font-size:13px;line-height:1.65;margin-top:8px;color:#555}}
.t{{color:#141414;font-weight:600}}
.src{{background:#1B6B8C;color:#fff;padding:1px 6px;border-radius:3px;font-size:11px}}
.dim{{color:#8a8a85}}
.warn{{color:#B4451F;margin-left:6px}}
.note{{color:#8a8a85;font-size:12px;font-style:italic}}
.cmd{{background:#fff;border-left:4px solid #1B6B8C;padding:12px 16px;font-size:14px;margin-top:28px}}
</style>
<h1>候选配图 · {slug} <span style="font-size:15px;font-weight:400;color:#666">
（{len(candidates)} 张已过授权与「能不能看」两道过滤）</span></h1>
<p>Commons 的授权字段由上传者填写，可能有误。点「原始页面」核对后再选。
标了 <b class="warn">SA 传染性</b> 的用在视频里理论上要求成品同样按 SA 授权，慎用。</p>
<div class=grid>{''.join(cards)}</div>
<p class=cmd>选定后执行：<code>python cli.py pick --slug {slug} --page &lt;页码&gt; --choice &lt;#&gt;</code><br>
会下原图到 <code>topics/assets/{slug}/pNN.jpg</code>，并自动把来源与授权写进 <code>assets.yaml</code>。</p>"""
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path
