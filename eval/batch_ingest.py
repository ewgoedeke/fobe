#!/usr/bin/env python3
"""
batch_ingest.py — Batch process all unprocessed PDFs through Docling.

Loads the Docling DocumentConverter once and reuses it across all PDFs.
Pipelines CPU post-processing (preprocess.py) with the next GPU conversion.
Saves complete Docling JSON to fixtures for the explorer's element overlay.

Usage:
    # Dry run
    python3 eval/batch_ingest.py --dry-run

    # Process first 10
    python3 eval/batch_ingest.py --limit 10

    # Full run (use tmux/nohup)
    nohup python3 eval/batch_ingest.py > /tmp/batch_ingest.log 2>&1 &

    # Resume after interruption (default behavior)
    python3 eval/batch_ingest.py
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "eval" / "fixtures"
SOURCE_DIRS = [REPO_ROOT / "sources" / "ugb", REPO_ROOT / "sources" / "ifrs"]
DOC_TAG_DIR = Path(os.environ.get("DOC_TAG_DIR", "/tmp/doc_tag"))
DEFAULT_WORK_DIR = Path("/tmp/fobe_corpus")
STATE_FILE = REPO_ROOT / "eval" / "batch_ingest_state.json"
PREPROCESS_PY = DOC_TAG_DIR / "preprocess.py"

# Import ingestion helpers from doc_tag (avoid code duplication)
sys.path.insert(0, str(DOC_TAG_DIR))
from ingest_docling import build_tables_raw, doc_to_dict, safe_name, ensure_empty_jsonl


# ── Resource monitoring ───────────────────────────────────

def available_memory_gb() -> float:
    """Get available memory in GB from /proc/meminfo."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except (OSError, ValueError):
        pass
    return 999.0  # assume plenty if we can't check


def available_disk_gb(path: Path) -> float:
    """Get available disk space in GB."""
    try:
        st = os.statvfs(str(path))
        return (st.f_bavail * st.f_frsize) / (1024 ** 3)
    except OSError:
        return 999.0


def gpu_memory_used_mb() -> int | None:
    """Get GPU memory used in MB via nvidia-smi."""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            return int(r.stdout.strip().split("\n")[0])
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return None


def try_free_gpu_memory():
    """Attempt to free GPU memory."""
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


# ── State management ─────────────────────────────────────

@dataclass
class DocStatus:
    name: str
    pdf_path: str
    pdf_size_mb: float
    status: str = "pending"  # pending | converting | postprocessing | done | failed
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    elapsed_s: float | None = None
    tables_count: int | None = None
    rows_count: int | None = None


@dataclass
class BatchState:
    docs: dict[str, DocStatus] = field(default_factory=dict)
    started_at: float | None = None
    finished_at: float | None = None

    def save(self, path: Path):
        """Save state atomically."""
        tmp = path.with_suffix(".tmp")
        data = {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "docs": {k: asdict(v) for k, v in self.docs.items()},
        }
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.rename(path)

    @classmethod
    def load(cls, path: Path) -> BatchState:
        """Load existing state or return empty."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            state = cls(
                started_at=data.get("started_at"),
                finished_at=data.get("finished_at"),
            )
            for k, v in data.get("docs", {}).items():
                state.docs[k] = DocStatus(**v)
            return state
        except (json.JSONDecodeError, TypeError, OSError):
            return cls()

    @property
    def done_count(self) -> int:
        return sum(1 for d in self.docs.values() if d.status == "done")

    @property
    def failed_count(self) -> int:
        return sum(1 for d in self.docs.values() if d.status == "failed")

    @property
    def pending_count(self) -> int:
        return sum(1 for d in self.docs.values() if d.status in ("pending", "converting", "postprocessing"))


# ── Discovery ────────────────────────────────────────────

def discover_pdfs(source_dirs: list[Path]) -> list[Path]:
    """Find all PDFs in source directories (recursively)."""
    pdfs = []
    for d in source_dirs:
        if d.is_dir():
            pdfs.extend(sorted(d.rglob("*.pdf")))
    return pdfs


def discover_missing_docling(source_dirs: list[Path], fixtures_dir: Path) -> list[Path]:
    """Find PDFs that have fixtures but no docling_elements.json."""
    needs_docling = set()
    if fixtures_dir.is_dir():
        for d in fixtures_dir.iterdir():
            if d.is_dir() and (d / "table_graphs.json").exists() and not (d / "docling_elements.json").exists():
                needs_docling.add(d.name)

    pdfs = discover_pdfs(source_dirs)
    return [p for p in pdfs if p.stem in needs_docling]


def discover_unprocessed(source_dirs: list[Path], fixtures_dir: Path) -> list[Path]:
    """Find PDFs that don't have a fixture with table_graphs.json."""
    existing = set()
    if fixtures_dir.is_dir():
        for d in fixtures_dir.iterdir():
            if d.is_dir() and (d / "table_graphs.json").exists():
                existing.add(d.name)

    pdfs = discover_pdfs(source_dirs)
    return [p for p in pdfs if p.stem not in existing]


# ── Core processing ──────────────────────────────────────

def _get_page_count(pdf_path: Path) -> int:
    """Get page count from a PDF without full conversion."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        count = len(doc)
        doc.close()
        return count
    except ImportError:
        pass
    # Fallback: use pdfinfo
    try:
        r = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":")[1].strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 0


CHUNK_SIZE_MB = 10  # PDFs above this size get chunked
CHUNK_PAGES = 40    # Pages per chunk


def _merge_docling_data(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge multiple chunked Docling outputs into one."""
    merged = {"tables": [], "texts": []}
    for chunk in chunks:
        merged["tables"].extend(chunk.get("tables", []))
        merged["texts"].extend(chunk.get("texts", []))
    # Carry over top-level keys from the first chunk
    for key in chunks[0]:
        if key not in merged:
            merged[key] = chunks[0][key]
    return merged


def process_one(
    converter: Any,
    pdf_path: Path,
    work_dir: Path,
    timeout_s: int,
) -> tuple[dict[str, Any], Path]:
    """Run Docling conversion and build tables_raw.

    For PDFs > CHUNK_SIZE_MB, splits into page-range chunks to avoid OOM.
    Returns (docling_data, stitched_dir).
    """
    name = safe_name(pdf_path.stem)
    doc_dir = work_dir / name
    stitched_dir = doc_dir / f"{name}_tables_stitched"
    stitched_dir.mkdir(parents=True, exist_ok=True)

    file_size_mb = pdf_path.stat().st_size / (1024 * 1024)

    if file_size_mb > CHUNK_SIZE_MB:
        page_count = _get_page_count(pdf_path)
        if page_count > CHUNK_PAGES:
            # Chunked conversion
            chunks = []
            for start in range(1, page_count + 1, CHUNK_PAGES):
                end = min(start + CHUNK_PAGES - 1, page_count)
                print(
                    f"    Chunk pages {start}-{end}/{page_count}",
                    file=sys.stderr,
                )
                result = converter.convert(
                    str(pdf_path), page_range=(start, end),
                )
                chunks.append(doc_to_dict(result.document))
                try_free_gpu_memory()

            docling_data = _merge_docling_data(chunks)
        else:
            result = converter.convert(str(pdf_path))
            docling_data = doc_to_dict(result.document)
    else:
        # Small PDF — convert in one go
        result = converter.convert(str(pdf_path))
        docling_data = doc_to_dict(result.document)

    # Save complete Docling JSON
    docling_json_path = stitched_dir / f"{name}_docling.json"
    docling_json_path.write_text(
        json.dumps(docling_data, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    # Build tables_raw.jsonl
    tables_raw_path = stitched_dir / "tables_raw.jsonl"
    build_tables_raw(docling_data, tables_raw_path)

    # Create scaffolding files
    ensure_empty_jsonl(stitched_dir / "tables_logical_manifest.jsonl")
    ensure_empty_jsonl(stitched_dir / "graph_training_data.jsonl")

    return docling_data, stitched_dir


def run_preprocess(doc_dir: Path, timeout_s: int) -> subprocess.Popen:
    """Launch preprocess.py as a background subprocess."""
    return subprocess.Popen(
        [sys.executable, str(PREPROCESS_PY), str(doc_dir)],
        cwd=str(DOC_TAG_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def wait_preprocess(proc: subprocess.Popen, name: str, timeout_s: int) -> bool:
    """Wait for a preprocess subprocess to finish. Returns True if successful."""
    try:
        proc.wait(timeout=timeout_s)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        print(f"    WARN: preprocess.py timed out for {name}", file=sys.stderr)
        return False


def finalize_fixture(
    name: str,
    stitched_dir: Path,
    fixtures_dir: Path,
    docling_data: dict[str, Any] | None = None,
) -> tuple[int, int]:
    """Copy outputs to fixture directory. Returns (table_count, row_count)."""
    fixture_dir = fixtures_dir / name
    fixture_dir.mkdir(parents=True, exist_ok=True)

    # Copy table_graphs.json
    tg_src = stitched_dir / "table_graphs.json"
    tables_count = 0
    rows_count = 0
    if tg_src.exists():
        shutil.copy2(tg_src, fixture_dir / "table_graphs.json")
        try:
            tg = json.loads(tg_src.read_text(encoding="utf-8"))
            tables = tg.get("tables", [])
            tables_count = len(tables)
            rows_count = sum(len(t.get("rows", [])) for t in tables)
        except (json.JSONDecodeError, OSError):
            pass

    # Copy complete Docling JSON for explorer element overlay
    docling_src = stitched_dir / f"{name}_docling.json"
    if docling_src.exists():
        shutil.copy2(docling_src, fixture_dir / "docling_elements.json")

    return tables_count, rows_count


# ── Progress reporting ───────────────────────────────────

def report_progress(state: BatchState, current: int, total: int):
    """Print progress summary."""
    elapsed = time.time() - (state.started_at or time.time())
    avg = elapsed / max(current, 1)
    remaining = (total - current) * avg
    eta_h = remaining / 3600

    mem = available_memory_gb()
    gpu = gpu_memory_used_mb()
    gpu_str = f", GPU {gpu}MB" if gpu is not None else ""

    print(
        f"\n{'=' * 60}\n"
        f"  Progress: {current}/{total} "
        f"({state.done_count} done, {state.failed_count} failed)\n"
        f"  Elapsed: {elapsed / 60:.0f}min, "
        f"Avg: {avg:.1f}s/doc, "
        f"ETA: {eta_h:.1f}h\n"
        f"  Resources: {mem:.1f}GB RAM free{gpu_str}\n"
        f"{'=' * 60}",
        file=sys.stderr,
    )


# ── Main ─────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Batch Docling ingestion for all PDFs")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--limit", type=int, default=0, help="Process at most N docs (0=all)")
    parser.add_argument("--dry-run", action="store_true", help="List what would be processed")
    parser.add_argument("--restart", action="store_true", help="Ignore state file, start fresh")
    parser.add_argument("--timeout", type=int, default=600, help="Per-doc timeout in seconds")
    parser.add_argument("--sort-by", choices=["size-asc", "size-desc", "name"], default="size-asc")
    parser.add_argument("--min-memory-gb", type=float, default=2.0,
                        help="Pause when available memory drops below this")
    parser.add_argument("--min-disk-gb", type=float, default=2.0,
                        help="Halt when disk space drops below this")
    parser.add_argument("--no-copy-docling", action="store_true",
                        help="Don't copy Docling JSON to fixture dir")
    parser.add_argument("--ifrs-only", action="store_true", help="Only process IFRS sources")
    parser.add_argument("--ugb-only", action="store_true", help="Only process UGB sources")
    parser.add_argument("--missing-docling", action="store_true",
                        help="Reprocess fixtures that have table_graphs but no docling_elements.json")
    parser.add_argument("--source-dir", type=Path, default=None,
                        help="Override source directories with a specific path")
    parser.add_argument("--max-size-mb", type=float, default=0,
                        help="Skip PDFs larger than this (0=no limit)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of parallel workers (launches subprocesses)")
    parser.add_argument("--worker-id", type=int, default=None,
                        help="Worker ID (0-based, used internally for sharding)")
    parser.add_argument("--num-workers", type=int, default=None,
                        help="Total workers (used internally for sharding)")
    args = parser.parse_args()

    # Select source directories
    if args.source_dir:
        source_dirs = [args.source_dir]
    elif args.ifrs_only:
        source_dirs = [d for d in SOURCE_DIRS if "ifrs" in d.name]
    elif args.ugb_only:
        source_dirs = [d for d in SOURCE_DIRS if "ugb" in d.name]
    else:
        source_dirs = SOURCE_DIRS

    # Discover PDFs to process
    if args.missing_docling:
        unprocessed = discover_missing_docling(source_dirs, FIXTURES_DIR)
    else:
        unprocessed = discover_unprocessed(source_dirs, FIXTURES_DIR)

    # Sort
    if args.sort_by == "size-asc":
        unprocessed.sort(key=lambda p: p.stat().st_size)
    elif args.sort_by == "size-desc":
        unprocessed.sort(key=lambda p: p.stat().st_size, reverse=True)
    else:
        unprocessed.sort(key=lambda p: p.name)

    if args.max_size_mb > 0:
        unprocessed = [p for p in unprocessed
                       if p.stat().st_size / (1024 * 1024) <= args.max_size_mb]

    if args.limit > 0:
        unprocessed = unprocessed[:args.limit]

    # Shard for multi-worker mode
    if args.worker_id is not None and args.num_workers is not None:
        unprocessed = [p for i, p in enumerate(unprocessed)
                       if i % args.num_workers == args.worker_id]

    if args.dry_run:
        print(f"Would process {len(unprocessed)} PDFs:\n")
        total_mb = 0
        for p in unprocessed:
            sz = p.stat().st_size / (1024 * 1024)
            total_mb += sz
            src = "ugb" if "ugb" in str(p) else "ifrs"
            print(f"  {p.stem:<60s} {sz:6.1f}MB  ({src})")
        print(f"\nTotal: {len(unprocessed)} PDFs, {total_mb:.0f}MB")
        return 0

    # Multi-worker mode: launch subprocesses and wait
    if args.workers > 1 and args.worker_id is None:
        print(f"Launching {args.workers} workers...", file=sys.stderr)
        procs = []
        for wid in range(args.workers):
            cmd = [
                sys.executable, __file__,
                "--worker-id", str(wid),
                "--num-workers", str(args.workers),
                "--work-dir", str(args.work_dir / f"worker_{wid}"),
                "--timeout", str(args.timeout),
                "--min-memory-gb", str(args.min_memory_gb),
                "--min-disk-gb", str(args.min_disk_gb),
                "--sort-by", args.sort_by,
            ]
            if args.restart:
                cmd.append("--restart")
            if args.ifrs_only:
                cmd.append("--ifrs-only")
            if args.ugb_only:
                cmd.append("--ugb-only")
            if args.source_dir:
                cmd.extend(["--source-dir", str(args.source_dir)])
            if args.max_size_mb > 0:
                cmd.extend(["--max-size-mb", str(args.max_size_mb)])
            if args.limit > 0:
                cmd.extend(["--limit", str(args.limit)])
            if args.missing_docling:
                cmd.append("--missing-docling")

            log_path = f"/tmp/batch_ingest_worker_{wid}.log"
            log_f = open(log_path, "w")
            p = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT)
            procs.append((wid, p, log_f, log_path))
            print(f"  Worker {wid}: PID {p.pid}, log {log_path}", file=sys.stderr)

        # Wait for all workers
        failed_workers = 0
        for wid, p, log_f, log_path in procs:
            rc = p.wait()
            log_f.close()
            status = "OK" if rc == 0 else f"FAILED (rc={rc})"
            print(f"  Worker {wid}: {status}", file=sys.stderr)
            if rc != 0:
                failed_workers += 1

        print(f"\nAll workers done. {failed_workers} failed.", file=sys.stderr)
        return 1 if failed_workers > 0 else 0

    # Verify doc_tag
    if not PREPROCESS_PY.exists():
        print(f"ERROR: preprocess.py not found at {PREPROCESS_PY}", file=sys.stderr)
        print(f"Set DOC_TAG_DIR env var or clone to /tmp/doc_tag", file=sys.stderr)
        return 1

    # Load or create state (each worker gets its own state file)
    state_file = STATE_FILE
    if args.worker_id is not None:
        state_file = STATE_FILE.with_name(f"batch_ingest_state_w{args.worker_id}.json")
    state = BatchState() if args.restart else BatchState.load(state_file)
    if state.started_at is None:
        state.started_at = time.time()

    # Register all docs in state
    for pdf in unprocessed:
        name = safe_name(pdf.stem)
        if name not in state.docs or state.docs[name].status in ("pending", "converting", "postprocessing"):
            state.docs[name] = DocStatus(
                name=name,
                pdf_path=str(pdf),
                pdf_size_mb=round(pdf.stat().st_size / (1024 * 1024), 2),
            )

    # Filter to actionable docs
    to_process = [
        (name, ds) for name, ds in state.docs.items()
        if ds.status in ("pending", "converting", "postprocessing")
    ]

    print(
        f"Batch ingestion: {len(to_process)} to process, "
        f"{state.done_count} already done, "
        f"{state.failed_count} previously failed",
        file=sys.stderr,
    )

    if not to_process:
        print("Nothing to process.", file=sys.stderr)
        return 0

    # Load Docling converter ONCE
    print("Loading Docling DocumentConverter...", file=sys.stderr)
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        print("ERROR: docling not installed. Use /tmp/docling_venv/bin/python3", file=sys.stderr)
        return 1

    converter = DocumentConverter()
    print("Converter ready.", file=sys.stderr)

    args.work_dir.mkdir(parents=True, exist_ok=True)
    state.save(state_file)

    # Track background preprocess
    bg_proc: subprocess.Popen | None = None
    bg_name: str | None = None
    bg_stitched: Path | None = None
    bg_docling_data: dict | None = None

    processed = 0
    converter_reload_counter = 0

    for i, (name, ds) in enumerate(to_process):
        pdf_path = Path(ds.pdf_path)
        if not pdf_path.exists():
            ds.status = "failed"
            ds.error = "PDF not found"
            state.save(state_file)
            continue

        # ── Wait for previous background preprocess ──
        if bg_proc is not None:
            ok = wait_preprocess(bg_proc, bg_name, args.timeout)
            if ok and bg_stitched:
                tc, rc = finalize_fixture(bg_name, bg_stitched, FIXTURES_DIR, bg_docling_data)
                prev = state.docs.get(bg_name)
                if prev:
                    prev.tables_count = tc
                    prev.rows_count = rc
                    prev.status = "done"
                    prev.finished_at = time.time()
                    prev.elapsed_s = round(prev.finished_at - (prev.started_at or prev.finished_at), 1)
            elif bg_name:
                prev = state.docs.get(bg_name)
                if prev:
                    prev.status = "failed"
                    prev.error = "preprocess.py failed"
            bg_proc = None
            bg_name = None
            bg_stitched = None
            bg_docling_data = None
            state.save(state_file)

        # ── Resource checks ──
        mem = available_memory_gb()
        if mem < args.min_memory_gb:
            print(f"  Low memory ({mem:.1f}GB), freeing...", file=sys.stderr)
            try_free_gpu_memory()
            time.sleep(30)
            mem = available_memory_gb()
            if mem < args.min_memory_gb:
                print(f"  Still low memory ({mem:.1f}GB), pausing 60s...", file=sys.stderr)
                time.sleep(60)

        disk = available_disk_gb(args.work_dir)
        if disk < args.min_disk_gb:
            print(f"HALT: Disk space critically low ({disk:.1f}GB)", file=sys.stderr)
            state.save(state_file)
            return 1

        # ── Process this document ──
        print(f"[{i + 1}/{len(to_process)}] {name} ({ds.pdf_size_mb:.1f}MB)", file=sys.stderr)
        ds.status = "converting"
        ds.started_at = time.time()
        state.save(state_file)

        try:
            docling_data, stitched_dir = process_one(
                converter, pdf_path, args.work_dir, args.timeout
            )
            tables_count = len(docling_data.get("tables", []))
            texts_count = len(docling_data.get("texts", []))
            print(
                f"    Docling: {tables_count} tables, {texts_count} texts, "
                f"{time.time() - ds.started_at:.0f}s",
                file=sys.stderr,
            )

            # Launch preprocess in background
            ds.status = "postprocessing"
            doc_dir = args.work_dir / name
            bg_proc = run_preprocess(doc_dir, args.timeout)
            bg_name = name
            bg_stitched = stitched_dir
            bg_docling_data = docling_data

        except Exception as exc:
            ds.status = "failed"
            ds.error = str(exc)[:200]
            ds.finished_at = time.time()
            ds.elapsed_s = round(ds.finished_at - (ds.started_at or ds.finished_at), 1)
            print(f"    FAILED: {ds.error}", file=sys.stderr)
            try_free_gpu_memory()

        state.save(state_file)
        processed += 1
        converter_reload_counter += 1

        # Reload converter every 10 docs to prevent memory leaks
        if converter_reload_counter >= 10:
            print("  Reloading converter (memory hygiene)...", file=sys.stderr)
            del converter
            try_free_gpu_memory()
            converter = DocumentConverter()
            converter_reload_counter = 0

        # Progress report every 10 docs
        if processed % 10 == 0:
            report_progress(state, processed, len(to_process))

    # ── Wait for final background preprocess ──
    if bg_proc is not None:
        ok = wait_preprocess(bg_proc, bg_name, args.timeout)
        if ok and bg_stitched:
            tc, rc = finalize_fixture(bg_name, bg_stitched, FIXTURES_DIR, bg_docling_data)
            prev = state.docs.get(bg_name)
            if prev:
                prev.tables_count = tc
                prev.rows_count = rc
                prev.status = "done"
                prev.finished_at = time.time()
                prev.elapsed_s = round(prev.finished_at - (prev.started_at or prev.finished_at), 1)
        elif bg_name:
            prev = state.docs.get(bg_name)
            if prev:
                prev.status = "failed"
                prev.error = "preprocess.py failed"

    state.finished_at = time.time()
    state.save(state_file)

    # ── Summary ──
    total_time = (state.finished_at or time.time()) - (state.started_at or time.time())
    total_tables = sum(d.tables_count or 0 for d in state.docs.values() if d.status == "done")
    total_rows = sum(d.rows_count or 0 for d in state.docs.values() if d.status == "done")

    print(
        f"\n{'=' * 60}\n"
        f"BATCH INGESTION COMPLETE\n"
        f"{'=' * 60}\n"
        f"  Total time:  {total_time / 3600:.1f}h ({total_time / 60:.0f}min)\n"
        f"  Processed:   {state.done_count}\n"
        f"  Failed:      {state.failed_count}\n"
        f"  Tables:      {total_tables}\n"
        f"  Rows:        {total_rows}\n",
        file=sys.stderr,
    )

    if state.failed_count > 0:
        print("Failed documents:", file=sys.stderr)
        for d in state.docs.values():
            if d.status == "failed":
                print(f"  {d.name}: {d.error}", file=sys.stderr)

    # Write report JSON
    report_path = REPO_ROOT / "eval" / "batch_ingest_report.json"
    report = {
        "started_at": state.started_at,
        "finished_at": state.finished_at,
        "total_time_h": round(total_time / 3600, 2),
        "processed": state.done_count,
        "failed": state.failed_count,
        "total_tables": total_tables,
        "total_rows": total_rows,
        "failures": [
            {"name": d.name, "error": d.error}
            for d in state.docs.values() if d.status == "failed"
        ],
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport: {report_path}", file=sys.stderr)

    return 0 if state.failed_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
