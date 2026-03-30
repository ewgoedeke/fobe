#!/usr/bin/env python3
"""
toc_analysis.py — Validate TOC ground truth and compare detection approaches.

Runs across all fixtures with ground_truth/toc.json and produces:
  1. Page reference validation (do tables match section types?)
  2. Note reference extraction from primary financials
  3. Feature extraction for TOC vs non-TOC tables
  4. Approach comparison (current heuristic, enhanced, feature-score, Docling baseline)
  5. Docling document_index vs manual ground truth comparison

Usage:
    python3 eval/toc_analysis.py [--verbose]
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ground_truth import load_toc_gt, load_toc_gt_dict, TocGroundTruth, TocSection
from reference_graph import build_reference_graph, has_note_column, DocumentRefGraph
from classify_tables import _detect_toc, _STATEMENT_KEYWORDS, _parse_toc_entries


def _load_gt_lenient(fixture_dir: str) -> TocGroundTruth | None:
    """Load ground truth with tolerance for extra fields (start_page_doc, etc.)."""
    gt = load_toc_gt(fixture_dir)
    if gt is not None:
        return gt
    # Fallback: load raw dict and strip extra fields
    raw = load_toc_gt_dict(fixture_dir)
    if raw is None:
        return None
    sections = []
    for s in raw.pop("sections", []):
        # Keep only known TocSection fields
        sections.append(TocSection(
            label=s.get("label", ""),
            statement_type=s.get("statement_type", "OTHER"),
            start_page=s.get("start_page"),
            end_page=s.get("end_page"),
            note_number=s.get("note_number"),
            validated=s.get("validated", False),
        ))
    return TocGroundTruth(
        version=raw.get("version", 1),
        annotated_at=raw.get("annotated_at", ""),
        annotator=raw.get("annotator", ""),
        has_toc=raw.get("has_toc", False),
        toc_table_id=raw.get("toc_table_id"),
        toc_pages=raw.get("toc_pages", []),
        sections=sections,
        notes_start_page=raw.get("notes_start_page"),
        notes_end_page=raw.get("notes_end_page"),
    )

# Keywords by statement type (from validate_ground_truth.py)
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

VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv

# Docling corpus location — raw *_docling.json files
_CORPUS_DIR = Path("/tmp/fobe_corpus")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _tables_by_page(tables: list[dict]) -> dict[int, list[dict]]:
    by_page: dict[int, list[dict]] = {}
    for t in tables:
        p = t.get("pageNo")
        if p is not None:
            by_page.setdefault(p, []).append(t)
    return by_page


def _all_labels(table: dict, max_rows: int = 15) -> list[str]:
    return [r.get("label", "").lower() for r in table.get("rows", [])[:max_rows]]


def _table_has_currency(table: dict) -> bool:
    meta = table.get("metadata", {})
    if meta.get("detectedCurrency"):
        return True
    for col in table.get("columns", []):
        if col.get("detectedAxes", {}).get("AXIS.CURRENCY"):
            return True
    return False


def _table_parsed_values(table: dict) -> list[float]:
    vals = []
    for r in table.get("rows", []):
        for c in r.get("cells", []):
            pv = c.get("parsedValue")
            if pv is not None:
                vals.append(float(pv))
    return vals


# ── Section 1a: Page Reference Validation ────────────────────────────────────

def validate_page_refs(tables: list[dict], gt: TocGroundTruth) -> list[dict]:
    by_page = _tables_by_page(tables)
    findings = []

    for idx, section in enumerate(gt.sections):
        start = section.start_page
        if start is None:
            findings.append({
                "section_idx": idx, "label": section.label,
                "statement_type": section.statement_type,
                "page": None, "status": "warning",
                "detail": "start_page is null",
            })
            continue

        end = section.end_page or start
        page_tables = []
        for p in range(start, end + 1):
            page_tables.extend(by_page.get(p, []))

        if not page_tables:
            findings.append({
                "section_idx": idx, "label": section.label,
                "statement_type": section.statement_type,
                "page": start, "status": "warning",
                "detail": f"No tables found on page(s) {start}-{end}",
            })
            continue

        stmt = section.statement_type
        base_type = stmt.split(".")[0] if "." in stmt else stmt

        # For TOC sections, check that tables look like a TOC (small int values)
        if stmt == "TOC":
            vals = []
            for t in page_tables:
                vals.extend(_table_parsed_values(t))
            small_ints = [v for v in vals if 1 <= v <= 500 and v == int(v)]
            pct = len(small_ints) / max(len(vals), 1)
            if pct > 0.5:
                findings.append({
                    "section_idx": idx, "label": section.label,
                    "statement_type": stmt, "page": start, "status": "ok",
                    "detail": f"TOC-like values ({pct:.0%} small ints) in {len(page_tables)} table(s)",
                })
            else:
                findings.append({
                    "section_idx": idx, "label": section.label,
                    "statement_type": stmt, "page": start, "status": "warning",
                    "detail": f"Not TOC-like ({pct:.0%} small ints) in {len(page_tables)} table(s)",
                })
            continue

        # For non-financial section types, just check tables exist
        if base_type in ("FRONT_MATTER", "OTHER", "AUDITOR_REPORT", "MANAGEMENT_REPORT",
                         "APPENDIX", "NOTES", "SUPERVISORY_BOARD", "ESG", "CORPORATE_GOVERNANCE"):
            findings.append({
                "section_idx": idx, "label": section.label,
                "statement_type": stmt, "page": start, "status": "ok",
                "detail": f"{len(page_tables)} table(s) on page range",
            })
            continue

        # For primary statements, check keyword matching
        keywords = _TYPE_KEYWORDS.get(base_type, [])
        if not keywords:
            findings.append({
                "section_idx": idx, "label": section.label,
                "statement_type": stmt, "page": start, "status": "ok",
                "detail": f"{len(page_tables)} table(s) found (no keywords for {base_type})",
            })
            continue

        matched = False
        for t in page_tables:
            for lbl in _all_labels(t):
                for kw in keywords:
                    if kw in lbl:
                        matched = True
                        break
                if matched:
                    break
            if matched:
                break

        # Also check if existing statementComponent matches
        sc_match = any(
            t.get("metadata", {}).get("statementComponent") == stmt
            for t in page_tables
        )

        if matched or sc_match:
            findings.append({
                "section_idx": idx, "label": section.label,
                "statement_type": stmt, "page": start, "status": "ok",
                "detail": f"Content matches {stmt} in {len(page_tables)} table(s)"
                          + (" (keyword)" if matched else " (statementComponent)"),
            })
        else:
            findings.append({
                "section_idx": idx, "label": section.label,
                "statement_type": stmt, "page": start, "status": "warning",
                "detail": f"No {stmt} keywords in {len(page_tables)} table(s)",
            })

    return findings


# ── Section 1b: Note Reference Extraction ────────────────────────────────────

def extract_note_refs(tables: list[dict], gt: TocGroundTruth) -> dict:
    graph = build_reference_graph(tables)

    # Collect all note references from primary statements
    primary_notes = {}
    for note_base, entries in sorted(graph.note_entries.items()):
        primary_labels = []
        source_stmts = set()
        for e in entries:
            primary_labels.append(e.source_label)
            if e.source_context:
                source_stmts.add(e.source_context)
        ctx = graph.context_for_note(note_base)
        primary_notes[note_base] = {
            "labels": list(set(primary_labels))[:5],
            "source_statements": sorted(source_stmts),
            "inferred_context": ctx,
        }

    # Check which ground truth NOTES/DISC sections could get note_number
    candidate_notes = []
    for idx, section in enumerate(gt.sections):
        if section.statement_type not in ("NOTES",) and not section.statement_type.startswith("DISC."):
            continue
        if section.note_number:
            continue
        # Try to match section label to a note context
        label_lower = section.label.lower() if section.label else ""
        for note_base, info in primary_notes.items():
            if info["inferred_context"] and label_lower:
                # Check if the label matches the context keywords
                ctx = info["inferred_context"]
                for lbl in info["labels"]:
                    if any(kw in label_lower for kw in lbl.lower().split()[:3] if len(kw) > 3):
                        candidate_notes.append({
                            "section_idx": idx,
                            "section_label": section.label,
                            "candidate_note": note_base,
                            "context": ctx,
                            "evidence": lbl,
                        })
                        break

    return {
        "total_notes_in_primaries": len(primary_notes),
        "notes_with_context": sum(1 for v in primary_notes.values() if v["inferred_context"]),
        "note_details": {str(k): v for k, v in primary_notes.items()},
        "candidate_note_numbers": candidate_notes,
    }


# ── Section 2: Feature Extraction ────────────────────────────────────────────

def extract_features(table: dict) -> dict:
    rows = table.get("rows", [])
    columns = table.get("columns", [])
    vals = _table_parsed_values(table)

    value_cols = [c for c in columns if c.get("role") == "VALUE"]
    label_cols = [c for c in columns if c.get("role") == "LABEL"]

    small_ints = [v for v in vals if 1 <= v <= 500 and v == int(v)]
    pct_small = len(small_ints) / max(len(vals), 1)

    # Monotonicity of values (in order of appearance)
    ordered_vals = []
    for r in rows:
        for c in r.get("cells", []):
            pv = c.get("parsedValue")
            if pv is not None:
                ordered_vals.append(float(pv))
    if len(ordered_vals) > 1:
        increasing = sum(1 for i in range(1, len(ordered_vals))
                         if ordered_vals[i] >= ordered_vals[i-1])
        pct_mono = increasing / (len(ordered_vals) - 1)
    else:
        pct_mono = 0.0

    # Statement keyword count
    all_text = " ".join(r.get("label", "").lower() for r in rows)
    for r in rows:
        for c in r.get("cells", []):
            txt = (c.get("text") or "").lower()
            if txt:
                all_text += " " + txt
    kw_count = sum(1 for kw in _STATEMENT_KEYWORDS if kw in all_text)

    # Note pattern count (e.g. "1. Topic", "21) Something")
    note_pattern_count = sum(
        1 for r in rows
        if re.match(r'^\s*\d+\s*[.)]\s+\S', r.get("label", ""))
    )

    return {
        "table_id": table.get("tableId", ""),
        "page": table.get("pageNo"),
        "row_count": len(rows),
        "col_count": len(columns),
        "value_col_count": len(value_cols),
        "label_col_count": len(label_cols),
        "has_note_column": has_note_column(table),
        "header_row_count": table.get("headerRowCount", 0),
        "has_currency": _table_has_currency(table),
        "pct_small_ints": round(pct_small, 3),
        "pct_monotonic": round(pct_mono, 3),
        "max_value": max(vals) if vals else None,
        "mean_value": round(sum(vals) / len(vals), 1) if vals else None,
        "value_count": len(vals),
        "statement_kw_count": kw_count,
        "note_pattern_count": note_pattern_count,
        "pct_rows_with_label": round(
            sum(1 for r in rows if r.get("label", "").strip()) / max(len(rows), 1), 3
        ),
    }


# ── Section 3: Approach Comparison ───────────────────────────────────────────

def approach_a_current(tables: list[dict]) -> dict[int, str] | None:
    """Current _detect_toc heuristic."""
    return _detect_toc(tables)


def approach_b_enhanced(tables: list[dict]) -> dict[int, str] | None:
    """Enhanced heuristic with additional filters."""
    # Search tables on pages 1-10 (not just first 20 by index)
    candidates = [t for t in tables if (t.get("pageNo") or 999) <= 10]
    if not candidates:
        candidates = tables[:20]

    for tbl in candidates:
        rows = tbl.get("rows", [])
        if len(rows) < 3:
            continue

        if has_note_column(tbl):
            continue

        # Enhanced: reject tables with detected currency
        if _table_has_currency(tbl):
            continue

        value_cols = [c for c in tbl.get("columns", []) if c.get("role") == "VALUE"]
        if len(value_cols) > 4:
            continue

        # Collect entries
        entries = []
        for r in rows:
            cells = r.get("cells", [])
            label = r.get("label", "").strip()
            if label:
                page_num = None
                for c in cells:
                    pv = c.get("parsedValue")
                    if pv is not None and 1 < pv < 500 and pv == int(pv):
                        page_num = int(pv)
                if page_num is not None:
                    entries.append((label, page_num))

            for i, c in enumerate(cells):
                if c.get("colIdx", 0) == 0:
                    continue
                txt = (c.get("text") or "").strip()
                pv = c.get("parsedValue")
                if txt and pv is None:
                    for c2 in cells[i+1:]:
                        pv2 = c2.get("parsedValue")
                        if pv2 is not None and 1 < pv2 < 500 and pv2 == int(pv2):
                            entries.append((txt, int(pv2)))
                            break

        if len(entries) < 3:
            continue

        # Enhanced: reject if max value > 500
        max_val = max(p for _, p in entries)
        if max_val > 500:
            continue

        pages = [p for _, p in entries]
        increasing = sum(1 for i in range(1, len(pages)) if pages[i] >= pages[i-1])
        if increasing < len(pages) * 0.5:
            continue

        # Check keywords
        all_text = set()
        for label, _ in entries:
            all_text.add(label.lower())
        for r in rows:
            for c in r.get("cells", []):
                txt = (c.get("text") or "").strip().lower()
                if txt:
                    all_text.add(txt)
        combined = " ".join(all_text)
        has_kw = any(kw in combined for kw in _STATEMENT_KEYWORDS)
        if not has_kw:
            continue

        page_map = _parse_toc_entries(entries)
        primary_in_toc = {v for v in page_map.values()
                          if v in ("PNL", "SFP", "OCI", "CFS", "SOCIE")}
        if len(primary_in_toc) >= 2:
            return page_map

    return None


def approach_c_feature_score(tables: list[dict]) -> dict[int, str] | None:
    """Feature-score based approach."""
    candidates = [t for t in tables if (t.get("pageNo") or 999) <= 15]
    if not candidates:
        candidates = tables[:20]

    best_score = -999
    best_map = None

    for tbl in candidates:
        rows = tbl.get("rows", [])
        if len(rows) < 3:
            continue

        feat = extract_features(tbl)

        # Compute score
        score = 0.0
        page = feat["page"] or 999
        score += 2.0 * (page <= 5)
        score += 1.5 * (not feat["has_note_column"])
        score += 1.5 * (not feat["has_currency"])
        score += 2.0 * feat["pct_small_ints"]
        score += 2.0 * feat["pct_monotonic"]
        score += 1.0 * (feat["statement_kw_count"] >= 2)
        score += 0.5 * (feat["header_row_count"] == 0)
        score += 1.0 * ((feat["max_value"] or 99999) < 500)
        score -= 2.0 * feat["has_note_column"]
        score -= 1.0 * (feat["value_col_count"] > 4)
        score -= 1.0 * feat["has_currency"]

        # Need a minimum score to consider
        if score < 5.0:
            continue

        # Try to build a page map
        entries = []
        for r in rows:
            cells = r.get("cells", [])
            label = r.get("label", "").strip()
            if label:
                page_num = None
                for c in cells:
                    pv = c.get("parsedValue")
                    if pv is not None and 1 < pv < 500 and pv == int(pv):
                        page_num = int(pv)
                if page_num is not None:
                    entries.append((label, page_num))

        if len(entries) < 3:
            continue

        page_map = _parse_toc_entries(entries)
        primary_in_toc = {v for v in page_map.values()
                          if v in ("PNL", "SFP", "OCI", "CFS", "SOCIE")}
        if len(primary_in_toc) >= 2 and score > best_score:
            best_score = score
            best_map = page_map

    return best_map


def _find_docling_json(fixture_dir: Path) -> Path | None:
    """Find the Docling JSON for a fixture by searching the corpus directory."""
    name = fixture_dir.name
    if not _CORPUS_DIR.exists():
        return None
    # Search for matching Docling JSON in corpus
    for candidate in _CORPUS_DIR.rglob(f"*_docling.json"):
        # Match by fixture name appearing in the corpus path
        if name in str(candidate.parent.parent.name) or name in str(candidate.parent.name):
            return candidate
    return None


def _load_docling_tables(docling_path: Path) -> list[dict]:
    """Load tables from a Docling JSON file."""
    with open(docling_path) as f:
        data = json.load(f)
    return data.get("tables", [])


def _docling_di_info(fixture_dir: Path) -> dict:
    """Get raw Docling document_index info for a fixture.

    Returns dict with:
      - docling_found: bool
      - di_count: number of document_index tables
      - di_pages: list of pages with document_index tables
      - di_tables: list of (page, row_count, pct_page_refs, first_label) tuples
    """
    docling_path = _find_docling_json(fixture_dir)
    if docling_path is None:
        return {"docling_found": False, "di_count": 0, "di_pages": [], "di_tables": []}

    tables = _load_docling_tables(docling_path)
    di_tables = [t for t in tables if t.get("label") == "document_index"]

    di_details = []
    di_pages = []
    for t in di_tables:
        page = t["prov"][0]["page_no"] if t.get("prov") else 0
        di_pages.append(page)
        grid = t.get("data", {}).get("grid", [])

        # Count rows with page-number-like values in last column
        page_refs = 0
        for row in grid:
            if not row:
                continue
            last = row[-1]
            txt = last.get("text", "") if isinstance(last, dict) else str(last)
            try:
                v = int(txt.strip())
                if 1 <= v <= 500:
                    page_refs += 1
            except (ValueError, AttributeError):
                pass
        pct = page_refs / max(len(grid), 1)

        first_label = ""
        if grid and grid[0]:
            cell = grid[0][0]
            first_label = (cell.get("text", "") if isinstance(cell, dict) else str(cell))[:60]

        di_details.append({
            "page": page,
            "row_count": len(grid),
            "pct_page_refs": round(pct, 2),
            "first_label": first_label,
        })

    return {
        "docling_found": True,
        "di_count": len(di_tables),
        "di_pages": sorted(set(di_pages)),
        "di_tables": di_details,
    }


def approach_d_docling_index(tables: list[dict], fixture_dir: Path) -> dict[int, str] | None:
    """Use Docling's document_index label as TOC detection baseline.

    Finds the Docling JSON for this fixture, identifies tables labeled
    'document_index', filters to those that look like real TOCs (≥50% of
    rows have page-number-like values), extracts (label, page) entries,
    and builds a page_map via _parse_toc_entries().
    """
    docling_path = _find_docling_json(fixture_dir)
    if docling_path is None:
        return None

    docling_tables = _load_docling_tables(docling_path)
    di_tables = [t for t in docling_tables if t.get("label") == "document_index"]
    if not di_tables:
        return None

    # Try each document_index table, take the first that qualifies as a real TOC
    for t in di_tables:
        grid = t.get("data", {}).get("grid", [])
        if len(grid) < 3:
            continue

        # Extract (label, page_number) entries
        entries = []
        page_ref_count = 0
        for row in grid:
            if not row:
                continue
            # Label is first column, page number is last column
            label_cell = row[0]
            label = (label_cell.get("text", "") if isinstance(label_cell, dict)
                     else str(label_cell)).strip()
            if not label:
                # Try concatenating non-last columns as label
                parts = []
                for cell in row[:-1]:
                    txt = (cell.get("text", "") if isinstance(cell, dict)
                           else str(cell)).strip()
                    if txt:
                        parts.append(txt)
                label = " ".join(parts)

            last_cell = row[-1]
            last_txt = (last_cell.get("text", "") if isinstance(last_cell, dict)
                        else str(last_cell)).strip()
            try:
                page_num = int(last_txt)
                if 1 <= page_num <= 500:
                    page_ref_count += 1
                    if label:
                        entries.append((label, page_num))
            except (ValueError, AttributeError):
                pass

        # Require ≥50% of rows to have page references
        pct_page_refs = page_ref_count / max(len(grid), 1)
        if pct_page_refs < 0.5:
            continue

        if len(entries) < 3:
            continue

        page_map = _parse_toc_entries(entries)
        primary_in_toc = {v for v in page_map.values()
                          if v in ("PNL", "SFP", "OCI", "CFS", "SOCIE")}
        if len(primary_in_toc) >= 2:
            return page_map

    return None


# ── Section 3b: MLP Classifier ──────────────────────────────────────────────

def _extract_mlp_features(table: dict, table_idx: int, total_tables: int) -> list[float]:
    """Extract numeric feature vector for MLP classification.

    Returns a fixed-length vector combining table content features
    with page/position features.
    """
    rows = table.get("rows", [])
    columns = table.get("columns", [])
    vals = _table_parsed_values(table)
    page = table.get("pageNo") or 0

    value_cols = [c for c in columns if c.get("role") == "VALUE"]
    small_ints = [v for v in vals if 1 <= v <= 500 and v == int(v)]

    # Monotonicity
    ordered_vals = []
    for r in rows:
        for c in r.get("cells", []):
            pv = c.get("parsedValue")
            if pv is not None:
                ordered_vals.append(float(pv))
    if len(ordered_vals) > 1:
        increasing = sum(1 for i in range(1, len(ordered_vals))
                         if ordered_vals[i] >= ordered_vals[i - 1])
        pct_mono = increasing / (len(ordered_vals) - 1)
    else:
        pct_mono = 0.0

    # Statement keywords
    all_text = " ".join(r.get("label", "").lower() for r in rows)
    for r in rows:
        for c in r.get("cells", []):
            txt = (c.get("text") or "").lower()
            if txt:
                all_text += " " + txt
    kw_count = sum(1 for kw in _STATEMENT_KEYWORDS if kw in all_text)

    # Note pattern count
    note_patterns = sum(
        1 for r in rows
        if re.match(r'^\s*\d+\s*[.)]\s+\S', r.get("label", ""))
    )

    # Value statistics
    max_val = max(vals) if vals else 0.0
    mean_val = (sum(vals) / len(vals)) if vals else 0.0
    std_val = 0.0
    if len(vals) > 1:
        std_val = (sum((v - mean_val) ** 2 for v in vals) / len(vals)) ** 0.5
    pct_negative = sum(1 for v in vals if v < 0) / max(len(vals), 1)

    # Label features
    labels = [r.get("label", "").strip() for r in rows]
    pct_with_label = sum(1 for l in labels if l) / max(len(labels), 1)
    avg_label_len = (sum(len(l) for l in labels if l) / max(sum(1 for l in labels if l), 1))
    # Ratio of labels containing dots/leaders (common in TOCs)
    pct_dotleader = sum(1 for l in labels if "...." in l or "…" in l) / max(len(labels), 1)

    return [
        # Page/position features
        float(page),
        1.0 if page <= 5 else 0.0,
        1.0 if page <= 15 else 0.0,
        table_idx / max(total_tables, 1),  # relative position in document

        # Table structure
        float(len(rows)),
        float(len(columns)),
        float(len(value_cols)),
        float(table.get("headerRowCount", 0)),
        1.0 if has_note_column(table) else 0.0,
        1.0 if _table_has_currency(table) else 0.0,

        # Value distribution
        len(small_ints) / max(len(vals), 1),  # pct_small_ints
        pct_mono,
        float(min(max_val, 1e8)),  # cap to avoid scale issues
        float(min(abs(mean_val), 1e8)),
        float(min(std_val, 1e8)),
        float(len(vals)),
        pct_negative,

        # Content features
        float(kw_count),
        float(note_patterns),
        pct_with_label,
        float(min(avg_label_len, 200)),
        pct_dotleader,
    ]


_MLP_FEATURE_NAMES = [
    "page", "page_le5", "page_le15", "rel_position",
    "row_count", "col_count", "value_col_count", "header_row_count",
    "has_note_column", "has_currency",
    "pct_small_ints", "pct_monotonic", "max_value", "mean_value_abs",
    "std_value", "value_count", "pct_negative",
    "statement_kw_count", "note_pattern_count",
    "pct_rows_with_label", "avg_label_len", "pct_dotleader",
]


def build_mlp_dataset(fixtures: list[Path]) -> tuple[list[dict], list[list[float]], list[int], list[str]]:
    """Build training dataset for MLP from all GT fixtures.

    Returns:
        samples: list of dicts with doc/table metadata
        X: feature matrix (list of feature vectors)
        y: labels (1=TOC, 0=not)
        doc_ids: document ID per sample (for LODOCV splits)
    """
    samples = []
    X = []
    y = []
    doc_ids = []

    for fixture_dir in fixtures:
        doc_name = fixture_dir.name
        tg_path = fixture_dir / "table_graphs.json"
        if not tg_path.exists():
            continue

        gt = _load_gt_lenient(str(fixture_dir))
        if gt is None:
            continue

        with open(tg_path) as f:
            tg = json.load(f)
        tables = tg.get("tables", [])

        # Determine GT TOC pages
        toc_pages = set()
        for s in gt.sections:
            if s.statement_type == "TOC" and s.start_page is not None:
                end = s.end_page or s.start_page
                for p in range(s.start_page, end + 1):
                    toc_pages.add(p)

        # Use first 30 tables per document
        for idx, t in enumerate(tables[:30]):
            page = t.get("pageNo")
            is_toc = (page in toc_pages) if toc_pages else False

            features = _extract_mlp_features(t, idx, len(tables))
            samples.append({
                "doc": doc_name,
                "table_id": t.get("tableId", f"t{idx}"),
                "page": page,
                "is_toc": is_toc,
            })
            X.append(features)
            y.append(1 if is_toc else 0)
            doc_ids.append(doc_name)

    return samples, X, y, doc_ids


def run_mlp_lodocv(fixtures: list[Path]) -> dict:
    """Run MLP with leave-one-document-out cross-validation.

    Returns per-document predictions and aggregate metrics.
    """
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler
    import numpy as np

    samples, X_raw, y_raw, doc_ids = build_mlp_dataset(fixtures)
    X = np.array(X_raw, dtype=np.float64)
    y = np.array(y_raw)
    doc_ids_arr = np.array(doc_ids)

    # Replace NaN/inf
    X = np.nan_to_num(X, nan=0.0, posinf=1e8, neginf=-1e8)

    unique_docs = sorted(set(doc_ids))
    all_preds = np.zeros(len(y), dtype=int)
    all_probs = np.zeros(len(y), dtype=float)

    per_doc_results = {}

    for held_out_doc in unique_docs:
        train_mask = doc_ids_arr != held_out_doc
        test_mask = doc_ids_arr == held_out_doc

        X_train, y_train = X[train_mask], y[train_mask]
        X_test = X[test_mask]

        scaler = StandardScaler()
        X_train_s = scaler.fit_transform(X_train)
        X_test_s = scaler.transform(X_test)

        # Class weight balancing via oversampling positive class
        pos_count = y_train.sum()
        neg_count = len(y_train) - pos_count
        if pos_count > 0 and neg_count > 0:
            ratio = neg_count / pos_count
            pos_indices = np.where(y_train == 1)[0]
            oversample = np.repeat(pos_indices, max(int(ratio) - 1, 0))
            if len(oversample) > 0:
                X_train_s = np.vstack([X_train_s, X_train_s[oversample]])
                y_train = np.concatenate([y_train, y_train[oversample]])

        clf = MLPClassifier(
            hidden_layer_sizes=(32, 16),
            activation="relu",
            max_iter=500,
            random_state=42,
            early_stopping=True,
            validation_fraction=0.15,
        )
        clf.fit(X_train_s, y_train)

        preds = clf.predict(X_test_s)
        probs = clf.predict_proba(X_test_s)[:, 1] if hasattr(clf, "predict_proba") else preds.astype(float)

        all_preds[test_mask] = preds
        all_probs[test_mask] = probs

        # Per-document: did we detect a TOC?
        test_indices = np.where(test_mask)[0]
        detected_toc_pages = set()
        for i in test_indices:
            if all_preds[i] == 1:
                detected_toc_pages.add(samples[i]["page"])

        gt_toc_pages = set()
        gt_has_toc = False
        gt = _load_gt_lenient(str(Path(__file__).parent / "fixtures" / held_out_doc))
        if gt:
            gt_has_toc = gt.has_toc
            for s in gt.sections:
                if s.statement_type == "TOC" and s.start_page is not None:
                    gt_toc_pages.add(s.start_page)

        per_doc_results[held_out_doc] = {
            "gt_has_toc": gt_has_toc,
            "gt_toc_pages": sorted(gt_toc_pages),
            "detected_toc_pages": sorted(detected_toc_pages),
            "n_tables": int(test_mask.sum()),
            "n_predicted_toc": int(preds.sum()),
        }

    # Aggregate table-level metrics
    tp = int(((all_preds == 1) & (y == 1)).sum())
    fp = int(((all_preds == 1) & (y == 0)).sum())
    fn = int(((all_preds == 0) & (y == 1)).sum())
    tn = int(((all_preds == 0) & (y == 0)).sum())

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)

    # Feature importance via permutation (rough)
    feature_importance = []
    for i, fname in enumerate(_MLP_FEATURE_NAMES):
        feature_importance.append((fname, float(np.abs(X[:, i][y == 1].mean() - X[:, i][y == 0].mean())
                                                / max(X[:, i].std(), 1e-9))))

    feature_importance.sort(key=lambda x: -x[1])

    return {
        "table_level": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        },
        "per_doc": per_doc_results,
        "feature_importance": feature_importance[:10],
        "total_samples": len(y),
        "positive_samples": int(y.sum()),
    }


def evaluate_approach(page_map: dict[int, str] | None,
                      gt: TocGroundTruth,
                      doc_name: str) -> dict:
    """Evaluate a detection result against ground truth."""
    gt_has_toc = gt.has_toc
    detected = page_map is not None

    result = {
        "gt_has_toc": gt_has_toc,
        "detected": detected,
        "correct_detection": (detected == gt_has_toc),
    }

    # If we have sections in GT and a page_map, compute precision/recall
    gt_primary_pages = {}
    for s in gt.sections:
        if s.statement_type in ("PNL", "SFP", "OCI", "CFS", "SOCIE"):
            if s.start_page is not None:
                gt_primary_pages[s.start_page] = s.statement_type

    if page_map and gt_primary_pages:
        # Precision: what fraction of detected primary page mappings are correct?
        detected_primaries = {p: s for p, s in page_map.items()
                              if s in ("PNL", "SFP", "OCI", "CFS", "SOCIE")}
        correct = sum(1 for p, s in detected_primaries.items()
                      if gt_primary_pages.get(p) == s)
        precision = correct / max(len(detected_primaries), 1)

        # Recall: what fraction of GT primary pages are in the detected map?
        recalled = sum(1 for p, s in gt_primary_pages.items()
                       if page_map.get(p) == s)
        recall = recalled / max(len(gt_primary_pages), 1)

        result["precision"] = round(precision, 3)
        result["recall"] = round(recall, 3)
        result["gt_primary_count"] = len(gt_primary_pages)
        result["detected_primary_count"] = len(detected_primaries)
        result["correct_count"] = correct

    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def find_fixtures() -> list[Path]:
    """Find all fixture directories with ground truth."""
    base = Path(__file__).parent / "fixtures"
    fixtures = []
    for toc_file in sorted(base.rglob("ground_truth/toc.json")):
        fixtures.append(toc_file.parent.parent)
    return fixtures


def analyze_document(fixture_dir: Path) -> dict:
    doc_name = fixture_dir.name
    tg_path = fixture_dir / "table_graphs.json"

    gt = _load_gt_lenient(str(fixture_dir))
    if gt is None:
        return {"doc": doc_name, "error": "no ground truth"}

    if not tg_path.exists():
        return {"doc": doc_name, "error": "no table_graphs.json"}

    with open(tg_path) as f:
        tg = json.load(f)
    tables = tg.get("tables", [])

    result = {
        "doc": doc_name,
        "has_toc": gt.has_toc,
        "gt_section_count": len(gt.sections),
        "table_count": len(tables),
    }

    # 1a. Page reference validation
    result["page_ref_findings"] = validate_page_refs(tables, gt)

    # 1b. Note reference extraction
    result["note_refs"] = extract_note_refs(tables, gt)

    # 2. Feature extraction for early tables
    toc_pages = set()
    for s in gt.sections:
        if s.statement_type == "TOC" and s.start_page is not None:
            end = s.end_page or s.start_page
            for p in range(s.start_page, end + 1):
                toc_pages.add(p)

    features = []
    for t in tables[:20]:
        feat = extract_features(t)
        feat["is_toc_gt"] = t.get("pageNo") in toc_pages if toc_pages else None
        features.append(feat)
    result["features"] = features

    # 3. Approach comparison
    result["approach_a"] = evaluate_approach(
        approach_a_current(tables), gt, doc_name)
    result["approach_b"] = evaluate_approach(
        approach_b_enhanced(tables), gt, doc_name)
    result["approach_c"] = evaluate_approach(
        approach_c_feature_score(tables), gt, doc_name)
    result["approach_d"] = evaluate_approach(
        approach_d_docling_index(tables, fixture_dir), gt, doc_name)

    # 4. Raw Docling document_index info
    result["docling_di"] = _docling_di_info(fixture_dir)

    return result


def print_summary(results: list[dict], mlp_results: dict | None = None) -> None:
    print("\n" + "=" * 80)
    print("TOC GROUND TRUTH ANALYSIS REPORT")
    print("=" * 80)

    # 1. Page reference summary
    print("\n── Page Reference Validation ──────────────────────────────────")
    for r in results:
        if "error" in r:
            print(f"\n  {r['doc']}: {r['error']}")
            continue
        findings = r.get("page_ref_findings", [])
        if not findings:
            continue
        ok = sum(1 for f in findings if f["status"] == "ok")
        warn = sum(1 for f in findings if f["status"] == "warning")
        print(f"\n  {r['doc']} ({ok} ok, {warn} warnings):")
        for f in findings:
            icon = "OK" if f["status"] == "ok" else "!!"
            label = f["label"][:45] if f["label"] else f["statement_type"]
            print(f"    [{icon}] {label:45s} p.{str(f.get('page','-')):>3s}  {f['detail']}")

    # 2. Note reference summary
    print("\n── Note Reference Summary ────────────────────────────────────")
    for r in results:
        if "error" in r:
            continue
        notes = r.get("note_refs", {})
        total = notes.get("total_notes_in_primaries", 0)
        with_ctx = notes.get("notes_with_context", 0)
        if total > 0:
            print(f"  {r['doc']:40s} {total:3d} notes in primaries, "
                  f"{with_ctx:3d} with inferred context")

    # 3. Feature analysis
    print("\n── TOC vs Non-TOC Feature Comparison ─────────────────────────")
    toc_features = []
    non_toc_features = []
    for r in results:
        if "error" in r:
            continue
        for feat in r.get("features", []):
            if feat.get("is_toc_gt") is True:
                toc_features.append(feat)
            elif feat.get("is_toc_gt") is False:
                non_toc_features.append(feat)

    if toc_features and non_toc_features:
        feature_names = ["pct_small_ints", "pct_monotonic", "has_note_column",
                         "has_currency", "value_col_count", "header_row_count",
                         "statement_kw_count", "max_value", "row_count"]
        print(f"  {'Feature':25s} {'TOC (avg)':>12s} {'Non-TOC (avg)':>14s}  {'Discriminative?':>15s}")
        print(f"  {'-'*25} {'-'*12} {'-'*14}  {'-'*15}")
        for fn in feature_names:
            toc_vals = [f[fn] for f in toc_features if f[fn] is not None]
            non_vals = [f[fn] for f in non_toc_features if f[fn] is not None]
            if toc_vals and non_vals:
                toc_avg = sum(toc_vals) / len(toc_vals)
                non_avg = sum(non_vals) / len(non_vals)
                # Simple discriminativeness: ratio of difference to combined range
                if isinstance(toc_avg, bool):
                    toc_avg = float(toc_avg)
                    non_avg = float(non_avg)
                diff = abs(toc_avg - non_avg)
                combined = max(abs(toc_avg), abs(non_avg), 0.001)
                disc = diff / combined
                disc_label = "***" if disc > 0.8 else "**" if disc > 0.5 else "*" if disc > 0.2 else ""
                if fn == "max_value":
                    print(f"  {fn:25s} {toc_avg:12.0f} {non_avg:14.0f}  {disc_label:>15s}")
                elif isinstance(toc_avg, float) and toc_avg < 10:
                    print(f"  {fn:25s} {toc_avg:12.3f} {non_avg:14.3f}  {disc_label:>15s}")
                else:
                    print(f"  {fn:25s} {toc_avg:12.1f} {non_avg:14.1f}  {disc_label:>15s}")
    else:
        print("  Insufficient labeled data for feature comparison")
        print(f"  TOC tables: {len(toc_features)}, Non-TOC tables: {len(non_toc_features)}")

    # 4. Docling document_index vs Ground Truth
    print("\n── Docling document_index vs Ground Truth ────────────────────")
    print(f"  {'Document':42s} {'GT':>4s} {'DI#':>4s} {'DI pages':>20s} {'Status':>8s}")
    print(f"  {'-'*42} {'-'*4} {'-'*4} {'-'*20} {'-'*8}")
    di_stats = {"HIT": 0, "TN": 0, "MISS": 0, "FP": 0, "NO_GT_PG": 0}
    for r in results:
        if "error" in r:
            continue
        di = r.get("docling_di", {})
        gt_toc = r.get("has_toc", False)
        di_count = di.get("di_count", 0)
        di_pages = di.get("di_pages", [])

        # Determine GT TOC pages
        gt_obj = _load_gt_lenient(str(Path(__file__).parent / "fixtures" / r["doc"]))
        gt_toc_pages = []
        if gt_obj:
            for s in gt_obj.sections:
                if s.statement_type == "TOC" and s.start_page is not None:
                    gt_toc_pages.append(s.start_page)

        if gt_toc and gt_toc_pages:
            status = "HIT" if any(p in di_pages for p in gt_toc_pages) else "MISS"
        elif gt_toc and not gt_toc_pages:
            status = "NO_GT_PG"
        elif not gt_toc and di_count == 0:
            status = "TN"
        elif not gt_toc and di_count > 0:
            status = "FP"
        else:
            status = "?"
        di_stats[status] = di_stats.get(status, 0) + 1

        gt_label = "Y" if gt_toc else "N"
        pages_str = str(di_pages) if di_pages else "-"
        print(f"  {r['doc']:42s} {gt_label:>4s} {di_count:>4d} {pages_str:>20s} {status:>8s}")

    print(f"\n  Summary: {di_stats}")
    if di_stats.get("HIT", 0) + di_stats.get("MISS", 0) > 0:
        total_pos = di_stats.get("HIT", 0) + di_stats.get("MISS", 0) + di_stats.get("NO_GT_PG", 0)
        total_neg = di_stats.get("TN", 0) + di_stats.get("FP", 0)
        raw_recall = di_stats.get("HIT", 0) / max(di_stats.get("HIT", 0) + di_stats.get("MISS", 0), 1)
        raw_precision = di_stats.get("HIT", 0) / max(di_stats.get("HIT", 0) + di_stats.get("FP", 0), 1)
        print(f"  Raw label recall:    {raw_recall:.0%} ({di_stats.get('HIT',0)}/{di_stats.get('HIT',0)+di_stats.get('MISS',0)} docs with GT TOC pages)")
        print(f"  Raw label precision: {raw_precision:.0%} ({di_stats.get('HIT',0)}/{di_stats.get('HIT',0)+di_stats.get('FP',0)} docs where Docling found doc_index)")

    # Show FP details
    fp_docs = [r for r in results if "error" not in r
               and not r.get("has_toc") and r.get("docling_di", {}).get("di_count", 0) > 0]
    if fp_docs:
        print("\n  False positive details (Docling labels non-TOC tables as document_index):")
        for r in fp_docs:
            di = r.get("docling_di", {})
            for dt in di.get("di_tables", []):
                print(f"    {r['doc']:35s} p.{dt['page']:>3d}  "
                      f"rows={dt['row_count']:>3d}  page_refs={dt['pct_page_refs']:.0%}  "
                      f"{dt['first_label']}")

    # 5. Approach comparison
    print("\n── Approach Comparison ────────────────────────────────────────")
    approaches = ["approach_a", "approach_b", "approach_c", "approach_d"]
    names = {"approach_a": "Current heuristic", "approach_b": "Enhanced heuristic",
             "approach_c": "Feature-score", "approach_d": "Docling baseline"}

    # Per-document results
    print(f"\n  {'Document':40s} {'GT':>4s} {'A':>4s} {'B':>4s} {'C':>4s} {'D':>4s}")
    print(f"  {'-'*40} {'-'*4} {'-'*4} {'-'*4} {'-'*4} {'-'*4}")
    for r in results:
        if "error" in r:
            continue
        gt_toc = "Y" if r.get("has_toc") else "N"
        cols = [gt_toc]
        for a in approaches:
            ar = r.get(a, {})
            if ar.get("detected"):
                cols.append("Y" if ar.get("correct_detection") else "FP")
            else:
                cols.append("N" if ar.get("correct_detection") else "FN")
        print(f"  {r['doc']:40s} {cols[0]:>4s} {cols[1]:>4s} {cols[2]:>4s} {cols[3]:>4s} {cols[4]:>4s}")

    # Aggregate
    print(f"\n  {'Metric':25s}", end="")
    for a in approaches:
        print(f"  {names[a]:>20s}", end="")
    print()
    print(f"  {'-'*25}", end="")
    for _ in approaches:
        print(f"  {'-'*20}", end="")
    print()

    for metric in ["correct_detection", "precision", "recall"]:
        print(f"  {metric:25s}", end="")
        for a in approaches:
            vals = [r[a].get(metric) for r in results
                    if "error" not in r and r[a].get(metric) is not None]
            if vals:
                if isinstance(vals[0], bool):
                    avg = sum(vals) / len(vals)
                    print(f"  {avg:18.0%} ({sum(vals)}/{len(vals)})", end="")
                else:
                    avg = sum(vals) / len(vals)
                    print(f"  {avg:20.3f}", end="")
            else:
                print(f"  {'n/a':>20s}", end="")
        print()

    # Ground truth issues
    print("\n── Ground Truth Issues Found ──────────────────────────────────")
    for r in results:
        if "error" in r:
            continue
        issues = []
        # Check for contradictions
        gt = _load_gt_lenient(str(Path(__file__).parent / "fixtures" / r["doc"]))
        if gt:
            toc_sections = [s for s in gt.sections if s.statement_type == "TOC"]
            if toc_sections and not gt.has_toc:
                issues.append("has_toc=false but TOC section exists")
            if gt.has_toc and not toc_sections and gt.sections:
                issues.append("has_toc=true but no TOC section defined")

            # Check for overlapping page ranges
            ranges = [(s.start_page, s.end_page or s.start_page, s.statement_type)
                      for s in gt.sections if s.start_page is not None]
            for i, (s1, e1, t1) in enumerate(ranges):
                for j, (s2, e2, t2) in enumerate(ranges):
                    if i >= j:
                        continue
                    if s1 <= e2 and s2 <= e1 and t1 != t2:
                        issues.append(f"Overlapping: {t1}(p.{s1}-{e1}) vs {t2}(p.{s2}-{e2})")

            # Unvalidated sections
            unval = sum(1 for s in gt.sections if not s.validated)
            if unval > 0:
                issues.append(f"{unval} unvalidated section(s)")

        if issues:
            print(f"  {r['doc']}:")
            for issue in issues:
                print(f"    - {issue}")

    # 6. MLP classifier results
    if mlp_results:
        print("\n── MLP Classifier (LODOCV) ────────────────────────────────────")
        tl = mlp_results["table_level"]
        print(f"  Table-level:  TP={tl['tp']}  FP={tl['fp']}  FN={tl['fn']}  TN={tl['tn']}")
        print(f"  Precision: {tl['precision']:.3f}   Recall: {tl['recall']:.3f}   F1: {tl['f1']:.3f}")
        print(f"  Samples: {mlp_results['total_samples']} ({mlp_results['positive_samples']} positive)")

        # Per-document results
        print(f"\n  {'Document':40s} {'GT':>4s} {'Pred':>5s} {'GT_pages':>12s} {'Det_pages':>12s}")
        print(f"  {'-'*40} {'-'*4} {'-'*5} {'-'*12} {'-'*12}")

        mlp_doc_correct = 0
        mlp_doc_total = 0
        mlp_doc_tp = mlp_doc_fp = mlp_doc_fn = mlp_doc_tn = 0

        for doc_name in sorted(mlp_results["per_doc"]):
            dr = mlp_results["per_doc"][doc_name]
            gt_label = "Y" if dr["gt_has_toc"] else "N"
            detected = len(dr["detected_toc_pages"]) > 0
            pred_label = "Y" if detected else "N"
            gt_pages = str(dr["gt_toc_pages"]) if dr["gt_toc_pages"] else "-"
            det_pages = str(dr["detected_toc_pages"]) if dr["detected_toc_pages"] else "-"
            correct = (detected == dr["gt_has_toc"])
            marker = "" if correct else " <--"
            print(f"  {doc_name:40s} {gt_label:>4s} {pred_label:>5s} {gt_pages:>12s} {det_pages:>12s}{marker}")

            mlp_doc_total += 1
            if correct:
                mlp_doc_correct += 1
            if dr["gt_has_toc"] and detected:
                mlp_doc_tp += 1
            elif not dr["gt_has_toc"] and detected:
                mlp_doc_fp += 1
            elif dr["gt_has_toc"] and not detected:
                mlp_doc_fn += 1
            else:
                mlp_doc_tn += 1

        doc_prec = mlp_doc_tp / max(mlp_doc_tp + mlp_doc_fp, 1)
        doc_recall = mlp_doc_tp / max(mlp_doc_tp + mlp_doc_fn, 1)
        doc_f1 = 2 * doc_prec * doc_recall / max(doc_prec + doc_recall, 1e-9)
        print(f"\n  Doc-level: {mlp_doc_correct}/{mlp_doc_total} correct "
              f"({mlp_doc_correct/max(mlp_doc_total,1):.0%})")
        print(f"  Doc precision: {doc_prec:.3f}  recall: {doc_recall:.3f}  F1: {doc_f1:.3f}")

        # Feature importance
        print(f"\n  Top features (mean separation between TOC/non-TOC):")
        for fname, score in mlp_results["feature_importance"]:
            bar = "#" * int(score * 10)
            print(f"    {fname:25s} {score:6.2f}  {bar}")

    print()


def main():
    fixtures = find_fixtures()
    print(f"Found {len(fixtures)} fixtures with ground truth\n")

    results = []
    for fixture_dir in fixtures:
        doc_name = fixture_dir.name
        if VERBOSE:
            print(f"Analyzing {doc_name}...")
        result = analyze_document(fixture_dir)
        results.append(result)

    # Run MLP classifier with LODOCV
    mlp_results = None
    try:
        print("\nRunning MLP classifier (LODOCV)...")
        mlp_results = run_mlp_lodocv(fixtures)
    except ImportError:
        print("  scikit-learn not installed, skipping MLP")
    except Exception as e:
        print(f"  MLP failed: {e}")

    # Write JSON report
    report_path = Path(__file__).parent / "toc_analysis_report.json"
    report_data = {"per_document": results}
    if mlp_results:
        report_data["mlp"] = mlp_results
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
    print(f"JSON report written to {report_path}")

    # Print human-readable summary
    print_summary(results, mlp_results)


if __name__ == "__main__":
    main()
