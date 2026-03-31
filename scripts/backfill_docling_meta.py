#!/usr/bin/env python3
"""
backfill_docling_meta.py — Populate docling metadata columns on existing documents.

Reads docling_elements.json from local fixtures (or R2 cache) and updates
docling_text_count, docling_table_count, docling_page_count, docling_size_kb,
and tg_page_count in the Supabase documents table.

Usage:
    python3 scripts/backfill_docling_meta.py [--dry-run]
    python3 scripts/backfill_docling_meta.py --slugs amag_2024 evn_2024

Environment: SUPABASE_URL, SUPABASE_SECRET_KEY
"""

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "eval" / "fixtures"

# Auto-load .env if present
_env_path = REPO_ROOT / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def compute_docling_stats(dl: dict) -> dict:
    """Extract stats from a parsed docling_elements.json dict."""
    stats = {
        "docling_text_count": None,
        "docling_table_count": None,
        "docling_page_count": None,
    }
    if "texts" in dl:
        stats["docling_text_count"] = len(dl.get("texts", []))
        stats["docling_table_count"] = len(dl.get("tables", []))
        pages = set()
        for item in dl.get("texts", []) + dl.get("tables", []):
            for prov in item.get("prov", []):
                p = prov.get("page_no")
                if p:
                    pages.add(p)
        stats["docling_page_count"] = len(pages)
    elif "pages" in dl and isinstance(dl["pages"], dict):
        stats["docling_page_count"] = len(dl["pages"])
    return stats


def compute_tg_page_count(fixture_dir: Path) -> int | None:
    """Count distinct pages with tables from table_graphs.json."""
    tg_path = fixture_dir / "table_graphs.json"
    if not tg_path.exists():
        return None
    try:
        with open(tg_path) as f:
            tg = json.load(f)
        pages = set()
        for t in tg.get("tables", []):
            p = t.get("pageNo")
            if p:
                pages.add(p)
        return len(pages)
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--slugs", nargs="*", help="Specific slugs to backfill")
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set")
        sys.exit(1)

    from supabase import create_client
    sb = create_client(url, key)

    # Fetch all documents
    all_docs = []
    offset = 0
    while True:
        batch = (sb.table("documents")
                 .select("id, slug, docling_url, docling_text_count")
                 .range(offset, offset + 999)
                 .execute().data)
        if not batch:
            break
        all_docs.extend(batch)
        offset += 1000

    if args.slugs:
        slug_set = set(args.slugs)
        all_docs = [d for d in all_docs if d["slug"] in slug_set]

    # Filter to those needing backfill
    needs_backfill = [d for d in all_docs if d.get("docling_text_count") is None]
    print(f"Total documents: {len(all_docs)}, needing backfill: {len(needs_backfill)}")

    updated = 0
    skipped = 0
    for i, doc in enumerate(needs_backfill):
        slug = doc["slug"]
        fixture_dir = FIXTURES_DIR / slug
        dl_path = fixture_dir / "docling_elements.json"

        update = {}

        # Docling stats
        if dl_path.exists():
            try:
                size_kb = round(dl_path.stat().st_size / 1024)
                with open(dl_path) as f:
                    dl = json.load(f)
                stats = compute_docling_stats(dl)
                update.update(stats)
                update["docling_size_kb"] = size_kb
            except Exception as e:
                print(f"  WARN {slug}: docling parse error: {e}")

        # TG page count
        tg_pages = compute_tg_page_count(fixture_dir)
        if tg_pages is not None:
            update["tg_page_count"] = tg_pages

        if not update:
            skipped += 1
            continue

        if args.dry_run:
            print(f"  [{i+1}/{len(needs_backfill)}] {slug}: {update}")
        else:
            sb.table("documents").update(update).eq("id", doc["id"]).execute()
            updated += 1
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(needs_backfill)}] updated {updated}...")

    print(f"\nDone. Updated: {updated}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
