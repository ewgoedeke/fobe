#!/usr/bin/env python3
"""
extract_docling.py — Extract docling_elements.json for fixtures that have PDFs but no docling.

Usage:
    python3 eval/extract_docling.py                          # all missing UGB20
    python3 eval/extract_docling.py --fixtures evn_ugb_2025  # specific fixture
    python3 eval/extract_docling.py --dry-run                # just list what's missing
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_set import UGB20

FIXTURE_ROOT = Path(__file__).parent / "fixtures"
SOURCES_UGB = Path(__file__).parent.parent / "sources" / "ugb"


def find_pdf(slug: str) -> Path | None:
    """Find the source PDF for a fixture slug."""
    direct = SOURCES_UGB / f"{slug}.pdf"
    if direct.exists():
        return direct
    # Search recursively
    for p in SOURCES_UGB.rglob(f"{slug}.pdf"):
        return p
    return None


def extract_one(pdf_path: Path, fixture_dir: Path, converter) -> dict:
    """Run docling on a PDF and save docling_elements.json."""
    result = converter.convert(str(pdf_path))

    # Export to dict
    doc = result.document
    for method in ("export_to_dict", "to_dict", "dict"):
        fn = getattr(doc, method, None)
        if callable(fn):
            try:
                data = fn()
                if isinstance(data, dict):
                    break
            except Exception:
                continue
    else:
        raise RuntimeError("Could not export docling document to dict")

    out_path = fixture_dir / "docling_elements.json"
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    n_texts = len(data.get("texts", []))
    n_tables = len(data.get("tables", []))
    pages = set()
    for t in data.get("texts", []):
        for prov in t.get("prov", []):
            p = prov.get("page_no")
            if p:
                pages.add(p)

    return {"texts": n_texts, "tables": n_tables, "pages": len(pages), "path": str(out_path)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", nargs="*", help="Specific fixtures to process")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.fixtures:
        slugs = args.fixtures
    else:
        slugs = [s for s in UGB20()
                 if not (FIXTURE_ROOT / s / "docling_elements.json").exists()
                 and (FIXTURE_ROOT / s / "table_graphs.json").exists()]

    # Find PDFs
    jobs = []
    for slug in slugs:
        pdf = find_pdf(slug)
        fixture_dir = FIXTURE_ROOT / slug
        if pdf and fixture_dir.is_dir():
            jobs.append((slug, pdf, fixture_dir))
        else:
            print(f"  SKIP {slug}: {'no PDF' if not pdf else 'no fixture dir'}")

    print(f"Fixtures to process: {len(jobs)}")
    total_mb = sum(p.stat().st_size / 1_000_000 for _, p, _ in jobs)
    print(f"Total PDF size: {total_mb:.1f} MB")

    for slug, pdf, _ in jobs:
        sz = pdf.stat().st_size / 1_000_000
        print(f"  {slug:50s} {sz:.1f} MB")

    if args.dry_run:
        return

    # Load converter once
    print("\nLoading Docling converter...")
    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()
    print("Ready.\n")

    for i, (slug, pdf, fixture_dir) in enumerate(jobs):
        sz = pdf.stat().st_size / 1_000_000
        print(f"[{i+1}/{len(jobs)}] {slug} ({sz:.1f} MB)...", end=" ", flush=True)
        t0 = time.time()
        try:
            info = extract_one(pdf, fixture_dir, converter)
            elapsed = time.time() - t0
            print(f"OK — {info['texts']} texts, {info['tables']} tables, "
                  f"{info['pages']} pages ({elapsed:.1f}s)")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"FAILED ({elapsed:.1f}s): {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
