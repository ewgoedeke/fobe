#!/usr/bin/env python3
"""
llm_tagger.py — LLM-assisted concept tagging for financial table rows.

Pipeline position:
  classify_tables.py → structural_inference.py → llm_tagger.py → check_consistency.py

For each table with a known statementComponent, filters the concept ontology to
valid concepts for that context, builds a structured prompt, calls Claude Sonnet,
and writes preTagged entries for newly assigned rows.

Usage:
    python3 eval/llm_tagger.py <table_graphs.json> [--dry-run] [--verbose] [--model sonnet]
    python3 eval/llm_tagger.py --all [--concurrency 5] [--dry-run] [--verbose]
"""

import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import yaml

# Add parent dir to path for sibling imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relationship_graph import load_concepts, ConceptMeta, _infer_context
from reference_graph import (
    build_reference_graph, DocumentRefGraph, has_note_column, parse_label,
)


# ── Pre-filter for untaggable labels ──────────────────────────────────────────

_UNTAGGABLE_PATTERNS = [
    re.compile(r"^\s*$"),                                  # empty / whitespace-only
    re.compile(r"^\d{1,2}[./]\d{1,2}[./]\d{2,4}$"),       # dates like 31.12.2024
    re.compile(r"^\d{4}$"),                                # bare year like 2024
    re.compile(r"^[\d.,\s%()+-]+$"),                       # numeric-only (with formatting chars)
    re.compile(r"^[(\[]?\d+[)\]]?$"),                      # note references like (1) or [3]
    re.compile(r"^note\s+\d", re.IGNORECASE),              # "Note 12", "note 3.2"
    re.compile(r"^(IAS|IFRS)\s*\d", re.IGNORECASE),       # IAS/IFRS references
    re.compile(r"^in\s+(EUR|USD|TEUR|TUSD|Mio|T€)", re.IGNORECASE),  # unit headers
]


def _is_untaggable_label(label: str) -> bool:
    """Return True if the row label is structurally untaggable (no concept match possible)."""
    text = label.strip()
    if not text:
        return True
    return any(p.search(text) for p in _UNTAGGABLE_PATTERNS)


# ── Constants ──────────────────────────────────────────────────────────────────

MODEL = "claude-sonnet-4-20250514"
MODEL_SHORT = "sonnet"
DEFAULT_CONCURRENCY = 5
SMALL_TABLE_THRESHOLD = 30   # rows: tables with ≤ this many rows are batched
SMALL_TABLE_BATCH = 3        # how many small tables per API call
MAX_PROMPT_CHARS = 8000      # split batch further if prompt exceeds this
CONFIDENCE = 0.8
METHOD = "llm"
RULE = "sonnet_tag"


# ── GAAP filtering ──────────────────────────────────────────────────────────────

def _filter_by_gaap(concepts: list[ConceptMeta], gaap: str) -> list[ConceptMeta]:
    """Filter concepts by GAAP framework.

    - IFRS documents: exclude UGB-specific concepts (*.UGB.*)
    - UGB documents: include everything (UGB-specific + shared base concepts)
    """
    if gaap == "IFRS":
        return [c for c in concepts if ".UGB." not in c.concept_id]
    # For UGB and other frameworks, include all concepts
    return concepts


# ── Concept index ──────────────────────────────────────────────────────────────

def _build_concept_index(repo_root: str) -> dict[str, list[ConceptMeta]]:
    """Load all concepts and group them by each valid_context they belong to.

    Returns: dict mapping context string → list of ConceptMeta
    """
    all_concepts = load_concepts(repo_root)
    index: dict[str, list[ConceptMeta]] = defaultdict(list)
    for meta in all_concepts.values():
        for ctx in meta.valid_contexts:
            index[ctx].append(meta)
    return dict(index)


# ── Prompt building ────────────────────────────────────────────────────────────

def _row_summary(
    row: dict,
    value_col_indices: set[int],
    note_context: Optional[str] = None,
) -> str:
    """Produce a one-line description of a row for the prompt."""
    label = (row.get("label", "").strip() or "(no label)")[:80]
    row_type = row.get("rowType", "DATA")
    pre = row.get("preTagged")

    # Pre-filter: mark structurally untaggable rows so LLM skips them
    if not pre and _is_untaggable_label(row.get("label", "")):
        tagged_note = "[SKIP]"
    elif pre:
        tagged_note = f"[already tagged: {pre['conceptId']}]"
    else:
        tagged_note = "[UNTAGGED]"

    # Check if this row has any numeric values
    cells = row.get("cells", [])
    has_values = any(
        c.get("parsedValue") is not None and c.get("colIdx") in value_col_indices
        for c in cells
    )

    row_idx = row.get("rowIdx", "?")
    type_note = "" if row_type == "DATA" else f", {row_type}"
    value_note = ", has values" if has_values else ", no values"
    note_hint = f", note→{note_context}" if note_context else ""

    return f"  row {row_idx}: \"{label}\" [{tagged_note}{type_note}{value_note}{note_hint}]"


def _build_table_prompt(
    table: dict,
    concepts: list[ConceptMeta],
    table_idx_in_batch: int = 0,
    ref_graph: Optional[DocumentRefGraph] = None,
) -> str:
    """Build the LLM prompt for a single table."""
    ctx = table.get("metadata", {}).get("statementComponent", "UNKNOWN")
    table_id = table.get("tableId", "?")
    page = table.get("pageNo", "?")

    columns = table.get("columns", [])
    value_col_indices = {c["colIdx"] for c in columns if c.get("role") == "VALUE"}

    # Build note column lookup for this table
    note_col_indices = set()
    for col in columns:
        if col.get("role") == "NOTES":
            note_col_indices.add(col["colIdx"])
        elif col.get("headerLabel", "").lower().strip() in (
            "note", "notes", "anhang", "anmerkung", "anmerkungen",
        ):
            note_col_indices.add(col["colIdx"])

    rows = table.get("rows", [])
    untagged_row_indices = [
        r.get("rowIdx") for r in rows
        if not r.get("preTagged") and not _is_untaggable_label(r.get("label", ""))
    ]

    concept_lines = "\n".join(
        f"  {m.concept_id}: {m.label}" for m in concepts
    )

    # Build row lines with note context hints
    row_lines_list = []
    for r in rows:
        note_ctx = None
        if ref_graph and note_col_indices:
            for cell in r.get("cells", []):
                if cell.get("colIdx") in note_col_indices:
                    note_text = cell.get("text", "").strip()
                    if note_text:
                        m = re.match(r"(\d+)", note_text)
                        if m:
                            note_ctx = ref_graph.context_for_note(int(m.group(1)))
                    break
        row_lines_list.append(_row_summary(r, value_col_indices, note_context=note_ctx))
    row_lines = "\n".join(row_lines_list)

    return (
        f"=== Table {table_idx_in_batch} (tableId={table_id}, page={page}) ===\n"
        f"Context: {ctx}\n\n"
        f"Valid concepts:\n{concept_lines}\n\n"
        f"Table rows:\n{row_lines}\n\n"
        f"For each UNTAGGED row, assign the best matching concept ID or null.\n"
        f"Rules:\n"
        f"  1. Only use concept IDs from the Valid concepts list above.\n"
        f"  2. Return null for axis members (country names, segment names, age brackets).\n"
        f"  3. Return null for generic labels (\"total\", \"other\", \"net\") unless the context makes it unambiguous.\n"
        f"  4. Return null for non-financial content (headers, page references, audit text).\n"
        f"  5. Return null for rows with no values that are section headers.\n"
        f"Untagged row indices: {untagged_row_indices}\n"
        f"Respond with ONLY a JSON object mapping row index (as string) to concept ID or null:\n"
        f"{{\"<rowIdx>\": \"<conceptId_or_null>\", ...}}"
    )


def _build_batch_prompt(
    tables_and_concepts: list[tuple[dict, list[ConceptMeta]]],
    ref_graph: Optional[DocumentRefGraph] = None,
) -> str:
    """Build a combined prompt for multiple small tables."""
    parts = []
    for i, (table, concepts) in enumerate(tables_and_concepts):
        parts.append(_build_table_prompt(table, concepts, table_idx_in_batch=i, ref_graph=ref_graph))

    n = len(tables_and_concepts)
    return (
        "You are tagging rows in financial statement tables.\n"
        "For each table below, assign concept IDs to UNTAGGED rows.\n\n"
        + "\n\n".join(parts)
        + f"\n\nRespond with ONLY a JSON array of {n} objects (one per table, in order). "
        "Each object maps row index strings to concept IDs or null.\n"
        "Example for 2 tables: [{\"3\": \"DISC.PPE.COST_ADDITIONS\"}, {\"1\": null, \"4\": \"DISC.TAX.CURRENT\"}]"
    )


def _build_single_prompt(
    table: dict,
    concepts: list[ConceptMeta],
    ref_graph: Optional[DocumentRefGraph] = None,
) -> str:
    """Build a prompt for a single large table."""
    return (
        "You are tagging rows in a financial statement table.\n\n"
        + _build_table_prompt(table, concepts, table_idx_in_batch=0, ref_graph=ref_graph)
        + "\n\nRespond with ONLY a JSON object mapping row index strings to concept IDs or null."
    )


# ── LLM call ──────────────────────────────────────────────────────────────────

def _call_llm(prompt: str, model: str = MODEL_SHORT, verbose: bool = False) -> Optional[str]:
    """Call Claude via anthropic SDK (preferred) or subprocess CLI fallback."""
    # Try anthropic SDK first
    try:
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        if verbose:
            print(f"  [llm] SDK error: {e}, falling back to CLI")

    # Fallback: subprocess claude CLI
    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--model", model, "--output-format", "text"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0 and verbose:
            print(f"  [llm] CLI stderr: {result.stderr[:200]}")
        return result.stdout.strip()
    except Exception as e:
        if verbose:
            print(f"  [llm] CLI error: {e}")
        return None


def _extract_json(text: str) -> Optional[str]:
    """Strip markdown fences and return the inner JSON string."""
    if not text:
        return None
    text = text.strip()
    if "```" in text:
        # Extract content between first ``` pair
        parts = text.split("```")
        if len(parts) >= 2:
            inner = parts[1]
            if inner.startswith("json"):
                inner = inner[4:]
            text = inner.strip()
    return text


def _parse_single_response(
    text: str,
    valid_concept_ids: set[str],
    verbose: bool = False,
) -> dict[int, Optional[str]]:
    """Parse a single-table JSON response. Returns {rowIdx: conceptId|None}."""
    raw = _extract_json(text)
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            return {}
        result = {}
        for k, v in obj.items():
            try:
                idx = int(k)
            except ValueError:
                continue
            if v is None or v == "null":
                result[idx] = None
            elif v in valid_concept_ids:
                result[idx] = v
            else:
                if verbose:
                    print(f"  [llm] Invalid concept ID ignored: {v!r}")
                result[idx] = None
        return result
    except json.JSONDecodeError as e:
        if verbose:
            print(f"  [llm] JSON parse error: {e} | text: {raw[:200]}")
        return {}


def _parse_batch_response(
    text: str,
    n_tables: int,
    valid_concept_ids: set[str],
    verbose: bool = False,
) -> list[dict[int, Optional[str]]]:
    """Parse a multi-table JSON array response. Returns list of {rowIdx: conceptId|None}."""
    raw = _extract_json(text)
    if not raw:
        return [{} for _ in range(n_tables)]
    try:
        arr = json.loads(raw)
        if not isinstance(arr, list):
            # Try to parse as single object — maybe model returned one table's result
            if isinstance(arr, dict):
                arr = [arr]
            else:
                return [{} for _ in range(n_tables)]

        results = []
        for i in range(n_tables):
            if i < len(arr):
                obj = arr[i]
                if not isinstance(obj, dict):
                    results.append({})
                    continue
                row_map = {}
                for k, v in obj.items():
                    try:
                        idx = int(k)
                    except ValueError:
                        continue
                    if v is None or v == "null":
                        row_map[idx] = None
                    elif v in valid_concept_ids:
                        row_map[idx] = v
                    else:
                        if verbose:
                            print(f"  [llm] Invalid concept ID ignored: {v!r}")
                        row_map[idx] = None
                results.append(row_map)
            else:
                results.append({})
        return results
    except json.JSONDecodeError as e:
        if verbose:
            print(f"  [llm] Batch JSON parse error: {e} | text: {raw[:200]}")
        return [{} for _ in range(n_tables)]


# ── Apply tags ────────────────────────────────────────────────────────────────

def _apply_tags(
    table: dict,
    row_map: dict[int, Optional[str]],
    dry_run: bool = False,
) -> int:
    """Write preTagged entries to rows in the table. Returns count of tags applied."""
    count = 0
    rows = table.get("rows", [])
    for row in rows:
        row_idx = row.get("rowIdx")
        if row_idx not in row_map:
            continue
        concept_id = row_map[row_idx]
        if concept_id is None:
            continue
        # Don't overwrite existing tags
        if row.get("preTagged"):
            continue
        # Don't tag rows with untaggable labels (guard against LLM hallucination)
        if _is_untaggable_label(row.get("label", "")):
            continue
        if not dry_run:
            row["preTagged"] = {
                "conceptId": concept_id,
                "method": METHOD,
                "confidence": CONFIDENCE,
                "rule": RULE,
                "model": MODEL,
            }
        count += 1
    return count


# ── Table filtering ────────────────────────────────────────────────────────────

def _has_untagged_value_rows(table: dict) -> bool:
    """Return True if this table has any taggable untagged rows with numeric values."""
    columns = table.get("columns", [])
    value_col_indices = {c["colIdx"] for c in columns if c.get("role") == "VALUE"}
    if not value_col_indices:
        return False
    for row in table.get("rows", []):
        if row.get("preTagged"):
            continue
        if _is_untaggable_label(row.get("label", "")):
            continue
        cells = row.get("cells", [])
        has_values = any(
            c.get("parsedValue") is not None and c.get("colIdx") in value_col_indices
            for c in cells
        )
        if has_values:
            return True
    return False


# ── Document tagging ──────────────────────────────────────────────────────────

def tag_document(
    tg_path: str,
    concept_index: dict[str, list[ConceptMeta]],
    dry_run: bool = False,
    verbose: bool = False,
    model: str = MODEL_SHORT,
    gaap: str | None = None,
) -> dict:
    """Tag all eligible tables in a table_graphs.json file.

    Args:
        gaap: Document GAAP framework ("IFRS", "UGB", etc.). When set,
              filters concepts by GAAP: IFRS docs exclude UGB-specific
              concepts (*.UGB.*), UGB docs exclude IFRS-only concepts.

    Returns a stats dict: {tables_processed, api_calls, tags_added}
    """
    with open(tg_path) as f:
        data = json.load(f)

    tables = data.get("tables", [])
    stats = {"tables_processed": 0, "api_calls": 0, "tags_added": 0}

    # Build reference graph for note context
    ref_graph = build_reference_graph(tables)

    # Separate tables into small (batched) and large (individual)
    eligible_small: list[tuple[dict, list[ConceptMeta]]] = []  # (table, concepts)
    eligible_large: list[tuple[dict, list[ConceptMeta]]] = []

    for table in tables:
        ctx = table.get("metadata", {}).get("statementComponent")
        if not ctx:
            continue
        if not _has_untagged_value_rows(table):
            continue
        # Filter to concepts whose primary context matches this table's context,
        # avoiding cross-context pollution (e.g. a DISC.PPE concept appearing in SFP)
        raw_concepts = concept_index.get(ctx, [])
        concepts = [
            m for m in raw_concepts
            if _infer_context(m.concept_id) == ctx
        ]
        # GAAP filter: exclude concepts from wrong framework (Issue #42)
        if gaap:
            concepts = _filter_by_gaap(concepts, gaap)
        if not concepts:
            if verbose:
                print(f"  [skip] No concepts for context {ctx} (tableId={table.get('tableId')})")
            continue

        n_rows = len(table.get("rows", []))
        if n_rows <= SMALL_TABLE_THRESHOLD:
            eligible_small.append((table, concepts))
        else:
            eligible_large.append((table, concepts))

    if verbose:
        print(f"  Eligible: {len(eligible_small)} small, {len(eligible_large)} large tables")

    # Process small tables in batches, splitting if prompt gets too large
    batch_num = 0
    pending = list(eligible_small)
    while pending:
        # Build a batch up to SMALL_TABLE_BATCH, but split further if prompt is too long
        batch = pending[:SMALL_TABLE_BATCH]
        pending = pending[SMALL_TABLE_BATCH:]

        # If the batch prompt is too large, shrink it
        while len(batch) > 1:
            trial_prompt = _build_batch_prompt(batch, ref_graph=ref_graph)
            if len(trial_prompt) <= MAX_PROMPT_CHARS:
                break
            # Put last table back and retry with smaller batch
            pending.insert(0, batch.pop())

        valid_ids: set[str] = set()
        for _, concepts in batch:
            valid_ids.update(m.concept_id for m in concepts)

        batch_num += 1
        if len(batch) == 1:
            # Degenerate — use single-table path
            table, concepts = batch[0]
            valid_ids = {m.concept_id for m in concepts}
            prompt = _build_single_prompt(table, concepts, ref_graph=ref_graph)
            if verbose:
                ctx = table.get("metadata", {}).get("statementComponent")
                print(f"  [llm] Single (oversized batch) table: {table.get('tableId')} (ctx={ctx})")
            text = _call_llm(prompt, model=model, verbose=verbose)
            stats["api_calls"] += 1
            row_map = _parse_single_response(text or "", valid_ids, verbose=verbose)
            n = _apply_tags(table, row_map, dry_run=dry_run)
            stats["tags_added"] += n
            stats["tables_processed"] += 1
            if verbose and n:
                print(f"    Tagged {n} rows in {table.get('tableId')}")
            continue

        prompt = _build_batch_prompt(batch, ref_graph=ref_graph)
        if verbose:
            ctx_list = [t.get("metadata", {}).get("statementComponent") for t, _ in batch]
            print(f"  [llm] Batch {batch_num}: {len(batch)} tables, contexts={ctx_list}")

        text = _call_llm(prompt, model=model, verbose=verbose)
        stats["api_calls"] += 1

        row_maps = _parse_batch_response(text or "", len(batch), valid_ids, verbose=verbose)
        for (table, _), row_map in zip(batch, row_maps):
            n = _apply_tags(table, row_map, dry_run=dry_run)
            stats["tags_added"] += n
            stats["tables_processed"] += 1
            if verbose and n:
                print(f"    Tagged {n} rows in {table.get('tableId')}")

    # Process large tables individually
    for table, concepts in eligible_large:
        valid_ids = {m.concept_id for m in concepts}
        prompt = _build_single_prompt(table, concepts, ref_graph=ref_graph)
        ctx = table.get("metadata", {}).get("statementComponent")
        if verbose:
            print(f"  [llm] Single large table: {table.get('tableId')} (ctx={ctx}, rows={len(table.get('rows', []))})")

        text = _call_llm(prompt, model=model, verbose=verbose)
        stats["api_calls"] += 1

        row_map = _parse_single_response(text or "", valid_ids, verbose=verbose)
        n = _apply_tags(table, row_map, dry_run=dry_run)
        stats["tags_added"] += n
        stats["tables_processed"] += 1
        if verbose and n:
            print(f"    Tagged {n} rows in {table.get('tableId')}")

    if not dry_run and (stats["tags_added"] > 0):
        with open(tg_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return stats


# ── Strip bad tags ────────────────────────────────────────────────────────────

def _strip_bad_tags(
    tg_path: str,
    dry_run: bool = False,
    verbose: bool = False,
) -> int:
    """Remove LLM-generated preTagged entries on rows with untaggable labels.

    Returns the number of tags stripped.
    """
    with open(tg_path) as f:
        data = json.load(f)

    stripped = 0
    for table in data.get("tables", []):
        for row in table.get("rows", []):
            pre = row.get("preTagged")
            if not pre:
                continue
            if pre.get("method") != METHOD:
                continue
            if _is_untaggable_label(row.get("label", "")):
                stripped += 1
                if verbose:
                    print(f"  [strip] row {row.get('rowIdx')} label={row.get('label', '')!r} "
                          f"concept={pre.get('conceptId')} (table={table.get('tableId')})")
                if not dry_run:
                    del row["preTagged"]

    if not dry_run and stripped > 0:
        with open(tg_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return stripped


# ── Coverage reporting ────────────────────────────────────────────────────────

def _count_coverage(tg_path: str) -> tuple[int, int]:
    """Return (tagged_value_rows, total_value_rows) for a table_graphs.json."""
    with open(tg_path) as f:
        data = json.load(f)
    tagged = 0
    total = 0
    for table in data.get("tables", []):
        ctx = table.get("metadata", {}).get("statementComponent")
        if not ctx:
            continue
        columns = table.get("columns", [])
        value_col_indices = {c["colIdx"] for c in columns if c.get("role") == "VALUE"}
        if not value_col_indices:
            continue
        for row in table.get("rows", []):
            cells = row.get("cells", [])
            has_values = any(
                c.get("parsedValue") is not None and c.get("colIdx") in value_col_indices
                for c in cells
            )
            if has_values:
                total += 1
                if row.get("preTagged"):
                    tagged += 1
    return tagged, total


# ── Main ──────────────────────────────────────────────────────────────────────

def _find_repo_root(start: str) -> str:
    """Walk up from start dir to find the repo root (has concepts/ dir)."""
    p = Path(start).resolve()
    for candidate in [p, p.parent, p.parent.parent]:
        if (candidate / "concepts").is_dir():
            return str(candidate)
    raise RuntimeError(f"Could not find repo root (no concepts/ dir) starting from {start}")


def _find_all_fixtures(repo_root: str) -> list[str]:
    """Find all table_graphs.json files under eval/fixtures/."""
    fixtures_dir = Path(repo_root) / "eval" / "fixtures"
    return sorted(str(p) for p in fixtures_dir.glob("*/table_graphs.json"))


def main():
    import argparse
    import concurrent.futures

    parser = argparse.ArgumentParser(description="LLM-assisted row tagging for financial tables")
    parser.add_argument("path", nargs="?", help="Path to table_graphs.json")
    parser.add_argument("--all", action="store_true", dest="run_all",
                        help="Run on all fixtures under eval/fixtures/")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't write changes back to disk")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print progress details")
    parser.add_argument("--model", default=MODEL_SHORT,
                        help=f"Claude model alias (default: {MODEL_SHORT})")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"Max parallel workers for --all (default: {DEFAULT_CONCURRENCY})")
    parser.add_argument("--strip-bad", action="store_true",
                        help="Remove existing LLM tags on rows with untaggable labels")
    args = parser.parse_args()

    if not args.path and not args.run_all and not args.strip_bad:
        parser.print_help()
        sys.exit(1)

    # Find repo root relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = _find_repo_root(script_dir)

    if args.verbose:
        print(f"Repo root: {repo_root}")

    # Handle --strip-bad mode
    if args.strip_bad:
        if args.path:
            paths = [args.path]
        else:
            paths = _find_all_fixtures(repo_root)
        total_stripped = 0
        for p in paths:
            fixture_name = Path(p).parent.name
            n = _strip_bad_tags(p, dry_run=args.dry_run, verbose=args.verbose)
            if n > 0:
                print(f"  {fixture_name}: stripped {n} bad tags")
            total_stripped += n
        print(f"\nTotal: {total_stripped} bad tags {'would be ' if args.dry_run else ''}stripped")
        if args.dry_run:
            print("(dry run — no changes written)")
        sys.exit(0)

    concept_index = _build_concept_index(repo_root)
    if args.verbose:
        total_concepts = sum(len(v) for v in concept_index.values())
        print(f"Loaded {total_concepts} concept entries across {len(concept_index)} contexts")

    if args.run_all:
        paths = _find_all_fixtures(repo_root)
        print(f"Found {len(paths)} fixtures")

        total_stats = {"tables_processed": 0, "api_calls": 0, "tags_added": 0}
        total_tagged_before = 0
        total_rows_before = 0

        # Count coverage before
        for p in paths:
            t, r = _count_coverage(p)
            total_tagged_before += t
            total_rows_before += r

        def process_one(tg_path: str) -> dict:
            fixture_name = Path(tg_path).parent.name
            try:
                s = tag_document(
                    tg_path,
                    concept_index,
                    dry_run=args.dry_run,
                    verbose=args.verbose,
                    model=args.model,
                )
                print(f"  {fixture_name}: +{s['tags_added']} tags, {s['api_calls']} calls", flush=True)
                return s
            except Exception as e:
                print(f"  {fixture_name}: ERROR — {e}", flush=True)
                return {"tables_processed": 0, "api_calls": 0, "tags_added": 0}

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {pool.submit(process_one, p): p for p in paths}
            for fut in concurrent.futures.as_completed(futures):
                s = fut.result()
                for k in total_stats:
                    total_stats[k] += s[k]

        # Count coverage after
        total_tagged_after = 0
        total_rows_after = 0
        for p in paths:
            t, r = _count_coverage(p)
            total_tagged_after += t
            total_rows_after += r

        before_pct = 100 * total_tagged_before / total_rows_before if total_rows_before else 0
        after_pct = 100 * total_tagged_after / total_rows_after if total_rows_after else 0

        print(f"\nDone. {total_stats['tags_added']} tags added across {len(paths)} fixtures")
        print(f"Coverage: {total_tagged_before}/{total_rows_before} ({before_pct:.1f}%) → "
              f"{total_tagged_after}/{total_rows_after} ({after_pct:.1f}%)")
        print(f"API calls: {total_stats['api_calls']}")

    else:
        tg_path = args.path
        if not os.path.exists(tg_path):
            print(f"Error: file not found: {tg_path}", file=sys.stderr)
            sys.exit(1)

        # Coverage before
        tagged_before, total_rows = _count_coverage(tg_path)

        stats = tag_document(
            tg_path,
            concept_index,
            dry_run=args.dry_run,
            verbose=args.verbose,
            model=args.model,
        )

        # Coverage after
        tagged_after, _ = _count_coverage(tg_path)

        fixture = Path(tg_path).parent.name
        before_pct = 100 * tagged_before / total_rows if total_rows else 0
        after_pct = 100 * tagged_after / total_rows if total_rows else 0
        print(f"{fixture}: +{stats['tags_added']} tags, {stats['api_calls']} API calls")
        print(f"Coverage: {tagged_before}/{total_rows} ({before_pct:.1f}%) → "
              f"{tagged_after}/{total_rows} ({after_pct:.1f}%)")

        if args.dry_run:
            print("(dry run — no changes written)")


if __name__ == "__main__":
    main()
