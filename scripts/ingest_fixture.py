#!/usr/bin/env python3
"""
ingest_fixture.py — Load a single fixture's data into Supabase Postgres.

Reads from eval/fixtures/<slug>/:
  - document_meta.json  → documents table
  - table_graphs.json   → tables, table_rows, cells, row_tags
  - ground_truth/toc.json → toc_sections
  - rank_tags.json      → (page-level predictions, stored as JSONB on documents)

Usage:
  python scripts/ingest_fixture.py amag_2024 [--dry-run]
  python scripts/ingest_fixture.py --all [--dry-run]

Environment: SUPABASE_URL, SUPABASE_SECRET_KEY
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "eval" / "fixtures"


def load_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def find_pdf_path(slug: str) -> str | None:
    """Find the source PDF for a fixture slug."""
    # Check IFRS sources
    ifrs_pdf = REPO_ROOT / "sources" / "ifrs" / f"{slug}.pdf"
    if ifrs_pdf.exists():
        return str(ifrs_pdf.relative_to(REPO_ROOT))

    # Check IFRS subdirectories
    for subdir in (REPO_ROOT / "sources" / "ifrs").iterdir():
        if subdir.is_dir():
            candidate = subdir / f"{slug}.pdf"
            if candidate.exists():
                return str(candidate.relative_to(REPO_ROOT))

    # Check UGB sources
    ugb_pdf = REPO_ROOT / "sources" / "ugb" / f"{slug}.pdf"
    if ugb_pdf.exists():
        return str(ugb_pdf.relative_to(REPO_ROOT))

    return None


def parse_fixture(slug: str) -> dict[str, Any]:
    """Parse a single fixture directory into database-ready dicts."""
    fixture_dir = FIXTURES_DIR / slug

    if not fixture_dir.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_dir}")

    result: dict[str, Any] = {"slug": slug, "errors": []}

    # ── Document metadata ────────────────────────────────────
    meta = load_json(fixture_dir / "document_meta.json")
    tg = load_json(fixture_dir / "table_graphs.json")

    if tg is None:
        raise FileNotFoundError(f"No table_graphs.json in {fixture_dir}")

    # Extract page count from table_graphs pages dict
    pages_dict = tg.get("pages", {})
    page_count = len(pages_dict) if isinstance(pages_dict, dict) else 0

    # Determine GAAP from meta or from slug heuristic
    gaap = "IFRS"
    if meta:
        gaap_raw = meta.get("gaap", "IFRS")
        gaap = gaap_raw.upper().replace("IFRS", "IFRS").replace("UGB", "UGB").replace("HGB", "HGB")
    elif "_ugb_" in slug:
        gaap = "UGB"
    elif "_hgb_" in slug:
        gaap = "HGB"

    result["document"] = {
        "slug": slug,
        "entity_name": meta.get("entity_name", slug.replace("_", " ").title()) if meta else slug,
        "gaap": gaap if gaap in ("IFRS", "UGB", "HGB") else "IFRS",
        "industry": (meta.get("industry", "general") or "general").lower() if meta else "general",
        "jurisdiction": meta.get("jurisdiction", "AT") if meta else "AT",
        "fiscal_year": meta.get("periods", {}).get("PERIOD.CURRENT", {}).get("year") if meta else None,
        "currency": (meta.get("currency", "EUR") or "EUR").replace("CURRENCY.", "") if meta else "EUR",
        "unit_scale": _parse_unit_scale(meta.get("unit", "")) if meta else 1,
        "language": "de",
        "page_count": page_count,
        "source_path": find_pdf_path(slug),
        "status": "structured",
    }

    # ── Tables, rows, cells ──────────────────────────────────
    result["tables"] = []
    result["rows"] = []   # flat list, each entry has _table_idx for FK linking
    result["cells"] = []  # flat list, each entry has _row_key for FK linking
    result["tags"] = []   # flat list from preTagged

    for table_idx, table in enumerate(tg.get("tables", [])):
        table_id = table.get("tableId", f"table_{table_idx}")
        metadata = table.get("metadata", {})

        table_record = {
            "_idx": table_idx,
            "table_id": table_id,
            "page_no": table.get("pageNo", 0),
            "bbox": table.get("bbox"),
            "statement_component": metadata.get("statementComponent"),
            "classification_method": _extract_classification_method(table),
            "section_path": metadata.get("sectionPath"),
            "detected_currency": metadata.get("detectedCurrency"),
            "detected_unit": metadata.get("detectedUnit"),
            "column_meta": json.dumps(table.get("columns", [])),
        }
        result["tables"].append(table_record)

        for row in table.get("rows", []):
            row_idx = row.get("rowIdx", 0)
            row_key = f"{table_idx}:{row_idx}"

            row_record = {
                "_table_idx": table_idx,
                "_row_key": row_key,
                "row_idx": row_idx,
                "label": row.get("label"),
                "row_type": row.get("rowType"),
                "indent_level": row.get("indentLevel", 0),
                "parent_row_idx": _parse_parent_idx(row.get("parentId")),
                "note_ref": row.get("noteRef"),
                "bbox": row.get("bbox"),
            }
            result["rows"].append(row_record)

            # Cells
            for cell in row.get("cells", []):
                cell_record = {
                    "_row_key": row_key,
                    "col_idx": cell.get("colIdx", 0),
                    "raw_text": cell.get("text"),
                    "parsed_value": cell.get("parsedValue"),
                    "is_negative": cell.get("isNegative", False),
                    "bbox": cell.get("bbox"),
                }
                result["cells"].append(cell_record)

            # Tags from preTagged
            pre_tagged = row.get("preTagged")
            if pre_tagged and isinstance(pre_tagged, dict) and pre_tagged.get("conceptId"):
                tag_record = {
                    "_row_key": row_key,
                    "concept_id": pre_tagged["conceptId"],
                    "tag_source": pre_tagged.get("method", "pretag"),
                    "confidence": pre_tagged.get("matchConfidence") or pre_tagged.get("confidence"),
                }
                result["tags"].append(tag_record)

    # ── TOC ground truth ─────────────────────────────────────
    result["toc_sections"] = []
    gt = load_json(fixture_dir / "ground_truth" / "toc.json")
    if gt and isinstance(gt, dict):
        seen_keys = set()
        for i, section in enumerate(gt.get("sections", [])):
            label = section.get("label", "")
            start_page = section.get("start_page", 0)
            # Deduplicate by (label, start_page) — unique constraint
            dedup_key = (label, start_page)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            result["toc_sections"].append({
                "label": label,
                "statement_type": section.get("statement_type", ""),
                "start_page": start_page,
                "end_page": section.get("end_page"),
                "note_number": section.get("note_number"),
                "sort_order": i,
                "source": "human" if section.get("validated") else "auto",
                "validated": section.get("validated", False),
            })

    # ── Rank tags (page-level MLP predictions) ───────────────
    rank_tags = load_json(fixture_dir / "rank_tags.json")
    result["rank_tags"] = rank_tags  # stored as reference; could go into a pages table later

    return result


def _parse_unit_scale(unit_str: str) -> int:
    if not unit_str:
        return 1
    unit_str = unit_str.upper()
    if "MILLION" in unit_str:
        return 1_000_000
    elif "THOUSAND" in unit_str or "TAUSEND" in unit_str:
        return 1_000
    elif "BILLION" in unit_str or "MILLIARD" in unit_str:
        return 1_000_000_000
    return 1


def _parse_parent_idx(parent_id: str | None) -> int | None:
    """Extract row index from parentId like 'row_5'."""
    if not parent_id:
        return None
    try:
        return int(parent_id.split("_")[-1])
    except (ValueError, IndexError):
        return None


def _extract_classification_method(table: dict) -> str | None:
    """Extract classification method from pipelineSteps if available."""
    for step in table.get("pipelineSteps", []):
        if step.get("stage") == "classify" or "classif" in step.get("action", ""):
            return step.get("method") or step.get("action")
    return None


def upsert_fixture(parsed: dict, supabase_url: str, supabase_key: str) -> dict:
    """Write parsed fixture data into Supabase."""
    from supabase import create_client

    sb = create_client(supabase_url, supabase_key)
    stats = {}

    # 1. Upsert document
    doc_data = parsed["document"]
    doc_resp = sb.table("documents").upsert(
        doc_data, on_conflict="slug"
    ).execute()
    doc_id = doc_resp.data[0]["id"]
    stats["document_id"] = doc_id

    # 2. Delete existing child data for idempotency
    sb.table("toc_sections").delete().eq("document_id", doc_id).execute()
    # Tables cascade to rows → cells → tags via ON DELETE CASCADE
    sb.table("tables").delete().eq("document_id", doc_id).execute()

    # 3. Insert tables and collect UUIDs
    table_uuid_map = {}  # _idx → UUID
    if parsed["tables"]:
        table_inserts = []
        for t in parsed["tables"]:
            insert = {k: v for k, v in t.items() if not k.startswith("_")}
            insert["document_id"] = doc_id
            table_inserts.append(insert)

        # Batch insert tables
        table_resp = sb.table("tables").insert(table_inserts).execute()
        for i, row in enumerate(table_resp.data):
            table_uuid_map[i] = row["id"]

    stats["tables"] = len(table_uuid_map)

    # 4. Insert rows and collect UUIDs
    row_uuid_map = {}  # _row_key → UUID
    if parsed["rows"]:
        # Batch in chunks to avoid payload limits
        row_inserts = []
        row_keys = []
        for r in parsed["rows"]:
            table_uuid = table_uuid_map.get(r["_table_idx"])
            if not table_uuid:
                continue
            insert = {k: v for k, v in r.items() if not k.startswith("_")}
            insert["table_id"] = table_uuid
            row_inserts.append(insert)
            row_keys.append(r["_row_key"])

        for chunk_start in range(0, len(row_inserts), 500):
            chunk = row_inserts[chunk_start:chunk_start + 500]
            keys_chunk = row_keys[chunk_start:chunk_start + 500]
            resp = sb.table("table_rows").insert(chunk).execute()
            for j, row_data in enumerate(resp.data):
                row_uuid_map[keys_chunk[j]] = row_data["id"]

    stats["rows"] = len(row_uuid_map)

    # 5. Insert cells
    cell_count = 0
    if parsed["cells"]:
        cell_inserts = []
        for c in parsed["cells"]:
            row_uuid = row_uuid_map.get(c["_row_key"])
            if not row_uuid:
                continue
            insert = {k: v for k, v in c.items() if not k.startswith("_")}
            insert["row_id"] = row_uuid
            cell_inserts.append(insert)

        for chunk_start in range(0, len(cell_inserts), 500):
            chunk = cell_inserts[chunk_start:chunk_start + 500]
            sb.table("cells").insert(chunk).execute()
            cell_count += len(chunk)

    stats["cells"] = cell_count

    # 6. Insert tags
    tag_count = 0
    if parsed["tags"]:
        tag_inserts = []
        for t in parsed["tags"]:
            row_uuid = row_uuid_map.get(t["_row_key"])
            if not row_uuid:
                continue
            tag_inserts.append({
                "row_id": row_uuid,
                "concept_id": t["concept_id"],
                "tag_source": t["tag_source"],
                "confidence": t["confidence"],
            })

        if tag_inserts:
            for chunk_start in range(0, len(tag_inserts), 500):
                chunk = tag_inserts[chunk_start:chunk_start + 500]
                sb.table("row_tags").insert(chunk).execute()
                tag_count += len(chunk)

    stats["tags"] = tag_count

    # 7. Insert TOC sections
    if parsed["toc_sections"]:
        toc_inserts = [{**s, "document_id": doc_id} for s in parsed["toc_sections"]]
        sb.table("toc_sections").insert(toc_inserts).execute()

    stats["toc_sections"] = len(parsed["toc_sections"])

    return stats


def main():
    parser = argparse.ArgumentParser(description="Ingest fixture(s) into Supabase")
    parser.add_argument("slugs", nargs="*", help="Fixture slug(s) to ingest")
    parser.add_argument("--all", action="store_true", help="Ingest all fixtures")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't write to DB")
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SECRET_KEY"))
    args = parser.parse_args()

    if args.all:
        slugs = sorted([
            d for d in os.listdir(FIXTURES_DIR)
            if (FIXTURES_DIR / d / "table_graphs.json").exists()
        ])
    elif args.slugs:
        slugs = args.slugs
    else:
        parser.error("Provide fixture slug(s) or --all")

    print(f"Processing {len(slugs)} fixture(s)...\n")

    total_stats = {"tables": 0, "rows": 0, "cells": 0, "tags": 0, "toc_sections": 0}
    errors = []

    for slug in slugs:
        try:
            parsed = parse_fixture(slug)

            if args.dry_run:
                print(f"  {slug}: {len(parsed['tables'])} tables, "
                      f"{len(parsed['rows'])} rows, {len(parsed['cells'])} cells, "
                      f"{len(parsed['tags'])} tags, {len(parsed['toc_sections'])} toc_sections")
                for k in total_stats:
                    total_stats[k] += len(parsed.get(k, []))
            else:
                if not args.supabase_url or not args.supabase_key:
                    print("Error: SUPABASE_URL and SUPABASE_SECRET_KEY required")
                    sys.exit(1)
                stats = upsert_fixture(parsed, args.supabase_url, args.supabase_key)
                print(f"  {slug}: {stats}")
                for k in total_stats:
                    total_stats[k] += stats.get(k, 0)

        except Exception as e:
            errors.append((slug, str(e)))
            print(f"  {slug}: ERROR — {e}")

    print(f"\nTotals: {total_stats}")
    if errors:
        print(f"\n{len(errors)} errors:")
        for slug, err in errors:
            print(f"  {slug}: {err}")


if __name__ == "__main__":
    main()
