# Mapping Granularity — Account-Level vs Reporting-Line-Level

## The problem

Entity financial statements present aggregated reporting lines:
```
Sonstige Forderungen (§224 B.II.4):  245,000
```

But the underlying accounts map to different ontology concepts:
```
2200 Sonstige Forderungen       42,000 → FS.SFP.OTHER_NON_FINANCIAL_ASSETS
2300 Vorsteuer                  68,000 → FS.SFP.CURRENT_TAX_ASSETS
2410 KöSt-Vorauszahlungen     180,000 → FS.SFP.CURRENT_TAX_ASSETS
2250 Ford. gg. Gesellschafter   15,000 → FS.SFP.RELATED_PARTY_RECEIVABLES (IC!)
2500 Ford. gg. SV-Träger      -60,000 → FS.SFP.OTHER_NON_FINANCIAL_ASSETS
```

## Three input quality levels

### Level 1: Trial balance (best — account-level mapping)

Source: CSV/XLSX Saldenliste with individual account codes.

Each account maps to exactly one concept. Many-to-one is fine:
```
1100 Rohstoffe       → FS.SFP.INVENTORIES
1300 Hilfsstoffe     → FS.SFP.INVENTORIES  (many:1 — both map to same concept)
1400 Betriebsstoffe  → FS.SFP.INVENTORIES
```

One-to-many requires a split with allocation:
```
6300 Gesetzl. Sozialaufwand → 70% FS.PNL.STAFF_COSTS (production)
                             → 30% FS.PNL.ADMIN_EXPENSES (admin)
```

**Mapping happens once, carries forward forever.**
IC accounts are tagged at source — no guessing.
This is the ideal input for consolidation.

### Level 2: Detailed FS with notes (good — line-item mapping)

Source: PDF annual report with face statements + disclosure notes.

Each reporting line maps to one concept. Composite lines create information loss:
```
"Other receivables: 245,000" → FS.SFP.OTHER_NON_FINANCIAL_ASSETS

But the notes might reveal:
  Note 12: "Other receivables include tax receivables of 248,000
            and amounts due from related parties of 15,000"
```

The note disaggregation recovers some of the lost granularity.
Cross-referencing face → notes is critical (issue #542).

**Problem cases:**
- Composite lines with no note breakdown
- IC amounts hidden inside aggregate lines
- Tax positions netted with other items

### Level 3: Summary FS only (worst — limited mapping)

Source: abbreviated/simplified FS (e.g., small GmbH filing at Firmenbuch).

Many lines are aggregate with no sub-detail:
```
"Forderungen: 1,080,000"  → FS.SFP.TRADE_RECEIVABLES (best guess)
```

No trial balance, no notes. The mapping is lossy.
Confidence is LOW. Many concepts will have no data.

## How the ontology handles each level

### Level 1 (trial balance):
```
mapping_source: TRIAL_BALANCE
granularity: ACCOUNT_CODE
confidence: HIGH (deterministic from alias table)

Fact: (SFP, FS.SFP.CURRENT_TAX_ASSETS, entity, 2024-12-31, {}) → 248,000
Fact: (SFP, FS.SFP.RELATED_PARTY_RECEIVABLES, entity, 2024-12-31, {ic_entity: parent}) → 15,000
Fact: (SFP, FS.SFP.OTHER_NON_FINANCIAL_ASSETS, entity, 2024-12-31, {}) → -18,000
```

All three concepts populated. IC tagged at source. Balance equation works.

### Level 2 (detailed FS + notes):
```
mapping_source: FINANCIAL_STATEMENTS
granularity: REPORTING_LINE

Face tag:
  (SFP, FS.SFP.OTHER_NON_FINANCIAL_ASSETS, entity, 2024-12-31, {}) → 245,000
  confidence: MEDIUM
  composite: true

Note disaggregation (if found):
  (DISC.FIN_INST, FS.SFP.CURRENT_TAX_ASSETS, entity, 2024-12-31, {}) → 248,000
  (DISC.RELATED_PARTIES, FS.SFP.RELATED_PARTY_RECEIVABLES, entity, 2024-12-31, {}) → 15,000
  source: note cross-reference
```

Partial recovery. The face tag is composite; the note tags provide the split.
Losslessness check: note amounts should reconcile to face (245,000 = 248,000 + 15,000 - 18,000).

### Level 3 (summary FS):
```
mapping_source: SUMMARY_FINANCIAL_STATEMENTS
granularity: AGGREGATE_LINE

Face tag:
  (SFP, FS.SFP.TRADE_RECEIVABLES, entity, 2024-12-31, {}) → 1,080,000
  confidence: LOW
  composite: true
  unmapped_components: [tax_receivables, ic_receivables, other]
```

Low confidence. Many concepts missing. Consolidation will work but with
less granular elimination and validation.

## Composite line handling

When a tagged line is known to be composite (aggregates multiple concepts):

```yaml
tag:
  concept_id: FS.SFP.OTHER_NON_FINANCIAL_ASSETS
  amount: 245000
  composite: true
  known_components:
    - { concept: FS.SFP.CURRENT_TAX_ASSETS, amount: 248000, source: "note 12" }
    - { concept: FS.SFP.RELATED_PARTY_RECEIVABLES, amount: 15000, source: "note 12", ic: true }
  residual: -18000  # 245000 - 248000 - 15000
  residual_concept: FS.SFP.OTHER_NON_FINANCIAL_ASSETS
```

The `composite` flag tells the consolidation pipeline:
- This line contains mixed concepts
- Known components are extracted (usable for IC elimination, tax analysis)
- The residual stays in the primary concept
- A trial-balance-level import would replace this with account-level facts

## Recommendation for pack submission

The readiness gate should incentivise Level 1:

| Input level | Readiness state | Gate impact |
|---|---|---|
| Trial balance (Level 1) | READY | Full IC elimination, full validation |
| Detailed FS + notes (Level 2) | READY with warnings | Partial IC, note-dependent validation |
| Summary FS only (Level 3) | DRAFT / needs review | Manual IC identification required |

The `source_medium` provenance tag captures this:
- `csv` / `xlsx` → likely Level 1 (trial balance)
- `pdf_tagged` → likely Level 2 (full FS with notes)
- `pdf_raw` → likely Level 3 (summary only)
