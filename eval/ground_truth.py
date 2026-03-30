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


# ── V2: Transition-based model ──────────────────────────────────────────────


@dataclass
class TransitionMarker:
    page: int
    section_type: str
    label: str = ""
    note_number: str | None = None
    source: str = "manual"         # manual | toc | detected | ref_edge
    validated: bool = False


@dataclass
class TocGroundTruthV2:
    version: int = 2
    annotated_at: str = ""
    annotator: str = ""
    has_toc: bool | None = None
    toc_pages: list[int] = field(default_factory=list)
    transitions: list[TransitionMarker] = field(default_factory=list)
    multi_tags: list[dict] = field(default_factory=list)


def v1_to_v2(v1: TocGroundTruth) -> TocGroundTruthV2:
    """Convert v1 section-range model to v2 transition-marker model."""
    transitions: list[TransitionMarker] = []
    for sec in sorted(v1.sections, key=lambda s: s.start_page):
        transitions.append(TransitionMarker(
            page=sec.start_page,
            section_type=sec.statement_type,
            label=sec.label,
            note_number=sec.note_number,
            source="manual",
            validated=sec.validated,
        ))
    return TocGroundTruthV2(
        version=2,
        annotated_at=v1.annotated_at,
        annotator=v1.annotator,
        has_toc=v1.has_toc,
        toc_pages=v1.toc_pages,
        transitions=transitions,
    )


def v2_to_v1(v2: TocGroundTruthV2, total_pages: int | None = None) -> TocGroundTruth:
    """Convert v2 transition-marker model to v1 section-range model.

    Each transition extends to the page before the next transition.
    The last transition extends to total_pages (or stays open-ended).
    """
    sorted_trans = sorted(v2.transitions, key=lambda t: t.page)
    sections: list[TocSection] = []
    for i, t in enumerate(sorted_trans):
        end_page = sorted_trans[i + 1].page - 1 if i + 1 < len(sorted_trans) else total_pages
        sections.append(TocSection(
            label=t.label,
            statement_type=t.section_type,
            start_page=t.page,
            end_page=end_page,
            note_number=t.note_number,
            validated=t.validated,
        ))

    # Derive notes_start_page / notes_end_page from NOTES sections
    notes_sections = [s for s in sections if s.statement_type == "NOTES"]
    notes_start = min((s.start_page for s in notes_sections), default=None)
    notes_end = max((s.end_page for s in notes_sections if s.end_page), default=None)

    return TocGroundTruth(
        version=1,
        annotated_at=v2.annotated_at,
        annotator=v2.annotator,
        has_toc=v2.has_toc if v2.has_toc is not None else False,
        toc_pages=v2.toc_pages,
        sections=sections,
        notes_start_page=notes_start,
        notes_end_page=notes_end,
    )


def v1_dict_to_v2_dict(data: dict) -> dict:
    """Convert v1 dict to v2 dict (for API layer)."""
    transitions = []
    for sec in sorted(data.get("sections", []), key=lambda s: s.get("start_page", 0)):
        transitions.append({
            "page": sec["start_page"],
            "section_type": sec.get("statement_type", ""),
            "label": sec.get("label", ""),
            "note_number": sec.get("note_number"),
            "source": "manual",
            "validated": sec.get("validated", False),
        })
    return {
        "version": 2,
        "annotated_at": data.get("annotated_at", ""),
        "annotator": data.get("annotator", ""),
        "has_toc": data.get("has_toc"),
        "toc_pages": data.get("toc_pages", []),
        "transitions": transitions,
        "multi_tags": [],
    }


def v2_dict_to_v1_dict(data: dict, total_pages: int | None = None) -> dict:
    """Convert v2 dict to v1 dict (for backward compat persistence)."""
    sorted_trans = sorted(data.get("transitions", []), key=lambda t: t.get("page", 0))
    sections = []
    for i, t in enumerate(sorted_trans):
        end_page = sorted_trans[i + 1]["page"] - 1 if i + 1 < len(sorted_trans) else total_pages
        sections.append({
            "label": t.get("label", ""),
            "statement_type": t.get("section_type", ""),
            "start_page": t["page"],
            "end_page": end_page,
            "note_number": t.get("note_number"),
            "validated": t.get("validated", False),
        })

    notes_sections = [s for s in sections if s["statement_type"] == "NOTES"]
    notes_start = min((s["start_page"] for s in notes_sections), default=None)
    notes_end = max((s["end_page"] for s in notes_sections if s.get("end_page")), default=None)

    return {
        "version": 1,
        "annotated_at": data.get("annotated_at", ""),
        "annotator": data.get("annotator", ""),
        "has_toc": data.get("has_toc") if data.get("has_toc") is not None else False,
        "toc_table_id": None,
        "toc_pages": data.get("toc_pages", []),
        "sections": sections,
        "notes_start_page": notes_start,
        "notes_end_page": notes_end,
    }


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
