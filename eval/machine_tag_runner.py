#!/usr/bin/env python3
"""
machine_tag_runner.py — Run a single tagging model across multiple documents.

Invoked as a subprocess by the explorer server. Runs one of three tagging
models (pretag, structural, llm) on each document, writes results to an
output directory, and optionally appends to the tag log and/or voting system.

Usage:
    python3 eval/machine_tag_runner.py \
        --model pretag \
        --documents amag_2024 evn_2024 \
        --output-dir eval/machine_tag_runs/30032026MT001 \
        [--dry-run] [--verbose] \
        [--write-tag-log] [--write-voting]
"""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Add eval dir to path for sibling imports
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(REPO_ROOT))

FIXTURES_DIR = REPO_ROOT / "eval" / "fixtures"

# ── Tag log / voting helpers ──────────────────────────────────────────────

TAG_LOG_PATH = FIXTURES_DIR / ".tag_log.jsonl"


def _append_tag_log_file(entry: dict):
    """Append a tag-log entry to the file-based JSONL log."""
    with open(TAG_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def _get_supabase_queries():
    """Lazily import explorer queries module (needs SUPABASE env vars)."""
    try:
        sys.path.insert(0, str(REPO_ROOT / "explorer"))
        import queries as Q
        # Test that supabase is configured
        Q.get_supabase()
        return Q
    except Exception:
        return None


def _append_tag_log(entry: dict, Q):
    """Write a tag-log entry to both file and Supabase (if available)."""
    _append_tag_log_file(entry)
    if Q:
        try:
            Q.append_tag_log(entry)
        except Exception:
            pass  # Supabase table may not exist yet


def _cast_vote(vote: dict, Q):
    """Cast a vote via Supabase queries (no HTTP, no auth)."""
    if Q:
        try:
            Q.cast_tag_vote(vote)
        except Exception as e:
            print(f"  [vote] failed: {e}", file=sys.stderr)


# ── Per-document runner ───────────────────────────────────────────────────

def _run_pretag(tg_path: str, dry_run: bool, verbose: bool) -> list[dict]:
    """Run pretag_all on a single document. Returns list of new tags."""
    from pretag_all import pretag_document
    return pretag_document(tg_path, dry_run=dry_run) or []


def _run_structural(tg_path: str, dry_run: bool, verbose: bool) -> list[dict]:
    """Run structural inference on a single document. Returns list of inferred tags."""
    from structural_inference import run_structural_inference
    return run_structural_inference(tg_path, dry_run=dry_run, verbose=verbose) or []


def _run_llm(tg_path: str, dry_run: bool, verbose: bool) -> list[dict]:
    """Run LLM tagger on a single document. Returns list of LLM tags."""
    from llm_tagger import tag_document
    return tag_document(tg_path, dry_run=dry_run, verbose=verbose) or []


MODEL_RUNNERS = {
    "pretag": _run_pretag,
    "structural": _run_structural,
    "llm": _run_llm,
}

SOURCE_MAP = {
    "pretag": "machine:pretag",
    "structural": "machine:structural",
    "llm": "machine:llm",
}


def run_document(
    doc_id: str,
    model: str,
    output_dir: Path,
    *,
    dry_run: bool = False,
    verbose: bool = False,
    write_tag_log: bool = False,
    write_voting: bool = False,
    Q=None,
) -> dict:
    """Process a single document with the chosen model. Returns result dict."""
    tg_path = str(FIXTURES_DIR / doc_id / "table_graphs.json")
    if not os.path.exists(tg_path):
        return {"document_id": doc_id, "error": f"table_graphs.json not found", "rows_tagged": 0}

    runner = MODEL_RUNNERS[model]
    source = SOURCE_MAP[model]

    try:
        tags = runner(tg_path, dry_run, verbose)
        if tags is None:
            tags = []
    except Exception as e:
        traceback.print_exc()
        return {"document_id": doc_id, "error": str(e), "rows_tagged": 0}

    rows_tagged = len(tags)
    tag_log_entries = 0
    votes_cast = 0

    now = datetime.now(timezone.utc).isoformat()

    # Write to tag log
    if write_tag_log and not dry_run:
        for tag in tags:
            entry = {
                "timestamp": now,
                "user_email": "machine",
                "doc_id": doc_id,
                "page_no": tag.get("page_no"),
                "action": "add",
                "element_type": tag.get("concept_id") or tag.get("preTagged"),
                "old_type": None,
                "source": source,
            }
            _append_tag_log(entry, Q)
            tag_log_entries += 1

    # Cast votes
    if write_voting and not dry_run and Q:
        for tag in tags:
            target_id = tag.get("row_id")
            concept = tag.get("concept_id") or tag.get("preTagged")
            if not target_id or not concept:
                continue
            vote = {
                "dimension": "row_concept",
                "target_id": target_id,
                "action": "tag",
                "value": concept,
                "confidence": tag.get("confidence", 0.8),
                "source": source,
                "comment": f"Machine tag run ({model})",
            }
            _cast_vote(vote, Q)
            votes_cast += 1

    result = {
        "document_id": doc_id,
        "rows_tagged": rows_tagged,
        "tag_log_entries": tag_log_entries,
        "votes_cast": votes_cast,
    }

    # Write per-doc result
    doc_dir = output_dir / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    with open(doc_dir / "result.json", "w") as f:
        json.dump(result, f, indent=2)

    return result


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run a tagging model across documents")
    parser.add_argument("--model", required=True, choices=["pretag", "structural", "llm"])
    parser.add_argument("--documents", nargs="+", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--write-tag-log", action="store_true")
    parser.add_argument("--write-voting", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Lazy-load Supabase queries if voting is needed
    Q = _get_supabase_queries() if (args.write_tag_log or args.write_voting) else None

    total_tagged = 0
    total_log = 0
    total_votes = 0
    docs_processed = 0

    print(f"Machine Tag: model={args.model}, docs={len(args.documents)}, "
          f"tag_log={args.write_tag_log}, voting={args.write_voting}, dry_run={args.dry_run}")

    for i, doc_id in enumerate(args.documents, 1):
        print(f"\n[{i}/{len(args.documents)}] {doc_id}")
        result = run_document(
            doc_id,
            args.model,
            output_dir,
            dry_run=args.dry_run,
            verbose=args.verbose,
            write_tag_log=args.write_tag_log,
            write_voting=args.write_voting,
            Q=Q,
        )
        if result.get("error"):
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  rows_tagged={result['rows_tagged']} "
                  f"tag_log={result['tag_log_entries']} votes={result['votes_cast']}")
            docs_processed += 1
        total_tagged += result.get("rows_tagged", 0)
        total_log += result.get("tag_log_entries", 0)
        total_votes += result.get("votes_cast", 0)

    # Write summary
    summary = {
        "model": args.model,
        "docs_processed": docs_processed,
        "docs_total": len(args.documents),
        "rows_tagged": total_tagged,
        "tag_log_entries": total_log,
        "votes_cast": total_votes,
        "dry_run": args.dry_run,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\nDone: {docs_processed}/{len(args.documents)} docs, "
          f"{total_tagged} rows tagged, {total_log} log entries, {total_votes} votes")


if __name__ == "__main__":
    main()
