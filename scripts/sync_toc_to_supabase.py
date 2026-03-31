#!/usr/bin/env python3
"""
sync_toc_to_supabase.py — Sync local toc_v2.json annotations to Supabase toc_sections.

Reads toc_v2.json from each fixture's ground_truth/ dir, converts transitions
to sections (with start_page/end_page ranges), and upserts into Supabase.

Usage:
    python3 scripts/sync_toc_to_supabase.py [--dry-run]
    python3 scripts/sync_toc_to_supabase.py --slugs amag_2024 evn_2024

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

sys.path.insert(0, str(REPO_ROOT))
from eval.ground_truth import v2_dict_to_v1_dict


def get_total_pages(fixture_dir: Path) -> int | None:
    """Get total page count from table_graphs.json."""
    tg_path = fixture_dir / "table_graphs.json"
    if not tg_path.exists():
        return None
    try:
        with open(tg_path) as f:
            tg = json.load(f)
        pages = tg.get("pages", {})
        if isinstance(pages, dict):
            return len(pages)
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--slugs", nargs="*", help="Specific slugs to sync")
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_SECRET_KEY must be set")
        sys.exit(1)

    from supabase import create_client
    sb = create_client(url, key)

    # Fetch all documents to get UUIDs and page counts
    all_docs = []
    offset = 0
    while True:
        batch = (sb.table("documents")
                 .select("id, slug, page_count")
                 .range(offset, offset + 999)
                 .execute().data)
        if not batch:
            break
        all_docs.extend(batch)
        offset += 1000

    slug_to_doc = {d["slug"]: d for d in all_docs}

    # Find fixtures with toc_v2.json
    if args.slugs:
        slugs = args.slugs
    else:
        slugs = sorted(slug_to_doc.keys())

    synced = 0
    skipped = 0
    errors = 0

    for slug in slugs:
        fixture_dir = FIXTURES_DIR / slug
        v2_path = fixture_dir / "ground_truth" / "toc_v2.json"

        if not v2_path.exists():
            continue

        doc = slug_to_doc.get(slug)
        if not doc:
            print(f"  WARN {slug}: not in Supabase documents table")
            skipped += 1
            continue

        try:
            with open(v2_path) as f:
                v2_data = json.load(f)
        except Exception as e:
            print(f"  ERROR {slug}: failed to read toc_v2.json: {e}")
            errors += 1
            continue

        transitions = v2_data.get("transitions", [])
        if not transitions:
            skipped += 1
            continue

        # Get total pages for end_page calculation
        total_pages = doc.get("page_count") or get_total_pages(fixture_dir)

        # Convert v2 transitions to v1 sections
        v1 = v2_dict_to_v1_dict(v2_data, total_pages=total_pages)
        sections = v1.get("sections", [])

        if not sections:
            skipped += 1
            continue

        doc_uuid = doc["id"]

        if args.dry_run:
            print(f"  {slug}: {len(sections)} sections, pages 1-{total_pages}")
            for s in sections:
                print(f"    {s['statement_type']:20s} pp.{s['start_page']}-{s.get('end_page', '?')}")
            continue

        # Delete existing and insert new
        sb.table("toc_sections").delete().eq("document_id", doc_uuid).execute()

        inserts = []
        for i, s in enumerate(sections):
            inserts.append({
                "document_id": doc_uuid,
                "label": s.get("label", ""),
                "statement_type": s.get("statement_type", ""),
                "start_page": s.get("start_page", 0),
                "end_page": s.get("end_page"),
                "note_number": s.get("note_number"),
                "sort_order": i,
                "source": "human" if s.get("validated") else "auto",
                "validated": s.get("validated", False),
            })

        sb.table("toc_sections").upsert(
            inserts, on_conflict="document_id,label,start_page"
        ).execute()

        synced += 1
        if synced % 20 == 0:
            print(f"  synced {synced}...")

    print(f"\nDone. Synced: {synced}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()
