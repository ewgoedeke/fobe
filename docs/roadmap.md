# FOBE Tagging Pipeline — Roadmap

## Milestone 1 — LLM Tagger (complete)

First full corpus pass using Claude Sonnet. Lifted structural coverage from 18% to 31.3% (4,204 new tags across 35 fixtures).

**Delivered:**
- `eval/llm_tagger.py` — batched prompting, context-filtered concept lists
- Pre-filters for untaggable rows (empty, numeric-only, dates, note refs, IAS/IFRS citations)
- `--strip-bad` flag for corpus cleanup
- Full corpus re-tag after pre-filter fix

---

## Milestone 2 — Gated pipeline (complete)

Implemented the 6-stage gated pipeline framework with quality gates between stages. If a gate fails, processing halts and findings are documented instead of propagating errors.

**Delivered:**
- [x] `eval/pipeline.py` — Framework (`GateResult`, `DocumentState`, `Pipeline`, `PipelineConfig`)
- [x] `eval/stages.py` — 6 stage implementations with `execute()` + `gate()` per stage
- [x] `eval/pipeline_runner.py` — CLI entry point
- [x] #36 fix: TOC poisoning — require ≥2 primary statement types, cap page-range propagation
- [x] #43 fix: Axis noise — expanded skip-lists for SEG (metrics, KPIs, totals), GEO (max length, negative keywords), PPE (movement labels, date headers)
- [x] #42 fix: GAAP filter — `_filter_by_gaap()` excludes `.UGB.` concepts for IFRS documents
- [x] `--pipeline` flag on `run_eval.py`

---

## Milestone 3 — Reclassification & threshold tuning (next)

Unblock the gated pipeline by fixing stale pre-baked classifications and tuning gate thresholds.

**Tasks:**
- [ ] #46: Add `--reclassify` flag — strip stale `statementComponent`, re-classify with TOC fix
- [ ] #47: Run full corpus with verbose gates, collect metric distributions, tune thresholds
- [ ] #48: Multipage table stitching — detect continuation tables, merge before hierarchy
- [ ] #49: Wire GAAP parameter through pipeline to LLM tagger

**Exit criterion:** ≥80% of docs with valid classifications pass all 6 gates; reclassified fixtures committed.

---

## Milestone 4 — LLM Tagger quality & efficiency

Fix the remaining issues identified in `LLM_TAGGER_REVIEW.md`.

**Quality fixes:**
- [ ] Compress already-tagged rows in prompt (~40% prompt size reduction)
- [ ] Switch batching criterion to untagged row count, not total row count
- [ ] SOCIE/note-ref table detection — skip if >50% of untagged rows are note-refs
- [ ] Extend `_AMBIGUOUS_LABELS` hard-filter for generic "Total" rows
- [ ] Cross-context OCI/SOCIE concept filtering

**Efficiency fixes:**
- [ ] Intra-fixture concurrency (`asyncio` or inner `ThreadPoolExecutor`)
- [ ] Proactive prompt size estimation before batching

**Exit criterion:** Bad tag rate below 1% on a held-out fixture set; wall time for full corpus re-tag below 10 minutes.

---

## Milestone 5 — Consistency validation across full corpus

Run `check_consistency.py` end-to-end on all fixtures and record `CONFIRMED` / `CONTRADICTED` / `UNCONFIRMED` scores per tag.

**Deliverables:**
- Per-fixture consistency report
- Corpus-level summary (coverage × corroboration matrix)
- `CONFIRMED` tag export — the gold-label dataset for Milestone 7

**Exit criterion:** At least 1,000 `CONFIRMED` tags across ≥10 fixtures, with corroboration scores computed for all tagged rows.

---

## Milestone 6 — Ontology stabilisation

No learning pipeline should be built against a moving target.

**Checklist:**
- [ ] All 26 DISC.* families have concepts, labels, and aliases defined
- [ ] `valid_contexts` is set correctly on all 581 concepts
- [ ] No concept additions planned within the next 2 corpus cycles
- [ ] Aliases cover the main EN + DE label variants for each concept

**Exit criterion:** Ontology passes a completeness check — all concepts in `constraints.yaml` exist in YAML files; no concepts in fixtures reference undefined IDs.

---

## Milestone 7 — Learning pipeline

**Readiness gate — all of the following must be true before starting:**

| Gate | Criterion | Measured by |
|---|---|---|
| Labeled data volume | ≥ 500 `CONFIRMED` tags per statement family (PNL, SFP, CFS, OCI, SOCIE) | Consistency report from M5 |
| Label space stability | No new core concept additions for ≥ 2 corpus cycles | Git log on `concepts/*.yaml` |
| Disclosure coverage | ≥ 5 `CONFIRMED` tags for each of the 26 DISC.* families | Consistency report from M5 |
| Quality baseline | Bad tag rate < 1% (from M4 exit criterion) | Held-out fixture audit |
| Eval split defined | ≥ 5 held-out fixtures (not used in training), covering IFRS + UGB | Manual designation |

**Planned architecture (subject to review at gate):**

1. **Semantic retrieval enhancement to `pretag_all.py`**
   - Replace SequenceMatcher fuzzy matching with multilingual sentence embedding
   - Index: all 581 concept labels + aliases (~966 entries, fits in memory)
   - Model: `paraphrase-multilingual-mpnet-base-v2` or `multilingual-e5-base`
   - Filter candidates by `valid_contexts` before ranking
   - Expected gain: structural coverage 18% → ~25%, fewer LLM calls

2. **Per-context encoder classifier (if labeled data volume is sufficient)**
   - One classifier per statement family (PNL, SFP, CFS, OCI, SOCIE, per-DISC family)
   - Fine-tuned sentence transformer head over ~20–60 classes per context
   - Training data: `CONFIRMED` tags from M5 + silver labels from LLM tagger
   - Train/test split: by document (not row) to prevent structural leakage
   - LLM fallback when classifier confidence < 0.6

3. **Active learning loop**
   - After each new fixture batch: identify low-confidence predictions
   - Consistency checker provides automatic quality gate (no annotation needed for high-confidence rows)
   - Human review queue: ~20–50 rows per document for uncertain cases
