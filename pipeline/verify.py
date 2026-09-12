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


def run(script: CaseScript, assets_dir: Path) -> Report:
    report = Report()
    report.checks.append(check_hook(script))
    report.checks.append(check_structure(script))
    report.checks.extend(check_assets(script, assets_dir))
    # 这两项机器判断不了，必须人看
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
