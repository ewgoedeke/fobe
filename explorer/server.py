#!/usr/bin/env python3
"""
FOBE Ontology Explorer — FastAPI backend.

Serves the ontology graph as JSON endpoints for the React force-graph frontend.
Supports expand-on-click: initially shows collapsed context nodes, then expands
to show individual concepts when a context is clicked.

Usage:
    cd explorer && python server.py
    # or: uvicorn server:app --reload --port 8787
"""

import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# Allow importing from eval/
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "eval"))
from relationship_graph import EdgeType, OntologyGraph, build_graph, _infer_context

app = FastAPI(title="FOBE Ontology Explorer")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── Cache the graph on startup ─────────────────────────────
_graph: OntologyGraph | None = None
_context_index: dict = {}  # ctx -> list of concept_ids
_edge_index: dict = {}     # concept_id -> list of edge dicts


def get_graph() -> OntologyGraph:
    global _graph, _context_index, _edge_index
    if _graph is None:
        _graph = build_graph(str(REPO_ROOT))
        _build_indices()
    return _graph


def _build_indices():
    """Pre-compute context membership and per-concept edge lookups."""
    global _context_index, _edge_index
    _context_index.clear()
    _edge_index.clear()

    for cid, meta in _graph.concepts.items():
        ctx = meta.valid_contexts[0] if meta.valid_contexts else _infer_context(cid)
        _context_index.setdefault(ctx, []).append(cid)

    # Index edges by involved concepts
    for edge in _graph.edges:
        involved = _edge_involved_concepts(edge)
        for cid in involved:
            _edge_index.setdefault(cid, []).append(edge)


def _edge_involved_concepts(edge) -> set[str]:
    """Return all concept IDs involved in an edge."""
    ids = set()
    if edge.parent:
        ids.add(edge.parent)
    ids.update(edge.children)
    if edge.face_concept:
        ids.add(edge.face_concept)
    ids.update(edge.detail_concepts)
    if edge.trigger_concept:
        ids.add(edge.trigger_concept)
    if edge.requires_concept:
        ids.add(edge.requires_concept)
    if edge.note_concept:
        ids.add(edge.note_concept)
    if edge.ic_face_concept:
        ids.add(edge.ic_face_concept)
    if edge.ic_external_concept:
        ids.add(edge.ic_external_concept)
    if edge.ic_concept:
        ids.add(edge.ic_concept)
    ids.discard("")
    return ids


# ── Context colors ─────────────────────────────────────────
CONTEXT_COLORS = {
    "PNL": "#2563eb",
    "SFP": "#059669",
    "OCI": "#7c3aed",
    "CFS": "#0891b2",
    "SOCIE": "#d97706",
}
DISC_COLOR = "#6b7280"
PRIMARY_CONTEXTS = {"PNL", "SFP", "OCI", "CFS", "SOCIE"}


def _ctx_color(ctx: str) -> str:
    return CONTEXT_COLORS.get(ctx, DISC_COLOR)


# ── Edge serialization ─────────────────────────────────────
EDGE_COLORS = {
    "SUMMATION": "#94a3b8",
    "CROSS_STATEMENT_TIE": "#3b82f6",
    "DISAGGREGATION": "#a78bfa",
    "NOTE_TO_FACE": "#64748b",
    "IC_DECOMPOSITION": "#f97316",
}


def _serialize_edge_links(edge, visible_ids: set[str]) -> list[dict]:
    """Convert an ontology GraphEdge into force-graph link dicts.
    Only emits links where both endpoints are in visible_ids."""
    links = []
    etype = edge.edge_type.value
    color = EDGE_COLORS.get(etype, "#475569")
    base = {
        "edge_type": etype,
        "edge_name": edge.name,
        "color": color,
        "severity": edge.severity,
        "ambiguities": [a.get("id", "") for a in edge.ambiguities],
    }

    if edge.edge_type == EdgeType.SUMMATION:
        for child in edge.children:
            if child in visible_ids and edge.parent in visible_ids:
                links.append({**base, "source": child, "target": edge.parent,
                              "label": "sums to", "partial": edge.partial})

    elif edge.edge_type == EdgeType.CROSS_STATEMENT_TIE:
        if edge.trigger_concept in visible_ids and edge.requires_concept in visible_ids:
            links.append({**base, "source": edge.trigger_concept,
                          "target": edge.requires_concept,
                          "label": edge.check, "curvature": 0.3})

    elif edge.edge_type == EdgeType.DISAGGREGATION:
        for dc in edge.detail_concepts:
            if dc and edge.face_concept in visible_ids and dc in visible_ids:
                links.append({**base, "source": edge.face_concept, "target": dc,
                              "label": f"by {edge.detail_axis or '?'}"})

    elif edge.edge_type == EdgeType.NOTE_TO_FACE:
        if edge.note_concept and edge.face_concept in visible_ids and edge.note_concept in visible_ids:
            links.append({**base, "source": edge.face_concept,
                          "target": edge.note_concept, "label": "note tie"})

    elif edge.edge_type == EdgeType.IC_DECOMPOSITION:
        if edge.ic_face_concept and edge.ic_external_concept:
            if edge.ic_face_concept in visible_ids and edge.ic_external_concept in visible_ids:
                links.append({**base, "source": edge.ic_face_concept,
                              "target": edge.ic_external_concept, "label": "external"})
        if edge.ic_face_concept and edge.ic_concept:
            if edge.ic_face_concept in visible_ids and edge.ic_concept in visible_ids:
                links.append({**base, "source": edge.ic_face_concept,
                              "target": edge.ic_concept, "label": "IC"})

    return links


# ── API endpoints ──────────────────────────────────────────

@app.get("/api/overview")
def overview():
    """Return collapsed context nodes + cross-context edges.
    Includes grouping: which disclosure belongs to which primary statement."""
    import math
    graph = get_graph()

    # 1. Compute disclosure → primary statement grouping from edges
    disc_to_primary: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        involved = _edge_involved_concepts(edge)
        primaries = set()
        discs = set()
        for cid in involved:
            meta = graph.concepts.get(cid)
            if not meta:
                continue
            ctx = meta.valid_contexts[0] if meta.valid_contexts else _infer_context(cid)
            if ctx in PRIMARY_CONTEXTS:
                primaries.add(ctx)
            elif ctx.startswith("DISC."):
                discs.add(ctx)
        for d in discs:
            disc_to_primary[d].update(primaries)

    # Assign each disc to its primary parent (first one if multiple)
    disc_parent = {}
    for d, prims in disc_to_primary.items():
        # Prefer SFP for shared disclosures, then PNL
        for preferred in ["SFP", "PNL", "CFS", "OCI", "SOCIE"]:
            if preferred in prims:
                disc_parent[d] = preferred
                break

    # 2. Pre-compute radial positions
    # Primary statements in a pentagon (inner ring)
    primary_order = ["PNL", "SFP", "CFS", "OCI", "SOCIE"]
    inner_r = 180
    positions = {}
    for i, ctx in enumerate(primary_order):
        angle = -math.pi / 2 + i * 2 * math.pi / 5  # start from top
        positions[f"ctx:{ctx}"] = {
            "fx": inner_r * math.cos(angle),
            "fy": inner_r * math.sin(angle),
        }

    # Connected disclosures in outer ring around their parent
    outer_r = 340
    parent_children = defaultdict(list)
    for d, parent in sorted(disc_parent.items()):
        parent_children[parent].append(d)

    for parent, children in parent_children.items():
        parent_pos = positions[f"ctx:{parent}"]
        parent_angle = math.atan2(parent_pos["fy"], parent_pos["fx"])
        # Spread children in a fan around the parent's angle
        spread = 0.5  # radians
        for j, child in enumerate(children):
            offset = (j - (len(children) - 1) / 2) * spread / max(len(children) - 1, 1)
            a = parent_angle + offset
            positions[f"ctx:{child}"] = {
                "fx": outer_r * math.cos(a),
                "fy": outer_r * math.sin(a),
            }

    # Unconnected disclosures: cluster at the bottom
    all_disc = sorted(ctx for ctx in _context_index if ctx.startswith("DISC."))
    connected_disc = set(disc_parent.keys())
    unconnected = [d for d in all_disc if d not in connected_disc]

    bottom_y = 300
    for j, d in enumerate(unconnected):
        x = (j - (len(unconnected) - 1) / 2) * 55
        positions[f"ctx:{d}"] = {"fx": x, "fy": bottom_y + (j % 2) * 40}

    # 3. Build nodes
    nodes = []
    for ctx, concept_ids in sorted(_context_index.items()):
        is_primary = ctx in PRIMARY_CONTEXTS
        is_connected = ctx in connected_disc
        node = {
            "id": f"ctx:{ctx}",
            "label": ctx,
            "type": "context",
            "color": _ctx_color(ctx),
            "concept_count": len(concept_ids),
            "is_primary": is_primary,
            "is_connected": is_connected or is_primary,
            "parent_statement": disc_parent.get(ctx),
            "val": 6 if is_primary else (3 if is_connected else 2),
        }
        pos = positions.get(f"ctx:{ctx}")
        if pos:
            node.update(pos)
        nodes.append(node)

    # 4. Cross-context edges
    links = []
    seen_pairs = set()
    for edge in graph.edges:
        involved = _edge_involved_concepts(edge)
        contexts_involved = set()
        for cid in involved:
            meta = graph.concepts.get(cid)
            if meta and meta.valid_contexts:
                contexts_involved.add(meta.valid_contexts[0])
            else:
                contexts_involved.add(_infer_context(cid))

        if len(contexts_involved) >= 2:
            ctx_list = sorted(contexts_involved)
            for i, c1 in enumerate(ctx_list):
                for c2 in ctx_list[i + 1:]:
                    pair = (c1, c2)
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        links.append({
                            "source": f"ctx:{c1}",
                            "target": f"ctx:{c2}",
                            "edge_type": edge.edge_type.value,
                            "edge_name": edge.name,
                            "color": EDGE_COLORS.get(edge.edge_type.value, "#475569"),
                            "label": edge.edge_type.value.replace("_", " ").lower(),
                        })

    return {"nodes": nodes, "links": links}


@app.get("/api/expand/{context}")
def expand_context(context: str):
    """Expand a context node into its individual concepts + internal edges."""
    graph = get_graph()
    concept_ids = _context_index.get(context, [])
    if not concept_ids:
        return {"nodes": [], "links": []}

    ctx_color = _ctx_color(context)
    nodes = []
    for cid in concept_ids:
        meta = graph.concepts.get(cid)
        if not meta:
            continue
        nodes.append({
            "id": cid,
            "label": meta.label or cid.split(".")[-1],
            "type": "concept",
            "context": context,
            "color": ctx_color,
            "is_total": meta.is_total,
            "balance_type": meta.balance_type,
            "unit_type": meta.unit_type,
            "val": 1,
        })

    # Edges between concepts in this context
    visible = set(concept_ids)
    links = []
    seen_edges = set()
    for cid in concept_ids:
        for edge in _edge_index.get(cid, []):
            if edge.name in seen_edges:
                continue
            new_links = _serialize_edge_links(edge, visible)
            if new_links:
                seen_edges.add(edge.name)
                links.extend(new_links)

    return {"nodes": nodes, "links": links}


@app.get("/api/neighborhood/{concept_id:path}")
def neighborhood(concept_id: str, depth: int = Query(1, ge=1, le=3)):
    """Return the neighborhood of a concept: all directly connected concepts + edges."""
    graph = get_graph()
    meta = graph.concepts.get(concept_id)
    if not meta:
        return {"nodes": [], "links": [], "center": concept_id}

    # BFS to collect neighbors
    visited = {concept_id}
    frontier = {concept_id}
    for _ in range(depth):
        next_frontier = set()
        for cid in frontier:
            for edge in _edge_index.get(cid, []):
                involved = _edge_involved_concepts(edge)
                for neighbor in involved:
                    if neighbor not in visited and neighbor in graph.concepts:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
        frontier = next_frontier

    # Build nodes
    nodes = []
    for cid in visited:
        m = graph.concepts.get(cid)
        if not m:
            continue
        ctx = m.valid_contexts[0] if m.valid_contexts else _infer_context(cid)
        nodes.append({
            "id": cid,
            "label": m.label or cid.split(".")[-1],
            "type": "concept",
            "context": ctx,
            "color": _ctx_color(ctx),
            "is_total": m.is_total,
            "balance_type": m.balance_type,
            "unit_type": m.unit_type,
            "val": 1,
            "is_center": cid == concept_id,
        })

    # Edges between visible nodes
    links = []
    seen_edges = set()
    for cid in visited:
        for edge in _edge_index.get(cid, []):
            if edge.name in seen_edges:
                continue
            new_links = _serialize_edge_links(edge, visited)
            if new_links:
                seen_edges.add(edge.name)
                links.extend(new_links)

    return {"nodes": nodes, "links": links, "center": concept_id}


@app.get("/api/search")
def search(q: str = Query(..., min_length=1)):
    """Search concepts by ID or label substring."""
    graph = get_graph()
    q_lower = q.lower()
    results = []
    for cid, meta in graph.concepts.items():
        if q_lower in cid.lower() or q_lower in (meta.label or "").lower():
            ctx = meta.valid_contexts[0] if meta.valid_contexts else _infer_context(cid)
            results.append({
                "id": cid,
                "label": meta.label,
                "context": ctx,
                "color": _ctx_color(ctx),
                "is_total": meta.is_total,
            })
            if len(results) >= 20:
                break
    return {"results": results}


@app.get("/api/concept/{concept_id:path}")
def concept_detail(concept_id: str):
    """Full metadata for a single concept."""
    graph = get_graph()
    meta = graph.concepts.get(concept_id)
    if not meta:
        return {"error": "not found"}

    ctx = meta.valid_contexts[0] if meta.valid_contexts else _infer_context(concept_id)

    # All edges involving this concept
    edges = []
    for edge in _edge_index.get(concept_id, []):
        involved = _edge_involved_concepts(edge)
        others = [c for c in involved if c != concept_id]
        edges.append({
            "edge_type": edge.edge_type.value,
            "edge_name": edge.name,
            "other_concepts": others,
            "severity": edge.severity,
            "check": edge.check,
            "ambiguities": [a.get("id", "") for a in edge.ambiguities],
        })

    return {
        "id": concept_id,
        "label": meta.label,
        "context": ctx,
        "color": _ctx_color(ctx),
        "balance_type": meta.balance_type,
        "unit_type": meta.unit_type,
        "is_total": meta.is_total,
        "has_ic_variant": meta.has_ic_variant,
        "ic_concept": meta.ic_concept,
        "disaggregation_targets": meta.disaggregation_targets,
        "measurement_variants": meta.measurement_variants,
        "edges": edges,
    }


@app.get("/api/stats")
def stats():
    """Summary stats for the ontology."""
    graph = get_graph()
    by_type = defaultdict(int)
    for e in graph.edges:
        by_type[e.edge_type.value] += 1
    return {
        "concepts": len(graph.concepts),
        "edges": len(graph.edges),
        "contexts": len(_context_index),
        "edge_types": dict(by_type),
        "primary_contexts": sorted(c for c in _context_index if c in PRIMARY_CONTEXTS),
        "disclosure_contexts": sorted(c for c in _context_index if c not in PRIMARY_CONTEXTS),
    }


# ── Document / PDF endpoints ──────────────────────────────

# Index: scan fixtures for table_graphs.json and map concepts → (document, page)
_documents: list[dict] = []
_concept_pages: dict[str, list[dict]] = {}  # concept_id → [{doc_id, page, label, table}]


def _build_document_index():
    """Scan eval/fixtures/ for table_graphs.json and build concept→page index."""
    global _documents, _concept_pages
    _documents = []
    _concept_pages = {}

    fixtures_dir = REPO_ROOT / "eval" / "fixtures"
    if not fixtures_dir.exists():
        return

    # Map fixture names to PDF paths and page offset.
    # pdf_page_offset: subtract from pageNo to get the PDF page index.
    # e.g. EuroTeleSites annual report page 105 → PDF extract page 7 → offset=98
    pdf_map = {
        "ca_immo_2024": {"pdf": "sources/ifrs/ca_immo_2024_en.pdf", "offset": 0},
        "eurotelesites_2024": {"pdf": "sources/ifrs/eurotelesites_2024.pdf", "offset": 98},
        "kpmg_ifs_2025": {"pdf": "sources/ifrs/kpmg-ifrs-ifs-2025.pdf", "offset": 0},
        "wienerberger_2024": None,
        "saldenliste_gmbh": None,
    }

    # Auto-discover PDFs by matching fixture name to sources/{gaap}/{name}.pdf
    sources_dir = REPO_ROOT / "sources"
    for gaap_dir in ("ifrs", "ugb", "hgb"):
        gaap_path = sources_dir / gaap_dir
        if gaap_path.is_dir():
            for pdf_file in gaap_path.glob("*.pdf"):
                stem = pdf_file.stem  # e.g. "agrana_2024"
                if stem not in pdf_map:
                    pdf_map[stem] = {
                        "pdf": f"sources/{gaap_dir}/{pdf_file.name}",
                        "offset": 0,
                    }

    for fixture_dir in sorted(fixtures_dir.iterdir()):
        if not fixture_dir.is_dir():
            continue
        tg_path = fixture_dir / "table_graphs.json"
        if not tg_path.exists():
            continue

        doc_id = fixture_dir.name
        doc_info = pdf_map.get(doc_id)
        if doc_info is None:
            pdf_rel = None
            page_offset = 0
        else:
            pdf_rel = doc_info["pdf"]
            page_offset = doc_info.get("offset", 0)
        pdf_path = (REPO_ROOT / pdf_rel) if pdf_rel else None
        has_pdf = pdf_path is not None and pdf_path.exists()

        with open(tg_path) as f:
            tg = json.load(f)

        tables = tg.get("tables", [])
        doc_concepts = []

        for table in tables:
            source_page = table.get("pageNo")
            pdf_page = max(1, source_page - page_offset) if source_page else 1
            table_id = table.get("tableId", "")
            ctx = table.get("metadata", {}).get("statementComponent", "")

            for row in table.get("rows", []):
                pt = row.get("preTagged")
                if not pt:
                    continue
                cid = pt.get("conceptId", "")
                if not cid:
                    continue

                entry = {
                    "doc_id": doc_id,
                    "page": pdf_page,
                    "source_page": source_page,
                    "label": row.get("label", ""),
                    "table_id": table_id,
                    "context": ctx,
                }
                _concept_pages.setdefault(cid, []).append(entry)
                doc_concepts.append(cid)

        _documents.append({
            "id": doc_id,
            "name": doc_id.replace("_", " ").title(),
            "pdf": pdf_rel if has_pdf else None,
            "has_pdf": has_pdf,
            "tables": len(tables),
            "tagged_concepts": len(set(doc_concepts)),
            "page_offset": page_offset,
        })


@app.get("/api/documents")
def list_documents():
    """List available documents with their PDF status."""
    if not _documents:
        _build_document_index()
    return {"documents": _documents}


@app.get("/api/concept-pages/{concept_id:path}")
def concept_pages(concept_id: str):
    """Return all document pages where a concept is tagged, with image URLs."""
    if not _concept_pages:
        _build_document_index()
    pages = _concept_pages.get(concept_id, [])

    # Enrich with image URLs from manifests
    for p in pages:
        doc_id = p["doc_id"]
        table_id = p.get("table_id", "")
        manifest_path = REPO_ROOT / "eval" / "fixtures" / doc_id / "images.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            entry = next((t for t in manifest.get("tables", []) if t["table_id"] == table_id), None)
            if entry:
                p["image_url"] = f"/api/table-image/{doc_id}/{table_id}"

    return {"concept_id": concept_id, "pages": pages}


@app.get("/api/tables/{doc_id}")
def doc_tables(doc_id: str):
    """Return all tables for a document with rows, cells, and tags."""
    fixtures_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    tg_path = fixtures_dir / "table_graphs.json"
    if not tg_path.exists():
        return {"error": "fixture not found", "tables": []}

    with open(tg_path) as f:
        tg = json.load(f)

    # Find page offset for this doc
    doc = next((d for d in _documents if d["id"] == doc_id), None)
    offset = doc.get("page_offset", 0) if doc else 0

    tables = []
    for t in tg.get("tables", []):
        source_page = t.get("pageNo")
        rows = []
        for r in t.get("rows", []):
            tag = r.get("preTagged", {}).get("conceptId", "") if r.get("preTagged") else ""
            cells = []
            for c in r.get("cells", []):
                cells.append({
                    "col": c.get("colIdx", 0),
                    "text": c.get("text", ""),
                    "value": c.get("parsedValue"),
                    "negative": c.get("isNegative", False),
                })
            rows.append({
                "label": r.get("label", ""),
                "row_type": r.get("rowType", "DATA"),
                "indent": r.get("indentLevel", 0),
                "tag": tag,
                "cells": cells,
            })
        tables.append({
            "table_id": t.get("tableId", ""),
            "context": t.get("metadata", {}).get("statementComponent", ""),
            "source_page": source_page,
            "currency": t.get("metadata", {}).get("detectedCurrency", ""),
            "unit": t.get("metadata", {}).get("detectedUnit", ""),
            "rows": rows,
        })

    return {"doc_id": doc_id, "tables": tables}


@app.get("/api/pdf/{doc_id}")
def serve_pdf(doc_id: str):
    """Serve a PDF file for a document."""
    if not _documents:
        _build_document_index()
    doc = next((d for d in _documents if d["id"] == doc_id), None)
    if not doc or not doc.get("pdf"):
        return {"error": "no PDF available"}
    pdf_path = REPO_ROOT / doc["pdf"]
    if not pdf_path.exists():
        return {"error": "PDF file not found"}
    return FileResponse(pdf_path, media_type="application/pdf",
                        headers={"Content-Disposition": f"inline; filename={pdf_path.name}"})


@app.get("/api/table-image/{doc_id}/{table_id}")
def table_image(doc_id: str, table_id: str):
    """Serve the PNG image for a specific table page."""
    manifest_path = REPO_ROOT / "eval" / "fixtures" / doc_id / "images.json"
    if not manifest_path.exists():
        return {"error": "no images for this document"}

    with open(manifest_path) as f:
        manifest = json.load(f)

    entry = next((t for t in manifest.get("tables", []) if t["table_id"] == table_id), None)
    if not entry:
        return {"error": f"no image for table {table_id}"}

    image_path = REPO_ROOT / "eval" / "fixtures" / doc_id / entry["image"]
    if not image_path.exists():
        return {"error": "image file not found"}

    return FileResponse(image_path, media_type="image/png")


@app.get("/api/table-images/{doc_id}")
def table_images_manifest(doc_id: str):
    """Return the images manifest for a document."""
    manifest_path = REPO_ROOT / "eval" / "fixtures" / doc_id / "images.json"
    if not manifest_path.exists():
        return {"doc_id": doc_id, "tables": []}

    with open(manifest_path) as f:
        manifest = json.load(f)

    # Add image URLs
    for t in manifest.get("tables", []):
        t["image_url"] = f"/api/table-image/{doc_id}/{t['table_id']}"

    return manifest


# ── HITL Classification Review ────────────────────────────

@app.get("/api/review/status")
def review_status():
    """List all fixtures with pipeline stage info for the review dashboard."""
    if not _documents:
        _build_document_index()

    fixtures_dir = REPO_ROOT / "eval" / "fixtures"
    if not fixtures_dir.exists():
        return {"fixtures": []}

    results = []
    for d in sorted(fixtures_dir.iterdir()):
        if not d.is_dir():
            continue
        tg_path = d / "table_graphs.json"
        if not tg_path.is_file():
            continue

        doc_id = d.name
        manifest_path = d / "review_needed.json"
        human_path = d / "human_review.json"
        meta_path = d / "document_meta.json"

        # Find PDF status from document index
        doc = next((doc for doc in _documents if doc["id"] == doc_id), None)
        has_pdf = bool(doc and doc.get("has_pdf"))

        # Load table_graphs.json for stage info
        try:
            with open(tg_path) as f:
                tg = json.load(f)
            tables = tg.get("tables", [])
        except Exception:
            tables = []

        # Classification stats
        from collections import Counter as _C
        class_counts = _C()
        method_counts = _C()
        total_tables = len(tables)
        for t in tables:
            meta = t.get("metadata", {})
            sc = meta.get("statementComponent")
            cm = meta.get("classification_method", "unclassified")
            if sc:
                class_counts[sc] += 1
            else:
                class_counts["unclassified"] += 1
            method_counts[cm] += 1

        # TOC detection: check if any table was classified via TOC
        toc_count = method_counts.get("toc", 0)
        has_toc = toc_count > 0

        # Note references: count tables with noteRef in rows
        note_ref_tables = 0
        total_note_refs = 0
        for t in tables:
            table_has_note = False
            for r in t.get("rows", []):
                if r.get("noteRef"):
                    total_note_refs += 1
                    table_has_note = True
            if table_has_note:
                note_ref_tables += 1

        # Page references: count distinct pages
        pages = set()
        for t in tables:
            p = t.get("pageNo")
            if p:
                pages.add(p)

        # Meta info
        meta_info = {}
        if meta_path.is_file():
            try:
                with open(meta_path) as f:
                    meta_info = json.load(f)
            except Exception:
                pass

        # Primary statement counts
        primary = {k: v for k, v in class_counts.items()
                   if k in ("PNL", "SFP", "OCI", "CFS", "SOCIE")}
        disc = {k: v for k, v in class_counts.items()
                if k.startswith("DISC.")}

        results.append({
            "id": doc_id,
            "has_pdf": has_pdf,
            "has_manifest": manifest_path.is_file(),
            "has_human_review": human_path.is_file(),
            # Stage info
            "total_tables": total_tables,
            "pages": len(pages),
            "page_range": f"{min(pages)}-{max(pages)}" if pages else "",
            # TOC
            "has_toc": has_toc,
            "toc_tables": toc_count,
            # Classification
            "primary_types": primary,
            "disc_types": len(disc),
            "unclassified": class_counts.get("unclassified", 0),
            "methods": dict(method_counts.most_common()),
            # References
            "note_ref_tables": note_ref_tables,
            "total_note_refs": total_note_refs,
            # Meta
            "gaap": meta_info.get("gaap", ""),
            "entity": meta_info.get("entity_name", ""),
            "industry": meta_info.get("industry", ""),
            "currency": meta_info.get("currency", ""),
        })

    return {"fixtures": results}


@app.get("/api/review/{doc_id}")
def review_manifest(doc_id: str):
    """Return review_needed.json for a document, generating if needed."""
    fixtures_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    manifest_path = fixtures_dir / "review_needed.json"
    tg_path = fixtures_dir / "table_graphs.json"

    if not tg_path.exists():
        return {"error": "fixture not found"}

    # If manifest exists, return it
    if manifest_path.exists():
        with open(manifest_path) as f:
            return json.load(f)

    # Generate on the fly from current table_graphs.json
    from human_review import generate_review_manifest
    from pipeline import GateResult
    from stages import PRIMARY_STATEMENTS
    from collections import Counter as _Counter

    with open(tg_path) as f:
        tables = json.load(f).get("tables", [])

    classified_types = _Counter()
    for t in tables:
        sc = t.get("metadata", {}).get("statementComponent")
        if sc:
            classified_types[sc] += 1

    primary_counts = {t: classified_types[t] for t in PRIMARY_STATEMENTS
                      if classified_types[t] > 0}
    findings = []
    for st, count in primary_counts.items():
        if count > 8:
            findings.append({"type": "inflated_primary",
                             "detail": f"{count} tables classified as {st} (max 8)"})

    gate_result = GateResult(passed=not findings, stage="stage2",
                             findings=findings, metrics={})

    toc_info = None
    try:
        from classify_tables import _detect_toc
        toc_info = _detect_toc(tables)
    except Exception:
        pass

    manifest = generate_review_manifest(tables, gate_result, toc_info, doc_id)
    return manifest


@app.get("/api/review/{doc_id}/human")
def get_human_review(doc_id: str):
    """Return existing human_review.json for a document."""
    review_path = REPO_ROOT / "eval" / "fixtures" / doc_id / "human_review.json"
    if not review_path.exists():
        return {"exists": False}
    with open(review_path) as f:
        data = json.load(f)
    data["exists"] = True
    return data


@app.post("/api/review/{doc_id}/save")
async def save_human_review(doc_id: str, request: Request):
    """Save human_review.json for a document."""
    fixtures_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    if not fixtures_dir.exists():
        return {"error": "fixture not found"}

    body = await request.json()
    review_path = fixtures_dir / "human_review.json"
    with open(review_path, "w") as f:
        json.dump(body, f, indent=2, default=str)

    return {"saved": True, "path": str(review_path)}


@app.get("/api/review/{doc_id}/tables")
def review_tables(doc_id: str):
    """Return tables with classification info for the review UI.

    Lighter than /api/tables/{doc_id} — includes classification metadata
    and first few row labels but not all cells/values.
    """
    tg_path = REPO_ROOT / "eval" / "fixtures" / doc_id / "table_graphs.json"
    if not tg_path.exists():
        return {"error": "fixture not found", "tables": []}

    with open(tg_path) as f:
        data = json.load(f)

    tables = []
    for t in data.get("tables", []):
        meta = t.get("metadata", {})
        rows = t.get("rows", [])

        # Extract first labels and column headers for context
        first_labels = []
        col_headers = []
        for r in rows:
            if r.get("rowType") == "HEADER" and not col_headers:
                col_headers = [c.get("text", "") for c in r.get("cells", [])
                               if c.get("text", "").strip()][:6]
            elif len(first_labels) < 3 and r.get("label", "").strip():
                first_labels.append(r["label"].strip()[:80])

        tables.append({
            "tableId": t.get("tableId", ""),
            "pageNo": t.get("pageNo"),
            "statementComponent": meta.get("statementComponent"),
            "classification_method": meta.get("classification_method", "unclassified"),
            "classification_confidence": meta.get("classification_confidence", "none"),
            "first_labels": first_labels,
            "col_headers": col_headers,
            "row_count": len(rows),
            "sectionPath": meta.get("sectionPath", []),
        })

    return {"doc_id": doc_id, "tables": tables}


# ── Ground Truth Annotation ───────────────────────────────

from test_set import TEST_SET, is_test_set
from ground_truth import load_toc_gt_dict, save_toc_gt_dict, toc_gt_path
from classify_tables import _detect_toc, _parse_toc_entries
from validate_ground_truth import validate_all as validate_gt_all


@app.get("/api/annotate/documents")
def annotate_documents():
    """List test-set documents with annotation status."""
    if not _documents:
        _build_document_index()

    fixtures_dir = REPO_ROOT / "eval" / "fixtures"
    results = []
    for doc_id in TEST_SET:
        fixture_dir = fixtures_dir / doc_id
        tg_path = fixture_dir / "table_graphs.json"

        # Basic info
        info = {
            "doc_id": doc_id,
            "gaap": "UGB" if "ugb" in doc_id else "IFRS",
            "has_fixture": tg_path.exists(),
            "table_count": 0,
            "has_pdf": False,
            "annotation_status": "not_started",
        }

        # Page count from table_graphs.json pages dict
        if tg_path.exists():
            try:
                with open(tg_path) as f:
                    tg_data = json.load(f)
                pages_obj = tg_data.get("pages", {})
                if isinstance(pages_obj, dict):
                    info["page_count"] = len(pages_obj)
                info["table_count"] = len(tg_data.get("tables", []))
            except (json.JSONDecodeError, OSError):
                pass

        # Check PDF availability
        doc = next((d for d in _documents if d["id"] == doc_id), None)
        if doc:
            info["has_pdf"] = doc.get("has_pdf", False)
            if not info["table_count"]:
                info["table_count"] = doc.get("tables", 0)

        # Check ground truth status
        gt = load_toc_gt_dict(str(fixture_dir))
        if gt:
            sections = gt.get("sections", [])
            if sections:
                info["annotation_status"] = "complete"
                info["section_count"] = len(sections)
            else:
                info["annotation_status"] = "in_progress"
            # has_toc: True/False if annotated, None if not yet tagged
            if "has_toc" in gt:
                info["has_toc"] = gt["has_toc"]

        results.append(info)

    return {"documents": results}


@app.get("/api/annotate/{doc_id}/toc")
def annotate_get_toc(doc_id: str):
    """Load ground truth TOC for a document, or empty template."""
    fixture_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    gt = load_toc_gt_dict(str(fixture_dir))

    # Get total page count
    page_count = 0
    tg_path = fixture_dir / "table_graphs.json"
    if tg_path.exists():
        try:
            with open(tg_path) as f:
                tg_data = json.load(f)
            pages_obj = tg_data.get("pages", {})
            if isinstance(pages_obj, dict):
                page_count = len(pages_obj)
        except (json.JSONDecodeError, OSError):
            pass

    if gt:
        return {"doc_id": doc_id, "ground_truth": gt, "page_count": page_count}

    # Return empty template
    return {"doc_id": doc_id, "page_count": page_count, "ground_truth": {
        "version": 1,
        "annotator": "",
        "toc_table_id": None,
        "toc_pages": [],
        "sections": [],
        "notes_start_page": None,
        "notes_end_page": None,
    }}


@app.post("/api/annotate/{doc_id}/toc")
async def annotate_save_toc(doc_id: str, request: Request):
    """Save ground truth TOC for a document."""
    body = await request.json()
    fixture_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    if not fixture_dir.exists():
        return {"error": f"fixture directory not found: {doc_id}"}

    save_toc_gt_dict(str(fixture_dir), body)
    return {"status": "saved", "doc_id": doc_id}


def _map_to_physical_section(stmt_type: str, label: str = "") -> str:
    """Map pipeline statement types to physical document section types.

    The pipeline produces semantic types (DISC.PPE, DISC.TAX, etc.) but ground
    truth annotation uses physical document structure types.
    """
    # Primary statements stay as-is
    if stmt_type in ("PNL", "SFP", "OCI", "CFS", "SOCIE"):
        return stmt_type
    # Already physical section types
    if stmt_type in ("TOC", "NOTES", "FRONT_MATTER", "MANAGEMENT_REPORT", "AUDITOR_REPORT",
                     "CORPORATE_GOVERNANCE", "ESG", "RISK_REPORT", "REMUNERATION_REPORT",
                     "SUPERVISORY_BOARD", "RESPONSIBILITY_STATEMENT", "APPENDIX", "OTHER"):
        return stmt_type
    # DISC.* → check if label says "Anlage" / "Beilage" → APPENDIX, else NOTES
    if stmt_type.startswith("DISC."):
        label_lower = label.lower()
        if any(kw in label_lower for kw in ("anlage", "beilage", "appendix", "schedule")):
            return "APPENDIX"
        return "NOTES"
    return "OTHER"


@app.get("/api/annotate/{doc_id}/toc/detect")
def annotate_detect_toc(doc_id: str):
    """Auto-detect TOC from table_graphs.json using pipeline's _detect_toc().

    Returns detected sections as pre-fill data for the annotation form.
    Maps pipeline semantic types (DISC.*) to physical section types.
    """
    tg_path = REPO_ROOT / "eval" / "fixtures" / doc_id / "table_graphs.json"
    if not tg_path.exists():
        return {"doc_id": doc_id, "detected": False, "sections": [],
                "error": "no table_graphs.json"}

    with open(tg_path) as f:
        tg = json.load(f)

    tables = tg.get("tables", [])
    page_map = _detect_toc(tables)

    if not page_map:
        return {"doc_id": doc_id, "detected": False, "sections": [],
                "message": "No TOC detected in document"}

    # Find the TOC table page to include as a section
    toc_page = None
    for tbl in tables[:20]:
        rows = tbl.get("rows", [])
        if len(rows) >= 3:
            entries = []
            for r in rows:
                for c in r.get("cells", []):
                    pv = c.get("parsedValue")
                    if pv is not None and 1 < pv < 500 and pv == int(pv):
                        entries.append(int(pv))
                        break
            if len(entries) >= 3:
                toc_page = tbl.get("pageNo")
                break

    # Convert page_map to section list (merge consecutive pages of same type)
    # First pass: collect raw sections with pipeline types
    raw_sections = []
    sorted_pages = sorted(page_map.items())
    current = None
    for page, stmt_type in sorted_pages:
        if current and current["_raw_type"] == stmt_type and page <= current["end_page"] + 5:
            current["end_page"] = page
        else:
            if current:
                raw_sections.append(current)
            current = {
                "label": "",
                "_raw_type": stmt_type,
                "start_page": page,
                "end_page": page,
                "note_number": None,
                "validated": False,
            }
    if current:
        raw_sections.append(current)

    # Try to enrich labels from the TOC table entries
    for tbl in tables[:20]:
        rows = tbl.get("rows", [])
        for r in rows:
            label = r.get("label", "").strip()
            if not label:
                continue
            for c in r.get("cells", []):
                pv = c.get("parsedValue")
                if pv is not None and 1 < pv < 500 and pv == int(pv):
                    page = int(pv)
                    for sec in raw_sections:
                        if sec["start_page"] == page and not sec["label"]:
                            sec["label"] = label
                            break

    # Map pipeline types to physical section types using label context
    sections = []

    # Insert TOC section if detected
    if toc_page:
        sections.append({
            "label": "Table of Contents",
            "statement_type": "TOC",
            "start_page": toc_page,
            "end_page": toc_page,
            "note_number": None,
            "validated": False,
        })

    for sec in raw_sections:
        sec["statement_type"] = _map_to_physical_section(sec["_raw_type"], sec["label"])
        del sec["_raw_type"]
        sections.append(sec)

    return {"doc_id": doc_id, "detected": True, "sections": sections}


@app.get("/api/annotate/{doc_id}/tables")
def annotate_tables(doc_id: str):
    """Return table list with page numbers for reference during annotation."""
    tg_path = REPO_ROOT / "eval" / "fixtures" / doc_id / "table_graphs.json"
    if not tg_path.exists():
        return {"doc_id": doc_id, "tables": []}

    with open(tg_path) as f:
        tg = json.load(f)

    tables = []
    for t in tg.get("tables", []):
        rows = t.get("rows", [])
        first_labels = [r.get("label", "").strip()[:80]
                        for r in rows if r.get("label", "").strip()][:3]
        tables.append({
            "tableId": t.get("tableId", ""),
            "pageNo": t.get("pageNo"),
            "row_count": len(rows),
            "first_labels": first_labels,
            "statementComponent": t.get("metadata", {}).get("statementComponent"),
        })
    return {"doc_id": doc_id, "tables": tables}


@app.post("/api/annotate/{doc_id}/validate")
def annotate_validate(doc_id: str):
    """Validate ground truth TOC against table data."""
    fixture_dir = str(REPO_ROOT / "eval" / "fixtures" / doc_id)
    result = validate_gt_all(fixture_dir)
    return {"doc_id": doc_id, **result}


# ── Element Browser endpoints ─────────────────────────────

PAGE_CACHE_DIR = Path("/tmp/fobe_page_cache")


@app.get("/api/page-image/{doc_id}/{page_no}")
def page_image(doc_id: str, page_no: int, dpi: int = 150):
    """Render a single PDF page as PNG using PyMuPDF."""
    if fitz is None:
        return Response(content=b"pymupdf not installed", status_code=501)

    if not _documents:
        _build_document_index()
    doc = next((d for d in _documents if d["id"] == doc_id), None)
    if not doc or not doc.get("pdf"):
        return {"error": "no PDF available"}
    pdf_path = REPO_ROOT / doc["pdf"]
    if not pdf_path.exists():
        return {"error": "PDF file not found"}

    # Check disk cache
    PAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = f"{doc_id}_{page_no}_{dpi}"
    cache_path = PAGE_CACHE_DIR / f"{cache_key}.png"
    if cache_path.exists():
        return FileResponse(cache_path, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=3600"})

    # Render page
    try:
        pdf_doc = fitz.open(str(pdf_path))
        page_offset = doc.get("page_offset", 0)
        page_idx = (page_no - 1) + page_offset  # page_no is 1-indexed
        if page_idx < 0 or page_idx >= len(pdf_doc):
            pdf_doc.close()
            return {"error": f"page {page_no} out of range"}
        page = pdf_doc[page_idx]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        pdf_doc.close()
    except Exception as e:
        return {"error": f"render failed: {e}"}

    # Cache to disk
    cache_path.write_bytes(png_bytes)
    return Response(content=png_bytes, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/elements/browse")
def elements_browse():
    """Build element-type-to-pages mapping across all test-set documents."""
    if not _documents:
        _build_document_index()

    fixtures_dir = REPO_ROOT / "eval" / "fixtures"
    results = []

    for doc_id in TEST_SET:
        fixture_dir = fixtures_dir / doc_id
        tg_path = fixture_dir / "table_graphs.json"
        if not tg_path.exists():
            continue

        try:
            with open(tg_path) as f:
                tg_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        pages_obj = tg_data.get("pages", {})
        page_count = len(pages_obj) if isinstance(pages_obj, dict) else 0

        # Page dimensions for coordinate mapping
        page_dims = {}
        if isinstance(pages_obj, dict):
            for pno, dims in pages_obj.items():
                page_dims[int(pno)] = {"width": dims.get("width", 595),
                                       "height": dims.get("height", 842)}

        # Collect all tables with bbox info
        all_tables = []
        for t in tg_data.get("tables", []):
            bbox = t.get("bbox", [0, 0, 0, 0])
            sc = t.get("metadata", {}).get("statementComponent")
            all_tables.append({
                "tableId": t.get("tableId", ""),
                "pageNo": t.get("pageNo"),
                "bbox": bbox,
                "statementComponent": sc,
            })

        # Build elements mapping
        elements = defaultdict(lambda: {"pages": set(), "tables": []})

        # Source 1: ground truth TOC sections (preferred)
        gt_path = fixture_dir / "ground_truth" / "toc.json"
        source = "table_classification"
        if gt_path.exists():
            try:
                with open(gt_path) as f:
                    gt = json.load(f)
                sections = gt.get("sections", [])
                if sections:
                    source = "ground_truth"
                    for sec in sections:
                        stype = sec.get("statement_type", "OTHER")
                        sp = sec.get("start_page")
                        ep = sec.get("end_page")
                        if sp and ep:
                            for p in range(sp, ep + 1):
                                elements[stype]["pages"].add(p)
            except (json.JSONDecodeError, OSError):
                pass

        # Source 2: always use table classification for pages + tables
        # (supplements ground truth which may be incomplete)
        for t in all_tables:
            sc = t.get("statementComponent")
            pno = t.get("pageNo")
            if sc and pno:
                elements[sc]["tables"].append(t)
                elements[sc]["pages"].add(pno)
            elif pno:
                elements["UNCLASSIFIED"]["tables"].append(t)
                elements["UNCLASSIFIED"]["pages"].add(pno)

        # Convert sets to sorted lists
        elements_out = {}
        for etype, data in elements.items():
            elements_out[etype] = {
                "pages": sorted(data["pages"]),
                "tables": data["tables"],
            }

        # PDF availability
        doc = next((d for d in _documents if d["id"] == doc_id), None)
        has_pdf = doc.get("has_pdf", False) if doc else False

        results.append({
            "doc_id": doc_id,
            "gaap": "UGB" if "ugb" in doc_id else "IFRS",
            "page_count": page_count,
            "has_pdf": has_pdf,
            "source": source,
            "page_dims": page_dims,
            "elements": elements_out,
            "all_tables": all_tables,
        })

    return {"documents": results}


# ── Serve frontend static files ───────────────────────────
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    # Pre-load graph and document index
    get_graph()
    _build_document_index()
    print(f"Documents: {len(_documents)} fixtures, {len(_concept_pages)} concept→page mappings")
    s = stats()
    print(f"FOBE Explorer: {s['concepts']} concepts, {s['edges']} edges, {s['contexts']} contexts")
    print(f"  Primary: {', '.join(s['primary_contexts'])}")
    print(f"  Disclosure: {', '.join(s['disclosure_contexts'])}")
    print("Starting server at http://localhost:8787")
    uvicorn.run(app, host="0.0.0.0", port=8787)
