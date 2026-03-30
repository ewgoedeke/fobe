#!/usr/bin/env python3
"""
review_cli.py -- CLI tool for HITL classification review.

Commands:
  generate <table_graphs.json>   Run classification gate + generate review_needed.json
  inspect <fixture_dir>          Pretty-print review manifest (page-ordered table view)
  template <fixture_dir>         Generate starter human_review.json from review_needed.json
  apply <fixture_dir>            Apply human_review.json to table_graphs.json
  status [--all]                 Show which fixtures need review / have review / are stale
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from human_review import (
    generate_review_manifest,
    generate_template,
    load_human_review,
    apply_overrides,
    is_review_stale,
    write_review_manifest,
    write_human_review,
)


def cmd_generate(args):
    """Run classification gate check and generate review_needed.json."""
    from classify_tables import classify_document, _detect_toc
    from pipeline import GateResult
    from stages import Stage2_StructureExtraction, PRIMARY_STATEMENTS

    tg_path = args.path
    if not os.path.isfile(tg_path):
        print(f"Error: {tg_path} not found", file=sys.stderr)
        sys.exit(1)

    fixture_dir = str(Path(tg_path).parent)
    doc_name = Path(tg_path).parent.name

    # Run classification (dry run — don't modify file)
    print(f"Classifying {doc_name}...", file=sys.stderr)
    classify_document(tg_path, dry_run=True, verbose=args.verbose)

    # Load tables
    with open(tg_path) as f:
        tables = json.load(f).get("tables", [])

    # Run gate check to get findings
    from collections import Counter
    classified_types = Counter()
    for table in tables:
        sc = table.get("metadata", {}).get("statementComponent")
        if sc:
            classified_types[sc] += 1

    primary_types = {t for t in classified_types if t in PRIMARY_STATEMENTS}
    primary_counts = {t: classified_types[t] for t in PRIMARY_STATEMENTS
                      if classified_types[t] > 0}
    max_per_primary = 8
    inflated = {t: n for t, n in primary_counts.items() if n > max_per_primary}

    findings = []
    if len(primary_types) < 1:
        findings.append({"type": "toc_unresolved",
                         "detail": f"Only {len(primary_types)} primary types"})
    for st, count in inflated.items():
        findings.append({"type": "inflated_primary",
                         "detail": f"{count} tables classified as {st} (max {max_per_primary})"})

    gate_result = GateResult(
        passed=not findings,
        stage="stage2",
        findings=findings,
        metrics={"primary_counts": primary_counts},
    )

    # Get TOC info
    toc_info = None
    try:
        toc_info = _detect_toc(tables)
    except Exception:
        pass

    manifest = generate_review_manifest(tables, gate_result, toc_info, doc_name)
    path = write_review_manifest(fixture_dir, manifest)

    flagged = manifest["summary"]["flagged_count"]
    total = manifest["summary"]["total_tables"]
    print(f"Generated {path}")
    print(f"  {total} tables, {flagged} flagged")
    if manifest["summary"].get("suggested_action"):
        print(f"  Suggestion: {manifest['summary']['suggested_action']}")


def cmd_inspect(args):
    """Pretty-print review manifest with page-ordered table view."""
    fixture_dir = _resolve_fixture_dir(args.path)
    manifest_path = os.path.join(fixture_dir, "review_needed.json")

    if not os.path.isfile(manifest_path):
        print(f"No review_needed.json in {fixture_dir}", file=sys.stderr)
        print("Run: python3 eval/review_cli.py generate "
              f"{os.path.join(fixture_dir, 'table_graphs.json')}",
              file=sys.stderr)
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    doc = manifest.get("document", "?")
    summary = manifest.get("summary", {})
    total = summary.get("total_tables", 0)
    flagged = summary.get("flagged_count", 0)

    print(f"\n{doc} — {total} tables, {flagged} flagged")
    print(f"Generated: {manifest.get('generated_at', '?')}")

    # TOC info
    toc = manifest.get("toc_detected")
    if toc and toc.get("page_map"):
        pm = toc["page_map"]
        toc_str = ", ".join(f"{p}→{t}" for p, t in sorted(pm.items(),
                            key=lambda x: int(x[0])))
        print(f"TOC: detected ({toc_str})")
    else:
        print("TOC: not detected")

    # Gate findings
    for f in manifest.get("gate_findings", []):
        print(f"  FINDING: [{f.get('type')}] {f.get('detail', '')}")

    if summary.get("suggested_action"):
        print(f"  Suggestion: {summary['suggested_action']}")

    # Human review status
    review_path = os.path.join(fixture_dir, "human_review.json")
    if os.path.isfile(review_path):
        print(f"  human_review.json: EXISTS")
    else:
        print(f"  human_review.json: not found")

    # Type breakdown
    print(f"\nClassification breakdown:")
    for typ, count in sorted(summary.get("by_type", {}).items(),
                             key=lambda x: -x[1]):
        marker = " <<<" if count > 8 and typ in ("PNL", "SFP", "OCI", "CFS", "SOCIE") else ""
        print(f"  {typ:>20}: {count}{marker}")

    # Page-ordered table listing
    print(f"\n{'Page':>4}  {'TableId':<12}  {'Classification':<18}  "
          f"{'Method':<14}  {'Conf':<6}  {'Rows':>4}  First Labels")
    print("─" * 110)

    for page_entry in manifest.get("page_index", []):
        page = page_entry["page"]
        for t in page_entry.get("tables", []):
            sc = t.get("classification") or "-"
            method = t.get("method", "-")
            conf = t.get("confidence", "-")
            rows = t.get("row_count", 0)
            labels = t.get("first_labels", [])
            label_str = labels[0] if labels else "(no labels)"
            # Truncate classification for display
            sc_display = sc[:18] if len(sc) > 18 else sc

            cols = t.get("col_headers", [])
            col_str = f" | cols: {', '.join(cols[:3])}" if cols else ""

            flag = " *" if t.get("flagged") else ""

            print(f"{page:>4}  {t['tableId']:<12}  {sc_display:<18}  "
                  f"{method:<14}  {conf:<6}  {rows:>4}  "
                  f"{label_str[:50]}{col_str[:30]}{flag}")

    print(f"\n* = flagged for review")
    print(f"Total: {total} tables, {flagged} flagged")


def cmd_template(args):
    """Generate a starter human_review.json from review_needed.json."""
    fixture_dir = _resolve_fixture_dir(args.path)
    manifest_path = os.path.join(fixture_dir, "review_needed.json")
    review_path = os.path.join(fixture_dir, "human_review.json")

    if not os.path.isfile(manifest_path):
        print(f"No review_needed.json in {fixture_dir}", file=sys.stderr)
        print("Run 'generate' first.", file=sys.stderr)
        sys.exit(1)

    if os.path.isfile(review_path) and not args.force:
        print(f"human_review.json already exists at {review_path}",
              file=sys.stderr)
        print("Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    template = generate_template(manifest)
    path = write_human_review(fixture_dir, template)

    n_tables = len(template.get("overrides", {}).get("tables", {}))
    n_ranges = len(template.get("overrides", {}).get("page_ranges", []))
    print(f"Generated {path}")
    print(f"  {n_tables} per-table overrides, {n_ranges} page ranges suggested")
    print(f"  Edit the file, then re-run the pipeline to apply.")


def cmd_apply(args):
    """Apply human_review.json to table_graphs.json and report results."""
    fixture_dir = _resolve_fixture_dir(args.path)
    tg_path = os.path.join(fixture_dir, "table_graphs.json")

    if not os.path.isfile(tg_path):
        print(f"No table_graphs.json in {fixture_dir}", file=sys.stderr)
        sys.exit(1)

    review = load_human_review(fixture_dir)
    if not review:
        print(f"No human_review.json in {fixture_dir}", file=sys.stderr)
        sys.exit(1)

    with open(tg_path) as f:
        data = json.load(f)
    tables = data.get("tables", [])

    stale, missing = is_review_stale(review, tables)
    if stale:
        print(f"WARNING: Review references missing tableIds: {missing}",
              file=sys.stderr)

    tables, stats = apply_overrides(tables, review)
    data["tables"] = tables

    if not args.dry_run:
        with open(tg_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"Applied overrides to {tg_path}")
    else:
        print(f"[DRY RUN] Would apply overrides to {tg_path}")

    print(f"  Stats: {json.dumps(stats, indent=2)}")


def cmd_status(args):
    """Show review status across all fixtures."""
    ontology_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fixtures_dir = os.path.join(ontology_root, "eval", "fixtures")

    if not os.path.isdir(fixtures_dir):
        print(f"Fixtures directory not found: {fixtures_dir}", file=sys.stderr)
        sys.exit(1)

    needs_review = []
    has_review = []
    stale_review = []
    no_manifest = []

    for name in sorted(os.listdir(fixtures_dir)):
        fixture_dir = os.path.join(fixtures_dir, name)
        tg_path = os.path.join(fixture_dir, "table_graphs.json")
        manifest_path = os.path.join(fixture_dir, "review_needed.json")
        review_path = os.path.join(fixture_dir, "human_review.json")

        if not os.path.isfile(tg_path):
            continue

        has_manifest = os.path.isfile(manifest_path)
        has_human = os.path.isfile(review_path)

        if has_human:
            # Check staleness
            with open(tg_path) as f:
                tables = json.load(f).get("tables", [])
            review = load_human_review(fixture_dir)
            if review:
                is_stale, _ = is_review_stale(review, tables)
                if is_stale:
                    stale_review.append(name)
                else:
                    has_review.append(name)
        elif has_manifest:
            needs_review.append(name)
        else:
            no_manifest.append(name)

    print(f"Review status ({len(needs_review) + len(has_review) + len(stale_review) + len(no_manifest)} fixtures):\n")

    if needs_review:
        print(f"  NEEDS REVIEW ({len(needs_review)}):")
        for n in needs_review:
            print(f"    {n}")

    if has_review:
        print(f"\n  HAS REVIEW ({len(has_review)}):")
        for n in has_review:
            print(f"    {n}")

    if stale_review:
        print(f"\n  STALE REVIEW ({len(stale_review)}):")
        for n in stale_review:
            print(f"    {n}  (human_review.json references missing tableIds)")

    if no_manifest:
        print(f"\n  NO MANIFEST ({len(no_manifest)}):")
        for n in no_manifest:
            print(f"    {n}")


def _resolve_fixture_dir(path: str) -> str:
    """Resolve a path to a fixture directory."""
    if os.path.isdir(path):
        return path
    if os.path.isfile(path):
        return str(Path(path).parent)
    # Try as fixture name
    ontology_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(ontology_root, "eval", "fixtures", path)
    if os.path.isdir(candidate):
        return candidate
    print(f"Cannot resolve fixture directory: {path}", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="HITL classification review tool")
    sub = parser.add_subparsers(dest="command")

    p_gen = sub.add_parser("generate",
                           help="Generate review_needed.json")
    p_gen.add_argument("path", help="Path to table_graphs.json")
    p_gen.add_argument("--verbose", "-v", action="store_true")

    p_insp = sub.add_parser("inspect",
                            help="Pretty-print review manifest")
    p_insp.add_argument("path", help="Fixture directory or path")

    p_tmpl = sub.add_parser("template",
                            help="Generate starter human_review.json")
    p_tmpl.add_argument("path", help="Fixture directory or path")
    p_tmpl.add_argument("--force", action="store_true",
                        help="Overwrite existing human_review.json")

    p_apply = sub.add_parser("apply",
                             help="Apply human_review.json to table_graphs.json")
    p_apply.add_argument("path", help="Fixture directory or path")
    p_apply.add_argument("--dry-run", action="store_true",
                         help="Show what would be applied without writing")

    p_status = sub.add_parser("status",
                              help="Show review status across fixtures")
    p_status.add_argument("--all", action="store_true",
                          help="Include fixtures without manifests")

    args = parser.parse_args()

    if args.command == "generate":
        cmd_generate(args)
    elif args.command == "inspect":
        cmd_inspect(args)
    elif args.command == "template":
        cmd_template(args)
    elif args.command == "apply":
        cmd_apply(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
