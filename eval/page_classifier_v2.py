#!/usr/bin/env python3
"""
page_classifier_v2.py — Multimodal page classifier (4 branches).

Branch 1: EfficientNet-B0 visual encoder on rendered PDF pages (224×224)
Branch 2: Depthwise-separable CNN on rasterized layout grids (6ch × 64×48)
Branch 3: Sentence-transformer text encoder (frozen, projected)
Branch 4: Handcrafted structural features from Docling metadata

Fusion: concatenate all branch outputs → LightGBM (LODOCV).

Usage:
    python3 eval/page_classifier_v2.py                  # LODOCV on UGB20
    python3 eval/page_classifier_v2.py --tier UGB50     # different tier
    python3 eval/page_classifier_v2.py --cache-only     # pre-extract features, don't train
    python3 eval/page_classifier_v2.py --ablation       # run per-branch ablation study
"""

import json
import sys
import os
import hashlib
from pathlib import Path
from collections import Counter

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_set import UGB20, UGB50, UGB100, UGB_ALL

FIXTURE_ROOT = Path(__file__).parent / "fixtures"
SOURCES_ROOT = Path(__file__).parent.parent / "sources"
CACHE_DIR = Path(__file__).parent / ".feature_cache"

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

# ── Branch 1: PDF page rendering ─────────────────────────────────────────

IMG_SIZE = 224

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(3, 1, 1)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(3, 1, 1)


def render_pdf_page(pdf_path: Path, page_no: int) -> np.ndarray | None:
    """Render a single PDF page to a 224×224 RGB numpy array (CHW, float32, ImageNet-normalized)."""
    import fitz
    try:
        doc = fitz.open(str(pdf_path))
        if page_no < 1 or page_no > len(doc):
            doc.close()
            return None
        page = doc[page_no - 1]  # fitz is 0-indexed
        # Render at resolution that gives ~224px on the short side
        zoom = IMG_SIZE / min(page.rect.width, page.rect.height)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
        doc.close()
    except Exception:
        return None

    # Resize to exactly 224×224
    from PIL import Image
    pil_img = Image.fromarray(img).resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
    arr = np.array(pil_img, dtype=np.float32) / 255.0
    # HWC → CHW, then ImageNet normalize
    arr = arr.transpose(2, 0, 1)
    arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
    return arr


def find_pdf(doc_id: str) -> Path | None:
    """Find source PDF for a fixture."""
    for gaap_dir in ("ugb", "ifrs", "hgb"):
        candidate = SOURCES_ROOT / gaap_dir / f"{doc_id}.pdf"
        if candidate.exists():
            return candidate
    return None


# ── Branch 2: Layout grid (from page_classifier.py) ──────────────────────

GRID_H, GRID_W = 64, 48

CH_TABLE_AREA = 0
CH_NUMERIC_CELL = 1
CH_LABEL_CELL = 2
CH_TEXT_BLOCK = 3
CH_SECTION_HEADER = 4
CH_LIST_ITEM = 5
N_CHANNELS = 6


def _fill_rect(grid: np.ndarray, channel: int,
               l: float, t: float, r: float, b: float,
               page_w: float, page_h: float, value: float = 1.0):
    if page_w <= 0 or page_h <= 0:
        return
    x0 = max(0.0, min(1.0, min(l, r) / page_w))
    x1 = max(0.0, min(1.0, max(l, r) / page_w))
    y0 = max(0.0, min(1.0, min(t, b) / page_h))
    y1 = max(0.0, min(1.0, max(t, b) / page_h))
    gx0 = int(x0 * GRID_W)
    gx1 = min(max(gx0 + 1, int(x1 * GRID_W)), GRID_W)
    gy0 = int(y0 * GRID_H)
    gy1 = min(max(gy0 + 1, int(y1 * GRID_H)), GRID_H)
    grid[channel, gy0:gy1, gx0:gx1] = value


def rasterize_page(tables_on_page, docling_texts, page_w, page_h):
    grid = np.zeros((N_CHANNELS, GRID_H, GRID_W), dtype=np.float32)
    for t in tables_on_page:
        bbox = t.get("bbox")
        if bbox and len(bbox) == 4:
            _fill_rect(grid, CH_TABLE_AREA, bbox[0], bbox[3], bbox[2], bbox[1],
                        page_w, page_h)
        for r in t.get("rows", []):
            rbbox = r.get("bbox")
            if not rbbox or len(rbbox) != 4:
                continue
            if r.get("label", "").strip():
                _fill_rect(grid, CH_LABEL_CELL, rbbox[0], rbbox[1], rbbox[2], rbbox[3],
                            page_w, page_h)
            for c in r.get("cells", []):
                if c.get("parsedValue") is not None:
                    cbbox = c.get("bbox")
                    if cbbox and len(cbbox) == 4:
                        _fill_rect(grid, CH_NUMERIC_CELL, cbbox[0], cbbox[1], cbbox[2], cbbox[3],
                                    page_w, page_h)
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
            continue
        else:
            ch = CH_TEXT_BLOCK
        _fill_rect(grid, ch, bb["l"], bb["t"], bb["r"], bb["b"], page_w, page_h)
    return grid


# ── Branch 3: Text extraction ────────────────────────────────────────────

def page_text(tables_on_page, docling_texts):
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


# ── Branch 4: Structural features ────────────────────────────────────────

N_STRUCTURAL = 30


def extract_structural_features(
    tables_on_page: list[dict],
    docling_texts: list[dict],
    page_w: float, page_h: float,
    page_no: int, total_pages: int,
) -> np.ndarray:
    """Extract ~30 handcrafted structural features from Docling elements."""
    f = np.zeros(N_STRUCTURAL, dtype=np.float32)

    # ── Element counts (0-6) ──
    f[0] = len(tables_on_page)
    f[1] = len(docling_texts)
    f[2] = sum(1 for t in docling_texts if t.get("label") == "section_header")
    f[3] = sum(1 for t in docling_texts if t.get("label") == "list_item")
    f[4] = sum(1 for t in docling_texts if t.get("label") == "footnote")
    f[5] = sum(1 for t in docling_texts if t.get("label") == "page_header")
    f[6] = sum(1 for t in docling_texts if t.get("label") == "caption")

    # ── Table structure (7-14) ──
    total_rows = sum(len(t.get("rows", [])) for t in tables_on_page)
    total_numeric = sum(
        1 for t in tables_on_page for r in t.get("rows", [])
        for c in r.get("cells", []) if c.get("parsedValue") is not None
    )
    total_cells = sum(
        len(r.get("cells", [])) for t in tables_on_page for r in t.get("rows", [])
    )
    f[7] = total_rows
    f[8] = total_numeric
    f[9] = total_numeric / max(total_cells, 1)  # numeric density
    f[10] = max((len(t.get("columns", [])) for t in tables_on_page), default=0)
    f[11] = 1.0 if any(t.get("headerRowCount", 0) > 0 for t in tables_on_page) else 0.0

    # Hierarchy
    depths = [r.get("depth", 0) for t in tables_on_page for r in t.get("rows", [])]
    f[12] = max(depths, default=0)
    f[13] = float(np.mean(depths)) if depths else 0.0
    f[14] = sum(1 for t in tables_on_page for r in t.get("rows", []) if r.get("childIds"))

    # ── Coverage ratios (15-17) ──
    page_area = page_w * page_h
    table_area = 0.0
    for t in tables_on_page:
        bb = t.get("bbox")
        if bb and len(bb) == 4:
            table_area += abs(bb[2] - bb[0]) * abs(bb[3] - bb[1])
    text_area = 0.0
    for el in docling_texts:
        bb = el.get("bbox", {})
        if isinstance(bb, dict) and "l" in bb:
            text_area += abs(bb["r"] - bb["l"]) * abs(bb["b"] - bb["t"])
    f[15] = table_area / max(page_area, 1)
    f[16] = text_area / max(page_area, 1)
    f[17] = table_area / max(text_area, 1)

    # ── Position features (18-19) ──
    f[18] = page_no / max(total_pages, 1)
    f[19] = 1.0 if page_no <= 2 else 0.0

    # ── Classification signals from table metadata (20-22) ──
    components = [t.get("statementComponent", "") or "" for t in tables_on_page]
    f[20] = 1.0 if any("PNL" in c for c in components) else 0.0
    f[21] = 1.0 if any("SFP" in c for c in components) else 0.0
    f[22] = 1.0 if any("CFS" in c for c in components) else 0.0

    # ── Keyword indicators targeting top error patterns (23-29) ──
    all_text = " ".join(t.get("text", "") for t in docling_texts).lower()
    row_text = " ".join(
        r.get("label", "") for t in tables_on_page for r in t.get("rows", [])
    ).lower()
    combined = all_text + " " + row_text

    f[23] = 1.0 if "bestätigungsvermerk" in combined else 0.0
    f[24] = 1.0 if ("wirtschaftsprüfer" in combined or "abschlussprüfer" in combined) else 0.0
    f[25] = 1.0 if ("prüfungsurteil" in combined or "audit opinion" in combined) else 0.0
    f[26] = 1.0 if "inhaltsverzeichnis" in combined else 0.0
    f[27] = 1.0 if "anhang" in combined else 0.0
    f[28] = 1.0 if "bilanzstichtag" in combined else 0.0
    f[29] = 1.0 if ("lagebericht" in combined or "management report" in combined) else 0.0

    return f


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


# ── CNN encoder (Branch 2) ───────────────────────────────────────────────

class DepthwiseSepConv(nn.Module):
    def __init__(self, in_ch, out_ch, kernel_size=3, padding=1):
        super().__init__()
        self.depthwise = nn.Conv2d(in_ch, in_ch, kernel_size, padding=padding,
                                    groups=in_ch, bias=False)
        self.pointwise = nn.Conv2d(in_ch, out_ch, 1, bias=False)
        self.bn = nn.BatchNorm2d(out_ch)

    def forward(self, x):
        return F.relu(self.bn(self.pointwise(self.depthwise(x))))


class SpatialEncoder(nn.Module):
    def __init__(self, embed_dim: int = 32):
        super().__init__()
        self.conv1 = DepthwiseSepConv(N_CHANNELS, 16)
        self.conv2 = DepthwiseSepConv(16, 32)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.proj = nn.Linear(32, embed_dim)

    def forward(self, x):
        x = F.max_pool2d(self.conv1(x), 2)
        x = F.max_pool2d(self.conv2(x), 2)
        return self.proj(self.pool(x).flatten(1))


class SpatialClassifier(nn.Module):
    def __init__(self, n_classes: int, embed_dim: int = 32):
        super().__init__()
        self.encoder = SpatialEncoder(embed_dim)
        self.head = nn.Linear(embed_dim, n_classes)

    def forward(self, x):
        return self.head(self.encoder(x))


# ── Visual encoder (Branch 1) ────────────────────────────────────────────

class VisualEncoder(nn.Module):
    def __init__(self, embed_dim: int = 64):
        super().__init__()
        from torchvision.models import efficientnet_b0, EfficientNet_B0_Weights
        eff = efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1)
        self.features = eff.features
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.proj = nn.Linear(1280, embed_dim)

        # Freeze entire backbone — only train projection head
        # With ~500 train samples per fold, fine-tuning conv layers overfits
        for p in self.features.parameters():
            p.requires_grad = False

    def forward(self, x):
        with torch.no_grad():
            x = self.features(x)
            x = self.pool(x).flatten(1)
        return self.proj(x)


class VisualClassifier(nn.Module):
    def __init__(self, n_classes: int, embed_dim: int = 64):
        super().__init__()
        self.encoder = VisualEncoder(embed_dim)
        self.head = nn.Linear(embed_dim, n_classes)

    def forward(self, x):
        return self.head(self.encoder(x))


# ── Training helpers ──────────────────────────────────────────────────────

def _class_weights(labels, n_classes, device):
    counts = np.bincount(labels, minlength=n_classes).astype(np.float32)
    weights = np.zeros(n_classes, dtype=np.float32)
    active = counts > 0
    weights[active] = len(labels) / (active.sum() * counts[active])
    return torch.tensor(weights, dtype=torch.float32).to(device)


def train_spatial_encoder(grids, labels, n_classes, device,
                          embed_dim=32, epochs=120, lr=2e-3):
    model = SpatialClassifier(n_classes, embed_dim).to(device)
    grid_t = torch.tensor(grids, dtype=torch.float32).to(device)
    labels_t = torch.tensor(labels, dtype=torch.long).to(device)
    weight_t = _class_weights(labels, n_classes, device)

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


def train_visual_encoder(images, labels, n_classes, device,
                         embed_dim=64, epochs=50, lr=2e-3, batch_size=64):
    model = VisualClassifier(n_classes, embed_dim).to(device)
    weight_t = _class_weights(labels, n_classes, device)

    optimizer = torch.optim.Adam(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=lr, weight_decay=1e-3,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, epochs)
    criterion = nn.CrossEntropyLoss(weight=weight_t)

    # Pre-extract frozen backbone features to avoid redundant forward passes
    model.eval()
    with torch.no_grad():
        backbone_feats = []
        for i in range(0, len(images), batch_size):
            batch = torch.tensor(images[i:i + batch_size], dtype=torch.float32).to(device)
            feat = model.encoder.features(batch)
            feat = model.encoder.pool(feat).flatten(1)
            backbone_feats.append(feat)
        backbone_feats = torch.cat(backbone_feats)

    labels_t = torch.tensor(labels, dtype=torch.long).to(device)

    # Only train proj + head on cached backbone features
    model.train()
    n = len(labels)
    for epoch in range(epochs):
        perm = torch.randperm(n)
        for i in range(0, n, batch_size):
            idx = perm[i:i + batch_size]
            feat = backbone_feats[idx]
            proj = model.encoder.proj(feat)
            logits = model.head(proj)
            optimizer.zero_grad()
            loss = criterion(logits, labels_t[idx])
            loss.backward()
            optimizer.step()
        scheduler.step()

    return model.encoder


def extract_encoder_features(encoder, data, device, batch_size=64):
    encoder.eval()
    feats = []
    with torch.no_grad():
        for i in range(0, len(data), batch_size):
            batch = torch.tensor(data[i:i + batch_size], dtype=torch.float32).to(device)
            feats.append(encoder(batch).cpu().numpy())
    return np.vstack(feats)


# ── Text encoder (Branch 3) ──────────────────────────────────────────────

_st_model = None

def get_text_embeddings(texts: list[str], batch_size=64) -> np.ndarray:
    """Extract sentence-transformer embeddings (frozen, cached in memory)."""
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer
        _st_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    embeddings = _st_model.encode(
        texts, batch_size=batch_size, show_progress_bar=True,
        convert_to_numpy=True,
    )
    return embeddings.astype(np.float32)


# ── Dataset builder ───────────────────────────────────────────────────────

def build_dataset(fixtures: list[Path], use_cache=True):
    """
    Build full multimodal dataset. Returns dict with:
      images: (N, 3, 224, 224) — rendered PDF pages
      grids:  (N, 6, 64, 48)  — layout grids
      texts:  list[str]        — page text for sentence-transformer
      structural: (N, 30)     — structural features
      labels: (N,)            — class indices
      doc_ids: list[str]      — document name per sample
      samples: list[dict]     — metadata per sample
    """
    cache_path = CACHE_DIR / "dataset.npz"
    meta_path = CACHE_DIR / "dataset_meta.json"

    # Check cache validity
    if use_cache and cache_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        cached_docs = set(meta.get("doc_ids_set", []))
        requested_docs = set(f.name for f in fixtures)
        if cached_docs == requested_docs:
            print("Loading cached features...")
            npz = np.load(cache_path, allow_pickle=True)
            return {
                "images": npz["images"],
                "grids": npz["grids"],
                "texts": list(npz["texts"]),
                "structural": npz["structural"],
                "labels": npz["labels"],
                "doc_ids": list(npz["doc_ids"]),
                "samples": json.loads(meta["samples_json"]),
            }

    images, grids, texts, structural = [], [], [], []
    labels, doc_ids, samples = [], [], []

    for fi, fixture_dir in enumerate(fixtures):
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

        pdf_path = find_pdf(doc_name)
        pdf_doc = None
        if pdf_path:
            import fitz
            try:
                pdf_doc = fitz.open(str(pdf_path))
            except Exception:
                pass

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

            # Branch 1: rendered image
            img = None
            if pdf_doc and 1 <= page <= len(pdf_doc):
                try:
                    from PIL import Image
                    fitz_page = pdf_doc[page - 1]
                    zoom = IMG_SIZE / min(fitz_page.rect.width, fitz_page.rect.height)
                    mat = fitz.Matrix(zoom, zoom)
                    pix = fitz_page.get_pixmap(matrix=mat, alpha=False)
                    raw = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, 3)
                    pil_img = Image.fromarray(raw).resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
                    img = np.array(pil_img, dtype=np.float32).transpose(2, 0, 1) / 255.0
                except Exception:
                    pass
            if img is None:
                # White page, ImageNet-normalized
                img = (np.ones((3, IMG_SIZE, IMG_SIZE), dtype=np.float32) - IMAGENET_MEAN) / IMAGENET_STD
            images.append(img)

            # Branch 2: layout grid
            grids.append(rasterize_page(page_tables, page_docling, pw, ph))

            # Branch 3: text
            texts.append(page_text(page_tables, page_docling))

            # Branch 4: structural
            structural.append(extract_structural_features(
                page_tables, page_docling, pw, ph, page, total_pages,
            ))

            labels.append(CLASS_TO_IDX[stype])
            doc_ids.append(doc_name)
            samples.append({"doc": doc_name, "page": page, "class": stype})

        if pdf_doc:
            pdf_doc.close()

        print(f"  [{fi+1}/{len(fixtures)}] {doc_name}: "
              f"{sum(1 for d in doc_ids if d == doc_name)} pages")

    result = {
        "images": np.array(images, dtype=np.float32),
        "grids": np.array(grids, dtype=np.float32),
        "texts": texts,
        "structural": np.array(structural, dtype=np.float32),
        "labels": np.array(labels),
        "doc_ids": doc_ids,
        "samples": samples,
    }

    # Save cache
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache_path,
        images=result["images"],
        grids=result["grids"],
        texts=np.array(result["texts"], dtype=object),
        structural=result["structural"],
        labels=result["labels"],
        doc_ids=np.array(result["doc_ids"], dtype=object),
    )
    meta_path.write_text(json.dumps({
        "doc_ids_set": sorted(set(doc_ids)),
        "n_samples": len(labels),
        "samples_json": json.dumps(samples),
    }))
    print(f"Cached to {cache_path}")

    return result


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


# ── LODOCV evaluation ────────────────────────────────────────────────────

CNN_EMBED_DIM = 32
VIS_EMBED_DIM = 64
TEXT_EMBED_DIM = 384  # raw sentence-transformer output (no projection in LightGBM path)


def run_lodocv(dataset, tier_name, branches=None):
    """
    Run leave-one-document-out cross-validation.

    branches: set of enabled branches. Default: all four.
        "visual"     — EfficientNet on rendered pages
        "layout"     — depthwise-sep CNN on layout grids
        "text"       — sentence-transformer embeddings
        "structural" — handcrafted structural features
    """
    if branches is None:
        branches = {"visual", "layout", "text", "structural"}

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_classes = len(CLASSES)

    y = dataset["labels"]
    doc_ids = dataset["doc_ids"]
    doc_ids_arr = np.array(doc_ids)
    unique_docs = sorted(set(doc_ids))

    # Pre-extract text embeddings (frozen — same for all folds)
    text_feats = None
    if "text" in branches:
        print("Extracting sentence-transformer embeddings...")
        text_feats = get_text_embeddings(dataset["texts"])
        print(f"  Text embeddings: {text_feats.shape}")

    all_preds = np.zeros(len(y), dtype=int)
    all_probs = np.zeros((len(y), n_classes), dtype=float)

    print(f"\nLODOCV on {len(unique_docs)} documents, branches: {sorted(branches)}...")
    for fold_i, held_out in enumerate(unique_docs):
        train_mask = doc_ids_arr != held_out
        test_mask = doc_ids_arr == held_out

        feature_parts_train = []
        feature_parts_test = []
        feat_names = []

        # Branch 1: Visual encoder
        if "visual" in branches:
            vis_encoder = train_visual_encoder(
                dataset["images"][train_mask], y[train_mask],
                n_classes, device, embed_dim=VIS_EMBED_DIM,
            )
            vis_train = extract_encoder_features(vis_encoder, dataset["images"][train_mask], device)
            vis_test = extract_encoder_features(vis_encoder, dataset["images"][test_mask], device)
            feature_parts_train.append(vis_train)
            feature_parts_test.append(vis_test)
            feat_names.extend([f"vis_{i}" for i in range(VIS_EMBED_DIM)])

        # Branch 2: Layout CNN
        if "layout" in branches:
            layout_encoder = train_spatial_encoder(
                dataset["grids"][train_mask], y[train_mask],
                n_classes, device, embed_dim=CNN_EMBED_DIM,
            )
            layout_train = extract_encoder_features(layout_encoder, dataset["grids"][train_mask], device)
            layout_test = extract_encoder_features(layout_encoder, dataset["grids"][test_mask], device)
            feature_parts_train.append(layout_train)
            feature_parts_test.append(layout_test)
            feat_names.extend([f"layout_{i}" for i in range(CNN_EMBED_DIM)])

        # Branch 3: Text embeddings
        if "text" in branches:
            feature_parts_train.append(text_feats[train_mask])
            feature_parts_test.append(text_feats[test_mask])
            feat_names.extend([f"text_{i}" for i in range(text_feats.shape[1])])

        # Branch 4: Structural features
        if "structural" in branches:
            feature_parts_train.append(dataset["structural"][train_mask])
            feature_parts_test.append(dataset["structural"][test_mask])
            feat_names.extend([f"struct_{i}" for i in range(N_STRUCTURAL)])

        X_train = np.hstack(feature_parts_train)
        X_test = np.hstack(feature_parts_test)

        lgbm = train_lgbm(X_train, y[train_mask], n_classes)
        probs = lgbm.predict(X_test)
        preds = probs.argmax(axis=1)

        all_preds[test_mask] = preds
        all_probs[test_mask] = probs

        n_test = test_mask.sum()
        correct = (preds == y[test_mask]).sum()
        print(f"  [{fold_i+1:2d}/{len(unique_docs)}] {held_out:55s} "
              f"{correct}/{n_test} ({100*correct/n_test:.0f}%)")

    return all_preds, all_probs, feat_names


# ── Reporting ─────────────────────────────────────────────────────────────

def print_report(y, all_preds, all_probs, tier_name, branches, feat_names,
                 doc_ids, samples, dataset=None):
    accuracy = (all_preds == y).sum() / len(y)
    n_classes = len(CLASSES)

    dist = Counter(CLASSES[yi] for yi in y)
    active_classes = [c for c in CLASSES if dist.get(c, 0) > 0]

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

    print("\n" + "=" * 70)
    branch_str = "+".join(sorted(branches))
    print(f"{tier_name} — {branch_str} → LightGBM (LODOCV)")
    print("=" * 70)
    print(f"\nAccuracy: {accuracy:.1%} ({int(accuracy * len(y))}/{len(y)})")

    print(f"\nClasses ({len(active_classes)}):")
    ml = max(len(c) for c in active_classes)
    print(f"{'Class':>{ml}s}  {'Prec':>6s}  {'Rec':>6s}  {'F1':>6s}  {'N':>5s}")
    print(f"{'-'*ml}  {'-'*6}  {'-'*6}  {'-'*6}  {'-'*5}")
    for cls in active_classes:
        m = class_metrics[cls]
        print(f"{cls:>{ml}s}  {m['precision']:6.3f}  {m['recall']:6.3f}  "
              f"{m['f1']:6.3f}  {m['support']:>5d}")

    # Macro F1
    f1s = [class_metrics[c]["f1"] for c in active_classes]
    print(f"\n{'Macro F1':>{ml}s}  {'':>6s}  {'':>6s}  {np.mean(f1s):6.3f}")

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

    # Save report
    report = {
        "scope": tier_name,
        "method": branch_str + "+lightgbm",
        "accuracy": round(accuracy, 3),
        "macro_f1": round(float(np.mean(f1s)), 3),
        "n_samples": len(y),
        "n_documents": len(set(doc_ids)),
        "branches": sorted(branches),
        "class_metrics": class_metrics,
        "class_distribution": {cls: dist.get(cls, 0) for cls in active_classes},
        "confusion_matrix": {"classes": active_classes, "matrix": confusion.tolist()},
        "n_errors": len(errors),
        "errors": errors,
    }
    out_path = Path(__file__).parent / f"page_eval_v2_{tier_name.lower()}.json"
    with open(out_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport: {out_path}")

    return report


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    tier_name = "UGB20"
    tier_fn = UGB20
    cache_only = False
    do_ablation = False

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--tier" and i + 1 < len(args):
            tier_name = args[i + 1]
            tier_fn = {"UGB20": UGB20, "UGB50": UGB50,
                       "UGB100": UGB100, "UGB_ALL": UGB_ALL}.get(tier_name, UGB20)
        elif arg == "--cache-only":
            cache_only = True
        elif arg == "--ablation":
            do_ablation = True

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    docs = tier_fn()
    fixtures = [FIXTURE_ROOT / d for d in docs if (FIXTURE_ROOT / d).is_dir()]
    with_gt = [f for f in fixtures if load_page_labels(f) is not None]
    print(f"{tier_name}: {len(with_gt)} fixtures with GT")

    # Build dataset
    print("\nBuilding dataset...")
    dataset = build_dataset(with_gt)
    y = dataset["labels"]
    print(f"Dataset: {len(y)} pages")
    print(f"  images: {dataset['images'].shape}")
    print(f"  grids:  {dataset['grids'].shape}")
    print(f"  structural: {dataset['structural'].shape}")

    dist = Counter(CLASSES[yi] for yi in y)
    active_classes = [c for c in CLASSES if dist.get(c, 0) > 0]
    print(f"\nClasses ({len(active_classes)}):")
    for cls in active_classes:
        n = dist[cls]
        print(f"  {cls:>25s}: {n:4d} ({100*n/len(y):5.1f}%)")

    if cache_only:
        print("\nCache-only mode — done.")
        return

    # Full run with all branches
    all_branches = {"visual", "layout", "text", "structural"}
    preds, probs, feat_names = run_lodocv(dataset, tier_name, branches=all_branches)
    print_report(y, preds, probs, tier_name, all_branches, feat_names,
                 dataset["doc_ids"], dataset["samples"], dataset)

    # Ablation study
    if do_ablation:
        print("\n\n" + "=" * 70)
        print("ABLATION STUDY")
        print("=" * 70)

        ablation_configs = [
            {"structural"},
            {"text"},
            {"layout"},
            {"visual"},
            {"layout", "text"},                    # v1 equivalent (was TF-IDF)
            {"structural", "text"},
            {"structural", "layout", "text"},      # everything minus visual
            {"visual", "layout", "text"},           # everything minus structural
        ]

        results = []
        for branches in ablation_configs:
            label = "+".join(sorted(branches))
            print(f"\n--- {label} ---")
            p, pr, fn = run_lodocv(dataset, tier_name, branches=branches)
            acc = (p == y).sum() / len(y)
            f1s = []
            for cls in active_classes:
                ci = CLASS_TO_IDX[cls]
                tp = int(((p == ci) & (y == ci)).sum())
                fp = int(((p == ci) & (y != ci)).sum())
                fn_c = int(((p != ci) & (y == ci)).sum())
                prec = tp / max(tp + fp, 1)
                rec = tp / max(tp + fn_c, 1)
                f1 = 2 * prec * rec / max(prec + rec, 1e-9)
                f1s.append(f1)
            macro_f1 = np.mean(f1s)
            results.append((label, acc, macro_f1))
            print(f"  Accuracy: {acc:.1%}  Macro-F1: {macro_f1:.3f}")

        print(f"\n{'Branches':45s} {'Acc':>7s} {'F1':>7s}")
        print("-" * 60)
        for label, acc, f1 in sorted(results, key=lambda x: -x[2]):
            print(f"{label:45s} {acc:7.1%} {f1:7.3f}")


if __name__ == "__main__":
    main()
