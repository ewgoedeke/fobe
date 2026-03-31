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
from datetime import datetime, timezone
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

# Allow importing from eval/ and explorer/
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "eval"))
sys.path.insert(0, str(REPO_ROOT))
from relationship_graph import EdgeType, OntologyGraph, build_graph, _infer_context
from section_types import PRIMARY_STATEMENTS

# ── Data source toggle ────────────────────────────────────────
# Set FOBE_DATA_SOURCE=supabase to read from Supabase instead of local files.
USE_SUPABASE = os.environ.get("FOBE_DATA_SOURCE", "files") == "supabase"

if USE_SUPABASE:
    from explorer import queries as Q
    from explorer.r2_cache import get_pdf_path as r2_get_pdf_path, get_docling_json as r2_get_docling_json
    from explorer.supabase_client import resolve_doc_uuid, get_supabase
    from explorer.auth import get_current_user, get_optional_user, AuthUser, _decode_token


def _require_auth(request: Request) -> "AuthUser":
    """Extract and validate user from Authorization header. Use in write endpoints."""
    if not USE_SUPABASE:
        return None  # no auth in file mode
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Authentication required")
    token = auth_header[7:]
    payload = _decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid token")
    return AuthUser(id=user_id, email=payload.get("email", ""))


def _optional_auth(request: Request) -> "AuthUser | None":
    """Try to extract user from Authorization header, return None on failure.

    Use for endpoints that write to local files and should work regardless
    of auth state (e.g. annotation endpoints).
    """
    try:
        return _require_auth(request)
    except Exception:
        return None

app = FastAPI(title="FOBE Ontology Explorer")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Auth endpoints ────────────────────────────────────────
# Uses admin API (service key) for signup to bypass email confirmation.
# Uses anon client for login so Supabase issues proper user JWTs.

if USE_SUPABASE:
    from functools import lru_cache
    from supabase import create_client as _create_client

    @lru_cache(maxsize=1)
    def _get_anon_client():
        """Supabase client with the anon/publishable key — for user-facing auth."""
        anon_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
        if not anon_key:
            raise RuntimeError("SUPABASE_PUBLISHABLE_KEY not set")
        return _create_client(os.environ["SUPABASE_URL"], anon_key)

    @app.post("/api/auth/signup")
    async def auth_signup(request: Request):
        """Register a new user with email + password (admin create, auto-confirmed)."""
        body = await request.json()
        email = body.get("email", "").strip()
        password = body.get("password", "")
        if not email or not password:
            return {"error": "email and password required"}
        sb = get_supabase()  # service key client for admin.create_user
        try:
            # Create user via admin API (auto-confirmed, no email needed)
            sb.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
            })
            # Now sign in to get a session token
            anon = _get_anon_client()
            login_resp = anon.auth.sign_in_with_password({"email": email, "password": password})
            user = login_resp.user
            session = login_resp.session
            return {
                "user": {"id": str(user.id), "email": user.email} if user else None,
                "session": {
                    "access_token": session.access_token,
                    "refresh_token": session.refresh_token,
                    "expires_in": session.expires_in,
                } if session else None,
            }
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/auth/login")
    async def auth_login(request: Request):
        """Sign in with email + password."""
        body = await request.json()
        email = body.get("email", "").strip()
        password = body.get("password", "")
        if not email or not password:
            return {"error": "email and password required"}
        sb = _get_anon_client()
        try:
            resp = sb.auth.sign_in_with_password({"email": email, "password": password})
            user = resp.user
            session = resp.session
            return {
                "user": {"id": str(user.id), "email": user.email} if user else None,
                "session": {
                    "access_token": session.access_token,
                    "refresh_token": session.refresh_token,
                    "expires_in": session.expires_in,
                } if session else None,
            }
        except Exception as e:
            return {"error": str(e)}

    @app.post("/api/auth/refresh")
    async def auth_refresh(request: Request):
        """Refresh an expired access token."""
        body = await request.json()
        refresh_token = body.get("refresh_token", "")
        if not refresh_token:
            return {"error": "refresh_token required"}
        sb = _get_anon_client()
        try:
            resp = sb.auth.refresh_session(refresh_token)
            session = resp.session
            return {
                "session": {
                    "access_token": session.access_token,
                    "refresh_token": session.refresh_token,
                    "expires_in": session.expires_in,
                } if session else None,
            }
        except Exception as e:
            return {"error": str(e)}

    @app.get("/api/auth/me")
    async def auth_me(user: AuthUser = Depends(get_current_user)):
        """Return the current authenticated user."""
        return {"user": {"id": user.id, "email": user.email}}

else:
    # Local dev mode — no Supabase, auto-authenticate
    _LOCAL_USER = {"id": "local", "email": "local@dev"}

    @app.post("/api/auth/signup")
    async def auth_signup_local(request: Request):
        return {"user": _LOCAL_USER, "session": {"access_token": "local", "refresh_token": "local", "expires_in": 86400}}

    @app.post("/api/auth/login")
    async def auth_login_local(request: Request):
        return {"user": _LOCAL_USER, "session": {"access_token": "local", "refresh_token": "local", "expires_in": 86400}}

    @app.post("/api/auth/refresh")
    async def auth_refresh_local(request: Request):
        return {"session": {"access_token": "local", "refresh_token": "local", "expires_in": 86400}}

    @app.get("/api/auth/me")
    async def auth_me_local(request: Request):
        return {"user": _LOCAL_USER}


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


@app.get("/api/ontology/contexts")
def ontology_contexts():
    """Return all contexts with concept counts, grouped into primary/disclosure."""
    graph = get_graph()
    contexts = []
    for ctx, cids in sorted(_context_index.items()):
        contexts.append({
            "id": ctx,
            "concept_count": len(cids),
            "group": "primary" if ctx in PRIMARY_STATEMENTS else "disclosure",
        })
    return {"contexts": contexts}


@app.get("/api/ontology/context/{context_id:path}")
def ontology_context_tree(context_id: str):
    """Return concepts in a context as a tree built from SUMMATION edges."""
    graph = get_graph()
    cids = _context_index.get(context_id, [])
    if not cids:
        return {"context_id": context_id, "concept_count": 0, "tree": []}

    cid_set = set(cids)

    # Build parent→children map from SUMMATION edges within this context
    children_map = defaultdict(list)
    has_parent = set()
    for edge in graph.edges_by_type(EdgeType.SUMMATION):
        if edge.parent in cid_set:
            for child in edge.children:
                if child in cid_set:
                    children_map[edge.parent].append(child)
                    has_parent.add(child)

    # Build tree nodes
    def build_node(cid):
        meta = graph.concepts.get(cid)
        label = meta.label if meta else cid.split(".")[-1]
        edge_count = len(_edge_index.get(cid, []))
        kids = children_map.get(cid, [])
        return {
            "id": cid,
            "label": label,
            "balance_type": meta.balance_type if meta else None,
            "is_total": meta.is_total if meta else False,
            "edge_count": edge_count,
            "children": [build_node(c) for c in kids],
        }

    # Root nodes: concepts with no parent in this context
    roots = [cid for cid in cids if cid not in has_parent]
    tree = [build_node(r) for r in roots]

    return {"context_id": context_id, "concept_count": len(cids), "tree": tree}


@app.get("/api/ontology/concept/{concept_id:path}")
def ontology_concept_detail(concept_id: str):
    """Full detail for a concept: metadata + cross-context edges + tagged examples."""
    graph = get_graph()
    meta = graph.concepts.get(concept_id)
    if not meta:
        return {"error": "not found"}

    ctx = meta.valid_contexts[0] if meta.valid_contexts else _infer_context(concept_id)

    # Cross-context edges
    cross_edges = []
    for edge in _edge_index.get(concept_id, []):
        involved = _edge_involved_concepts(edge)
        for other_cid in involved:
            if other_cid == concept_id:
                continue
            other_meta = graph.concepts.get(other_cid)
            if not other_meta:
                continue
            other_ctx = other_meta.valid_contexts[0] if other_meta.valid_contexts else _infer_context(other_cid)
            cross_edges.append({
                "concept_id": other_cid,
                "label": other_meta.label,
                "context": other_ctx,
                "edge_type": edge.edge_type.value,
                "edge_name": edge.name,
            })

    # Examples from Supabase (if available)
    examples = []
    if USE_SUPABASE:
        try:
            examples = Q.query_concept_examples(concept_id, limit=20)
        except Exception:
            pass

    return {
        "id": concept_id,
        "label": meta.label,
        "context": ctx,
        "balance_type": meta.balance_type,
        "unit_type": meta.unit_type,
        "is_total": meta.is_total,
        "valid_contexts": meta.valid_contexts,
        "cross_edges": cross_edges,
        "examples": examples,
    }


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


# ── Dashboard: corpus health + activity ──────────────────

@app.get("/api/dashboard/corpus-health")
def dashboard_corpus_health():
    """Per-fixture file completeness for the dashboard."""
    fixtures_dir = REPO_ROOT / "eval" / "fixtures"
    results = []
    for d in sorted(fixtures_dir.iterdir()):
        if not d.is_dir():
            continue
        tg = d / "table_graphs.json"
        if not tg.exists():
            continue
        doc_id = d.name
        has_docling = (d / "docling_elements.json").exists()
        has_gt = (d / "ground_truth").is_dir()
        has_rank = (d / "rank_tags.json").exists()
        has_meta = (d / "document_meta.json").exists()
        # Quick completeness check on table_graphs
        tg_ok = True
        table_count = 0
        try:
            with open(tg) as f:
                data = json.load(f)
            table_count = len(data.get("tables", []))
            if table_count == 0:
                tg_ok = False
        except (json.JSONDecodeError, OSError):
            tg_ok = False
        results.append({
            "doc_id": doc_id,
            "table_graphs": tg_ok,
            "table_count": table_count,
            "docling": has_docling,
            "ground_truth": has_gt,
            "rank_tags": has_rank,
            "meta": has_meta,
        })
    # Summary
    total = len(results)
    complete = sum(1 for r in results if r["docling"] and r["table_graphs"] and r["meta"])
    missing_docling = [r["doc_id"] for r in results if not r["docling"]]
    missing_meta = [r["doc_id"] for r in results if not r["meta"]]
    broken_tg = [r["doc_id"] for r in results if not r["table_graphs"]]
    return {
        "total": total,
        "complete": complete,
        "missing_docling": missing_docling,
        "missing_meta": missing_meta,
        "broken_table_graphs": broken_tg,
        "fixtures": results,
    }


def _adaptive_bucket_by_action(entries: list[dict], target_bins: int = 20) -> tuple[list[dict], int]:
    """Bucket tag entries by action into ~target_bins data points.

    Returns (chart_data, total_actions).
    """
    from datetime import timedelta
    from collections import Counter

    if not entries:
        return [], 0

    parsed = []
    for e in entries:
        dt = _parse_ts(e.get("timestamp", ""))
        if dt:
            parsed.append((dt, e.get("action", "unknown")))

    if not parsed:
        return [], 0

    parsed.sort(key=lambda x: x[0])
    total = len(parsed)
    span = (parsed[-1][0] - parsed[0][0]).total_seconds()

    # Synthetic bins when natural time granularity can't produce enough bins
    min_bucket = 60
    max_natural_bins = span / min_bucket if span > 0 else 0
    if max_natural_bins < target_bins or total <= target_bins:
        chunk = max(1, total // target_bins)
        chart = []
        for i in range(0, total, chunk):
            batch = parsed[i:i + chunk]
            row = {"date": str(i // chunk + 1), "total": len(batch)}
            action_counts = Counter(a for _, a in batch)
            for action in ("add", "remove", "reclassify"):
                row[action] = action_counts.get(action, 0)
            chart.append(row)
        return chart, total

    # Pick the largest bucket size that still yields >= target_bins
    intervals = [604800, 86400, 21600, 3600, 900, 300, 60]
    bucket_secs = 60
    for secs in intervals:
        if span / secs >= target_bins:
            bucket_secs = secs
            break

    origin = parsed[0][0].replace(second=0, microsecond=0)
    if bucket_secs >= 86400:
        origin = origin.replace(hour=0, minute=0)
    elif bucket_secs >= 3600:
        origin = origin.replace(minute=0)

    bucket_action = Counter()
    bucket_total = Counter()
    for dt, action in parsed:
        idx = int((dt - origin).total_seconds() // bucket_secs)
        bucket_action[(idx, action)] += 1
        bucket_total[idx] += 1

    max_idx = int((parsed[-1][0] - origin).total_seconds() // bucket_secs)

    def fmt(idx):
        dt = origin + timedelta(seconds=idx * bucket_secs)
        if bucket_secs >= 86400:
            return dt.strftime("%m-%d")
        elif bucket_secs >= 3600:
            return dt.strftime("%m-%d %H:00")
        else:
            return dt.strftime("%m-%d %H:%M")

    chart = []
    for i in range(max_idx + 1):
        row = {"date": fmt(i), "total": bucket_total.get(i, 0)}
        for action in ("add", "remove", "reclassify"):
            row[action] = bucket_action.get((i, action), 0)
        chart.append(row)

    return chart, total


@app.get("/api/dashboard/tag-activity")
def dashboard_tag_activity():
    """Aggregate tag log entries with adaptive time bucketing."""
    entries = []
    if USE_SUPABASE:
        try:
            entries = Q.get_tag_log(limit=5000, offset=0)
        except Exception:
            pass
    if not entries and _TAG_LOG_PATH.exists():
        lines = [l for l in _TAG_LOG_PATH.read_text().strip().split("\n") if l]
        entries = [json.loads(l) for l in lines]

    chart, total = _adaptive_bucket_by_action(entries)
    return {"activity": chart, "total_actions": total}


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

    # Auto-discover PDFs by matching fixture name to sources/{gaap}/**/{name}.pdf
    sources_dir = REPO_ROOT / "sources"
    for gaap_dir in ("ifrs", "ugb", "hgb"):
        gaap_path = sources_dir / gaap_dir
        if gaap_path.is_dir():
            for pdf_file in gaap_path.rglob("*.pdf"):
                stem = pdf_file.stem  # e.g. "agrana_2024"
                rel = pdf_file.relative_to(REPO_ROOT)
                if stem not in pdf_map:
                    pdf_map[stem] = {
                        "pdf": str(rel),
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

        try:
            with open(tg_path) as f:
                tg = json.load(f)
        except json.JSONDecodeError as e:
            print(f"WARNING: skipping {doc_id} — corrupt table_graphs.json: {e}")
            continue

        tables = tg.get("tables", [])
        doc_gaap = tg.get("gaap")
        doc_concepts = []

        # Detect page count from docling_elements.json if available
        docling_path = fixture_dir / "docling_elements.json"
        doc_page_count = None
        if docling_path.exists():
            try:
                with open(docling_path) as f:
                    dl = json.load(f)
                pages = dl.get("pages", {})
                if isinstance(pages, dict):
                    doc_page_count = len(pages)
            except Exception:
                pass

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
            "gaap": doc_gaap,
            "page_count": doc_page_count,
            "table_count": len(tables),
            "pdf": pdf_rel if has_pdf else None,
            "has_pdf": has_pdf,
            "tables": len(tables),
            "tagged_concepts": len(set(doc_concepts)),
            "page_offset": page_offset,
        })


@app.get("/api/documents")
def list_documents():
    """List available documents with their PDF status."""
    if USE_SUPABASE:
        return {"documents": Q.query_documents_list()}
    if not _documents:
        _build_document_index()
    return {"documents": _documents}


@app.get("/api/documents/stats")
def documents_stats():
    """Per-document statistics: rows, tagged rows, conflicts."""
    if USE_SUPABASE:
        return {"stats": Q.query_documents_stats()}
    # File-based fallback: compute from table_graphs.json
    stats = []
    for doc in _documents:
        doc_id = doc["id"]
        tg_path = REPO_ROOT / "eval" / "fixtures" / doc_id / "table_graphs.json"
        if not tg_path.exists():
            stats.append({
                "doc_id": doc_id, "slug": doc_id,
                "table_count": 0, "total_rows": 0,
                "tagged_rows": 0, "conflict_rows": 0,
            })
            continue
        with open(tg_path) as f:
            tg = json.load(f)
        tables = tg.get("tables", [])
        total_rows = 0
        tagged_rows = 0
        conflict_rows = 0
        for t in tables:
            for r in t.get("rows", []):
                if r.get("isHeader") or r.get("isSpacer"):
                    continue
                total_rows += 1
                tag = r.get("preTagged", {})
                if tag and tag.get("conceptId"):
                    tagged_rows += 1
        stats.append({
            "doc_id": doc_id, "slug": doc_id,
            "table_count": len(tables), "total_rows": total_rows,
            "tagged_rows": tagged_rows, "conflict_rows": conflict_rows,
        })
    return {"stats": stats}


@app.get("/api/concept-pages/{concept_id:path}")
def concept_pages(concept_id: str):
    """Return all document pages where a concept is tagged, with image URLs."""
    if USE_SUPABASE:
        pages = Q.query_concept_pages(concept_id)
        return {"concept_id": concept_id, "pages": pages}
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
    if USE_SUPABASE:
        return {"doc_id": doc_id, "tables": Q.query_doc_tables(doc_id)}
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
    if USE_SUPABASE:
        doc_info = Q.query_doc_info(doc_id)
        if not doc_info or not doc_info.get("pdf_url"):
            return {"error": "no PDF available"}
        pdf_path = r2_get_pdf_path(doc_id, doc_info["pdf_url"])
        if not pdf_path or not pdf_path.exists():
            return {"error": "PDF file not found"}
        return FileResponse(pdf_path, media_type="application/pdf",
                            headers={"Content-Disposition": f"inline; filename={doc_id}.pdf"})
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
    if USE_SUPABASE:
        return {"fixtures": Q.query_review_status()}
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
    if USE_SUPABASE:
        return Q.query_human_review(doc_id)
    review_path = REPO_ROOT / "eval" / "fixtures" / doc_id / "human_review.json"
    if not review_path.exists():
        return {"exists": False}
    with open(review_path) as f:
        data = json.load(f)
    data["exists"] = True
    return data


@app.post("/api/review/{doc_id}/save")
async def save_human_review_endpoint(doc_id: str, request: Request):
    """Save human_review.json for a document."""
    user = _require_auth(request)
    body = await request.json()
    if USE_SUPABASE:
        Q.save_human_review(doc_id, body, user_id=user.id)
        return {"saved": True, "path": f"supabase:classification_overrides/{doc_id}"}
    fixtures_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    if not fixtures_dir.exists():
        return {"error": "fixture not found"}

    review_path = fixtures_dir / "human_review.json"
    with open(review_path, "w") as f:
        json.dump(body, f, indent=2, default=str)

    return {"saved": True, "path": str(review_path)}


@app.get("/api/review/{doc_id}/tables")
def review_tables(doc_id: str):
    """Return tables with classification info for the review UI."""
    if USE_SUPABASE:
        return {"doc_id": doc_id, "tables": Q.query_review_tables(doc_id)}
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
from ground_truth import (
    load_toc_gt_dict, save_toc_gt_dict, toc_gt_path, gt_dir,
    v1_dict_to_v2_dict, v2_dict_to_v1_dict,
)
from classify_tables import _detect_toc, _parse_toc_entries
from validate_ground_truth import validate_all as validate_gt_all


@app.get("/api/annotate/documents")
def annotate_documents(q: str = "", limit: int = 500, tier: str = "", tier_only: bool = False):
    """Search documents for annotation with server-side filtering.

    tier: optional UGB tier filter — "UGB20", "UGB50", "UGB100", "UGB200", "UGB500", "UGB_ALL", or "" for default TEST_SET.
    tier_only: if True, return only the UGB tier docs (no IFRS prefix). Useful for GT page.
    """
    from test_set import IFRS_TEST_SET, ugb_tier, UGB_ALL as _ugb_all

    tier_map = {
        "UGB20": lambda: ugb_tier(20),
        "UGB50": lambda: ugb_tier(50),
        "UGB100": lambda: ugb_tier(100),
        "UGB200": lambda: ugb_tier(200),
        "UGB500": lambda: ugb_tier(500),
        "UGB_ALL": _ugb_all,
    }

    # Tier filtering: resolve slug list from local tier definitions
    has_tier_filter = tier and tier.upper() in tier_map
    if has_tier_filter:
        ugb_docs = tier_map[tier.upper()]()
        doc_ids = ugb_docs if tier_only else IFRS_TEST_SET + ugb_docs
    elif USE_SUPABASE:
        return {"documents": Q.query_annotate_documents_search(q, limit)}
    else:
        doc_ids = TEST_SET

    # In Supabase mode, query docs from DB using the resolved slug list
    if USE_SUPABASE:
        return {"documents": Q.query_annotate_documents_search(q, limit, slugs=doc_ids)}

    if not _documents:
        _build_document_index()

    # Apply search filter
    if q:
        doc_ids = [d for d in doc_ids if q.lower() in d.lower()]

    # Apply limit
    doc_ids = doc_ids[:limit]

    fixtures_dir = REPO_ROOT / "eval" / "fixtures"
    results = []
    for doc_id in doc_ids:
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

        # Check v2 completion flag
        v2_path = gt_dir(str(fixture_dir)) / "toc_v2.json"
        if v2_path.exists():
            try:
                with open(v2_path) as f:
                    v2 = json.load(f)
                if v2.get("completed_at"):
                    info["completed_at"] = v2["completed_at"]
            except (json.JSONDecodeError, OSError):
                pass

        results.append(info)

    return {"documents": results}


@app.get("/api/annotate/{doc_id}/toc")
def annotate_get_toc(doc_id: str):
    """Load ground truth TOC for a document, or empty template."""
    fixture_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    if USE_SUPABASE and not fixture_dir.exists():
        return Q.query_toc_sections(doc_id)
    gt = load_toc_gt_dict(str(fixture_dir))

    # Get total page count and page dimensions
    page_count = 0
    page_dims = {}
    tg_path = fixture_dir / "table_graphs.json"
    if tg_path.exists():
        try:
            with open(tg_path) as f:
                tg_data = json.load(f)
            pages_obj = tg_data.get("pages", {})
            if isinstance(pages_obj, dict):
                page_count = len(pages_obj)
                for pno, dims in pages_obj.items():
                    page_dims[int(pno)] = {"width": dims.get("width", 595),
                                           "height": dims.get("height", 842)}
        except (json.JSONDecodeError, OSError):
            pass

    # Also check for v2 file
    v2_path = gt_dir(str(fixture_dir)) / "toc_v2.json"
    v2_gt = None
    if v2_path.exists():
        try:
            with open(v2_path) as f:
                v2_gt = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    if gt:
        # Include v2 data if available, otherwise convert v1 on the fly
        ground_truth_v2 = v2_gt or v1_dict_to_v2_dict(gt)
        return {
            "doc_id": doc_id,
            "ground_truth": gt,
            "ground_truth_v2": ground_truth_v2,
            "page_count": page_count,
            "page_dims": page_dims,
        }

    # Return empty template
    return {"doc_id": doc_id, "page_count": page_count, "page_dims": page_dims, "ground_truth": {
        "version": 1,
        "annotator": "",
        "toc_table_id": None,
        "toc_pages": [],
        "sections": [],
        "notes_start_page": None,
        "notes_end_page": None,
    }, "ground_truth_v2": {
        "version": 2,
        "annotator": "",
        "has_toc": None,
        "toc_pages": [],
        "transitions": [],
        "multi_tags": [],
    }}


@app.post("/api/annotate/{doc_id}/toc")
async def annotate_save_toc(doc_id: str, request: Request):
    """Save ground truth TOC for a document.

    Accepts v1 or v2 format. If v2, also writes v1 compat for pipeline.
    """
    _optional_auth(request)
    body = await request.json()
    if USE_SUPABASE:
        # v2 format has transitions; convert to v1 sections for Supabase storage
        if body.get("version", 1) >= 2 and "transitions" in body:
            # Get page_count for end_page calculation
            page_count = Q.get_document_page_count(doc_id)
            v1 = v2_dict_to_v1_dict(body, total_pages=page_count)
            Q.save_toc_sections(doc_id, v1)
        else:
            Q.save_toc_sections(doc_id, body)
        return {"status": "saved", "doc_id": doc_id}
    fixture_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    if not fixture_dir.exists():
        return {"error": f"fixture directory not found: {doc_id}"}

    version = body.get("version", 1)
    if version >= 2:
        # Get total pages for v1 end_page calculation
        total_pages = None
        tg_path = fixture_dir / "table_graphs.json"
        if tg_path.exists():
            try:
                with open(tg_path) as f:
                    tg = json.load(f)
                pages_obj = tg.get("pages", {})
                if isinstance(pages_obj, dict):
                    total_pages = len(pages_obj)
            except (json.JSONDecodeError, OSError):
                pass

        # Save v2 canonical
        v2_path = gt_dir(str(fixture_dir)) / "toc_v2.json"
        v2_path.parent.mkdir(parents=True, exist_ok=True)
        body["annotated_at"] = datetime.now(timezone.utc).isoformat()
        with open(v2_path, "w") as f:
            json.dump(body, f, indent=2, ensure_ascii=False)

        # Write v1 compat
        v1_data = v2_dict_to_v1_dict(body, total_pages=total_pages)
        save_toc_gt_dict(str(fixture_dir), v1_data)
    else:
        save_toc_gt_dict(str(fixture_dir), body)

    return {"status": "saved", "doc_id": doc_id}


# ── Event log (page views, document uploads, etc.) ──────────
_EVENT_LOG_PATH = REPO_ROOT / "eval" / "fixtures" / ".event_log.jsonl"


def _log_event(event_type: str, **kwargs):
    """Append a timestamped event to the event log. Non-blocking, fire-and-forget."""
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "event": event_type, **kwargs}
    try:
        with open(_EVENT_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # never fail the request over logging


def _parse_ts(ts: str):
    """Parse an ISO timestamp string to a datetime object."""
    from datetime import datetime as _dt
    try:
        clean = ts.replace("+00:00", "+0000").replace("Z", "+0000")
        if "+" not in clean and "-" not in clean[10:]:
            clean += "+0000"
        return _dt.fromisoformat(clean.replace("+0000", "+00:00"))
    except (ValueError, TypeError):
        return None


def _adaptive_bucket(timestamps: list[str], target_bins: int = 20) -> list[dict]:
    """Bucket timestamps into ~target_bins data points, adaptive granularity.

    For batch-ingested data (all same timestamp), distributes items across
    synthetic bins so the chart shows a visible shape.
    Returns [{"date": label, "count": n}, ...] with zero-filled gaps.
    """
    from datetime import timedelta
    from collections import Counter

    if not timestamps:
        return []

    parsed = [dt for ts in timestamps if (dt := _parse_ts(ts)) is not None]
    if not parsed:
        return []

    parsed.sort()
    total = len(parsed)
    span = (parsed[-1] - parsed[0]).total_seconds()

    # If we can't get enough natural time bins, spread items evenly
    # into synthetic bins (handles batch ingest + short time spans).
    min_bucket = 60
    max_natural_bins = span / min_bucket if span > 0 else 0
    if max_natural_bins < target_bins or total <= target_bins:
        chunk = max(1, total // target_bins)
        result = []
        for i in range(0, total, chunk):
            n = min(chunk, total - i)
            result.append({"date": str(i // chunk + 1), "count": n})
        return result

    # Pick the largest bucket size that still yields >= target_bins
    intervals = [604800, 86400, 21600, 3600, 900, 300, 60]
    bucket_secs = 60
    for secs in intervals:
        if span / secs >= target_bins:
            bucket_secs = secs
            break

    # Align origin
    origin = parsed[0].replace(second=0, microsecond=0)
    if bucket_secs >= 86400:
        origin = origin.replace(hour=0, minute=0)
    elif bucket_secs >= 3600:
        origin = origin.replace(minute=0)

    bucket_counts = Counter()
    for dt in parsed:
        idx = int((dt - origin).total_seconds() // bucket_secs)
        bucket_counts[idx] += 1

    max_idx = int((parsed[-1] - origin).total_seconds() // bucket_secs)

    def fmt(idx):
        dt = origin + timedelta(seconds=idx * bucket_secs)
        if bucket_secs >= 86400:
            return dt.strftime("%m-%d")
        elif bucket_secs >= 3600:
            return dt.strftime("%m-%d %H:00")
        else:
            return dt.strftime("%m-%d %H:%M")

    return [{"date": fmt(i), "count": bucket_counts.get(i, 0)} for i in range(max_idx + 1)]


@app.get("/api/dashboard/event-activity")
def dashboard_event_activity():
    """Aggregate event log entries with adaptive time bucketing."""
    if not _EVENT_LOG_PATH.exists():
        return {"uploads": [], "views": []}

    lines = [l for l in _EVENT_LOG_PATH.read_text().strip().split("\n") if l]
    entries = [json.loads(l) for l in lines]

    upload_ts = []
    view_ts = []
    for e in entries:
        ts = e.get("timestamp", "")
        evt = e.get("event", "")
        if evt == "document_upload":
            upload_ts.append(ts)
        elif evt == "page_view":
            view_ts.append(ts)

    return {
        "uploads": _adaptive_bucket(upload_ts),
        "views": _adaptive_bucket(view_ts),
    }


# ── Tag action log ───────────────────────────────────────────
_TAG_LOG_PATH = REPO_ROOT / "eval" / "fixtures" / ".tag_log.jsonl"


@app.post("/api/tag-log")
async def append_tag_log(request: Request):
    """Append a tagging action to the audit log."""
    try:
        user = _require_auth(request)
    except Exception:
        user = None
    body = await request.json()
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "user_email": user.email if user else body.get("user_email", "local"),
        "doc_id": body.get("doc_id"),
        "page_no": body.get("page_no"),
        "action": body.get("action"),
        "element_type": body.get("element_type"),
        "old_type": body.get("old_type"),
        "source": body.get("source", "human"),
    }
    if USE_SUPABASE:
        try:
            Q.append_tag_log(entry)
            return {"status": "logged"}
        except Exception:
            pass  # table may not exist yet, fall through to file-based
    with open(_TAG_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return {"status": "logged"}


@app.get("/api/tag-log")
async def get_tag_log(limit: int = Query(200), offset: int = Query(0)):
    """Retrieve tag log entries, most recent first."""
    if USE_SUPABASE:
        try:
            entries = Q.get_tag_log(limit=limit, offset=offset)
            return {"entries": entries, "total": len(entries)}
        except Exception:
            pass  # table may not exist yet, fall through to file-based
    if not _TAG_LOG_PATH.exists():
        return {"entries": [], "total": 0}
    lines = [l for l in _TAG_LOG_PATH.read_text().strip().split("\n") if l]
    total = len(lines)
    lines.reverse()
    entries = [json.loads(l) for l in lines[offset:offset + limit]]
    return {"entries": entries, "total": total}


# ── Voting endpoints ─────────────────────────────────────────


@app.post("/api/votes/cast")
async def cast_vote(request: Request):
    """Cast a tag vote (tag, untag, or dissent). Requires auth."""
    user = _require_auth(request)
    body = await request.json()
    vote = {
        "dimension": body["dimension"],
        "target_id": body["target_id"],
        "action": body["action"],
        "value": body.get("value"),
        "prev_value": body.get("prev_value"),
        "confidence": body.get("confidence"),
        "source": body.get("source", "human"),
        "comment": body.get("comment"),
        "user_id": str(user.id),
    }
    if USE_SUPABASE:
        try:
            result = Q.cast_tag_vote(vote)
            return {"status": "ok", "vote": result}
        except Exception:
            return {"error": "voting tables not yet migrated"}
    return {"error": "voting requires Supabase backend"}


@app.get("/api/votes/{dimension}/{target_id}")
def get_votes(dimension: str, target_id: str):
    """Get votes and consensus for a target."""
    if USE_SUPABASE:
        try:
            data = Q.get_votes(dimension, target_id)
            return data
        except Exception:
            pass
    return {"votes": [], "consensus": None}


@app.get("/api/votes/conflicts/{doc_id}")
def get_vote_conflicts(doc_id: str):
    """Get targets with dissent or multiple distinct values for a document."""
    if USE_SUPABASE:
        try:
            conflicts = Q.get_vote_conflicts(doc_id)
            return {"conflicts": conflicts}
        except Exception:
            pass
    return {"conflicts": []}


# ── Ground Truth Sets ────────────────────────────────────────


_GT_SETS_PATH = REPO_ROOT / "eval" / "fixtures" / ".gt_sets.json"


def _load_gt_sets() -> list[dict]:
    if _GT_SETS_PATH.exists():
        with open(_GT_SETS_PATH) as f:
            return json.load(f)
    return []


def _save_gt_sets(sets: list[dict]):
    with open(_GT_SETS_PATH, "w") as f:
        json.dump(sets, f, indent=2)


@app.get("/api/gt/sets")
def api_list_gt_sets():
    """List all ground truth sets with doc counts."""
    if USE_SUPABASE:
        try:
            return {"sets": Q.query_gt_sets()}
        except Exception:
            pass  # table may not exist yet
    sets = _load_gt_sets()
    for s in sets:
        s["doc_count"] = len(s.get("doc_ids", []))
    return {"sets": sets}


@app.post("/api/gt/sets")
async def api_create_gt_set(request: Request):
    """Create a new GT set."""
    try:
        user = _require_auth(request)
        user_email = user.email
        user_id = str(user.id)
    except Exception:
        user_email = "local"
        user_id = None
    body = await request.json()
    if USE_SUPABASE and user_id:
        try:
            result = Q.create_gt_set(body["name"], body.get("description", ""), user_id)
            return {"set": result}
        except Exception:
            pass  # table may not exist yet
    # File-based fallback
    import uuid
    sets = _load_gt_sets()
    new_set = {
        "id": str(uuid.uuid4()),
        "name": body["name"],
        "description": body.get("description", ""),
        "created_by": user_email,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "doc_ids": [],
    }
    sets.append(new_set)
    _save_gt_sets(sets)
    return {"set": new_set}


def _fixture_stats(doc_id: str) -> dict:
    """Compute docling + tag coverage stats for a fixture."""
    fixture_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    dl_path = fixture_dir / "docling_elements.json"
    tg_path = fixture_dir / "table_graphs.json"

    stats = {
        "docling_size": None,
        "docling_texts": None,
        "docling_tables": None,
        "docling_pages": None,
        "tg_pages": None,
        "docling_match": None,
        "tag_coverage": None,
    }

    # table_graphs page count
    total_pages = None
    if tg_path.exists():
        try:
            with open(tg_path) as f:
                tg = json.load(f)
            tg_page_set = set()
            for t in tg.get("tables", []):
                p = t.get("pageNo")
                if p:
                    tg_page_set.add(p)
            stats["tg_pages"] = len(tg_page_set)
        except Exception:
            pass

    # Docling stats
    if not dl_path.exists():
        stats["docling_match"] = "missing"
    else:
        try:
            size_kb = dl_path.stat().st_size / 1024
            stats["docling_size"] = round(size_kb)

            with open(dl_path) as f:
                dl = json.load(f)

            if "texts" in dl:
                stats["docling_texts"] = len(dl.get("texts", []))
                stats["docling_tables"] = len(dl.get("tables", []))
                pages = set()
                for t in dl.get("texts", []):
                    for prov in t.get("prov", []):
                        p = prov.get("page_no")
                        if p:
                            pages.add(p)
                for t in dl.get("tables", []):
                    for prov in t.get("prov", []):
                        p = prov.get("page_no")
                        if p:
                            pages.add(p)
                stats["docling_pages"] = len(pages)
                if "pages" in dl and isinstance(dl["pages"], dict):
                    total_pages = len(dl["pages"])
            elif "pages" in dl and isinstance(dl["pages"], dict):
                stats["docling_pages"] = len(dl["pages"])
                total_pages = len(dl["pages"])

            if stats["docling_pages"] is not None and stats["tg_pages"] is not None:
                if stats["docling_pages"] >= stats["tg_pages"]:
                    stats["docling_match"] = "ok"
                else:
                    stats["docling_match"] = "partial"
            elif stats["docling_pages"] is not None:
                stats["docling_match"] = "ok"
        except Exception:
            stats["docling_match"] = "error"

    # Tag coverage from toc_v2 or toc v1
    gt_dir_path = fixture_dir / "ground_truth"
    v2_path = gt_dir_path / "toc_v2.json"
    v1_path = gt_dir_path / "toc.json"
    page_count = total_pages or stats.get("docling_pages") or stats.get("tg_pages")

    if page_count and v2_path.exists():
        try:
            with open(v2_path) as f:
                v2 = json.load(f)
            transitions = v2.get("transitions", [])
            if transitions:
                # Every page from first transition onward is tagged
                tagged_from = min(t["page"] for t in transitions)
                tagged_pages = page_count - tagged_from + 1
                stats["tag_coverage"] = min(100, round(100 * tagged_pages / page_count))
        except Exception:
            pass
    elif page_count and v1_path.exists():
        try:
            with open(v1_path) as f:
                v1 = json.load(f)
            sections = v1.get("sections", [])
            if sections:
                tagged = set()
                for sec in sections:
                    sp = sec.get("start_page")
                    ep = sec.get("end_page")
                    if sp and ep:
                        tagged.update(range(sp, ep + 1))
                if tagged:
                    stats["tag_coverage"] = min(100, round(100 * len(tagged) / page_count))
        except Exception:
            pass

    return stats


@app.get("/api/gt/sets/{set_id}/docs")
def api_gt_set_docs(set_id: str):
    """Documents in a GT set with per-doc stats."""
    if USE_SUPABASE:
        try:
            docs = Q.query_gt_set_docs(set_id)
        except Exception:
            docs = None
        if docs is not None:
            return {"docs": docs}
    sets = _load_gt_sets()
    gt_set = next((s for s in sets if s["id"] == set_id), None)
    if not gt_set:
        return {"docs": []}
    docs = []
    for doc_id in gt_set.get("doc_ids", []):
        doc = next((d for d in _documents if d["id"] == doc_id), None)
        if doc:
            entry = {
                "document_id": doc_id,
                "slug": doc_id,
                "entity_name": doc.get("name"),
                "gaap": "IFRS" if "ifrs" in doc_id else "UGB" if "ugb" in doc_id else "IFRS",
                "page_count": doc.get("page_count"),
                "has_pdf": doc.get("has_pdf", False),
            }
            entry.update(_fixture_stats(doc_id))
            docs.append(entry)
    return {"docs": docs}


@app.post("/api/gt/sets/{set_id}/docs")
async def api_add_gt_set_docs(set_id: str, request: Request):
    """Add documents to a GT set."""
    try:
        user = _require_auth(request)
        user_id = str(user.id)
    except Exception:
        user_id = None
    body = await request.json()
    doc_ids = body.get("doc_ids", [])
    if USE_SUPABASE and user_id:
        try:
            count = Q.add_gt_set_docs(set_id, doc_ids, user_id)
            return {"added": count}
        except Exception:
            pass
    # File-based fallback
    sets = _load_gt_sets()
    gt_set = next((s for s in sets if s["id"] == set_id), None)
    if not gt_set:
        return {"error": "set not found", "added": 0}
    existing = set(gt_set.get("doc_ids", []))
    new_ids = [d for d in doc_ids if d not in existing]
    gt_set.setdefault("doc_ids", []).extend(new_ids)
    _save_gt_sets(sets)
    return {"added": len(new_ids)}


@app.delete("/api/gt/sets/{set_id}/docs/{document_id}")
async def api_remove_gt_set_doc(set_id: str, document_id: str, request: Request):
    """Remove a document from a GT set."""
    try:
        _require_auth(request)
    except Exception:
        pass
    if USE_SUPABASE:
        try:
            Q.remove_gt_set_doc(set_id, document_id)
            return {"status": "removed"}
        except Exception:
            pass
    # File-based fallback
    sets = _load_gt_sets()
    gt_set = next((s for s in sets if s["id"] == set_id), None)
    if gt_set and "doc_ids" in gt_set:
        gt_set["doc_ids"] = [d for d in gt_set["doc_ids"] if d != document_id]
        _save_gt_sets(sets)
    return {"status": "removed"}


# ── Document Edges ───────────────────────────────────────────


@app.get("/api/edges/{doc_id}")
def get_doc_edges(doc_id: str):
    """Get all internal edges for a document."""
    if USE_SUPABASE:
        edges = Q.query_doc_edges(doc_id)
        return {"doc_id": doc_id, "edges": edges}
    # File-based fallback: run reference_graph on table_graphs.json
    tg_path = REPO_ROOT / "eval" / "fixtures" / doc_id / "table_graphs.json"
    if not tg_path.exists():
        return {"doc_id": doc_id, "edges": []}
    with open(tg_path) as f:
        tg = json.load(f)
    from reference_graph import build_reference_graph
    ref_graph = build_reference_graph(tg.get("tables", []))

    # Build lookup: table_id → pageNo
    tables_by_id = {t["tableId"]: t for t in tg.get("tables", []) if "tableId" in t}

    # Build lookup: section_type → start_page from ground truth
    gt = load_toc_gt_dict(str(REPO_ROOT / "eval" / "fixtures" / doc_id))
    section_pages: dict[str, int] = {}
    if gt:
        for sec in gt.get("sections", []):
            st = sec.get("statement_type", "")
            if st not in section_pages:
                section_pages[st] = sec.get("start_page", 0)

    edges = []
    for note_num, entries in ref_graph.note_entries.items():
        ctx = ref_graph.context_for_note(note_num)
        for entry in entries:
            source_tbl = tables_by_id.get(entry.source_table_id)
            source_page = source_tbl.get("pageNo") if source_tbl else None
            target_page = section_pages.get(ctx) if ctx else None
            edges.append({
                "id": f"{doc_id}:{entry.source_table_id}:{entry.source_row_idx}:{note_num}",
                "edge_type": "note_ref",
                "source_type": "table_row",
                "source_id": f"{entry.source_table_id}:{entry.source_row_idx}",
                "source_page": source_page,
                "target_type": "toc_section",
                "target_id": ctx or f"note_{note_num}",
                "target_page": target_page,
                "note_number": note_num,
                "confidence": 1.0,
                "validated": False,
                "source_label": entry.source_label,
                "source_context": entry.source_context,
                "target_context": ctx,
            })
    return {"doc_id": doc_id, "edges": edges}


@app.post("/api/edges/{doc_id}")
async def api_create_doc_edge(doc_id: str, request: Request):
    """Create a new internal edge."""
    _require_auth(request)
    body = await request.json()
    if USE_SUPABASE:
        try:
            edge = Q.create_doc_edge(doc_id, body)
            return {"edge": edge}
        except Exception as e:
            return {"error": f"edge creation failed: {e}"}
    return {"error": "requires Supabase backend"}


@app.put("/api/edges/{edge_id}")
async def api_update_doc_edge(edge_id: str, request: Request):
    """Update/validate an internal edge."""
    user = _require_auth(request)
    body = await request.json()
    if "validated" in body and body["validated"]:
        body["validated_by"] = str(user.id)
    if USE_SUPABASE:
        try:
            edge = Q.update_doc_edge(edge_id, body)
            return {"edge": edge}
        except Exception as e:
            return {"error": f"edge update failed: {e}"}
    return {"error": "requires Supabase backend"}


@app.delete("/api/edges/{edge_id}")
async def api_delete_doc_edge(edge_id: str, request: Request):
    """Delete an internal edge."""
    _require_auth(request)
    if USE_SUPABASE:
        try:
            Q.delete_doc_edge(edge_id)
            return {"status": "deleted"}
        except Exception as e:
            return {"error": f"edge deletion failed: {e}"}
    return {"error": "requires Supabase backend"}


@app.post("/api/edges/{doc_id}/auto-detect")
async def auto_detect_edges(doc_id: str, request: Request):
    """Run reference_graph.build_reference_graph() and save detected edges."""
    _require_auth(request)
    fixture_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    tg_path = fixture_dir / "table_graphs.json"
    if not tg_path.exists():
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "Fixture not found"})
    with open(tg_path) as f:
        tg = json.load(f)

    # Precondition: document must have ToC and primary financials in ground truth
    missing = []
    if USE_SUPABASE:
        toc_data = Q.query_toc_sections(doc_id)
        sections = toc_data.get("ground_truth", {}).get("sections", [])
    else:
        gt = load_toc_gt_dict(str(fixture_dir))
        sections = gt.get("sections", []) if gt else []
        if not gt:
            missing.append("ground truth annotations")
    if not missing:
        types = {s.get("statement_type") for s in sections}
        if "TOC" not in types:
            missing.append("ToC section")
        primary = types & {"PNL", "SFP", "OCI", "CFS", "SOCIE"}
        if not primary:
            missing.append("primary financial statements (PNL, SFP, OCI, CFS, or SOCIE)")
    if missing:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=422,
            content={"error": f"Cannot auto-detect edges: missing {', '.join(missing)} in ground truth. Annotate these first."},
        )
    from reference_graph import build_reference_graph
    ref_graph = build_reference_graph(tg.get("tables", []))
    created = 0
    if USE_SUPABASE:
        for note_num, entries in ref_graph.note_entries.items():
            ctx = ref_graph.context_for_note(note_num)
            for entry in entries:
                try:
                    Q.create_doc_edge(doc_id, {
                        "source_type": "table_row",
                        "source_id": f"{entry.source_table_id}:{entry.source_row_idx}",
                        "target_type": "toc_section",
                        "target_id": ctx or f"note_{note_num}",
                        "edge_type": "note_ref",
                        "note_number": note_num,
                        "confidence": 1.0,
                    })
                    created += 1
                except Exception:
                    pass  # duplicate or constraint violation
    return {"doc_id": doc_id, "edges_created": created, "total_note_refs": sum(len(v) for v in ref_graph.note_entries.values())}


# Keywords for mapping TOC entry labels to physical document section types.
# Checked before _STATEMENT_KEYWORDS to catch general reporting sections
# that the table classifier doesn't know about.
_TOC_SECTION_KEYWORDS = {
    # English
    "management report": "MANAGEMENT_REPORT",
    "directors' report": "MANAGEMENT_REPORT",
    "management review": "MANAGEMENT_REPORT",
    "management discussion": "MANAGEMENT_REPORT",
    "report of the management": "MANAGEMENT_REPORT",
    "report of the executive": "MANAGEMENT_REPORT",
    "group management report": "MANAGEMENT_REPORT",
    "consolidated management": "MANAGEMENT_REPORT",
    "auditor's report": "AUDITOR_REPORT",
    "auditor\u00b4s report": "AUDITOR_REPORT",
    "auditor\u2019s report": "AUDITOR_REPORT",
    "auditor report": "AUDITOR_REPORT",
    "independent auditor": "AUDITOR_REPORT",
    "audit report": "AUDITOR_REPORT",
    "assurance report": "AUDITOR_REPORT",
    "corporate governance": "CORPORATE_GOVERNANCE",
    "governance report": "CORPORATE_GOVERNANCE",
    "sustainability": "ESG",
    "esg report": "ESG",
    "non-financial": "ESG",
    "supervisory board": "SUPERVISORY_BOARD",
    "report of the supervisory": "SUPERVISORY_BOARD",
    "aufsichtsrat": "SUPERVISORY_BOARD",
    "risk report": "RISK_REPORT",
    "risk management": "RISK_REPORT",
    "remuneration": "REMUNERATION_REPORT",
    "vergütung": "REMUNERATION_REPORT",
    "responsibility statement": "RESPONSIBILITY_STATEMENT",
    "statement of all members": "RESPONSIBILITY_STATEMENT",
    "erklärung aller mitglieder": "RESPONSIBILITY_STATEMENT",
    "table of contents": "TOC",
    "contents": "TOC",
    "inhaltsverzeichnis": "TOC",
    "to our shareholders": "FRONT_MATTER",
    "an unsere aktionäre": "FRONT_MATTER",
    "further information": "APPENDIX",
    "appendix": "APPENDIX",
    "contact": "APPENDIX",
    "imprint": "APPENDIX",
    "financial calendar": "FRONT_MATTER",
    # German
    "lagebericht": "MANAGEMENT_REPORT",
    "konzernlagebericht": "MANAGEMENT_REPORT",
    "bestätigungsvermerk": "AUDITOR_REPORT",
    "wirtschaftsprüfer": "AUDITOR_REPORT",
    "nachhaltigkeitsbericht": "ESG",
    "nichtfinanzielle": "ESG",
    "risikobericht": "RISK_REPORT",
    "corporate-governance": "CORPORATE_GOVERNANCE",
    "erklärung der gesetzlichen vertreter": "RESPONSIBILITY_STATEMENT",
    "vollständigkeitserklärung": "RESPONSIBILITY_STATEMENT",
}


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
    Note: TOC detection requires local table_graphs.json (not yet ported to Supabase).
    """
    if USE_SUPABASE:
        return {"doc_id": doc_id, "detected": False, "sections": [],
                "error": "TOC detection not yet available in Supabase mode"}
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
    if USE_SUPABASE:
        return {"doc_id": doc_id, "tables": Q.query_annotate_tables(doc_id)}
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
    if USE_SUPABASE:
        return {"doc_id": doc_id, "valid": True, "errors": [],
                "message": "Validation not yet available in Supabase mode"}
    fixture_dir = str(REPO_ROOT / "eval" / "fixtures" / doc_id)
    result = validate_gt_all(fixture_dir)
    return {"doc_id": doc_id, **result}


# ── Annotation v2 endpoints ───────────────────────────────


@app.get("/api/annotate/{doc_id}/page-features")
def annotate_page_features(doc_id: str):
    """Per-page features: rank predictions + TOC entries + note references.

    Combines multiple data sources into a single per-page feature map
    for the annotation workflow UI.
    """
    fixture_dir = REPO_ROOT / "eval" / "fixtures" / doc_id

    # 1. Rank tags (ML page classifier predictions)
    rank_tags: dict = {}
    rank_path = fixture_dir / "rank_tags.json"
    if rank_path.exists():
        try:
            with open(rank_path) as f:
                rt_data = json.load(f)
            rank_tags = rt_data.get("pages", {})
        except (json.JSONDecodeError, OSError):
            pass

    # 2. TOC entries (from pipeline detection)
    toc_entries: dict[int, str] = {}
    toc_refs: dict[int, list] = {}  # target page → list of {label, page} from TOC rows
    tg_path = fixture_dir / "table_graphs.json"
    if tg_path.exists():
        try:
            with open(tg_path) as f:
                tg = json.load(f)
            page_map = _detect_toc(tg.get("tables", []))
            if page_map:
                toc_entries = page_map
            # Build toc_refs: for each TOC row, record the label → target page mapping
            for tbl in tg.get("tables", [])[:20]:
                rows = tbl.get("rows", [])
                if len(rows) < 3:
                    continue
                entries_count = 0
                for r in rows:
                    for c in r.get("cells", []):
                        pv = c.get("parsedValue")
                        if pv is not None and 1 < pv < 500 and pv == int(pv):
                            entries_count += 1
                            break
                if entries_count < 3:
                    continue
                for r in rows:
                    label = r.get("label", "").strip()
                    if not label:
                        continue
                    for c in r.get("cells", []):
                        pv = c.get("parsedValue")
                        if pv is not None and 1 < pv < 500 and pv == int(pv):
                            target_page = int(pv)
                            toc_refs.setdefault(target_page, []).append({
                                "label": label,
                                "page": target_page,
                            })
                            break
                break  # only use first TOC table
        except (json.JSONDecodeError, OSError):
            pass

    # 3. Note references (from reference graph)
    note_refs: dict[int, list] = {}  # page → list of note ref summaries
    if tg_path.exists():
        try:
            with open(tg_path) as f:
                tg = json.load(f)
            from reference_graph import build_reference_graph
            ref_graph = build_reference_graph(tg.get("tables", []))
            # Index note refs by page (via source table page)
            tables_by_id = {t["tableId"]: t for t in tg.get("tables", []) if "tableId" in t}
            for note_num, entries in ref_graph.note_entries.items():
                ctx = ref_graph.context_for_note(note_num)
                for entry in entries:
                    tbl = tables_by_id.get(entry.source_table_id)
                    page = tbl.get("pageNo") if tbl else None
                    if page is not None:
                        note_refs.setdefault(page, []).append({
                            "note_number": note_num,
                            "source_label": entry.source_label,
                            "target_context": ctx,
                        })
        except (json.JSONDecodeError, OSError, Exception):
            pass

    # 4. Get page count
    page_count = 0
    pages_obj = {}
    if tg_path.exists():
        try:
            with open(tg_path) as f:
                tg = json.load(f)
            pages_obj = tg.get("pages", {})
            page_count = len(pages_obj)
        except (json.JSONDecodeError, OSError):
            pass

    # Build per-page feature map
    features: dict[str, dict] = {}
    for p in range(1, page_count + 1):
        ps = str(p)
        feat: dict = {"page": p}

        # Rank predictions
        if ps in rank_tags:
            rt = rank_tags[ps]
            feat["top_class"] = rt.get("top_class")
            feat["top_score"] = rt.get("top_score")
            feat["predictions"] = rt.get("predictions", [])

        # TOC entry
        if p in toc_entries:
            feat["toc_type"] = toc_entries[p]

        # TOC references pointing to this page
        if p in toc_refs:
            feat["toc_refs"] = toc_refs[p]

        # Note refs on this page
        if p in note_refs:
            feat["note_refs"] = note_refs[p]

        features[ps] = feat

    return {"doc_id": doc_id, "page_count": page_count, "features": features}


def _classify_toc_label(label: str) -> str | None:
    """Classify a TOC entry label into a section type."""
    label_lower = label.lower()
    from classify_tables import _STATEMENT_KEYWORDS
    for kw, stype in _TOC_SECTION_KEYWORDS.items():
        if kw in label_lower:
            return stype
    for kw, stmt in _STATEMENT_KEYWORDS.items():
        if kw in label_lower:
            return _map_to_physical_section(stmt, label)
    return None


def _extract_toc_from_text(fixture_dir: Path, page_no: int) -> list[dict]:
    """Extract TOC entries from docling text elements on a given page.

    Parses text items like '269 Income Statement for Group' into
    structured entries with page number and label.
    """
    import re
    dl_path = fixture_dir / "docling_elements.json"
    if not dl_path.exists():
        return []
    try:
        with open(dl_path) as f:
            dl = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    texts = dl.get("texts", [])
    page_texts = [
        t for t in texts
        if (t.get("prov") or [{}])[0].get("page_no") == page_no
    ]

    entries = []
    pattern = re.compile(r"^(\d+)\s+(.+)$")
    for t in page_texts:
        text = (t.get("text") or "").strip()
        m = pattern.match(text)
        if not m:
            continue
        page_num = int(m.group(1))
        label = m.group(2).strip()
        if page_num < 2 or not label:
            continue
        section_type = _classify_toc_label(label)
        entries.append({
            "label": label,
            "page": page_num,
            "section_type": section_type,
            "source": "text",
        })

    return entries


def _finalize_toc_entries(doc_id: str, entries: list[dict],
                          total_pages: int,
                          toc_table_id: str | None = None,
                          toc_page_val: int | None = None) -> dict:
    """Add page_offset and internal_page to TOC entries.

    If TOC page numbers exceed the fixture's page count, computes an offset
    so that internal_page = page - offset maps to fixture page numbers.
    """
    if not entries:
        return {"doc_id": doc_id, "entries": entries, "toc_table_id": toc_table_id,
                "toc_page": toc_page_val, "total_pages": total_pages}

    # Detect page offset: if most entries have page > total_pages,
    # the TOC uses external (full-report) page numbers
    external_count = sum(1 for e in entries if e["page"] > total_pages)
    page_offset = 0
    if external_count > len(entries) // 2 and total_pages > 0:
        # Use the smallest TOC page number to estimate offset
        min_toc_page = min(e["page"] for e in entries)
        # Assume the first TOC entry maps to a page near the start of the fixture
        # (page 2, since page 1 is typically the TOC/cover itself)
        page_offset = min_toc_page - 2

    for e in entries:
        e["external_page"] = e["page"]  # original printed page number
        if page_offset > 0:
            e["internal_page"] = e["page"] - page_offset
        else:
            e["internal_page"] = e["page"]

    return {
        "doc_id": doc_id,
        "entries": entries,
        "toc_table_id": toc_table_id,
        "toc_page": toc_page_val,
        "total_pages": total_pages,
        "page_offset": page_offset,
    }


@app.get("/api/annotate/{doc_id}/toc/entries")
def annotate_toc_entries(doc_id: str, toc_page: int | None = None):
    """Parsed TOC table rows with bboxes.

    Returns individual TOC entries extracted from the detected TOC table,
    including row labels, page numbers, and bounding boxes for overlay display.

    If toc_page is provided, only tables on that page are considered.
    """
    fixture_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    tg_path = fixture_dir / "table_graphs.json"
    if not tg_path.exists():
        return {"doc_id": doc_id, "entries": [], "toc_table_id": None}

    try:
        with open(tg_path) as f:
            tg = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"doc_id": doc_id, "entries": [], "toc_table_id": None}

    tables = tg.get("tables", [])

    # Find the TOC table using same heuristic as _detect_toc
    # If toc_page is specified, only consider tables on that page
    toc_table = None
    candidates = tables[:20]
    if toc_page is not None:
        candidates = [t for t in tables if t.get("pageNo") == toc_page]
    for tbl in candidates:
        rows = tbl.get("rows", [])
        if len(rows) < 3:
            continue
        from reference_graph import has_note_column
        if has_note_column(tbl):
            continue
        entries_count = 0
        for r in rows:
            for c in r.get("cells", []):
                pv = c.get("parsedValue")
                if pv is not None and 1 < pv < 500 and pv == int(pv):
                    entries_count += 1
                    break
        if entries_count >= 3:
            toc_table = tbl
            break

    total_pages = len(tg.get("pages", {}))

    if toc_table:
        # Extract entries from table rows
        entries = []
        for r in toc_table.get("rows", []):
            label = r.get("label", "").strip()
            if not label:
                continue
            page_num = None
            for c in r.get("cells", []):
                pv = c.get("parsedValue")
                if pv is not None and 1 < pv < 500 and pv == int(pv):
                    page_num = int(pv)
            if page_num is None:
                continue
            section_type = _classify_toc_label(label)
            entries.append({
                "label": label,
                "page": page_num,
                "section_type": section_type,
                "bbox": r.get("bbox"),
                "row_idx": r.get("rowIdx"),
                "source": "table",
            })
        return _finalize_toc_entries(doc_id, entries, total_pages,
                                     toc_table_id=toc_table.get("tableId"),
                                     toc_page_val=toc_table.get("pageNo"))

    # Fallback: parse TOC from docling text elements on the specified page
    if toc_page is not None:
        entries = _extract_toc_from_text(fixture_dir, toc_page)
        if entries:
            return _finalize_toc_entries(doc_id, entries, total_pages,
                                         toc_page_val=toc_page)

    return {"doc_id": doc_id, "entries": [], "toc_table_id": None,
            "toc_page": toc_page, "total_pages": total_pages}


@app.post("/api/annotate/{doc_id}/transitions")
async def annotate_save_transitions(doc_id: str, request: Request):
    """Save v2 transitions and write v1 compat file.

    Accepts TocGroundTruthV2 format, persists it, and also writes
    the backward-compatible v1 toc.json for pipeline consumption.
    """
    user = _optional_auth(request)
    body = await request.json()

    # Ensure version is 2
    body.setdefault("version", 2)

    # Save to Supabase: convert v2 transitions → v1 sections
    if USE_SUPABASE:
        page_count = Q.get_document_page_count(doc_id)
        v1_data = v2_dict_to_v1_dict(body, total_pages=page_count)
        Q.save_toc_sections(doc_id, v1_data)

    fixture_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    if fixture_dir.exists():
        # Get total pages for v1 end_page calculation
        total_pages = None
        tg_path = fixture_dir / "table_graphs.json"
        if tg_path.exists():
            try:
                with open(tg_path) as f:
                    tg = json.load(f)
                pages_obj = tg.get("pages", {})
                if isinstance(pages_obj, dict):
                    total_pages = len(pages_obj)
            except (json.JSONDecodeError, OSError):
                pass

        # Load previous transitions for diff
        v2_path = gt_dir(str(fixture_dir)) / "toc_v2.json"
        v2_path.parent.mkdir(parents=True, exist_ok=True)
        old_transitions = {}
        if v2_path.exists():
            try:
                with open(v2_path) as f:
                    old = json.load(f)
                old_transitions = {t["page"]: t.get("section_type") for t in old.get("transitions", [])}
            except (json.JSONDecodeError, OSError):
                pass

        # Save v2 as the canonical format
        body["annotated_at"] = datetime.now(timezone.utc).isoformat()
        with open(v2_path, "w") as f:
            json.dump(body, f, indent=2, ensure_ascii=False)

        # Write v1 compat for pipeline
        v1_data_local = v2_dict_to_v1_dict(body, total_pages=total_pages)
        save_toc_gt_dict(str(fixture_dir), v1_data_local)

        # Log transition changes to tag log
        user_email = user.email if user else "local"
        now = datetime.utcnow().isoformat() + "Z"
        new_transitions = {t["page"]: t for t in body.get("transitions", [])}
        log_entries = []
        for page, t in new_transitions.items():
            old_type = old_transitions.get(page)
            if old_type is None:
                log_entries.append({"timestamp": now, "user_email": user_email, "doc_id": doc_id,
                    "page_no": page, "action": "add", "element_type": t["section_type"],
                    "old_type": None, "source": "human"})
            elif old_type != t["section_type"]:
                log_entries.append({"timestamp": now, "user_email": user_email, "doc_id": doc_id,
                    "page_no": page, "action": "reclassify", "element_type": t["section_type"],
                    "old_type": old_type, "source": "human"})
        for page, old_type in old_transitions.items():
            if page not in new_transitions:
                log_entries.append({"timestamp": now, "user_email": user_email, "doc_id": doc_id,
                    "page_no": page, "action": "remove", "element_type": None,
                    "old_type": old_type, "source": "human"})
        if log_entries:
            with open(_TAG_LOG_PATH, "a") as f:
                for entry in log_entries:
                    f.write(json.dumps(entry) + "\n")
    elif not USE_SUPABASE:
        return {"error": f"fixture directory not found: {doc_id}"}

    # Invalidate browse cache so Element Browser picks up new tags
    global _elements_browse_cache
    _elements_browse_cache = None

    return {"status": "saved", "doc_id": doc_id, "version": 2}


@app.post("/api/annotate/{doc_id}/mark-complete")
async def annotate_mark_complete(doc_id: str, request: Request):
    """Mark a document's annotation as complete (or incomplete).

    Body: {"complete": true} or {"complete": false}
    Writes a `completed_at` timestamp into ground_truth/toc_v2.json.
    """
    user = _optional_auth(request)
    body = await request.json()
    is_complete = body.get("complete", True)

    fixture_dir = REPO_ROOT / "eval" / "fixtures" / doc_id
    if not fixture_dir.exists():
        return {"error": f"fixture directory not found: {doc_id}"}

    v2_path = gt_dir(str(fixture_dir)) / "toc_v2.json"
    v2_data = {}
    if v2_path.exists():
        try:
            with open(v2_path) as f:
                v2_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    if is_complete:
        v2_data["completed_at"] = datetime.now(timezone.utc).isoformat()
        v2_data["completed_by"] = user.email if user else "local"
    else:
        v2_data.pop("completed_at", None)
        v2_data.pop("completed_by", None)

    v2_path.parent.mkdir(parents=True, exist_ok=True)
    with open(v2_path, "w") as f:
        json.dump(v2_data, f, indent=2, ensure_ascii=False)

    return {"status": "ok", "doc_id": doc_id, "complete": is_complete}


# ── Element Browser endpoints ─────────────────────────────

PAGE_CACHE_DIR = Path("/tmp/fobe_page_cache")


@app.get("/api/page-image/{doc_id}/{page_no}")
def page_image(doc_id: str, page_no: int, dpi: int = 150):
    """Render a single PDF page as PNG using PyMuPDF."""
    _log_event("page_view", doc_id=doc_id, page_no=page_no)

    if fitz is None:
        return Response(content=b"pymupdf not installed", status_code=501)

    # Check disk cache first (shared between both modes)
    PAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = f"{doc_id}_{page_no}_{dpi}"
    cache_path = PAGE_CACHE_DIR / f"{cache_key}.png"
    if cache_path.exists():
        return FileResponse(cache_path, media_type="image/png",
                            headers={"Cache-Control": "public, max-age=3600"})

    if USE_SUPABASE:
        doc_info = Q.query_doc_info(doc_id)
        if not doc_info:
            return Response(content=b"document not found", status_code=404)
        pdf_path = r2_get_pdf_path(doc_id, doc_info.get("pdf_url"))
        if not pdf_path:
            return Response(content=b"no PDF available", status_code=404)
        page_offset = doc_info.get("page_offset", 0) or 0
    else:
        if not _documents:
            _build_document_index()
        doc = next((d for d in _documents if d["id"] == doc_id), None)
        if not doc or not doc.get("pdf"):
            return Response(content=b"no PDF available", status_code=404)
        pdf_path = REPO_ROOT / doc["pdf"]
        if not pdf_path.exists():
            return Response(content=b"PDF file not found", status_code=404)
        page_offset = doc.get("page_offset", 0)

    # Render page
    try:
        pdf_doc = fitz.open(str(pdf_path))
        page_idx = (page_no - 1) + page_offset  # page_no is 1-indexed
        if page_idx < 0 or page_idx >= len(pdf_doc):
            pdf_doc.close()
            return Response(content=f"page {page_no} out of range".encode(), status_code=404)
        page = pdf_doc[page_idx]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        pdf_doc.close()
    except Exception as e:
        return Response(content=f"render failed: {e}".encode(), status_code=500)

    # Cache to disk
    cache_path.write_bytes(png_bytes)
    return Response(content=png_bytes, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


_elements_browse_cache: dict | None = None
_elements_browse_cache_time: float = 0

def _build_browse_entry_for_fixture(fixture_dir: Path) -> dict | None:
    """Extract lightweight browse metadata from a single fixture directory.

    Reads only the fields needed for the browse listing — avoids loading
    full row/cell data from multi-MB table_graphs.json files.
    """
    doc_id = fixture_dir.name
    tg_path = fixture_dir / "table_graphs.json"
    if not tg_path.exists():
        return None

    # --- Extract only top-level keys we need via streaming partial parse ---
    # For large files, ijson would be ideal, but stdlib json is fine if we
    # discard data quickly.  The real win is the disk cache below.
    try:
        with open(tg_path) as f:
            tg_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    pages_obj = tg_data.get("pages", {})
    page_count = len(pages_obj) if isinstance(pages_obj, dict) else 0

    page_dims = {}
    if isinstance(pages_obj, dict) and pages_obj:
        for pno, dims in pages_obj.items():
            page_dims[int(pno)] = {"width": dims.get("width", 595),
                                   "height": dims.get("height", 842)}
    else:
        table_pages = {t.get("pageNo") for t in tg_data.get("tables", []) if t.get("pageNo")}
        if table_pages:
            page_count = max(table_pages)
            for pno in table_pages:
                page_dims[pno] = {"width": 595, "height": 842}

    all_tables = []
    for t in tg_data.get("tables", []):
        sc = t.get("metadata", {}).get("statementComponent")
        all_tables.append({
            "tableId": t.get("tableId", ""),
            "pageNo": t.get("pageNo"),
            "statementComponent": sc,
        })

    # Free the large data immediately
    del tg_data

    # Build elements mapping
    elements = defaultdict(lambda: {"pages": set(), "tables": []})

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
                    if not stype:
                        continue
                    sp = sec.get("start_page")
                    ep = sec.get("end_page")
                    if sp and ep:
                        for p in range(sp, ep + 1):
                            elements[stype]["pages"].add(p)
        except (json.JSONDecodeError, OSError):
            pass

    for t in all_tables:
        sc = t.get("statementComponent")
        pno = t.get("pageNo")
        if sc and pno:
            elements[sc]["tables"].append(t)
            elements[sc]["pages"].add(pno)
        elif pno:
            elements["UNCLASSIFIED"]["tables"].append(t)
            elements["UNCLASSIFIED"]["pages"].add(pno)

    elements_out = {}
    for etype, data in elements.items():
        elements_out[etype] = {
            "pages": sorted(data["pages"]),
            "tables": data["tables"],
        }

    return {
        "doc_id": doc_id,
        "gaap": "UGB" if "ugb" in doc_id else "IFRS",
        "page_count": page_count,
        "page_dims": page_dims,
        "has_pdf": False,  # patched by caller
        "source": source,
        "elements": elements_out,
        "has_rank_tags": (fixture_dir / "rank_tags.json").exists(),
    }


# ── Persistent disk cache for /api/elements/browse ──────────────
_BROWSE_CACHE_PATH = REPO_ROOT / "eval" / "fixtures" / ".browse_cache.json"


def _browse_cache_load() -> tuple[dict, dict]:
    """Load per-fixture browse cache from disk.

    Returns (entries_by_doc_id, mtimes_by_doc_id).
    """
    if not _BROWSE_CACHE_PATH.exists():
        return {}, {}
    try:
        with open(_BROWSE_CACHE_PATH) as f:
            raw = json.load(f)
        entries = {e["doc_id"]: e for e in raw.get("entries", [])}
        mtimes = raw.get("mtimes", {})
        return entries, mtimes
    except (json.JSONDecodeError, OSError, KeyError):
        return {}, {}


def _browse_cache_save(entries: dict, mtimes: dict):
    """Persist browse cache to disk."""
    try:
        with open(_BROWSE_CACHE_PATH, "w") as f:
            json.dump({"entries": list(entries.values()), "mtimes": mtimes}, f,
                      separators=(",", ":"))
    except OSError:
        pass


@app.get("/api/elements/browse")
def elements_browse():
    """Build element-type-to-pages mapping across all test-set documents.

    Uses a per-fixture disk cache keyed on table_graphs.json mtime so that
    only changed fixtures are re-parsed.  Typical cold start: <1s (vs 20s+).
    """
    global _elements_browse_cache, _elements_browse_cache_time
    import time as _time
    if USE_SUPABASE:
        return {"documents": Q.query_elements_browse()}
    # In-memory cache: 60s TTL
    if _elements_browse_cache and (_time.time() - _elements_browse_cache_time) < 60:
        return _elements_browse_cache
    if not _documents:
        _build_document_index()

    fixtures_dir = REPO_ROOT / "eval" / "fixtures"

    # Load disk cache
    cached_entries, cached_mtimes = _browse_cache_load()
    entries = {}
    mtimes = {}
    dirty = False

    for fixture_dir in sorted(fixtures_dir.iterdir()):
        if not fixture_dir.is_dir():
            continue
        doc_id = fixture_dir.name
        tg_path = fixture_dir / "table_graphs.json"
        if not tg_path.exists():
            continue

        # Check mtime — skip re-parsing if unchanged
        try:
            current_mtime = tg_path.stat().st_mtime
        except OSError:
            continue
        gt_path = fixture_dir / "ground_truth" / "toc.json"
        gt_mtime = gt_path.stat().st_mtime if gt_path.exists() else 0
        combined_mtime = f"{current_mtime}:{gt_mtime}"

        if doc_id in cached_entries and cached_mtimes.get(doc_id) == combined_mtime:
            entries[doc_id] = cached_entries[doc_id]
            mtimes[doc_id] = combined_mtime
            continue

        # Cache miss — parse this fixture
        entry = _build_browse_entry_for_fixture(fixture_dir)
        if entry:
            entries[doc_id] = entry
            mtimes[doc_id] = combined_mtime
            dirty = True

    # Patch has_pdf from document index
    for doc_id, entry in entries.items():
        doc = next((d for d in _documents if d["id"] == doc_id), None)
        entry["has_pdf"] = doc.get("has_pdf", False) if doc else False

    # Load reviews and attach
    reviews_path = fixtures_dir / ".reviews.json"
    reviews = {}
    if reviews_path.exists():
        try:
            with open(reviews_path) as f:
                reviews = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    for entry in entries.values():
        entry["reviews"] = reviews.get(entry["doc_id"], {})

    results = sorted(entries.values(), key=lambda e: e["doc_id"])
    result = {"documents": results}

    # Save disk cache if anything changed
    if dirty:
        _browse_cache_save(entries, mtimes)

    _elements_browse_cache = result
    _elements_browse_cache_time = _time.time()
    return result


@app.get("/api/elements/browse/{doc_id}/detail")
def elements_browse_detail(doc_id: str):
    """Return full detail for a single document: elements, page_dims, rank_tags."""
    if USE_SUPABASE:
        docs = Q.query_elements_browse(doc_id=doc_id)
        return docs[0] if docs else {}
    fixtures_dir = REPO_ROOT / "eval" / "fixtures"
    fixture_dir = fixtures_dir / doc_id
    tg_path = fixture_dir / "table_graphs.json"
    if not tg_path.exists():
        return {}

    try:
        with open(tg_path) as f:
            tg_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    pages_obj = tg_data.get("pages", {})
    page_dims = {}
    if isinstance(pages_obj, dict):
        for pno, dims in pages_obj.items():
            page_dims[int(pno)] = {"width": dims.get("width", 595),
                                   "height": dims.get("height", 842)}

    all_tables = []
    for t in tg_data.get("tables", []):
        sc = t.get("metadata", {}).get("statementComponent")
        all_tables.append({
            "tableId": t.get("tableId", ""),
            "pageNo": t.get("pageNo"),
            "statementComponent": sc,
        })

    elements = defaultdict(lambda: {"pages": set(), "tables": []})
    gt_path = fixture_dir / "ground_truth" / "toc.json"
    if gt_path.exists():
        try:
            with open(gt_path) as f:
                gt = json.load(f)
            for sec in gt.get("sections", []):
                stype = sec.get("statement_type", "OTHER")
                sp, ep = sec.get("start_page"), sec.get("end_page")
                if sp and ep:
                    for p in range(sp, ep + 1):
                        elements[stype]["pages"].add(p)
        except (json.JSONDecodeError, OSError):
            pass

    for t in all_tables:
        sc, pno = t.get("statementComponent"), t.get("pageNo")
        if sc and pno:
            elements[sc]["tables"].append(t)
            elements[sc]["pages"].add(pno)
        elif pno:
            elements["UNCLASSIFIED"]["tables"].append(t)
            elements["UNCLASSIFIED"]["pages"].add(pno)

    elements_out = {}
    for etype, data in elements.items():
        elements_out[etype] = {"pages": sorted(data["pages"]), "tables": data["tables"]}

    result = {"page_dims": page_dims, "elements": elements_out}

    rt_path = fixture_dir / "rank_tags.json"
    if rt_path.exists():
        try:
            with open(rt_path) as f:
                result["rank_tags"] = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    return result


@app.get("/api/elements/browse/{doc_id}/tables")
def elements_browse_tables(doc_id: str):
    """Return table overlay data (with row/col bboxes) for a single document."""
    if USE_SUPABASE:
        return {"tables": Q.query_doc_overlay_tables(doc_id)}
    fixtures_dir = REPO_ROOT / "eval" / "fixtures"
    tg_path = fixtures_dir / doc_id / "table_graphs.json"
    if not tg_path.exists():
        return {"tables": []}

    try:
        with open(tg_path) as f:
            tg_data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"tables": []}

    all_tables = []
    for t in tg_data.get("tables", []):
        bbox = t.get("bbox", [0, 0, 0, 0])
        sc = t.get("metadata", {}).get("statementComponent")
        entry = {
            "tableId": t.get("tableId", ""),
            "pageNo": t.get("pageNo"),
            "bbox": bbox,
            "statementComponent": sc,
        }
        row_bboxes = []
        for r in t.get("rows", []):
            rb = r.get("bbox", [0, 0, 0, 0])
            if any(v != 0 for v in rb):
                row_bboxes.append({
                    "bbox": rb,
                    "label": r.get("label", "")[:60],
                    "preTagged": r.get("preTagged"),
                    "rowType": r.get("rowType"),
                })
        if row_bboxes:
            entry["rows"] = row_bboxes
        col_bboxes = []
        for c in t.get("columns", []):
            cb = c.get("bbox", [0, 0, 0, 0])
            if any(v != 0 for v in cb):
                col_bboxes.append({
                    "bbox": cb,
                    "role": c.get("role"),
                    "headerLabel": c.get("headerLabel", ""),
                })
        if col_bboxes:
            entry["columns"] = col_bboxes
        all_tables.append(entry)

    return {"tables": all_tables}


# ── Rank tags (MLP predictions) ───────────────────────────

@app.get("/api/elements/rank_tags")
def elements_rank_tags():
    """Serve MLP-predicted rank_tags for all fixtures."""
    if USE_SUPABASE:
        return {"rank_tags": Q.query_rank_tags()}
    fixtures_dir = REPO_ROOT / "eval" / "fixtures"
    results = {}

    for fixture_dir in sorted(fixtures_dir.iterdir()):
        rt_path = fixture_dir / "rank_tags.json"
        if not rt_path.exists():
            continue
        try:
            with open(rt_path) as f:
                results[fixture_dir.name] = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

    return {"rank_tags": results}


@app.get("/api/elements/browse_ranked")
def elements_browse_ranked():
    """Element browser data augmented with rank_tag predictions."""
    base_data = elements_browse()
    fixtures_dir = REPO_ROOT / "eval" / "fixtures"

    return base_data


@app.get("/api/elements/reviews")
def elements_get_reviews():
    if USE_SUPABASE:
        return Q.query_reviews()
    reviews_path = REPO_ROOT / "eval" / "fixtures" / ".reviews.json"
    if reviews_path.exists():
        with open(reviews_path) as f:
            return json.load(f)
    return {}


@app.post("/api/elements/review/{doc_id}/{element_type}")
async def elements_set_review(doc_id: str, element_type: str, request: Request):
    """Mark pages as seen. Body: {"pages": [1,2,3]} or {} to mark entire doc."""
    user = _require_auth(request)
    if USE_SUPABASE:
        body = await request.json() if request.headers.get("content-type") == "application/json" else {}
        pages = body.get("pages")
        Q.set_review(doc_id, element_type, pages, user_id=user.id)
        return {"status": "ok"}
    reviews_path = REPO_ROOT / "eval" / "fixtures" / ".reviews.json"
    reviews = {}
    if reviews_path.exists():
        try:
            with open(reviews_path) as f:
                reviews = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    if doc_id not in reviews:
        reviews[doc_id] = {}

    body = await request.json() if request.headers.get("content-type") == "application/json" else {}
    pages = body.get("pages")

    if pages:
        # Merge pages into existing seen set
        existing = reviews[doc_id].get(element_type, {})
        if isinstance(existing, str):
            # Migrate old format (timestamp) to page-level
            existing = {"all": True}
        if not isinstance(existing, dict):
            existing = {}
        seen = set(existing.get("seen_pages", []))
        seen.update(pages)
        existing["seen_pages"] = sorted(seen)
        existing["updated_at"] = datetime.now().isoformat()
        reviews[doc_id][element_type] = existing
    else:
        # Mark entire doc as reviewed
        reviews[doc_id][element_type] = {"all": True, "updated_at": datetime.now().isoformat()}

    with open(reviews_path, "w") as f:
        json.dump(reviews, f, indent=2)
    return {"status": "ok"}


@app.delete("/api/elements/review/{doc_id}/{element_type}")
async def elements_unset_review(doc_id: str, element_type: str, request: Request):
    user = _require_auth(request)
    if USE_SUPABASE:
        Q.unset_review(doc_id, element_type, user_id=user.id)
        return {"status": "ok"}
    reviews_path = REPO_ROOT / "eval" / "fixtures" / ".reviews.json"
    reviews = {}
    if reviews_path.exists():
        try:
            with open(reviews_path) as f:
                reviews = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    if doc_id in reviews and element_type in reviews[doc_id]:
        del reviews[doc_id][element_type]
        if not reviews[doc_id]:
            del reviews[doc_id]
    with open(reviews_path, "w") as f:
        json.dump(reviews, f, indent=2)
    return {"status": "ok"}


@app.post("/api/elements/retrain")
async def elements_retrain():
    """Retrain MLP classifier and regenerate rank_tags for all fixtures."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "eval/rank_pages.py"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        return {"status": "error", "stderr": result.stderr[-2000:]}
    # Count how many rank_tags.json files were written
    fixtures_dir = REPO_ROOT / "eval" / "fixtures"
    count = sum(1 for d in fixtures_dir.iterdir() if (d / "rank_tags.json").exists())
    return {"status": "ok", "fixtures_updated": count, "stdout": result.stdout[-1000:]}


# ── Docling page elements (all bboxes) ────────────────────

DOCLING_SEARCH_DIRS = [
    Path("/tmp/fobe_corpus"),
    Path("/tmp/doc_tag"),
]


def _find_docling_json(doc_id: str) -> Path | None:
    """Locate the Docling JSON for a fixture."""
    for search_dir in DOCLING_SEARCH_DIRS:
        if not search_dir.is_dir():
            continue
        # Pattern: <dir>/<doc_id>/<doc_id>_tables_stitched/<doc_id>_docling.json
        candidate = search_dir / doc_id / f"{doc_id}_tables_stitched" / f"{doc_id}_docling.json"
        if candidate.exists():
            return candidate
        # Also try finding by glob
        for p in search_dir.glob(f"*{doc_id}*/*_docling.json"):
            return p
    # Check fixture dir itself
    fixture_candidate = REPO_ROOT / "eval" / "fixtures" / doc_id / "docling_elements.json"
    if fixture_candidate.exists():
        return fixture_candidate
    return None


def _extract_docling_page_elements(data: dict, page_no: int) -> dict:
    """Extract all Docling-detected elements on a page with their bboxes."""
    elements = []

    # Extract text elements
    for t in data.get("texts", []):
        prov = t.get("prov", [])
        if not prov or prov[0].get("page_no") != page_no:
            continue
        bb = prov[0].get("bbox", {})
        if not isinstance(bb, dict):
            continue
        elements.append({
            "label": t.get("label", "text"),
            "text": (t.get("text") or "")[:80],
            "bbox": [bb.get("l", 0), bb.get("t", 0), bb.get("r", 0), bb.get("b", 0)],
            "coord_origin": bb.get("coord_origin", "BOTTOMLEFT"),
        })

    # Extract pictures
    for p in data.get("pictures", []):
        prov = p.get("prov", [])
        if not prov or prov[0].get("page_no") != page_no:
            continue
        bb = prov[0].get("bbox", {})
        if not isinstance(bb, dict):
            continue
        elements.append({
            "label": p.get("label", "picture"),
            "text": "",
            "bbox": [bb.get("l", 0), bb.get("t", 0), bb.get("r", 0), bb.get("b", 0)],
            "coord_origin": bb.get("coord_origin", "BOTTOMLEFT"),
        })

    # Extract tables (just label + bbox, detail is already in table_graphs)
    for t in data.get("tables", []):
        prov = t.get("prov", [])
        if not prov or prov[0].get("page_no") != page_no:
            continue
        bb = prov[0].get("bbox", {})
        if not isinstance(bb, dict):
            continue
        num_rows = len(t.get("data", {}).get("grid", []))
        elements.append({
            "label": "table",
            "text": f"{num_rows} rows",
            "bbox": [bb.get("l", 0), bb.get("t", 0), bb.get("r", 0), bb.get("b", 0)],
            "coord_origin": bb.get("coord_origin", "BOTTOMLEFT"),
        })

    return {"elements": elements, "available": True}


@app.get("/api/docling-elements/{doc_id}/{page_no}")
def docling_page_elements(doc_id: str, page_no: int):
    """Return all Docling-detected elements on a page with their bboxes."""
    if USE_SUPABASE:
        doc_info = Q.query_doc_info(doc_id)
        data = r2_get_docling_json(doc_id, doc_info.get("docling_url") if doc_info else None)
        if not data:
            docling_path = _find_docling_json(doc_id)
            if docling_path:
                with open(docling_path) as f:
                    data = json.load(f)
        if not data:
            return {"elements": [], "available": False}
        return _extract_docling_page_elements(data, page_no)
    docling_path = _find_docling_json(doc_id)
    if not docling_path:
        return {"elements": [], "available": False}

    try:
        with open(docling_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"elements": [], "available": False}

    return _extract_docling_page_elements(data, page_no)


@app.get("/api/docling-available/{doc_id}")
def docling_available(doc_id: str):
    """Check if Docling JSON is available for a document."""
    if USE_SUPABASE:
        if Q.query_docling_available(doc_id):
            return {"available": True}
        # Fall back to local files (r2_get_docling_json checks local docling_elements.json)
    return {"available": _find_docling_json(doc_id) is not None}


# ── Ontology Gaps ────────────────────────────────────────────


_GAPS_PATH = REPO_ROOT / "eval" / "fixtures" / ".ontology_gaps.json"
_PROPOSALS_PATH = REPO_ROOT / "eval" / "fixtures" / ".concept_proposals.json"


def _load_gaps() -> list[dict]:
    if _GAPS_PATH.exists():
        with open(_GAPS_PATH) as f:
            return json.load(f)
    return []


def _save_gaps(gaps: list[dict]):
    with open(_GAPS_PATH, "w") as f:
        json.dump(gaps, f, indent=2, default=str)


def _load_proposals() -> list[dict]:
    if _PROPOSALS_PATH.exists():
        with open(_PROPOSALS_PATH) as f:
            return json.load(f)
    return []


def _save_proposals(proposals: list[dict]):
    with open(_PROPOSALS_PATH, "w") as f:
        json.dump(proposals, f, indent=2, default=str)


@app.get("/api/ontology/gaps")
def api_list_gaps(status: str = None, context: str = None):
    """List ontology gaps."""
    if USE_SUPABASE:
        try:
            gaps = Q.query_ontology_gaps(status=status, context=context)
            return {"gaps": gaps}
        except Exception:
            pass
    # File-based fallback
    gaps = _load_gaps()
    if status:
        gaps = [g for g in gaps if g.get("status") == status]
    if context:
        gaps = [g for g in gaps if g.get("context") == context]
    return {"gaps": gaps}


@app.post("/api/ontology/gaps")
async def api_create_gap(request: Request):
    """Flag a new ontology gap."""
    user = _require_auth(request)
    body = await request.json()
    gap = {
        "row_label": body["row_label"],
        "context": body.get("context"),
        "description": body.get("description"),
        "document_id": body.get("document_id"),
        "table_id": body.get("table_id"),
        "row_id": body.get("row_id"),
        "status": "open",
        "reported_by": str(user.id),
    }
    if USE_SUPABASE:
        try:
            result = Q.create_ontology_gap(gap)
            return {"gap": result}
        except Exception:
            pass
    # File-based fallback
    import uuid
    gap["id"] = str(uuid.uuid4())
    gap["created_at"] = datetime.utcnow().isoformat()
    gaps = _load_gaps()
    gaps.insert(0, gap)
    _save_gaps(gaps)
    return {"gap": gap}


@app.put("/api/ontology/gaps/{gap_id}")
async def api_update_gap(gap_id: str, request: Request):
    """Update an ontology gap (status, resolution)."""
    user = _require_auth(request)
    body = await request.json()
    if body.get("status") in ("accepted", "rejected", "duplicate"):
        body["resolved_by"] = str(user.id)
        body["resolved_at"] = datetime.utcnow().isoformat()
    if USE_SUPABASE:
        try:
            result = Q.update_ontology_gap(gap_id, body)
            return {"gap": result}
        except Exception:
            pass
    # File-based fallback
    gaps = _load_gaps()
    for g in gaps:
        if g.get("id") == gap_id:
            g.update(body)
            _save_gaps(gaps)
            return {"gap": g}
    return {"error": "gap not found"}


@app.get("/api/ontology/proposals")
def api_list_proposals(status: str = None):
    """List concept proposals."""
    if USE_SUPABASE:
        try:
            proposals = Q.query_concept_proposals(status=status)
            return {"proposals": proposals}
        except Exception:
            pass
    # File-based fallback
    proposals = _load_proposals()
    if status:
        proposals = [p for p in proposals if p.get("status") == status]
    return {"proposals": proposals}


@app.post("/api/ontology/proposals")
async def api_create_proposal(request: Request):
    """Propose a new concept to fill a gap."""
    user = _require_auth(request)
    body = await request.json()
    proposal = {
        "gap_id": body.get("gap_id"),
        "concept_id": body["concept_id"],
        "label": body["label"],
        "context": body.get("context"),
        "balance_type": body.get("balance_type"),
        "period_type": body.get("period_type"),
        "unit_type": body.get("unit_type"),
        "is_total": body.get("is_total", False),
        "gaap": body.get("gaap"),
        "aliases": body.get("aliases", []),
        "rationale": body.get("rationale"),
        "example_docs": body.get("example_docs", []),
        "status": "draft",
        "proposed_by": str(user.id),
    }
    if USE_SUPABASE:
        try:
            result = Q.create_concept_proposal(proposal)
            # Link gap to proposal
            if body.get("gap_id"):
                try:
                    Q.update_ontology_gap(body["gap_id"], {
                        "status": "proposed",
                        "proposed_concept_id": proposal.get("concept_id", body["concept_id"]),
                    })
                except Exception:
                    pass
            return {"proposal": result}
        except Exception:
            pass
    # File-based fallback
    import uuid
    proposal["id"] = str(uuid.uuid4())
    proposal["created_at"] = datetime.utcnow().isoformat()
    proposals = _load_proposals()
    proposals.insert(0, proposal)
    _save_proposals(proposals)
    # Update linked gap
    if body.get("gap_id"):
        gaps = _load_gaps()
        for g in gaps:
            if g.get("id") == body["gap_id"]:
                g["status"] = "proposed"
                g["proposed_concept_id"] = body["concept_id"]
                _save_gaps(gaps)
                break
    return {"proposal": proposal}


@app.put("/api/ontology/proposals/{proposal_id}")
async def api_update_proposal(proposal_id: str, request: Request):
    """Update a concept proposal."""
    user = _require_auth(request)
    body = await request.json()
    if body.get("status") in ("accepted", "rejected"):
        body["reviewed_by"] = str(user.id)
        body["reviewed_at"] = datetime.utcnow().isoformat()
    if USE_SUPABASE:
        try:
            result = Q.update_concept_proposal(proposal_id, body)
            return {"proposal": result}
        except Exception:
            pass
    # File-based fallback
    proposals = _load_proposals()
    for p in proposals:
        if p.get("id") == proposal_id:
            p.update(body)
            _save_proposals(proposals)
            return {"proposal": p}
    return {"error": "proposal not found"}


@app.post("/api/ontology/proposals/{proposal_id}/accept")
async def api_accept_proposal(proposal_id: str, request: Request):
    """Accept a proposal: mark as accepted and update linked gap."""
    user = _require_auth(request)
    if USE_SUPABASE:
        try:
            Q.update_concept_proposal(proposal_id, {
                "status": "accepted",
                "reviewed_by": str(user.id),
                "reviewed_at": datetime.utcnow().isoformat(),
            })
            # TODO: insert into concepts + aliases + gaap_labels tables
            return {"status": "accepted"}
        except Exception:
            pass
    # File-based fallback
    proposals = _load_proposals()
    for p in proposals:
        if p.get("id") == proposal_id:
            p["status"] = "accepted"
            p["reviewed_by"] = str(user.id)
            p["reviewed_at"] = datetime.utcnow().isoformat()
            _save_proposals(proposals)
            # Update linked gap
            if p.get("gap_id"):
                gaps = _load_gaps()
                for g in gaps:
                    if g.get("id") == p["gap_id"]:
                        g["status"] = "accepted"
                        g["resolved_by"] = str(user.id)
                        g["resolved_at"] = datetime.utcnow().isoformat()
                        _save_gaps(gaps)
                        break
            return {"status": "accepted"}
    return {"error": "proposal not found"}


@app.post("/api/ontology/proposals/{proposal_id}/reject")
async def api_reject_proposal(proposal_id: str, request: Request):
    """Reject a proposal."""
    user = _require_auth(request)
    if USE_SUPABASE:
        try:
            Q.update_concept_proposal(proposal_id, {
                "status": "rejected",
                "reviewed_by": str(user.id),
                "reviewed_at": datetime.utcnow().isoformat(),
            })
            return {"status": "rejected"}
        except Exception:
            pass
    # File-based fallback
    proposals = _load_proposals()
    for p in proposals:
        if p.get("id") == proposal_id:
            p["status"] = "rejected"
            p["reviewed_by"] = str(user.id)
            p["reviewed_at"] = datetime.utcnow().isoformat()
            _save_proposals(proposals)
            return {"status": "rejected"}
    return {"error": "proposal not found"}


# ── Pipeline Runs ────────────────────────────────────────────


_RUNS_DIR = REPO_ROOT / "eval" / "runs"
_RUNS_STATE_PATH = REPO_ROOT / "eval" / "runs" / ".runs_index.json"
_active_processes: dict[str, "subprocess.Popen"] = {}


def _load_runs_index() -> list[dict]:
    if _RUNS_STATE_PATH.exists():
        with open(_RUNS_STATE_PATH) as f:
            return json.load(f)
    return []


def _save_runs_index(runs: list[dict]):
    _RUNS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_RUNS_STATE_PATH, "w") as f:
        json.dump(runs, f, indent=2, default=str)


def _make_run_id() -> str:
    from datetime import datetime
    now = datetime.utcnow()
    # Count today's runs
    runs = _load_runs_index()
    today = now.strftime("%d%m%Y")
    today_count = sum(1 for r in runs if r.get("run_id", "").startswith(today + "EVAL"))
    return f"{today}EVAL{today_count + 1:03d}"


def _read_run_summary(run_id: str) -> dict | None:
    summary_path = _RUNS_DIR / run_id / "summary.json"
    if summary_path.exists():
        with open(summary_path) as f:
            return json.load(f)
    return None


def _read_run_results(run_id: str) -> list[dict]:
    """Read per-document pipeline.json results from a run directory."""
    run_dir = _RUNS_DIR / run_id
    if not run_dir.exists():
        return []
    results = []
    for doc_dir in sorted(run_dir.iterdir()):
        if not doc_dir.is_dir() or doc_dir.name.startswith("."):
            continue
        pipeline_json = doc_dir / "pipeline.json"
        if pipeline_json.exists():
            with open(pipeline_json) as f:
                data = json.load(f)
            results.append({
                "document_id": doc_dir.name,
                "status": data.get("status", "completed"),
                "halted_at": data.get("halted_at"),
                "stage_results": data.get("stage_results", {}),
                "metrics": data.get("metrics", {}),
                "error": data.get("error"),
            })
    return results


def _update_run_progress(run_id: str):
    """Update a run's progress from its output directory."""
    runs = _load_runs_index()
    for run in runs:
        if run["run_id"] == run_id:
            results = _read_run_results(run_id)
            docs_completed = len(results)
            docs_total = len(run.get("config", {}).get("documents", []))
            run["progress"] = {
                "docs_completed": docs_completed,
                "docs_total": docs_total,
            }
            # Check if process is still alive
            proc = _active_processes.get(run_id)
            if proc:
                poll = proc.poll()
                if poll is not None:
                    # Process finished
                    del _active_processes[run_id]
                    summary = _read_run_summary(run_id)
                    run["status"] = "completed" if poll == 0 else "failed"
                    run["completed_at"] = datetime.utcnow().isoformat()
                    if summary:
                        run["summary"] = summary
            _save_runs_index(runs)
            return run
    return None


@app.get("/api/runs/defaults")
def api_run_defaults():
    """Return default pipeline config and thresholds."""
    sys.path.insert(0, str(REPO_ROOT / "eval"))
    from pipeline import PipelineConfig
    return {
        "thresholds": PipelineConfig.DEFAULT_THRESHOLDS,
        "stages": ["stage1", "stage2", "stage3", "stage4", "stage5", "stage6"],
    }


@app.get("/api/runs")
def api_list_runs():
    """List all pipeline runs."""
    runs = _load_runs_index()
    # Update progress for running runs
    for run in runs:
        if run.get("status") == "running":
            _update_run_progress(run["run_id"])
    runs = _load_runs_index()  # Re-read after updates
    return {"runs": runs}


@app.get("/api/runs/{run_id}")
def api_get_run(run_id: str):
    """Get a single run with progress."""
    runs = _load_runs_index()
    for run in runs:
        if run["run_id"] == run_id:
            if run.get("status") == "running":
                _update_run_progress(run_id)
                runs = _load_runs_index()
                for r in runs:
                    if r["run_id"] == run_id:
                        return r
            return run
    return {"error": "run not found"}


@app.get("/api/runs/{run_id}/results")
def api_get_run_results(run_id: str):
    """Get per-document results for a run."""
    results = _read_run_results(run_id)
    return {"results": results}


@app.post("/api/runs")
async def api_create_run(request: Request):
    """Create and start a new pipeline run."""
    import subprocess
    user = _require_auth(request)
    body = await request.json()

    run_id = _make_run_id()
    documents = body.get("documents", [])
    stages = body.get("stages")
    config = body.get("config", {})

    # Build CLI args
    cmd = [
        sys.executable, str(REPO_ROOT / "eval" / "pipeline_runner.py"),
        "--all",
        "--output-dir", str(_RUNS_DIR / run_id),
        "--verbose",
    ]
    if documents:
        cmd.extend(["--documents"] + documents)
    if stages:
        cmd.extend(["--stages", ",".join(stages)])
    if not config.get("use_llm", True):
        cmd.append("--no-llm")
    if config.get("reclassify", False):
        cmd.append("--reclassify")
    if config.get("use_ground_truth", False):
        cmd.append("--use-ground-truth")

    # Store run in index
    run_entry = {
        "run_id": run_id,
        "status": "running",
        "created_by": str(user.id),
        "config": {
            "documents": documents,
            "stages": stages,
            "use_llm": config.get("use_llm", True),
            "reclassify": config.get("reclassify", False),
            "use_ground_truth": config.get("use_ground_truth", False),
            "gaap_filter": config.get("gaap_filter"),
            "thresholds": config.get("thresholds", {}),
        },
        "progress": {"docs_completed": 0, "docs_total": len(documents)},
        "started_at": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    }
    runs = _load_runs_index()
    runs.insert(0, run_entry)
    _save_runs_index(runs)

    # Launch subprocess
    (_RUNS_DIR / run_id).mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=open(_RUNS_DIR / run_id / "stdout.log", "w"),
        stderr=subprocess.STDOUT,
    )
    _active_processes[run_id] = proc

    return {"run": run_entry}


@app.post("/api/runs/{run_id}/cancel")
async def api_cancel_run(run_id: str, request: Request):
    """Cancel a running pipeline."""
    _require_auth(request)
    proc = _active_processes.get(run_id)
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        del _active_processes[run_id]

    runs = _load_runs_index()
    for run in runs:
        if run["run_id"] == run_id:
            run["status"] = "cancelled"
            run["completed_at"] = datetime.utcnow().isoformat()
            _save_runs_index(runs)
            return {"status": "cancelled"}
    return {"error": "run not found"}


# ── Machine Tag Runs ──────────────────────────────────────
_MT_RUNS_DIR = REPO_ROOT / "eval" / "machine_tag_runs"
_MT_RUNS_STATE_PATH = _MT_RUNS_DIR / ".mt_runs_index.json"
_mt_active_processes: dict[str, "subprocess.Popen"] = {}


def _load_mt_runs_index() -> list[dict]:
    if _MT_RUNS_STATE_PATH.exists():
        with open(_MT_RUNS_STATE_PATH) as f:
            return json.load(f)
    return []


def _save_mt_runs_index(runs: list[dict]):
    _MT_RUNS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_MT_RUNS_STATE_PATH, "w") as f:
        json.dump(runs, f, indent=2, default=str)


def _make_mt_run_id() -> str:
    now = datetime.utcnow()
    runs = _load_mt_runs_index()
    today = now.strftime("%d%m%Y")
    today_count = sum(1 for r in runs if r.get("run_id", "").startswith(today + "MT"))
    return f"{today}MT{today_count + 1:03d}"


def _read_mt_run_summary(run_id: str) -> dict | None:
    summary_path = _MT_RUNS_DIR / run_id / "summary.json"
    if summary_path.exists():
        with open(summary_path) as f:
            return json.load(f)
    return None


def _read_mt_run_results(run_id: str) -> list[dict]:
    """Read per-document result.json files from a machine tag run directory."""
    run_dir = _MT_RUNS_DIR / run_id
    if not run_dir.exists():
        return []
    results = []
    for doc_dir in sorted(run_dir.iterdir()):
        if not doc_dir.is_dir() or doc_dir.name.startswith("."):
            continue
        result_json = doc_dir / "result.json"
        if result_json.exists():
            with open(result_json) as f:
                results.append(json.load(f))
    return results


def _update_mt_run_progress(run_id: str):
    """Update a machine tag run's progress from its output directory."""
    runs = _load_mt_runs_index()
    for run in runs:
        if run["run_id"] == run_id:
            results = _read_mt_run_results(run_id)
            docs_completed = len(results)
            docs_total = len(run.get("config", {}).get("documents", []))
            run["progress"] = {
                "docs_completed": docs_completed,
                "docs_total": docs_total,
            }
            proc = _mt_active_processes.get(run_id)
            if proc:
                poll = proc.poll()
                if poll is not None:
                    del _mt_active_processes[run_id]
                    summary = _read_mt_run_summary(run_id)
                    run["status"] = "completed" if poll == 0 else "failed"
                    run["completed_at"] = datetime.utcnow().isoformat()
                    if summary:
                        run["summary"] = summary
            _save_mt_runs_index(runs)
            return run
    return None


@app.get("/api/machine-tag/runs")
def api_list_mt_runs():
    """List all machine tag runs."""
    runs = _load_mt_runs_index()
    for run in runs:
        if run.get("status") == "running":
            _update_mt_run_progress(run["run_id"])
    runs = _load_mt_runs_index()
    return {"runs": runs}


@app.get("/api/machine-tag/runs/{run_id}")
def api_get_mt_run(run_id: str):
    """Get a single machine tag run with progress."""
    runs = _load_mt_runs_index()
    for run in runs:
        if run["run_id"] == run_id:
            if run.get("status") == "running":
                _update_mt_run_progress(run_id)
                runs = _load_mt_runs_index()
                for r in runs:
                    if r["run_id"] == run_id:
                        return r
            return run
    return {"error": "run not found"}


@app.get("/api/machine-tag/runs/{run_id}/results")
def api_get_mt_run_results(run_id: str):
    """Get per-document results for a machine tag run."""
    results = _read_mt_run_results(run_id)
    return {"results": results}


@app.post("/api/machine-tag/runs")
async def api_create_mt_run(request: Request):
    """Create and start a new machine tag run."""
    import subprocess
    user = _require_auth(request)
    body = await request.json()

    run_id = _make_mt_run_id()
    model = body.get("model", "pretag")
    documents = body.get("documents", [])
    config = body.get("config", {})

    cmd = [
        sys.executable, str(REPO_ROOT / "eval" / "machine_tag_runner.py"),
        "--model", model,
        "--documents", *documents,
        "--output-dir", str(_MT_RUNS_DIR / run_id),
    ]
    if config.get("dry_run"):
        cmd.append("--dry-run")
    if config.get("verbose"):
        cmd.append("--verbose")
    if config.get("write_tag_log"):
        cmd.append("--write-tag-log")
    if config.get("write_voting"):
        cmd.append("--write-voting")

    run_entry = {
        "run_id": run_id,
        "status": "running",
        "created_by": str(user.id),
        "config": {
            "model": model,
            "documents": documents,
            "dry_run": config.get("dry_run", False),
            "verbose": config.get("verbose", False),
            "write_tag_log": config.get("write_tag_log", False),
            "write_voting": config.get("write_voting", False),
        },
        "progress": {"docs_completed": 0, "docs_total": len(documents)},
        "started_at": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    }
    runs = _load_mt_runs_index()
    runs.insert(0, run_entry)
    _save_mt_runs_index(runs)

    (_MT_RUNS_DIR / run_id).mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        stdout=open(_MT_RUNS_DIR / run_id / "stdout.log", "w"),
        stderr=subprocess.STDOUT,
    )
    _mt_active_processes[run_id] = proc

    return {"run": run_entry}


@app.post("/api/machine-tag/runs/{run_id}/cancel")
async def api_cancel_mt_run(run_id: str, request: Request):
    """Cancel a running machine tag run."""
    _require_auth(request)
    proc = _mt_active_processes.get(run_id)
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        del _mt_active_processes[run_id]

    runs = _load_mt_runs_index()
    for run in runs:
        if run["run_id"] == run_id:
            run["status"] = "cancelled"
            run["completed_at"] = datetime.utcnow().isoformat()
            _save_mt_runs_index(runs)
            return {"status": "cancelled"}
    return {"error": "run not found"}


# ── Serve frontend static files ───────────────────────────
FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    # Pre-load graph
    get_graph()
    s = stats()
    print(f"FOBE Explorer: {s['concepts']} concepts, {s['edges']} edges, {s['contexts']} contexts")
    print(f"  Primary: {', '.join(s['primary_contexts'])}")
    print(f"  Disclosure: {', '.join(s['disclosure_contexts'])}")

    if USE_SUPABASE:
        print("Data source: Supabase")
    else:
        _build_document_index()
        print(f"Data source: local files — {len(_documents)} fixtures, {len(_concept_pages)} concept→page mappings")
        # Pre-warm elements browse cache (avoids 17s cold start on first request)
        import time as _t
        _t0 = _t.time()
        elements_browse()
        print(f"Elements browse cache warmed in {_t.time() - _t0:.1f}s")

    print("Starting server at http://localhost:8787")
    uvicorn.run(app, host="0.0.0.0", port=8787)
