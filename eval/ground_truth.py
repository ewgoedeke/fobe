#!/usr/bin/env python3
"""
ground_truth.py -- Schema and utilities for ground truth annotations.

Ground truth files live in eval/fixtures/<name>/ground_truth/toc.json.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class TocSection:
    label: str
    statement_type: str          # PNL, SFP, OCI, CFS, SOCIE, DISC.*
    start_page: int
    end_page: int | None = None
    note_number: str | None = None
    validated: bool = False


@dataclass
class TocGroundTruth:
    version: int = 1
    annotated_at: str = ""
    annotator: str = ""
    has_toc: bool = False         # whether the PDF contains a TOC table
    toc_table_id: str | None = None
    toc_pages: list[int] = field(default_factory=list)
    sections: list[TocSection] = field(default_factory=list)
    notes_start_page: int | None = None
    notes_end_page: int | None = None


def gt_dir(fixture_dir: str | Path) -> Path:
    return Path(fixture_dir) / "ground_truth"


def toc_gt_path(fixture_dir: str | Path) -> Path:
    return gt_dir(fixture_dir) / "toc.json"


def load_toc_gt(fixture_dir: str | Path) -> TocGroundTruth | None:
    """Load ground truth TOC from fixture dir, or None if not found."""
    p = toc_gt_path(fixture_dir)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            data = json.load(f)
        sections = [TocSection(**s) for s in data.pop("sections", [])]
        return TocGroundTruth(**data, sections=sections)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def save_toc_gt(fixture_dir: str | Path, gt: TocGroundTruth) -> Path:
    """Save ground truth TOC to fixture dir. Creates directory if needed."""
    p = toc_gt_path(fixture_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    gt.annotated_at = datetime.now(timezone.utc).isoformat()
    with open(p, "w") as f:
        json.dump(asdict(gt), f, indent=2, ensure_ascii=False)
    return p


def save_toc_gt_dict(fixture_dir: str | Path, data: dict) -> Path:
    """Save raw dict as ground truth TOC (from API). Adds timestamp."""
    p = toc_gt_path(fixture_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    data["annotated_at"] = datetime.now(timezone.utc).isoformat()
    data.setdefault("version", 1)
    with open(p, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return p


def load_toc_gt_dict(fixture_dir: str | Path) -> dict | None:
    """Load raw dict from ground truth TOC file."""
    p = toc_gt_path(fixture_dir)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def toc_gt_to_page_map(gt: TocGroundTruth) -> dict[int, str]:
    """Convert ground truth TOC to page->statementComponent map.

    This produces the same format as classify_tables._detect_toc(),
    so it can be used as a drop-in replacement in the pipeline.
    """
    page_map: dict[int, str] = {}
    for section in gt.sections:
        end = section.end_page or section.start_page
        for page in range(section.start_page, end + 1):
            page_map[page] = section.statement_type
    return page_map
