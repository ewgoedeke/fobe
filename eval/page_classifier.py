#!/usr/bin/env python3
"""
page_classifier.py — Page context classifier using spatial layout CNN + TF-IDF.

Rasterizes docling/table bboxes into a spatial feature grid, runs a shallow
depthwise-separable CNN for visual features, concatenates with TF-IDF word
features, and classifies with a linear head.

Usage:
    python3 eval/page_classifier.py                # LODOCV on UGB20
    python3 eval/page_classifier.py --tier UGB50   # different tier
"""

import json
import sys
import os
from pathlib import Path
from collections import Counter

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_set import UGB20, UGB50, UGB100, UGB_ALL

FIXTURE_ROOT = Path(__file__).parent / "fixtures"

# ── Classes ───────────────────────────────────────────────────────────────

CLASSES = [
    "FRONT_MATTER", "TOC",
    "PNL", "SFP", "OCI", "CFS", "SOCIE",
    "MANAGEMENT_REPORT", "AUDITOR_REPORT", "SUPERVISORY_BOARD",
    "ESG", "CORPORATE_GOVERNANCE", "RISK_REPORT",
    "REMUNERATION_REPORT", "RESPONSIBILITY_STATEMENT",
    "NOTES", "APPENDIX",
]
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}

# ── Spatial grid rasterization ────────────────────────────────────────────

GRID_H, GRID_W = 64, 48  # portrait A4 aspect ratio (~1.33:1)

# Channels for the spatial grid
CH_TABLE_AREA = 0      # table bbox fill
CH_NUMERIC_CELL = 1    # cells with parsed numeric values
CH_LABEL_CELL = 2      # row label areas
CH_TEXT_BLOCK = 3       # docling text elements
CH_SECTION_HEADER = 4  # docling section headers
CH_LIST_ITEM = 5       # docling list items
N_CHANNELS = 6


def _fill_rect(grid: np.ndarray, channel: int,
               l: float, t: float, r: float, b: float,
               page_w: float, page_h: float, value: float = 1.0):
    """Fill a rectangle in the grid. Handles both TOPLEFT and BOTTOMLEFT coords."""
    if page_w <= 0 or page_h <= 0:
        return

    # Normalize to [0, 1]
    x0 = min(l, r) / page_w
    x1 = max(l, r) / page_w
    y0 = min(t, b) / page_h
    y1 = max(t, b) / page_h

    # Clamp
    x0 = max(0.0, min(1.0, x0))
    x1 = max(0.0, min(1.0, x1))
    y0 = max(0.0, min(1.0, y0))
    y1 = max(0.0, min(1.0, y1))

    # Map to grid
    gx0 = int(x0 * GRID_W)
    gx1 = max(gx0 + 1, int(x1 * GRID_W))
    gy0 = int(y0 * GRID_H)
    gy1 = max(gy0 + 1, int(y1 * GRID_H))

    gx1 = min(gx1, GRID_W)
    gy1 = min(gy1, GRID_H)

    grid[channel, gy0:gy1, gx0:gx1] = value


def rasterize_page(
    tables_on_page: list[dict],
    docling_texts: list[dict],
    page_w: float, page_h: float,
) -> np.ndarray:
    """Rasterize page layout into a multi-channel spatial grid."""
    grid = np.zeros((N_CHANNELS, GRID_H, GRID_W), dtype=np.float32)

    for t in tables_on_page:
        # Table-level bbox (BOTTOMLEFT origin)
        bbox = t.get("bbox")
        if bbox and len(bbox) == 4:
            _fill_rect(grid, CH_TABLE_AREA, bbox[0], bbox[3], bbox[2], bbox[1],
                        page_w, page_h)

        for r in t.get("rows", []):
            rbbox = r.get("bbox")
            if not rbbox or len(rbbox) != 4:
                continue

            # Row label area
            label = r.get("label", "").strip()
            if label:
                _fill_rect(grid, CH_LABEL_CELL,
                            rbbox[0], rbbox[1], rbbox[2], rbbox[3],
                            page_w, page_h)

            # Numeric cells
            for c in r.get("cells", []):
                if c.get("parsedValue") is not None:
                    cbbox = c.get("bbox")
                    if cbbox and len(cbbox) == 4:
                        _fill_rect(grid, CH_NUMERIC_CELL,
                                    cbbox[0], cbbox[1], cbbox[2], cbbox[3],
                                    page_w, page_h)

    # Docling text elements
    for el in docling_texts:
        bb = el.get("bbox", {})
        if not isinstance(bb, dict) or "l" not in bb:
            continue

        label = el.get("label", "")
        if label == "section_header":
            ch = CH_SECTION_HEADER
        elif label == "list_item":
            ch = CH_LIST_ITEM
        elif label in ("page_header", "page_footer"):
            continue  # skip furniture
        else:
            ch = CH_TEXT_BLOCK

        _fill_rect(grid, ch, bb["l"], bb["t"], bb["r"], bb["b"],
                    page_w, page_h)

    return grid


# ── Text extraction ───────────────────────────────────────────────────────

def page_text(tables_on_page: list[dict], docling_texts: list[dict]) -> str:
    parts = []
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
    for el in docling_texts:
        txt = (el.get("text") or "").strip()
        if txt:
            parts.append(txt)
    return " ".join(parts)


# ── Docling loading ───────────────────────────────────────────────────────

def load_docling_texts(fixture_dir: Path) -> dict[int, list[dict]]:
    de_path = fixture_dir / "docling_elements.json"
    if not de_path.exists():
        return {}
    try:
        data = json.loads(de_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

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
    return {}


# ── Ground truth ──────────────────────────────────────────────────────────

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


# ── Dataset ───────────────────────────────────────────────────────────────

def build_dataset(fixtures: list[Path]):
    """Returns grids, texts, labels, doc_ids, samples."""
    grids, texts, labels, doc_ids, samples = [], [], [], [], []

    for fixture_dir in fixtures:
        doc_name = fixture_dir.name
        page_labels = load_page_labels(fixture_dir)
        if page_labels is None:
            continue

        with open(fixture_dir / "table_graphs.json") as f:
            tg = json.load(f)

        pages_obj = tg.get("pages", {})
        total_pages = len(pages_obj)
        tables = tg.get("tables", [])
        docling_by_page = load_docling_texts(fixture_dir)

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
            pw = page_dims.get("width", 595.0)
            ph = page_dims.get("height", 842.0)

            page_tables = tables_by_page.get(page, [])
            page_docling = docling_by_page.get(page, [])

            grid = rasterize_page(page_tables, page_docling, pw, ph)
            text = page_text(page_tables, page_docling)

            grids.append(grid)
            texts.append(text)
            labels.append(CLASS_TO_IDX[stype])
            doc_ids.append(doc_name)
            samples.append({"doc": doc_name, "page": page, "class": stype})

    return (np.array(grids, dtype=np.float32), texts,
            np.array(labels), doc_ids, samples)


# ── Model ─────────────────────────────────────────────────────────────────

class DepthwiseSepConv(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size=3, padding=1):
        super().__init__()
        self.depthwise = nn.Conv2d(in_ch, in_ch, kernel_size, padding=padding,
                                    groups=in_ch, bias=False)
        self.pointwise = nn.Conv2d(in_ch, out_ch, 1, bias=False)
        self.bn = nn.BatchNorm2d(out_ch)

    def forward(self, x):
        x = self.depthwise(x)
        x = self.pointwise(x)
        x = self.bn(x)
        return F.relu(x)


class PageClassifier(nn.Module):
    def __init__(self, n_tfidf_features: int, n_classes: int,
                 visual_dim: int = 64):
        super().__init__()

        # Spatial CNN: 6ch → 16 → 32 → global pool → visual_dim
        self.conv1 = DepthwiseSepConv(N_CHANNELS, 16)
        self.conv2 = DepthwiseSepConv(16, 32)
        self.conv3 = DepthwiseSepConv(32, visual_dim)
        self.pool = nn.AdaptiveAvgPool2d(1)

        # Combined head
        combined_dim = visual_dim + n_tfidf_features
        self.head = nn.Sequential(
            nn.Linear(combined_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, n_classes),
        )

    def forward(self, grid, tfidf):
        # Visual branch
        v = self.conv1(grid)
        v = F.max_pool2d(v, 2)       # 64x48 → 32x24
        v = self.conv2(v)
        v = F.max_pool2d(v, 2)       # 32x24 → 16x12
        v = self.conv3(v)
        v = self.pool(v)              # → visual_dim x 1 x 1
        v = v.flatten(1)              # → visual_dim

        # Concat and classify
        x = torch.cat([v, tfidf], dim=1)
        return self.head(x)


# ── CNN feature extractor (trained per fold, feeds into LightGBM) ─────────

class SpatialEncoder(nn.Module):
    """Shallow depthwise-sep CNN → fixed-size visual embedding."""

    def __init__(self, embed_dim: int = 32):
        super().__init__()
        self.conv1 = DepthwiseSepConv(N_CHANNELS, 16)
        self.conv2 = DepthwiseSepConv(16, 32)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.proj = nn.Linear(32, embed_dim)

    def forward(self, x):
        x = self.conv1(x)
        x = F.max_pool2d(x, 2)       # 64x48 → 32x24
        x = self.conv2(x)
        x = F.max_pool2d(x, 2)       # 32x24 → 16x12
        x = self.pool(x).flatten(1)  # → 32
        return self.proj(x)           # → embed_dim


class SpatialClassifier(nn.Module):
    """CNN encoder + linear head for pretraining."""

    def __init__(self, n_classes: int, embed_dim: int = 32):
        super().__init__()
        self.encoder = SpatialEncoder(embed_dim)
        self.head = nn.Linear(embed_dim, n_classes)

    def forward(self, x):
        return self.head(self.encoder(x))


def train_cnn_encoder(grids, labels, n_classes, device,
                      embed_dim=32, epochs=120, lr=2e-3):
    """Train CNN on grids, return the encoder (feature extractor)."""
    model = SpatialClassifier(n_classes, embed_dim).to(device)

    grid_t = torch.tensor(grids, dtype=torch.float32).to(device)
    labels_t = torch.tensor(labels, dtype=torch.long).to(device)

    # Class weights
    counts = np.bincount(labels, minlength=n_classes).astype(np.float32)
    weights = np.zeros(n_classes, dtype=np.float32)
    active = counts > 0
    weights[active] = len(labels) / (active.sum() * counts[active])
    weight_t = torch.tensor(weights, dtype=torch.float32).to(device)

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-3)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, epochs)
    criterion = nn.CrossEntropyLoss(weight=weight_t)

    model.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = criterion(model(grid_t), labels_t)
        loss.backward()
        optimizer.step()
        scheduler.step()

    return model.encoder


def extract_cnn_features(encoder, grids, device):
    """Extract visual embeddings from trained encoder."""
    encoder.eval()
    with torch.no_grad():
        grid_t = torch.tensor(grids, dtype=torch.float32).to(device)
        feats = encoder(grid_t).cpu().numpy()
    return feats


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

CNN_EMBED_DIM = 32

def main():
    tier_name = "UGB20"
    tier_fn = UGB20
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--tier" and i + 1 < len(sys.argv) - 1:
            tier_name = sys.argv[i + 2]
            tier_fn = {"UGB20": UGB20, "UGB50": UGB50,
                       "UGB100": UGB100, "UGB_ALL": UGB_ALL}.get(tier_name, UGB20)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    docs = tier_fn()
    fixtures = [FIXTURE_ROOT / d for d in docs if (FIXTURE_ROOT / d).is_dir()]
    with_gt = [f for f in fixtures if load_page_labels(f) is not None]
    print(f"{tier_name}: {len(with_gt)} fixtures with GT")

    # Build dataset
    grids, texts, y, doc_ids, samples = build_dataset(with_gt)
    print(f"Dataset: {len(y)} pages, grid shape: {grids.shape}")

    dist = Counter(CLASSES[yi] for yi in y)
    active_classes = [c for c in CLASSES if dist.get(c, 0) > 0]
    print(f"\nClasses ({len(active_classes)}):")
    for cls in active_classes:
        n = dist[cls]
        print(f"  {cls:>25s}: {n:4d} ({100*n/len(y):5.1f}%)")

    nonempty = (grids.sum(axis=(1, 2, 3)) > 0).sum()
    print(f"\nPages with spatial data: {nonempty}/{len(grids)} ({100*nonempty/len(grids):.0f}%)")

    # TF-IDF
    vectorizer = TfidfVectorizer(max_features=2000, sublinear_tf=True, min_df=2)
    X_tfidf = vectorizer.fit_transform(texts).toarray().astype(np.float32)
    vocab = vectorizer.get_feature_names_out()
    print(f"TF-IDF: {len(vocab)} terms")
    print(f"CNN embed dim: {CNN_EMBED_DIM}")
    print(f"Combined will be: {len(vocab)} tfidf + {CNN_EMBED_DIM} cnn = {len(vocab) + CNN_EMBED_DIM}")

    # LODOCV: per fold, train CNN → extract features → concat with TF-IDF → LightGBM
    doc_ids_arr = np.array(doc_ids)
    unique_docs = sorted(set(doc_ids))
    n_classes = len(CLASSES)

    all_preds = np.zeros(len(y), dtype=int)
    all_probs = np.zeros((len(y), n_classes), dtype=float)

    print(f"\nLODOCV on {len(unique_docs)} documents...")
    for fold_i, held_out in enumerate(unique_docs):
        train_mask = doc_ids_arr != held_out
        test_mask = doc_ids_arr == held_out

        # 1. Train CNN encoder on train grids
        encoder = train_cnn_encoder(
            grids[train_mask], y[train_mask], n_classes, device,
            embed_dim=CNN_EMBED_DIM,
        )

        # 2. Extract CNN features for train and test
        cnn_train = extract_cnn_features(encoder, grids[train_mask], device)
        cnn_test = extract_cnn_features(encoder, grids[test_mask], device)

        # 3. Concat: TF-IDF + CNN features
        X_train = np.hstack([X_tfidf[train_mask], cnn_train])
        X_test = np.hstack([X_tfidf[test_mask], cnn_test])

        # 4. LightGBM
        lgbm = train_lgbm(X_train, y[train_mask], n_classes)
        probs = lgbm.predict(X_test)
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

    errors = []
    for i in range(len(y)):
        if all_preds[i] != y[i]:
            errors.append({
                "doc": doc_ids[i], "page": samples[i]["page"],
                "true": CLASSES[y[i]], "pred": CLASSES[all_preds[i]],
                "conf": round(float(all_probs[i, all_preds[i]]), 3),
            })

    # Print
    print("\n" + "=" * 70)
    print(f"{tier_name} — TF-IDF + SPATIAL FEATURES + LightGBM (LODOCV)")
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
        "NOTES": "NOT", "AUDITOR_REPORT": "AUD", "APPENDIX": "APP",
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

    # Feature importance — train full CNN + LightGBM on all data
    print(f"\nTop 25 features by importance:")
    full_encoder = train_cnn_encoder(grids, y, n_classes, device, embed_dim=CNN_EMBED_DIM)
    full_cnn = extract_cnn_features(full_encoder, grids, device)
    X_all = np.hstack([X_tfidf, full_cnn])
    full_model = train_lgbm(X_all, y, n_classes)
    importance = full_model.feature_importance(importance_type="gain")
    cnn_feat_names = [f"cnn_{i}" for i in range(CNN_EMBED_DIM)]
    all_feat_names = list(vocab) + cnn_feat_names
    top_feats = sorted(enumerate(importance), key=lambda x: -x[1])[:25]
    for idx, imp in top_feats:
        name = all_feat_names[idx] if idx < len(all_feat_names) else f"feat_{idx}"
        marker = " *" if idx >= len(vocab) else ""
        print(f"  {name:30s} {imp:10.1f}{marker}")

    # Save
    report = {
        "scope": tier_name, "method": "tfidf+cnn+lightgbm",
        "accuracy": round(accuracy, 3),
        "n_samples": len(y), "n_documents": len(unique_docs),
        "grid_shape": list(grids.shape[1:]),
        "vocab_size": len(vocab),
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
