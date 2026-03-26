# LLM Tagger Implementation Plan

## Goal

Tag the ~20K untagged rows (with values, in classified tables) using Claude Sonnet.
Target: 10.9% → 25-40% coverage.

## Architecture

New file: `eval/llm_tagger.py`

Pipeline position:
```
classify_tables.py → structural_inference.py → llm_tagger.py → check_consistency.py
```

## How it works

### Per-table prompting

For each table with untagged rows:

1. **Filter valid concepts** by `statementComponent` → only concepts whose `valid_contexts` includes this table's context. Typically 5-25 concepts per context.

2. **Build prompt** showing:
   - Table context (e.g., "DISC.PPE")
   - Valid concepts list with labels
   - All rows: already-tagged rows (for structural context) and untagged rows to classify

3. **LLM returns** JSON mapping row indices to concept IDs (or null for non-matchable rows like headers, axis members, generic "total").

### Sample prompt

```
You are tagging rows in a financial table.
Context: DISC.PPE (Property, plant and equipment rollforward)

Valid concepts:
  DISC.PPE.COST_OPENING: Cost — opening balance
  DISC.PPE.COST_ADDITIONS: Cost — additions
  DISC.PPE.COST_DISPOSALS: Cost — disposals
  DISC.PPE.COST_FX_EFFECT: Cost — effect of FX movements
  DISC.PPE.COST_CLOSING: Cost — closing balance
  DISC.PPE.ACCUM_DEPR_CHARGE: Accumulated depreciation — charge for year
  DISC.PPE.CARRYING_AMOUNT: Carrying amount (net)
  ... (19 total)

Table rows:
  row 0: "Cost" [SECTION, no values]
  row 1: "Balance at 1 January" [already tagged: DISC.PPE.COST_OPENING]
  row 2: "Additions" [UNTAGGED, has values]
  row 3: "Disposals" [UNTAGGED, has values]
  row 4: "Currency translation" [UNTAGGED, has values]
  row 5: "Reclassifications" [UNTAGGED, has values]
  row 6: "Balance at 31 December" [already tagged: DISC.PPE.COST_CLOSING]

For each UNTAGGED row, assign the best matching concept ID or null.
Respond with ONLY a JSON object: {"2": "DISC.PPE.COST_ADDITIONS", "3": "DISC.PPE.COST_DISPOSALS", ...}
```

### Batching strategy

- **Small tables (≤30 rows)**: batch 5 tables per API call
- **Large tables (>30 rows)**: 1 per call
- **Estimated ~800 API calls total** using Claude Sonnet
- Run with 5 concurrent requests for ~5 min total

### Key rules

1. **Only pick from valid concepts** — never invent IDs
2. **Return null for axis members** (country names, segment names, age brackets) — these need document_meta.json, not concept tagging
3. **Return null for generic labels** ("total", "other", "net") unless the context makes it unambiguous
4. **Return null for non-financial content** (page references, audit text)
5. **Trust existing tags** — don't re-tag already-tagged rows

### Output format

Write `preTagged` with:
```json
{
    "conceptId": "DISC.PPE.COST_ADDITIONS",
    "method": "llm",
    "confidence": 0.8,
    "rule": "sonnet_tag",
    "model": "claude-sonnet-4-20250514"
}
```

## Files to create/modify

| File | Change |
|------|--------|
| `eval/llm_tagger.py` | **New** — main script |
| `eval/run_all.py` | Add llm_tagger step (optional, gated on --llm) |

## CLI interface

```
python3 eval/llm_tagger.py <table_graphs.json> [--dry-run] [--verbose] [--model sonnet]
python3 eval/llm_tagger.py --all [--concurrency 5]
```

## Implementation steps (for Sonnet session)

1. Build concept index: load all concepts from `concepts/*.yaml`, group by `valid_contexts`
2. Implement `_build_table_prompt()` — formats one table for the LLM
3. Implement `_batch_tables()` — groups small tables into batches
4. Implement `_call_llm()` — calls Claude Sonnet via CLI or SDK
5. Implement `_parse_response()` — validates JSON, filters to valid concept IDs
6. Implement `tag_document()` — orchestrates the pipeline for one fixture
7. Implement `main()` with `--all` support and concurrency
8. Test on 3 fixtures, measure coverage
9. Run across full corpus

## Expected impact

- ~800 API calls × ~$0.003/call = ~$2.40 total cost
- ~5 min wall time with 5 concurrent
- Target: +8,000-15,000 tags → 25-40% coverage
