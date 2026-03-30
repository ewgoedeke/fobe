#!/usr/bin/env python3
"""
run_eval.py — Structured evaluation runner.

Runs the full eval pipeline across documents and writes per-document
results plus a cross-document summary into a timestamped run folder.

Output structure:
    eval/runs/<run_id>/
        <doc_name>/
            meta.json
            classification.json
            tagging.json
            consistency.json
            corroboration.json
            error.json          (only if the document failed)
        summary.json

Usage:
    python3 eval/run_eval.py --all --no-llm --verbose
    python3 eval/run_eval.py eval/fixtures/omv_2024/table_graphs.json
    python3 eval/run_eval.py --all --output-dir /tmp/my_eval
    python3 eval/run_eval.py --all --pipeline    # use gated pipeline
"""

import argparse
import json
import os
import sys
import time
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

# Ensure eval/ is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from run_corpus import analyze_document
    from check_classification import check_table
except ImportError:
    analyze_document = None
    check_table = None
from generate_document_meta import generate_meta
from classify_tables import classify_document


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


def process_document(tg_path: str, ontology_root: str, doc_dir: str,
                     use_llm: bool, verbose: bool) -> dict:
    """Run full pipeline for one document. Returns result dict or raises."""
    # 1. Meta
    meta = generate_meta(tg_path, verbose=verbose)
    with open(os.path.join(doc_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    # 2. Classification (dry_run=True so we don't modify the source file)
    classification = classify_document(tg_path, dry_run=True,
                                       verbose=verbose, use_llm=use_llm)
    with open(os.path.join(doc_dir, "classification.json"), "w") as f:
        json.dump(classification, f, indent=2)

    # 3. Classification checks
    with open(tg_path) as f:
        data = json.load(f)
    tables = data.get("tables", [])
    all_issues = []
    for table in tables:
        all_issues.extend(check_table(table))
    by_severity = Counter(i["severity"] for i in all_issues)
    classification_check = {
        "tables_checked": len(tables),
        "issues": all_issues,
        "summary": dict(by_severity),
    }

    # 4. Full analysis (tagging, consistency, corroboration)
    result = analyze_document(tg_path, ontology_root)

    # 5. Slice result into per-concern output files

    tagging = {
        "name": result["name"],
        "tables": result["tables"],
        "total_rows": result["total_rows"],
        "data_rows": result["data_rows"],
        "pretagged_rows": result["pretagged_rows"],
        "label_matched_rows": result["label_matched_rows"],
        "structural_inferred": result["structural_inferred"],
        "structural_by_rule": result["structural_by_rule"],
        "structural_iterations": result["structural_iterations"],
        "indexed_facts": result["indexed_facts"],
        "unique_concepts": result["unique_concepts"],
        "concept_list": result["concept_list"],
        "classified_tables": result["classified_tables"],
        "fact_sources": result["fact_sources"],
    }
    with open(os.path.join(doc_dir, "tagging.json"), "w") as f:
        json.dump(tagging, f, indent=2)

    consistency = {
        "name": result["name"],
        "findings_count": result["findings_count"],
        "by_category": result["by_category"],
        "by_edge": result["by_edge"],
        "classification_check": classification_check,
        "findings": result["findings"],
    }
    with open(os.path.join(doc_dir, "consistency.json"), "w") as f:
        json.dump(consistency, f, indent=2)

    corroboration = {
        "name": result["name"],
        "corroboration": result["corroboration"],
        "fact_scores": result["fact_scores"],
        "confirmed_concepts": result["confirmed_concepts"],
        "contradicted_concepts": result["contradicted_concepts"],
        "unconfirmed_concepts": result["unconfirmed_concepts"],
    }
    with open(os.path.join(doc_dir, "corroboration.json"), "w") as f:
        json.dump(corroboration, f, indent=2)

    return result


def build_summary(results: list[dict], errors: list[dict],
                  run_id: str, elapsed: float) -> dict:
    """Aggregate per-document results into a cross-document summary."""
    totals = Counter()
    all_categories = Counter()
    all_edges = Counter()
    all_fact_scores = Counter()
    classification_totals = Counter()
    docs = []

    for r in results:
        totals["tables"] += r["tables"]
        totals["total_rows"] += r["total_rows"]
        totals["data_rows"] += r["data_rows"]
        totals["pretagged_rows"] += r["pretagged_rows"]
        totals["label_matched_rows"] += r["label_matched_rows"]
        totals["structural_inferred"] += r["structural_inferred"]
        totals["indexed_facts"] += r["indexed_facts"]

        for cat, cnt in r["by_category"].items():
            all_categories[cat] += cnt
        for edge, cnt in r["by_edge"].items():
            all_edges[edge] += cnt
        for key in ("confirmed", "corroborated", "unconfirmed", "contradicted"):
            all_fact_scores[key] += r["fact_scores"].get(key, 0)
        all_fact_scores["total"] += r["fact_scores"].get("total", 0)
        all_fact_scores["table_arithmetic"] += r["fact_scores"].get("table_arithmetic", 0)

        for cls, cnt in r["classified_tables"].items():
            classification_totals[cls] += cnt

        docs.append({
            "name": r["name"],
            "tables": r["tables"],
            "indexed_facts": r["indexed_facts"],
            "findings_count": r["findings_count"],
            "fact_scores": r["fact_scores"],
            "corroboration": r["corroboration"],
        })

    # Cross-document patterns: concepts that appear contradicted in multiple docs
    contradicted_across = Counter()
    for r in results:
        for c in r["contradicted_concepts"]:
            contradicted_across[c] += 1
    recurring_contradictions = {
        c: cnt for c, cnt in contradicted_across.most_common()
        if cnt >= 2
    }

    return {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "documents_processed": len(results),
        "documents_failed": len(errors),
        "totals": dict(totals),
        "classification_totals": dict(classification_totals.most_common()),
        "finding_categories": dict(all_categories.most_common()),
        "finding_edges": dict(all_edges.most_common()),
        "fact_scores": dict(all_fact_scores),
        "cross_document_patterns": {
            "recurring_contradictions": recurring_contradictions,
        },
        "documents": docs,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="FOBE structured eval runner")
    parser.add_argument("paths", nargs="*", help="table_graphs.json paths")
    parser.add_argument("--all", action="store_true",
                        help="Run on all fixtures + /tmp/doc_tag/")
    parser.add_argument("--no-llm", action="store_true",
                        help="Disable LLM-based classification")
    parser.add_argument("--verbose", action="store_true",
                        help="Print detailed progress")
    parser.add_argument("--output-dir",
                        help="Override output directory (default: eval/runs/<run_id>)")
    parser.add_argument("--pipeline", action="store_true",
                        help="Use gated pipeline (recommended)")
    args = parser.parse_args()

    ontology_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Discover documents
    if args.all:
        doc_paths = discover_fixtures(ontology_root)
    else:
        doc_paths = args.paths

    if not doc_paths:
        parser.print_help()
        sys.exit(1)

    # Set up run directory
    runs_dir = os.path.join(ontology_root, "eval", "runs")
    run_id = generate_run_id(runs_dir)

    if args.output_dir:
        run_dir = args.output_dir
    else:
        run_dir = os.path.join(runs_dir, run_id)

    os.makedirs(run_dir, exist_ok=True)
    print(f"Run {run_id}: {len(doc_paths)} documents → {run_dir}", file=sys.stderr)

    # Gated pipeline mode
    if args.pipeline:
        from pipeline import Pipeline, PipelineConfig, _write_json
        from stages import build_default_stages
        from pipeline_runner import build_summary as pipeline_build_summary

        config = PipelineConfig(
            use_llm=not args.no_llm,
            verbose=args.verbose,
            output_dir=run_dir,
            ontology_root=ontology_root,
        )
        pipeline = Pipeline(config=config, stages=build_default_stages())

        states = []
        t0 = time.monotonic()
        for i, tg_path in enumerate(doc_paths, 1):
            doc_name = Path(tg_path).parent.name
            if args.verbose:
                print(f"\n[{i}/{len(doc_paths)}] {doc_name}", file=sys.stderr)
            state = pipeline.run(tg_path)
            states.append(state)
            doc_dir_ = os.path.join(run_dir, doc_name)
            pipeline.persist(state, doc_dir_)
            status_icon = {"completed": "OK", "halted_at_gate": "HALT",
                           "error": "ERR"}.get(state.status, "?")
            print(f"  [{status_icon}] {doc_name}", file=sys.stderr)

        elapsed = time.monotonic() - t0
        summary = pipeline_build_summary(states, run_id, elapsed)
        _write_json(os.path.join(run_dir, "summary.json"), summary)

        ps = summary["pipeline_summary"]
        print(f"\nDone: {ps['completed']} completed, "
              f"{sum(ps['halted'].values())} halted, "
              f"{ps['errors']} errors", file=sys.stderr)
        print(f"Summary: {os.path.join(run_dir, 'summary.json')}", file=sys.stderr)
        return

    results = []
    errors = []
    t0 = time.monotonic()

    for i, tg_path in enumerate(doc_paths, 1):
        doc_name = Path(tg_path).parent.name
        doc_dir = os.path.join(run_dir, doc_name)
        os.makedirs(doc_dir, exist_ok=True)

        if args.verbose:
            print(f"[{i}/{len(doc_paths)}] {doc_name} ...", file=sys.stderr)

        try:
            r = process_document(
                tg_path, ontology_root, doc_dir,
                use_llm=not args.no_llm,
                verbose=args.verbose,
            )
            results.append(r)
            if args.verbose:
                fs = r["fact_scores"]
                print(f"  facts={r['indexed_facts']}  "
                      f"confirmed={fs['confirmed']}  "
                      f"contradicted={fs['contradicted']}  "
                      f"findings={r['findings_count']}",
                      file=sys.stderr)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"  ERROR ({doc_name}): {e}", file=sys.stderr)
            error_info = {
                "document": doc_name,
                "path": tg_path,
                "error": str(e),
                "traceback": tb,
            }
            errors.append(error_info)
            with open(os.path.join(doc_dir, "error.json"), "w") as f:
                json.dump(error_info, f, indent=2)

    elapsed = time.monotonic() - t0

    # Write summary
    summary = build_summary(results, errors, run_id, elapsed)
    summary_path = os.path.join(run_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Print final status
    print(f"\nDone: {len(results)} OK, {len(errors)} failed "
          f"in {elapsed:.1f}s", file=sys.stderr)
    print(f"Summary: {summary_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
