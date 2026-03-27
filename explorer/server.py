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

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
