#!/usr/bin/env python3
"""
extract_table_images.py — Render PDF pages containing tables to PNG images.

For each fixture with a matching source PDF, extracts the relevant pages
as PNG images for use in the ontology explorer.

Usage:
    python3 eval/extract_table_images.py          # extract all
    python3 eval/extract_table_images.py --dpi 150 # lower quality
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Fixture → PDF mapping with page offsets (same as explorer/server.py)
PDF_MAP = {
    "ca_immo_2024": {"pdf": "sources/ifrs/ca_immo_2024_en.pdf", "offset": 0},
    "eurotelesites_2024": {"pdf": "sources/ifrs/eurotelesites_2024.pdf", "offset": 98},
    "kpmg_ifs_2025": {"pdf": "sources/ifrs/kpmg-ifrs-ifs-2025.pdf", "offset": 0},
}


def extract_images(dpi: int = 200):
    fixtures_dir = REPO_ROOT / "eval" / "fixtures"

    for fixture_dir in sorted(fixtures_dir.iterdir()):
        if not fixture_dir.is_dir():
            continue

        doc_id = fixture_dir.name
        mapping = PDF_MAP.get(doc_id)
        if not mapping:
            print(f"  {doc_id}: no PDF mapping, skipping")
            continue

        pdf_path = REPO_ROOT / mapping["pdf"]
        if not pdf_path.exists():
            print(f"  {doc_id}: PDF not found at {pdf_path}, skipping")
            continue

        tg_path = fixture_dir / "table_graphs.json"
        if not tg_path.exists():
            print(f"  {doc_id}: no table_graphs.json, skipping")
            continue

        offset = mapping.get("offset", 0)

        with open(tg_path) as f:
            tg = json.load(f)

        tables = tg.get("tables", [])
        if not tables:
            continue

        # Collect unique pages to render
        page_tables = {}  # pdf_page → [table_info]
        for t in tables:
            source_page = t.get("pageNo")
            if not source_page:
                continue
            pdf_page = max(1, source_page - offset)
            table_info = {
                "table_id": t.get("tableId", ""),
                "context": t.get("metadata", {}).get("statementComponent", ""),
                "source_page": source_page,
                "pdf_page": pdf_page,
            }
            page_tables.setdefault(pdf_page, []).append(table_info)

        # Create images directory
        images_dir = fixture_dir / "images"
        images_dir.mkdir(exist_ok=True)

        manifest = {"doc_id": doc_id, "pdf": mapping["pdf"], "tables": []}

        print(f"  {doc_id}: extracting {len(page_tables)} pages from {pdf_path.name}")

        for pdf_page, table_infos in sorted(page_tables.items()):
            out_prefix = images_dir / f"page_{pdf_page}"
            out_file = images_dir / f"page_{pdf_page}.png"

            # Use pdftoppm to render single page
            cmd = [
                "pdftoppm",
                "-png",
                "-r", str(dpi),
                "-f", str(pdf_page),
                "-l", str(pdf_page),
                "-singlefile",
                str(pdf_path),
                str(out_prefix),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"    ERROR page {pdf_page}: {result.stderr.strip()}")
                continue

            if not out_file.exists():
                print(f"    ERROR: {out_file} not created")
                continue

            size_kb = out_file.stat().st_size / 1024
            print(f"    page {pdf_page} → {out_file.name} ({size_kb:.0f} KB)")

            for ti in table_infos:
                manifest["tables"].append({
                    **ti,
                    "image": f"images/page_{pdf_page}.png",
                })

        # Write manifest
        manifest_path = fixture_dir / "images.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"    manifest: {manifest_path} ({len(manifest['tables'])} tables)")


def main():
    parser = argparse.ArgumentParser(description="Extract table page images from PDFs")
    parser.add_argument("--dpi", type=int, default=200, help="Resolution (default: 200)")
    args = parser.parse_args()

    print("Extracting table images...")
    extract_images(dpi=args.dpi)
    print("Done.")


if __name__ == "__main__":
    main()
