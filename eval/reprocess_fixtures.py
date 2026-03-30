#!/usr/bin/env python3
"""
Reprocess eval fixtures to extract cell-level bounding boxes from Docling.

This script re-runs the Docling ingestion pipeline on source PDFs to regenerate
table_graphs.json files with row/cell/column bounding boxes.

Background: The original ingest_docling.py discarded cell-level bboxes from
Docling output (initialized as [0,0,0,0]). The fix extracts them from
grid[row][col]["bbox"]. Existing fixtures need reprocessing.

Usage:
    # Reprocess all fixtures that have matching source PDFs
    python3 eval/reprocess_fixtures.py

    # Reprocess specific fixtures
    python3 eval/reprocess_fixtures.py --fixtures amag_2024 evn_2024

    # Dry run (show what would be done)
    python3 eval/reprocess_fixtures.py --dry-run

    # Check current bbox coverage without reprocessing
    python3 eval/reprocess_fixtures.py --audit-only

Requirements:
    - docling (pip install docling)
    - ingest_docling.py and preprocess.py in DOC_TAG_DIR
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "eval" / "fixtures"
SOURCES_DIRS = [REPO_ROOT / "sources" / "ifrs", REPO_ROOT / "sources" / "ugb"]
DOC_TAG_DIR = Path(os.environ.get("DOC_TAG_DIR", "/tmp/doc_tag"))


def find_source_pdf(fixture_name: str) -> Path | None:
    """Find the source PDF for a fixture name."""
    for src_dir in SOURCES_DIRS:
        if not src_dir.is_dir():
            continue
        # Direct name match
        for pdf in src_dir.iterdir():
            if not pdf.suffix == ".pdf":
                continue
            stem = pdf.stem.lower()
            # Try various matching strategies
            fixture_lower = fixture_name.lower()
            # Exact match (minus year suffix)
            base = fixture_lower.rsplit("_", 1)[0] if fixture_lower[-4:].isdigit() else fixture_lower
            if base in stem or stem.startswith(base[:20]):
                return pdf
    return None


def audit_fixture(fixture_dir: Path) -> dict:
    """Check bbox coverage of a fixture."""
    tg_path = fixture_dir / "table_graphs.json"
    if not tg_path.exists():
        return {"exists": False}
    with open(tg_path) as f:
        tg = json.load(f)
    tables = tg.get("tables", [])
    total_rows = sum(len(t.get("rows", [])) for t in tables)
    rows_with_bb = sum(
        1 for t in tables for r in t.get("rows", [])
        if any(v != 0 for v in r.get("bbox", [0, 0, 0, 0]))
    )
    return {
        "exists": True,
        "tables": len(tables),
        "total_rows": total_rows,
        "rows_with_bbox": rows_with_bb,
        "pct": rows_with_bb * 100 // max(total_rows, 1),
    }


def reprocess_fixture(fixture_name: str, pdf_path: Path, dry_run: bool = False) -> bool:
    """Re-ingest a fixture from its source PDF."""
    print(f"\n  PDF: {pdf_path.name}")

    if dry_run:
        print(f"  [DRY RUN] Would reprocess")
        return True

    # Create temp doc directory matching ingest_docling.py expectations
    with tempfile.TemporaryDirectory(prefix=f"reprocess_{fixture_name}_") as tmp:
        doc_dir = Path(tmp) / "doc"
        doc_dir.mkdir()

        ingest_script = DOC_TAG_DIR / "ingest_docling.py"
        if not ingest_script.exists():
            print(f"  ERROR: {ingest_script} not found")
            return False

        # Run ingest_docling.py
        display_name = fixture_name
        result = subprocess.run(
            ["python3", str(ingest_script),
             "--pdf", str(pdf_path),
             "--doc-dir", str(doc_dir),
             "--display-name", display_name],
            capture_output=True, text=True, timeout=600,
        )
        if result.returncode != 0:
            print(f"  ERROR: ingest_docling.py failed")
            print(f"  stderr: {result.stderr[:300]}")
            return False

        # Find the generated table_graphs.json
        stitched_dir = doc_dir / f"{display_name}_tables_stitched"
        tg_path = stitched_dir / "table_graphs.json"
        if not tg_path.exists():
            print(f"  ERROR: table_graphs.json not generated")
            return False

        # Verify
        with open(tg_path) as f:
            tg = json.load(f)
        tables = tg.get("tables", [])
        total_rows = sum(len(t.get("rows", [])) for t in tables)
        rows_bb = sum(
            1 for t in tables for r in t.get("rows", [])
            if any(v != 0 for v in r.get("bbox", [0, 0, 0, 0]))
        )
        pct = rows_bb * 100 // max(total_rows, 1)
        print(f"  Result: {len(tables)} tables, {total_rows} rows, {rows_bb} with bbox ({pct}%)")

        # Copy to fixture directory
        fixture_dir = FIXTURES_DIR / fixture_name
        dest = fixture_dir / "table_graphs.json"
        if dest.exists():
            # Backup
            backup = fixture_dir / "table_graphs.json.bak"
            if not backup.exists():
                import shutil
                shutil.copy2(dest, backup)

        import shutil
        shutil.copy2(tg_path, dest)
        print(f"  Copied to {dest}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Reprocess eval fixtures for cell-level bboxes")
    parser.add_argument("--fixtures", nargs="*", help="Specific fixtures to reprocess")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audit-only", action="store_true", help="Just show current bbox coverage")
    args = parser.parse_args()

    fixtures = args.fixtures or sorted(
        d.name for d in FIXTURES_DIR.iterdir()
        if d.is_dir() and (d / "table_graphs.json").exists()
    )

    if args.audit_only:
        print(f"{'Fixture':<55} {'Tables':>6} {'Rows':>6} {'BBox':>6} {'%':>4}")
        print("-" * 83)
        needs_reprocess = 0
        for name in fixtures:
            info = audit_fixture(FIXTURES_DIR / name)
            if not info["exists"]:
                continue
            mark = " *" if info["pct"] < 100 else ""
            print(f"{name:<55} {info['tables']:>6} {info['total_rows']:>6} {info['rows_with_bbox']:>6} {info['pct']:>3}%{mark}")
            if info["pct"] < 100:
                needs_reprocess += 1
        print(f"\n* = needs reprocessing ({needs_reprocess} of {len(fixtures)})")
        return 0

    ok = 0
    fail = 0
    skipped = 0
    for name in fixtures:
        print(f"\n{'='*60}")
        print(f"Fixture: {name}")

        # Check if already at 100%
        info = audit_fixture(FIXTURES_DIR / name)
        if info.get("pct", 0) == 100:
            print(f"  Already 100% bbox coverage, skipping")
            skipped += 1
            continue

        pdf = find_source_pdf(name)
        if not pdf:
            print(f"  No source PDF found, skipping")
            skipped += 1
            continue

        if reprocess_fixture(name, pdf, dry_run=args.dry_run):
            ok += 1
        else:
            fail += 1

    print(f"\n{'='*60}")
    print(f"Results: {ok} reprocessed, {fail} failed, {skipped} skipped")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
