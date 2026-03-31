#!/usr/bin/env python3
"""
eval_ugb20_pages.py — Evaluate page-level context classification on UGB20.

Simple approach: TF-IDF on all page words + layout features, LightGBM.

Usage:
    python3 eval/eval_ugb20_pages.py
    python3 eval/eval_ugb20_pages.py --tier UGB50
"""

import json
import sys
import os
from pathlib import Path
from collections import Counter

import numpy as np
from scipy.sparse import hstack, csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_set import UGB20, UGB50, UGB100, UGB_ALL

FIXTURE_ROOT = Path(__file__).parent / "fixtures"

# ── Classes (full taxonomy, no OTHER) ─────────────────────────────────────

CLASSES = [
    "FRONT_MATTER", "TOC",
    "PNL", "SFP", "OCI", "CFS", "SOCIE",
    "MANAGEMENT_REPORT", "AUDITOR_REPORT", "SUPERVISORY_BOARD",
    "ESG", "CORPORATE_GOVERNANCE", "RISK_REPORT",
    "REMUNERATION_REPORT", "RESPONSIBILITY_STATEMENT",
    "NOTES", "APPENDIX",
]
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}


# ── Docling elements loading ──────────────────────────────────────────────

def _load_docling_texts(fixture_dir: Path) -> dict[int, list[dict]]:
    """Load docling texts grouped by page. Returns {page: [text_elements]}."""
    de_path = fixture_dir / "docling_elements.json"
    if not de_path.exists():
        return {}
    try:
        data = json.loads(de_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    # DoclingDocument format
    if isinstance(data, dict) and "texts" in data:
        by_page: dict[int, list[dict]] = {}
        for t in data.get("texts", []):
            for prov in t.get("prov", []):
                page = prov.get("page_no")
                if page is not None:
                    by_page.setdefault(page, []).append({
                        "text": t.get("text", ""),
                        "label": t.get("label", ""),
                        "bbox": prov.get("bbox", {}),
                    })
        return by_page

    # Legacy format: {page_str: [elements]}
    if isinstance(data, dict):
        by_page = {}
        for k, v in data.items():
            try:
                page = int(k)
            except ValueError:
                continue
            by_page[page] = v if isinstance(v, list) else [v]
        return by_page

    return {}


# ── Page feature extraction ───────────────────────────────────────────────

def extract_page(
    page_no: int,
    total_pages: int,
    tables_on_page: list[dict],
    docling_texts: list[dict],
    page_width: float,
    page_height: float,
) -> tuple[str, list[float]]:
    """Extract text and layout features for a single page.

    Returns (text_for_tfidf, layout_features).
    """
    parts = []

    # ── Text from tables ──
    for t in tables_on_page:
        for col in t.get("columns", []):
            h = col.get("header", "").strip()
            if h:
                parts.append(h)
        for r in t.get("rows", []):
            label = r.get("label", "").strip()
            if label:
                parts.append(label)
            for c in r.get("cells", []):
                txt = (c.get("text") or "").strip()
                if txt:
                    parts.append(txt)

    # ── Text from docling ──
    for el in docling_texts:
        txt = (el.get("text") or "").strip()
        if txt:
            parts.append(txt)

    text = " ".join(parts)

    # ── Layout features ──
    word_count = len(text.split()) if text.strip() else 0

    # Table layout
    n_tables = len(tables_on_page)
    total_rows = sum(len(t.get("rows", [])) for t in tables_on_page)
    total_cols = sum(len(t.get("columns", [])) for t in tables_on_page)
    total_value_cols = sum(
        sum(1 for c in t.get("columns", []) if c.get("role") == "VALUE")
        for t in tables_on_page
    )
    total_header_rows = sum(t.get("headerRowCount", 0) for t in tables_on_page)

    # Table area coverage (fraction of page area covered by tables)
    page_area = max(page_width * page_height, 1.0)
    table_area = 0.0
    for t in tables_on_page:
        bbox = t.get("bbox")
        if bbox and len(bbox) == 4:
            # bbox is [l, t, r, b] in BOTTOMLEFT — width * height
            w = abs(bbox[2] - bbox[0])
            h = abs(bbox[1] - bbox[3])
            table_area += w * h
    table_coverage = min(table_area / page_area, 1.0)

    # Text density from docling (chars per page area)
    docling_char_count = sum(len(el.get("text", "")) for el in docling_texts)
    text_density = docling_char_count / page_area

    # Docling element type counts
    n_section_headers = sum(1 for el in docling_texts if el.get("label") == "section_header")
    n_list_items = sum(1 for el in docling_texts if el.get("label") == "list_item")
    n_paragraphs = sum(1 for el in docling_texts if el.get("label") in ("text", "paragraph"))

    # Text bbox coverage (how much of page has text, from docling bboxes)
    text_area = 0.0
    for el in docling_texts:
        bb = el.get("bbox", {})
        if isinstance(bb, dict) and "l" in bb:
            w = abs(bb.get("r", 0) - bb.get("l", 0))
            h = abs(bb.get("t", 0) - bb.get("b", 0))
            text_area += w * h
    text_coverage = min(text_area / page_area, 1.0) if page_area > 0 else 0.0

    # Row indent levels (structural depth indicator)
    indent_levels = [r.get("indentLevel", 0) for t in tables_on_page for r in t.get("rows", [])]
    max_indent = max(indent_levels) if indent_levels else 0
    mean_indent = sum(indent_levels) / len(indent_levels) if indent_levels else 0.0

    # Numeric content ratio
    all_cells = [c for t in tables_on_page for r in t.get("rows", []) for c in r.get("cells", [])]
    n_numeric = sum(1 for c in all_cells if c.get("parsedValue") is not None)
    numeric_ratio = n_numeric / max(len(all_cells), 1)

    # Position features
    rel_pos = page_no / max(total_pages, 1)

    features = [
        # Position (3)
        float(page_no),
        rel_pos,
        1.0 if page_no <= 3 else 0.0,
        # Word/text counts (4)
        float(word_count),
        float(docling_char_count),
        text_density,
        text_coverage,
        # Table structure (7)
        float(n_tables),
        float(total_rows),
        float(total_cols),
        float(total_value_cols),
        float(total_header_rows),
        table_coverage,
        numeric_ratio,
        # Docling element types (3)
        float(n_section_headers),
        float(n_list_items),
        float(n_paragraphs),
        # Table structure depth (2)
        float(max_indent),
        mean_indent,
    ]

    return text, features


LAYOUT_FEATURE_NAMES = [
    "page_no", "rel_pos", "is_first_3",
    "word_count", "docling_chars", "text_density", "text_coverage",
    "n_tables", "total_rows", "total_cols", "total_value_cols",
    "total_header_rows", "table_coverage", "numeric_ratio",
    "n_section_headers", "n_list_items", "n_paragraphs",
    "max_indent", "mean_indent",
]


# ── Ground truth loading ──────────────────────────────────────────────────

def load_page_labels(fixture_dir: Path) -> dict[int, str] | None:
    tg_path = fixture_dir / "table_graphs.json"
    if not tg_path.exists():
        return None

    with open(tg_path) as f:
        tg = json.load(f)
    pages_obj = tg.get("pages", {})
    if not pages_obj:
        return None
    total_pages = max(int(k) for k in pages_obj)

    v2_path = fixture_dir / "ground_truth" / "toc_v2.json"
    v1_path = fixture_dir / "ground_truth" / "toc.json"

    if v2_path.exists():
        data = json.loads(v2_path.read_text())
        transitions = sorted(data.get("transitions", []), key=lambda t: t["page"])
        if not transitions:
            return None
        labels = {}
        for i, tr in enumerate(transitions):
            start = tr["page"]
            end = transitions[i + 1]["page"] if i + 1 < len(transitions) else total_pages + 1
            for p in range(start, end):
                if str(p) in pages_obj:
                    labels[p] = tr["section_type"]
        return labels if labels else None

    elif v1_path.exists():
        data = json.loads(v1_path.read_text())
        sections = data.get("sections", [])
        if not sections:
            return None
        labels = {}
        for sec in sections:
            sp = sec.get("start_page", 0)
            ep = sec.get("end_page") or sp
            for p in range(sp, ep + 1):
                if str(p) in pages_obj:
                    labels[p] = sec["statement_type"]
        for tp in data.get("toc_pages", []):
            if str(tp) in pages_obj:
                labels[tp] = "TOC"
        return labels if labels else None

    return None


# ── Dataset building ──────────────────────────────────────────────────────

def build_dataset(fixtures: list[Path]):
    """Returns texts, layout_features, labels, doc_ids, sample_info."""
    texts, layout_feats, labels, doc_ids, samples = [], [], [], [], []

    for fixture_dir in fixtures:
        doc_name = fixture_dir.name
        page_labels = load_page_labels(fixture_dir)
        if page_labels is None:
            continue

        tg_path = fixture_dir / "table_graphs.json"
        with open(tg_path) as f:
            tg = json.load(f)

        pages_obj = tg.get("pages", {})
        total_pages = len(pages_obj)
        tables = tg.get("tables", [])
        docling_by_page = _load_docling_texts(fixture_dir)

        tables_by_page: dict[int, list[dict]] = {}
        for t in tables:
            p = t.get("pageNo")
            if p is not None:
                tables_by_page.setdefault(p, []).append(t)

        for page_str in pages_obj:
            page = int(page_str)
            stype = page_labels.get(page)
            if stype is None or stype not in CLASS_TO_IDX:
                continue

            page_dims = pages_obj[page_str]
            text, feats = extract_page(
                page, total_pages,
                tables_by_page.get(page, []),
                docling_by_page.get(page, []),
                page_dims.get("width", 595.0),
                page_dims.get("height", 842.0),
            )

            texts.append(text)
            layout_feats.append(feats)
            labels.append(CLASS_TO_IDX[stype])
            doc_ids.append(doc_name)
            samples.append({"doc": doc_name, "page": page, "class": stype})

    return texts, np.array(layout_feats, dtype=np.float32), np.array(labels), doc_ids, samples


# ── LightGBM ─────────────────────────────────────────────────────────────

def train_lgbm(X_train, y_train, n_classes):
    import lightgbm as lgb

    train_data = lgb.Dataset(X_train, label=y_train)
    params = {
        "objective": "multiclass",
        "num_class": n_classes,
        "metric": "multi_logloss",
        "is_unbalance": True,
        "learning_rate": 0.05,
        "num_leaves": 63,
        "max_depth": 8,
        "min_child_samples": 5,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "seed": 42,
    }
    return lgb.train(
        params, train_data, num_boost_round=500,
        valid_sets=[train_data],
        callbacks=[lgb.early_stopping(20, verbose=False)],
    )


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    tier_name = "UGB20"
    tier_fn = UGB20
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--tier" and i + 1 < len(sys.argv) - 1:
            tier_name = sys.argv[i + 2]
            tier_fn = {"UGB20": UGB20, "UGB50": UGB50,
                       "UGB100": UGB100, "UGB_ALL": UGB_ALL}.get(tier_name, UGB20)

    docs = tier_fn()
    fixtures = [FIXTURE_ROOT / d for d in docs if (FIXTURE_ROOT / d).is_dir()]
    print(f"{tier_name}: {len(fixtures)} fixtures")

    with_gt = [f for f in fixtures if load_page_labels(f) is not None]
    print(f"With ground truth: {len(with_gt)}")

    # Build dataset
    texts, layout, y, doc_ids, samples = build_dataset(with_gt)
    n_docs = len(set(doc_ids))
    print(f"Dataset: {len(y)} pages from {n_docs} documents")
    print(f"Layout features: {layout.shape[1]} ({', '.join(LAYOUT_FEATURE_NAMES)})")

    dist = Counter(CLASSES[yi] for yi in y)
    active_classes = [c for c in CLASSES if dist.get(c, 0) > 0]
    print(f"\nClass distribution ({len(active_classes)} classes):")
    for cls in active_classes:
        n = dist[cls]
        print(f"  {cls:>25s}: {n:4d} ({100*n/len(y):5.1f}%)")

    # TF-IDF on words
    print(f"\nFitting TF-IDF...")
    vectorizer = TfidfVectorizer(max_features=3000, sublinear_tf=True, min_df=2)
    X_tfidf = vectorizer.fit_transform(texts)
    vocab = vectorizer.get_feature_names_out()
    print(f"Vocabulary: {len(vocab)} terms")

    # Combine: TF-IDF (sparse) + layout (dense)
    X_all = hstack([X_tfidf, csr_matrix(layout)])
    print(f"Combined features: {X_all.shape[1]} ({len(vocab)} tfidf + {layout.shape[1]} layout)")

    # LODOCV
    doc_ids_arr = np.array(doc_ids)
    unique_docs = sorted(set(doc_ids))
    n_classes = len(CLASSES)

    all_preds = np.zeros(len(y), dtype=int)
    all_probs = np.zeros((len(y), n_classes), dtype=float)

    print(f"\nLODOCV on {len(unique_docs)} documents...")
    for fold_i, held_out in enumerate(unique_docs):
        train_mask = doc_ids_arr != held_out
        test_mask = doc_ids_arr == held_out

        X_train = X_all[train_mask].toarray()
        X_test = X_all[test_mask].toarray()
        y_train = y[train_mask]

        model = train_lgbm(X_train, y_train, n_classes)
        probs = model.predict(X_test)
        preds = probs.argmax(axis=1)

        all_preds[test_mask] = preds
        all_probs[test_mask] = probs

        n_test = test_mask.sum()
        correct = (preds == y[test_mask]).sum()
        print(f"  [{fold_i+1:2d}/{len(unique_docs)}] {held_out:45s} {correct}/{n_test} ({100*correct/n_test:.0f}%)")

    # Metrics
    accuracy = (all_preds == y).sum() / len(y)

    class_metrics = {}
    for cls in active_classes:
        ci = CLASS_TO_IDX[cls]
        tp = int(((all_preds == ci) & (y == ci)).sum())
        fp = int(((all_preds == ci) & (y != ci)).sum())
        fn = int(((all_preds != ci) & (y == ci)).sum())
        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * prec * rec / max(prec + rec, 1e-9)
        class_metrics[cls] = {
            "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(f1, 3), "support": int((y == ci).sum()),
        }

    # Confusion
    n_active = len(active_classes)
    confusion = np.zeros((n_active, n_active), dtype=int)
    active_idx_list = [CLASS_TO_IDX[c] for c in active_classes]
    idx_to_active = {ci: ai for ai, ci in enumerate(active_idx_list)}
    for true_i, pred_i in zip(y, all_preds):
        ai_true = idx_to_active.get(true_i)
        ai_pred = idx_to_active.get(pred_i)
        if ai_true is not None and ai_pred is not None:
            confusion[ai_true][ai_pred] += 1

    # Errors
    errors = []
    for i in range(len(y)):
        if all_preds[i] != y[i]:
            errors.append({
                "doc": doc_ids[i], "page": samples[i]["page"],
                "true": CLASSES[y[i]], "pred": CLASSES[all_preds[i]],
                "conf": round(float(all_probs[i, all_preds[i]]), 3),
            })

    # ── Print results ──
    print("\n" + "=" * 70)
    print(f"{tier_name} — TF-IDF + LAYOUT + LightGBM (LODOCV)")
    print("=" * 70)
    print(f"\nAccuracy: {accuracy:.1%} ({int(accuracy * len(y))}/{len(y)})")

    ml = max(len(c) for c in active_classes)
    print(f"\n{'Class':>{ml}s}  {'Prec':>6s}  {'Rec':>6s}  {'F1':>6s}  {'N':>5s}")
    print(f"{'-'*ml}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*5}")
    for cls in active_classes:
        m = class_metrics[cls]
        print(f"{cls:>{ml}s}  {m['precision']:6.3f}  {m['recall']:6.3f}  "
              f"{m['f1']:6.3f}  {m['support']:>5d}")

    abbrev = {
        "FRONT_MATTER": "FM", "TOC": "TOC", "PNL": "PNL", "SFP": "SFP",
        "OCI": "OCI", "CFS": "CFS", "SOCIE": "SOC", "NOTES": "NOT",
        "AUDITOR_REPORT": "AUD", "MANAGEMENT_REPORT": "MGT", "APPENDIX": "APP",
    }
    print(f"\nConfusion (rows=true, cols=pred):")
    header = " " * (ml + 1) + "".join(f"{abbrev.get(c, c[:3]):>6s}" for c in active_classes)
    print(header)
    for ri, cls in enumerate(active_classes):
        row = f"{cls:>{ml}s} " + "".join(f"{confusion[ri][ci]:>6d}" for ci in range(n_active))
        print(row)

    print(f"\nErrors: {len(errors)}")
    if errors:
        error_pairs = Counter((e["true"], e["pred"]) for e in errors)
        print(f"\nTop error patterns:")
        for (true, pred), count in error_pairs.most_common(10):
            print(f"  {true:>{ml}s} → {pred:<{ml}s}: {count}")

        print(f"\nSample errors:")
        for e in errors[:20]:
            print(f"  {e['doc']:45s} p{e['page']:<3d} {e['true']:>18s} → {e['pred']:<18s} conf={e['conf']:.2f}")

    # Feature importance
    print(f"\nTop 20 features by importance (full-data model):")
    full_model = train_lgbm(X_all.toarray(), y, n_classes)
    importance = full_model.feature_importance(importance_type="gain")
    all_feat_names = list(vocab) + LAYOUT_FEATURE_NAMES
    top_feats = sorted(enumerate(importance), key=lambda x: -x[1])[:20]
    for idx, imp in top_feats:
        name = all_feat_names[idx] if idx < len(all_feat_names) else f"feat_{idx}"
        print(f"  {name:30s} {imp:10.1f}")

    # Save
    report = {
        "scope": tier_name, "method": "tfidf+layout+lightgbm",
        "accuracy": round(accuracy, 3),
        "n_samples": len(y), "n_documents": n_docs,
        "vocab_size": len(vocab), "n_layout_features": layout.shape[1],
        "class_metrics": class_metrics,
        "class_distribution": {cls: dist.get(cls, 0) for cls in active_classes},
        "confusion_matrix": {"classes": active_classes, "matrix": confusion.tolist()},
        "n_errors": len(errors), "errors": errors,
    }
    out_path = Path(__file__).parent / "ugb20_page_eval.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport: {out_path}")


if __name__ == "__main__":
    main()
