#!/usr/bin/env python3
"""
pipeline_runner.py -- CLI entry point for the gated FOBE pipeline.

Runs the 6-stage pipeline with quality gates on one or more documents.
Each stage has a gate that can halt processing if quality is insufficient.

Output structure:
    eval/runs/<run_id>/
        <doc_name>/
            pipeline.json          (gate results, status, metrics)
            meta.json
            classification.json
            tagging.json
            consistency.json
            corroboration.json
        summary.json

Usage:
    python3 eval/pipeline_runner.py <table_graphs.json>
    python3 eval/pipeline_runner.py --all --verbose
    python3 eval/pipeline_runner.py --all --no-llm --output-dir /tmp/my_run
    python3 eval/pipeline_runner.py eval/fixtures/omv_2024/table_graphs.json --stages stage1,stage2
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline import Pipeline, PipelineConfig, DocumentState, _write_json
from stages import build_default_stages


def generate_run_id(runs_dir: str) -> str:
    """Generate run ID like 27032026EVAL001 (DDMMYYYYEVAL + sequence)."""
    today = datetime.now().strftime("%d%m%Y")
    prefix = f"{today}EVAL"
    existing = []
    if os.path.isdir(runs_dir):
        for name in os.listdir(runs_dir):
            if name.startswith(prefix):
                try:
                    seq = int(name[len(prefix):])
                    existing.append(seq)
                except ValueError:
                    pass
    next_seq = max(existing, default=0) + 1
    return f"{prefix}{next_seq:03d}"


def discover_fixtures(ontology_root: str) -> list[str]:
    """Find all table_graphs.json files in eval/fixtures/ and /tmp/doc_tag/."""
    fixtures_dir = Path(ontology_root) / "eval" / "fixtures"
    doc_tag_dir = Path("/tmp/doc_tag")
    seen = set()
    paths = []
    for p in sorted(
        list(doc_tag_dir.glob("*/*/table_graphs.json"))
        + list(fixtures_dir.glob("*/table_graphs.json"))
    ):
        s = str(p)
        if s not in seen:
            seen.add(s)
            paths.append(s)
    return paths


def build_summary(states: list[DocumentState], run_id: str,
                  elapsed: float) -> dict:
    """Aggregate pipeline results into a cross-document summary."""
    completed = []
    halted = Counter()  # stage → count
    errors = []
    halt_details = []

    totals = Counter()
    all_fact_scores = Counter()
    classification_totals = Counter()
    docs = []

    for state in states:
        if state.status == "completed":
            completed.append(state)
        elif state.status == "halted_at_gate":
            halted[state.halted_at] += 1
            halt_details.append({
                "doc": state.doc_name,
                "stage": state.halted_at,
                "reason": _first_finding(state),
            })
        elif state.status == "error":
            errors.append({
                "doc": state.doc_name,
                "error": state.error,
            })

        # Collect metrics from completed documents
        if state.tagging:
            t = state.tagging
            totals["tables"] += t.get("tables", 0)
            totals["total_rows"] += t.get("total_rows", 0)
            totals["data_rows"] += t.get("data_rows", 0)
            totals["pretagged_rows"] += t.get("pretagged_rows", 0)
            totals["indexed_facts"] += t.get("indexed_facts", 0)
            for cls, cnt in t.get("classified_tables", {}).items():
                classification_totals[cls] += cnt

        if state.corroboration:
            fs = state.corroboration.get("fact_scores", {})
            for key in ("confirmed", "corroborated", "unconfirmed",
                        "contradicted", "total", "table_arithmetic"):
                all_fact_scores[key] += fs.get(key, 0)

        doc_entry = {
            "name": state.doc_name,
            "status": state.status,
            "halted_at": state.halted_at,
            "stages_run": [sr["stage"] for sr in state.stage_results],
        }
        if state.tagging:
            doc_entry["indexed_facts"] = state.tagging.get("indexed_facts", 0)
        if state.corroboration:
            doc_entry["fact_scores"] = state.corroboration.get("fact_scores", {})
        docs.append(doc_entry)

    return {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "pipeline_summary": {
            "completed": len(completed),
            "halted": dict(halted),
            "errors": len(errors),
            "halt_details": halt_details,
            "error_details": errors,
        },
        "totals": dict(totals),
        "classification_totals": dict(classification_totals.most_common()),
        "fact_scores": dict(all_fact_scores),
        "documents": docs,
    }


def _first_finding(state: DocumentState) -> str:
    """Extract the first finding message from a halted state."""
    if state.halted_at and state.halted_at in state.gate_results:
        gr = state.gate_results[state.halted_at]
        if gr.findings:
            return gr.findings[0].get("detail", gr.findings[0].get("type", ""))
    return ""


def main():
    parser = argparse.ArgumentParser(
        description="FOBE gated pipeline runner")
    parser.add_argument("paths", nargs="*",
                        help="table_graphs.json path(s)")
    parser.add_argument("--all", action="store_true",
                        help="Run on all fixtures + /tmp/doc_tag/")
    parser.add_argument("--no-llm", action="store_true",
                        help="Disable LLM-based stages")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print detailed progress")
    parser.add_argument("--output-dir",
                        help="Override output directory")
    parser.add_argument("--reclassify", action="store_true",
                        help="Strip existing statementComponent and re-classify "
                             "all tables from scratch")
    parser.add_argument("--documents", nargs="*",
                        help="Filter --all to specific fixture names "
                             "(e.g. amag_2024 evn_2024)")
    parser.add_argument("--stages",
                        help="Comma-separated stage names to run "
                             "(e.g. stage1,stage2,stage3)")

    args = parser.parse_args()

    ontology_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Discover documents
    if args.all:
        doc_paths = discover_fixtures(ontology_root)
    else:
        doc_paths = args.paths

    # Filter by --documents if specified
    if args.documents:
        doc_set = set(args.documents)
        doc_paths = [p for p in doc_paths
                     if Path(p).parent.name in doc_set]

    if not doc_paths:
        parser.print_help()
        sys.exit(1)

    # Parse stages
    stages_to_run = None
    if args.stages:
        stages_to_run = [s.strip() for s in args.stages.split(",")]

    # Set up run directory
    runs_dir = os.path.join(ontology_root, "eval", "runs")
    run_id = generate_run_id(runs_dir)

    if args.output_dir:
        run_dir = args.output_dir
    else:
        run_dir = os.path.join(runs_dir, run_id)

    os.makedirs(run_dir, exist_ok=True)

    # Configure pipeline
    config = PipelineConfig(
        stages_to_run=stages_to_run,
        use_llm=not args.no_llm,
        reclassify=args.reclassify,
        verbose=args.verbose,
        output_dir=run_dir,
        ontology_root=ontology_root,
    )

    pipeline = Pipeline(config=config, stages=build_default_stages())

    print(f"Run {run_id}: {len(doc_paths)} documents → {run_dir}",
          file=sys.stderr)

    states = []
    t0 = time.monotonic()

    for i, tg_path in enumerate(doc_paths, 1):
        doc_name = Path(tg_path).parent.name
        if args.verbose:
            print(f"\n[{i}/{len(doc_paths)}] {doc_name}", file=sys.stderr)

        state = pipeline.run(tg_path)
        states.append(state)

        # Persist per-document results
        doc_dir = os.path.join(run_dir, doc_name)
        pipeline.persist(state, doc_dir)

        # Brief status line
        status_icon = {"completed": "OK", "halted_at_gate": "HALT",
                       "error": "ERR"}.get(state.status, "?")
        suffix = ""
        if state.halted_at:
            suffix = f" at {state.halted_at}: {_first_finding(state)[:60]}"
        elif state.status == "error":
            suffix = f": {state.error[:60]}"
        elif state.corroboration:
            fs = state.corroboration.get("fact_scores", {})
            suffix = (f"  facts={fs.get('total', 0)}  "
                      f"confirmed={fs.get('confirmed', 0)}  "
                      f"contradicted={fs.get('contradicted', 0)}")

        print(f"  [{status_icon}] {doc_name}{suffix}", file=sys.stderr)

    elapsed = time.monotonic() - t0

    # Write summary
    summary = build_summary(states, run_id, elapsed)
    summary_path = os.path.join(run_dir, "summary.json")
    _write_json(summary_path, summary)

    # Final status
    ps = summary["pipeline_summary"]
    print(f"\nDone: {ps['completed']} completed, "
          f"{sum(ps['halted'].values())} halted, "
          f"{ps['errors']} errors in {elapsed:.1f}s",
          file=sys.stderr)
    if ps["halt_details"]:
        print("Halted documents:", file=sys.stderr)
        for h in ps["halt_details"]:
            print(f"  {h['doc']} @ {h['stage']}: {h['reason'][:80]}",
                  file=sys.stderr)
    print(f"Summary: {summary_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
