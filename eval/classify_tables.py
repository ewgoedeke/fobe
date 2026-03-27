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
from reference_graph import build_reference_graph, has_note_column, DocumentRefGraph


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

        # Reject tables with Note/Anhang columns — these are financial statements
        if has_note_column(tbl):
            continue

        # Count VALUE columns — TOC should have at most 2 (page number columns)
        value_cols = [c for c in tbl.get("columns", []) if c.get("role") == "VALUE"]
        if len(value_cols) > 2:
            continue

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
        page_map = _parse_toc_entries(entries)

        # Gate: require ≥2 distinct primary statement types to accept TOC.
        # A single-type TOC is likely a false positive (Issue #36).
        primary_in_toc = {v for v in page_map.values()
                          if v in ("PNL", "SFP", "OCI", "CFS", "SOCIE")}
        if len(primary_in_toc) >= 2:
            return page_map
        # else: continue scanning — this table is not a real TOC

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
        # Cap range propagation: if the table is too far from the nearest
        # TOC entry, don't assign (avoids over-classifying distant tables)
        distance = page - best_page
        # Find the next section's start page to determine safe range
        sorted_pages = sorted(page_map.keys())
        idx = sorted_pages.index(best_page)
        if idx + 1 < len(sorted_pages):
            max_distance = sorted_pages[idx + 1] - best_page
        else:
            max_distance = 20  # last section: cap at 20 pages
        if distance > max_distance:
            return None
        return section

    return None


# ── Note-section classification ───────────────────────────────────

def _classify_by_note_section(table: dict, ref_graph: DocumentRefGraph) -> str | None:
    """Classify a table by looking up its note column values in the reference graph.

    If a table has a Note column and most of the note numbers point to the same
    disclosure context, assign that context.
    """
    if not has_note_column(table):
        return None

    columns = table.get("columns", [])
    note_col_indices = set()
    for col in columns:
        if col.get("role") == "NOTES":
            note_col_indices.add(col["colIdx"])
        elif col.get("headerLabel", "").lower().strip() in (
            "note", "notes", "anhang", "anmerkung", "anmerkungen",
        ):
            note_col_indices.add(col["colIdx"])

    if not note_col_indices:
        return None

    # Collect note numbers from this table's rows
    from collections import Counter
    context_votes: Counter = Counter()

    for row in table.get("rows", []):
        for cell in row.get("cells", []):
            if cell.get("colIdx") not in note_col_indices:
                continue
            note_text = cell.get("text", "").strip()
            if not note_text:
                continue
            # Extract base number
            m = re.match(r"(\d+)", note_text)
            if not m:
                continue
            note_base = int(m.group(1))
            ctx = ref_graph.context_for_note(note_base)
            if ctx:
                context_votes[ctx] += 1

    if not context_votes:
        return None

    # If there's a dominant context (>= 50% of votes), use it
    total_votes = sum(context_votes.values())
    top_ctx, top_count = context_votes.most_common(1)[0]
    if top_count >= total_votes * 0.5 and top_count >= 2:
        return top_ctx

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


# ── LLM classification ────────────────────────────────────────────

_VALID_CONTEXTS = [
    "PNL", "SFP", "OCI", "CFS", "SOCIE",
    "DISC.SEGMENTS", "DISC.REVENUE", "DISC.PPE", "DISC.INTANGIBLES",
    "DISC.GOODWILL", "DISC.INV_PROP", "DISC.LEASES", "DISC.PROVISIONS",
    "DISC.TAX", "DISC.EMPLOYEE_BENEFITS", "DISC.EPS", "DISC.SHARE_BASED",
    "DISC.BCA", "DISC.FIN_INST", "DISC.FAIR_VALUE", "DISC.INVENTORIES",
    "DISC.BORROWINGS", "DISC.RELATED_PARTIES", "DISC.CONTINGENCIES",
    "DISC.HELD_FOR_SALE", "DISC.HEDGE", "DISC.CREDIT_RISK",
    "DISC.BIOLOGICAL_ASSETS", "DISC.GOV_GRANTS", "DISC.DIVIDENDS",
    "DISC.ASSOCIATES", "DISC.IMPAIRMENT", "DISC.FX_RISK",
    "DISC.INTEREST_RATE_RISK", "DISC.NCI", "DISC.RESTATEMENT",
    "DISC.PERSONNEL", "DISC.AUDITOR", "DISC.EQUITY",
]


def _classify_by_llm(tables: list[dict], verbose: bool = False) -> list[str | None]:
    """Use Claude API to classify tables that keyword matching couldn't handle.

    Tries anthropic SDK first, falls back to subprocess claude call.
    """
    # Process in batches of 30 to stay within token limits
    all_results = []
    batch_size = 30
    for batch_start in range(0, len(tables), batch_size):
        batch = tables[batch_start:batch_start + batch_size]
        batch_results = _classify_batch_llm(batch, verbose)
        all_results.extend(batch_results)
    return all_results


def _classify_batch_llm(tables: list[dict], verbose: bool) -> list[str | None]:
    """Classify a batch of tables via Claude."""
    table_descriptions = []
    for i, table in enumerate(tables):
        rows = table.get("rows", [])
        columns = table.get("columns", [])
        col_headers = [c.get("headerLabel", "")[:40] for c in columns[:8]]
        row_labels = [r.get("label", "")[:50] for r in rows[:12] if r.get("label", "").strip()]
        page = table.get("pageNo", "?")
        has_values = any(
            c.get("parsedValue") is not None
            for r in rows
            for c in r.get("cells", [])
        )

        table_descriptions.append(
            f"Table {i} (page {page}, {'has values' if has_values else 'no values'}):\n"
            f"  Columns: {col_headers}\n"
            f"  Row labels: {row_labels}"
        )

    prompt = (
        "Classify each financial table into one of these contexts, or null if it's "
        "not a financial data table (e.g., table of contents, audit text, regulatory references).\n\n"
        "Valid contexts:\n"
        + "\n".join(f"  {ctx}" for ctx in _VALID_CONTEXTS)
        + "\n\nTables to classify:\n"
        + "\n".join(table_descriptions)
        + '\n\nRespond with ONLY a JSON array of strings (one per table), e.g.:\n'
        '["PNL", "DISC.PPE", null, "SFP", "DISC.TAX"]\n\n'
        "No explanations. Just the JSON array."
    )

    # Try anthropic SDK first
    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
    except Exception:
        # Fallback: use claude CLI via subprocess
        try:
            import subprocess
            result = subprocess.run(
                ["claude", "-p", prompt, "--model", "sonnet", "--output-format", "text"],
                capture_output=True, text=True, timeout=60,
            )
            text = result.stdout.strip()
        except Exception as e:
            if verbose:
                print(f"  [llm] Error: {e}")
            return [None] * len(tables)

    try:
        # Extract JSON array from response (may have markdown fences)
        import json as json_mod
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        results = json_mod.loads(text.strip())
        if isinstance(results, list) and len(results) == len(tables):
            validated = []
            for r in results:
                if r in _VALID_CONTEXTS:
                    validated.append(r)
                else:
                    validated.append(None)
            return validated
    except Exception as e:
        if verbose:
            print(f"  [llm] Parse error: {e}")

    return [None] * len(tables)


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
                      verbose: bool = False, use_llm: bool = False,
                      reclassify: bool = False) -> dict:
    """Classify all tables in a table_graphs.json file.

    Args:
        reclassify: If True, strip existing statementComponent from all tables
                    before classifying, forcing fresh classification.
    """
    with open(tg_path) as f:
        data = json.load(f)
    tables = data.get("tables", [])

    if reclassify:
        stripped = 0
        for table in tables:
            meta = table.get("metadata", {})
            if meta.get("statementComponent"):
                del meta["statementComponent"]
                meta.pop("classification_confidence", None)
                meta.pop("classification_method", None)
                stripped += 1
        if verbose:
            print(f"  Reclassify: stripped statementComponent from {stripped}/{len(tables)} tables")

    stats = {"already": 0, "toc": 0, "note_section": 0, "section_path": 0,
             "keyword": 0, "llm": 0, "unclassified": 0}

    # Step 0: Build reference graph
    ref_graph = build_reference_graph(tables)
    if ref_graph.note_entries and verbose:
        print(f"  Reference graph: {len(ref_graph.note_entries)} note numbers, "
              f"{len(ref_graph.note_to_context)} contexts mapped")

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
            table["metadata"].setdefault("classification_confidence", "high")
            table["metadata"].setdefault("classification_method", "already")
            continue

        # Step 2: TOC page lookup
        result = _classify_by_page(table, page_map) if page_map else None
        if result:
            stats["toc"] += 1
            if verbose:
                print(f"  [toc]     {table['tableId']:15s} p.{str(table.get('pageNo','?')):>3s} → {result}")
            if not dry_run:
                table["metadata"]["statementComponent"] = result
                table["metadata"]["classification_confidence"] = "high"
                table["metadata"]["classification_method"] = "toc"
            continue

        # Step 2b: Note-section classification
        result = _classify_by_note_section(table, ref_graph)
        if result:
            stats["note_section"] += 1
            if verbose:
                print(f"  [note]    {table['tableId']:15s} → {result}")
            if not dry_run:
                table["metadata"]["statementComponent"] = result
                table["metadata"]["classification_confidence"] = "medium"
                table["metadata"]["classification_method"] = "note_section"
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
                table["metadata"]["classification_confidence"] = "medium"
                table["metadata"]["classification_method"] = "section_path"
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
                table["metadata"]["classification_confidence"] = "medium"
                table["metadata"]["classification_method"] = "keyword"
            continue

        stats["unclassified"] += 1
        table["metadata"]["classification_confidence"] = "none"
        table["metadata"]["classification_method"] = "unclassified"

    # Step 5: LLM classification for remaining unclassified tables
    if use_llm and stats["unclassified"] > 0:
        unclassified = [t for t in tables
                        if not t.get("metadata", {}).get("statementComponent")]
        if unclassified:
            llm_results = _classify_by_llm(unclassified, verbose)
            for table, result in zip(unclassified, llm_results):
                if result:
                    stats["llm"] += 1
                    stats["unclassified"] -= 1
                    if verbose:
                        first_label = table["rows"][0]["label"][:30] if table["rows"] else ""
                        print(f"  [llm]     {table['tableId']:15s} {first_label:30s} → {result}")
                    if not dry_run:
                        table["metadata"]["statementComponent"] = result
                        table["metadata"]["classification_confidence"] = "low"
                        table["metadata"]["classification_method"] = "llm"

    total = len(tables)
    classified = stats["already"] + stats["toc"] + stats["note_section"] + stats["section_path"] + stats["keyword"] + stats.get("llm", 0)
    parts = f"already={stats['already']}, toc={stats['toc']}, note={stats['note_section']}, section={stats['section_path']}, keyword={stats['keyword']}"
    if stats.get("llm"):
        parts += f", llm={stats['llm']}"
    print(f"  Classified: {classified}/{total} ({parts}, unclassified={stats['unclassified']})")

    if not dry_run:
        with open(tg_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return stats


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    use_llm = "--llm" in sys.argv
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    reclassify = "--reclassify" in sys.argv
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
        classify_document(path, dry_run=dry_run, verbose=verbose,
                         use_llm=use_llm, reclassify=reclassify)


if __name__ == "__main__":
    main()
