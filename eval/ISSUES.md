# Eval Issue Tracker

Running log of issues identified through eval runs, linked to GitHub issues and resolution actions.

## How to use
- Add findings as they surface in eval runs
- Update status as fixes land
- Reference the eval run and learnings file where the issue was first found

## Status key
- **OPEN** — identified, not yet fixed
- **IN PROGRESS** — fix underway
- **FIXED** — fix merged, awaiting re-eval
- **VERIFIED** — fix confirmed by subsequent eval run

---

## Pipeline — Classification

| # | Issue | Impact | GitHub | Found in | Status | Resolution |
|---|-------|--------|--------|----------|--------|------------|
| 1 | TOC single-entry poisoning: one keyword match classifies entire document as one statement type (Pierer=214/216 SFP) | HIGH | [#36](https://github.com/ewgoedeke/fobe/issues/36) | 27032026EVAL002 §4 | OPEN | Require >=2 distinct primary statements in TOC; add `--reclassify` flag |
| 2 | SOCIE under-classified: German column header keywords missing (50 found vs ~140 expected) | HIGH | [#37](https://github.com/ewgoedeke/fobe/issues/37) | 27032026EVAL002 §4 | OPEN | Extend DE/AT keywords; add row-label fallback; detect transposed layout |
| 3 | SFP/PNL counts inflated: 663 SFP, 179 PNL across 39 docs (expected ~80 each) | HIGH | [#36](https://github.com/ewgoedeke/fobe/issues/36), [#38](https://github.com/ewgoedeke/fobe/issues/38) | 27032026EVAL002 §4 | OPEN | Fix TOC poisoning (#36), reclassify (#38) |
| 4 | Structural signals not used for classification (keyword-only) | MED | [#34](https://github.com/ewgoedeke/fobe/issues/34) | 27032026EVAL002 §4 | OPEN | Add PNL cascade, SFP balance equation, CFS three-section sum checks |
| 5 | ML classifier proposed to replace/augment keyword rules | MED | [#35](https://github.com/ewgoedeke/fobe/issues/35) | 27032026EVAL002 §4 | OPEN | XGBoost on TF-IDF + structural features; document-level CV |
| 6 | Document reference graph not exploited (TOC, note refs, cross-references) | MED | [#40](https://github.com/ewgoedeke/fobe/issues/40) | 27032026EVAL002 target pipeline | OPEN | Build DocumentRefGraph from TOC + note columns; use for classification + tagging |

## Pipeline — Axis Extraction (meta.json)

| # | Issue | Impact | GitHub | Found in | Status | Resolution |
|---|-------|--------|--------|----------|--------|------------|
| 7 | SEG axis noise: metrics, periods, KPIs, headers stored as segments (AMAG 9/13 wrong) | HIGH | [#43](https://github.com/ewgoedeke/fobe/issues/43) | 27032026EVAL002 §1 | OPEN | Expand skip-list; split compound headers; cross-column arithmetic validation |
| 8 | GEO axis noise: paragraphs, KPIs, business segments stored as geographies (VIG 7/7, EVN 8/13 wrong) | HIGH | [#43](https://github.com/ewgoedeke/fobe/issues/43) | 27032026EVAL002 §2 | OPEN | Max length filter; geography whitelist; paragraph detection; source table restriction |
| 9 | PPE axis wrong content: movement labels instead of asset classes (EVN 0/22 real); totals included | HIGH | [#43](https://github.com/ewgoedeke/fobe/issues/43) | 27032026EVAL002 §3 | OPEN | Extract from column headers only; movement keyword filter; exclude totals |
| 10 | Period suffixes baked into axis labels ("Land | 2024\|25") | MED | [#43](https://github.com/ewgoedeke/fobe/issues/43) | 27032026EVAL002 §3 | OPEN | Strip period suffixes; deduplicate across periods |
| 11 | Line-break hyphens in labels ("Consoli- dation") | LOW | [#43](https://github.com/ewgoedeke/fobe/issues/43) | 27032026EVAL002 §6 | OPEN | Normalize with `re.sub(r'(\w)-\s+(\w)', r'\1\2', label)` |
| 12 | Industry misclassification (Agrana = OIL_GAS) | MED | [#44](https://github.com/ewgoedeke/fobe/issues/44) | 27032026EVAL002 §5 | OPEN | Review industry inference logic; validate against entity profiles |

## Pipeline — Tagging

| # | Issue | Impact | GitHub | Found in | Status | Resolution |
|---|-------|--------|--------|----------|--------|------------|
| 13 | LLM tagger ignores GAAP — UGB concepts offered for IFRS docs and vice versa | MED | [#42](https://github.com/ewgoedeke/fobe/issues/42) | 27032026EVAL002 §7 | OPEN | Filter concepts by document GAAP; allow `gaap` as list for dual-GAAP docs |
| 14 | structural_inference assigns primary-statement concepts inside DISC tables (DISC.TAX gets FS.SFP.PPE_NET) | MED | [#34](https://github.com/ewgoedeke/fobe/issues/34) | 27032026EVAL002 §4 | OPEN | Gate label-match tagging on statementComponent; skip primary concepts in DISC.* |
| 15 | Tagging scope not constrained by table context (all concepts available for all tables) | MED | — | 27032026EVAL002 target pipeline | OPEN | Constrain concept candidates by statementComponent + GAAP + note-reference |

## Pipeline — Infrastructure

| # | Issue | Impact | GitHub | Found in | Status | Resolution |
|---|-------|--------|--------|----------|--------|------------|
| 16 | No table corruption/quality detection — garbage tables processed blindly | HIGH | [#45](https://github.com/ewgoedeke/fobe/issues/45) | 27032026EVAL002 target pipeline | OPEN | Per-table quality score propagated through pipeline; skip suspect tables |
| 17 | No multipage table stitching | MED | — | 27032026EVAL002 target pipeline | OPEN | Detect continuation tables (same columns, next page); stitch before hierarchy |
| 18 | Structured eval run output | LOW | [#41](https://github.com/ewgoedeke/fobe/issues/41) | — | FIXED | `run_eval.py` produces timestamped per-document results |
| 19 | Corrupted fixtures locked in (already=N; continue) | HIGH | [#38](https://github.com/ewgoedeke/fobe/issues/38) | 27032026EVAL002 §4 | OPEN | Reclassify pierer_mobility, pierer_afr, flughafen_wien after #36 + #37 |

## Ontology

| # | Issue | Impact | GitHub | Found in | Status | Resolution |
|---|-------|--------|--------|----------|--------|------------|
| 20 | Missing disclosure concept families (see #18-#27) | MED | [#18](https://github.com/ewgoedeke/fobe/issues/18)–[#27](https://github.com/ewgoedeke/fobe/issues/27) | ontology gap analysis | OPEN | Expand DISC.*, add DISC.MEASURE, DISC.EBITDA, ESG namespace |

---

## Validation test subset

For validating pipeline changes without full corpus run, use these 8 documents (details in `runs/27032026EVAL002/learnings.md`):

`amag_2024`, `evn_2024`, `vig_holding_2024`, `pierer_mobility_2024`, `kapsch_2024`, `a1_group_A1_2024_tables_stitched`, `rbi_ugb_2024`, `lenzing_2025`

---

## Eval run history

| Run ID | Date | Documents | Key findings |
|--------|------|-----------|-------------|
| 27032026EVAL002 | 2026-03-27 | 39 | Axis noise (§1-3), SFP inflation (§4), industry (§5), GAAP filtering (§7), target pipeline |
