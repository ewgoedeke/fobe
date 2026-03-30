#!/usr/bin/env python3
"""
migrate_existing.py — Batch migrate all existing fixtures and PDFs to Supabase + UploadThing.

Phase 1: Seed ontology (concepts, gaap_labels, aliases)
Phase 2: Ingest all fixtures into Postgres (tables, rows, cells, tags, TOC)
Phase 3: Upload PDFs to Cloudflare R2 (when --upload-pdfs is set)
Phase 4: Upload Docling JSONs to Cloudflare R2 (when --upload-docling is set)

Usage:
  # Dry run — parse everything, print stats
  python scripts/migrate_existing.py --dry-run

  # Seed ontology + ingest fixtures only (no file uploads)
  python scripts/migrate_existing.py

  # Full migration including file uploads
  python scripts/migrate_existing.py --upload-pdfs --upload-docling

Environment:
  SUPABASE_URL, SUPABASE_SECRET_KEY
  R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET (for file uploads)
  R2_PUBLIC_URL (e.g. https://pub-xxx.r2.dev or custom domain)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "eval" / "fixtures"
SOURCES_DIR = REPO_ROOT / "sources"

# State file for resumable uploads
STATE_FILE = REPO_ROOT / "scripts" / ".migrate_state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"uploaded_pdfs": {}, "uploaded_docling": {}, "ingested_fixtures": []}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def find_all_pdfs() -> list[tuple[str, Path]]:
    """Find all source PDFs and their fixture slugs."""
    pdfs = []

    # IFRS PDFs (top-level)
    ifrs_dir = SOURCES_DIR / "ifrs"
    if ifrs_dir.exists():
        for pdf in sorted(ifrs_dir.glob("*.pdf")):
            slug = pdf.stem
            pdfs.append((slug, pdf))
        # Subdirectories (country-specific)
        for subdir in sorted(ifrs_dir.iterdir()):
            if subdir.is_dir():
                for pdf in sorted(subdir.glob("*.pdf")):
                    slug = pdf.stem
                    pdfs.append((slug, pdf))

    # UGB PDFs
    ugb_dir = SOURCES_DIR / "ugb"
    if ugb_dir.exists():
        for pdf in sorted(ugb_dir.glob("*.pdf")):
            slug = pdf.stem
            pdfs.append((slug, pdf))

    return pdfs


def find_all_fixtures() -> list[str]:
    """Find all fixture slugs that have table_graphs.json."""
    return sorted([
        d for d in os.listdir(FIXTURES_DIR)
        if (FIXTURES_DIR / d / "table_graphs.json").exists()
    ])


def phase1_seed_ontology(dry_run: bool, supabase_url: str = None, supabase_key: str = None):
    """Seed ontology from YAML files."""
    print("=" * 60)
    print("Phase 1: Seed Ontology")
    print("=" * 60)

    from seed_ontology import collect_all, seed_supabase

    concepts, gaap_labels, aliases = collect_all(REPO_ROOT)
    print(f"  Concepts:    {len(concepts)}")
    print(f"  GAAP labels: {len(gaap_labels)}")
    print(f"  Aliases:     {len(aliases)}")

    if dry_run:
        print("  [dry-run] Skipping write.\n")
        return

    stats = seed_supabase(concepts, gaap_labels, aliases, supabase_url, supabase_key)
    print(f"  Written: {stats}\n")


def phase2_ingest_fixtures(dry_run: bool, supabase_url: str = None, supabase_key: str = None):
    """Ingest all fixtures into Postgres."""
    print("=" * 60)
    print("Phase 2: Ingest Fixtures")
    print("=" * 60)

    from ingest_fixture import parse_fixture, upsert_fixture

    state = load_state()
    fixtures = find_all_fixtures()
    print(f"  Found {len(fixtures)} fixtures")

    already = set(state.get("ingested_fixtures", []))
    remaining = [f for f in fixtures if f not in already]
    print(f"  Already ingested: {len(already)}, remaining: {len(remaining)}")

    totals = {"tables": 0, "rows": 0, "cells": 0, "tags": 0, "toc_sections": 0}
    errors = []

    for i, slug in enumerate(remaining):
        try:
            parsed = parse_fixture(slug)

            if dry_run:
                t = len(parsed["tables"])
                r = len(parsed["rows"])
                c = len(parsed["cells"])
                totals["tables"] += t
                totals["rows"] += r
                totals["cells"] += c
                totals["tags"] += len(parsed["tags"])
                totals["toc_sections"] += len(parsed["toc_sections"])
                if (i + 1) % 20 == 0:
                    print(f"  [{i+1}/{len(remaining)}] {slug}: {t} tables, {r} rows, {c} cells")
            else:
                stats = upsert_fixture(parsed, supabase_url, supabase_key)
                state["ingested_fixtures"].append(slug)
                save_state(state)
                for k in totals:
                    totals[k] += stats.get(k, 0)
                if (i + 1) % 10 == 0:
                    print(f"  [{i+1}/{len(remaining)}] {slug}: {stats}")

        except Exception as e:
            errors.append((slug, str(e)))
            print(f"  ERROR {slug}: {e}")

    print(f"\n  Totals: {totals}")
    if errors:
        print(f"  {len(errors)} errors:")
        for slug, err in errors[:10]:
            print(f"    {slug}: {err}")
    print()


def _get_r2_client():
    """Create a boto3 S3 client configured for Cloudflare R2."""
    import boto3

    account_id = os.environ.get("R2_ACCOUNT_ID")
    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")

    if not all([account_id, access_key, secret_key]):
        raise RuntimeError("R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY required")

    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
    )


def _upload_to_r2(file_path: Path, r2_key: str, s3_client, bucket: str) -> str:
    """Upload a single file to Cloudflare R2. Returns the public URL."""
    content_type = "application/pdf" if file_path.suffix == ".pdf" else "application/json"
    s3_client.upload_file(
        str(file_path), bucket, r2_key,
        ExtraArgs={"ContentType": content_type},
    )
    public_url = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")
    return f"{public_url}/{r2_key}"


def phase3_upload_pdfs(dry_run: bool):
    """Upload PDFs to Cloudflare R2."""
    print("=" * 60)
    print("Phase 3: Upload PDFs to Cloudflare R2")
    print("=" * 60)

    state = load_state()
    pdfs = find_all_pdfs()
    print(f"  Found {len(pdfs)} PDFs")

    already = set(state.get("uploaded_pdfs", {}).keys())
    remaining = [(slug, path) for slug, path in pdfs if slug not in already]
    print(f"  Already uploaded: {len(already)}, remaining: {len(remaining)}")

    total_size = sum(p.stat().st_size for _, p in remaining)
    print(f"  Total upload size: {total_size / 1024 / 1024:.0f} MB")

    if dry_run:
        print("  [dry-run] Skipping upload.\n")
        return

    try:
        s3 = _get_r2_client()
    except RuntimeError as e:
        print(f"  ERROR: {e}\n")
        return

    bucket = os.environ.get("R2_BUCKET", "fobe")

    for i, (slug, path) in enumerate(remaining):
        try:
            r2_key = f"pdfs/{slug}.pdf"
            url = _upload_to_r2(path, r2_key, s3, bucket)
            state["uploaded_pdfs"][slug] = url
            save_state(state)
            if (i + 1) % 50 == 0 or i == 0:
                print(f"  [{i+1}/{len(remaining)}] {slug} ({path.stat().st_size/1024/1024:.1f} MB)")
        except Exception as e:
            print(f"  ERROR {slug}: {e}")

    print(f"  Uploaded {len(remaining) - len([s for s,_ in remaining if s not in state['uploaded_pdfs']])} PDFs.\n")


def phase4_upload_docling(dry_run: bool):
    """Upload Docling JSON files to Cloudflare R2."""
    print("=" * 60)
    print("Phase 4: Upload Docling JSONs to Cloudflare R2")
    print("=" * 60)

    state = load_state()
    docling_files = []
    for slug in find_all_fixtures():
        path = FIXTURES_DIR / slug / "docling_elements.json"
        if path.exists():
            docling_files.append((slug, path))

    print(f"  Found {len(docling_files)} Docling JSONs")

    already = set(state.get("uploaded_docling", {}).keys())
    remaining = [(slug, path) for slug, path in docling_files if slug not in already]
    print(f"  Already uploaded: {len(already)}, remaining: {len(remaining)}")

    total_size = sum(p.stat().st_size for _, p in remaining)
    print(f"  Total upload size: {total_size / 1024 / 1024:.0f} MB")

    if dry_run:
        print("  [dry-run] Skipping upload.\n")
        return

    try:
        s3 = _get_r2_client()
    except RuntimeError as e:
        print(f"  ERROR: {e}\n")
        return

    bucket = os.environ.get("R2_BUCKET", "fobe")

    for i, (slug, path) in enumerate(remaining):
        try:
            r2_key = f"docling/{slug}.json"
            url = _upload_to_r2(path, r2_key, s3, bucket)
            state["uploaded_docling"][slug] = url
            save_state(state)
            if (i + 1) % 20 == 0 or i == 0:
                print(f"  [{i+1}/{len(remaining)}] {slug} ({path.stat().st_size/1024/1024:.1f} MB)")
        except Exception as e:
            print(f"  ERROR {slug}: {e}")

    print()


def phase5_link_urls(dry_run: bool, supabase_url: str = None, supabase_key: str = None):
    """Update documents table with UploadThing URLs from state file."""
    print("=" * 60)
    print("Phase 5: Link UploadThing URLs to Documents")
    print("=" * 60)

    state = load_state()
    pdf_urls = state.get("uploaded_pdfs", {})
    docling_urls = state.get("uploaded_docling", {})

    print(f"  PDF URLs to link: {len(pdf_urls)}")
    print(f"  Docling URLs to link: {len(docling_urls)}")

    if dry_run or not pdf_urls and not docling_urls:
        print("  [dry-run or nothing to link]\n")
        return

    from supabase import create_client
    sb = create_client(supabase_url, supabase_key)

    linked = 0
    for slug, url in {**pdf_urls}.items():
        sb.table("documents").update({"pdf_url": url}).eq("slug", slug).execute()
        linked += 1

    for slug, url in {**docling_urls}.items():
        sb.table("documents").update({
            "docling_url": url,
            "docling_status": "uploaded",
        }).eq("slug", slug).execute()
        linked += 1

    print(f"  Linked {linked} URLs.\n")


def main():
    parser = argparse.ArgumentParser(description="Batch migrate FOBE data to Supabase + UploadThing")
    parser.add_argument("--dry-run", action="store_true", help="Parse and count only")
    parser.add_argument("--upload-pdfs", action="store_true", help="Upload PDFs to UploadThing")
    parser.add_argument("--upload-docling", action="store_true", help="Upload Docling JSONs to UploadThing")
    parser.add_argument("--skip-ontology", action="store_true", help="Skip Phase 1 ontology seed")
    parser.add_argument("--skip-fixtures", action="store_true", help="Skip Phase 2 fixture ingestion")
    parser.add_argument("--link-urls-only", action="store_true", help="Only run Phase 5 URL linking")
    parser.add_argument("--supabase-url", default=os.environ.get("SUPABASE_URL"))
    parser.add_argument("--supabase-key", default=os.environ.get("SUPABASE_SECRET_KEY"))
    args = parser.parse_args()

    if not args.dry_run and (not args.supabase_url or not args.supabase_key):
        print("Error: SUPABASE_URL and SUPABASE_SECRET_KEY required (or --dry-run)")
        sys.exit(1)

    # Add scripts/ to path so we can import seed_ontology and ingest_fixture
    sys.path.insert(0, str(Path(__file__).parent))

    if args.link_urls_only:
        phase5_link_urls(args.dry_run, args.supabase_url, args.supabase_key)
        return

    if not args.skip_ontology:
        phase1_seed_ontology(args.dry_run, args.supabase_url, args.supabase_key)

    if not args.skip_fixtures:
        phase2_ingest_fixtures(args.dry_run, args.supabase_url, args.supabase_key)

    if args.upload_pdfs:
        phase3_upload_pdfs(args.dry_run)

    if args.upload_docling:
        phase4_upload_docling(args.dry_run)

    # Link URLs if we uploaded anything
    if (args.upload_pdfs or args.upload_docling) and not args.dry_run:
        phase5_link_urls(args.dry_run, args.supabase_url, args.supabase_key)

    print("Done.")


if __name__ == "__main__":
    main()
