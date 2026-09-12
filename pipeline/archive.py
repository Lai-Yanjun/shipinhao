"""归档台账。

CASE 编号在校验通过时才分配，不在生成时分配 —— 这样编号永远连续，废稿不占号。
台账是这条流水线唯一的事实来源：哪期过了校验、编号多少、发到哪了、链接是什么。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import yaml

from .config import ROOT

ARCHIVE = ROOT / "archive"
INDEX = ARCHIVE / "index.yaml"


def load_index() -> dict[str, Any]:
    if not INDEX.exists():
        return {"next_case_no": 1, "cases": []}
    return yaml.safe_load(INDEX.read_text(encoding="utf-8")) or {
        "next_case_no": 1,
        "cases": [],
    }


def save_index(index: dict[str, Any]) -> None:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(
        yaml.safe_dump(index, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def find_case(index: dict[str, Any], slug: str) -> dict[str, Any] | None:
    for case in index["cases"]:
        if case["slug"] == slug:
            return case
    return None


def register(
    slug: str,
    case_title: str,
    hook_title: str,
    verified_by: str,
) -> tuple[dict[str, Any], bool]:
    """登记一期并分配编号。已登记过的直接返回原记录，编号不变。"""
    index = load_index()
    existing = find_case(index, slug)
    if existing is not None:
        return existing, False

    case = {
        "case_no": index["next_case_no"],
        "slug": slug,
        "case_title": case_title,
        "hook_title": hook_title,
        "status": "verified",
        "verified_at": date.today().isoformat(),
        "verified_by": verified_by,
        "published": [],
    }
    index["cases"].append(case)
    index["next_case_no"] += 1
    save_index(index)
    return case, True


def record_publish(slug: str, platform: str, url: str, published_at: str) -> dict[str, Any]:
    index = load_index()
    case = find_case(index, slug)
    if case is None:
        raise KeyError(f"台账里没有 {slug}，先跑 verify")
    case["published"] = [p for p in case["published"] if p["platform"] != platform]
    case["published"].append(
        {"platform": platform, "url": url, "published_at": published_at}
    )
    case["status"] = "published"
    save_index(index)
    return case


def case_dir(case_no: int, slug: str) -> Path:
    return ARCHIVE / f"CASE-{case_no:02d}-{slug}"
