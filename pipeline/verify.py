"""发布前校验。

四项检查对应四种不同的翻车方式：事实错误会被判造谣，素材无授权要赔钱，
合规风险会被限流，钩子用了事件学名则根本没人点。
任何一项不过就不分配编号 —— 这是流水线上唯一的人工闸门，不能自动化掉。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import CaseScript

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
# 钩子里出现这些词，说明写成了事件学名而不是具体动作
HOOK_BANNED = ("事件", "之谜", "谜案", "悬案", "真相", "揭秘", "震惊")
# 版面预算：1080px 宽减去两侧 96px 留白，46px 字号约容 19 个汉字，留一字余量。
# 超出会折行，折行会把图注和页脚挤出页面。
MAX_CHARS_PER_LINE = 21
MAX_LINES_PER_PAGE = 8
MAX_HEADLINE_CHARS = 12
# 替观众下情绪结论的词。对标样本里一个都没有。
BANNED_WORDS = ("震惊", "细思极恐", "毛骨悚然", "不寒而栗", "骇人听闻", "令人发指", "真相竟然")
# 自我指涉。我们没有主播，页面上出现这些等于把黄金位置让给废话 ——
# 对标样本里写得最差的几条开场全栽在这里。
SELF_REFERENCE = ("本期", "本栏目", "这期", "欢迎来到", "大家好", "今天给大家")

# 内页图框约 1080×620。object-fit: cover 会按这个比例裁切，
# 原图越接近方形或竖版，裁掉的越多。
TARGET_ASPECT = 1080 / 620
MIN_RETAINED = 0.70          # 保留不足七成算警告
BLOCK_RETAINED = 0.50        # 保留不足一半直接卡住
MIN_WIDTH, MIN_HEIGHT = 1080, 620


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    needs_human: bool = False


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)

    @property
    def blocking(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    @property
    def human_items(self) -> list[Check]:
        return [c for c in self.checks if c.needs_human]


def check_assets(script: CaseScript, assets_dir: Path) -> list[Check]:
    """每张进片的图都必须在 assets.yaml 里登记来源与授权。"""
    needed = [
        i
        for i, page in enumerate(script.pages, start=1)
        if page.image_query or page.image_caption
    ]
    present = {
        i: next(
            (assets_dir / f"p{i:02d}{e}" for e in IMAGE_EXTS
             if (assets_dir / f"p{i:02d}{e}").exists()),
            None,
        )
        for i in needed
    }
    missing = [i for i, p in present.items() if p is None]
    if missing:
        return [Check("素材齐备", False, f"第 {missing} 页缺配图")]

    manifest = assets_dir / "assets.yaml"
    if not manifest.exists():
        return [Check("素材授权登记", False, f"缺 {manifest}，见 docs/compliance.md")]

    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    registered = {entry.get("file"): entry for entry in (data.get("assets") or [])}

    unregistered, incomplete = [], []
    for path in present.values():
        entry = registered.get(path.name)
        if entry is None:
            unregistered.append(path.name)
        elif not all(entry.get(k) for k in ("source_url", "license", "checked_at")):
            incomplete.append(path.name)

    checks = [Check("素材齐备", True, f"{len(present)} 页配图到位")]
    if unregistered:
        checks.append(Check("素材授权登记", False, f"未登记：{unregistered}"))
    elif incomplete:
        checks.append(
            Check("素材授权登记", False, f"登记不完整（缺来源/授权/核查日期）：{incomplete}")
        )
    else:
        checks.append(Check("素材授权登记", True, f"{len(registered)} 张已登记"))
    return checks


def check_hook(script: CaseScript) -> Check:
    hit = [w for w in HOOK_BANNED if w in script.hook_title]
    if hit:
        return Check(
            "封面钩子", False,
            f"「{script.hook_title}」含 {hit} —— 钩子要写具体动作，不写事件学名",
        )
    if not 4 <= len(script.hook_title) <= 10:
        return Check("封面钩子", False, f"「{script.hook_title}」长度应在 4-10 字")
    return Check("封面钩子", True, script.hook_title)


def check_structure(script: CaseScript) -> Check:
    kinds = [p.kind for p in script.pages]
    if "contradiction" not in kinds:
        return Check("叙事结构", False, "缺逻辑空洞页 —— 这是整条视频的命门")
    # 过渡页检测：正文行数过少的事实页说明这一页没有承载爆点
    thin = [
        i for i, p in enumerate(script.pages, start=1)
        if p.kind in ("fact", "coordinate", "contradiction") and len(p.body_lines) < 3
    ]
    if thin:
        return Check("叙事结构", False, f"第 {thin} 页正文过薄，疑似过渡页")
    return Check("叙事结构", True, f"{len(kinds)} 页，结构完整")


def check_layout(script: CaseScript) -> Check:
    """版面预算。超了不是不好看 —— 是图注和页脚会被挤出页面。"""
    problems = []
    for i, page in enumerate(script.pages, start=1):
        if len(page.headline) > MAX_HEADLINE_CHARS:
            problems.append(f"第 {i} 页标题 {len(page.headline)} 字，超出 {MAX_HEADLINE_CHARS}")
        if len(page.body_lines) > MAX_LINES_PER_PAGE:
            problems.append(f"第 {i} 页 {len(page.body_lines)} 行，超出 {MAX_LINES_PER_PAGE} 行")
        for line in page.body_lines:
            if len(line) > MAX_CHARS_PER_LINE:
                problems.append(f"第 {i} 页「{line[:12]}…」{len(line)} 字，超出 {MAX_CHARS_PER_LINE}")
    if problems:
        return Check("版面预算", False, "；".join(problems[:4]))
    return Check("版面预算", True, f"标题 ≤{MAX_HEADLINE_CHARS} 字，每页 ≤{MAX_LINES_PER_PAGE} 行，每行 ≤{MAX_CHARS_PER_LINE} 字")


def check_words(script: CaseScript) -> Check:
    """两类词：替观众下情绪结论的，和把版面让给废话的。"""
    hits = []
    for i, page in enumerate(script.pages, start=1):
        # cta 页允许引导互动，但仍不许自报家门
        banned = BANNED_WORDS + SELF_REFERENCE
        for line in [page.headline, *page.body_lines]:
            hits += [f"第 {i} 页「{w}」" for w in banned if w in line]
    if hits:
        return Check("禁用词", False, "；".join(hits))
    return Check("禁用词", True, "无情绪结论词、无自我指涉")


def check_crop(script: CaseScript, assets_dir: Path) -> Check:
    """裁切损失与分辨率。

    图会被 cover 裁成约 1080×620。竖图进来上下裁掉大半，主体常常整个没了；
    原图小于成图尺寸则满幅铺开必糊。这两件事渲染完才看得出来，用机器提前拦。
    """
    try:
        from PIL import Image
    except ModuleNotFoundError:
        return Check("裁切与分辨率", True, "未装 Pillow，跳过")

    problems, notes = [], []
    for i, page in enumerate(script.pages, start=1):
        asset = next(
            (assets_dir / f"p{i:02d}{e}" for e in IMAGE_EXTS
             if (assets_dir / f"p{i:02d}{e}").exists()),
            None,
        )
        if asset is None:
            continue
        with Image.open(asset) as im:
            width, height = im.size
        aspect = width / height
        retained = (TARGET_ASPECT / aspect) if aspect > TARGET_ASPECT else (aspect / TARGET_ASPECT)

        if retained < BLOCK_RETAINED:
            problems.append(f"第 {i} 页 {width}×{height} 裁切后只剩 {retained:.0%}")
        elif retained < MIN_RETAINED:
            notes.append(f"第 {i} 页裁切后剩 {retained:.0%}，主体须在中央横带上")
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            problems.append(f"第 {i} 页 {width}×{height} 低于 {MIN_WIDTH}×{MIN_HEIGHT}，会糊")

    if problems:
        return Check("裁切与分辨率", False, "；".join(problems))
    return Check("裁切与分辨率", True, "；".join(notes) or "全部达标")


def check_caption_match(script: CaseScript, assets_dir: Path) -> Check:
    """图注与配图是否相符 —— 只能人看。

    图注是在配图之前写的，之后才把图挂上去，中间没有任何环节检查两者是否一致。
    实测踩过：图注写「出发前的队伍合影，1959年1月」，实际配的是 2012 年拍的
    纪念碑肖像；图注写「卷宗中的现场位置示意」，实际配的是卷宗封面。
    这类错误恰好撞在 docs/compliance.md 的第一条红线上（不编造细节），
    机器判断不了图里是什么，所以列为强制人工项，把每一对图注/文件名摆出来对照。
    """
    pairs = []
    for i, page in enumerate(script.pages, start=1):
        if not page.image_caption:
            continue
        asset = next(
            (assets_dir / f"p{i:02d}{e}" for e in IMAGE_EXTS
             if (assets_dir / f"p{i:02d}{e}").exists()),
            None,
        )
        if asset is None:
            continue
        source = "（assets.yaml 未登记）"
        manifest = assets_dir / "assets.yaml"
        if manifest.exists():
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            entry = next(
                (a for a in (data.get("assets") or []) if a.get("file") == asset.name),
                None,
            )
            if entry:
                source = entry.get("note") or entry.get("source_url", "")
        pairs.append(f"      · 第 {i} 页 图注「{page.image_caption}」\n        配图 {source}")
    if not pairs:
        return Check("图注与配图相符", True, "无配图页", needs_human=False)
    return Check("图注与配图相符", True, "\n".join(pairs), needs_human=True)


def run(script: CaseScript, assets_dir: Path) -> Report:
    report = Report()
    report.checks.append(check_hook(script))
    report.checks.append(check_structure(script))
    report.checks.append(check_layout(script))
    report.checks.append(check_words(script))
    report.checks.extend(check_assets(script, assets_dir))
    report.checks.append(check_crop(script, assets_dir))
    report.checks.append(check_caption_match(script, assets_dir))
    # 以下几项机器判断不了，必须人看
    report.checks.append(
        Check(
            "事实核查", True,
            "\n".join(f"      · {n}" for n in script.fact_notes),
            needs_human=True,
        )
    )
    report.checks.append(
        Check(
            "合规自检", True,
            "\n".join(f"      · {r}" for r in script.risk_flags),
            needs_human=True,
        )
    )
    return report
