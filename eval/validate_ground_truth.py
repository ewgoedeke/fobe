#!/usr/bin/env python3
"""
validate_ground_truth.py -- Validate ground truth TOC annotations against table data.

Checks:
1. Page references: do tables on declared pages match expected statement types?
2. Note references: do note numbers in TOC match actual note columns in tables?
"""

import json
import re
from pathlib import Path

from ground_truth import load_toc_gt, TocGroundTruth
from reference_graph import build_reference_graph, has_note_column

# Keywords by statement type (subset for validation)
_TYPE_KEYWORDS: dict[str, list[str]] = {
    "PNL": ["revenue", "umsatz", "erlöse", "gewinn", "verlust", "profit", "loss",
            "ebit", "ergebnis", "aufwend", "ertrag"],
    "SFP": ["assets", "aktiva", "passiva", "liabilities", "equity", "eigenkapital",
            "verbindlichkeiten", "bilanz", "forderung", "rückstellung"],
    "OCI": ["other comprehensive", "sonstiges ergebnis", "gesamtergebnis"],
    "CFS": ["cash flow", "kapitalfluss", "zahlungsmittel", "finanzmittel",
            "cashflow", "geldfluss"],
    "SOCIE": ["eigenkapital", "equity", "gezeichnetes kapital", "retained earnings",
              "gewinnrücklage"],
}


def validate_page_refs(tg_path: str, gt: TocGroundTruth) -> list[dict]:
    """Check if TOC page references match table content on those pages.

    Returns list of findings: [{section_idx, label, page, status, detail}]
    """
    with open(tg_path) as f:
        tg = json.load(f)

    tables = tg.get("tables", [])

    # Index tables by page
    tables_by_page: dict[int, list[dict]] = {}
    for t in tables:
        page = t.get("pageNo")
        if page is not None:
            tables_by_page.setdefault(page, []).append(t)

    findings = []
    for idx, section in enumerate(gt.sections):
        start = section.start_page
        end = section.end_page or start

        # Collect all tables in page range
        page_tables = []
        for p in range(start, end + 1):
            page_tables.extend(tables_by_page.get(p, []))

        if not page_tables:
            findings.append({
                "section_idx": idx,
                "label": section.label,
                "page": start,
                "status": "warning",
                "detail": f"No tables found on page(s) {start}-{end}",
            })
            continue

        # Check if any table labels match expected keywords
        stmt_type = section.statement_type
        base_type = stmt_type.split(".")[0] if "." in stmt_type else stmt_type
        keywords = _TYPE_KEYWORDS.get(base_type, [])

        if not keywords:
            # Disclosure types — just check tables exist
            findings.append({
                "section_idx": idx,
                "label": section.label,
                "page": start,
                "status": "ok",
                "detail": f"{len(page_tables)} table(s) on page range",
            })
            continue

        # Check labels
        matched = False
        all_labels = []
        for t in page_tables:
            for r in t.get("rows", [])[:10]:
                label = r.get("label", "").lower()
                all_labels.append(label)
                for kw in keywords:
                    if kw in label:
                        matched = True
                        break
                if matched:
                    break
            if matched:
                break

        if matched:
            findings.append({
                "section_idx": idx,
                "label": section.label,
                "page": start,
                "status": "ok",
                "detail": f"Keywords match {stmt_type} in {len(page_tables)} table(s)",
            })
        else:
            findings.append({
                "section_idx": idx,
                "label": section.label,
                "page": start,
                "status": "warning",
                "detail": f"No {stmt_type} keywords found in {len(page_tables)} table(s)",
            })

    return findings


def validate_note_refs(tg_path: str, gt: TocGroundTruth) -> list[dict]:
    """Cross-reference note numbers from TOC with note columns in tables.

    Returns list of findings for sections that have note_number set.
    """
    with open(tg_path) as f:
        tg = json.load(f)

    tables = tg.get("tables", [])

    # Collect note references from primary statement tables
    note_refs_in_tables: set[str] = set()
    for t in tables:
        meta = t.get("metadata", {})
        stmt = meta.get("statementComponent", "")
        if stmt not in ("PNL", "SFP", "OCI", "CFS", "SOCIE"):
            continue
        if not has_note_column(t):
            continue
        for r in t.get("rows", []):
            for c in r.get("cells", []):
                text = str(c.get("text", "")).strip()
                if re.match(r'^\d{1,3}$', text):
                    note_refs_in_tables.add(text)

    findings = []
    for idx, section in enumerate(gt.sections):
        if not section.note_number:
            continue

        note_num = section.note_number.strip()
        if note_num in note_refs_in_tables:
            findings.append({
                "section_idx": idx,
                "label": section.label,
                "note_number": note_num,
                "status": "ok",
                "detail": f"Note {note_num} referenced in primary statements",
            })
        else:
            findings.append({
                "section_idx": idx,
                "label": section.label,
                "note_number": note_num,
                "status": "warning",
                "detail": f"Note {note_num} not found in primary statement note columns",
            })

    return findings


def validate_all(fixture_dir: str) -> dict:
    """Run all validations for a fixture directory."""
    tg_path = str(Path(fixture_dir) / "table_graphs.json")
    gt = load_toc_gt(fixture_dir)

    if gt is None:
        return {"error": "no ground truth found"}

    if not Path(tg_path).exists():
        return {"error": "no table_graphs.json found"}

    page_findings = validate_page_refs(tg_path, gt)
    note_findings = validate_note_refs(tg_path, gt)

    return {
        "page_refs": page_findings,
        "note_refs": note_findings,
        "summary": {
            "page_ok": sum(1 for f in page_findings if f["status"] == "ok"),
            "page_warnings": sum(1 for f in page_findings if f["status"] == "warning"),
            "note_ok": sum(1 for f in note_findings if f["status"] == "ok"),
            "note_warnings": sum(1 for f in note_findings if f["status"] == "warning"),
        },
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 eval/validate_ground_truth.py eval/fixtures/<name>")
        sys.exit(1)

    result = validate_all(sys.argv[1])
    if "error" in result:
        print(f"Error: {result['error']}")
        sys.exit(1)

    print(f"Page reference validation ({result['summary']['page_ok']} ok, "
          f"{result['summary']['page_warnings']} warnings):")
    for f in result["page_refs"]:
        icon = "OK" if f["status"] == "ok" else "WARN"
        print(f"  [{icon}] {f['label'][:50]:50s} p.{f['page']:3d}  {f['detail']}")

    if result["note_refs"]:
        print(f"\nNote reference validation ({result['summary']['note_ok']} ok, "
              f"{result['summary']['note_warnings']} warnings):")
        for f in result["note_refs"]:
            icon = "OK" if f["status"] == "ok" else "WARN"
            print(f"  [{icon}] Note {f['note_number']:3s} {f['label'][:50]:50s}  {f['detail']}")
