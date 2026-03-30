#!/usr/bin/env python3
"""
rank_pages.py — Multi-class page classifier using MLP.

Classifies every page (not just table pages) by combining:
- Table features (row/column structure, keywords, values) when tables exist
- Text features (section headers, keyword density, Docling elements) for all pages

Trains on ground-truth TOC sections, outputs per-fixture rank_tags.json.

Usage:
    python3 eval/rank_pages.py                     # train + predict all fixtures
    python3 eval/rank_pages.py --eval              # LODOCV evaluation only
    python3 eval/rank_pages.py --fixtures f1 f2    # predict specific fixtures
"""

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reference_graph import has_note_column
from classify_tables import _STATEMENT_KEYWORDS
from section_types import RANK_CLASSES as CLASSES, TYPE_TO_RANK_CLASS as _TYPE_MAP

# ── Classes ──────────────────────────────────────────────────────────────────

CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}

# Per-class keywords (searched in lowercased page text)
_CLASS_KEYWORDS = {
    "TOC": ["inhaltsverzeichnis", "table of contents", "contents", "inhalt",
            "verzeichnis", "index"],
    "PNL": ["revenue", "umsatz", "erlöse", "gewinn", "verlust", "profit", "loss",
            "ebit", "ergebnis", "aufwend", "ertrag", "gewinn- und verlustrechnung",
            "income statement", "profit or loss",
            "konzern-gewinn", "konzernergebnis", "erfolgsrechnung"],
    "SFP": ["assets", "aktiva", "passiva", "liabilities", "equity", "eigenkapital",
            "verbindlichkeiten", "bilanz", "forderung", "rückstellung",
            "balance sheet", "financial position",
            "konzernbilanz", "konzern-bilanz", "vermögenslage", "finanzlage"],
    "OCI": ["other comprehensive", "sonstiges ergebnis", "gesamtergebnis",
            "konzern-gesamtergebnis", "gesamtergebnisrechnung"],
    "CFS": ["cash flow", "kapitalfluss", "zahlungsmittel", "finanzmittel",
            "cashflow", "geldfluss", "kapitalflussrechnung"],
    "SOCIE": ["eigenkapitalveränderung", "changes in equity", "gezeichnetes kapital",
              "retained earnings", "gewinnrücklage", "eigenkapitalspiegel",
              "eigenkapitalentwicklung", "eigenkapitalveränderungsrechnung"],
    "NOTES": ["anhang", "erläuterung", "notes to", "anlagenspiegel",
              "konzernanhang", "konzern-anhang"],
}


# ── Feature extraction ───────────────────────────────────────────────────────

FEATURE_NAMES = [
    # Position
    "page", "page_le5", "page_le15", "rel_position",
    # Table presence & structure (aggregated across tables on this page)
    "has_table", "table_count", "total_rows", "total_cols",
    "total_value_cols", "total_header_rows",
    "has_note_col", "has_currency",
    # Value distribution (from all tables on page)
    "pct_small_ints", "pct_monotonic", "max_value", "mean_value_abs",
    "std_value", "value_count", "pct_negative",
    # Table content features
    "statement_kw_count", "note_pattern_count",
    "pct_rows_with_label", "avg_label_len", "pct_dotleader",
    # Text features (from Docling elements)
    "text_element_count", "section_header_count", "list_item_count",
    "text_char_count", "avg_text_len",
    "has_page_number_list",  # lines with page numbers (TOC indicator)
    "pct_short_lines",  # short text lines (TOC-like)
    "pct_numeric_lines",  # lines that are mostly numbers
    # Per-class keyword hits (from both table labels and page text)
    "kw_toc", "kw_pnl", "kw_sfp", "kw_oci", "kw_cfs", "kw_socie", "kw_notes",
    # TOC cross-reference features (page referenced from TOC as a specific type)
    "toc_ref_pnl", "toc_ref_sfp", "toc_ref_oci", "toc_ref_cfs",
    "toc_ref_socie", "toc_ref_notes", "toc_ref_any",
]


def _table_parsed_values(table: dict) -> list[float]:
    vals = []
    for r in table.get("rows", []):
        for c in r.get("cells", []):
            pv = c.get("parsedValue")
            if pv is not None:
                vals.append(float(pv))
    return vals


def _table_has_currency(table: dict) -> bool:
    meta = table.get("metadata", {})
    if meta.get("detectedCurrency"):
        return True
    for col in table.get("columns", []):
        if col.get("detectedAxes", {}).get("AXIS.CURRENCY"):
            return True
    return False


def extract_page_features(
    page_no: int,
    total_pages: int,
    tables_on_page: list[dict],
    text_elements: list[dict],
    toc_refs: set[str] | None = None,
) -> list[float]:
    """Extract feature vector for a single page.

    toc_refs: set of statement types this page is referenced as from TOC
              (e.g. {"PNL", "NOTES"}).
    """

    # ── Position features ──
    rel_pos = page_no / max(total_pages, 1)

    # ── Table features (aggregate all tables on this page) ──
    has_table = 1.0 if tables_on_page else 0.0
    table_count = float(len(tables_on_page))

    all_rows = []
    all_cols = []
    all_vals = []
    total_header_rows = 0
    any_note_col = False
    any_currency = False

    for t in tables_on_page:
        rows = t.get("rows", [])
        columns = t.get("columns", [])
        all_rows.extend(rows)
        all_cols.extend(columns)
        all_vals.extend(_table_parsed_values(t))
        total_header_rows += t.get("headerRowCount", 0)
        if has_note_column(t):
            any_note_col = True
        if _table_has_currency(t):
            any_currency = True

    value_cols = [c for c in all_cols if c.get("role") == "VALUE"]
    small_ints = [v for v in all_vals if 1 <= v <= 500 and v == int(v)]

    # Monotonicity
    ordered_vals = []
    for r in all_rows:
        for c in r.get("cells", []):
            pv = c.get("parsedValue")
            if pv is not None:
                ordered_vals.append(float(pv))
    if len(ordered_vals) > 1:
        increasing = sum(1 for i in range(1, len(ordered_vals))
                         if ordered_vals[i] >= ordered_vals[i - 1])
        pct_mono = increasing / (len(ordered_vals) - 1)
    else:
        pct_mono = 0.0

    # Table text blob
    table_text = " ".join(r.get("label", "").lower() for r in all_rows)
    for r in all_rows:
        for c in r.get("cells", []):
            txt = (c.get("text") or "").lower()
            if txt:
                table_text += " " + txt

    kw_count = sum(1 for kw in _STATEMENT_KEYWORDS if kw in table_text)
    note_patterns = sum(
        1 for r in all_rows
        if re.match(r'^\s*\d+\s*[.)]\s+\S', r.get("label", ""))
    )

    # Value statistics
    max_val = max(all_vals) if all_vals else 0.0
    mean_val = (sum(all_vals) / len(all_vals)) if all_vals else 0.0
    std_val = 0.0
    if len(all_vals) > 1:
        std_val = (sum((v - mean_val) ** 2 for v in all_vals) / len(all_vals)) ** 0.5
    pct_negative = sum(1 for v in all_vals if v < 0) / max(len(all_vals), 1)

    labels = [r.get("label", "").strip() for r in all_rows]
    pct_with_label = sum(1 for l in labels if l) / max(len(labels), 1)
    avg_label_len = (sum(len(l) for l in labels if l) /
                     max(sum(1 for l in labels if l), 1))
    pct_dotleader = (sum(1 for l in labels if "...." in l or "…" in l) /
                     max(len(labels), 1))

    # ── Text features (from Docling elements) ──
    text_count = float(len(text_elements))
    section_headers = [e for e in text_elements if e.get("label") == "section_header"]
    list_items = [e for e in text_elements if e.get("label") == "list_item"]

    all_text_strs = [e.get("text", "") for e in text_elements]
    total_chars = sum(len(t) for t in all_text_strs)
    avg_text_len = total_chars / max(len(all_text_strs), 1)

    # TOC indicator: lines ending with page numbers (e.g., "Revenue ......... 42")
    page_num_pattern = re.compile(r'[\.\s…·]{3,}\s*\d+\s*$')
    page_num_lines = sum(1 for t in all_text_strs if page_num_pattern.search(t))
    has_page_num_list = 1.0 if page_num_lines >= 3 else 0.0

    # Short lines (< 50 chars) — TOC entries tend to be short
    short_lines = sum(1 for t in all_text_strs if 0 < len(t.strip()) < 50)
    pct_short = short_lines / max(len(all_text_strs), 1)

    # Numeric lines
    numeric_lines = sum(1 for t in all_text_strs
                        if t.strip() and
                        sum(c.isdigit() for c in t) / max(len(t), 1) > 0.3)
    pct_numeric = numeric_lines / max(len(all_text_strs), 1)

    # ── Per-class keyword hits (combined table + text) ──
    page_text = table_text + " " + " ".join(t.lower() for t in all_text_strs)
    class_kw_hits = []
    for cls_name in ["TOC", "PNL", "SFP", "OCI", "CFS", "SOCIE", "NOTES"]:
        kws = _CLASS_KEYWORDS.get(cls_name, [])
        hits = sum(1 for kw in kws if kw in page_text)
        class_kw_hits.append(float(hits))

    return [
        float(page_no),
        1.0 if page_no <= 5 else 0.0,
        1.0 if page_no <= 15 else 0.0,
        rel_pos,
        # Table features
        has_table, table_count,
        float(len(all_rows)), float(len(all_cols)),
        float(len(value_cols)), float(total_header_rows),
        1.0 if any_note_col else 0.0,
        1.0 if any_currency else 0.0,
        len(small_ints) / max(len(all_vals), 1),
        pct_mono,
        float(min(max_val, 1e8)),
        float(min(abs(mean_val), 1e8)),
        float(min(std_val, 1e8)),
        float(len(all_vals)),
        pct_negative,
        float(kw_count),
        float(note_patterns),
        pct_with_label,
        float(min(avg_label_len, 200)),
        pct_dotleader,
        # Text features
        text_count,
        float(len(section_headers)),
        float(len(list_items)),
        float(min(total_chars, 50000)),
        float(min(avg_text_len, 500)),
        has_page_num_list,
        pct_short,
        pct_numeric,
    ] + class_kw_hits + [
        # TOC cross-reference features
        1.0 if toc_refs and "PNL" in toc_refs else 0.0,
        1.0 if toc_refs and "SFP" in toc_refs else 0.0,
        1.0 if toc_refs and "OCI" in toc_refs else 0.0,
        1.0 if toc_refs and "CFS" in toc_refs else 0.0,
        1.0 if toc_refs and "SOCIE" in toc_refs else 0.0,
        1.0 if toc_refs and "NOTES" in toc_refs else 0.0,
        1.0 if toc_refs else 0.0,
    ]


# ── Docling element loading ──────────────────────────────────────────────────

# TOC keywords for identifying TOC tables
_TOC_TABLE_KW = ["inhaltsverzeichnis", "table of contents", "contents",
                 "inhalt", "verzeichnis"]


def _extract_toc_refs(tables: list[dict], total_pages: int
                      ) -> dict[int, set[str]]:
    """Parse TOC tables to find page references to statement types.

    Returns {page_no: {"PNL", "SFP", ...}} for pages referenced from TOC.
    """
    # Find candidate TOC tables: have TOC keywords or many rows ending with numbers
    candidate_tables = []
    for t in tables:
        rows = t.get("rows", [])
        header_text = " ".join(r.get("label", "").lower() for r in rows[:5])
        has_toc_kw = any(kw in header_text for kw in _TOC_TABLE_KW)

        ref_count = 0
        for r in rows:
            cells = [c.get("text", "") for c in r.get("cells", [])]
            last_cell = cells[-1].strip() if cells else ""
            if re.match(r"^\d{1,4}$", last_cell):
                ref_count += 1
        if has_toc_kw or ref_count >= 5:
            candidate_tables.append(t)

    if not candidate_tables:
        return {}

    refs: dict[int, set[str]] = {}
    for t in candidate_tables:
        for r in t.get("rows", []):
            cells = [c.get("text", "") for c in r.get("cells", [])]
            label = r.get("label", "")
            full_text = (label + " " + " ".join(cells)).lower()
            all_text = " ".join(cells)
            page_match = re.findall(r"\b(\d{1,4})\b", all_text)
            if not page_match:
                continue
            ref_page = int(page_match[-1])
            if ref_page < 1 or ref_page > total_pages:
                continue
            for stype, kws in _CLASS_KEYWORDS.items():
                if stype == "TOC":
                    continue
                if any(kw in full_text for kw in kws):
                    refs.setdefault(ref_page, set()).add(stype)

    return refs

def _load_docling_elements_by_page(fixture_dir: Path) -> dict[int, list[dict]]:
    """Load Docling elements grouped by page number.

    Returns {page_no: [{"label": ..., "text": ...}, ...]}.
    """
    de_path = fixture_dir / "docling_elements.json"
    if not de_path.exists():
        return {}

    try:
        with open(de_path) as f:
            de = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    by_page: dict[int, list[dict]] = {}

    # Docling JSON structure: texts[] with prov[].page_no
    for t in de.get("texts", []):
        prov = t.get("prov", [])
        page = prov[0].get("page_no") if prov else None
        if page is None:
            continue
        by_page.setdefault(page, []).append({
            "label": t.get("label", "text"),
            "text": t.get("text", ""),
        })

    return by_page


# ── Dataset building ─────────────────────────────────────────────────────────

def _load_gt_lenient(fixture_dir: Path) -> dict | None:
    gt_path = fixture_dir / "ground_truth" / "toc.json"
    if not gt_path.exists():
        return None
    with open(gt_path) as f:
        return json.load(f)


def find_gt_fixtures() -> list[Path]:
    base = Path(__file__).parent / "fixtures"
    return sorted(p.parent.parent for p in base.rglob("ground_truth/toc.json"))


def _page_to_class(page: int, gt: dict) -> str:
    for sec in gt.get("sections", []):
        sp = sec.get("start_page")
        ep = sec.get("end_page") or sp
        if sp is not None and sp <= page <= ep:
            raw_type = sec.get("statement_type", "OTHER")
            return _TYPE_MAP.get(raw_type, "OTHER")
    return "OTHER"


def _load_fixture_pages(fixture_dir: Path
                        ) -> tuple[dict, list[dict], dict[int, list[dict]], dict[int, set[str]]]:
    """Load table_graphs, docling elements, and TOC refs for a fixture.

    Returns (tg_data, tables, docling_by_page, toc_refs).
    """
    tg_path = fixture_dir / "table_graphs.json"
    if not tg_path.exists():
        return {}, [], {}, {}

    with open(tg_path) as f:
        tg = json.load(f)

    tables = tg.get("tables", [])
    total_pages = len(tg.get("pages", {}))
    docling_by_page = _load_docling_elements_by_page(fixture_dir)
    toc_refs = _extract_toc_refs(tables, total_pages)

    return tg, tables, docling_by_page, toc_refs


def build_dataset(fixtures: list[Path]
                  ) -> tuple[np.ndarray, np.ndarray, list[str], list[dict]]:
    """Build page-level training dataset from GT fixtures."""
    X_list, y_list, doc_ids, samples = [], [], [], []

    for fixture_dir in fixtures:
        doc_name = fixture_dir.name
        gt = _load_gt_lenient(fixture_dir)
        if gt is None:
            continue

        tg, tables, docling_by_page, toc_refs = _load_fixture_pages(fixture_dir)
        if not tg:
            continue

        pages_obj = tg.get("pages", {})
        total_pages = len(pages_obj)
        if total_pages == 0:
            continue

        # Group tables by page
        tables_by_page: dict[int, list[dict]] = {}
        for t in tables:
            p = t.get("pageNo")
            if p is not None:
                tables_by_page.setdefault(p, []).append(t)

        # Create one sample per page
        for page_str in pages_obj:
            page = int(page_str)
            cls = _page_to_class(page, gt)
            cls_idx = CLASS_TO_IDX.get(cls, CLASS_TO_IDX["OTHER"])

            page_tables = tables_by_page.get(page, [])
            page_text_els = docling_by_page.get(page, [])

            features = extract_page_features(
                page, total_pages, page_tables, page_text_els,
                toc_refs=toc_refs.get(page))

            X_list.append(features)
            y_list.append(cls_idx)
            doc_ids.append(doc_name)
            samples.append({
                "doc": doc_name, "page": page, "class": cls,
                "has_table": bool(page_tables),
                "has_text": bool(page_text_els),
            })

    X = np.array(X_list, dtype=np.float64)
    y = np.array(y_list)
    X = np.nan_to_num(X, nan=0.0, posinf=1e8, neginf=-1e8)
    return X, y, doc_ids, samples


# ── MLP training ─────────────────────────────────────────────────────────────

def _train_mlp(X_train, y_train):
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()

    X_scaled = scaler.fit_transform(X_train)

    # Use sample_weight to balance classes without inflating dataset size
    class_counts = Counter(y_train)
    max_count = max(class_counts.values())
    weights = np.array([max_count / class_counts[yi] for yi in y_train])
    # Cap weight to avoid extreme upweighting of tiny classes
    weights = np.minimum(weights, 50.0)

    clf = MLPClassifier(
        hidden_layer_sizes=(64, 32),
        activation="relu",
        max_iter=800,
        random_state=42,
        early_stopping=True,
        validation_fraction=0.15,
    )
    # MLPClassifier doesn't support sample_weight in fit() — use imblearn or
    # just subsample. Fall back to fast oversampling with a tight cap.
    target_count = min(max_count, 500)
    rng = np.random.RandomState(42)
    extra_indices = []
    for cls_idx, count in class_counts.items():
        if count < target_count:
            cls_mask = np.where(y_train == cls_idx)[0]
            extra_needed = target_count - count
            extra_indices.append(rng.choice(cls_mask, extra_needed, replace=True))
    if extra_indices:
        extra = np.concatenate(extra_indices)
        X_scaled = np.vstack([X_scaled, X_scaled[extra]])
        y_train = np.concatenate([y_train, y_train[extra]])

    clf.fit(X_scaled, y_train)
    return clf, scaler


def predict_proba(clf, scaler, X: np.ndarray) -> np.ndarray:
    X_scaled = scaler.transform(np.nan_to_num(X, nan=0.0, posinf=1e8, neginf=-1e8))
    return clf.predict_proba(X_scaled)


# ── LODOCV evaluation ────────────────────────────────────────────────────────

def run_lodocv(fixtures: list[Path]) -> dict:
    X, y, doc_ids, samples = build_dataset(fixtures)
    doc_ids_arr = np.array(doc_ids)
    unique_docs = sorted(set(doc_ids))

    all_preds = np.zeros(len(y), dtype=int)
    all_probs = np.zeros((len(y), len(CLASSES)), dtype=float)
    per_doc = {}

    for held_out in unique_docs:
        train_mask = doc_ids_arr != held_out
        test_mask = doc_ids_arr == held_out

        X_train, y_train = X[train_mask], y[train_mask]
        X_test = X[test_mask]

        clf, scaler = _train_mlp(X_train, y_train.copy())
        raw_probs = predict_proba(clf, scaler, X_test)

        # Map back to full class indices (some classes may be missing in fold)
        probs = np.zeros((raw_probs.shape[0], len(CLASSES)), dtype=float)
        for col_idx, cls_idx in enumerate(clf.classes_):
            probs[:, cls_idx] = raw_probs[:, col_idx]

        preds = probs.argmax(axis=1)

        all_preds[test_mask] = preds
        all_probs[test_mask] = probs

        test_indices = np.where(test_mask)[0]
        page_predictions = {}
        for i in test_indices:
            page = samples[i]["page"]
            prob_row = probs[i - test_indices[0]]
            top5 = sorted(enumerate(prob_row), key=lambda x: -x[1])[:5]
            page_predictions[page] = [
                {"class": CLASSES[ci], "score": round(float(s), 3)}
                for ci, s in top5
            ]

        gt = _load_gt_lenient(Path(__file__).parent / "fixtures" / held_out)
        gt_pages = {}
        if gt:
            for sec in gt.get("sections", []):
                sp = sec.get("start_page")
                if sp:
                    gt_pages[sp] = sec.get("statement_type", "OTHER")

        per_doc[held_out] = {
            "page_predictions": page_predictions,
            "gt_pages": gt_pages,
        }

    class_metrics = {}
    for ci, cls in enumerate(CLASSES):
        tp = int(((all_preds == ci) & (y == ci)).sum())
        fp = int(((all_preds == ci) & (y != ci)).sum())
        fn = int(((all_preds != ci) & (y == ci)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        support = int((y == ci).sum())
        class_metrics[cls] = {
            "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(f1, 3), "support": support,
        }

    accuracy = int((all_preds == y).sum()) / max(len(y), 1)

    return {
        "accuracy": round(accuracy, 3),
        "class_metrics": class_metrics,
        "per_doc": per_doc,
        "n_samples": len(y),
        "class_distribution": {CLASSES[ci]: int(c) for ci, c in
                                sorted(Counter(y).items())},
    }


# ── Full prediction ──────────────────────────────────────────────────────────

def predict_all_fixtures(gt_fixtures: list[Path],
                         all_fixtures: list[Path]) -> dict[str, dict]:
    """Train on all GT data, predict rank_tags for every page in every fixture."""
    X_train, y_train, _, _ = build_dataset(gt_fixtures)
    clf, scaler = _train_mlp(X_train, y_train.copy())

    results = {}

    for fixture_dir in all_fixtures:
        doc_name = fixture_dir.name
        tg, tables, docling_by_page, toc_refs = _load_fixture_pages(fixture_dir)
        if not tg:
            continue

        pages_obj = tg.get("pages", {})
        total_pages = len(pages_obj)
        if total_pages == 0:
            continue

        # Group tables by page
        tables_by_page: dict[int, list[dict]] = {}
        for t in tables:
            p = t.get("pageNo")
            if p is not None:
                tables_by_page.setdefault(p, []).append(t)

        # Extract features for every page
        X_list = []
        page_info = []
        for page_str in sorted(pages_obj.keys(), key=int):
            page = int(page_str)
            page_tables = tables_by_page.get(page, [])
            page_text_els = docling_by_page.get(page, [])

            features = extract_page_features(
                page, total_pages, page_tables, page_text_els,
                toc_refs=toc_refs.get(page))
            X_list.append(features)
            page_info.append({"page": page})

        if not X_list:
            continue

        X = np.array(X_list, dtype=np.float64)
        probs = predict_proba(clf, scaler, X)

        # Build per-page rank_tags
        page_ranks = {}
        for i, info in enumerate(page_info):
            page = info["page"]
            top5 = sorted(enumerate(probs[i]), key=lambda x: -x[1])[:5]
            page_ranks[page] = {
                "page": page,
                "top_class": CLASSES[top5[0][0]],
                "top_score": round(float(top5[0][1]), 3),
                "predictions": [
                    {"class": CLASSES[ci], "score": round(float(s), 3)}
                    for ci, s in top5
                ],
            }

        results[doc_name] = {"pages": page_ranks}

        out_path = fixture_dir / "rank_tags.json"
        with open(out_path, "w") as f:
            json.dump({"pages": page_ranks}, f, indent=2, ensure_ascii=False)

    return results


# ── CLI ──────────────────────────────────────────────────────────────────────

def print_eval_results(results: dict) -> None:
    print("\n" + "=" * 70)
    print("PAGE-LEVEL CLASSIFIER — LODOCV EVALUATION")
    print("=" * 70)

    print(f"\nOverall accuracy: {results['accuracy']:.1%}")
    print(f"Samples (pages): {results['n_samples']}")
    print(f"Class distribution: {results['class_distribution']}")

    print(f"\n{'Class':>8s}  {'Prec':>6s}  {'Rec':>6s}  {'F1':>6s}  {'Support':>8s}")
    print(f"{'-'*8}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*8}")
    for cls in CLASSES:
        m = results["class_metrics"].get(cls, {})
        print(f"{cls:>8s}  {m.get('precision',0):6.3f}  {m.get('recall',0):6.3f}  "
              f"{m.get('f1',0):6.3f}  {m.get('support',0):>8d}")

    print(f"\n{'Document':40s} {'Page':>5s} {'GT':>8s} {'Top1':>8s} {'Score':>6s} {'Top2':>8s}")
    print(f"{'-'*40} {'-'*5} {'-'*8} {'-'*8} {'-'*6} {'-'*8}")

    for doc_name in sorted(results["per_doc"]):
        dr = results["per_doc"][doc_name]
        gt_pages = dr.get("gt_pages", {})
        page_preds = dr.get("page_predictions", {})

        interesting_pages = set(gt_pages.keys())
        for page_str, preds in page_preds.items():
            page = int(page_str)
            if preds and preds[0]["class"] != "OTHER":
                interesting_pages.add(page)

        for page in sorted(interesting_pages)[:8]:
            gt_type = gt_pages.get(page, gt_pages.get(str(page), ""))
            preds = page_preds.get(page, page_preds.get(str(page), []))
            top1 = preds[0] if preds else {"class": "?", "score": 0}
            top2 = preds[1] if len(preds) > 1 else {"class": "", "score": 0}
            match = " OK" if top1["class"] == _TYPE_MAP.get(gt_type, gt_type) else ""
            print(f"{doc_name:40s} {page:>5d} {gt_type:>8s} {top1['class']:>8s} "
                  f"{top1['score']:>6.2f} {top2['class']:>8s}{match}")


def main():
    args = sys.argv[1:]
    gt_fixtures = find_gt_fixtures()

    if not gt_fixtures:
        print("No ground truth fixtures found")
        sys.exit(1)

    print(f"Found {len(gt_fixtures)} GT fixtures")

    if "--eval" in args:
        results = run_lodocv(gt_fixtures)
        print_eval_results(results)

        out_path = Path(__file__).parent / "rank_eval_report.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nReport: {out_path}")
        return

    # Full prediction mode
    fixtures_dir = Path(__file__).parent / "fixtures"
    fixture_filter = []
    if "--fixtures" in args:
        idx = args.index("--fixtures")
        fixture_filter = args[idx + 1:]

    if fixture_filter:
        all_fixtures = [fixtures_dir / name for name in fixture_filter
                        if (fixtures_dir / name).exists()]
    else:
        all_fixtures = sorted(p for p in fixtures_dir.iterdir()
                              if p.is_dir() and (p / "table_graphs.json").exists())

    print(f"Predicting {len(all_fixtures)} fixtures...")
    results = predict_all_fixtures(gt_fixtures, all_fixtures)

    # Summary
    print(f"\nWrote rank_tags.json for {len(results)} fixtures")
    for doc_name in sorted(results)[:10]:
        r = results[doc_name]
        pages = r["pages"]
        non_other = {p: v for p, v in pages.items()
                     if v["top_class"] != "OTHER"}
        if non_other:
            top_pages = sorted(non_other.items(),
                               key=lambda x: -x[1]["top_score"])[:5]
            preds_str = ", ".join(
                f"p.{p}={v['top_class']}({v['top_score']:.2f})"
                for p, v in top_pages)
            print(f"  {doc_name:40s} {preds_str}")

    if len(results) > 10:
        print(f"  ... and {len(results) - 10} more")


if __name__ == "__main__":
    main()
