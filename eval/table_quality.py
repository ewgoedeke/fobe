#!/usr/bin/env python3
"""
table_quality.py -- Per-table quality scoring propagated through the pipeline.

Each stage can downgrade a table's quality score. Downstream stages use the
score to decide whether to process, skip, or flag the table.

Quality levels:
    1.0  = good (default)
    0.7  = suspect (some issues detected)
    0.3  = poor (significant problems)
    0.0  = corrupt (should not be processed further)

Usage:
    from table_quality import assess_quality, get_quality, is_processable
    assess_quality(tables)           # run all checks, mutate metadata
    q = get_quality(table)           # read score
    if is_processable(table):        # check if worth tagging
"""

from __future__ import annotations

import re

# Minimum quality for a table to be worth LLM tagging
PROCESSABLE_THRESHOLD = 0.3


def get_quality(table: dict) -> float:
    """Read the quality score from table metadata (default 1.0)."""
    return table.get("metadata", {}).get("qualityScore", 1.0)


def set_quality(table: dict, score: float, reason: str | None = None) -> None:
    """Set quality score, only downgrading (never upgrading)."""
    md = table.setdefault("metadata", {})
    current = md.get("qualityScore", 1.0)
    new_score = min(current, score)
    md["qualityScore"] = round(new_score, 2)
    if reason:
        md.setdefault("qualityFindings", []).append(reason)


def is_processable(table: dict) -> bool:
    """Check if a table is worth processing (tagging, LLM, etc.)."""
    return get_quality(table) >= PROCESSABLE_THRESHOLD


def assess_structure(tables: list[dict], verbose: bool = False) -> dict:
    """Run structural quality checks on all tables.

    Checks:
    1. Column count consistency — do all rows have the expected number of cells?
    2. Empty table detection — tables with 0 data rows.
    3. Parse rate per table — if <50% of VALUE cells have parsedValue, flag.
    4. Value magnitude spread — if values span >6 orders of magnitude, flag.

    Returns summary dict with counts.
    """
    import sys

    checked = 0
    flagged = 0

    for table in tables:
        checked += 1
        rows = table.get("rows", [])
        columns = table.get("columns", [])
        value_col_indices = {c["colIdx"] for c in columns if c.get("role") == "VALUE"}

        # Check 1: Empty table
        if len(rows) == 0:
            set_quality(table, 0.0, "empty_table")
            flagged += 1
            continue

        # Check 2: Column count consistency
        expected_cols = len(columns)
        if expected_cols > 0:
            inconsistent = sum(
                1 for r in rows
                if len(r.get("cells", [])) != expected_cols
            )
            if inconsistent > len(rows) * 0.3:
                set_quality(table, 0.3, f"column_count_inconsistent ({inconsistent}/{len(rows)} rows)")
                flagged += 1

        # Check 3: Parse rate per table
        if value_col_indices:
            total_vc = 0
            parsed_vc = 0
            for row in rows:
                for cell in row.get("cells", []):
                    if cell.get("colIdx") in value_col_indices:
                        text = (cell.get("text") or "").strip()
                        if text:
                            total_vc += 1
                            if cell.get("parsedValue") is not None:
                                parsed_vc += 1
            if total_vc > 0:
                parse_rate = parsed_vc / total_vc
                if parse_rate < 0.3:
                    set_quality(table, 0.3, f"low_parse_rate ({parse_rate:.0%})")
                    flagged += 1
                elif parse_rate < 0.5:
                    set_quality(table, 0.7, f"moderate_parse_rate ({parse_rate:.0%})")

        # Check 4: Value magnitude spread (detect scale inconsistency)
        values = []
        for row in rows:
            for cell in row.get("cells", []):
                if cell.get("colIdx") in value_col_indices:
                    pv = cell.get("parsedValue")
                    if pv is not None and pv != 0:
                        values.append(abs(pv))
        if len(values) >= 3:
            min_v = min(values)
            max_v = max(values)
            if min_v > 0 and max_v / min_v > 1_000_000:
                set_quality(table, 0.7, f"magnitude_spread ({min_v:.0f}..{max_v:.0f})")

        # Check 5: Garbled labels (OCR artifacts)
        garbled_count = 0
        for row in rows:
            label = row.get("label", "")
            # OCR artifacts: high ratio of special chars to alphanumeric
            alpha = sum(1 for c in label if c.isalnum() or c.isspace())
            special = sum(1 for c in label if not c.isalnum() and not c.isspace())
            if len(label) > 5 and special > alpha:
                garbled_count += 1
        if garbled_count > len(rows) * 0.3:
            set_quality(table, 0.3, f"garbled_labels ({garbled_count}/{len(rows)} rows)")
            flagged += 1

    return {
        "checked": checked,
        "flagged": flagged,
    }


def assess_hierarchy(tables: list[dict]) -> dict:
    """Check hierarchy quality: arithmetic consistency per table.

    Tables where <50% of parent-child sums hold are flagged as suspect.
    """
    flagged = 0
    for table in tables:
        rows_by_id = {r["rowId"]: r for r in table.get("rows", [])}
        value_col_indices = {c["colIdx"] for c in table.get("columns", [])
                            if c.get("role") == "VALUE"}
        if not value_col_indices:
            continue

        checks = 0
        passes = 0
        for row in table.get("rows", []):
            child_ids = row.get("childIds", [])
            if not child_ids:
                continue
            children = [rows_by_id.get(cid) for cid in child_ids]
            children = [c for c in children if c is not None]
            if len(children) < 2:
                continue

            for ci in value_col_indices:
                parent_val = None
                child_vals = []
                for cell in row.get("cells", []):
                    if cell.get("colIdx") == ci:
                        parent_val = cell.get("parsedValue")
                for child in children:
                    for cell in child.get("cells", []):
                        if cell.get("colIdx") == ci:
                            child_vals.append(cell.get("parsedValue"))

                if parent_val is not None and all(v is not None for v in child_vals):
                    checks += 1
                    tolerance = max(1.0, abs(parent_val) * 0.02)
                    if abs(sum(child_vals) - parent_val) <= tolerance:
                        passes += 1

        if checks >= 3:
            rate = passes / checks
            if rate < 0.5:
                set_quality(table, 0.3, f"hierarchy_inconsistent ({passes}/{checks})")
                flagged += 1
            elif rate < 0.7:
                set_quality(table, 0.7, f"hierarchy_moderate ({passes}/{checks})")

    return {"flagged": flagged}
