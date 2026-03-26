#!/usr/bin/env python3
"""
convert_isg.py — Convert ISG-format table extraction to table_graphs.json.

The ISG format (from finparse4) has:
  { "tables": [ { "index": N, "csv_file": "...", "data": [{col: val}] } ] }

This converts to the table_graphs.json format the consistency engine expects,
including numeric parsing, column detection, and row hierarchy building.

Usage:
    python3 eval/convert_isg.py /tmp/finparse4/iso20022/isg-2025-ifs_full_result.json
"""

import json
import re
import sys
from pathlib import Path


def _parse_number(text: str) -> float | None:
    """Parse a financial number from text. Handles (parens), commas, spaces."""
    if not text or not text.strip():
        return None
    s = text.strip()
    if s in ("-", "–", "—", "n/a", "N/A", ""):
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()

    # Remove note refs like "c,d" or "e" after the number
    s = re.sub(r'\s*[a-z,\s*]+$', '', s)
    # Remove spaces used as thousand separators
    s = s.replace(" ", "").replace("\u00a0", "").replace("\u2009", "")
    # Remove commas (thousand separators)
    s = s.replace(",", "")

    try:
        val = float(s)
        return -val if negative else val
    except ValueError:
        return None


def _detect_statement(cols: list[str], rows: list[dict]) -> str | None:
    """Detect the statement type from column headers and row labels."""
    col_text = " ".join(cols).lower()
    all_labels = [str(list(r.values())[0]).lower() for r in rows]
    labels = " ".join(all_labels[:10])
    labels_all = " ".join(all_labels)

    # SFP: assets side (header mentions statement of financial position / "as at")
    is_sfp_header = ("statement of financial position" in col_text
                     or "as at" in col_text
                     or ("31 december" in col_text and "for the year" not in col_text))
    if is_sfp_header:
        if "assets" in labels or ("equity" in labels and "liabilities" in labels_all):
            return "SFP"

    # PNL must be checked before SFP equity side (both contain "equity" keyword)
    if "revenue" in labels and ("cost of sales" in labels or "gross profit" in labels):
        return "PNL"
    if "other comprehensive income" in labels:
        return "OCI"
    if "cash flows" in labels or "cash flow" in col_text:
        return "CFS"
    if "attributable to" in labels and "comprehensive" in labels:
        return "OCI"
    if "segment" in col_text or "segment" in labels[:200]:
        return "DISC.SEGMENTS"

    # SFP equity+liabilities side (split table): first row is "Equity" or
    # "Liabilities", and table contains SFP-specific keywords like
    # "share capital", "total equity and liabilities", "borrowings"
    first_label = all_labels[0].strip() if all_labels else ""
    if first_label in ("equity", "liabilities", "liabilities and equity"):
        if any(kw in labels_all for kw in ["share capital", "retained earnings",
                                           "total equity and liabilities",
                                           "total equity", "borrowings"]):
            return "SFP"

    # ── Disclosure note classification ────────────────────────────
    # Only classify tables that have numeric values (skip pure text/reference tables)
    # At this point, rows are raw ISG dicts: {col_name: value, ...}
    has_values = False
    for r in rows:
        vals = list(r.values())[1:]  # skip label column
        for v in vals:
            if _parse_number(str(v)) is not None:
                has_values = True
                break
        if has_values:
            break
    if not has_values:
        return None

    kw = labels_all
    col_kw = col_text  # column headers, already lowered

    # SOCIE (Statement of Changes in Equity) — detected from column headers
    if any(w in col_kw for w in ["retained earnings", "treasury share",
                                   "revaluation reserve", "hedging reserve",
                                   "translation reserve", "fair value reserve",
                                   "non- controlling interests", "total equity"]):
        if any(w in col_kw for w in ["reserve", "retained", "nci", "total"]):
            return "SOCIE"

    # Segments (IFRS 8) — column headers often name segments
    if any(w in col_kw for w in ["reportable segment", "all other segment",
                                   "total reportable", "segment total"]):
        return "DISC.SEGMENTS"
    if "segment" in kw and any(w in kw for w in ["revenue", "assets", "liabilities",
                                                   "reportable", "operating"]):
        return "DISC.SEGMENTS"

    # Revenue disaggregation (IFRS 15)
    if "revenue" in kw and any(w in kw for w in ["disaggregat", "timing",
                                                   "geography", "product",
                                                   "point in time", "over time",
                                                   "contract"]):
        return "DISC.REVENUE"

    # PPE rollforward (IAS 16)
    if any(w in kw for w in ["property, plant", "ppe"]):
        if any(w in kw for w in ["cost", "depreciation", "carrying", "additions",
                                  "disposals", "balance at"]):
            return "DISC.PPE"

    # Intangibles rollforward (IAS 38)
    if "intangible" in kw and any(w in kw for w in ["cost", "amortis", "carrying",
                                                      "additions", "balance at"]):
        return "DISC.INTANGIBLES"

    # Goodwill (IFRS 3 / IAS 36)
    if "goodwill" in kw and any(w in kw for w in ["impairment", "carrying",
                                                    "cgu", "balance at"]):
        return "DISC.GOODWILL"

    # Investment property (IAS 40)
    if "investment property" in kw:
        return "DISC.INV_PROP"

    # Leases (IFRS 16)
    if "right-of-use" in kw or ("lease" in kw and any(w in kw for w in [
            "maturity", "liability", "right", "depreciation"])):
        return "DISC.LEASES"

    # Provisions rollforward (IAS 37)
    if "provision" in kw and any(w in kw for w in ["opening", "closing",
                                                     "beginning", "reversal",
                                                     "utilised", "balance at"]):
        return "DISC.PROVISIONS"

    # Tax (IAS 12)
    if "deferred tax" in kw:
        return "DISC.TAX"
    if "tax" in kw and any(w in kw for w in ["effective", "reconcil", "rate",
                                               "current tax expense"]):
        return "DISC.TAX"

    # Employee benefits (IAS 19)
    if any(w in kw for w in ["employee benefit", "pension", "defined benefit",
                               "actuarial", "post-employment"]):
        return "DISC.EMPLOYEE_BENEFITS"
    if "employee" in kw and any(w in kw for w in ["wages", "salaries", "social",
                                                    "contribution"]):
        return "DISC.EMPLOYEE_BENEFITS"

    # Earnings per share (IAS 33)
    if "earnings per share" in kw or ("weighted" in kw and "shares" in kw):
        return "DISC.EPS"
    if "profit" in kw and "attributable" in kw and "ordinary" in kw:
        return "DISC.EPS"

    # Share-based payments (IFRS 2) / Share capital
    if "share" in kw and any(w in kw for w in ["option", "based", "plan",
                                                 "granted", "vested", "exercised"]):
        return "DISC.SHARE_BASED"

    # Business combinations (IFRS 3)
    if any(w in kw for w in ["acquisition", "business combination", "purchase price",
                               "consideration transferred"]):
        return "DISC.BCA"

    # Financial instruments (IFRS 7/9)
    if "financial" in kw and any(w in kw for w in ["asset", "instrument",
                                                     "liability", "fvoci",
                                                     "amortised cost"]):
        return "DISC.FIN_INST"

    # Fair value hierarchy (IFRS 13)
    if "fair value" in kw and any(w in kw for w in ["level", "hierarch"]):
        return "DISC.FAIR_VALUE"

    # Inventories (IAS 2)
    if any(w in kw for w in ["inventor", "raw material", "finished good",
                               "work in progress"]):
        return "DISC.INVENTORIES"

    # Borrowings / debt (IFRS 7)
    if any(w in kw for w in ["borrowing", "bond issue", "loan"]):
        if any(w in kw for w in ["maturity", "repayment", "carrying",
                                   "balance at", "proceeds"]):
            return "DISC.BORROWINGS"

    # Related parties (IAS 24)
    if "related party" in kw or "key management" in kw:
        return "DISC.RELATED_PARTIES"

    # Contingencies and commitments (IAS 37)
    if "contingent" in kw or "commitment" in kw:
        return "DISC.CONTINGENCIES"

    # Held for sale / discontinued ops (IFRS 5)
    if any(w in kw for w in ["held for sale", "disposal group", "discontinued"]):
        return "DISC.HELD_FOR_SALE"

    # Hedge accounting (IFRS 9)
    if any(w in kw for w in ["hedge", "hedging", "cash flow hedge",
                               "forward exchange contract"]):
        return "DISC.HEDGE"

    # Credit risk / ECL (IFRS 9)
    if "credit" in kw and any(w in kw for w in ["risk", "ecl", "loss allowance",
                                                   "expected"]):
        return "DISC.CREDIT_RISK"
    if "receivable" in kw and any(w in kw for w in ["ageing", "past due",
                                                      "allowance"]):
        return "DISC.CREDIT_RISK"

    # Biological assets (IAS 41)
    if "biological" in kw:
        return "DISC.BIOLOGICAL_ASSETS"

    # Government grants (IAS 20)
    if "government grant" in kw:
        return "DISC.GOV_GRANTS"

    # Dividends
    if "dividend" in kw:
        return "DISC.DIVIDENDS"

    # Associates / Joint ventures (IAS 28)
    if "associate" in kw or "joint venture" in kw:
        return "DISC.ASSOCIATES"

    # Impairment (IAS 36)
    if "impairment" in kw and any(w in kw for w in ["loss", "test", "recoverable"]):
        return "DISC.IMPAIRMENT"

    # Depreciation/amortisation detail
    if any(w in kw for w in ["depreciation", "amortisation"]) and "useful" in kw:
        return "DISC.PPE"

    # ── Column-header-driven classification ──────────────────────
    # These catch tables where row labels are cryptic but column headers
    # reveal the disclosure context.

    # Financing reconciliation (IAS 7.44) — columns name liability types
    if any(w in col_kw for w in ["lease liabilities", "redeemable preference",
                                   "derivatives (assets)"]):
        return "DISC.BORROWINGS"

    # Fair value hierarchy — columns have Level 1/2/3 or carrying amount/fair value
    if any(w in col_kw for w in ["level 1", "level 2", "level 3"]):
        return "DISC.FAIR_VALUE"
    if "carrying amount" in col_kw and "fair value" in col_kw:
        return "DISC.FAIR_VALUE"

    # NCI subsidiary detail (IFRS 12)
    if any(w in col_kw for w in ["intra-group", "individually immaterial"]):
        return "DISC.NCI"

    # Credit risk — ECL stages, loss rate, gross carrying amount
    if any(w in col_kw for w in ["loss rate", "loss allowance", "credit-",
                                   "gross carrying amount", "ecl"]):
        return "DISC.CREDIT_RISK"
    if any(w in kw for w in ["past due", "low risk", "substandard", "doubtful"]):
        return "DISC.CREDIT_RISK"

    # Credit concentration by geography/customer type
    if ("carrying amount" in col_kw or "net carrying" in col_kw):
        if any(w in kw for w in ["country", "region", "wholesale",
                                   "retail", "end-user"]):
            return "DISC.CREDIT_RISK"

    # Hedge accounting detail — hedge effectiveness columns
    if any(w in col_kw for w in ["hedge ineffectiveness", "hedging reserve",
                                   "costs of hedging"]):
        return "DISC.HEDGE"

    # FX sensitivity / interest rate sensitivity
    if any(w in col_kw for w in ["strengthening", "weakening"]):
        return "DISC.FX_RISK"
    if any(w in col_kw for w in ["bp increase", "bp decrease",
                                   "100 bp"]):
        return "DISC.INTEREST_RATE_RISK"

    # Exchange rates table
    if any(w in col_kw for w in ["average rate", "spot rate"]):
        return "DISC.FX_RISK"

    # Lease maturity (IFRS 16)
    if any(w in kw for w in ["less than one year", "one to two years",
                               "two to three years", "more than five years"]):
        return "DISC.LEASES"

    # Revenue disaggregation — geography or product in columns
    if any(w in col_kw for w in ["geographical", "product"]):
        if "revenue" in kw or "revenue" in col_kw:
            return "DISC.REVENUE"

    # Deferred tax movement — columns show OCI/equity/BCA/other
    if any(w in col_kw for w in ["recognised in oci", "recognised directly in equity",
                                   "acquired in business"]):
        return "DISC.TAX"

    # Tax losses / deductible differences
    if any(w in kw for w in ["deductible temporary", "tax losses",
                               "never expire"]):
        return "DISC.TAX"

    # Segment detail — column headers name specific segments or say "segment"
    if any(w in col_kw for w in ["forestry", "timber", "packaging",
                                   "non-recycled", "recycled",
                                   "segment total", "consolidated total",
                                   "reportable segment"]):
        return "DISC.SEGMENTS"
    # Revenue reconciliation with segment elimination
    if "inter-segment" in kw and ("revenue" in kw or "elimination" in kw):
        return "DISC.SEGMENTS"

    # Share options movement
    if any(w in kw for w in ["outstanding at 1 january", "exercised during",
                               "forfeited during", "granted during"]):
        return "DISC.SHARE_BASED"
    if any(w in col_kw for w in ["number of options", "weighted- average exercis"]):
        return "DISC.SHARE_BASED"

    # Investment property fair value
    if any(w in kw for w in ["income-generating property", "vacant property"]):
        return "DISC.INV_PROP"

    # Supplier finance arrangements (IAS 7.44F)
    if "supplier finance" in kw:
        return "DISC.BORROWINGS"

    # Goodwill impairment testing — CGU key assumptions
    if any(w in kw for w in ["discount rate", "terminal value growth",
                               "ebitda growth rate"]):
        return "DISC.GOODWILL"

    # Equity investments at FVOCI detail
    if any(w in kw for w in ["equity securities", "consumer markets",
                               "pharmaceuticals"]):
        return "DISC.FIN_INST"

    # Trade receivables breakdown
    if "trade receivables" in kw and "related parties" in kw:
        return "DISC.RELATED_PARTIES"

    # Error correction / restatement impact
    if "correction of error" in col_kw or "restatement" in col_kw:
        return "DISC.RESTATEMENT"

    # Biological assets (column-driven)
    if any(w in col_kw for w in ["biological", "bearer", "consumable"]):
        return "DISC.BIOLOGICAL_ASSETS"

    # Dividends per share
    if any(w in kw for w in ["cents per qualifying ordinary share",
                               "cents per non-redeemable"]):
        return "DISC.DIVIDENDS"

    # Revenue by geography or NCA by geography
    if any(w in kw for w in ["country x", "all foreign countries",
                               "foreign countries"]):
        return "DISC.SEGMENTS"

    # Share-based payment liabilities
    if any(w in kw for w in ["carrying amount of liabilities for",
                               "intrinsic value of liabilities for"]):
        return "DISC.SHARE_BASED"

    # Biological asset fair value gains
    if any(w in kw for w in ["change in fair value (realised)",
                               "change in fair value (unrealised)"]):
        return "DISC.BIOLOGICAL_ASSETS"

    # PPE depreciation impact
    if "depreciation" in kw and "expense" in kw:
        return "DISC.PPE"

    # Impairment by CGU
    if any(w in kw for w in ["non-recycled papers", "timber products"]):
        return "DISC.GOODWILL"

    # Investment at fair value
    if any(w in col_kw for w in ["fair value at 31 december",
                                   "dividend income recognise"]):
        return "DISC.FIN_INST"

    return None


def _detect_unit(cols: list[str]) -> str:
    """Detect unit from column headers."""
    col_text = " ".join(cols).lower()
    if "thousands" in col_text or "in thousands" in col_text:
        return "UNIT.THOUSANDS"
    if "millions" in col_text:
        return "UNIT.MILLIONS"
    return "UNIT.THOUSANDS"  # KPMG IFS default


def convert_table(isg_table: dict) -> dict | None:
    """Convert one ISG table to table_graphs.json format."""
    data = isg_table.get("data", [])
    if not data or len(data) < 2:
        return None

    cols = list(data[0].keys())
    if len(cols) < 2:
        return None

    table_id = f"table_{isg_table['index']}"
    label_col = cols[0]
    value_cols = cols[1:]

    # Detect statement type and unit
    sc = _detect_statement(cols, data)
    unit = _detect_unit(cols)

    # Build columns metadata
    columns = [{"colIdx": 0, "role": "LABEL", "headerLabel": label_col, "detectedAxes": {}}]

    for i, vc in enumerate(value_cols):
        role = "VALUE"
        axes = {}
        vc_lower = vc.lower()

        # Detect if this is a note column
        if "note" in vc_lower:
            role = "NOTES"
        else:
            axes["AXIS.VALUE_TYPE"] = "VALTYPE.TERMINAL"
            # Try to extract year
            year_match = re.search(r'20\d{2}', vc)
            if year_match:
                axes["AXIS.PERIOD"] = f"PERIOD.Y{year_match.group()}"

        columns.append({
            "colIdx": i + 1,
            "role": role,
            "headerLabel": vc,
            "detectedAxes": axes,
        })

    # Build rows
    rows = []
    value_col_indices = [c["colIdx"] for c in columns if c["role"] == "VALUE"]

    for row_idx, row_data in enumerate(data):
        values = list(row_data.values())
        label = str(values[0]).strip() if values else ""

        # Skip header rows that repeat column names
        if row_idx == 0 and label.lower().startswith("in thousands"):
            continue

        cells = [{"colIdx": 0, "text": label, "parsedValue": None, "isNegative": False}]

        has_any_value = False
        for ci, vc in enumerate(value_cols):
            raw = str(values[ci + 1]) if ci + 1 < len(values) else ""
            pv = _parse_number(raw)
            if pv is not None:
                has_any_value = True
            cells.append({
                "colIdx": ci + 1,
                "text": raw,
                "parsedValue": pv,
                "isNegative": pv is not None and pv < 0,
            })

        # Determine row type
        row_type = "DATA"
        label_lower = label.lower()
        if not label:
            row_type = "SEPARATOR"
        elif any(label_lower.startswith(kw) for kw in ["total ", "net "]) or label_lower in ("total", "net"):
            row_type = "TOTAL_EXPLICIT"
        elif label_lower in ("", " "):
            row_type = "SEPARATOR"

        rows.append({
            "rowId": f"row:{isg_table['index']}:{row_idx}",
            "rowIdx": row_idx,
            "label": label,
            "rowType": row_type,
            "indentLevel": 0,
            "depth": 0,
            "parentId": None,
            "childIds": [],
            "cells": cells,
            "preTagged": None,
        })

    if not rows:
        return None

    # Build row hierarchy (simple: TOTAL rows' children are preceding DATA rows)
    _build_simple_hierarchy(rows, value_col_indices)

    return {
        "tableId": table_id,
        "pageNo": isg_table["index"],
        "headerRowCount": 0,
        "labelColIdx": 0,
        "metadata": {
            "statementComponent": sc,
            "detectedCurrency": "CURRENCY.EUR",
            "detectedUnit": unit,
            "signConvention": "PRESENTATION",
            "sectionPath": [],
            "scope": None,
        },
        "columns": columns,
        "rows": rows,
        "aggregationGroups": [],
        "pipelineSteps": [
            {"id": "isg_convert", "label": "Converted from ISG format", "params": {}},
        ],
        "rawHeaders": [],
        "filledHeaders": [],
    }


def _build_simple_hierarchy(rows: list[dict], value_col_indices: list[int]):
    """Build parent-child hierarchy via multi-pass subtotal detection.

    Pass logic (up to 5 passes):
      1. For each row with values, check if it equals the sum of a consecutive
         run of rows above (backward subtotal) or below (forward breakdown).
      2. Once a subtotal is found, its children are marked and excluded from
         being candidates in subsequent passes.
      3. Rows detected as subtotals but typed DATA are reclassified as
         TOTAL_IMPLICIT.

    This handles nested structures like:
      detail1, detail2, detail3 → subtotalA (implicit)
      detail4, detail5         → subtotalB (implicit)
      subtotalA + subtotalB    → TOTAL (explicit)
    """
    max_passes = 5
    assigned: set[int] = set()  # row indices already assigned as children

    for pass_num in range(max_passes):
        found_any = False

        # Process in document order — smaller groups (earlier in the table)
        # get detected before their parents (later in the table).
        # Within each pass, skip rows already consumed or already parents.
        for i, row in enumerate(rows):
            # Skip rows already assigned as children or already have children
            if i in assigned or row.get("childIds"):
                continue
            # Skip rows without values
            if row["rowType"] == "SEPARATOR":
                continue

            # Try backward subtotal: row[i] = SUM(consecutive preceding rows)
            result = _try_backward_subtotal(rows, i, value_col_indices, assigned)
            if result:
                _apply_hierarchy(rows, i, result, assigned)
                found_any = True
                continue

            # Try forward breakdown: row[i] = SUM(consecutive following rows)
            result = _try_forward_breakdown(rows, i, value_col_indices, assigned)
            if result:
                _apply_hierarchy(rows, i, result, assigned)
                found_any = True

        if not found_any:
            break


def _try_backward_subtotal(rows: list[dict], total_idx: int,
                           value_col_indices: list[int],
                           assigned: set[int]) -> list[int] | None:
    """Check if rows[total_idx] = SUM of consecutive preceding rows.

    Skips rows already assigned as children of other subtotals — they
    belong to a lower level. But rows that are subtotals themselves
    (have childIds) are valid candidates for the next hierarchy level.

    Tries progressively longer runs of candidates (2..N) and returns the
    first match. Requires at least 2 children.
    """
    candidates = []
    for j in range(total_idx - 1, -1, -1):
        prev = rows[j]
        if prev["rowType"] == "SEPARATOR":
            break
        if j in assigned:
            # Skip assigned children, but don't break — there may be
            # unassigned rows or subtotals further up
            continue
        if prev.get("childIds") or prev["rowType"] in ("DATA", "TOTAL_EXPLICIT", "TOTAL_IMPLICIT"):
            candidates.append(j)

    if len(candidates) < 2:
        return None

    # Strategy 1: Try just the subtotal rows (rows with childIds) — these
    # are the expected children at the next hierarchy level.
    subtotal_candidates = [j for j in candidates if rows[j].get("childIds")]
    if len(subtotal_candidates) >= 2:
        if _check_sum(rows, total_idx, subtotal_candidates, value_col_indices):
            return subtotal_candidates

    # Strategy 2: Try progressively longer contiguous runs from closest row.
    for length in range(2, len(candidates) + 1):
        subset = candidates[:length]
        if _check_sum(rows, total_idx, subset, value_col_indices):
            return subset

    return None


def _try_forward_breakdown(rows: list[dict], parent_idx: int,
                           value_col_indices: list[int],
                           assigned: set[int]) -> list[int] | None:
    """Check if rows[parent_idx] = SUM of consecutive following rows.

    Used for parent rows that precede their children (e.g., "Profit after tax"
    followed by "thereof NCI" + "thereof parent").
    """
    candidates = []
    for j in range(parent_idx + 1, len(rows)):
        nxt = rows[j]
        if nxt["rowType"] == "SEPARATOR":
            break
        if j in assigned:
            continue
        if nxt.get("childIds") or nxt["rowType"] in ("DATA", "TOTAL_EXPLICIT", "TOTAL_IMPLICIT"):
            candidates.append(j)

    if len(candidates) < 2:
        return None

    for length in range(2, len(candidates) + 1):
        subset = candidates[:length]
        if _check_sum(rows, parent_idx, subset, value_col_indices):
            return subset

    return None


def _check_sum(rows: list[dict], total_idx: int, child_indices: list[int],
               value_col_indices: list[int]) -> bool:
    """Check if total row ≈ SUM(child rows) across value columns.

    Requires match on at least one column where total has a value.
    Missing child values are treated as 0 (empty cells in financial
    tables typically mean zero). At least half of children must have
    a value in a column for it to count.
    Uses tolerance of max(0.5, 0.005 * |total|) per column.
    """
    matched_any = False
    for col_idx in value_col_indices:
        total_val = _get_pv(rows[total_idx], col_idx)
        if total_val is None:
            continue

        child_sum = 0.0
        present_count = 0
        for ci in child_indices:
            cv = _get_pv(rows[ci], col_idx)
            if cv is not None:
                child_sum += cv
                present_count += 1

        # Need at least 2 children with values, and at least half overall
        if present_count < max(2, len(child_indices) / 2):
            continue

        tol = max(0.5, 0.005 * abs(total_val))
        if abs(total_val - child_sum) <= tol:
            matched_any = True
        else:
            # If this column has values but doesn't match, fail
            return False

    return matched_any


def _apply_hierarchy(rows: list[dict], parent_idx: int,
                     child_indices: list[int], assigned: set[int]):
    """Set parent-child links and reclassify subtotal rows."""
    parent_row = rows[parent_idx]
    # Sort children by row index (document order)
    child_indices_sorted = sorted(child_indices)
    child_ids = [rows[ci]["rowId"] for ci in child_indices_sorted]
    parent_row["childIds"] = child_ids

    for ci in child_indices_sorted:
        rows[ci]["parentId"] = parent_row["rowId"]
        assigned.add(ci)

    # Reclassify DATA rows detected as subtotals to TOTAL_IMPLICIT
    if parent_row["rowType"] == "DATA":
        parent_row["rowType"] = "TOTAL_IMPLICIT"


def _get_pv(row: dict, col_idx: int) -> float | None:
    for cell in row.get("cells", []):
        if cell.get("colIdx") == col_idx and cell.get("parsedValue") is not None:
            return cell["parsedValue"]
    return None


def convert_document(isg_path: str) -> dict:
    """Convert full ISG document to table_graphs.json format."""
    with open(isg_path) as f:
        data = json.load(f)

    tables = []
    for isg_table in data.get("tables", []):
        converted = convert_table(isg_table)
        if converted:
            tables.append(converted)

    return {"tables": tables}


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <isg_result.json> [output.json]")
        sys.exit(1)

    isg_path = sys.argv[1]
    result = convert_document(isg_path)

    out_path = sys.argv[2] if len(sys.argv) > 2 else isg_path.replace(".json", "_table_graphs.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    tables = result["tables"]
    classified = sum(1 for t in tables if t["metadata"].get("statementComponent"))
    rows_with_children = sum(1 for t in tables for r in t.get("rows", []) if r.get("childIds"))
    print(f"Converted {len(tables)} tables ({classified} classified)")
    print(f"Rows with childIds: {rows_with_children}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
