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
    labels = " ".join(str(list(r.values())[0]) for r in rows[:10]).lower()

    if "statement of financial position" in col_text or "31 december" in col_text:
        if "equity" in labels and "assets" in labels:
            return "SFP"
    if "revenue" in labels and ("cost of sales" in labels or "gross profit" in labels):
        return "PNL"
    if "other comprehensive income" in labels:
        return "OCI"
    if "cash flows" in labels or "cash flow" in col_text:
        return "CFS"
    if "attributable to" in labels and "comprehensive" in labels:
        return "OCI"
    if "segment" in col_text or "segment" in labels[:200]:
        return None  # segments handled separately
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
    """Build parent-child hierarchy by checking if TOTAL rows sum their predecessors."""
    tolerance = 0.5

    for i, row in enumerate(rows):
        if row["rowType"] != "TOTAL_EXPLICIT":
            continue

        # Try to find children: scan backward until another TOTAL or start
        candidates = []
        for j in range(i - 1, -1, -1):
            prev = rows[j]
            if prev["rowType"] in ("TOTAL_EXPLICIT", "SEPARATOR"):
                break
            if prev["rowType"] == "DATA":
                candidates.append(j)

        if not candidates:
            continue

        # Check if total = SUM(candidates) for any value column
        for col_idx in value_col_indices:
            total_val = _get_pv(row, col_idx)
            if total_val is None:
                continue

            child_sum = 0.0
            all_found = True
            for ci in candidates:
                cv = _get_pv(rows[ci], col_idx)
                if cv is not None:
                    child_sum += cv
                else:
                    all_found = False

            if all_found and abs(total_val - child_sum) <= tolerance:
                # Match! Set hierarchy
                child_ids = [rows[ci]["rowId"] for ci in reversed(candidates)]
                row["childIds"] = child_ids
                for ci in candidates:
                    rows[ci]["parentId"] = row["rowId"]
                break  # one column match is enough


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
