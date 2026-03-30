# LLM Tagger — Quality & Efficiency Review

Post-run review of the first full corpus pass (4,204 tags, 18.0% → 31.3% coverage).

---

## Tag Quality Issues

### 1. Note references tagged as financial data (high severity)

The LLM tags rows whose labels are note/standard references, not financial line items.

**kpmg_ifs_2025 examples** (SOCIE table — rows are IAS/IFRS citation columns, not row labels):
```
"IAS 1.106(b)"       → FS.SOCIE.BALANCE_RESTATED
"IAS 1.106(d)(i)"    → FS.SOCIE.PROFIT_FOR_PERIOD
"IFRS 13.6(a)"       → FS.SOCIE.OCI_FOR_PERIOD
```

**doco_2024 examples** (OCI table — rows are note number cross-references):
```
"5.1."  → FS.OCI.REMEASURE_DEFINED_BENEFIT
"5.2."  → FS.OCI.FVOCI_EQUITY_FV_CHANGE
"5.3."  → FS.OCI.REVALUATION_PPE
"5.16." → (similar)
```
Root cause: Docling extraction creates these tables with note references as row labels rather than actual OCI component names. The LLM assigns the *positionally correct* concept (5.1 appears where remeasurements usually are) but this is coincidental pattern-matching, not real tagging.

**Estimated bad tags from this issue: ~40-60 across corpus**

**Fix:** Pre-filter rows where label matches `/^\d+\.\d+\.?$|^(IAS|IFRS|AG)\s+\d+/i`. These are never taggable.

---

### 2. Date labels tagged (medium severity)

**evn_2024 examples:**
```
"30.09.2023" → FS.SOCIE.BALANCE_CLOSING
"30.09.2024" → FS.SOCIE.BALANCE_CLOSING
```
The concept is plausible (a closing balance row could have a date label in Austrian reporting), but the label is a column header that leaked into the row label, not a real row. These should be null.

**Fix:** Pre-filter labels matching `/^\d{1,2}\.\d{1,2}\.\d{4}$/`.

---

### 3. Empty or near-empty labels tagged (medium severity)

Rows with `label == ""` or `label == "(no label)"` receive tags. These are separator/spacer rows from the PDF extraction — they carry no semantic content.

Found across: andritz_ugb_2024, evn_2024, facc_2024, kpmg_ifs_2025, doco_2024.

**Estimated bad tags: ~44 across corpus**

**Fix:** In `_has_untagged_value_rows()` and prompt building, skip rows where `label.strip() in ("", "(no label)")`. Already shown in `_row_summary()` — just needs a skip condition before adding to `untagged_row_indices`.

---

### 4. Purely numeric labels tagged (low-medium severity)

**evn_2024 / kpmg examples:**
```
"61.6"  → DISC.BORROWINGS.TOTAL
"940"   → DISC.SEGMENTS.INTERSEGMENT_REVENUE
"127"   → DISC.SEGMENTS.TOTAL_LIABILITIES
"653"   → FS.SOCIE.PROFIT_FOR_PERIOD
```
These are partial cell values or page numbers that Docling placed in the label column. Numeric-only strings are never valid financial row labels.

**Fix:** Pre-filter labels matching `/^\d+[\.,]?\d*$|^\(\d+[\.,]?\d*\)$/`.

---

### 5. Generic "Total" rows in wrong contexts (low severity)

Bare `"Total"` labels get assigned to a specific concept even when the context is ambiguous:
```
"Total" → DISC.REVENUE.TOTAL_REVENUE  (could be any total in the table)
```
The LLM picks the most prominent concept in context, which is sometimes wrong.

**Fix:** The prompt rules already say "return null for generic labels unless the context makes it unambiguous" — the LLM isn't reliably following this. Consider adding it as a hard pre-filter: skip rows whose normalised label is in `_AMBIGUOUS_LABELS` (already defined in `check_consistency.py`).

---

### 6. SOCIE tables with note-reference-only row labels (structural issue)

Several SOCIE tables (especially kpmg_ifs_2025) have rows labelled only by note references like `"6.1."`, `"6.2."` etc. with no text label — these are tables where the column dimension carries the concept (each column = one equity component) and the rows are transactions. The LLM cannot reliably tag these without understanding column semantics.

**Recommendation:** For SOCIE tables where >50% of rows have note-ref or numeric labels, skip LLM tagging entirely — structural inference handles the important rows already.

---

## Process Inefficiencies

### 1. All rows sent in prompt, not just untagged ones (highest token waste)

`_build_table_prompt()` sends every row in the table (already-tagged + untagged + separators). Only untagged rows with values need the LLM's attention; already-tagged rows just provide structural context.

**Measured overhead:** ~55% of row lines in prompts are for already-tagged rows.

**Better approach:** Send only untagged rows in full, summarise already-tagged rows as a brief context block (e.g. "Previously tagged: row 1=COST_OPENING, row 6=COST_CLOSING"). This reduces prompt size by ~40-50% and allows larger batches within `MAX_PROMPT_CHARS`.

---

### 2. MAX_PROMPT_CHARS guard is reactive, not proactive

The current logic builds the full batch prompt *then* trims if over the limit. This means:
- For every oversized batch, one wasted `_build_batch_prompt()` call
- Single-table fallback still builds a large prompt for large tables with many concepts

**Better approach:** Estimate prompt size per table before batching (rows × ~60 chars + concepts × ~50 chars) and build batches up-front to fit within the limit.

---

### 3. Large tables processed one-per-call even when small in practice

A table with 31 rows (just over the 30-row threshold) triggers a solo API call. In practice many "large" tables have only 2-5 untagged rows — they could be batched.

**Better approach:** Use untagged row count, not total row count, as the batching criterion. A table with 40 total rows but only 3 untagged rows is effectively a small tagging job.

---

### 4. No intra-fixture concurrency

`tag_document()` processes all API calls sequentially within a fixture. For large fixtures (kpmg_ifs_2025: 99 eligible tables → ~35 API calls), this means ~35 serial round-trips. With 3 concurrent fixtures via `ThreadPoolExecutor`, the wall time is dominated by the slowest fixture's sequential chain.

**Better approach:** Collect all prompts for a fixture up-front, then dispatch them concurrently (e.g. `asyncio` with `max_workers` semaphore, or a second `ThreadPoolExecutor` inside `tag_document`). File write only happens once at the end regardless.

**Estimated wall-time improvement:** 3-5× for large fixtures.

---

### 5. Concept list includes cross-context concepts for OCI/SOCIE

The `valid_contexts` for some OCI concepts includes `PNL` entries (e.g. `FS.PNL.REVENUE` and `FS.PNL.NET_PROFIT` appear in the OCI concept list). This adds noise — the LLM should never assign a PNL concept to an OCI row.

**Root cause:** `_build_concept_index()` groups by every entry in `valid_contexts`. Some concepts have broad valid_contexts that span statement types.

**Recommendation:** When building the prompt for a table with `statementComponent=OCI`, restrict to concepts whose *primary* context (inferred from ID prefix) matches OCI, unless the concept explicitly lists OCI in `valid_contexts`.

---

### 6. No skip for fixtures already fully tagged

On re-runs, `_has_untagged_value_rows()` correctly skips already-tagged tables, but the fixture is still loaded and scanned. For the incremental use case (re-run after adding new concepts), a fast pre-check on `preTagged` density could skip loading large fixtures entirely.

---

## Summary Table

| Issue | Type | Estimated bad tags / waste | Fix difficulty |
|---|---|---|---|
| Note/standard references tagged | Quality | ~40-60 bad tags | Easy — regex pre-filter |
| Empty / "(no label)" rows tagged | Quality | ~44 bad tags | Easy — skip in prompt builder |
| Date labels tagged | Quality | ~10 bad tags | Easy — regex pre-filter |
| Numeric-only labels tagged | Quality | ~20 bad tags | Easy — regex pre-filter |
| Generic "Total" over-tagged | Quality | ~10 bad tags | Easy — extend ambiguous label list |
| SOCIE note-ref tables | Quality | Structural — skip whole table type | Medium |
| All rows in prompt (55% overhead) | Efficiency | ~40% prompt size reduction possible | Medium |
| Large table threshold uses total rows | Efficiency | ~86 extra solo API calls | Easy |
| No intra-fixture concurrency | Efficiency | 3-5× wall time on large fixtures | Hard |
| Reactive MAX_PROMPT_CHARS splitting | Efficiency | Minor extra work per oversized batch | Easy |
| Cross-context concepts in OCI/SOCIE | Quality | Noise, minor wrong assignments | Medium |

---

## Recommended Next Steps (prioritised)

1. **Add pre-filter in `_build_table_prompt()`** — skip rows where label is empty, numeric-only, date, or matches note-reference patterns. Quick win: eliminates ~120+ bad tags with 10 lines of code.

2. **Switch batching criterion to untagged row count** — use `sum(1 for r in rows if not r.get("preTagged"))` instead of `len(rows)` for the small/large split. Reduces solo API calls.

3. **Compress already-tagged rows in prompt** — replace full row descriptions of tagged rows with a compact summary. Halves prompt size for tables with rich existing coverage.

4. **Add intra-fixture concurrency** — parallelise API calls within `tag_document()`. Most impactful for large fixtures like kpmg_ifs (35 serial calls → ~8 with concurrency=5).

5. **Add SOCIE/note-ref table detection** — if >50% of untagged rows have labels matching note-ref patterns, skip the table (return empty dict, don't call LLM).
