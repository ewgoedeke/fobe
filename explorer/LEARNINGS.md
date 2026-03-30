# Explorer Learnings

## 2026-03-28: Bounding Box Coordinate System

### Bug
Bounding box overlays in the Element Browser were misplaced on page images.

### Root Cause
Two compounding errors in `PageWithOverlays.jsx`:

1. **Wrong bbox format assumption**: The code treated `bbox` as `[x, y, width, height]` but the actual format from Docling is `[x1, y1, x2, y2]` (left, top, right, bottom in PDF coordinate space). The stitching code in `table_stitching.py:127-131` confirms this — it uses `min(b[0])`, `min(b[1])`, `max(b[2])`, `max(b[3])` to merge bounding boxes, which only makes sense for corner coordinates.

2. **Wrong coordinate origin**: PDF coordinates use bottom-left origin (y increases upward), while CSS uses top-left origin (y increases downward). The y-coordinate was used directly as CSS `top`, placing boxes at the opposite vertical position.

### Evidence
- `kapsch_2024` raw_0: `bbox=[230.6, 682.7, 525.3, 253.6]` on page height 841.89
- `y + h = 936.3 > 841.89` — impossible if `[x, y, w, h]` with top-left origin
- `amag_2024` page 3 tables ordered by y1 descending match visual top-to-bottom order, confirming bottom-left origin

### Fix
```javascript
// Before (wrong):
const [bx, by, bw, bh] = t.bbox
left: (bx / pageDims.width) * 100 + '%'
top:  (by / pageDims.height) * 100 + '%'
width:  (bw / pageDims.width) * 100 + '%'
height: (bh / pageDims.height) * 100 + '%'

// After (correct):
const [x1, y1, x2, y2] = t.bbox  // PDF coords: bottom-left origin
left: (x1 / pageDims.width) * 100 + '%'
top:  ((pageDims.height - y1) / pageDims.height) * 100 + '%'
width:  ((x2 - x1) / pageDims.width) * 100 + '%'
height: ((y1 - y2) / pageDims.height) * 100 + '%'
```

### Lesson
When working with document coordinates, always verify:
1. The bbox format (corner coords vs origin+size) — check stitching/merge code for clues
2. The coordinate origin (PDF = bottom-left, CSS/image = top-left)
3. Validate with arithmetic: if `y + h > page_height`, the format assumption is wrong

## 2026-03-28: text_ Tables Missing from Element Browser Views

### Observation
Only `raw_` tables (Docling HTML table extractions) appear as bounding box overlays. `text_` tables (text-layout-based extractions) are mostly invisible.

### Root Cause
`text_` tables almost universally have `statementComponent=None` — they aren't classified by the pipeline. The Element Browser shows pages per selected statement type. Since `text_` tables don't contribute to any statement type's page set, their pages aren't displayed, and their bounding boxes never render.

### Impact
- `text_` tables exist in fixtures (e.g., amag_2024 has 24, evn_2024 has 10)
- They have valid bounding boxes but no classification
- They're only visible if a `raw_` table on the same page happens to be classified

### Potential Fix
Either classify `text_` tables in the pipeline (table_classifier.py), or add an "ALL" / "UNCLASSIFIED" view option to the Element Browser.

## 2026-03-28: Docling Cell-Level Bounding Boxes Discarded

### Bug
`raw_` tables in `table_graphs.json` had row/column/cell bboxes all set to `[0, 0, 0, 0]`, despite Docling providing per-cell bounding boxes in its output.

### Root Cause
In `ingest_docling.py:build_tables_raw()`, the code extracted text from Docling grid cells but **ignored their bbox data**. Row, column, and cell bboxes were initialized as all-zeros placeholders:

```python
# Before (discarding Docling cell bboxes):
"row_bboxes": [[0, 0, 0, 0] for _ in grid],
"col_bboxes": [[0, 0, 0, 0] for _ in range(col_count)],
"cell_bboxes": [[[0, 0, 0, 0] for _ in row] for row in grid],
```

Meanwhile, Docling's grid cells contain rich bbox data:
```json
{
  "text": "1 Europe West",
  "bbox": {"l": 78.662, "t": 635.598, "r": 131.757, "b": 641.866, "coord_origin": "TOPLEFT"},
  "row_span": 1, "col_span": 1, ...
}
```

### Coordinate System Mismatch
Two coordinate origins coexist in Docling output:
- **Table-level bbox** (from `prov[0].bbox`): `coord_origin: "BOTTOMLEFT"` (standard PDF)
- **Cell-level bboxes** (from `data.grid[r][c].bbox`): `coord_origin: "TOPLEFT"` (screen/CSS)

This means `table_bbox` and `row_bboxes` use different coordinate systems. The frontend `PageWithOverlays.jsx` handles this with separate conversion functions (`pdfToCSS` for table bbox, `tlToCSS` for row/cell bboxes).

### Fix
Updated `build_tables_raw()` to:
1. Extract cell bboxes from `grid[row][col]["bbox"]` as `[l, t, r, b]`
2. Compute row bboxes as the union of all cell bboxes in each row
3. Compute column bboxes as the union of all cell bboxes in each column

After fix: Wienerberger test — 211 tables, all cells/rows/columns have valid bounding boxes.

### Lesson
When wrapping a library's output, audit what data is available before writing placeholder zeros. The Docling grid cell dict had 12 fields (bbox, row_span, col_span, etc.) but only `text` was being read.

### Reprocessing Status (2026-03-28)

Existing `table_graphs.json` fixtures were generated with the old code and have zero bboxes for `raw_` tables. They need reprocessing through `ingest_docling.py` + `preprocess.py` to get cell-level bboxes.

- **4 documents reprocessed** via `/tmp/doc_tag/reprocess_bboxes.py` (006 Wienerberger, 007 Verbund, 010 voestalpine, 011 A1 Group) — all achieved 100% row bbox coverage.
- **63 eval fixtures** need reprocessing. 38 have 0% row bboxes, 24 have 1-15% (only `text_` tables). None have 100%.
- **Reprocessing script**: `eval/reprocess_fixtures.py` — matches fixtures to source PDFs in `sources/ifrs/` and `sources/ugb/`, re-runs full Docling pipeline. Requires `docling` pip package.
- Run: `python3 eval/reprocess_fixtures.py --audit-only` to check status, `python3 eval/reprocess_fixtures.py` to reprocess.

## 2026-03-28: FACC TOC Not Detected

### Observation
FACC 2024 TOC page (page 2) shows "0 tables" in Element Browser despite having visible TOC content.

### Root Cause
The FACC TOC is a **designed landscape spread** (1559x794 pts — double-width) with the TOC as styled text on the left half and a large photo on the right half. Docling's HTML table extractor doesn't detect it because the TOC content is rendered as graphic design elements, not HTML `<table>` markup.

### Impact
- No table bounding boxes on the TOC page
- TOC structure must come from ground truth annotation, not automatic detection
- This is a known Docling limitation for designed/graphical annual report layouts

### Lesson
Docling only detects tables rendered as HTML `<table>` elements in the PDF structure. Visually formatted tables (styled text, multi-column layouts, graphical designs) require the text-recovery pipeline (`recover_text_tables()` in `preprocess.py`) or manual annotation.

## 2026-03-28: Docling Cell Metadata Discarded

### Bug
`ingest_docling.py` only extracted `text` from Docling grid cells, discarding structural metadata that Docling provides per cell: `column_header`, `row_header`, `row_section`, `row_span`, `col_span`.

### Fix
Added `cell_meta` extraction in `build_tables_raw()`. Each cell's metadata is captured as a sparse dict (only non-default values stored). This data is available in `tables_raw.jsonl` for `preprocess.py` to use for header detection, section identification, and merged cell handling.

### Available Docling cell fields now captured
| Field | Type | Use |
|-------|------|-----|
| `column_header` | bool | Improves header row detection |
| `row_header` | bool | Identifies label/row-header cells |
| `row_section` | bool | Identifies section divider rows |
| `row_span` | int | Merged cell height (>1 means spanning rows) |
| `col_span` | int | Merged cell width (>1 means spanning columns) |

## 2026-03-28: table_stitching.py Bbox Merge Bug

### Bug
`table_stitching.py` used `min(y1)` and `max(y2)` to merge bounding boxes when stitching multi-page tables. This is correct for TOPLEFT coordinates but **wrong for BOTTOMLEFT** (the coordinate system used by table-level bboxes). It produced a bbox covering the overlap region instead of the union.

### Fix
Changed to `max(y1)` (highest top) and `min(y2)` (lowest bottom) for BOTTOMLEFT, with comments documenting the coordinate system. Also added filtering of all-zero bboxes before merging.
