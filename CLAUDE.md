# CLAUDE.md

## Project overview

FOBE (Framework for Ontology Building and Evaluation) is a multi-GAAP financial concept taxonomy for tagging, validating, and consolidating financial statements extracted from PDF annual reports.

## Key concepts

- **Ontology**: ~606 concept IDs across 5 primary statements (PNL, SFP, OCI, CFS, SOCIE) and 26 disclosure families (DISC.*)
- **GAAP**: supports IFRS, UGB (Austrian), HGB (German). Austrian IFRS reports often include UGB disclosures.
- **Axes**: dimensional model — segments (SEG), geographies (GEO), PPE classes (PPEDOC), periods (PERIOD)
- **table_graphs.json**: Docling-parsed table data with rows, columns, hierarchy (parentId/childIds), and metadata

## Eval pipeline (6 stages)

```
PDF → Docling → Structure extraction (TOC + classification + meta)
    → Numeric conversion → Table structure (hierarchy + multipage)
    → Fact tagging (GAAP + context-constrained) → Validation & scoring
```

Key files in order:
1. `eval/generate_document_meta.py` → meta.json
2. `eval/classify_tables.py` + `eval/table_classifier.py` → statementComponent per table
3. `eval/pretag_all.py` → label-matched row tags
4. `eval/structural_inference.py` → hierarchy-propagated tags (4 passes: top-down, bottom-up, cross-table, division)
5. `eval/llm_tagger.py` → LLM-inferred tags for untagged rows (Claude Sonnet)
6. `eval/check_consistency.py` → findings + fact scores

Entry point: `eval/run_eval.py` → writes results to `eval/runs/<run_id>/`

## Issue tracking

- `eval/ISSUES.md` — running tracker mapping findings to GitHub issues with status
- `eval/runs/*/learnings.md` — per-run analysis with root causes and plans
- GitHub issues — detailed specs and fix proposals

## Validation test subset

8 documents for quick pipeline validation (covers IFRS/UGB, DE/EN, all known issue types):
```
amag_2024, evn_2024, vig_holding_2024, pierer_mobility_2024,
kapsch_2024, a1_group_A1_2024_tables_stitched, rbi_ugb_2024, lenzing_2025
```

## Known open issues (see eval/ISSUES.md for full list)

- **#36**: TOC single-entry poisoning → entire document classified as one statement type
- **#43**: Axis member extraction captures noise (SEG, GEO, PPE axes contaminated)
- **#42**: LLM tagger ignores GAAP — UGB concepts offered for IFRS docs
- **#45**: No table corruption/quality detection — garbage processed blindly

## Reprocessing fixtures

All 63 eval fixtures need reprocessing to get cell-level bounding boxes (the original ingestion discarded them). Use:

```bash
# Check current bbox coverage
python3 eval/reprocess_fixtures.py --audit-only

# Reprocess all (requires: pip install docling)
python3 eval/reprocess_fixtures.py

# Reprocess specific fixtures
python3 eval/reprocess_fixtures.py --fixtures amag_2024 evn_2024
```

See `explorer/LEARNINGS.md` for full history of bbox bugs and fixes.

## Common commands

```bash
# Full eval run
python3 eval/run_eval.py

# Test subset
python3 eval/run_eval.py --documents amag_2024 evn_2024 vig_holding_2024 pierer_mobility_2024 kapsch_2024 a1_group_A1_2024_tables_stitched rbi_ugb_2024 lenzing_2025

# Classify + reclassify a single fixture
python3 eval/classify_tables.py eval/fixtures/<name>/table_graphs.json --reclassify --verbose

# LLM tag a fixture
python3 eval/llm_tagger.py eval/fixtures/<name>/table_graphs.json

# Consistency check
python3 eval/check_consistency.py eval/fixtures/<name>/table_graphs.json --json
```

## Ontology structure

```
concepts/          # Concept definitions by statement family
  sfp.yaml, pnl.yaml, oci.yaml, cfs.yaml, socie.yaml
  disc/            # 26 disclosure families (ppe, segment, revenue, tax, ...)
gaap/              # Framework-specific labels (ifrs.yaml, ugb.yaml, hgb.yaml)
industry/          # Sector extensions (banks.yaml, insurers.yaml)
counterparts.yaml  # Cross-statement relationships (summation, ties, IC)
axes.yaml          # 33 dimension axes (STD + DOC dual-axis model)
aliases.yaml       # 130+ label variants (EN + DE)
```

## Terminology

- **statementComponent**: the classification of a table (PNL, SFP, DISC.PPE, etc.)
- **preTagged**: concept tags assigned to rows (from label matching, structural inference, or LLM)
- **CONFIRMED/CORROBORATED/CONTRADICTED**: fact corroboration scores from consistency checks
- **DOC axis**: document-specific axis members (SEG.001, GEO.001, PPEDOC.001) extracted from the specific document
- **STD axis**: standard/ontology-defined axis members shared across all documents

## Bounding box coordinate systems

Two coordinate origins coexist in the pipeline — mixing them up causes visual misplacement:

- **Table-level bbox** (`table_graphs.json` top-level `bbox`): `[l, t, r, b]` in **BOTTOMLEFT** origin (standard PDF — y increases upward). Sourced from Docling's `prov[0].bbox`.
- **Row/cell bboxes** (`rows[].bbox`, `cells[].bbox`): `[l, t, r, b]` in **TOPLEFT** origin (screen/CSS — y increases downward). Sourced from Docling's `data.grid[r][c].bbox`.

The explorer frontend handles both via `pdfToCSS()` and `tlToCSS()` in `PageWithOverlays.jsx`.

## Docling ingestion

Upstream ingestion lives in `/tmp/doc_tag/` (or `~/work/doc_tag/`):
- `ingest_docling.py` — PDF → Docling JSON → `tables_raw.jsonl`
- `preprocess.py` — `tables_raw.jsonl` → `table_graphs.json`

The ingestion extracts from each Docling grid cell:
- **bbox**: `[l, t, r, b]` in TOPLEFT origin — row/column bboxes computed as unions
- **cell_meta**: `column_header`, `row_header`, `row_section` flags and `row_span`/`col_span` for merged cells

Batch processing: `bash eval/process_corpus.sh` (re-ingests all source PDFs with bbox verification).

See `explorer/LEARNINGS.md` for historical bugs in this pipeline.
