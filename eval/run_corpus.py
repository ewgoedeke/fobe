#!/usr/bin/env python3
"""
run_corpus.py — Run consistency checks across all available documents
and produce a comparative tagging report.

Reports per document:
  - Tables / rows / preTagged / label-matched facts
  - Corroboration results: confirmed, contradicted, unconfirmed
  - Findings by category
  - Cross-document patterns

Usage:
    python3 eval/run_corpus.py <dir1/table_graphs.json> [dir2/...] [...]
    python3 eval/run_corpus.py --all   # scan /tmp/doc_tag/ + eval/fixtures/
"""

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_consistency import (
    check_document, check_document_scored, index_facts, Finding, Category,
    PRIMARY_STATEMENTS, _match_label, _infer_table_context,
)
from fact_scoring import CorroborationStatus
from relationship_graph import build_graph, EdgeType
from structural_inference import cascade as structural_cascade


def analyze_document(doc_path: str, ontology_root: str) -> dict:
    """Analyze a single document and return structured results."""
    with open(doc_path) as f:
        data = json.load(f)
    tables = data.get("tables", [])

    # Basic stats
    total_rows = 0
    data_rows = 0
    pretagged_rows = 0
    label_matched_rows = 0
    classified_tables = Counter()

    for table in tables:
        sc = table.get("metadata", {}).get("statementComponent")
        classified_tables[sc or "unclassified"] += 1
        table_ctx = _infer_table_context(table)

        for row in table.get("rows", []):
            total_rows += 1
            if row.get("rowType") in ("DATA", "TOTAL_EXPLICIT", "TOTAL_IMPLICIT"):
                data_rows += 1
            pt = row.get("preTagged")
            if pt and isinstance(pt, dict) and pt.get("conceptId"):
                pretagged_rows += 1
            else:
                label = row.get("label", "") or ""
                if _match_label(label, table_context=table_ctx, ontology_root=ontology_root):
                    label_matched_rows += 1

    # Structural inference (dry-run: count but don't modify original)
    import copy
    tables_copy = copy.deepcopy(tables)
    si_iterations, si_tags = structural_cascade(tables_copy, ontology_root)
    si_by_rule = Counter(t.rule for t in si_tags)
    structural_inferred = len(si_tags)

    # Index facts
    facts = index_facts(tables, ontology_root=ontology_root)

    # Fact stats
    unique_concepts = set()
    fact_sources = Counter()  # preTagged vs label-matched
    for (ctx, cid, pk), flist in facts.items():
        unique_concepts.add(cid)
        for f in flist:
            if f.is_primary:
                fact_sources["primary_statement"] += 1
            else:
                fact_sources["note_or_other"] += 1

    # Run checks with scoring
    findings, score_registry = check_document_scored(tables, ontology_root)

    # Categorize findings
    by_category = Counter()
    by_edge = Counter()
    finding_details = []
    for f in findings:
        by_category[f.category.value] += 1
        if f.edge_name:
            by_edge[f.edge_name] += 1
        finding_details.append(f.to_dict())

    # Per-fact corroboration from score registry
    fact_status_counts = Counter()
    for fs in score_registry.values():
        fact_status_counts[fs.status.value] += 1

    # Table arithmetic stats
    table_arith_count = sum(
        1 for fs in score_registry.values()
        if any(c.check_type == "TABLE_ARITHMETIC" for c in fs.checks)
    )

    # Concept-level summary (backward compat + overview)
    confirmed_concepts = set()
    contradicted_concepts = set()
    for fs in score_registry.values():
        if fs.status == CorroborationStatus.CONFIRMED:
            confirmed_concepts.add(fs.concept_id)
        elif fs.status == CorroborationStatus.CONTRADICTED:
            contradicted_concepts.add(fs.concept_id)
    unconfirmed_concepts = unique_concepts - confirmed_concepts - contradicted_concepts

    return {
        "path": doc_path,
        "name": Path(doc_path).parent.name,
        "tables": len(tables),
        "total_rows": total_rows,
        "data_rows": data_rows,
        "pretagged_rows": pretagged_rows,
        "label_matched_rows": label_matched_rows,
        "structural_inferred": structural_inferred,
        "structural_by_rule": dict(si_by_rule),
        "structural_iterations": si_iterations,
        "indexed_facts": len(facts),
        "unique_concepts": len(unique_concepts),
        "concept_list": sorted(unique_concepts),
        "classified_tables": dict(classified_tables.most_common()),
        "fact_sources": dict(fact_sources),
        "findings_count": len(findings),
        "by_category": dict(by_category),
        "by_edge": dict(by_edge.most_common()),
        "confirmed_concepts": sorted(confirmed_concepts),
        "contradicted_concepts": sorted(contradicted_concepts),
        "unconfirmed_concepts": sorted(unconfirmed_concepts),
        "corroboration": {
            "confirmed": len(confirmed_concepts),
            "contradicted": len(contradicted_concepts),
            "unconfirmed": len(unconfirmed_concepts),
        },
        "fact_scores": {
            "confirmed": fact_status_counts.get("CONFIRMED", 0),
            "corroborated": fact_status_counts.get("CORROBORATED", 0),
            "unconfirmed": fact_status_counts.get("UNCONFIRMED", 0),
            "contradicted": fact_status_counts.get("CONTRADICTED", 0),
            "total": len(score_registry),
            "table_arithmetic": table_arith_count,
        },
        "findings": finding_details,
    }


def print_comparison(results: list[dict]):
    """Print a comparative summary across all documents."""
    print(f"\n{'=' * 90}")
    print(f"FOBE Corpus Analysis — {len(results)} documents")
    print(f"{'=' * 90}")

    # Header
    names = [r["name"][:20] for r in results]
    print(f"\n{'Metric':<35s}", end="")
    for n in names:
        print(f" {n:>15s}", end="")
    print()
    print("─" * (35 + 16 * len(names)))

    # Rows
    metrics = [
        ("Tables", "tables"),
        ("Data rows", "data_rows"),
        ("PreTagged rows", "pretagged_rows"),
        ("Label-matched rows", "label_matched_rows"),
        ("Structural inferred", "structural_inferred"),
        ("Indexed fact keys", "indexed_facts"),
        ("Unique concepts", "unique_concepts"),
    ]
    for label, key in metrics:
        print(f"{label:<35s}", end="")
        for r in results:
            print(f" {r[key]:>15,d}", end="")
        print()

    # Per-fact corroboration scores
    print()
    print(f"{'Fact Scores':<35s}", end="")
    for n in names:
        print(f" {n:>15s}", end="")
    print()
    print("─" * (35 + 16 * len(names)))
    for label, key in [
        ("CONFIRMED (≥2 checks)", "confirmed"),
        ("CORROBORATED (1 check)", "corroborated"),
        ("UNCONFIRMED (no checks)", "unconfirmed"),
        ("CONTRADICTED (failed)", "contradicted"),
        ("Total scored facts", "total"),
        ("Table arithmetic hits", "table_arithmetic"),
    ]:
        print(f"  {label:<33s}", end="")
        for r in results:
            print(f" {r.get('fact_scores', {}).get(key, 0):>15,d}", end="")
        print()

    # Concept-level summary
    print()
    print(f"{'Concept Summary':<35s}", end="")
    for n in names:
        print(f" {n:>15s}", end="")
    print()
    print("─" * (35 + 16 * len(names)))
    for label, key in [("Confirmed concepts", "confirmed"), ("Contradicted concepts", "contradicted"), ("Unconfirmed concepts", "unconfirmed")]:
        print(f"  {label:<33s}", end="")
        for r in results:
            print(f" {r['corroboration'][key]:>15,d}", end="")
        print()

    # Findings
    print()
    print(f"{'Findings':<35s}", end="")
    for n in names:
        print(f" {n:>15s}", end="")
    print()
    print("─" * (35 + 16 * len(names)))

    all_cats = sorted(set(cat for r in results for cat in r["by_category"]))
    icons = {
        "VALID_DISAGGREGATION": "✅",
        "VALID_TIE": "✅",
        "BROKEN_RELATIONSHIP": "❌",
        "DECOMPOSITION_RESIDUAL": "⚠️",
        "EXPLAINED_MISMATCH": "ℹ️",
        "UNEXPLAINED_INCONSISTENCY": "❓",
    }
    for cat in all_cats:
        icon = icons.get(cat, "  ")
        print(f"  {icon} {cat:<31s}", end="")
        for r in results:
            print(f" {r['by_category'].get(cat, 0):>15,d}", end="")
        print()

    # Total
    print(f"  {'TOTAL':<33s}", end="")
    for r in results:
        print(f" {r['findings_count']:>15,d}", end="")
    print()

    # Cross-document patterns
    print(f"\n{'=' * 90}")
    print("Cross-document patterns")
    print(f"{'=' * 90}")

    # Which concepts are confirmed across multiple documents?
    concept_confirm_count = Counter()
    for r in results:
        for c in r["confirmed_concepts"]:
            concept_confirm_count[c] += 1

    multi_confirmed = [(c, n) for c, n in concept_confirm_count.most_common() if n > 1]
    if multi_confirmed:
        print(f"\nConcepts confirmed in multiple documents:")
        for c, n in multi_confirmed:
            print(f"  {c:<50s} {n}/{len(results)} documents")

    # Which edges fire most?
    edge_count = Counter()
    for r in results:
        for edge, count in r["by_edge"].items():
            edge_count[edge] += count
    if edge_count:
        print(f"\nMost active checks:")
        for edge, count in edge_count.most_common(10):
            print(f"  {edge:<50s} {count} findings")

    # Which concepts are unconfirmed everywhere?
    always_unconfirmed = None
    for r in results:
        s = set(r["unconfirmed_concepts"])
        if always_unconfirmed is None:
            always_unconfirmed = s
        else:
            always_unconfirmed &= s
    if always_unconfirmed:
        print(f"\nConcepts unconfirmed in ALL documents ({len(always_unconfirmed)}):")
        for c in sorted(always_unconfirmed)[:20]:
            print(f"  {c}")
        if len(always_unconfirmed) > 20:
            print(f"  ... and {len(always_unconfirmed) - 20} more")

    # Per-document detail
    for r in results:
        print(f"\n{'─' * 90}")
        print(f"{r['name']}")
        print(f"{'─' * 90}")
        if r["findings"]:
            for f in r["findings"]:
                sev = f.get("severity", "")
                cat = f.get("category", "")
                msg = f.get("message", "")[:80]
                print(f"  [{sev:7s}] {cat:30s} {msg}")
        else:
            print("  (no findings)")


def main():
    ontology_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if "--all" in sys.argv:
        # Scan both doc_tag (preTagged) and eval/fixtures (Docling-parsed)
        doc_tag_dir = Path("/tmp/doc_tag")
        fixtures_dir = Path(ontology_root) / "eval" / "fixtures"
        seen = set()
        doc_paths = []
        for p in sorted(
            list(doc_tag_dir.glob("*/*/table_graphs.json"))
            + list(fixtures_dir.glob("*/table_graphs.json"))
        ):
            if str(p) not in seen:
                seen.add(str(p))
                doc_paths.append(str(p))
    else:
        doc_paths = [a for a in sys.argv[1:] if not a.startswith("-")]

    if not doc_paths:
        print("Usage: python3 eval/run_corpus.py --all")
        print("   or: python3 eval/run_corpus.py <path1> <path2> ...")
        sys.exit(1)

    results = []
    for dp in doc_paths:
        print(f"Analyzing: {dp} ...", file=sys.stderr)
        try:
            r = analyze_document(dp, ontology_root)
            results.append(r)
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)

    print_comparison(results)

    # JSON output if requested
    if "--json" in sys.argv:
        json_out = {
            "documents": len(results),
            "results": results,
        }
        out_path = os.path.join(ontology_root, "eval", "corpus_results.json")
        with open(out_path, "w") as f:
            json.dump(json_out, f, indent=2)
        print(f"\nJSON written to: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
