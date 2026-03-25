#!/usr/bin/env python3
"""
check_consistency.py — Three-pass structural consistency checker.

Replaces check_cross_reference.py with ontology-driven validation.

Pass 1: Validate DECLARED relationships (counterparts.yaml + concept metadata)
  → VALID_DISAGGREGATION, VALID_TIE, BROKEN_RELATIONSHIP, IC_LEAKAGE

Pass 2: Explain KNOWN mismatch patterns (mismatch_patterns.yaml)
  → EXPLAINED_MISMATCH with pattern ID

Pass 3: Flag UNEXPLAINED cross-table inconsistencies
  → UNEXPLAINED_INCONSISTENCY

Usage:
    python3 eval/check_consistency.py <table_graphs.json> [--ontology-root /path/to/fobe]
    python3 eval/check_consistency.py <table_graphs.json> --json  # JSON output
    python3 eval/check_consistency.py <table_graphs.json> --check fixtures/wienerberger_2024/expected_violations.json
"""

import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional

# Add parent dir to path for sibling imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from relationship_graph import (
    OntologyGraph, GraphEdge, EdgeType, ConceptMeta,
    build_graph, load_concepts, _infer_context,
)

import yaml


# ── Result categories ──────────────────────────────────────────────

class Category(Enum):
    VALID_DISAGGREGATION = "VALID_DISAGGREGATION"
    VALID_TIE = "VALID_TIE"
    BROKEN_RELATIONSHIP = "BROKEN_RELATIONSHIP"
    EXPLAINED_MISMATCH = "EXPLAINED_MISMATCH"
    UNEXPLAINED_INCONSISTENCY = "UNEXPLAINED_INCONSISTENCY"
    IC_LEAKAGE = "IC_LEAKAGE"


@dataclass
class Finding:
    category: Category
    edge_name: str = ""
    severity: str = "INFO"
    # Amounts
    expected: Optional[float] = None
    actual: Optional[float] = None
    delta: Optional[float] = None
    # Context
    table_ids: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    message: str = ""
    # Pass 2
    pattern_id: Optional[str] = None
    # Details
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {
            "category": self.category.value,
            "severity": self.severity,
            "message": self.message,
        }
        if self.edge_name:
            d["edge_name"] = self.edge_name
        if self.expected is not None:
            d["expected"] = self.expected
        if self.actual is not None:
            d["actual"] = self.actual
        if self.delta is not None:
            d["delta"] = self.delta
        if self.table_ids:
            d["table_ids"] = self.table_ids
        if self.concepts:
            d["concepts"] = self.concepts
        if self.pattern_id:
            d["pattern_id"] = self.pattern_id
        if self.details:
            d["details"] = self.details
        return d


# ── Fact indexing ──────────────────────────────────────────────────

@dataclass
class Fact:
    """A single numeric observation from the document."""
    table_id: str
    context: str        # statementComponent or inferred from concept
    concept_id: str     # from preTagged or label matching
    label: str
    amount: float
    col_idx: int        # column index in the table
    period_key: str     # e.g. "Y2024", "Y2023", or "ord_0", "ord_1"
    unit_scale: int     # 1, 1000, 1000000
    page: int = 0
    is_primary: bool = False  # from a primary statement (PNL/SFP/OCI/CFS/SOCIE)
    value_col_count: int = 0  # number of value columns in source table


PRIMARY_STATEMENTS = {"PNL", "SFP", "OCI", "CFS", "SOCIE"}

# ── Label-based concept matching ───────────────────────────────────
# Maps normalized labels to (concept_id, context) for untagged rows.
# Only high-confidence matches — ambiguous labels are skipped.

LABEL_CONCEPT_MAP: dict[str, tuple[str, str]] = {
    # Segment note labels → DISC.SEGMENTS concepts
    "external revenues": ("DISC.SEGMENTS.EXTERNAL_REVENUE", "DISC.SEGMENTS"),
    "external revenue": ("DISC.SEGMENTS.EXTERNAL_REVENUE", "DISC.SEGMENTS"),
    "intercompany revenues": ("DISC.SEGMENTS.INTERSEGMENT_REVENUE", "DISC.SEGMENTS"),
    "intercompany revenue": ("DISC.SEGMENTS.INTERSEGMENT_REVENUE", "DISC.SEGMENTS"),
    "inter-segment revenue": ("DISC.SEGMENTS.INTERSEGMENT_REVENUE", "DISC.SEGMENTS"),
    "intersegment revenue": ("DISC.SEGMENTS.INTERSEGMENT_REVENUE", "DISC.SEGMENTS"),
    "total revenues": ("DISC.SEGMENTS.TOTAL_REVENUE", "DISC.SEGMENTS"),
    "segment revenue": ("DISC.SEGMENTS.TOTAL_REVENUE", "DISC.SEGMENTS"),
    "segment assets": ("DISC.SEGMENTS.TOTAL_ASSETS", "DISC.SEGMENTS"),
    "segment liabilities": ("DISC.SEGMENTS.TOTAL_LIABILITIES", "DISC.SEGMENTS"),
    "capital expenditure": ("DISC.SEGMENTS.CAPEX", "DISC.SEGMENTS"),
    # Revenue disaggregation
    "goods transferred at a point in time": ("DISC.REVENUE.GOODS_TRANSFERRED_POINT", "DISC.REVENUE"),
    "goods transferred over time": ("DISC.REVENUE.GOODS_TRANSFERRED_OVERTIME", "DISC.REVENUE"),
    "services transferred over time": ("DISC.REVENUE.GOODS_TRANSFERRED_OVERTIME", "DISC.REVENUE"),
    # Tax disaggregation
    "current tax expense": ("DISC.TAX.CURRENT_TAX_EXPENSE", "DISC.TAX"),
    "current income tax": ("DISC.TAX.CURRENT_TAX_EXPENSE", "DISC.TAX"),
    "deferred tax expense": ("DISC.TAX.DEFERRED_TAX_EXPENSE", "DISC.TAX"),
    "deferred tax expense/income": ("DISC.TAX.DEFERRED_TAX_EXPENSE", "DISC.TAX"),
    "deferred tax income": ("DISC.TAX.DEFERRED_TAX_EXPENSE", "DISC.TAX"),
    "income taxes": ("DISC.TAX.TOTAL_TAX_EXPENSE", "DISC.TAX"),
    "incometaxes": ("DISC.TAX.TOTAL_TAX_EXPENSE", "DISC.TAX"),
    "income tax expense": ("DISC.TAX.TOTAL_TAX_EXPENSE", "DISC.TAX"),
    # Revenue note total
    "total revenue": ("DISC.REVENUE.TOTAL_REVENUE", "DISC.REVENUE"),
    "total revenues": ("DISC.REVENUE.TOTAL_REVENUE", "DISC.REVENUE"),
    # PPE rollforward
    "carrying amount": ("DISC.PPE.CARRYING_AMOUNT", "DISC.PPE"),
    "net book value": ("DISC.PPE.CARRYING_AMOUNT", "DISC.PPE"),
}

# Patterns for stripping common noise from labels
_LABEL_STRIP = re.compile(r'\s*\d+\)?\s*$|^\d+\.\s*')  # trailing "1)" or leading "7."


def _normalize_label(label: str) -> str:
    """Normalize a label for matching."""
    label = _LABEL_STRIP.sub("", label.strip()).strip().lower()
    # Remove extra whitespace
    label = re.sub(r'\s+', ' ', label)
    return label


def _match_label(label: str, table_context: Optional[str] = None) -> Optional[tuple[str, str]]:
    """Try to match a label to a (concept_id, context) pair.

    Returns None if the match would conflict with the table's known context
    (e.g., 'Total revenues' in a PNL table is the face line, not DISC.SEGMENTS).
    """
    norm = _normalize_label(label)
    if not norm or len(norm) < 3:
        return None
    # Exact match
    match = LABEL_CONCEPT_MAP.get(norm)
    if not match:
        # Suffix-tolerant match: "External revenues 1)" normalizes to
        # "external revenues" after stripping — already handled by normalizer.
        # Also try with common suffixes stripped:
        for suffix in [" total", " net", " gross"]:
            if norm.endswith(suffix):
                match = LABEL_CONCEPT_MAP.get(norm[:-len(suffix)].strip())
                if match:
                    break
    if not match:
        return None

    concept_id, label_ctx = match
    # Don't label-match disclosure concepts in primary statement tables
    # (e.g., "Total revenues" in PNL is the face line, not DISC.SEGMENTS)
    if table_context in PRIMARY_STATEMENTS and label_ctx.startswith("DISC."):
        return None
    # Don't match PPE rollforward concepts in non-PPE tables
    if label_ctx == "DISC.PPE" and table_context and table_context != "DISC.PPE":
        return None

    return match


def _infer_table_context(table: dict) -> Optional[str]:
    """Infer context from table metadata (sectionPath, statementComponent)."""
    sc = table.get("metadata", {}).get("statementComponent")
    if sc:
        return sc
    # Check sectionPath for clues
    section = table.get("metadata", {}).get("sectionPath", [])
    section_text = " ".join(section).lower()
    if "segment" in section_text or "operating segment" in section_text:
        return "DISC.SEGMENTS"
    if "revenue" in section_text and "disaggregat" in section_text:
        return "DISC.REVENUE"
    if "property, plant" in section_text or "ppe" in section_text:
        return "DISC.PPE"
    if "tax" in section_text:
        return "DISC.TAX"
    if "provision" in section_text:
        return "DISC.PROVISIONS"
    if "investment property" in section_text:
        return "DISC.INV_PROP"
    return None


def _get_unit_scale(table: dict) -> int:
    """Extract unit scale from table metadata."""
    unit = table.get("metadata", {}).get("detectedUnit", "UNIT.UNITS")
    if unit in ("UNIT.THOUSANDS", "TEUR"):
        return 1000
    elif unit in ("UNIT.MILLIONS", "Mio"):
        return 1000000
    return 1


def _get_value_columns(table: dict) -> list[dict]:
    """Get VALUE columns with their axis metadata, sorted by colIdx."""
    cols = table.get("columns", [])
    return sorted(
        [c for c in cols if c.get("role") == "VALUE"],
        key=lambda c: c["colIdx"],
    )


def _extract_period(col: dict, pos: int, total: int) -> str:
    """Extract period key from column axes, falling back to ordinal."""
    axes = col.get("detectedAxes", {})
    period_axis = axes.get("AXIS.PERIOD", "")
    if period_axis and period_axis.startswith("PERIOD."):
        return period_axis.replace("PERIOD.", "")  # e.g. "Y2024"
    # Fallback: ordinal from left (first value col = 0 = most recent)
    return f"ord_{pos}"


def index_facts(tables: list[dict]) -> dict[tuple[str, str, str], list[Fact]]:
    """
    Index all tagged facts from the document.

    Returns: {(context, concept_id, period_key): [Fact, ...]}
    Facts from primary statements are sorted first within each key.
    """
    facts: dict[tuple[str, str, str], list[Fact]] = defaultdict(list)

    for table in tables:
        table_id = table["tableId"]
        sc = table.get("metadata", {}).get("statementComponent")
        page = table.get("pageNo", 0)
        scale = _get_unit_scale(table)
        value_columns = _get_value_columns(table)
        value_col_indices = [c["colIdx"] for c in value_columns]
        is_primary = sc in PRIMARY_STATEMENTS
        table_context = _infer_table_context(table)

        # For multi-segment tables (>4 value columns with period dupes),
        # only index the last column per period (= group total column).
        group_total_cols: Optional[set[int]] = None
        if len(value_columns) > 4:
            # Find the last column index for each period
            last_by_period: dict[str, int] = {}
            for vc in value_columns:
                pk = _extract_period(vc, 0, 0)
                last_by_period[pk] = vc["colIdx"]  # last one wins
            group_total_cols = set(last_by_period.values())

        for row in table.get("rows", []):
            label = row.get("label", "") or ""
            pt = row.get("preTagged")

            # Determine concept_id and context: preTagged first, then label match
            concept_id = None
            context = None
            is_label_matched = False

            if pt and isinstance(pt, dict) and pt.get("conceptId"):
                concept_id = pt["conceptId"]
                context = sc or _infer_context(concept_id)
            else:
                match = _match_label(label, table_context=table_context)
                if match:
                    concept_id, label_ctx = match
                    context = table_context or label_ctx
                    is_label_matched = True
                    # For DISC.SEGMENTS concepts, only index from actual
                    # segment note tables (multi-column with per-segment data)
                    if label_ctx == "DISC.SEGMENTS" and len(value_columns) <= 4:
                        concept_id = None  # skip — KPI summary, not segment note

            if not concept_id:
                continue

            for cell in row.get("cells", []):
                pv = cell.get("parsedValue")
                col_idx = cell.get("colIdx", -1)
                if pv is None or col_idx not in value_col_indices:
                    continue

                # For label-matched facts in multi-segment tables,
                # only use group total columns (last col per period)
                if is_label_matched and group_total_cols is not None:
                    if col_idx not in group_total_cols:
                        continue

                col_pos = value_col_indices.index(col_idx)
                col_meta = value_columns[col_pos]
                period_key = _extract_period(col_meta, col_pos, len(value_columns))

                normalized = pv * scale
                fact = Fact(
                    table_id=table_id,
                    context=context,
                    concept_id=concept_id,
                    label=label,
                    amount=normalized,
                    col_idx=col_idx,
                    period_key=period_key,
                    unit_scale=scale,
                    page=page,
                    is_primary=is_primary,
                    value_col_count=len(value_columns),
                )
                facts[(context, concept_id, period_key)].append(fact)

    # Sort: prefer primary statements with few value columns (2-3 = actual statement)
    # over summaries (10+ columns = multi-year overview with potential unit issues)
    for key in facts:
        facts[key].sort(key=lambda f: (
            not f.is_primary,
            # Prefer tables with 2-4 value columns (actual statements)
            0 if f.value_col_count <= 4 else 1,
            f.table_id,
        ))

    return facts


def _get_period_keys(facts: dict) -> list[str]:
    """Get the common period keys across all facts, sorted most-recent first."""
    keys = set()
    for (ctx, cid, pk) in facts:
        keys.add(pk)
    # Sort: Y2024 > Y2023 > ord_0 > ord_1
    def sort_key(k):
        if k.startswith("Y"):
            return (-int(k[1:]), k)
        if k.startswith("ord_"):
            return (0, k)
        return (1, k)
    return sorted(keys, key=sort_key)


def _lookup(facts: dict, context: str, concept: str, period_key: str) -> Optional[float]:
    """Look up a fact amount, preferring primary statement sources."""
    key = (context, concept, period_key)
    entries = facts.get(key, [])
    if not entries:
        return None
    # First entry is from primary statement (sorted)
    return entries[0].amount


def _lookup_fact(facts: dict, context: str, concept: str, period_key: str) -> Optional[Fact]:
    """Look up the best fact, preferring primary statement sources."""
    key = (context, concept, period_key)
    entries = facts.get(key, [])
    return entries[0] if entries else None


def _sum_by_axis(facts: dict, context: str, concept: str, period_key: str) -> Optional[float]:
    """Sum all facts for a concept in a context (across axis members)."""
    total = 0.0
    found = False
    for (ctx, cid, pk), entries in facts.items():
        if ctx == context and cid == concept and pk == period_key and entries:
            for e in entries:
                total += e.amount
                found = True
    return total if found else None


# ── Pass 1: Validate declared relationships ────────────────────────

TOLERANCE = 1000.0  # Allow rounding tolerance (1 TEUR = 1000 EUR normalized)


def _triage_residual(
    edge: GraphEdge,
    residual: float,
    face_val: float,
    facts: dict,
    period_key: str,
) -> dict:
    """Triage a disaggregation residual using the ontology's declared ambiguities.

    Returns dict with: category, severity, message, extra_concepts, extra_details.
    """
    # 1. Check if residual_confirm matches (e.g., IC line confirms the delta)
    if edge.residual_confirm:
        confirm_ctx = edge.residual_confirm.get("context", edge.detail_context)
        confirm_cid = edge.residual_confirm.get("concept", "")
        confirm_val = _lookup(facts, confirm_ctx, confirm_cid, period_key)
        if confirm_val is not None and abs(confirm_val - residual) <= TOLERANCE:
            # Find the matching ambiguity for confirmed IC
            amb_id = "IC_NOT_ELIMINATED"
            for amb in edge.ambiguities:
                if amb.get("id") == amb_id:
                    return {
                        "category": Category.IC_LEAKAGE,
                        "severity": amb.get("severity", "WARNING"),
                        "message": f"IC confirmed: {{face}}={{face_val:,.0f}}, external={{detail_sum:,.0f}}, IC={{residual:,.0f}} (matches tagged {confirm_cid}) [{{pk}}]",
                        "extra_concepts": [confirm_cid],
                        "extra_details": {"ambiguity": amb_id, "ic_confirmed": True},
                    }

    # 2. Check for rounding (residual < 0.01% of face)
    if face_val != 0 and abs(residual / face_val) < 0.0001:
        return {
            "category": Category.VALID_DISAGGREGATION,
            "severity": "INFO",
            "message": f"Disaggregation holds (rounding): {{face}}={{face_val:,.0f}}, SUM={{detail_sum:,.0f}}, Δ={{residual:,.0f}} (<0.01%) [{{pk}}]",
            "extra_details": {"ambiguity": "ROUNDING"},
        }

    # 3. Build ambiguity list for unconfirmed residual
    possible = [amb.get("id") for amb in edge.ambiguities if amb.get("id") != "ROUNDING"]

    return {
        "category": Category.IC_LEAKAGE,
        "severity": "INFO",
        "message": f"Disaggregation residual: {{face}}={{face_val:,.0f}}, SUM={{detail_sum:,.0f}}, Δ={{residual:,.0f}} — possible: {', '.join(possible) or 'unknown cause'} [{{pk}}]",
        "extra_details": {"ambiguity": "UNRESOLVED", "possible_causes": possible},
    }


def pass1_validate(graph: OntologyGraph, facts: dict) -> list[Finding]:
    """Validate all declared relationships against document facts."""
    findings = []
    period_keys = _get_period_keys(facts)
    # Use the two most recent year-based periods for validation
    year_keys = [k for k in period_keys if k.startswith("Y")][:2]
    if not year_keys:
        year_keys = period_keys[:2]

    # Summation trees
    for edge in graph.edges_by_type(EdgeType.SUMMATION):
        ctx = edge.parent_context or _infer_context(edge.parent)
        for pk in year_keys:
            parent_fact = _lookup_fact(facts, ctx, edge.parent, pk)
            if parent_fact is None:
                continue
            parent_val = parent_fact.amount

            child_vals = []
            missing = []
            for child_id in edge.children:
                child_ctx = edge.children_context or ctx
                cf = _lookup_fact(facts, child_ctx, child_id, pk)
                if cf is not None:
                    child_vals.append((child_id, cf.amount, cf))
                else:
                    missing.append(child_id)

            if not child_vals:
                continue

            # Skip if parent and children come from different magnitude tables
            # (e.g., 10-year overview in Mio vs primary statement in TEUR)
            parent_scale = parent_fact.value_col_count
            child_scales = [cf.value_col_count for _, _, cf in child_vals]
            if parent_scale > 4 and any(cs <= 4 for cs in child_scales):
                continue  # parent from summary table, children from primary — skip
            if parent_scale <= 4 and any(cs > 4 for cs in child_scales):
                continue  # mixed sources — skip

            child_sum = sum(v for _, v, _ in child_vals)
            delta = abs(parent_val - child_sum)

            if delta <= TOLERANCE:
                findings.append(Finding(
                    category=Category.VALID_DISAGGREGATION,
                    edge_name=edge.name,
                    expected=parent_val,
                    actual=child_sum,
                    delta=delta,
                    concepts=[edge.parent] + [c for c, _, _ in child_vals],
                    message=f"Summation holds: {edge.parent} = SUM({', '.join(c for c,_,_ in child_vals)}) [{pk}]",
                    details={"period": pk, "missing_children": missing},
                ))
            elif edge.partial:
                findings.append(Finding(
                    category=Category.VALID_DISAGGREGATION,
                    edge_name=edge.name,
                    severity="INFO",
                    expected=parent_val,
                    actual=child_sum,
                    delta=delta,
                    concepts=[edge.parent] + [c for c, _, _ in child_vals],
                    message=f"Partial summation: {edge.parent}={parent_val:,.0f}, SUM(children)={child_sum:,.0f}, Δ={delta:,.0f} (unallocated) [{pk}]",
                    details={"period": pk, "partial": True, "missing_children": missing},
                ))
            else:
                findings.append(Finding(
                    category=Category.BROKEN_RELATIONSHIP,
                    edge_name=edge.name,
                    severity="ERROR",
                    expected=parent_val,
                    actual=child_sum,
                    delta=delta,
                    concepts=[edge.parent] + [c for c, _, _ in child_vals],
                    message=f"Summation BROKEN: {edge.parent}={parent_val:,.0f} ≠ SUM({', '.join(c for c,_,_ in child_vals)})={child_sum:,.0f}, Δ={delta:,.0f} [{pk}]",
                    details={"period": pk, "missing_children": missing},
                ))

    # Cross-statement ties
    for edge in graph.edges_by_type(EdgeType.CROSS_STATEMENT_TIE):
        for pk in year_keys:
            trigger_val = _lookup(facts, edge.trigger_context, edge.trigger_concept, pk)
            requires_val = _lookup(facts, edge.requires_context, edge.requires_concept, pk)

            if trigger_val is None or requires_val is None:
                continue

            if edge.check == "equals":
                delta = abs(trigger_val - requires_val)
            elif "+" in edge.check and "= 0" in edge.check:
                delta = abs(trigger_val + requires_val)
            else:
                delta = abs(trigger_val - requires_val)

            if delta <= TOLERANCE:
                findings.append(Finding(
                    category=Category.VALID_TIE,
                    edge_name=edge.name,
                    expected=trigger_val,
                    actual=requires_val,
                    delta=delta,
                    concepts=[edge.trigger_concept, edge.requires_concept],
                    message=f"Cross-statement tie holds: {edge.trigger_concept} ({edge.trigger_context}) ↔ {edge.requires_concept} ({edge.requires_context}) [{pk}]",
                    details={"period": pk},
                ))
            else:
                findings.append(Finding(
                    category=Category.BROKEN_RELATIONSHIP,
                    edge_name=edge.name,
                    severity=edge.severity,
                    expected=trigger_val,
                    actual=requires_val,
                    delta=delta,
                    concepts=[edge.trigger_concept, edge.requires_concept],
                    message=f"Cross-statement tie BROKEN: {edge.trigger_concept}={trigger_val:,.0f} ≠ {edge.requires_concept}={requires_val:,.0f}, Δ={delta:,.0f} [{pk}]",
                    details={"period": pk},
                ))

    # Note-to-face ties
    for edge in graph.edges_by_type(EdgeType.NOTE_TO_FACE):
        for pk in year_keys:
            face_val = _lookup(facts, edge.face_context, edge.face_concept, pk)
            if face_val is None:
                continue

            # Note total: either a single concept or SUM of concepts
            note_val = None
            if edge.note_concept:
                note_val = _lookup(facts, edge.note_context, edge.note_concept, pk)
            elif edge.note_sum_concepts:
                total = 0.0
                found_any = False
                for nc in edge.note_sum_concepts:
                    nv = _lookup(facts, edge.note_context, nc, pk)
                    if nv is not None:
                        total += nv
                        found_any = True
                if found_any:
                    note_val = total

            if note_val is None:
                continue

            delta = abs(face_val - note_val)

            if delta <= TOLERANCE:
                findings.append(Finding(
                    category=Category.VALID_TIE,
                    edge_name=edge.name,
                    expected=face_val,
                    actual=note_val,
                    delta=delta,
                    concepts=[edge.face_concept, edge.note_concept or "SUM(...)"],
                    message=f"Note ties to face: {edge.face_concept} ({edge.face_context}) = note total ({edge.note_context}) [{pk}]",
                    details={"period": pk},
                ))
            else:
                # Triage using ambiguities
                possible = [a.get("id") for a in edge.ambiguities]
                sev = edge.severity
                # Downgrade to INFO if rounding
                if face_val != 0 and abs(delta / face_val) < 0.0001:
                    sev = "INFO"
                    possible = ["ROUNDING"]

                findings.append(Finding(
                    category=Category.BROKEN_RELATIONSHIP,
                    edge_name=edge.name,
                    severity=sev,
                    expected=face_val,
                    actual=note_val,
                    delta=delta,
                    concepts=[edge.face_concept, edge.note_concept or "SUM(...)"],
                    message=f"Note ≠ face: {edge.face_concept}={face_val:,.0f} ≠ note({edge.note_context})={note_val:,.0f}, Δ={delta:,.0f} — possible: {', '.join(possible) or 'unknown'} [{pk}]",
                    details={"period": pk, "possible_causes": possible},
                ))

    # Disaggregation ties
    for edge in graph.edges_by_type(EdgeType.DISAGGREGATION):
        for pk in year_keys:
            face_val = _lookup(facts, edge.face_context, edge.face_concept, pk)
            if face_val is None:
                continue

            detail_sum = 0.0
            detail_found = False
            for dc in edge.detail_concepts:
                dv = _sum_by_axis(facts, edge.detail_context, dc, pk)
                if dv is not None:
                    detail_sum += dv
                    detail_found = True

            if not detail_found:
                continue

            delta = abs(face_val - detail_sum)

            if delta <= TOLERANCE:
                findings.append(Finding(
                    category=Category.VALID_DISAGGREGATION,
                    edge_name=edge.name,
                    expected=face_val,
                    actual=detail_sum,
                    delta=delta,
                    concepts=[edge.face_concept] + edge.detail_concepts,
                    message=f"Disaggregation holds: {edge.face_concept} ({edge.face_context}) = SUM({edge.detail_context}) [{pk}]",
                    details={"period": pk},
                ))
            elif edge.ic_residual:
                residual = face_val - detail_sum
                # Triage the residual using ontology ambiguities
                triage = _triage_residual(edge, residual, face_val, facts, pk)
                findings.append(Finding(
                    category=triage["category"],
                    edge_name=edge.name,
                    severity=triage["severity"],
                    expected=face_val,
                    actual=detail_sum,
                    delta=delta,
                    concepts=[edge.face_concept] + edge.detail_concepts + triage.get("extra_concepts", []),
                    message=triage["message"].format(
                        face=edge.face_concept, face_val=face_val,
                        detail_sum=detail_sum, residual=residual, pk=pk,
                    ),
                    details={"period": pk, "residual": residual, **triage.get("extra_details", {})},
                ))
            else:
                findings.append(Finding(
                    category=Category.BROKEN_RELATIONSHIP,
                    edge_name=edge.name,
                    severity="WARNING",
                    expected=face_val,
                    actual=detail_sum,
                    delta=delta,
                    concepts=[edge.face_concept] + edge.detail_concepts,
                    message=f"Disaggregation BROKEN: {edge.face_concept}={face_val:,.0f} ≠ SUM({edge.detail_context})={detail_sum:,.0f}, Δ={delta:,.0f} [{pk}]",
                    details={"period": pk},
                ))

    # IC decomposition
    for edge in graph.edges_by_type(EdgeType.IC_DECOMPOSITION):
        face_ctx = _infer_context(edge.ic_face_concept)
        for pk in year_keys:
            face_val = _lookup(facts, face_ctx, edge.ic_face_concept, pk)
            if face_val is None:
                continue

            ext_val = None
            if edge.ic_external_concept:
                ext_ctx = _infer_context(edge.ic_external_concept)
                ext_val = _sum_by_axis(facts, ext_ctx, edge.ic_external_concept, pk)

            ic_val = None
            if edge.ic_concept:
                ic_ctx = _infer_context(edge.ic_concept)
                ic_val = _sum_by_axis(facts, ic_ctx, edge.ic_concept, pk)

            if ext_val is None:
                continue

            ic_amount = ic_val or 0
            expected = ext_val + ic_amount
            delta = abs(face_val - expected)

            if delta <= TOLERANCE:
                findings.append(Finding(
                    category=Category.VALID_DISAGGREGATION,
                    edge_name=edge.name,
                    expected=face_val,
                    actual=expected,
                    delta=delta,
                    concepts=[edge.ic_face_concept, edge.ic_external_concept or "", edge.ic_concept or ""],
                    message=f"IC decomposition valid: {edge.ic_face_concept}={face_val:,.0f} = external({ext_val:,.0f}) + IC({ic_amount:,.0f}) [{pk}]",
                    details={"period": pk},
                ))
            elif ic_amount == 0 and delta > TOLERANCE:
                findings.append(Finding(
                    category=Category.IC_LEAKAGE,
                    edge_name=edge.name,
                    severity="WARNING",
                    expected=face_val,
                    actual=ext_val,
                    delta=delta,
                    concepts=[edge.ic_face_concept, edge.ic_external_concept or ""],
                    message=f"IC LEAKAGE: {edge.ic_face_concept}={face_val:,.0f}, external={ext_val:,.0f}, IC not tagged, Δ={delta:,.0f} [{pk}]",
                    details={"period": pk, "ic_missing": True},
                ))
            else:
                findings.append(Finding(
                    category=Category.BROKEN_RELATIONSHIP,
                    edge_name=edge.name,
                    severity="ERROR",
                    expected=face_val,
                    actual=expected,
                    delta=delta,
                    concepts=[edge.ic_face_concept, edge.ic_external_concept or "", edge.ic_concept or ""],
                    message=f"IC decomposition BROKEN: {edge.ic_face_concept}={face_val:,.0f} ≠ external({ext_val:,.0f}) + IC({ic_amount:,.0f}) = {expected:,.0f} [{pk}]",
                    details={"period": pk},
                ))

    return findings


# ── Pass 2: Explain known mismatch patterns ────────────────────────

def load_mismatch_patterns(repo_root: str) -> list[dict]:
    """Load mismatch_patterns.yaml."""
    mp_path = Path(repo_root) / "mismatch_patterns.yaml"
    if not mp_path.exists():
        return []
    with open(mp_path) as f:
        data = yaml.safe_load(f)
    return data.get("mismatch_patterns", [])


def _build_cross_table_amounts(facts: dict) -> list[dict]:
    """Find amounts that appear in multiple tables (potential cross-references)."""
    # Group by concept across tables (deduplicate across periods)
    by_concept: dict[str, list[Fact]] = defaultdict(list)
    for (ctx, cid, period), fact_list in facts.items():
        for f in fact_list:
            by_concept[cid].append(f)
    # Use concept-level grouping for mismatch detection (not per-period)
    by_concept_period: dict[tuple[str, str], list[Fact]] = defaultdict(list)
    for (ctx, cid, period), fact_list in facts.items():
        for f in fact_list:
            by_concept_period[(cid, period)].append(f)

    # Also group by normalized amount across tables
    by_amount: dict[float, list[Fact]] = defaultdict(list)
    for fact_list in facts.values():
        for f in fact_list:
            if abs(f.amount) >= 100:  # skip trivial
                by_amount[f.amount].append(f)

    cross_table = []
    seen_concept_mismatches = set()

    # Same concept in different tables (deduplicated: one finding per concept)
    for (cid, period), flist in by_concept_period.items():
        if cid in seen_concept_mismatches:
            continue
        tables = set(f.table_id for f in flist)
        if len(tables) > 1:
            amounts = [f.amount for f in flist]
            if len(set(amounts)) > 1:  # different amounts → potential mismatch
                cross_table.append({
                    "type": "concept_mismatch",
                    "concept": cid,
                    "period": period,
                    "facts": flist,
                    "amounts": amounts,
                })
                seen_concept_mismatches.add(cid)

    # Same amount in different tables (brute force — limited to significant amounts)
    for amount, flist in by_amount.items():
        tables = set(f.table_id for f in flist)
        if len(tables) > 1:
            concepts = set(f.concept_id for f in flist)
            if len(concepts) > 1:
                cross_table.append({
                    "type": "amount_match",
                    "amount": amount,
                    "facts": flist,
                    "concepts": list(concepts),
                })

    return cross_table


def pass2_explain(
    graph: OntologyGraph,
    facts: dict,
    patterns: list[dict],
    pass1_findings: list[Finding],
) -> list[Finding]:
    """Check for known mismatch patterns in unexplained cross-table observations."""
    findings = []

    # Concepts already explained by Pass 1
    explained_concepts = set()
    for f in pass1_findings:
        for c in f.concepts:
            if c:
                explained_concepts.add(c)

    cross_table = _build_cross_table_amounts(facts)

    for obs in cross_table:
        if obs["type"] == "concept_mismatch":
            cid = obs["concept"]
            if cid in explained_concepts:
                continue

            concept_meta = graph.concepts.get(cid)
            flist = obs["facts"]
            amounts = obs["amounts"]

            # Check SHARE_COUNT_VS_MONETARY
            if concept_meta and concept_meta.note_unit_type == "shares":
                findings.append(Finding(
                    category=Category.EXPLAINED_MISMATCH,
                    pattern_id="SHARE_COUNT_VS_MONETARY",
                    severity="INFO",
                    concepts=[cid],
                    table_ids=[f.table_id for f in flist],
                    message=f"Unit mismatch: {cid} appears as monetary and share count in different tables",
                    details={"amounts": amounts},
                ))
                continue

            # Check GROSS_VS_NET (concept has measurement_variants)
            if concept_meta and concept_meta.measurement_variants:
                findings.append(Finding(
                    category=Category.EXPLAINED_MISMATCH,
                    pattern_id="GROSS_VS_NET",
                    severity="INFO",
                    concepts=[cid],
                    table_ids=[f.table_id for f in flist],
                    message=f"Measurement mismatch: {cid} has cost/FV variants — face vs note may differ",
                    details={"amounts": amounts, "variants": [v.get("model") for v in concept_meta.measurement_variants]},
                ))
                continue

            # Check UNIT_SCALE
            if len(amounts) >= 2:
                found_scale = False
                for i, a1 in enumerate(amounts):
                    if found_scale:
                        break
                    for a2 in amounts[i + 1:]:
                        if a1 != 0 and a2 != 0:
                            ratio = abs(a1 / a2)
                            if 990 < ratio < 1010 or 990000 < ratio < 1010000:
                                findings.append(Finding(
                                    category=Category.EXPLAINED_MISMATCH,
                                    pattern_id="UNIT_SCALE",
                                    severity="INFO",
                                    concepts=[cid],
                                    table_ids=list(set(f.table_id for f in flist)),
                                    message=f"Unit scale difference: {cid} values differ by ×{ratio:,.0f}",
                                    details={"amounts": list(set(amounts)), "ratio": ratio},
                                ))
                                found_scale = True
                                break

        elif obs["type"] == "amount_match":
            # Same amount, different concepts across tables
            concepts = obs.get("concepts", [])
            if any(c in explained_concepts for c in concepts):
                continue

            flist = obs["facts"]
            labels = [f.label.lower() for f in flist]

            # Check GENERIC_LABEL_COLLISION
            generic = ["other", "total", "thereof", "davon", "summe", "gesamt", "sonstige"]
            if any(any(g in lbl for g in generic) for lbl in labels):
                # Suppress — too generic
                continue

            # Check ASSOCIATE_OWN_FIGURES
            contexts = set(f.context for f in flist)
            if "DISC.ASSOCIATES" in contexts:
                findings.append(Finding(
                    category=Category.EXPLAINED_MISMATCH,
                    pattern_id="ASSOCIATE_OWN_FIGURES",
                    severity="INFO",
                    concepts=list(concepts),
                    table_ids=[f.table_id for f in flist],
                    message=f"Associate own figures: amount {obs['amount']:,.0f} appears in DISC.ASSOCIATES and primary statements",
                    details={"amount": obs["amount"]},
                ))

    return findings


# ── Pass 3: Flag unexplained inconsistencies ───────────────────────

# Labels that indicate PNL-structure content (should not appear in OCI)
_PNL_LABELS = re.compile(
    r'\b(revenue|revenues|umsatz|erlös|cost of (sales|goods)|gross profit|'
    r'ebitda|ebit|operating (profit|result|loss)|betriebsergebnis|'
    r'profit before tax|ergebnis vor steuern|income tax|ertragsteuer|'
    r'net profit|jahresüberschuss|selling expenses|admin|verwaltung)\b',
    re.IGNORECASE
)

# Labels that indicate SFP-structure content
_SFP_LABELS = re.compile(
    r'\b(total assets|summe aktiva|total equity|eigenkapital|'
    r'non-current (assets|liabilities)|current (assets|liabilities))\b',
    re.IGNORECASE
)


def pass3_unexplained(
    graph: OntologyGraph,
    facts: dict,
    tables: list[dict],
    pass1_findings: list[Finding],
    pass2_findings: list[Finding],
) -> list[Finding]:
    """Flag cross-table observations not explained by Pass 1 or Pass 2."""
    findings = []

    # Collect all explained table+concept pairs
    explained_keys = set()
    for f in pass1_findings + pass2_findings:
        for c in f.concepts:
            for tid in f.table_ids:
                explained_keys.add((tid, c))
        for c in f.concepts:
            if c:
                explained_keys.add(("*", c))

    # 1. Context-concept validation for preTagged facts
    for (ctx, cid, pk), fact_list in facts.items():
        if not cid or ctx == "NOTES" or ctx is None:
            continue

        concept_meta = graph.concepts.get(cid)
        if not concept_meta:
            continue

        valid = concept_meta.valid_contexts
        if valid and ctx not in valid:
            if ctx == "DISC.ASSOCIATES":
                continue
            if ctx.startswith("DISC."):
                continue

            for fact in fact_list:
                if ("*", cid) in explained_keys:
                    continue
                findings.append(Finding(
                    category=Category.UNEXPLAINED_INCONSISTENCY,
                    severity="WARNING",
                    table_ids=[fact.table_id],
                    concepts=[cid],
                    message=f"Context mismatch: {cid} found in {ctx} but valid_contexts={valid} (table {fact.table_id}, page {fact.page})",
                    details={"context": ctx, "valid_contexts": valid, "label": fact.label, "page": fact.page},
                ))

    # 2. Label-based context validation: detect misclassified tables
    #    (e.g., OCI table with PNL-structure labels → likely associate summary)
    seen_tables = set()
    for table in tables:
        table_id = table["tableId"]
        sc = table.get("metadata", {}).get("statementComponent")
        if not sc or sc == "NOTES":
            continue

        labels = [r.get("label", "") or "" for r in table.get("rows", [])]
        data_rows = [r for r in table.get("rows", [])
                     if r.get("rowType") in ("DATA", "TOTAL_EXPLICIT", "TOTAL_IMPLICIT")]
        pnl_matches = sum(1 for l in labels if _PNL_LABELS.search(l))
        sfp_matches = sum(1 for l in labels if _SFP_LABELS.search(l))

        # OCI table with PNL-structure labels
        if sc == "OCI" and pnl_matches >= 2:
            forbidden_labels = [l for l in labels if _PNL_LABELS.search(l)]
            findings.append(Finding(
                category=Category.UNEXPLAINED_INCONSISTENCY,
                severity="WARNING",
                table_ids=[table_id],
                message=f"OCI table contains PNL-structure labels: {forbidden_labels[:3]} (table {table_id}, page {table.get('pageNo', '?')})",
                details={
                    "context": sc,
                    "pnl_labels": forbidden_labels[:5],
                    "page": table.get("pageNo"),
                    "suggestion": "Likely IAS 28 associate summary or segment P&L — reclassify to DISC.ASSOCIATES",
                },
            ))

        # Small table with mixed PNL + SFP → likely associate summary
        if len(data_rows) <= 8 and pnl_matches >= 2 and sfp_matches >= 1:
            if sc not in ("DISC.ASSOCIATES", None):
                findings.append(Finding(
                    category=Category.UNEXPLAINED_INCONSISTENCY,
                    severity="INFO",
                    table_ids=[table_id],
                    message=f"Small table ({len(data_rows)} rows) with PNL + SFP structure — likely associate summary (table {table_id}, page {table.get('pageNo', '?')})",
                    details={
                        "context": sc,
                        "row_count": len(data_rows),
                        "page": table.get("pageNo"),
                        "suggestion": "Reclassify to DISC.ASSOCIATES",
                    },
                ))

    return findings


# ── Main orchestrator ──────────────────────────────────────────────

def check_document(tables: list[dict], ontology_root: str) -> list[Finding]:
    """Run the three-pass consistency check on a document."""
    # Build ontology graph
    graph = build_graph(ontology_root)

    # Index facts
    facts = index_facts(tables)

    # Pass 1
    p1 = pass1_validate(graph, facts)

    # Pass 2
    patterns = load_mismatch_patterns(ontology_root)
    p2 = pass2_explain(graph, facts, patterns, p1)

    # Pass 3
    p3 = pass3_unexplained(graph, facts, tables, p1, p2)

    return p1 + p2 + p3


def check_against_expected(findings: list[Finding], expected_path: str) -> tuple[list[str], list[str]]:
    """Check findings against expected violations fixture.

    Returns (pass_messages, fail_messages).
    """
    with open(expected_path) as f:
        expected = json.load(f)

    passes = []
    fails = []

    for exp in expected.get("expected_violations", []):
        cat = exp.get("category")
        pattern = exp.get("pattern_id")
        concept = exp.get("concept")
        edge = exp.get("edge_name")

        matched = False
        for finding in findings:
            if cat and finding.category.value != cat:
                continue
            if pattern and finding.pattern_id != pattern:
                continue
            if concept and concept not in finding.concepts:
                continue
            if edge and finding.edge_name != edge:
                continue
            matched = True
            break

        desc = exp.get("description", f"{cat} {concept or edge or pattern}")
        if matched:
            passes.append(f"PASS: {desc}")
        else:
            fails.append(f"FAIL: expected {desc} not found")

    # Check for unexpected errors
    for finding in findings:
        if finding.severity == "ERROR" and finding.category == Category.BROKEN_RELATIONSHIP:
            # Check if this was expected
            was_expected = False
            for exp in expected.get("expected_violations", []):
                if exp.get("category") == "BROKEN_RELATIONSHIP":
                    was_expected = True
                    break
            if not was_expected:
                fails.append(f"UNEXPECTED ERROR: {finding.message}")

    return passes, fails


def main():
    import argparse

    parser = argparse.ArgumentParser(description="FOBE three-pass consistency checker")
    parser.add_argument("document", help="Path to table_graphs.json")
    parser.add_argument("--ontology-root", default=None, help="Path to FOBE repo root")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--check", default=None, help="Path to expected_violations.json fixture")
    args = parser.parse_args()

    # Determine ontology root
    ontology_root = args.ontology_root
    if not ontology_root:
        ontology_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Load document
    with open(args.document) as f:
        data = json.load(f)
    tables = data.get("tables", [])

    # Run check
    findings = check_document(tables, ontology_root)

    if args.check:
        passes, fails = check_against_expected(findings, args.check)
        print(f"\n{'=' * 60}")
        print(f"Fixture check: {args.check}")
        print(f"{'=' * 60}")
        for p in passes:
            print(f"  ✅ {p}")
        for f_ in fails:
            print(f"  ❌ {f_}")
        print(f"\nResult: {len(passes)} passed, {len(fails)} failed")
        return 1 if fails else 0

    if args.json:
        output = {
            "tables_checked": len(tables),
            "findings": [f.to_dict() for f in findings],
            "summary": {},
        }
        for f in findings:
            cat = f.category.value
            output["summary"][cat] = output["summary"].get(cat, 0) + 1
        print(json.dumps(output, indent=2))
        return 0

    # Human-readable output
    by_category: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_category[f.category.value].append(f)

    print(f"\n{'=' * 70}")
    print(f"FOBE Consistency Check: {len(tables)} tables, {len(findings)} findings")
    print(f"{'=' * 70}")

    category_order = [
        Category.VALID_DISAGGREGATION,
        Category.VALID_TIE,
        Category.BROKEN_RELATIONSHIP,
        Category.IC_LEAKAGE,
        Category.EXPLAINED_MISMATCH,
        Category.UNEXPLAINED_INCONSISTENCY,
    ]
    icons = {
        Category.VALID_DISAGGREGATION: "✅",
        Category.VALID_TIE: "✅",
        Category.BROKEN_RELATIONSHIP: "❌",
        Category.IC_LEAKAGE: "⚠️",
        Category.EXPLAINED_MISMATCH: "ℹ️",
        Category.UNEXPLAINED_INCONSISTENCY: "❓",
    }

    for cat in category_order:
        flist = by_category.get(cat.value, [])
        if not flist:
            continue
        icon = icons.get(cat, "?")
        print(f"\n{'─' * 70}")
        print(f"{icon} {cat.value} ({len(flist)})")
        print(f"{'─' * 70}")
        for f in flist:
            print(f"  [{f.severity}] {f.message}")

    # Summary
    print(f"\n{'=' * 70}")
    print(f"SUMMARY")
    for cat in category_order:
        count = len(by_category.get(cat.value, []))
        if count:
            icon = icons.get(cat, "?")
            print(f"  {icon} {cat.value}: {count}")

    errors = len(by_category.get(Category.BROKEN_RELATIONSHIP.value, []))
    ic_leak = len(by_category.get(Category.IC_LEAKAGE.value, []))
    return 1 if errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
