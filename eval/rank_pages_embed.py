#!/usr/bin/env python3
"""
rank_pages_embed.py — Page classifier using sentence embeddings + LightGBM.

Embeds page text with a multilingual sentence-transformer, combines with
handcrafted numeric features, and classifies with LightGBM.

Usage:
    python3 eval/rank_pages_embed.py --eval          # LODOCV evaluation
    python3 eval/rank_pages_embed.py                  # train + predict all
    python3 eval/rank_pages_embed.py --embed-only     # cache embeddings only
"""

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rank_pages import (
    CLASSES, CLASS_TO_IDX, _TYPE_MAP, FEATURE_NAMES,
    extract_page_features, _load_docling_elements_by_page,
    _extract_toc_refs, _load_gt_lenient, find_gt_fixtures,
    _page_to_class,
)

EMBED_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
EMBED_DIM = 384
EMBED_CACHE_DIR = Path(__file__).parent / ".embed_cache"


# ── Page text extraction ────────────────────────────────────────────────────

def _page_text(
    tables_on_page: list[dict],
    text_elements: list[dict],
) -> str:
    """Build a single text blob from all content on a page."""
    parts = []

    # Table content: column headers + row labels + cell text
    for t in tables_on_page:
        # Column headers
        for col in t.get("columns", []):
            header = col.get("header", "")
            if header:
                parts.append(header)

        # Row labels and cell text
        for r in t.get("rows", []):
            label = r.get("label", "").strip()
            if label:
                parts.append(label)
            for c in r.get("cells", []):
                txt = (c.get("text") or "").strip()
                if txt and not txt.replace(",", "").replace(".", "").replace("-", "").isdigit():
                    parts.append(txt)

    # Docling text elements
    for el in text_elements:
        txt = el.get("text", "").strip()
        if txt:
            parts.append(txt)

    return " ".join(parts)[:2000]  # cap at 2000 chars


# ── Embedding ───────────────────────────────────────────────────────────────

def _get_embed_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL)


def _cache_path(fixture_name: str) -> Path:
    return EMBED_CACHE_DIR / f"{fixture_name}.npz"


def embed_fixture(
    fixture_dir: Path,
    model,
    force: bool = False,
) -> dict[int, np.ndarray] | None:
    """Embed all pages in a fixture. Returns {page_no: embedding_384d}.

    Caches to disk to avoid re-embedding.
    """
    fixture_name = fixture_dir.name
    cache = _cache_path(fixture_name)

    if cache.exists() and not force:
        data = np.load(cache)
        return {int(k): data[k] for k in data.files}

    tg_path = fixture_dir / "table_graphs.json"
    if not tg_path.exists():
        return None

    with open(tg_path) as f:
        tg = json.load(f)

    pages_obj = tg.get("pages", {})
    if not pages_obj:
        return None

    tables = tg.get("tables", [])
    docling_by_page = _load_docling_elements_by_page(fixture_dir)

    # Group tables by page
    tables_by_page: dict[int, list[dict]] = {}
    for t in tables:
        p = t.get("pageNo")
        if p is not None:
            tables_by_page.setdefault(p, []).append(t)

    # Build text for each page
    page_nums = sorted(int(k) for k in pages_obj)
    texts = []
    for page in page_nums:
        pt = _page_text(
            tables_by_page.get(page, []),
            docling_by_page.get(page, []),
        )
        texts.append(pt if pt.strip() else "empty page")

    # Embed all at once (batched)
    embeddings = model.encode(texts, batch_size=64, show_progress_bar=False)

    result = {}
    save_dict = {}
    for i, page in enumerate(page_nums):
        result[page] = embeddings[i]
        save_dict[str(page)] = embeddings[i]

    EMBED_CACHE_DIR.mkdir(exist_ok=True)
    np.savez_compressed(cache, **save_dict)

    return result


def embed_all_fixtures(fixtures: list[Path], force: bool = False) -> dict[str, dict[int, np.ndarray]]:
    """Embed all fixtures, with progress reporting."""
    model = _get_embed_model()

    results = {}
    cached = 0
    embedded = 0
    t0 = time.time()

    for i, fixture_dir in enumerate(fixtures):
        cache = _cache_path(fixture_dir.name)
        was_cached = cache.exists() and not force

        emb = embed_fixture(fixture_dir, model, force=force)
        if emb is not None:
            results[fixture_dir.name] = emb
            if was_cached:
                cached += 1
            else:
                embedded += 1

        if (i + 1) % 20 == 0 or i == len(fixtures) - 1:
            elapsed = time.time() - t0
            print(f"  [{i+1}/{len(fixtures)}] {embedded} embedded, {cached} cached ({elapsed:.1f}s)")

    return results


# ── Dataset building ────────────────────────────────────────────────────────

def build_dataset(
    fixtures: list[Path],
    embeddings: dict[str, dict[int, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray, list[str], list[dict]]:
    """Build combined feature matrix: embeddings + handcrafted features."""
    X_list, y_list, doc_ids, samples = [], [], [], []

    for fixture_dir in fixtures:
        doc_name = fixture_dir.name
        gt = _load_gt_lenient(fixture_dir)
        if gt is None:
            continue

        doc_embeddings = embeddings.get(doc_name, {})
        if not doc_embeddings:
            continue

        tg_path = fixture_dir / "table_graphs.json"
        if not tg_path.exists():
            continue
        with open(tg_path) as f:
            tg = json.load(f)

        pages_obj = tg.get("pages", {})
        total_pages = len(pages_obj)
        if total_pages == 0:
            continue

        tables = tg.get("tables", [])
        docling_by_page = _load_docling_elements_by_page(fixture_dir)
        toc_refs = _extract_toc_refs(tables, total_pages)

        tables_by_page: dict[int, list[dict]] = {}
        for t in tables:
            p = t.get("pageNo")
            if p is not None:
                tables_by_page.setdefault(p, []).append(t)

        for page_str in pages_obj:
            page = int(page_str)
            cls = _page_to_class(page, gt)
            cls_idx = CLASS_TO_IDX.get(cls, CLASS_TO_IDX["OTHER"])

            page_tables = tables_by_page.get(page, [])
            page_text_els = docling_by_page.get(page, [])

            # Handcrafted features
            hc_features = extract_page_features(
                page, total_pages, page_tables, page_text_els,
                toc_refs=toc_refs.get(page))

            # Embedding (384-dim)
            emb = doc_embeddings.get(page)
            if emb is None:
                emb = np.zeros(EMBED_DIM, dtype=np.float32)

            # Combine: embedding + handcrafted
            combined = np.concatenate([emb, np.array(hc_features, dtype=np.float32)])

            X_list.append(combined)
            y_list.append(cls_idx)
            doc_ids.append(doc_name)
            samples.append({
                "doc": doc_name, "page": page, "class": cls,
            })

    X = np.array(X_list, dtype=np.float32)
    y = np.array(y_list)
    return X, y, doc_ids, samples


# ── LightGBM training ──────────────────────────────────────────────────────

def _train_lgbm(X_train, y_train):
    import lightgbm as lgb

    train_data = lgb.Dataset(X_train, label=y_train)

    params = {
        "objective": "multiclass",
        "num_class": len(CLASSES),
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

    model = lgb.train(
        params,
        train_data,
        num_boost_round=500,
        valid_sets=[train_data],
        callbacks=[lgb.early_stopping(20, verbose=False)],
    )
    return model


def predict_proba_lgbm(model, X: np.ndarray) -> np.ndarray:
    return model.predict(X)


# ── LODOCV evaluation ───────────────────────────────────────────────────────

def run_lodocv(
    fixtures: list[Path],
    embeddings: dict[str, dict[int, np.ndarray]],
) -> dict:
    X, y, doc_ids, samples = build_dataset(fixtures, embeddings)
    doc_ids_arr = np.array(doc_ids)
    unique_docs = sorted(set(doc_ids))

    all_preds = np.zeros(len(y), dtype=int)
    all_probs = np.zeros((len(y), len(CLASSES)), dtype=float)

    t0 = time.time()
    for fold_i, held_out in enumerate(unique_docs):
        train_mask = doc_ids_arr != held_out
        test_mask = doc_ids_arr == held_out

        X_train, y_train = X[train_mask], y[train_mask]
        X_test = X[test_mask]

        model = _train_lgbm(X_train, y_train)
        probs = predict_proba_lgbm(model, X_test)
        preds = probs.argmax(axis=1)

        all_preds[test_mask] = preds
        all_probs[test_mask] = probs

        if (fold_i + 1) % 10 == 0:
            elapsed = time.time() - t0
            print(f"  Fold {fold_i+1}/{len(unique_docs)} ({elapsed:.1f}s)")

    # Metrics
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

    # Per-class confusion details
    errors = []
    for i in range(len(y)):
        if all_preds[i] != y[i]:
            errors.append({
                "doc": doc_ids[i],
                "page": samples[i]["page"],
                "true": CLASSES[y[i]],
                "pred": CLASSES[all_preds[i]],
                "conf": round(float(all_probs[i, all_preds[i]]), 3),
            })

    return {
        "accuracy": round(accuracy, 3),
        "class_metrics": class_metrics,
        "n_samples": len(y),
        "class_distribution": {CLASSES[ci]: int(c) for ci, c in
                                sorted(Counter(y).items())},
        "n_errors": len(errors),
        "sample_errors": errors[:50],
    }


def print_eval_results(results: dict) -> None:
    print("\n" + "=" * 70)
    print("EMBEDDING + LIGHTGBM — LODOCV EVALUATION")
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

    print(f"\nErrors: {results['n_errors']}")
    if results.get("sample_errors"):
        print(f"\n{'Document':40s} {'Page':>5s} {'True':>8s} {'Pred':>8s} {'Conf':>6s}")
        print(f"{'-'*40} {'-'*5} {'-'*8} {'-'*8} {'-'*6}")
        for e in results["sample_errors"][:30]:
            print(f"{e['doc']:40s} {e['page']:>5d} {e['true']:>8s} {e['pred']:>8s} {e['conf']:>6.2f}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    gt_fixtures = find_gt_fixtures()
    fixtures_dir = Path(__file__).parent / "fixtures"
    all_fixtures = sorted(p for p in fixtures_dir.iterdir()
                          if p.is_dir() and (p / "table_graphs.json").exists())

    print(f"GT fixtures: {len(gt_fixtures)}, total fixtures: {len(all_fixtures)}")

    if "--embed-only" in args:
        print("Embedding all fixtures...")
        embed_all_fixtures(all_fixtures, force="--force" in args)
        print("Done.")
        return

    # Embed GT fixtures (needed for eval and training)
    print("Embedding GT fixtures...")
    gt_embeddings = embed_all_fixtures(gt_fixtures, force="--force" in args)
    print(f"Embedded {len(gt_embeddings)} fixtures")

    if "--eval" in args:
        print("\nRunning LODOCV...")
        results = run_lodocv(gt_fixtures, gt_embeddings)
        print_eval_results(results)

        out_path = Path(__file__).parent / "rank_embed_eval_report.json"
        with open(out_path, "w") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"\nReport: {out_path}")
        return

    # Full prediction mode
    print("Embedding all fixtures...")
    all_embeddings = embed_all_fixtures(all_fixtures)

    # Train on all GT data
    print("Building training set...")
    X_train, y_train, _, _ = build_dataset(gt_fixtures, gt_embeddings)
    print(f"Training LightGBM on {X_train.shape[0]} samples, {X_train.shape[1]} features...")
    model = _train_lgbm(X_train, y_train)

    # Predict all fixtures
    print("Predicting all fixtures...")
    n_written = 0
    for fixture_dir in all_fixtures:
        doc_name = fixture_dir.name
        doc_emb = all_embeddings.get(doc_name, {})
        if not doc_emb:
            continue

        tg_path = fixture_dir / "table_graphs.json"
        with open(tg_path) as f:
            tg = json.load(f)

        pages_obj = tg.get("pages", {})
        total_pages = len(pages_obj)
        if total_pages == 0:
            continue

        tables = tg.get("tables", [])
        docling_by_page = _load_docling_elements_by_page(fixture_dir)
        toc_refs = _extract_toc_refs(tables, total_pages)

        tables_by_page: dict[int, list[dict]] = {}
        for t in tables:
            p = t.get("pageNo")
            if p is not None:
                tables_by_page.setdefault(p, []).append(t)

        X_list = []
        page_info = []
        for page_str in sorted(pages_obj.keys(), key=int):
            page = int(page_str)
            page_tables = tables_by_page.get(page, [])
            page_text_els = docling_by_page.get(page, [])

            hc = extract_page_features(
                page, total_pages, page_tables, page_text_els,
                toc_refs=toc_refs.get(page))
            emb = doc_emb.get(page, np.zeros(EMBED_DIM, dtype=np.float32))
            combined = np.concatenate([emb, np.array(hc, dtype=np.float32)])
            X_list.append(combined)
            page_info.append({"page": page})

        if not X_list:
            continue

        X = np.array(X_list, dtype=np.float32)
        probs = predict_proba_lgbm(model, X)

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

        out_path = fixture_dir / "rank_tags.json"
        with open(out_path, "w") as f:
            json.dump({"pages": page_ranks}, f, indent=2, ensure_ascii=False)
        n_written += 1

    print(f"\nWrote rank_tags.json for {n_written} fixtures")


if __name__ == "__main__":
    main()
