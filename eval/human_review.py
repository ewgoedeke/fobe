#!/usr/bin/env python3
"""
human_review.py -- HITL review system for Stage 2 classification.

Generates review manifests when classification quality gates fail,
loads and applies human overrides, and checks for staleness.

Files (live in fixture directory alongside table_graphs.json):
  review_needed.json  -- auto-generated manifest (read-only for humans)
  human_review.json   -- human-authored overrides applied by pipeline
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Review manifest generation ───────────────────────────────────

def generate_review_manifest(
    tables: list[dict],
    gate_result: Any,
    toc_info: dict | None,
    doc_name: str,
) -> dict:
    """Build review_needed.json content from gate findings + table data.

    Args:
        tables: List of table dicts from table_graphs.json.
        gate_result: GateResult from Stage 2 gate (has .findings, .metrics).
        toc_info: TOC page_map dict if detected, else None.
        doc_name: Document identifier.

    Returns:
        Dict ready to write as review_needed.json.
    """
    # Build page index — tables grouped by page, sorted
    page_groups: dict[int, list[dict]] = defaultdict(list)
    type_counts: Counter = Counter()
    flagged_count = 0

    # Determine which types are inflated from gate findings
    inflated_types = set()
    for f in (gate_result.findings if gate_result else []):
        if f.get("type") == "inflated_primary":
            # Extract type from detail like "132 tables classified as SFP ..."
            detail = f.get("detail", "")
            for token in detail.split():
                if token in ("PNL", "SFP", "OCI", "CFS", "SOCIE"):
                    inflated_types.add(token)

    for table in tables:
        meta = table.get("metadata", {})
        page = table.get("pageNo") or 0
        sc = meta.get("statementComponent")
        method = meta.get("classification_method", "unclassified")
        confidence = meta.get("classification_confidence", "none")

        if sc:
            type_counts[sc] += 1

        # Extract context for reviewer
        rows = table.get("rows", [])
        first_labels = []
        col_headers = []
        data_row_count = 0
        for r in rows:
            rt = r.get("rowType")
            if rt == "HEADER" and not col_headers:
                col_headers = [c.get("text", "") for c in r.get("cells", [])
                               if c.get("text", "").strip()][:6]
            elif rt != "HEADER":
                if len(first_labels) < 3 and r.get("label", "").strip():
                    first_labels.append(r["label"].strip()[:80])
                if rt in ("DATA", "TOTAL", None):
                    data_row_count += 1

        # Determine if flagged
        flagged = False
        flag_reason = None
        if sc in inflated_types:
            flagged = True
            flag_reason = f"inflated_primary: {sc} count={type_counts[sc]}"
        if not sc:
            flagged = True
            flag_reason = "unclassified"

        if flagged:
            flagged_count += 1

        entry = {
            "tableId": table.get("tableId", ""),
            "classification": sc,
            "method": method,
            "confidence": confidence,
            "first_labels": first_labels,
            "col_headers": col_headers,
            "row_count": len(rows),
            "data_row_count": data_row_count,
            "sectionPath": meta.get("sectionPath", []),
            "flagged": flagged,
        }
        if flag_reason:
            entry["flag_reason"] = flag_reason

        page_groups[page].append(entry)

    # Build page index sorted by page
    page_index = []
    for page in sorted(page_groups.keys()):
        page_index.append({
            "page": page,
            "tables": page_groups[page],
        })

    # Build suggested action
    suggested = _build_suggested_action(type_counts, inflated_types, page_groups)

    # Flagged page range
    flagged_pages = [p for p, ts in page_groups.items()
                     if any(t["flagged"] for t in ts)]
    flagged_range = ([min(flagged_pages), max(flagged_pages)]
                     if flagged_pages else None)

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "document": doc_name,
        "gate_findings": (gate_result.findings if gate_result else []),
        "toc_detected": ({"page_map": toc_info} if toc_info else None),
        "page_index": page_index,
        "summary": {
            "total_tables": len(tables),
            "by_type": dict(type_counts.most_common()),
            "flagged_count": flagged_count,
            "flagged_page_range": flagged_range,
            "suggested_action": suggested,
        },
    }
    return manifest


def _build_suggested_action(
    type_counts: Counter,
    inflated_types: set,
    page_groups: dict[int, list],
) -> str:
    """Generate a human-readable suggestion for the reviewer."""
    parts = []
    for st in sorted(inflated_types):
        count = type_counts[st]
        pages_with_type = [p for p, ts in page_groups.items()
                           if any(t["classification"] == st for t in ts)]
        if pages_with_type:
            lo, hi = min(pages_with_type), max(pages_with_type)
            parts.append(
                f"Review {count} {st} classifications on pages {lo}-{hi}; "
                f"likely over-classified")
    unclassified = sum(1 for ts in page_groups.values()
                       for t in ts if not t["classification"])
    if unclassified:
        parts.append(f"{unclassified} unclassified tables need assignment")
    return ". ".join(parts) if parts else "Review classifications"


# ── Human review loading and validation ──────────────────────────

def load_human_review(fixture_dir: str) -> dict | None:
    """Load human_review.json if it exists. Returns None if not found."""
    path = os.path.join(fixture_dir, "human_review.json")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        review = json.load(f)
    # Basic validation
    if "overrides" not in review:
        raise ValueError(f"human_review.json missing 'overrides' key: {path}")
    overrides = review["overrides"]
    if not isinstance(overrides.get("tables", {}), dict):
        raise ValueError("overrides.tables must be a dict (tableId -> override)")
    if not isinstance(overrides.get("page_ranges", []), list):
        raise ValueError("overrides.page_ranges must be a list")
    if not isinstance(overrides.get("patterns", []), list):
        raise ValueError("overrides.patterns must be a list")
    return review


def is_review_stale(review: dict, tables: list[dict]) -> tuple[bool, list[str]]:
    """Check if human_review.json references tableIds that no longer exist.

    Returns (is_stale, list_of_missing_ids).
    """
    current_ids = {t.get("tableId") for t in tables}
    referenced_ids = set()

    overrides = review.get("overrides", {})
    referenced_ids.update(overrides.get("tables", {}).keys())
    referenced_ids.update(review.get("confirmed_tables", []))

    missing = sorted(referenced_ids - current_ids)
    return (bool(missing), missing)


# ── Override application ─────────────────────────────────────────

def apply_overrides(
    tables: list[dict],
    review: dict,
) -> tuple[list[dict], dict]:
    """Apply human_review overrides to tables.

    Priority: per-table > pattern > page-range > automated.
    Sets classification_method="human_review", classification_confidence="high".
    Preserves previous classification in classification_previous.

    Args:
        tables: List of table dicts (mutated in place).
        review: Parsed human_review.json dict.

    Returns:
        (tables, stats) where stats has counts of applied overrides.
    """
    overrides = review.get("overrides", {})
    table_overrides = overrides.get("tables", {})
    page_ranges = overrides.get("page_ranges", [])
    patterns = overrides.get("patterns", [])
    confirmed = set(review.get("confirmed_tables", []))

    stats = Counter()

    for table in tables:
        tid = table.get("tableId", "")
        meta = table.setdefault("metadata", {})
        page = table.get("pageNo") or 0

        # Confirmed tables — lock current classification
        if tid in confirmed:
            meta["classification_method"] = "human_review"
            meta["classification_confidence"] = "high"
            stats["confirmed"] += 1
            continue

        # Per-table override (highest priority)
        if tid in table_overrides:
            _apply_single_override(meta, table_overrides[tid])
            stats["per_table"] += 1
            continue

        # Pattern override (match first row label)
        matched_pattern = False
        rows = table.get("rows", [])
        first_label = ""
        for r in rows:
            if r.get("label", "").strip():
                first_label = r["label"].strip()
                break

        for pat in patterns:
            regex = pat.get("label_pattern", "")
            if regex and first_label and re.search(regex, first_label, re.IGNORECASE):
                _apply_single_override(meta, pat)
                stats["pattern"] += 1
                matched_pattern = True
                break

        if matched_pattern:
            continue

        # Page range override
        matched_range = False
        for pr in page_ranges:
            start = pr.get("start_page", 0)
            end = pr.get("end_page", 999999)
            if start <= page <= end:
                _apply_single_override(meta, pr)
                stats["page_range"] += 1
                matched_range = True
                break

        if matched_range:
            continue

        # No override — keep automated classification
        stats["kept_automated"] += 1

    stats["total_applied"] = (stats["per_table"] + stats["pattern"]
                              + stats["page_range"] + stats["confirmed"])
    return tables, dict(stats)


def _apply_single_override(meta: dict, override: dict) -> None:
    """Apply a single override to table metadata."""
    # Preserve previous classification for audit
    prev_sc = meta.get("statementComponent")
    prev_method = meta.get("classification_method")
    if prev_sc or prev_method:
        meta["classification_previous"] = {
            "statementComponent": prev_sc,
            "classification_method": prev_method,
            "classification_confidence": meta.get("classification_confidence"),
        }

    sc = override.get("statementComponent")
    meta["statementComponent"] = sc  # None is valid (= not a data table)
    meta["classification_method"] = "human_review"
    meta["classification_confidence"] = "high"


# ── Template generation ──────────────────────────────────────────

def generate_template(review_manifest: dict) -> dict:
    """Generate a starter human_review.json from review_needed.json.

    Pre-populates flagged tables as empty overrides and suggests
    page ranges based on contiguous blocks.
    """
    template: dict[str, Any] = {
        "version": 1,
        "reviewed_at": "",
        "reviewer": "",
        "overrides": {
            "tables": {},
            "page_ranges": [],
            "patterns": [],
        },
        "confirmed_tables": [],
        "gate_override": False,
    }

    # Collect flagged tables for per-table overrides
    flagged_tables = {}
    for page_entry in review_manifest.get("page_index", []):
        for t in page_entry.get("tables", []):
            if t.get("flagged"):
                flagged_tables[t["tableId"]] = {
                    "statementComponent": t.get("classification"),
                    "comment": f"page {page_entry['page']}: "
                               f"{', '.join(t.get('first_labels', [])[:2]) or '(no labels)'}",
                }

    # Suggest page ranges from contiguous flagged blocks
    page_ranges = _suggest_page_ranges(review_manifest)

    # If page ranges cover most flagged tables, use ranges instead of per-table
    if page_ranges:
        template["overrides"]["page_ranges"] = page_ranges
        # Only include per-table overrides for tables NOT covered by ranges
        covered_pages = set()
        for pr in page_ranges:
            covered_pages.update(range(pr["start_page"], pr["end_page"] + 1))
        for page_entry in review_manifest.get("page_index", []):
            if page_entry["page"] not in covered_pages:
                for t in page_entry.get("tables", []):
                    if t.get("flagged"):
                        template["overrides"]["tables"][t["tableId"]] = {
                            "statementComponent": t.get("classification"),
                            "comment": (f"page {page_entry['page']}: "
                                        f"{', '.join(t.get('first_labels', [])[:2]) or '(no labels)'}"),
                        }
    else:
        template["overrides"]["tables"] = flagged_tables

    # Suggest confirmed_tables for non-flagged tables
    non_flagged = []
    for page_entry in review_manifest.get("page_index", []):
        for t in page_entry.get("tables", []):
            if not t.get("flagged") and t.get("classification"):
                non_flagged.append(t["tableId"])
    if non_flagged:
        template["_comment_confirmed"] = (
            "Add tableIds to confirmed_tables to lock their current classification. "
            f"{len(non_flagged)} non-flagged tables available."
        )

    return template


def _suggest_page_ranges(manifest: dict) -> list[dict]:
    """Suggest page ranges from contiguous blocks of flagged tables."""
    # Group consecutive flagged pages
    flagged_pages = []
    for page_entry in manifest.get("page_index", []):
        if any(t.get("flagged") for t in page_entry.get("tables", [])):
            flagged_pages.append(page_entry["page"])

    if len(flagged_pages) < 3:
        return []

    # Find contiguous runs
    ranges = []
    start = flagged_pages[0]
    prev = flagged_pages[0]
    for p in flagged_pages[1:]:
        if p - prev > 3:  # Allow small gaps (up to 3 pages)
            if prev - start >= 2:  # Only suggest ranges spanning 3+ pages
                ranges.append({"start_page": start, "end_page": prev,
                               "statementComponent": None,
                               "comment": "TODO: set correct classification"})
            start = p
        prev = p
    # Close last range
    if prev - start >= 2:
        ranges.append({"start_page": start, "end_page": prev,
                       "statementComponent": None,
                       "comment": "TODO: set correct classification"})

    return ranges


# ── File I/O helpers ─────────────────────────────────────────────

def write_review_manifest(fixture_dir: str, manifest: dict) -> str:
    """Write review_needed.json to fixture directory. Returns path."""
    path = os.path.join(fixture_dir, "review_needed.json")
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    return path


def write_human_review(fixture_dir: str, review: dict) -> str:
    """Write human_review.json to fixture directory. Returns path."""
    path = os.path.join(fixture_dir, "human_review.json")
    with open(path, "w") as f:
        json.dump(review, f, indent=2, default=str)
    return path
