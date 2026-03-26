#!/usr/bin/env python3
"""
structural_inference.py — Propagate concept tags through table hierarchy + ontology summation trees.

Uses parentId/childIds from table_graphs.json and summation trees from counterparts.yaml
to infer concept assignments for untagged rows. Runs AFTER label matching (pretag_all.py)
and BEFORE consistency checking (check_consistency.py).

Propagation passes:
  1. Top-down:    tagged parent + summation tree → tag untagged children
  2. Bottom-up:   all children tagged + summation tree → tag untagged parent
  3. Cross-table: note-to-face ties propagate between primary statements and disclosure notes
  4. Division:    known ratio relationships (e.g., EPS = net_profit / shares)

All passes cascade until fixed-point (no new tags).

Usage:
    python3 eval/structural_inference.py <table_graphs.json> [--dry-run] [--verbose]
"""

import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import permutations
from typing import Optional

# Add parent dir to path for sibling imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relationship_graph import (
    OntologyGraph, GraphEdge, EdgeType,
    build_graph, _infer_context,
)
from check_consistency import (
    _match_label, _infer_table_context, _get_label_index,
)


# ── Tolerance ─────────────────────────────────────────────────────

TOLERANCE = 1000  # 1 TEUR — same as check_consistency.py


# ── Data structures ───────────────────────────────────────────────

@dataclass
class InferredTag:
    row_id: str
    table_id: str
    concept_id: str
    confidence: float
    rule: str               # top_down | top_down_arithmetic | bottom_up | bottom_up_partial | cross_table | division
    source_rows: list[str]  # rowIds that drove this inference
    edge_name: str          # which summation tree / tie was used
    iteration: int = 0


@dataclass
class TableHierarchy:
    table_id: str
    context: str                             # statementComponent
    rows: dict[str, dict] = field(default_factory=dict)           # rowId → row dict
    children_of: dict[str, list[str]] = field(default_factory=dict)  # rowId → [childRowIds]
    parent_of: dict[str, str] = field(default_factory=dict)          # rowId → parentRowId
    tagged: dict[str, str] = field(default_factory=dict)             # rowId → conceptId (mutable)
    values: dict = field(default_factory=dict)                       # (rowId, colIdx) → parsedValue
    value_col_indices: list[int] = field(default_factory=list)       # indices of VALUE columns


# ── Position heuristics for European reporting ────────────────────

# For SFP: non-current appears before current in European convention.
# Key = parent concept, value = ordered list of expected children.
POSITION_ORDERED = {
    "FS.SFP.TOTAL_ASSETS": ["FS.SFP.NON_CURRENT_ASSETS", "FS.SFP.CURRENT_ASSETS"],
    "FS.SFP.TOTAL_EQUITY_AND_LIABILITIES": ["FS.SFP.TOTAL_EQUITY", "FS.SFP.NON_CURRENT_LIABILITIES", "FS.SFP.CURRENT_LIABILITIES"],
}


# ── Build phase ───────────────────────────────────────────────────

PRIMARY_STATEMENTS = {"PNL", "SFP", "OCI", "CFS", "SOCIE"}


def build_table_hierarchies(tables: list[dict]) -> list[TableHierarchy]:
    """Build per-table hierarchy structures from table_graphs.json tables."""
    hierarchies = []
    for table in tables:
        ctx = table.get("metadata", {}).get("statementComponent")
        if not ctx:
            continue

        h = TableHierarchy(table_id=table["tableId"], context=ctx)

        # Identify value columns
        for col in table.get("columns", []):
            if col.get("role") == "VALUE":
                h.value_col_indices.append(col["colIdx"])

        for row in table.get("rows", []):
            rid = row["rowId"]
            h.rows[rid] = row

            if row.get("parentId"):
                h.parent_of[rid] = row["parentId"]
            if row.get("childIds"):
                h.children_of[rid] = row["childIds"]

            # Index tagged concepts
            pt = row.get("preTagged")
            if pt and pt.get("conceptId"):
                h.tagged[rid] = pt["conceptId"]

            # Index cell values
            for cell in row.get("cells", []):
                if cell.get("parsedValue") is not None:
                    h.values[(rid, cell["colIdx"])] = cell["parsedValue"]

        hierarchies.append(h)
    return hierarchies


def _get_row_values(h: TableHierarchy, row_id: str) -> list[Optional[float]]:
    """Get values for a row across all value columns."""
    return [h.values.get((row_id, ci)) for ci in h.value_col_indices]


def _values_sum_match(parent_vals: list[Optional[float]],
                      child_vals_list: list[list[Optional[float]]],
                      tolerance: float = TOLERANCE) -> bool:
    """Check if parent values ≈ SUM(children values) across all value columns."""
    matched_any = False
    for col_i in range(len(parent_vals)):
        pv = parent_vals[col_i]
        if pv is None:
            continue
        child_sum = 0.0
        all_present = True
        for cv_list in child_vals_list:
            cv = cv_list[col_i] if col_i < len(cv_list) else None
            if cv is None:
                all_present = False
                break
            child_sum += cv
        if not all_present:
            continue
        if abs(pv - child_sum) > tolerance:
            return False
        matched_any = True
    return matched_any


# ── Summation tree index ──────────────────────────────────────────

def _build_summation_index(graph: OntologyGraph) -> tuple[dict, dict]:
    """Build lookup dicts from summation tree edges.

    Returns:
        parent_to_trees: concept_id → [GraphEdge] (trees where concept is parent)
        child_to_trees:  concept_id → [GraphEdge] (trees where concept is a child)
    """
    parent_to_trees: dict[str, list[GraphEdge]] = defaultdict(list)
    child_to_trees: dict[str, list[GraphEdge]] = defaultdict(list)
    for edge in graph.edges_by_type(EdgeType.SUMMATION):
        parent_to_trees[edge.parent].append(edge)
        for child_id in edge.children:
            child_to_trees[child_id].append(edge)
    return dict(parent_to_trees), dict(child_to_trees)


# ── Pass 1: Top-down propagation ─────────────────────────────────

def propagate_top_down(hierarchies: list[TableHierarchy],
                       parent_to_trees: dict[str, list[GraphEdge]],
                       iteration: int,
                       verbose: bool = False) -> list[InferredTag]:
    """For each tagged parent with a summation tree, try to tag untagged children."""
    inferred = []
    for h in hierarchies:
        for row_id, concept_id in list(h.tagged.items()):
            trees = parent_to_trees.get(concept_id, [])
            if not trees:
                continue

            child_rows = h.children_of.get(row_id, [])
            if not child_rows:
                continue

            for tree in trees:
                # Check context compatibility
                if tree.parent_context and tree.parent_context != h.context:
                    continue

                # Partition children
                tagged_children = {}    # row_id → concept_id
                untagged_children = []  # row_ids
                for crid in child_rows:
                    if crid in h.tagged:
                        tagged_children[crid] = h.tagged[crid]
                    else:
                        # Only consider DATA/TOTAL rows, not SECTION
                        row = h.rows.get(crid, {})
                        if row.get("rowType") in ("DATA", "TOTAL_EXPLICIT", "TOTAL_IMPLICIT"):
                            untagged_children.append(crid)

                if not untagged_children:
                    continue

                # Which tree children are already matched?
                matched_tree_children = set()
                for crid, ccid in tagged_children.items():
                    if ccid in tree.children:
                        matched_tree_children.add(ccid)

                unmatched_tree_children = [c for c in tree.children
                                           if c not in matched_tree_children]

                if not unmatched_tree_children:
                    continue

                # Case 1: 1 untagged row, 1 unmatched tree child → direct assignment
                if len(untagged_children) == 1 and len(unmatched_tree_children) == 1:
                    confidence = 0.85
                    # Position bonus
                    if concept_id in POSITION_ORDERED:
                        expected_order = POSITION_ORDERED[concept_id]
                        # Check if the unmatched concept's expected position matches
                        target_concept = unmatched_tree_children[0]
                        if target_concept in expected_order:
                            expected_idx = expected_order.index(target_concept)
                            # Get all children sorted by row index
                            all_children_sorted = sorted(child_rows,
                                key=lambda r: h.rows.get(r, {}).get("rowIdx", 999))
                            actual_idx = all_children_sorted.index(untagged_children[0]) if untagged_children[0] in all_children_sorted else -1
                            if actual_idx == expected_idx:
                                confidence += 0.05

                    inferred.append(InferredTag(
                        row_id=untagged_children[0],
                        table_id=h.table_id,
                        concept_id=unmatched_tree_children[0],
                        confidence=confidence,
                        rule="top_down",
                        source_rows=[row_id],
                        edge_name=tree.name,
                        iteration=iteration,
                    ))
                    if verbose:
                        label = h.rows.get(untagged_children[0], {}).get("label", "?")
                        print(f"  [top_down] {label} → {unmatched_tree_children[0]} (conf={confidence:.2f})")

                # Case 2: N untagged = N unmatched → arithmetic verification
                elif len(untagged_children) == len(unmatched_tree_children):
                    result = _try_arithmetic_assignment(
                        h, row_id, untagged_children, unmatched_tree_children)
                    if result:
                        for crid, ccid in result.items():
                            confidence = 0.75
                            if concept_id in POSITION_ORDERED:
                                expected_order = POSITION_ORDERED[concept_id]
                                if ccid in expected_order:
                                    all_sorted = sorted(child_rows,
                                        key=lambda r: h.rows.get(r, {}).get("rowIdx", 999))
                                    if crid in all_sorted:
                                        actual_idx = all_sorted.index(crid)
                                        expected_idx = expected_order.index(ccid)
                                        if actual_idx == expected_idx:
                                            confidence += 0.05
                            inferred.append(InferredTag(
                                row_id=crid,
                                table_id=h.table_id,
                                concept_id=ccid,
                                confidence=confidence,
                                rule="top_down_arithmetic",
                                source_rows=[row_id],
                                edge_name=tree.name,
                                iteration=iteration,
                            ))
                            if verbose:
                                label = h.rows.get(crid, {}).get("label", "?")
                                print(f"  [top_down_arith] {label} → {ccid} (conf={confidence:.2f})")

                # Case 3: partial tree, more untagged rows than tree children
                # Only attempt when the ambiguity is low (at most 1 extra untagged child)
                elif (tree.partial
                      and len(unmatched_tree_children) <= len(untagged_children)
                      and len(untagged_children) - len(unmatched_tree_children) <= 1):
                    if len(unmatched_tree_children) == 1:
                        # Try label hint + position to pick the right untagged row
                        best = _pick_best_untagged(h, untagged_children, unmatched_tree_children[0])
                        if best:
                            inferred.append(InferredTag(
                                row_id=best,
                                table_id=h.table_id,
                                concept_id=unmatched_tree_children[0],
                                confidence=0.75,
                                rule="top_down",
                                source_rows=[row_id],
                                edge_name=tree.name,
                                iteration=iteration,
                            ))
                            if verbose:
                                label = h.rows.get(best, {}).get("label", "?")
                                print(f"  [top_down_partial] {label} → {unmatched_tree_children[0]} (conf=0.75)")
                    elif len(unmatched_tree_children) > 1:
                        # Try arithmetic for the subset
                        result = _try_arithmetic_partial(
                            h, row_id, untagged_children, unmatched_tree_children, tagged_children)
                        if result:
                            for crid, ccid in result.items():
                                inferred.append(InferredTag(
                                    row_id=crid,
                                    table_id=h.table_id,
                                    concept_id=ccid,
                                    confidence=0.65,
                                    rule="top_down_arithmetic",
                                    source_rows=[row_id],
                                    edge_name=tree.name,
                                    iteration=iteration,
                                ))

    return inferred


def _try_arithmetic_assignment(h: TableHierarchy, parent_id: str,
                               untagged_rows: list[str],
                               unmatched_concepts: list[str]) -> Optional[dict[str, str]]:
    """Try all permutations to find a unique one where SUM(children) = parent.

    When arithmetic is degenerate (multiple permutations match — e.g., because
    parent = SUM(all children) regardless of order), falls back to position
    ordering from POSITION_ORDERED.

    Returns row_id → concept_id mapping or None.
    """
    if len(untagged_rows) > 5:
        return None  # too many permutations

    parent_vals = _get_row_values(h, parent_id)

    # Get tagged children values (already assigned)
    tagged_child_vals = []
    for crid in h.children_of.get(parent_id, []):
        if crid in h.tagged and crid not in untagged_rows:
            tagged_child_vals.append(_get_row_values(h, crid))

    valid_assignments = []
    for perm in permutations(unmatched_concepts):
        assignment = dict(zip(untagged_rows, perm))
        all_child_vals = tagged_child_vals + [_get_row_values(h, rid) for rid in untagged_rows]
        if _values_sum_match(parent_vals, all_child_vals):
            valid_assignments.append(assignment)

    if len(valid_assignments) == 1:
        return valid_assignments[0]

    if len(valid_assignments) > 1:
        # Arithmetic is degenerate — use position ordering as tiebreaker
        parent_concept = h.tagged.get(parent_id)
        if parent_concept and parent_concept in POSITION_ORDERED:
            expected_order = POSITION_ORDERED[parent_concept]
            # Filter to only unmatched concepts, preserving their relative order
            unmatched_order = [c for c in expected_order if c in unmatched_concepts]
            if len(unmatched_order) == len(unmatched_concepts):
                sorted_rows = sorted(untagged_rows,
                    key=lambda r: h.rows.get(r, {}).get("rowIdx", 999))
                # Pair by relative position: first untagged row → first unmatched concept
                assignment = dict(zip(sorted_rows, unmatched_order))
                return assignment

        # No position heuristic available — skip (ambiguous)
        return None

    return None


def _try_arithmetic_partial(h: TableHierarchy, parent_id: str,
                            untagged_rows: list[str],
                            unmatched_concepts: list[str],
                            tagged_children: dict[str, str]) -> Optional[dict[str, str]]:
    """For partial trees: try to find a subset of untagged rows that match the unmatched concepts."""
    if len(untagged_rows) > 8 or len(unmatched_concepts) > 4:
        return None  # too expensive

    from itertools import combinations

    for combo in combinations(untagged_rows, len(unmatched_concepts)):
        result = _try_arithmetic_assignment(h, parent_id, list(combo), unmatched_concepts)
        if result:
            return result
    return None


def _pick_best_untagged(h: TableHierarchy, candidates: list[str], target_concept: str) -> Optional[str]:
    """Pick the best untagged row for a concept using position heuristics.

    For concepts in POSITION_ORDERED, prefer the row at the expected position.
    """
    # Find which parent this concept belongs to in POSITION_ORDERED
    for parent_concept, ordered_children in POSITION_ORDERED.items():
        if target_concept in ordered_children:
            expected_idx = ordered_children.index(target_concept)
            # Sort candidates by row index
            sorted_candidates = sorted(candidates,
                key=lambda r: h.rows.get(r, {}).get("rowIdx", 999))
            if expected_idx < len(sorted_candidates):
                return sorted_candidates[expected_idx]

    # Fallback: if only one candidate has values, pick it
    with_values = [r for r in candidates if any(
        h.values.get((r, ci)) is not None for ci in h.value_col_indices)]
    if len(with_values) == 1:
        return with_values[0]

    return None


# ── Pass 2: Bottom-up propagation ─────────────────────────────────

def propagate_bottom_up(hierarchies: list[TableHierarchy],
                        child_to_trees: dict[str, list[GraphEdge]],
                        iteration: int,
                        verbose: bool = False) -> list[InferredTag]:
    """For each untagged row whose children are all tagged, try to infer the parent concept."""
    inferred = []
    for h in hierarchies:
        for row_id, child_ids in h.children_of.items():
            if row_id in h.tagged:
                continue  # already tagged
            if not child_ids:
                continue

            # All children must be tagged
            child_concepts = []
            all_tagged = True
            for cid in child_ids:
                if cid in h.tagged:
                    child_concepts.append(h.tagged[cid])
                else:
                    all_tagged = False
                    break

            if not all_tagged:
                continue

            child_set = set(child_concepts)

            # Find a summation tree that matches
            best_match = None
            best_confidence = 0.0
            best_rule = ""

            # Check trees via any child concept
            candidate_trees = set()
            for cc in child_concepts:
                for tree in child_to_trees.get(cc, []):
                    candidate_trees.add(id(tree))

            for cc in child_concepts:
                for tree in child_to_trees.get(cc, []):
                    # Context check
                    if tree.parent_context and tree.parent_context != h.context:
                        continue

                    tree_child_set = set(tree.children)

                    if child_set == tree_child_set:
                        # Exact match — high confidence
                        conf = 0.90
                        # Verify arithmetic
                        parent_vals = _get_row_values(h, row_id)
                        child_vals = [_get_row_values(h, cid) for cid in child_ids]
                        if any(pv is not None for pv in parent_vals):
                            if _values_sum_match(parent_vals, child_vals):
                                conf = 0.95  # arithmetic confirmed
                            else:
                                conf = 0.70  # children match but arithmetic doesn't
                        if conf > best_confidence:
                            best_match = tree
                            best_confidence = conf
                            best_rule = "bottom_up"

                    elif child_set.issubset(tree_child_set) and tree.partial:
                        # Partial match
                        conf = 0.70
                        parent_vals = _get_row_values(h, row_id)
                        child_vals = [_get_row_values(h, cid) for cid in child_ids]
                        if any(pv is not None for pv in parent_vals):
                            if _values_sum_match(parent_vals, child_vals):
                                conf = 0.75
                        if conf > best_confidence:
                            best_match = tree
                            best_confidence = conf
                            best_rule = "bottom_up_partial"

            if best_match:
                inferred.append(InferredTag(
                    row_id=row_id,
                    table_id=h.table_id,
                    concept_id=best_match.parent,
                    confidence=best_confidence,
                    rule=best_rule,
                    source_rows=child_ids,
                    edge_name=best_match.name,
                    iteration=iteration,
                ))
                if verbose:
                    label = h.rows.get(row_id, {}).get("label", "?")
                    print(f"  [bottom_up] {label} → {best_match.parent} (conf={best_confidence:.2f})")

    return inferred


# ── Pass 3: Cross-table propagation ──────────────────────────────

def propagate_cross_table(hierarchies: list[TableHierarchy],
                          graph: OntologyGraph,
                          iteration: int,
                          verbose: bool = False) -> list[InferredTag]:
    """Use note-to-face ties to propagate between primary statements and disclosure notes."""
    inferred = []

    # Build face value index: (concept, colIdx) → (amount, rowId, tableId)
    face_index: dict[tuple[str, int], tuple[float, str, str]] = {}
    for h in hierarchies:
        if h.context not in PRIMARY_STATEMENTS:
            continue
        for rid, cid in h.tagged.items():
            for ci in h.value_col_indices:
                val = h.values.get((rid, ci))
                if val is not None:
                    face_index[(cid, ci)] = (val, rid, h.table_id)

    # Process note-to-face ties
    for edge in graph.edges_by_type(EdgeType.NOTE_TO_FACE):
        if not edge.note_concept:
            continue

        # Find face value
        face_vals = {}
        for ci_key, (val, rid, tid) in face_index.items():
            if ci_key[0] == edge.face_concept:
                face_vals[ci_key[1]] = (val, rid)

        if not face_vals:
            continue

        # Find note tables matching the note context
        for h in hierarchies:
            if h.context != edge.note_context:
                continue

            for rid, row in h.rows.items():
                if rid in h.tagged:
                    continue
                if row.get("rowType") not in ("TOTAL_EXPLICIT", "TOTAL_IMPLICIT"):
                    continue

                # Check value match across columns
                matched = 0
                checked = 0
                source_rows = []
                for ci in h.value_col_indices:
                    note_val = h.values.get((rid, ci))
                    if note_val is None:
                        continue
                    face_entry = face_vals.get(ci)
                    if face_entry is None:
                        continue
                    checked += 1
                    face_val, face_rid = face_entry
                    if abs(note_val - face_val) <= TOLERANCE:
                        matched += 1
                        source_rows.append(face_rid)

                if matched > 0 and matched == checked:
                    inferred.append(InferredTag(
                        row_id=rid,
                        table_id=h.table_id,
                        concept_id=edge.note_concept,
                        confidence=0.70,
                        rule="cross_table",
                        source_rows=source_rows,
                        edge_name=edge.name,
                        iteration=iteration,
                    ))
                    if verbose:
                        label = h.rows.get(rid, {}).get("label", "?")
                        print(f"  [cross_table] {label} → {edge.note_concept} (conf=0.70)")

    return inferred


# ── Pass 4: Division relationship propagation ─────────────────────

# Known ratio relationships: result = numerator / denominator
DIVISION_RULES = [
    {
        "result": "DISC.EPS.WEIGHTED_AVG_SHARES_BASIC",
        "numerator": "FS.PNL.NET_PROFIT",
        "denominator": "FS.PNL.EPS_BASIC",
    },
    {
        "result": "DISC.EPS.WEIGHTED_AVG_SHARES_DILUTED",
        "numerator": "FS.PNL.NET_PROFIT",
        "denominator": "FS.PNL.EPS_DILUTED",
    },
]


def propagate_divisions(hierarchies: list[TableHierarchy],
                        iteration: int,
                        verbose: bool = False) -> list[InferredTag]:
    """For known ratio relationships, find rows whose values match numerator/denominator."""
    inferred = []

    # Build global concept → {colIdx → (value, rowId)} index across all tables
    concept_vals: dict[str, dict[int, tuple[float, str]]] = defaultdict(dict)
    for h in hierarchies:
        for rid, cid in h.tagged.items():
            for ci in h.value_col_indices:
                val = h.values.get((rid, ci))
                if val is not None:
                    concept_vals[cid][ci] = (val, rid)

    for rule in DIVISION_RULES:
        num_vals = concept_vals.get(rule["numerator"], {})
        den_vals = concept_vals.get(rule["denominator"], {})
        if not num_vals or not den_vals:
            continue

        # Compute expected ratio per column
        expected: dict[int, float] = {}
        for ci in num_vals:
            if ci in den_vals:
                den_v = den_vals[ci][0]
                if abs(den_v) > 1e-9:
                    expected[ci] = num_vals[ci][0] / den_v

        if not expected:
            continue

        # Search all tables for matching values
        for h in hierarchies:
            for rid, row in h.rows.items():
                if rid in h.tagged:
                    continue
                if row.get("rowType") not in ("DATA", "TOTAL_EXPLICIT", "TOTAL_IMPLICIT"):
                    continue

                matched = 0
                checked = 0
                for ci, exp_val in expected.items():
                    actual = h.values.get((rid, ci))
                    if actual is None:
                        continue
                    checked += 1
                    # Tolerance: 0.1% relative for ratios
                    if abs(exp_val) > 1e-9 and abs(actual - exp_val) / abs(exp_val) < 0.001:
                        matched += 1

                if matched > 0 and matched == checked:
                    source = [num_vals[ci][1] for ci in expected if ci in num_vals]
                    source += [den_vals[ci][1] for ci in expected if ci in den_vals]
                    inferred.append(InferredTag(
                        row_id=rid,
                        table_id=h.table_id,
                        concept_id=rule["result"],
                        confidence=0.60,
                        rule="division",
                        source_rows=list(set(source)),
                        edge_name=f"div_{rule['result']}",
                        iteration=iteration,
                    ))
                    if verbose:
                        label = h.rows.get(rid, {}).get("label", "?")
                        print(f"  [division] {label} → {rule['result']} (conf=0.60)")

    return inferred


# ── Pass 0: Label matching (fill pretag_all gaps) ─────────────────

def _label_match_pass(tables: list[dict], ontology_root: str,
                      verbose: bool = False) -> list[InferredTag]:
    """Use the full ontology label index to tag rows that pretag_all missed."""
    _get_label_index(ontology_root)  # ensure label index is built
    inferred = []

    for table in tables:
        ctx = table.get("metadata", {}).get("statementComponent")
        if not ctx:
            continue

        for row in table.get("rows", []):
            pt = row.get("preTagged")
            if pt and pt.get("conceptId"):
                continue
            if row.get("rowType") == "SEPARATOR":
                continue

            label = row.get("label", "")
            if not label or not label.strip():
                continue

            match = _match_label(label, table_context=ctx, ontology_root=ontology_root)
            if match:
                concept_id, label_ctx = match
                tag = InferredTag(
                    row_id=row["rowId"],
                    table_id=table["tableId"],
                    concept_id=concept_id,
                    confidence=0.80,
                    rule="label_match",
                    source_rows=[],
                    edge_name="ontology_label_index",
                    iteration=-1,
                )
                row["preTagged"] = {
                    "conceptId": concept_id,
                    "method": "structural",
                    "confidence": 0.80,
                    "rule": "label_match",
                    "sourceRows": [],
                    "edge": "ontology_label_index",
                }
                inferred.append(tag)
                if verbose:
                    print(f"  [label] {label[:50]} → {concept_id}")

    if inferred and verbose:
        print(f"  Label matching: {len(inferred)} additional tags")

    return inferred


# ── Cascade loop ──────────────────────────────────────────────────

def apply_tag(tables: list[dict], tag: InferredTag):
    """Write an inferred tag into the table_graphs.json row."""
    for table in tables:
        if table["tableId"] != tag.table_id:
            continue
        for row in table.get("rows", []):
            if row["rowId"] == tag.row_id:
                row["preTagged"] = {
                    "conceptId": tag.concept_id,
                    "method": "structural",
                    "confidence": round(tag.confidence, 3),
                    "rule": tag.rule,
                    "sourceRows": tag.source_rows,
                    "edge": tag.edge_name,
                }
                return


def cascade(tables: list[dict], ontology_root: str,
            max_iterations: int = 10,
            verbose: bool = False) -> tuple[int, list[InferredTag]]:
    """Run all propagation passes until fixed-point.

    Returns (iterations_used, all_inferred_tags).
    """
    graph = build_graph(ontology_root)
    parent_to_trees, child_to_trees = _build_summation_index(graph)

    # Pass 0: Fill gaps via the full ontology label index.
    # pretag_all.py uses a separate label index that may miss concepts
    # defined in concepts/*.yaml, gaap/ugb.yaml, or aliases.yaml.
    label_matched = _label_match_pass(tables, ontology_root, verbose)

    all_inferred: list[InferredTag] = list(label_matched)

    for iteration in range(max_iterations):
        hierarchies = build_table_hierarchies(tables)

        if verbose:
            print(f"\n── Iteration {iteration + 1} ──")

        new_tags = []
        new_tags += propagate_top_down(hierarchies, parent_to_trees, iteration, verbose)
        new_tags += propagate_bottom_up(hierarchies, child_to_trees, iteration, verbose)
        new_tags += propagate_cross_table(hierarchies, graph, iteration, verbose)
        new_tags += propagate_divisions(hierarchies, iteration, verbose)

        if not new_tags:
            if verbose:
                print("  No new tags — fixed point reached.")
            break

        # Deduplicate: if multiple rules infer the same row, keep highest confidence
        best_per_row: dict[str, InferredTag] = {}
        for tag in new_tags:
            existing = best_per_row.get(tag.row_id)
            if existing is None or tag.confidence > existing.confidence:
                best_per_row[tag.row_id] = tag

        # Apply (never overwrite existing tags)
        applied = 0
        for tag in best_per_row.values():
            # Double-check not already tagged (may have been tagged by a
            # different rule in the same iteration via a different hierarchy)
            already = False
            for table in tables:
                if table["tableId"] != tag.table_id:
                    continue
                for row in table.get("rows", []):
                    if row["rowId"] == tag.row_id:
                        pt = row.get("preTagged")
                        if pt and pt.get("conceptId"):
                            already = True
                        break
                break

            if not already:
                apply_tag(tables, tag)
                all_inferred.append(tag)
                applied += 1

        if verbose:
            print(f"  Applied {applied} new tags (from {len(new_tags)} candidates)")

        if applied == 0:
            break

    return iteration + 1 if all_inferred else 0, all_inferred


# ── CLI ───────────────────────────────────────────────────────────

def run_structural_inference(tg_path: str, dry_run: bool = False, verbose: bool = False):
    """Run structural inference on a table_graphs.json file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ontology_root = os.path.dirname(script_dir)

    with open(tg_path) as f:
        data = json.load(f)
    tables = data.get("tables", [])

    # Count pre-existing tags
    pre_tagged = 0
    total_rows = 0
    for table in tables:
        for row in table.get("rows", []):
            total_rows += 1
            pt = row.get("preTagged")
            if pt and pt.get("conceptId"):
                pre_tagged += 1

    print(f"Structural inference: {tg_path}")
    print(f"  Before: {pre_tagged}/{total_rows} tagged ({100*pre_tagged/total_rows:.1f}%)" if total_rows else "  No rows")

    iterations, all_inferred = cascade(tables, ontology_root, verbose=verbose)

    # Count post-inference tags
    post_tagged = 0
    for table in tables:
        for row in table.get("rows", []):
            pt = row.get("preTagged")
            if pt and pt.get("conceptId"):
                post_tagged += 1

    new_tags = post_tagged - pre_tagged
    print(f"  After:  {post_tagged}/{total_rows} tagged ({100*post_tagged/total_rows:.1f}%)" if total_rows else "")
    print(f"  Inferred: {new_tags} new tags in {iterations} iterations")

    # Breakdown by rule
    if all_inferred:
        by_rule = defaultdict(int)
        for tag in all_inferred:
            by_rule[tag.rule] += 1
        for rule, count in sorted(by_rule.items()):
            print(f"    {rule}: {count}")

    if not dry_run and all_inferred:
        # Backup original
        backup_path = tg_path + ".structural.bak"
        if not os.path.exists(backup_path):
            import shutil
            shutil.copy2(tg_path, backup_path)
            print(f"  Backup: {backup_path}")

        with open(tg_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  Written: {tg_path}")
    elif dry_run:
        print(f"  [DRY RUN] No changes written.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    path = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    if not os.path.exists(path):
        print(f"Error: {path} not found")
        sys.exit(1)

    run_structural_inference(path, dry_run=dry_run, verbose=verbose)
