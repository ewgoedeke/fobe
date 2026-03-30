#!/usr/bin/env python3
"""
prompt_generator.py -- Generate tagging prompts as markdown files for IDE sessions.

Instead of calling the API directly, this generates prompt files that can be
run in Claude Code / IDE sessions (free with Pro/Team), with a result parser
to apply the responses back.

Cost strategy:
  - Haiku for batch classification (200+ tables)
  - IDE sessions for interactive tagging (free)
  - Sonnet only for ambiguous cases

Usage:
    # Generate prompts for a document
    python3 eval/prompt_generator.py eval/fixtures/kapsch_2024/table_graphs.json

    # Apply results after running in IDE
    python3 eval/prompt_generator.py --apply eval/fixtures/kapsch_2024/tagging_results.json

    # Generate classification prompts (for batch API with Haiku)
    python3 eval/prompt_generator.py --classify eval/fixtures/kapsch_2024/table_graphs.json
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relationship_graph import load_concepts, ConceptMeta, _infer_context
from table_quality import is_processable


def _row_summary_md(row: dict, value_col_indices: set[int]) -> str:
    """One-line markdown row description."""
    idx = row.get("rowIdx", "?")
    label = (row.get("label") or "").strip()
    tag = ""
    if row.get("preTagged"):
        tag = f" **[{row['preTagged'].get('conceptId', '?')}]**"

    vals = []
    for cell in row.get("cells", []):
        if cell.get("colIdx") in value_col_indices:
            pv = cell.get("parsedValue")
            if pv is not None:
                vals.append(f"{pv:,.0f}")
            else:
                vals.append(cell.get("text", "").strip() or "-")

    indent = "  " * row.get("indentLevel", 0)
    val_str = " | ".join(vals[:4])  # max 4 value columns for readability
    return f"| {idx} | {indent}{label}{tag} | {val_str} |"


def generate_tagging_prompt(
    table: dict,
    concepts: list[ConceptMeta],
    doc_name: str = "",
) -> str:
    """Generate a markdown tagging prompt for one table.

    Designed to be copy-pasted into an IDE session.
    """
    ctx = table.get("metadata", {}).get("statementComponent", "UNKNOWN")
    table_id = table.get("tableId", "?")
    page = table.get("pageNo", "?")
    rows = table.get("rows", [])
    columns = table.get("columns", [])
    value_col_indices = {c["colIdx"] for c in columns if c.get("role") == "VALUE"}
    col_headers = [c.get("headerLabel", "") for c in columns if c.get("role") == "VALUE"]

    # Count untagged
    untagged = [r for r in rows if not r.get("preTagged")]
    if not untagged:
        return ""

    concept_lines = "\n".join(f"- `{m.concept_id}`: {m.label}" for m in concepts)

    # Build table in markdown
    header_line = "| Row | Label | " + " | ".join(col_headers[:4]) + " |"
    sep_line = "|-----|-------|" + "|".join(["------"] * min(len(col_headers), 4)) + "|"
    row_lines = [_row_summary_md(r, value_col_indices) for r in rows]

    return f"""### Table {table_id} (page {page}) — {ctx} — {len(untagged)}/{len(rows)} untagged

Concepts:
{concept_lines}

{header_line}
{sep_line}
{chr(10).join(row_lines)}
"""


def generate_document_prompts(
    tg_path: str,
    concept_index: dict[str, list[ConceptMeta]],
    gaap: str | None = None,
    output_dir: str | None = None,
) -> list[str]:
    """Generate prompt markdown files for all untagged tables in a document.

    Args:
        tg_path: Path to table_graphs.json.
        concept_index: Concept index from _build_concept_index.
        gaap: GAAP framework for filtering (IFRS, UGB, etc.).
        output_dir: Directory to write prompt files (default: alongside tg_path).

    Returns:
        List of generated prompt file paths.
    """
    with open(tg_path) as f:
        data = json.load(f)

    tables = data.get("tables", [])
    doc_name = Path(tg_path).parent.name

    if output_dir is None:
        output_dir = str(Path(tg_path).parent)

    prompt_dir = os.path.join(output_dir, "prompts")
    os.makedirs(prompt_dir, exist_ok=True)

    generated = []
    batch_parts = []
    batch_meta = []  # track (tableId, untagged_indices) for result parsing

    for table in tables:
        sc = table.get("metadata", {}).get("statementComponent")
        if not sc:
            continue
        if not is_processable(table):
            continue

        # Check for untagged rows
        has_untagged = any(
            not r.get("preTagged") and (r.get("label") or "").strip()
            for r in table.get("rows", [])
        )
        if not has_untagged:
            continue

        # Get concepts for this context
        raw_concepts = concept_index.get(sc, [])
        concepts = [m for m in raw_concepts if _infer_context(m.concept_id) == sc]

        # Apply GAAP filter
        if gaap and gaap.upper() == "IFRS":
            concepts = [c for c in concepts if ".UGB." not in c.concept_id]

        if not concepts:
            continue

        prompt = generate_tagging_prompt(table, concepts, doc_name)
        if prompt:
            batch_parts.append(prompt)
            untagged_indices = [
                r["rowIdx"] for r in table.get("rows", [])
                if not r.get("preTagged") and (r.get("label") or "").strip()
            ]
            batch_meta.append({
                "tableId": table["tableId"],
                "statementComponent": sc,
                "untagged_indices": untagged_indices,
            })

    if not batch_parts:
        return []

    # Write a single combined prompt file (easier to paste into IDE)
    combined_path = os.path.join(prompt_dir, f"{doc_name}_tagging.md")
    header = f"""# Tagging Prompts for {doc_name}

**Instructions**: Copy this entire file into a Claude Code / IDE session.
For each table, assign concept IDs to untagged rows.
Respond with a JSON array where each element corresponds to one table below.

**Total tables**: {len(batch_parts)}

---

"""
    footer = f"""
---

## Response format

Respond with a JSON array of {len(batch_parts)} objects, one per table in order:
```json
[
  {{"<rowIdx>": "<conceptId_or_null>", ...}},
  ...
]
```

Save your response to: `{os.path.join(prompt_dir, doc_name + '_results.json')}`
"""

    with open(combined_path, "w") as f:
        f.write(header + "\n---\n\n".join(batch_parts) + footer)

    # Write metadata for result parsing
    meta_path = os.path.join(prompt_dir, f"{doc_name}_meta.json")
    with open(meta_path, "w") as f:
        json.dump({"document": doc_name, "tables": batch_meta}, f, indent=2)

    generated.append(combined_path)
    return generated


def apply_results(
    tg_path: str,
    results_path: str,
    meta_path: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Apply tagging results from an IDE session back to table_graphs.json.

    Args:
        tg_path: Path to table_graphs.json.
        results_path: Path to JSON results file (array of {rowIdx: conceptId}).
        meta_path: Path to prompt metadata file.
        dry_run: If True, don't write changes.
        verbose: Print details.

    Returns:
        Summary dict with counts.
    """
    with open(tg_path) as f:
        data = json.load(f)
    with open(results_path) as f:
        results = json.load(f)
    with open(meta_path) as f:
        meta = json.load(f)

    tables_by_id = {t["tableId"]: t for t in data["tables"]}
    applied = 0
    skipped = 0

    for i, table_meta in enumerate(meta["tables"]):
        if i >= len(results):
            break
        table_id = table_meta["tableId"]
        table = tables_by_id.get(table_id)
        if not table:
            continue

        assignments = results[i]
        if not isinstance(assignments, dict):
            continue

        for row_idx_str, concept_id in assignments.items():
            if concept_id is None or concept_id == "null":
                continue
            row_idx = int(row_idx_str)
            for row in table.get("rows", []):
                if row.get("rowIdx") == row_idx:
                    if row.get("preTagged"):
                        skipped += 1
                        continue
                    row["preTagged"] = {
                        "conceptId": concept_id,
                        "method": "llm",
                        "confidence": 0.8,
                        "rule": "ide_session_tag",
                        "sourceRows": [],
                        "edge": "ide_session",
                    }
                    applied += 1
                    if verbose:
                        print(f"  {table_id} row {row_idx}: {concept_id}",
                              file=sys.stderr)
                    break

    if not dry_run and applied > 0:
        with open(tg_path, "w") as f:
            json.dump(data, f, indent=2, default=str)

    return {"applied": applied, "skipped": skipped}


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate/apply tagging prompts")
    parser.add_argument("path", help="table_graphs.json path")
    parser.add_argument("--apply", metavar="RESULTS",
                        help="Apply results JSON from IDE session")
    parser.add_argument("--meta", help="Metadata JSON path (for --apply)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if args.apply:
        meta_path = args.meta
        if not meta_path:
            # Guess meta path from results path
            meta_path = args.apply.replace("_results.json", "_meta.json")
        result = apply_results(args.path, args.apply, meta_path,
                               dry_run=args.dry_run, verbose=args.verbose)
        print(f"Applied {result['applied']} tags, skipped {result['skipped']}",
              file=sys.stderr)
    else:
        from llm_tagger import _build_concept_index
        concept_index = _build_concept_index(repo_root)

        # Try to get GAAP from meta.json
        gaap = None
        meta_json = Path(args.path).parent / "meta.json"
        if meta_json.exists():
            with open(meta_json) as f:
                gaap = json.load(f).get("gaap")

        paths = generate_document_prompts(
            args.path, concept_index, gaap=gaap, verbose=args.verbose)
        for p in paths:
            print(f"Generated: {p}", file=sys.stderr)


if __name__ == "__main__":
    main()
