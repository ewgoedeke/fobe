#!/usr/bin/env python3
"""
Seed predefined Ground Truth sets into Supabase.

Creates the tier sets (Test Set, UGB20..UGB_ALL, IFRS) and populates
them with the correct documents via gt_set_documents.

Prerequisites:
  - Migration 005_gt_sets.sql must be applied first
  - All fixture documents must already be ingested into Supabase

Usage:
    python3 scripts/seed_gt_sets.py [--dry-run]
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "explorer" / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from explorer.supabase_client import get_supabase
from eval.test_set import (
    IFRS_TEST_SET, UGB_TEST_SET, TEST_SET,
    ifrs_tier, IFRS_ALL,
    ugb_tier, UGB_ALL,
)

# Predefined sets to create
PREDEFINED_SETS = [
    {
        "name": "Test Set",
        "description": "Core IFRS + UGB evaluation set (22 documents)",
        "docs_fn": lambda: TEST_SET,
    },
    {
        "name": "IFRS",
        "description": "IFRS core evaluation documents (10)",
        "docs_fn": lambda: IFRS_TEST_SET,
    },
    {
        "name": "IFRS20",
        "description": "Core 20 IFRS documents (includes IFRS core)",
        "docs_fn": lambda: ifrs_tier(20),
    },
    {
        "name": "IFRS50",
        "description": "Cumulative 50 IFRS documents (includes IFRS20)",
        "docs_fn": lambda: ifrs_tier(50),
    },
    {
        "name": "IFRS100",
        "description": "Cumulative 100 IFRS documents (includes IFRS50)",
        "docs_fn": lambda: ifrs_tier(100),
    },
    {
        "name": "IFRS200",
        "description": "Cumulative 200 IFRS documents (includes IFRS100)",
        "docs_fn": lambda: ifrs_tier(200),
    },
    {
        "name": "IFRS All",
        "description": "All available IFRS fixtures",
        "docs_fn": IFRS_ALL,
    },
    {
        "name": "UGB20",
        "description": "Core 20 UGB documents",
        "docs_fn": lambda: ugb_tier(20),
    },
    {
        "name": "UGB50",
        "description": "Cumulative 50 UGB documents (includes UGB20)",
        "docs_fn": lambda: ugb_tier(50),
    },
    {
        "name": "UGB100",
        "description": "Cumulative 100 UGB documents (includes UGB50)",
        "docs_fn": lambda: ugb_tier(100),
    },
    {
        "name": "UGB200",
        "description": "Cumulative 200 UGB documents (includes UGB100)",
        "docs_fn": lambda: ugb_tier(200),
    },
    {
        "name": "UGB500",
        "description": "Cumulative 500 UGB documents (includes UGB200)",
        "docs_fn": lambda: ugb_tier(500),
    },
    {
        "name": "UGB All",
        "description": "All available UGB fixtures",
        "docs_fn": UGB_ALL,
    },
]


def main():
    parser = argparse.ArgumentParser(description="Seed GT sets into Supabase")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without writing")
    args = parser.parse_args()

    sb = get_supabase()

    # Build slug → UUID map
    print("Loading documents from Supabase...")
    all_docs = []
    offset = 0
    while True:
        batch = sb.table("documents").select("id, slug").range(offset, offset + 999).execute().data
        if not batch:
            break
        all_docs.extend(batch)
        offset += 1000
    slug_to_uuid = {d["slug"]: d["id"] for d in all_docs}
    print(f"  {len(slug_to_uuid)} documents found")

    # Check existing GT sets
    existing_sets = sb.table("gt_sets").select("id, name").execute().data or []
    existing_names = {s["name"]: s["id"] for s in existing_sets}

    for set_def in PREDEFINED_SETS:
        name = set_def["name"]
        doc_slugs = set_def["docs_fn"]()
        doc_uuids = [slug_to_uuid[s] for s in doc_slugs if s in slug_to_uuid]
        missing = [s for s in doc_slugs if s not in slug_to_uuid]

        print(f"\n{name}: {len(doc_slugs)} docs ({len(doc_uuids)} in Supabase, {len(missing)} missing)")
        if missing:
            print(f"  Missing: {missing[:5]}{'...' if len(missing) > 5 else ''}")

        if args.dry_run:
            if name in existing_names:
                print(f"  [DRY RUN] Would update existing set {existing_names[name]}")
            else:
                print(f"  [DRY RUN] Would create set and add {len(doc_uuids)} documents")
            continue

        # Create or get the set
        if name in existing_names:
            set_id = existing_names[name]
            print(f"  Set already exists: {set_id}")
            # Update description
            sb.table("gt_sets").update({"description": set_def["description"]}).eq("id", set_id).execute()
            # Clear existing associations so membership is exact
            sb.table("gt_set_documents").delete().eq("set_id", set_id).execute()
        else:
            resp = sb.table("gt_sets").insert({
                "name": name,
                "description": set_def["description"],
            }).execute()
            set_id = resp.data[0]["id"]
            print(f"  Created set: {set_id}")

        # Upsert documents in batches of 200
        total_added = 0
        for i in range(0, len(doc_uuids), 200):
            batch = doc_uuids[i:i + 200]
            entries = [{"set_id": set_id, "document_id": uid} for uid in batch]
            resp = sb.table("gt_set_documents").upsert(
                entries, on_conflict="set_id,document_id"
            ).execute()
            total_added += len(resp.data) if resp.data else 0
        print(f"  Upserted {total_added} document associations")

    print("\nDone!")


if __name__ == "__main__":
    main()
