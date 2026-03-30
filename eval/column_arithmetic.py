#!/usr/bin/env python3
"""
column_arithmetic.py -- Cross-column arithmetic checks for axis validation.

Detects which VALUE columns participate in additive summation relationships
(real segments/geographies) vs. which are derived metrics (Change %, ratios).

A real segment column should satisfy:
    col_A + col_B + ... ≈ col_Total   for most data rows.

A metric column (e.g. "Change %", "in % of Group") will NOT satisfy this.

Usage:
    from column_arithmetic import classify_columns
    result = classify_columns(table)
    # result.additive_cols = [1, 2, 3]      — real segment columns
    # result.total_col = 4                   — the total column
    # result.derived_cols = [5, 6]           — derived/metric columns
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations


TOLERANCE_REL = 0.02   # 2% relative tolerance
TOLERANCE_ABS = 1.0    # absolute tolerance (units vary by table scale)


@dataclass
class ColumnClassification:
    """Result of cross-column arithmetic analysis for a table."""
    table_id: str
    additive_cols: list[int] = field(default_factory=list)
    total_col: int | None = None
    derived_cols: list[int] = field(default_factory=list)
    check_count: int = 0       # rows checked
    match_count: int = 0       # rows where summation held
    confidence: float = 0.0


def _get_col_values(table: dict) -> dict[int, list[float | None]]:
    """Extract per-column value lists from table rows (data rows only)."""
    value_col_indices = {
        c["colIdx"] for c in table.get("columns", [])
        if c.get("role") == "VALUE"
    }
    cols: dict[int, list[float | None]] = {ci: [] for ci in value_col_indices}

    for row in table.get("rows", []):
        for ci in value_col_indices:
            val = None
            for cell in row.get("cells", []):
                if cell.get("colIdx") == ci:
                    val = cell.get("parsedValue")
                    break
            cols[ci].append(val)

    return cols


def _check_summation(parts: list[list[float | None]],
                     total: list[float | None]) -> tuple[int, int]:
    """Check how many rows satisfy sum(parts) ≈ total.

    Returns (checked, matched) — rows where all values are present, and
    rows where the summation holds within tolerance.
    """
    checked = 0
    matched = 0

    for row_idx in range(len(total)):
        t = total[row_idx]
        if t is None:
            continue
        vals = [p[row_idx] for p in parts]
        if any(v is None for v in vals):
            continue
        checked += 1

        s = sum(vals)
        # Tolerance: relative + absolute
        tol = max(TOLERANCE_ABS, abs(t) * TOLERANCE_REL)
        if abs(s - t) <= tol:
            matched += 1

    return checked, matched


def classify_columns(table: dict, min_rows: int = 3,
                     min_match_rate: float = 0.60) -> ColumnClassification:
    """Classify VALUE columns as additive (segment) or derived (metric).

    Tries all possible partitions of value columns into:
        additive_cols + total_col
    and checks if the additive cols sum to the total col.

    Args:
        table: Table dict with columns and rows.
        min_rows: Minimum data rows needed for a reliable check.
        min_match_rate: Fraction of rows that must match for classification.

    Returns:
        ColumnClassification with the best partition found.
    """
    table_id = table.get("tableId", "?")
    col_values = _get_col_values(table)
    col_indices = sorted(col_values.keys())

    if len(col_indices) < 3:
        # Need at least 2 parts + 1 total for meaningful check
        return ColumnClassification(table_id=table_id)

    best = ColumnClassification(table_id=table_id)

    # Try each column as the potential "total" column
    for total_idx in col_indices:
        remaining = [ci for ci in col_indices if ci != total_idx]

        # Try subsets of remaining as additive parts (at least 2)
        for size in range(2, len(remaining) + 1):
            for combo in combinations(remaining, size):
                parts = [col_values[ci] for ci in combo]
                total_vals = col_values[total_idx]
                checked, matched = _check_summation(parts, total_vals)

                if checked < min_rows:
                    continue

                rate = matched / checked
                if rate >= min_match_rate and rate > best.confidence:
                    derived = [ci for ci in col_indices
                               if ci != total_idx and ci not in combo]
                    best = ColumnClassification(
                        table_id=table_id,
                        additive_cols=list(combo),
                        total_col=total_idx,
                        derived_cols=derived,
                        check_count=checked,
                        match_count=matched,
                        confidence=rate,
                    )

    return best


def validate_segment_columns(table: dict, segment_members: dict[str, str],
                             verbose: bool = False) -> dict[str, str]:
    """Filter segment members to only those in additive columns.

    Args:
        table: A DISC.SEGMENTS table.
        segment_members: Current {SEG.xxx: label} dict.
        verbose: Print filtering info.

    Returns:
        Filtered segment members dict.
    """
    result = classify_columns(table)
    if not result.additive_cols and not result.total_col:
        return segment_members  # no arithmetic signal, keep all

    # Map column indices to header labels
    col_headers = {}
    for col in table.get("columns", []):
        if col.get("role") == "VALUE":
            col_headers[col["colIdx"]] = col.get("headerLabel", "")

    # Identify which segment labels correspond to additive columns
    additive_labels = {col_headers.get(ci, "").strip().lower()
                       for ci in result.additive_cols}
    total_label = col_headers.get(result.total_col, "").strip().lower()

    filtered = {}
    for seg_id, label in segment_members.items():
        label_lower = label.strip().lower()
        # Keep if it matches an additive column (not total, not derived)
        if label_lower in additive_labels:
            filtered[seg_id] = label
        elif verbose:
            import sys
            reason = "total" if label_lower == total_label else "derived/metric"
            print(f"    col_arith: dropping {seg_id}={label} ({reason})",
                  file=sys.stderr)

    return filtered if filtered else segment_members  # fallback to all if filter too aggressive
