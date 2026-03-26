#!/usr/bin/env python3
"""
relationship_graph.py — Build a directed relationship graph from the FOBE ontology.

Loads counterparts.yaml + concept metadata to produce a static graph of all
declared relationships between (context, concept) pairs.

Edge types:
  SUMMATION           — parent concept = SUM(children)
  DISAGGREGATION      — face concept = SUM(detail concepts along axis)
  CROSS_STATEMENT_TIE — two concepts across statements must be equal
  IC_DECOMPOSITION    — face = external + IC (residual should be zero)
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml


class EdgeType(Enum):
    SUMMATION = "SUMMATION"
    DISAGGREGATION = "DISAGGREGATION"
    CROSS_STATEMENT_TIE = "CROSS_STATEMENT_TIE"
    IC_DECOMPOSITION = "IC_DECOMPOSITION"
    NOTE_TO_FACE = "NOTE_TO_FACE"
    DIVISION = "DIVISION"


@dataclass
class GraphEdge:
    edge_type: EdgeType
    name: str
    # For SUMMATION
    parent: Optional[str] = None          # concept id
    parent_context: Optional[str] = None
    children: list[str] = field(default_factory=list)  # concept ids
    children_context: Optional[str] = None
    partial: bool = False                 # partial sums allowed (unallocated remainder)
    # For DISAGGREGATION
    face_context: Optional[str] = None
    face_concept: Optional[str] = None
    detail_context: Optional[str] = None
    detail_concepts: list[str] = field(default_factory=list)
    detail_axis: Optional[str] = None
    ic_residual: bool = False             # allow IC residual in sum
    residual_confirm: Optional[dict] = None  # {concept, context} to confirm IC residual
    # Ambiguities: known reasons a residual/mismatch can exist
    ambiguities: list[dict] = field(default_factory=list)
    # For CROSS_STATEMENT_TIE
    trigger_context: Optional[str] = None
    trigger_concept: Optional[str] = None
    requires_context: Optional[str] = None
    requires_concept: Optional[str] = None
    check: str = "equals"
    severity: str = "WARNING"
    # For NOTE_TO_FACE
    note_context: Optional[str] = None
    note_concept: Optional[str] = None
    note_sum_concepts: list[str] = field(default_factory=list)  # if note total = SUM(concepts)
    # For IC_DECOMPOSITION
    ic_face_concept: Optional[str] = None
    ic_external_concept: Optional[str] = None
    ic_concept: Optional[str] = None
    # For DIVISION
    numerator_concept: Optional[str] = None
    denominator_concept: Optional[str] = None
    result_concept: Optional[str] = None
    tolerance: float = 0.02
    is_subtraction: bool = False  # special case: result = numerator - denominator


@dataclass
class ConceptMeta:
    """Metadata extracted from concept YAML for consistency checking."""
    concept_id: str
    label: str = ""
    unit_type: str = "monetary"
    note_unit_type: Optional[str] = None
    valid_contexts: list[str] = field(default_factory=list)
    has_ic_variant: bool = False
    ic_concept: Optional[str] = None
    disaggregation_targets: list[dict] = field(default_factory=list)
    measurement_variants: list[dict] = field(default_factory=list)
    is_total: bool = False
    balance_type: str = "debit"


@dataclass
class OntologyGraph:
    """The complete relationship graph built from the ontology."""
    edges: list[GraphEdge] = field(default_factory=list)
    concepts: dict[str, ConceptMeta] = field(default_factory=dict)

    def edges_by_type(self, edge_type: EdgeType) -> list[GraphEdge]:
        return [e for e in self.edges if e.edge_type == edge_type]


def _infer_context(concept_id: str) -> str:
    """Infer the default context from a concept ID prefix."""
    prefix_map = {
        "FS.PNL.": "PNL",
        "FS.SFP.": "SFP",
        "FS.OCI.": "OCI",
        "FS.CFS.": "CFS",
        "FS.SOCIE.": "SOCIE",
    }
    for prefix, ctx in prefix_map.items():
        if concept_id.startswith(prefix):
            return ctx
    # Disclosure concepts: DISC.SEGMENTS.X → DISC.SEGMENTS
    parts = concept_id.split(".")
    if len(parts) >= 2 and parts[0] == "DISC":
        return f"{parts[0]}.{parts[1]}"
    return "UNKNOWN"


def load_concepts(repo_root: str) -> dict[str, ConceptMeta]:
    """Load all concept definitions from concepts/*.yaml and concepts/disc/*.yaml."""
    concepts = {}
    concepts_dir = Path(repo_root) / "concepts"

    yaml_files = list(concepts_dir.glob("*.yaml")) + list(
        (concepts_dir / "disc").glob("*.yaml")
    )

    for fpath in yaml_files:
        with open(fpath) as f:
            data = yaml.safe_load(f)
        if not data or "concepts" not in data:
            continue
        for c in data["concepts"]:
            cid = c.get("id", "")
            meta = ConceptMeta(
                concept_id=cid,
                label=c.get("label", ""),
                unit_type=c.get("unit_type", "monetary"),
                note_unit_type=c.get("note_unit_type"),
                valid_contexts=c.get("valid_contexts", []),
                has_ic_variant=c.get("has_ic_variant", False),
                ic_concept=c.get("ic_concept"),
                disaggregation_targets=c.get("disaggregation_targets", []),
                measurement_variants=c.get("measurement_variants", []),
                is_total=c.get("is_total", False),
                balance_type=c.get("balance_type", "debit"),
            )
            # If valid_contexts not explicitly set, infer from ID
            if not meta.valid_contexts:
                inferred = _infer_context(cid)
                if inferred != "UNKNOWN":
                    meta.valid_contexts = [inferred]
            concepts[cid] = meta

    return concepts


def load_counterparts(repo_root: str) -> dict:
    """Load counterparts.yaml."""
    cp_path = Path(repo_root) / "counterparts.yaml"
    with open(cp_path) as f:
        return yaml.safe_load(f)


def build_graph(repo_root: str) -> OntologyGraph:
    """Build the complete ontology relationship graph."""
    concepts = load_concepts(repo_root)
    counterparts = load_counterparts(repo_root)
    edges: list[GraphEdge] = []

    # 1. Summation trees from counterparts.yaml
    for tree in counterparts.get("summation_trees", []):
        parent_id = tree["parent"]
        parent_ctx = _infer_context(parent_id)
        children_ids = tree["children"]
        edges.append(GraphEdge(
            edge_type=EdgeType.SUMMATION,
            name=f"sum_{parent_id}",
            parent=parent_id,
            parent_context=parent_ctx,
            children=children_ids,
            children_context=parent_ctx,
            partial=tree.get("partial", False),
        ))

    # 2. Cross-statement ties from counterparts.yaml
    for tie in counterparts.get("cross_statement_ties", []):
        edges.append(GraphEdge(
            edge_type=EdgeType.CROSS_STATEMENT_TIE,
            name=tie["name"],
            trigger_context=tie["trigger"]["context"],
            trigger_concept=tie["trigger"]["concept"],
            requires_context=tie["requires"]["context"],
            requires_concept=tie["requires"]["concept"],
            check=tie.get("check", "equals"),
            severity=tie.get("severity", "ERROR"),
            ambiguities=tie.get("ambiguities", []),
        ))

    # 3. Disaggregation ties from counterparts.yaml
    for tie in counterparts.get("disaggregation_ties", []):
        detail_concepts = tie.get("concepts", [])
        edges.append(GraphEdge(
            edge_type=EdgeType.DISAGGREGATION,
            name=tie["name"],
            face_context=tie["face"]["context"],
            face_concept=tie["face"]["concept"],
            detail_context=tie["detail"].get("context"),
            detail_concepts=detail_concepts if detail_concepts else [tie["detail"].get("concept", "")],
            detail_axis=tie["detail"].get("axis"),
            ic_residual="residual" in tie.get("check", ""),
            residual_confirm=tie.get("residual_confirm"),
            severity=tie.get("severity", "WARNING"),
            ambiguities=tie.get("ambiguities", []),
        ))

    # 4. Note-to-face ties from counterparts.yaml
    for tie in counterparts.get("note_to_face_ties", []):
        note_total = tie.get("note_total", {})
        # note_total can be a simple {context, concept} or a {check: "SUM(...)", context}
        note_concepts = []
        note_concept = None
        if isinstance(note_total, dict):
            note_concept = note_total.get("concept")
            check_str = note_total.get("check", "")
            if check_str.startswith("SUM("):
                # Parse SUM(CONCEPT1, CONCEPT2) syntax
                inner = check_str[4:].rstrip(")")
                note_concepts = [c.strip() for c in inner.split(",")]
        edges.append(GraphEdge(
            edge_type=EdgeType.NOTE_TO_FACE,
            name=tie["name"],
            face_context=tie["face"]["context"],
            face_concept=tie["face"]["concept"],
            note_context=note_total.get("context") if isinstance(note_total, dict) else None,
            note_concept=note_concept,
            note_sum_concepts=note_concepts,
            severity=tie.get("severity", "WARNING"),
            ambiguities=tie.get("ambiguities", []),
        ))

    # 5. IC decomposition from counterparts.yaml
    for ic in counterparts.get("ic_decomposition", []):
        edges.append(GraphEdge(
            edge_type=EdgeType.IC_DECOMPOSITION,
            name=ic["name"],
            ic_face_concept=ic["face_concept"],
            ic_external_concept=ic.get("external_concept"),
            ic_concept=ic.get("ic_concept"),
            ambiguities=ic.get("ambiguities", []),
        ))

    # 6. Division relationships from counterparts.yaml
    for div in counterparts.get("division_relationships", []):
        edges.append(GraphEdge(
            edge_type=EdgeType.DIVISION,
            name=div["name"],
            numerator_concept=div["numerator"]["concept"],
            denominator_concept=div["denominator"]["concept"],
            result_concept=div["result"]["concept"],
            tolerance=div.get("tolerance", 0.02),
            is_subtraction=div.get("denominator_is_subtraction", False),
            check=div.get("check", "result = numerator / denominator"),
            ambiguities=div.get("ambiguities", []),
        ))

    # 5. Disaggregation targets from enriched concept metadata
    for cid, meta in concepts.items():
        for target in meta.disaggregation_targets:
            # Skip if already covered by counterparts.yaml disaggregation_ties
            target_ctx = target.get("context", "")
            target_concepts = target.get("concepts", [])
            target_concept = target.get("concept")
            if target_concept:
                target_concepts = [target_concept]

            already_covered = any(
                e.face_concept == cid
                and e.detail_context == target_ctx
                for e in edges
                if e.edge_type == EdgeType.DISAGGREGATION
            )
            if not already_covered and target_concepts:
                edges.append(GraphEdge(
                    edge_type=EdgeType.DISAGGREGATION,
                    name=f"concept_{cid}_to_{target_ctx}",
                    face_context=_infer_context(cid),
                    face_concept=cid,
                    detail_context=target_ctx,
                    detail_concepts=target_concepts,
                    detail_axis=target.get("axis"),
                ))

    graph = OntologyGraph(edges=edges, concepts=concepts)
    return graph


def print_graph_summary(graph: OntologyGraph) -> None:
    """Print a summary of the relationship graph."""
    by_type = {}
    for e in graph.edges:
        by_type.setdefault(e.edge_type.value, []).append(e)

    print(f"Ontology Graph: {len(graph.concepts)} concepts, {len(graph.edges)} edges")
    for etype, elist in sorted(by_type.items()):
        print(f"  {etype}: {len(elist)}")
        for e in elist:
            print(f"    - {e.name}")


if __name__ == "__main__":
    import sys

    repo_root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    graph = build_graph(repo_root)
    print_graph_summary(graph)
