#!/usr/bin/env python3
"""
classify_tables.py — Classify tables in table_graphs.json by statement type.

Reads Docling-extracted table_graphs.json files and sets statementComponent
for each table using:
  1. Table of contents (TOC) detection → page-range → section map
  2. sectionPath metadata (if available)
  3. Row label + column header keyword matching

Pipeline position:
    classify_tables.py → pretag_all.py → structural_inference.py → check_consistency.py

Usage:
    python3 eval/classify_tables.py <table_graphs.json> [--dry-run] [--verbose]
    python3 eval/classify_tables.py --all   # scan corpus dirs
"""

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from table_classifier import classify_table


# ── TOC detection ─────────────────────────────────────────────────

# Keywords that indicate a TOC entry maps to a primary statement
_STATEMENT_KEYWORDS = {
    # English
    "income statement": "PNL", "profit or loss": "PNL",
    "statement of profit": "PNL", "consolidated income": "PNL",
    "profit and loss": "PNL",
    "balance sheet": "SFP", "financial position": "SFP",
    "statement of financial position": "SFP", "consolidated balance": "SFP",
    "comprehensive income": "OCI", "other comprehensive": "OCI",
    "statement of comprehensive": "OCI",
    "cash flow": "CFS", "cash flows": "CFS",
    "changes in equity": "SOCIE", "statement of changes": "SOCIE",
    "notes to the": "NOTES", "notes to the financial": "NOTES",
    # German
    "gewinn- und verlustrechnung": "PNL", "erfolgsrechnung": "PNL",
    "gesamtergebnisrechnung": "OCI",
    "konzern-gewinn": "PNL", "konzerngewinn": "PNL",
    "bilanz": "SFP", "konzernbilanz": "SFP",
    "kapitalflussrechnung": "CFS", "cashflow": "CFS",
    "eigenkapitalveränderung": "SOCIE", "veränderung des eigenkapitals": "SOCIE",
    "konzern-eigenkapitalveränderung": "SOCIE",
    "anhang": "NOTES", "erläuterungen": "NOTES", "anmerkungen": "NOTES",
    "anlagenspiegel": "DISC.PPE",
    "beteiligungsliste": "DISC.ASSOCIATES",
    "segmentbericht": "DISC.SEGMENTS",
}

# Note number → disclosure context patterns
_NOTE_PATTERNS = [
    (r"segment", "DISC.SEGMENTS"),
    (r"revenue|umsatz|erlös", "DISC.REVENUE"),
    (r"property.+plant|sachanlag|ppe", "DISC.PPE"),
    (r"intangible|immateriell", "DISC.INTANGIBLES"),
    (r"goodwill|firmenwert", "DISC.GOODWILL"),
    (r"investment property|als finanzinvestition", "DISC.INV_PROP"),
    (r"lease|leasing|nutzungsrecht", "DISC.LEASES"),
    (r"provision|rückstellung", "DISC.PROVISIONS"),
    (r"tax|steuer", "DISC.TAX"),
    (r"employee.+benefit|pension|abfertigung|personal", "DISC.EMPLOYEE_BENEFITS"),
    (r"earnings per share|ergebnis je aktie", "DISC.EPS"),
    (r"share.+based|aktienbasiert", "DISC.SHARE_BASED"),
    (r"business combination|unternehmenserwerb|akquisition", "DISC.BCA"),
    (r"financial instrument|finanzinstrument", "DISC.FIN_INST"),
    (r"fair value|beizulegender zeitwert", "DISC.FAIR_VALUE"),
    (r"inventor|vorräte|vorrat", "DISC.INVENTORIES"),
    (r"borrowing|anleihe|darlehen", "DISC.BORROWINGS"),
    (r"related part|nahestehend", "DISC.RELATED_PARTIES"),
    (r"contingent|eventual", "DISC.CONTINGENCIES"),
    (r"held for sale|discontinued|aufgegeben", "DISC.HELD_FOR_SALE"),
    (r"hedge|sicherung", "DISC.HEDGE"),
    (r"credit risk|kreditrisiko", "DISC.CREDIT_RISK"),
    (r"biological|biologisch", "DISC.BIOLOGICAL_ASSETS"),
    (r"government grant|zuwendung", "DISC.GOV_GRANTS"),
    (r"dividend|dividende", "DISC.DIVIDENDS"),
    (r"associate|joint venture|assoziiert|gemeinschaft", "DISC.ASSOCIATES"),
    (r"impairment|wertminderung", "DISC.IMPAIRMENT"),
    (r"depreciation|amortisation|abschreibung", "DISC.PPE"),
    (r"capital|eigenkapital", "DISC.EQUITY"),
    (r"operating expense|material|materialaufwand", "DISC.EXPENSES"),
]


def _detect_toc(tables: list[dict]) -> dict[int, str] | None:
    """Scan first tables for a table of contents with page references.

    Returns page→section map or None if no TOC found.
    """
    for tbl in tables[:20]:
        rows = tbl.get("rows", [])
        if len(rows) < 3:
            continue

        # Count VALUE columns
        value_cols = [c for c in tbl.get("columns", []) if c.get("role") == "VALUE"]

        # Collect (label, page_number) pairs
        entries = []
        for r in rows:
            label = r.get("label", "").strip()
            if not label:
                continue

            # Look for page numbers in cells
            page_num = None
            for c in r.get("cells", []):
                pv = c.get("parsedValue")
                if pv is not None and 1 < pv < 500 and pv == int(pv):
                    # Check it's plausibly a page number (not a financial value)
                    # Page numbers are typically small integers in the rightmost column
                    page_num = int(pv)

            if page_num is not None:
                entries.append((label, page_num))

        if len(entries) < 3:
            continue

        # Distinguish TOC from KPI summary:
        # TOC: most values are monotonically increasing page numbers
        # KPI: values are financial amounts (large, not monotonic)
        pages = [p for _, p in entries]
        if len(value_cols) >= 3:
            # Multiple value columns = likely KPI summary, not TOC
            continue

        # Check for monotonically increasing tendency (allowing some noise)
        increasing = sum(1 for i in range(1, len(pages)) if pages[i] >= pages[i-1])
        if increasing < len(pages) * 0.5:
            continue

        # Check for statement keywords in entries
        has_statement_kw = False
        for label, _ in entries:
            label_lower = label.lower()
            for kw in _STATEMENT_KEYWORDS:
                if kw in label_lower:
                    has_statement_kw = True
                    break
            if has_statement_kw:
                break

        if not has_statement_kw:
            continue

        # Build page→section map
        return _parse_toc_entries(entries)

    return None


def _parse_toc_entries(entries: list[tuple[str, int]]) -> dict[int, str]:
    """Convert TOC entries to page→section map."""
    page_map: dict[int, str] = {}

    for label, page in entries:
        label_lower = label.lower().strip()

        # Check primary statement keywords
        matched = False
        for kw, stmt in _STATEMENT_KEYWORDS.items():
            if kw in label_lower:
                page_map[page] = stmt
                matched = True
                break

        if matched:
            continue

        # Check note number patterns (e.g., "6. Segmentberichterstattung")
        # Strip leading note numbers
        note_label = re.sub(r'^\d+[\.\)]\s*', '', label_lower)
        for pattern, disc_ctx in _NOTE_PATTERNS:
            if re.search(pattern, note_label):
                page_map[page] = disc_ctx
                break

    return page_map


def _classify_by_page(table: dict, page_map: dict[int, str]) -> str | None:
    """Look up a table's page number in the TOC-derived section map."""
    page = table.get("pageNo")
    if page is None:
        return None

    # Direct match
    if page in page_map:
        return page_map[page]

    # Range match: find the section whose start page is closest but <= table page
    sorted_pages = sorted(page_map.keys())
    best_page = None
    for p in sorted_pages:
        if p <= page:
            best_page = p
        else:
            break

    if best_page is not None:
        section = page_map[best_page]
        # If the section is NOTES, don't assign it directly — let keyword
        # matching determine the specific DISC.* context
        if section == "NOTES":
            return None
        return section

    return None


# ── sectionPath classification ────────────────────────────────────

def _classify_by_section_path(table: dict) -> str | None:
    """Classify using sectionPath metadata."""
    section = table.get("metadata", {}).get("sectionPath", [])
    if not section:
        return None

    section_text = " ".join(section).lower()

    for kw, stmt in _STATEMENT_KEYWORDS.items():
        if kw in section_text:
            return stmt

    # Note patterns
    for pattern, disc_ctx in _NOTE_PATTERNS:
        if re.search(pattern, section_text):
            return disc_ctx

    return None


# ── Keyword classification ────────────────────────────────────────

def _classify_by_keywords(table: dict) -> str | None:
    """Classify using row labels and column headers."""
    rows = table.get("rows", [])
    columns = table.get("columns", [])

    # Build inputs for classify_table
    all_labels = [r.get("label", "").lower() for r in rows]
    labels_first10 = " ".join(all_labels[:10])
    labels_all = " ".join(all_labels)
    col_headers = " ".join(c.get("headerLabel", "").lower() for c in columns)
    first_label = all_labels[0].strip() if all_labels else ""

    # Check if table has any values
    value_col_indices = {c["colIdx"] for c in columns if c.get("role") == "VALUE"}
    has_values = any(
        c.get("parsedValue") is not None
        for r in rows
        for c in r.get("cells", [])
        if c.get("colIdx") in value_col_indices
    )

    return classify_table(labels_first10, labels_all, col_headers,
                          first_label, has_values)


# ── Main pipeline ─────────────────────────────────────────────────

def classify_document(tg_path: str, dry_run: bool = False,
                      verbose: bool = False) -> dict:
    """Classify all tables in a table_graphs.json file."""
    with open(tg_path) as f:
        data = json.load(f)
    tables = data.get("tables", [])

    stats = {"already": 0, "toc": 0, "section_path": 0, "keyword": 0,
             "unclassified": 0}

    # Step 1: Detect TOC
    page_map = _detect_toc(tables)
    if page_map and verbose:
        print(f"  TOC detected: {len(page_map)} sections")
        for p, s in sorted(page_map.items()):
            print(f"    p.{p} → {s}")

    for table in tables:
        sc = table.get("metadata", {}).get("statementComponent")
        if sc:
            stats["already"] += 1
            continue

        # Step 2: TOC page lookup
        result = _classify_by_page(table, page_map) if page_map else None
        if result:
            stats["toc"] += 1
            if verbose:
                print(f"  [toc]     {table['tableId']:15s} p.{table.get('pageNo','?'):>3s} → {result}")
            if not dry_run:
                table["metadata"]["statementComponent"] = result
            continue

        # Step 3: sectionPath
        result = _classify_by_section_path(table)
        if result:
            stats["section_path"] += 1
            if verbose:
                sp = " > ".join(table["metadata"].get("sectionPath", []))[:50]
                print(f"  [section] {table['tableId']:15s} {sp} → {result}")
            if not dry_run:
                table["metadata"]["statementComponent"] = result
            continue

        # Step 4: Keywords
        result = _classify_by_keywords(table)
        if result:
            stats["keyword"] += 1
            if verbose:
                first_label = table["rows"][0]["label"][:30] if table["rows"] else ""
                print(f"  [keyword] {table['tableId']:15s} {first_label:30s} → {result}")
            if not dry_run:
                table["metadata"]["statementComponent"] = result
            continue

        stats["unclassified"] += 1

    total = len(tables)
    classified = stats["already"] + stats["toc"] + stats["section_path"] + stats["keyword"]
    print(f"  Classified: {classified}/{total} "
          f"(already={stats['already']}, toc={stats['toc']}, "
          f"section={stats['section_path']}, keyword={stats['keyword']}, "
          f"unclassified={stats['unclassified']})")

    if not dry_run:
        with open(tg_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return stats


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--") and not a == "-v"]

    if "--all" in sys.argv:
        # Scan corpus directories
        paths = []
        for base in ["/tmp/fobe_corpus2", "/tmp/doc_tag"]:
            for tg in Path(base).rglob("table_graphs.json"):
                paths.append(str(tg))
        # Also scan local fixtures
        for tg in Path("eval/fixtures").rglob("table_graphs.json"):
            paths.append(str(tg))
    else:
        paths = args

    for path in sorted(paths):
        if not os.path.exists(path):
            print(f"Error: {path} not found")
            continue
        name = Path(path).parent.name
        print(f"\n{name}:")
        classify_document(path, dry_run=dry_run, verbose=verbose)


if __name__ == "__main__":
    main()
