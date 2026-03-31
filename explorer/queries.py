"""
Supabase query functions for the FOBE explorer server.

Each function returns data in the exact shape the current file-based endpoints produce,
so the frontend needs zero changes.
"""

import time
import logging
from collections import defaultdict

from explorer.supabase_client import get_supabase, reset_supabase, resolve_doc_uuid

logger = logging.getLogger(__name__)

_RETRYABLE = (
    "RemoteProtocolError", "ConnectionTerminated", "WriteError",
    "Broken pipe", "Connection reset", "GOAWAY",
)


def _is_retryable(exc: Exception) -> bool:
    """Check if an exception is a transient Supabase/HTTP2 connection error."""
    msg = f"{type(exc).__name__}: {exc}"
    return any(token in msg for token in _RETRYABLE)


# ── Documents ────────────────────────────────────────────────


def _paginated_select(table_name: str, select: str, page_size: int = 1000,
                      max_retries: int = 3) -> list[dict]:
    """Fetch all rows from a Supabase table, paginating past the default limit.

    Retries on transient HTTP/2 connection errors (broken pipe, GOAWAY, etc.).
    """
    sb = get_supabase()
    all_rows = []
    offset = 0
    while True:
        for attempt in range(max_retries):
            try:
                batch = (sb.table(table_name).select(select)
                         .range(offset, offset + page_size - 1)
                         .execute().data)
                break
            except Exception as exc:
                if attempt < max_retries - 1 and _is_retryable(exc):
                    wait = 0.5 * (attempt + 1)
                    logger.warning("Supabase retry %d/%d for %s: %s (wait %.1fs)",
                                   attempt + 1, max_retries, table_name, exc, wait)
                    time.sleep(wait)
                    sb = reset_supabase()  # fresh client after connection error
                    continue
                raise
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_rows


_doc_list_cache = {"data": None, "ts": 0}
_table_counts_cache = {"data": None, "ts": 0}
_TABLE_COUNTS_TTL = 300  # 5 minutes — tables rarely change


def _get_table_counts() -> dict[str, int]:
    """Fetch table counts per document, cached for 5 minutes.

    This avoids fetching the full 97K+ tables table on every request.
    """
    now = time.time()
    if (_table_counts_cache["data"] is not None
            and now - _table_counts_cache["ts"] < _TABLE_COUNTS_TTL):
        return _table_counts_cache["data"]

    tables = _paginated_select("tables", "document_id")
    counts = {}
    for t in tables:
        doc_id = t["document_id"]
        counts[doc_id] = counts.get(doc_id, 0) + 1

    _table_counts_cache["data"] = counts
    _table_counts_cache["ts"] = now
    return counts


def query_documents_list(force_refresh: bool = False) -> list[dict]:
    """Replace _build_document_index() → _documents list.

    Caches for 60s.  Table counts are computed once from the tables table
    and cached alongside the document list.
    """
    import time

    now = time.time()
    if (not force_refresh
            and _doc_list_cache["data"] is not None
            and now - _doc_list_cache["ts"] < 60):
        return _doc_list_cache["data"]

    # Try fetching with denormalized counts; fall back if columns don't exist yet
    try:
        docs = _paginated_select("documents",
            "id, slug, entity_name, gaap, page_count, table_count, row_count, pdf_url, page_offset")
        has_counts = any(d.get("table_count") for d in docs)
    except Exception:
        docs = _paginated_select("documents",
            "id, slug, entity_name, gaap, page_count, pdf_url, page_offset")
        has_counts = False

    table_counts = {} if has_counts else _get_table_counts()

    # Tags (small, <5K)
    tags = _paginated_select("row_tags",
        "concept_id, row_id, table_rows!inner(table_id, tables!inner(document_id))")
    concept_counts = defaultdict(set)
    for t in tags:
        doc_id = t["table_rows"]["tables"]["document_id"]
        concept_counts[doc_id].add(t["concept_id"])

    result = []
    for doc in docs:
        tc = doc.get("table_count") or table_counts.get(doc["id"], 0)
        result.append({
            "id": doc["slug"],
            "name": doc["entity_name"] or doc["slug"].replace("_", " ").title(),
            "gaap": doc.get("gaap"),
            "page_count": doc.get("page_count"),
            "pdf": doc["pdf_url"],
            "has_pdf": bool(doc["pdf_url"]),
            "table_count": tc,
            "tables": tc,
            "tagged_concepts": len(concept_counts.get(doc["id"], set())),
            "page_offset": doc.get("page_offset", 0) or 0,
        })

    _doc_list_cache["data"] = result
    _doc_list_cache["ts"] = now
    return result


# ── Document stats ──────────────────────────────────────────

_doc_stats_cache = {"data": None, "ts": 0}


def query_documents_stats() -> list[dict]:
    """Per-document stats: table count, total rows, tagged rows, conflict rows.

    Uses paginated fetches for documents and tables.  Row/tag counts come from
    the tables query (avoiding a 1M+ row fetch of table_rows).
    """
    import time

    now = time.time()
    if _doc_stats_cache["data"] is not None and now - _doc_stats_cache["ts"] < 30:
        return _doc_stats_cache["data"]

    # Documents (paginated) — includes denormalized counts when available
    try:
        docs = _paginated_select("documents",
            "id, slug, entity_name, gaap, page_count, table_count, row_count, pdf_url")
        has_counts = any(d.get("table_count") for d in docs)
    except Exception:
        docs = _paginated_select("documents",
            "id, slug, entity_name, gaap, page_count, pdf_url")
        has_counts = False

    table_counts = {} if has_counts else _get_table_counts()

    # Tags (small, paginated for safety)
    tags = _paginated_select("row_tags",
        "concept_id, row_id, table_rows!inner(table_id, tables!inner(document_id))")
    tagged_rows_by_doc = defaultdict(set)
    for tag in tags:
        doc_id = tag["table_rows"]["tables"]["document_id"]
        tagged_rows_by_doc[doc_id].add(tag["row_id"])

    result = []
    for doc in docs:
        did = doc["id"]
        result.append({
            "doc_id": doc["slug"],
            "slug": doc["slug"],
            "entity_name": doc["entity_name"],
            "gaap": doc["gaap"],
            "page_count": doc.get("page_count") or 0,
            "table_count": doc.get("table_count") or table_counts.get(did, 0),
            "total_rows": doc.get("row_count") or 0,
            "tagged_rows": len(tagged_rows_by_doc.get(did, set())),
            "conflict_rows": 0,
            "has_pdf": bool(doc.get("pdf_url")),
        })

    _doc_stats_cache["data"] = result
    _doc_stats_cache["ts"] = now
    return result


# ── Concept examples (for ontology detail) ──────────────────


def query_concept_examples(concept_id: str, limit: int = 20) -> list[dict]:
    """Return tagged row examples for a concept across documents."""
    sb = get_supabase()
    resp = (
        sb.table("row_tags")
        .select(
            "tag_source, confidence, "
            "table_rows!inner(label, tables!inner(page_no, "
            "documents!inner(slug, entity_name)))"
        )
        .eq("concept_id", concept_id)
        .limit(limit)
        .execute()
    )
    examples = []
    for tag in resp.data or []:
        tr = tag["table_rows"]
        t = tr["tables"]
        d = t["documents"]
        examples.append({
            "doc_id": d["slug"],
            "doc_name": d.get("entity_name") or d["slug"],
            "page_no": t["page_no"],
            "row_label": tr.get("label", ""),
            "tag_source": tag.get("tag_source", ""),
            "confidence": tag.get("confidence"),
        })
    return examples


# ── Concept pages ────────────────────────────────────────────


def query_concept_pages(concept_id: str) -> list[dict]:
    """Replace _concept_pages index lookup."""
    sb = get_supabase()

    # Join row_tags → table_rows → tables → documents
    resp = sb.table("row_tags").select(
        "concept_id, "
        "table_rows!inner(label, tables!inner(document_id, table_id, page_no, statement_component, "
        "documents!inner(slug, page_offset)))"
    ).eq("concept_id", concept_id).execute()

    pages = []
    for tag in resp.data:
        tr = tag["table_rows"]
        t = tr["tables"]
        d = t["documents"]
        offset = d.get("page_offset", 0) or 0
        source_page = t["page_no"]
        pdf_page = max(1, source_page - offset) if source_page else 1

        pages.append({
            "doc_id": d["slug"],
            "page": pdf_page,
            "source_page": source_page,
            "label": tr.get("label", ""),
            "table_id": t["table_id"],
            "context": t.get("statement_component", ""),
        })

    return pages


# ── Element Browser ──────────────────────────────────────────


_elements_browse_cache = {"data": None, "ts": 0}


def query_elements_browse(doc_id: str | None = None) -> list[dict]:
    """Replace the massive elements_browse() file scan. Cached for 5 minutes."""
    now = time.time()
    if (_elements_browse_cache["data"] is not None
            and now - _elements_browse_cache["ts"] < 300):
        return _elements_browse_cache["data"]

    sb = get_supabase()

    # 1. All documents (paginated)
    docs = _paginated_select("documents",
        "id, slug, gaap, page_count, page_dims, pdf_url")
    doc_map = {d["id"]: d for d in docs}

    # 2. All TOC sections (paginated)
    toc_rows = _paginated_select("toc_sections",
        "document_id, statement_type, start_page, end_page, source")
    toc_by_doc = defaultdict(list)
    for t in toc_rows:
        toc_by_doc[t["document_id"]].append(t)

    # 3. All tables (paginated — 97K+ rows)
    table_rows = _paginated_select("tables",
        "document_id, table_id, page_no, statement_component")
    tables_by_doc = defaultdict(list)
    for t in table_rows:
        tables_by_doc[t["document_id"]].append(t)

    # 4. Page reviews (paginated)
    review_rows = _paginated_select("page_reviews",
        "document_id, element_type, page_no, reviewed_at")
    reviews_by_doc = defaultdict(lambda: defaultdict(dict))
    for r in review_rows:
        doc_uuid = r["document_id"]
        slug = doc_map.get(doc_uuid, {}).get("slug", "")
        et = r["element_type"]
        if r["page_no"] is None:
            reviews_by_doc[slug][et] = {"all": True, "updated_at": r["reviewed_at"]}
        else:
            entry = reviews_by_doc[slug].setdefault(et, {"seen_pages": [], "updated_at": None})
            if isinstance(entry, dict) and "seen_pages" in entry:
                entry["seen_pages"].append(r["page_no"])
                entry["updated_at"] = r["reviewed_at"]

    results = []
    for doc in docs:
        doc_uuid = doc["id"]
        slug = doc["slug"]
        page_count = doc.get("page_count") or 0

        # Page dimensions
        page_dims = doc.get("page_dims") or {}

        # Build elements mapping
        elements = defaultdict(lambda: {"pages": set(), "tables": []})

        # Source 1: ground truth TOC sections (preferred)
        toc_sections = toc_by_doc.get(doc_uuid, [])
        source = "table_classification"
        if toc_sections:
            source = "ground_truth"
            for sec in toc_sections:
                stype = sec.get("statement_type", "OTHER")
                sp = sec.get("start_page")
                ep = sec.get("end_page")
                if sp and ep:
                    for p in range(sp, ep + 1):
                        elements[stype]["pages"].add(p)

        # Source 2: table classification (supplements TOC)
        for t in tables_by_doc.get(doc_uuid, []):
            sc = t.get("statement_component")
            pno = t.get("page_no")
            table_entry = {
                "tableId": t["table_id"],
                "pageNo": pno,
                "statementComponent": sc,
            }
            if sc and pno:
                elements[sc]["tables"].append(table_entry)
                elements[sc]["pages"].add(pno)
            elif pno:
                elements["UNCLASSIFIED"]["tables"].append(table_entry)
                elements["UNCLASSIFIED"]["pages"].add(pno)

        # Convert sets to sorted lists
        elements_out = {}
        for etype, data in elements.items():
            elements_out[etype] = {
                "pages": sorted(data["pages"]),
                "tables": data["tables"],
            }

        entry = {
            "doc_id": slug,
            "gaap": doc.get("gaap", "IFRS"),
            "page_count": page_count,
            "has_pdf": bool(doc.get("pdf_url")),
            "source": source,
            "page_dims": page_dims,
            "elements": elements_out,
        }

        # Reviews
        entry["reviews"] = dict(reviews_by_doc.get(slug, {}))

        results.append(entry)

    _elements_browse_cache["data"] = results
    _elements_browse_cache["ts"] = time.time()
    return results


def query_doc_overlay_tables(doc_id: str) -> list[dict]:
    """Replace elements_browse_tables() — table overlay data with row/col bboxes."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return []

    # Get tables
    tables = sb.table("tables").select(
        "id, table_id, page_no, bbox, statement_component, column_meta"
    ).eq("document_id", doc_uuid).execute().data

    if not tables:
        return []

    table_uuid_map = {t["id"]: t for t in tables}
    table_uuids = [t["id"] for t in tables]

    # Get rows with bboxes (batch by table)
    rows = sb.table("table_rows").select(
        "id, table_id, label, row_type, bbox, row_idx"
    ).in_("table_id", table_uuids).order("row_idx").execute().data

    rows_by_table = defaultdict(list)
    row_ids = []
    for r in rows:
        rows_by_table[r["table_id"]].append(r)
        row_ids.append(r["id"])

    # Get tags for these rows
    tags_by_row = {}
    if row_ids:
        # Batch in chunks to avoid URL length limits
        for i in range(0, len(row_ids), 200):
            chunk = row_ids[i:i + 200]
            tag_rows = sb.table("row_tags").select(
                "row_id, concept_id, tag_source, confidence"
            ).in_("row_id", chunk).execute().data
            for t in tag_rows:
                tags_by_row[t["row_id"]] = t

    result = []
    for t in tables:
        entry = {
            "tableId": t["table_id"],
            "pageNo": t["page_no"],
            "bbox": t.get("bbox") or [0, 0, 0, 0],
            "statementComponent": t.get("statement_component"),
        }

        # Row bboxes
        row_bboxes = []
        for r in rows_by_table.get(t["id"], []):
            rb = r.get("bbox") or [0, 0, 0, 0]
            if any(v != 0 for v in rb):
                pre_tagged = None
                tag = tags_by_row.get(r["id"])
                if tag:
                    pre_tagged = {
                        "conceptId": tag["concept_id"],
                        "method": tag.get("tag_source"),
                        "confidence": tag.get("confidence"),
                    }
                row_bboxes.append({
                    "bbox": rb,
                    "label": (r.get("label") or "")[:60],
                    "preTagged": pre_tagged,
                    "rowType": r.get("row_type"),
                })
        if row_bboxes:
            entry["rows"] = row_bboxes

        # Column bboxes from column_meta JSONB
        col_meta = t.get("column_meta")
        if col_meta:
            import json
            if isinstance(col_meta, str):
                col_meta = json.loads(col_meta)
            col_bboxes = []
            for c in col_meta:
                cb = c.get("bbox", [0, 0, 0, 0])
                if any(v != 0 for v in cb):
                    col_bboxes.append({
                        "bbox": cb,
                        "role": c.get("role"),
                        "headerLabel": c.get("headerLabel", ""),
                    })
            if col_bboxes:
                entry["columns"] = col_bboxes

        result.append(entry)

    return result


# ── Full table data ──────────────────────────────────────────


def query_doc_tables(doc_id: str) -> list[dict]:
    """Replace doc_tables() — full table data with rows, cells, tags."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return []

    # Get tables
    tables = sb.table("tables").select(
        "id, table_id, page_no, statement_component, detected_currency, detected_unit"
    ).eq("document_id", doc_uuid).order("page_no").execute().data

    if not tables:
        return []

    table_uuids = [t["id"] for t in tables]

    # Get all rows for these tables
    rows = sb.table("table_rows").select(
        "id, table_id, row_idx, label, row_type, indent_level"
    ).in_("table_id", table_uuids).order("row_idx").execute().data

    rows_by_table = defaultdict(list)
    row_ids = []
    for r in rows:
        rows_by_table[r["table_id"]].append(r)
        row_ids.append(r["id"])

    # Get all cells
    cells_by_row = defaultdict(list)
    for i in range(0, len(row_ids), 200):
        chunk = row_ids[i:i + 200]
        cells = sb.table("cells").select(
            "row_id, col_idx, raw_text, parsed_value, is_negative"
        ).in_("row_id", chunk).order("col_idx").execute().data
        for c in cells:
            cells_by_row[c["row_id"]].append(c)

    # Get tags
    tags_by_row = {}
    for i in range(0, len(row_ids), 200):
        chunk = row_ids[i:i + 200]
        tag_rows = sb.table("row_tags").select(
            "row_id, concept_id"
        ).in_("row_id", chunk).execute().data
        for t in tag_rows:
            tags_by_row[t["row_id"]] = t["concept_id"]

    result = []
    for t in tables:
        table_rows = []
        for r in rows_by_table.get(t["id"], []):
            row_cells = []
            for c in cells_by_row.get(r["id"], []):
                row_cells.append({
                    "col": c.get("col_idx", 0),
                    "text": c.get("raw_text", ""),
                    "value": c.get("parsed_value"),
                    "negative": c.get("is_negative", False),
                })
            table_rows.append({
                "label": r.get("label", ""),
                "row_type": r.get("row_type", "DATA"),
                "indent": r.get("indent_level", 0),
                "tag": tags_by_row.get(r["id"], ""),
                "cells": row_cells,
            })
        result.append({
            "table_id": t["table_id"],
            "context": t.get("statement_component", ""),
            "source_page": t["page_no"],
            "currency": t.get("detected_currency", ""),
            "unit": t.get("detected_unit", ""),
            "rows": table_rows,
        })

    return result


# ── Rank tags ────────────────────────────────────────────────


def query_rank_tags() -> dict:
    """Replace elements_rank_tags() — MLP predictions from documents.rank_tags."""
    sb = get_supabase()
    docs = sb.table("documents").select("slug, rank_tags").not_.is_("rank_tags", "null").execute().data
    return {d["slug"]: d["rank_tags"] for d in docs}


# ── Reviews ──────────────────────────────────────────────────


def query_reviews() -> dict:
    """Replace .reviews.json read — returns {doc_id: {element_type: review_state}}."""
    sb = get_supabase()
    reviews = sb.table("page_reviews").select(
        "document_id, element_type, page_no, reviewed_at, documents!inner(slug)"
    ).execute().data

    result = defaultdict(lambda: defaultdict(dict))
    for r in reviews:
        slug = r["documents"]["slug"]
        et = r["element_type"]
        if r["page_no"] is None:
            result[slug][et] = {"all": True, "updated_at": r["reviewed_at"]}
        else:
            entry = result[slug].setdefault(et, {"seen_pages": [], "updated_at": None})
            if isinstance(entry, dict) and "seen_pages" in entry:
                entry["seen_pages"].append(r["page_no"])
                entry["updated_at"] = r["reviewed_at"]

    return dict(result)


def set_review(doc_id: str, element_type: str, pages: list[int] | None = None, user_id: str | None = None):
    """Replace .reviews.json write — mark pages or full doc as reviewed."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return

    if pages:
        # Mark specific pages
        for page_no in pages:
            sb.table("page_reviews").upsert({
                "user_id": user_id,
                "document_id": doc_uuid,
                "element_type": element_type,
                "page_no": page_no,
            }, on_conflict="user_id,document_id,element_type,page_no").execute()
    else:
        # Mark entire doc
        sb.table("page_reviews").upsert({
            "user_id": user_id,
            "document_id": doc_uuid,
            "element_type": element_type,
            "page_no": None,
        }, on_conflict="user_id,document_id,element_type,page_no").execute()


def unset_review(doc_id: str, element_type: str, user_id: str | None = None):
    """Delete review entries for a doc/element_type."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return

    q = sb.table("page_reviews").delete().eq(
        "document_id", doc_uuid
    ).eq("element_type", element_type)
    if user_id:
        q = q.eq("user_id", user_id)
    q.execute()


# ── Review status (HITL dashboard) ───────────────────────────


def query_review_status() -> list[dict]:
    """Replace review_status() — dashboard of all fixtures."""
    sb = get_supabase()

    docs = sb.table("documents").select(
        "id, slug, gaap, entity_name, industry, currency, page_count, pdf_url"
    ).execute().data

    # Tables grouped by doc
    tables = sb.table("tables").select(
        "document_id, table_id, page_no, statement_component, classification_method"
    ).execute().data
    tables_by_doc = defaultdict(list)
    for t in tables:
        tables_by_doc[t["document_id"]].append(t)

    # TOC sections by doc
    toc_rows = sb.table("toc_sections").select(
        "document_id, id"
    ).execute().data
    toc_by_doc = defaultdict(int)
    for t in toc_rows:
        toc_by_doc[t["document_id"]] += 1

    # Human review overrides
    overrides = sb.table("classification_overrides").select(
        "table_id, statement_component"
    ).execute().data
    override_set = {o["table_id"] for o in overrides}

    fixtures = []
    for doc in docs:
        doc_uuid = doc["id"]
        doc_tables = tables_by_doc.get(doc_uuid, [])

        pages = set()
        primary_types = defaultdict(int)
        methods = defaultdict(int)
        disc_count = 0
        unclassified = 0
        note_ref_tables = 0

        for t in doc_tables:
            pno = t.get("page_no")
            if pno:
                pages.add(pno)
            sc = t.get("statement_component", "")
            method = t.get("classification_method", "unclassified")
            methods[method] += 1

            if sc in ("PNL", "SFP", "OCI", "CFS", "SOCIE"):
                primary_types[sc] += 1
            elif sc and sc.startswith("DISC."):
                disc_count += 1
            elif not sc:
                unclassified += 1

        has_toc = any(m == "toc" for m in methods)
        page_list = sorted(pages)
        page_range = f"{page_list[0]}-{page_list[-1]}" if page_list else ""

        fixtures.append({
            "id": doc["slug"],
            "has_pdf": bool(doc.get("pdf_url")),
            "has_manifest": False,
            "has_human_review": any(
                t["id"] in override_set
                for t in doc_tables
                if isinstance(t.get("id"), str)
            ),
            "total_tables": len(doc_tables),
            "pages": len(pages),
            "page_range": page_range,
            "has_toc": has_toc,
            "toc_tables": toc_by_doc.get(doc_uuid, 0),
            "primary_types": dict(primary_types),
            "disc_types": disc_count,
            "unclassified": unclassified,
            "methods": dict(methods),
            "note_ref_tables": note_ref_tables,
            "total_note_refs": 0,
            "gaap": doc.get("gaap", "IFRS"),
            "entity": doc.get("entity_name", ""),
            "industry": doc.get("industry", "general"),
            "currency": doc.get("currency", "EUR"),
        })

    return fixtures


# ── Review tables (lightweight) ──────────────────────────────


def query_review_tables(doc_id: str) -> list[dict]:
    """Replace review_tables() — lightweight table listing."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return []

    tables = sb.table("tables").select(
        "id, table_id, page_no, statement_component, classification_method, section_path"
    ).eq("document_id", doc_uuid).order("page_no").execute().data

    if not tables:
        return []

    table_uuids = [t["id"] for t in tables]

    # Get first 3 row labels per table
    rows = sb.table("table_rows").select(
        "table_id, label, row_type"
    ).in_("table_id", table_uuids).order("row_idx").execute().data

    rows_by_table = defaultdict(list)
    for r in rows:
        rows_by_table[r["table_id"]].append(r)

    result = []
    for t in tables:
        table_rows = rows_by_table.get(t["id"], [])
        first_labels = [r["label"] for r in table_rows[:3] if r.get("label")]
        col_headers = [
            r["label"] for r in table_rows
            if r.get("row_type") == "HEADER" and r.get("label")
        ][:6]

        section_path = t.get("section_path")
        if isinstance(section_path, str):
            section_path = section_path.split(" > ") if section_path else []

        result.append({
            "tableId": t["table_id"],
            "pageNo": t["page_no"],
            "statementComponent": t.get("statement_component"),
            "classification_method": t.get("classification_method", "unclassified"),
            "classification_confidence": "medium",
            "first_labels": first_labels,
            "col_headers": col_headers,
            "row_count": len(table_rows),
            "sectionPath": section_path or [],
        })

    return result


# ── Human review (classification overrides) ──────────────────


def query_human_review(doc_id: str) -> dict:
    """Read classification_overrides for a document."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return {"exists": False}

    # Get tables for this doc to map table UUIDs to table_ids
    tables = sb.table("tables").select("id, table_id").eq("document_id", doc_uuid).execute().data
    table_map = {t["id"]: t["table_id"] for t in tables}

    overrides = sb.table("classification_overrides").select(
        "table_id, statement_component, comment, created_at"
    ).in_("table_id", list(table_map.keys())).execute().data

    if not overrides:
        return {"exists": False}

    override_dict = {}
    for o in overrides:
        tid = table_map.get(o["table_id"], o["table_id"])
        override_dict[tid] = {
            "statementComponent": o["statement_component"],
            "comment": o.get("comment"),
        }

    return {
        "exists": True,
        "version": 1,
        "overrides": {"tables": override_dict},
        "confirmed_tables": [],
    }


def save_human_review(doc_id: str, review_data: dict, user_id: str | None = None):
    """Save classification overrides from review UI."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return

    # Get table UUID mapping
    tables = sb.table("tables").select("id, table_id").eq("document_id", doc_uuid).execute().data
    id_map = {t["table_id"]: t["id"] for t in tables}

    # Extract overrides
    overrides = review_data.get("overrides", {}).get("tables", {})
    for table_id_str, override in overrides.items():
        table_uuid = id_map.get(table_id_str)
        if not table_uuid:
            continue
        sb.table("classification_overrides").upsert({
            "table_id": table_uuid,
            "user_id": user_id,
            "statement_component": override.get("statementComponent", ""),
            "comment": override.get("comment"),
        }).execute()


# ── TOC Annotation ───────────────────────────────────────────


def query_annotate_documents_search(
    q: str = "", limit: int = 20, slugs: list[str] | None = None,
) -> list[dict]:
    """Search documents for annotation dropdown with server-side filtering.

    slugs: optional whitelist — when provided, only return docs whose slug is in the list.
    """
    sb = get_supabase()

    try:
        query = sb.table("documents").select("id, slug, gaap, page_count, table_count, pdf_url")
        if slugs:
            # Batch .in_() for large slug lists (PostgREST limit ~100 per call)
            all_docs = []
            for i in range(0, len(slugs), 80):
                batch = slugs[i:i + 80]
                bq = sb.table("documents").select("id, slug, gaap, page_count, table_count, pdf_url")
                bq = bq.in_("slug", batch)
                if q:
                    bq = bq.ilike("slug", f"*{q}*")
                all_docs.extend(bq.order("slug").execute().data)
            docs = all_docs[:limit]
        else:
            if q:
                query = query.ilike("slug", f"*{q}*")
            docs = query.order("slug").limit(limit).execute().data
    except Exception:
        query = sb.table("documents").select("id, slug, gaap, page_count, pdf_url")
        if q:
            query = query.ilike("slug", f"*{q}*")
        docs = query.order("slug").limit(limit).execute().data

    if not docs:
        return []

    # Fetch toc_sections only for matched documents
    doc_ids = [d["id"] for d in docs]
    toc_by_doc = defaultdict(list)
    # Batch in small groups to stay within PostgREST 1000-row default limit
    # (~20 docs × ~30 sections = ~600 rows, safely under limit)
    for i in range(0, len(doc_ids), 20):
        batch_ids = doc_ids[i:i + 20]
        toc_rows = (sb.table("toc_sections")
                    .select("document_id, validated, validated_at")
                    .in_("document_id", batch_ids)
                    .limit(1000)
                    .execute().data)
        for t in toc_rows:
            toc_by_doc[t["document_id"]].append(t)

    result = []
    for doc in docs:
        doc_uuid = doc["id"]
        sections = toc_by_doc.get(doc_uuid, [])
        section_count = len(sections)

        if section_count == 0:
            status = "not_started"
            has_toc = None
        elif any(s.get("validated") for s in sections):
            status = "complete"
            has_toc = True
        else:
            status = "in_progress"
            has_toc = True

        # Use max validated_at as completed_at
        validated_times = [s["validated_at"] for s in sections if s.get("validated_at")]
        completed_at = max(validated_times) if validated_times else None

        entry = {
            "doc_id": doc["slug"],
            "gaap": doc.get("gaap", "IFRS"),
            "has_fixture": True,
            "table_count": doc.get("table_count", 0),
            "has_pdf": bool(doc.get("pdf_url")),
            "page_count": doc.get("page_count", 0),
            "annotation_status": status,
            "has_toc": has_toc,
        }
        if section_count > 0:
            entry["section_count"] = section_count
        if completed_at:
            entry["completed_at"] = completed_at

        result.append(entry)

    return result


def query_toc_sections(doc_id: str) -> dict:
    """Read toc_sections for a document."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return {}

    # Get page count and dimensions
    doc = sb.table("documents").select("page_count, page_dims").eq("id", doc_uuid).single().execute()
    page_count = doc.data.get("page_count", 0) if doc.data else 0
    page_dims = doc.data.get("page_dims") or {} if doc.data else {}

    sections = sb.table("toc_sections").select(
        "label, statement_type, start_page, end_page, note_number, validated, sort_order"
    ).eq("document_id", doc_uuid).order("sort_order").execute().data

    if not sections:
        return {
            "doc_id": doc_id,
            "page_count": page_count,
            "page_dims": page_dims,
            "ground_truth": {
                "version": 1,
                "annotator": "",
                "toc_table_id": None,
                "toc_pages": [],
                "sections": [],
                "notes_start_page": None,
                "notes_end_page": None,
            },
        }

    gt_sections = []
    for s in sections:
        gt_sections.append({
            "label": s.get("label", ""),
            "statement_type": s.get("statement_type", ""),
            "start_page": s.get("start_page"),
            "end_page": s.get("end_page"),
            "note_number": s.get("note_number"),
            "validated": s.get("validated", False),
        })

    return {
        "doc_id": doc_id,
        "page_count": page_count,
        "page_dims": page_dims,
        "ground_truth": {
            "version": 1,
            "annotator": "",
            "toc_table_id": None,
            "toc_pages": [],
            "sections": gt_sections,
            "notes_start_page": None,
            "notes_end_page": None,
        },
    }


def get_document_page_count(doc_id: str) -> int | None:
    """Get page_count for a document by slug."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return None
    resp = sb.table("documents").select("page_count").eq("id", doc_uuid).single().execute()
    return resp.data.get("page_count") if resp.data else None


def save_toc_sections(doc_id: str, ground_truth: dict):
    """Save TOC sections from annotation UI."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return

    # Delete existing sections first, then insert new ones
    sb.table("toc_sections").delete().eq("document_id", doc_uuid).execute()

    # Insert new sections
    sections = ground_truth.get("sections", [])
    if sections:
        inserts = []
        for i, s in enumerate(sections):
            inserts.append({
                "document_id": doc_uuid,
                "label": s.get("label", ""),
                "statement_type": s.get("statement_type", ""),
                "start_page": s.get("start_page", 0),
                "end_page": s.get("end_page"),
                "note_number": s.get("note_number"),
                "sort_order": i,
                "source": "human" if s.get("validated") else "auto",
                "validated": s.get("validated", False),
            })
        sb.table("toc_sections").upsert(
            inserts, on_conflict="document_id,label,start_page"
        ).execute()


# ── Voting ──────────────────────────────────────────────────


def cast_tag_vote(vote: dict) -> dict:
    """Insert a vote into tag_votes. Consensus is auto-computed via trigger."""
    sb = get_supabase()
    resp = sb.table("tag_votes").insert(vote).execute()
    return resp.data[0] if resp.data else {}


def get_votes(dimension: str, target_id: str) -> dict:
    """Get all votes + consensus for a (dimension, target)."""
    sb = get_supabase()
    votes = (
        sb.table("tag_votes")
        .select("*")
        .eq("dimension", dimension)
        .eq("target_id", target_id)
        .order("created_at", desc=True)
        .execute()
        .data or []
    )
    consensus_resp = (
        sb.table("tag_consensus")
        .select("*")
        .eq("dimension", dimension)
        .eq("target_id", target_id)
        .maybe_single()
        .execute()
    )
    return {"votes": votes, "consensus": consensus_resp.data}


def get_vote_conflicts(doc_id: str) -> list[dict]:
    """Get targets with dissent or multiple values for a document's rows."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return []

    # Get all row UUIDs for this document
    tables = sb.table("tables").select("id").eq("document_id", doc_uuid).execute().data or []
    if not tables:
        return []

    table_ids = [t["id"] for t in tables]
    rows = sb.table("table_rows").select("id").in_("table_id", table_ids).execute().data or []
    row_ids = [r["id"] for r in rows]

    if not row_ids:
        return []

    # Find consensus entries with dissent
    conflicts = (
        sb.table("tag_consensus")
        .select("*")
        .eq("dimension", "row_concept")
        .in_("target_id", row_ids)
        .gt("dissent_count", 0)
        .execute()
        .data or []
    )
    return conflicts


# ── Ground Truth Sets ───────────────────────────────────────


def query_gt_sets() -> list[dict]:
    """List all GT sets with document counts and doc_ids (slugs)."""
    sb = get_supabase()
    sets = sb.table("gt_sets").select("*").order("created_at", desc=True).execute().data or []
    # Fetch all set-doc mappings with document slug via join
    set_docs = _paginated_select(
        "gt_set_documents", "set_id, document_id, documents!inner(slug)")
    docs_by_set = defaultdict(list)
    for sd in set_docs:
        slug = sd.get("documents", {}).get("slug") if isinstance(sd.get("documents"), dict) else None
        if slug:
            docs_by_set[sd["set_id"]].append(slug)

    for s in sets:
        s["doc_ids"] = docs_by_set.get(s["id"], [])
        s["doc_count"] = len(s["doc_ids"])
    return sets


def create_gt_set(name: str, description: str, user_id: str = None) -> dict:
    sb = get_supabase()
    entry = {"name": name, "description": description}
    if user_id:
        entry["created_by"] = user_id
    resp = sb.table("gt_sets").insert(entry).execute()
    return resp.data[0] if resp.data else {}


def query_gt_set_docs(set_id: str) -> list[dict]:
    """Documents in a GT set with per-doc stats including docling metadata and tag coverage."""
    sb = get_supabase()

    # Try extended select with docling metadata columns; fall back if migration not yet applied
    _EXTENDED_SELECT = (
        "document_id, added_at, "
        "documents!inner(slug, entity_name, gaap, page_count, pdf_url, docling_url, "
        "docling_text_count, docling_table_count, docling_page_count, docling_size_kb, "
        "tg_page_count)"
    )
    _BASIC_SELECT = (
        "document_id, added_at, "
        "documents!inner(slug, entity_name, gaap, page_count, pdf_url, docling_url)"
    )
    try:
        rows = (
            sb.table("gt_set_documents")
            .select(_EXTENDED_SELECT)
            .eq("set_id", set_id)
            .execute()
            .data or []
        )
    except Exception:
        rows = (
            sb.table("gt_set_documents")
            .select(_BASIC_SELECT)
            .eq("set_id", set_id)
            .execute()
            .data or []
        )

    # Collect document UUIDs for tag coverage query
    doc_ids = [r["document_id"] for r in rows]

    # Batch-fetch toc_sections for tag coverage
    tag_coverage_map = {}
    page_count_map = {}
    if doc_ids:
        # Build page count map
        for r in rows:
            d = r["documents"]
            pc = d.get("page_count")
            if pc:
                page_count_map[r["document_id"]] = pc

        # Fetch toc_sections for all docs in the set
        sections = _paginated_select(
            "toc_sections",
            "document_id, start_page, end_page"
        )
        # Group by document_id
        sections_by_doc = defaultdict(list)
        for s in sections:
            if s["document_id"] in set(doc_ids):
                sections_by_doc[s["document_id"]].append(s)

        for doc_id, secs in sections_by_doc.items():
            pc = page_count_map.get(doc_id)
            if not pc:
                continue
            tagged = set()
            for sec in secs:
                sp = sec.get("start_page")
                ep = sec.get("end_page")
                if sp and ep:
                    tagged.update(range(sp, ep + 1))
            if tagged:
                tag_coverage_map[doc_id] = min(100, round(100 * len(tagged) / pc))

    result = []
    for r in rows:
        d = r["documents"]
        dl_pages = d.get("docling_page_count")
        tg_pages = d.get("tg_page_count")

        # Compute match status
        if dl_pages is None:
            match = "missing" if not d.get("docling_url") else None
        elif tg_pages is not None:
            match = "ok" if dl_pages >= tg_pages else "partial"
        else:
            match = "ok"

        result.append({
            "document_id": r["document_id"],
            "slug": d["slug"],
            "entity_name": d.get("entity_name"),
            "gaap": d["gaap"],
            "page_count": d.get("page_count"),
            "has_pdf": bool(d.get("pdf_url")),
            "added_at": r["added_at"],
            "docling_url": d.get("docling_url"),
            "docling_size": d.get("docling_size_kb"),
            "docling_texts": d.get("docling_text_count"),
            "docling_tables": d.get("docling_table_count"),
            "docling_pages": dl_pages,
            "tg_pages": tg_pages,
            "docling_match": match,
            "tag_coverage": tag_coverage_map.get(r["document_id"]),
        })
    return result


def add_gt_set_docs(set_id: str, doc_ids: list[str], user_id: str = None) -> int:
    """Add documents to a GT set by document UUID. Returns count added."""
    sb = get_supabase()
    entries = [{"set_id": set_id, "document_id": did, "added_by": user_id} for did in doc_ids]
    resp = sb.table("gt_set_documents").upsert(entries, on_conflict="set_id,document_id").execute()
    return len(resp.data) if resp.data else 0


def remove_gt_set_doc(set_id: str, document_id: str) -> bool:
    sb = get_supabase()
    sb.table("gt_set_documents").delete().eq("set_id", set_id).eq("document_id", document_id).execute()
    return True


# ── Document Edges ──────────────────────────────────────────


def query_doc_edges(doc_id: str) -> list[dict]:
    """Get all internal edges for a document with source/target labels."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return []

    edges = (
        sb.table("internal_edges")
        .select("*")
        .eq("document_id", doc_uuid)
        .order("edge_type")
        .execute()
        .data or []
    )
    return edges


def create_doc_edge(doc_id: str, edge: dict) -> dict:
    """Create a new internal edge."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return {}

    entry = {
        "document_id": doc_uuid,
        "source_type": edge["source_type"],
        "source_id": edge["source_id"],
        "target_type": edge["target_type"],
        "target_id": edge["target_id"],
        "edge_type": edge["edge_type"],
        "note_number": edge.get("note_number"),
        "confidence": edge.get("confidence", 1.0),
    }
    resp = sb.table("internal_edges").insert(entry).execute()
    return resp.data[0] if resp.data else {}


def update_doc_edge(edge_id: str, updates: dict) -> dict:
    """Update an internal edge (validate, change type, etc.)."""
    sb = get_supabase()
    resp = sb.table("internal_edges").update(updates).eq("id", edge_id).execute()
    return resp.data[0] if resp.data else {}


def delete_doc_edge(edge_id: str) -> bool:
    sb = get_supabase()
    sb.table("internal_edges").delete().eq("id", edge_id).execute()
    return True


# ── Annotate tables (lightweight) ────────────────────────────


def query_annotate_tables(doc_id: str) -> list[dict]:
    """Lightweight table listing for annotation UI."""
    sb = get_supabase()
    doc_uuid = resolve_doc_uuid(doc_id)
    if not doc_uuid:
        return []

    tables = sb.table("tables").select(
        "id, table_id, page_no, statement_component"
    ).eq("document_id", doc_uuid).order("page_no").execute().data

    if not tables:
        return []

    table_uuids = [t["id"] for t in tables]

    # Get first 3 labels per table
    rows = sb.table("table_rows").select(
        "table_id, label"
    ).in_("table_id", table_uuids).order("row_idx").execute().data

    rows_by_table = defaultdict(list)
    for r in rows:
        rows_by_table[r["table_id"]].append(r)

    result = []
    for t in tables:
        table_rows = rows_by_table.get(t["id"], [])
        first_labels = [r["label"] for r in table_rows[:3] if r.get("label")]
        result.append({
            "tableId": t["table_id"],
            "pageNo": t["page_no"],
            "row_count": len(table_rows),
            "first_labels": first_labels,
            "statementComponent": t.get("statement_component"),
        })

    return result


# ── Docling elements ─────────────────────────────────────────


def query_docling_available(doc_id: str) -> bool:
    """Check if docling JSON is available for a document."""
    sb = get_supabase()
    resp = sb.table("documents").select("docling_url").eq("slug", doc_id).single().execute()
    if resp.data:
        return bool(resp.data.get("docling_url"))
    return False


def query_doc_info(doc_id: str) -> dict | None:
    """Get document info for PDF/docling URL lookups."""
    sb = get_supabase()
    resp = sb.table("documents").select(
        "id, slug, pdf_url, docling_url, page_offset, page_count"
    ).eq("slug", doc_id).single().execute()
    return resp.data


# ── Tag action log ───────────────────────────────────────────

def append_tag_log(entry: dict):
    """Insert a tagging action into the tag_actions table."""
    sb = get_supabase()
    sb.table("tag_actions").insert(entry).execute()


def get_tag_log(limit: int = 200, offset: int = 0) -> list:
    """Retrieve tag log entries, most recent first."""
    sb = get_supabase()
    resp = (
        sb.table("tag_actions")
        .select("*")
        .order("timestamp", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return resp.data or []


# ── Ontology gaps ────────────────────────────────────────────


def query_ontology_gaps(status: str | None = None, context: str | None = None) -> list:
    """List ontology gaps, optionally filtered by status and context."""
    sb = get_supabase()
    q = sb.table("ontology_gaps").select("*").order("created_at", desc=True)
    if status:
        q = q.eq("status", status)
    if context:
        q = q.eq("context", context)
    return q.execute().data or []


def create_ontology_gap(data: dict) -> dict:
    """Create a new ontology gap report."""
    sb = get_supabase()
    resp = sb.table("ontology_gaps").insert(data).execute()
    return resp.data[0] if resp.data else data


def update_ontology_gap(gap_id: str, updates: dict) -> dict:
    """Update an ontology gap (status, resolution, etc.)."""
    sb = get_supabase()
    resp = sb.table("ontology_gaps").update(updates).eq("id", gap_id).execute()
    return resp.data[0] if resp.data else updates


# ── Concept proposals ────────────────────────────────────────


def query_concept_proposals(status: str | None = None) -> list:
    """List concept proposals, optionally filtered by status."""
    sb = get_supabase()
    q = sb.table("concept_proposals").select("*").order("created_at", desc=True)
    if status:
        q = q.eq("status", status)
    return q.execute().data or []


def create_concept_proposal(data: dict) -> dict:
    """Create a new concept proposal."""
    sb = get_supabase()
    resp = sb.table("concept_proposals").insert(data).execute()
    return resp.data[0] if resp.data else data


def update_concept_proposal(proposal_id: str, updates: dict) -> dict:
    """Update a concept proposal (status, review, etc.)."""
    sb = get_supabase()
    resp = sb.table("concept_proposals").update(updates).eq("id", proposal_id).execute()
    return resp.data[0] if resp.data else updates
