# FOBE Fact Identity Model

## The 5-component fact identity

Every tagged financial fact has a unique identity composed of:

```
(context, concept_id, entity_id, period, axes) → one amount
```

| Component | What it answers | Examples |
|---|---|---|
| **context** | Where does this fact appear? | PNL, SFP, OCI, CFS, SOCIE, DISC.PPE, DISC.SEGMENTS, DISC.TAX |
| **concept_id** | What does the number mean? | FS.PNL.REVENUE, FS.SFP.CASH, DISC.PPE.COST_ADDITIONS |
| **entity_id** | Who does it relate to? | suedwerk_gmbh, nordtechnik_gmbh |
| **period** | When? (instant or duration) | 2024-12-31 (instant) or 2024-01-01..2024-12-31 (duration) |
| **axes** | How is it broken down? | AXIS.SEGMENT_DOC: SEG.001, AXIS.PPE_CLASS_DOC: PPEDOC.002 |

## Why context matters

The same economic reality (revenue = 1,200,000) legitimately appears in multiple places:

| Context | Concept | Axes | Amount |
|---|---|---|---|
| PNL | FS.PNL.REVENUE | — | 1,200,000 |
| DISC.SEGMENTS | DISC.SEGMENTS.EXTERNAL_REVENUE | SEG.001 | 680,000 |
| DISC.SEGMENTS | DISC.SEGMENTS.EXTERNAL_REVENUE | SEG.002 | 380,000 |
| DISC.SEGMENTS | DISC.SEGMENTS.EXTERNAL_REVENUE | SEG.003 | 140,000 |
| DISC.REVENUE | DISC.REVENUE.GOODS_TRANSFERRED_OVERTIME | — | 800,000 |
| DISC.REVENUE | DISC.REVENUE.GOODS_TRANSFERRED_POINT | — | 400,000 |

Without context, the segment revenue amounts would appear to violate uniqueness. With context, each is a distinct fact.

## Uniqueness constraint

```
For any (context, concept_id, entity_id, period_start, period_end, axes):
  there must be exactly ONE amount.
```

Violation = tagging error (duplicate tag, or same row tagged twice with identical identity).

## Disaggregation ties (context links)

Disaggregation relationships connect facts across contexts:

```
SUM(DISC.SEGMENTS context, DISC.SEGMENTS.EXTERNAL_REVENUE, by AXIS.SEGMENT_DOC)
  = PNL context, FS.PNL.REVENUE
```

```
SUM(DISC.REVENUE context, by timing axis)
  = PNL context, FS.PNL.REVENUE
```

These are defined in relations.yaml as note_links with type = disaggregation.

## Cross-statement ties (context-to-context)

```
PNL:    FS.PNL.NET_PROFIT           = SOCIE: FS.SOCIE.PROFIT_FOR_PERIOD
OCI:    FS.OCI.TOTAL_OCI            = SOCIE: FS.SOCIE.OCI_FOR_PERIOD
SOCIE:  FS.SOCIE.BALANCE_CLOSING    = SFP:   FS.SFP.TOTAL_EQUITY
CFS:    FS.CFS.CASH_CLOSING         = SFP:   FS.SFP.CASH
```

## Amount cross-referencing

When the same amount value appears in different contexts:
- **Expected**: face amount = note total (disaggregation tie)
- **Expected with scale**: face in TEUR = note in EUR (×1000 relationship)
- **Unexpected**: same amount, unrelated concepts → investigate
