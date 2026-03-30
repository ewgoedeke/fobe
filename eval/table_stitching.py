#!/usr/bin/env python3
"""
table_stitching.py -- Detect and merge multipage continuation tables.

A continuation table has the same VALUE column headers as the preceding table
and appears on the same or next page.  Stitching concatenates rows from
continuation tables into a single logical table, then removes the originals.

Usage:
    from table_stitching import stitch_tables
    merged_count = stitch_tables(tables, verbose=False)
"""

from __future__ import annotations

import copy
from typing import Any


def _value_col_signature(table: dict) -> tuple[str, ...]:
    """Canonical tuple of VALUE-column headerLabels for comparison."""
    return tuple(
        c.get("headerLabel", "")
        for c in table.get("columns", [])
        if c.get("role") == "VALUE"
    )


def _ends_with_total(table: dict) -> bool:
    """Check if the last row label looks like a total/summary row."""
    rows = table.get("rows", [])
    if not rows:
        return False
    label = (rows[-1].get("label") or "").strip().lower()
    return label in ("total", "summe", "gesamt", "insgesamt", "zusammen",
                      "zwischensumme", "subtotal")


def _same_classification(prev: dict, curr: dict) -> bool:
    """Check that both tables have compatible classifications.

    Two tables can be stitched if:
    - Both are unclassified (None), OR
    - Both have the same statementComponent
    Tables with different classifications are separate disclosures that
    happen to share column structure.
    """
    prev_sc = prev.get("metadata", {}).get("statementComponent")
    curr_sc = curr.get("metadata", {}).get("statementComponent")
    # Both None → compatible (unclassified continuation)
    if prev_sc is None and curr_sc is None:
        return True
    # One classified, one not → compatible (continuation of classified table)
    if prev_sc is None or curr_sc is None:
        return True
    # Both classified → must match
    return prev_sc == curr_sc


def _find_chains(tables: list[dict]) -> list[list[int]]:
    """Identify chains of consecutive tables with identical column structure.

    Returns list of chains, each chain a list of indices into *tables*.
    Only chains with len >= 2 are returned.

    A continuation table must:
    1. Have identical VALUE column headers to the previous table
    2. Appear on the same page or the next page
    3. Have compatible statementComponent classification
    4. The previous table must NOT end with a "Total" row (total = complete)
    """
    if not tables:
        return []

    chains: list[list[int]] = []
    current: list[int] = [0]

    for i in range(1, len(tables)):
        prev = tables[current[-1]]
        curr = tables[i]

        prev_sig = _value_col_signature(prev)
        curr_sig = _value_col_signature(curr)

        # Must have value columns and identical signatures
        same_cols = prev_sig == curr_sig and len(prev_sig) > 0

        # Must be on the same page or the next page
        page_gap = curr.get("pageNo", 0) - prev.get("pageNo", 0)
        close_pages = 0 <= page_gap <= 1

        # Must have compatible classifications
        compat_class = _same_classification(prev, curr)

        # Previous table ending with "Total" means it's complete
        prev_complete = _ends_with_total(prev)

        if same_cols and close_pages and compat_class and not prev_complete:
            current.append(i)
        else:
            if len(current) >= 2:
                chains.append(current)
            current = [i]

    if len(current) >= 2:
        chains.append(current)

    return chains


def _merge_chain(tables: list[dict], chain_indices: list[int]) -> dict:
    """Merge a chain of tables into one logical table.

    The first table in the chain is used as the base.  Rows from subsequent
    tables are appended, with rowIdx and rowId renumbered.
    """
    base = copy.deepcopy(tables[chain_indices[0]])
    base_table_idx = base["tableId"]

    # Track original tableIds for provenance
    source_ids = [tables[i]["tableId"] for i in chain_indices]
    base.setdefault("metadata", {})["stitchedFrom"] = source_ids

    # Expand bbox to encompass all tables
    # Table bbox is [l, t, r, b] in BOTTOMLEFT origin (y increases upward):
    #   l = left edge, t = top edge (high y), r = right edge, b = bottom edge (low y)
    # Union: leftmost left, highest top (max y), rightmost right, lowest bottom (min y)
    all_bboxes = [tables[i].get("bbox", [0, 0, 0, 0]) for i in chain_indices]
    valid_bboxes = [b for b in all_bboxes if any(v != 0 for v in b)]
    if valid_bboxes:
        base["bbox"] = [
            min(b[0] for b in valid_bboxes),   # leftmost
            max(b[1] for b in valid_bboxes),   # highest top (max y in BOTTOMLEFT)
            max(b[2] for b in valid_bboxes),   # rightmost
            min(b[3] for b in valid_bboxes),   # lowest bottom (min y in BOTTOMLEFT)
        ]

    # Update page range
    pages = [tables[i].get("pageNo", 0) for i in chain_indices]
    base["pageNo"] = min(pages)
    base["metadata"]["pageRange"] = [min(pages), max(pages)]

    # Append rows from continuation tables
    next_row_idx = len(base.get("rows", []))
    for chain_idx in chain_indices[1:]:
        cont = tables[chain_idx]
        for row in cont.get("rows", []):
            new_row = copy.deepcopy(row)
            new_row["rowIdx"] = next_row_idx
            # Renumber rowId to avoid collisions
            old_id = new_row["rowId"]
            new_id = f"row:{base_table_idx.replace('raw_', '')}:{next_row_idx}"
            new_row["rowId"] = new_id

            # Clear parent/child references across table boundaries —
            # structural inference will rebuild them.
            new_row["parentId"] = None
            new_row["childIds"] = []

            next_row_idx += 1
            base["rows"].append(new_row)

    # Clear hierarchy on base rows too — will be rebuilt by structural inference
    for row in base["rows"]:
        row["parentId"] = None
        row["childIds"] = []

    return base


def stitch_tables(tables: list[dict], verbose: bool = False) -> int:
    """Detect and merge multipage continuation tables in place.

    Args:
        tables: List of table dicts (mutated in place).
        verbose: Print merge info to stderr.

    Returns:
        Number of merges performed (0 if no stitching needed).
    """
    chains = _find_chains(tables)
    if not chains:
        return 0

    # Process chains in reverse order so index removal is safe
    merged_count = 0
    for chain in reversed(chains):
        merged = _merge_chain(tables, chain)

        if verbose:
            source_ids = merged["metadata"]["stitchedFrom"]
            import sys
            print(f"    stitch: {' + '.join(source_ids)} → {merged['tableId']} "
                  f"({len(merged['rows'])} rows)",
                  file=sys.stderr)

        # Replace the first table in the chain with the merged result
        tables[chain[0]] = merged

        # Remove the continuation tables (in reverse to preserve indices)
        for idx in reversed(chain[1:]):
            tables.pop(idx)

        merged_count += 1

    return merged_count
