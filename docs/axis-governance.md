# Axis Governance — Preventing Axis Noise

## Problem

33 axes × 649 concepts = potential for overwhelming combinatorial explosion.
A tagger seeing 15 axis dropdowns per row will produce garbage.

## Solution: Three-tier axis visibility

### Tier 1: Inherited (never shown, always present)
These axes are set once at document or table level and inherited by every cell:
- `AXIS.CURRENCY` — from document_meta.presentation_currency
- `AXIS.UNIT` — from table metadata.detectedUnit
- `AXIS.PERIOD_KEY` — from column.detectedAxes
- `AXIS.PERIOD_RELATION` — from column (CURRENT/COMPARATIVE)
- `AXIS.TIME_TYPE` — from concept.period_type (instant/duration)
- `AXIS.PNL_FORMAT` — from document_meta.framework.pnl_format
- `AXIS.FUNCTIONAL_CURRENCY` — from entity metadata

**Rule: tagger never sees these. They're auto-populated.**

### Tier 2: Contextual (shown only when concept requires it)
These axes appear in the UI only for concepts in their `applicable_concepts` list:
- `AXIS.PPE_CLASS_DOC` — only for FS.SFP.PPE_NET, DISC.PPE.*
- `AXIS.SEGMENT_DOC` — only in DISC.SEGMENTS context
- `AXIS.MATURITY` — only for SFP concepts that have current/non-current split
- `AXIS.ECL_STAGE` — only for DISC.BANK.ECL_*
- `AXIS.FAIR_VALUE_LEVEL` — only for DISC.FAIR_VALUE.*
- `AXIS.SCOPE` — only when discontinued operations exist

**Rule: shown as optional badge. Tagger adds only if the row is a dimensional breakdown.**

### Tier 3: Policy (set once per entity per close, never per row)
Accounting policy axes don't vary row-by-row — they're entity-level elections:
- `AXIS.VALUATION_METHOD` — set on entity profile, applies to all inventory concepts
- `AXIS.MEASUREMENT_MODEL` — set per asset class (PPE: cost, Investment property: FV)
- `AXIS.DEPRECIATION_METHOD` — set per asset class
- `AXIS.GOODWILL_TREATMENT` — set per close (IFRS locked, UGB Wahlrecht)
- `AXIS.NCI_MEASUREMENT` — set per acquisition
- `AXIS.CONSOLIDATION_METHOD` — set per entity in control_intervals
- `AXIS.LEASE_TREATMENT` — set per entity (IFRS 16 or exempt)
- `AXIS.BORROWING_COSTS` — set per entity
- `AXIS.ACQUISITION_COST_TREATMENT` — set per close (framework-dependent)

**Rule: never shown in tagging UI. Set in close_policy_snapshot / entity metadata.
Inherited by all facts for that entity. Only surface when comparing across entities
(comparability warning).**

## Implementation

```yaml
axis_visibility:
  inherited:
    - AXIS.CURRENCY
    - AXIS.UNIT
    - AXIS.PERIOD_KEY
    - AXIS.PERIOD_RELATION
    - AXIS.TIME_TYPE
    - AXIS.PNL_FORMAT
    - AXIS.FUNCTIONAL_CURRENCY

  contextual:
    AXIS.SEGMENT_DOC:     { contexts: [DISC.SEGMENTS] }
    AXIS.GEOGRAPHY_DOC:   { contexts: [DISC.SEGMENTS] }
    AXIS.PPE_CLASS_DOC:   { contexts: [DISC.PPE], concepts: [FS.SFP.PPE_NET] }
    AXIS.PPE_CLASS_STD:   { contexts: [DISC.PPE], concepts: [FS.SFP.PPE_NET] }
    AXIS.INTANGIBLE_CLASS_STD: { contexts: [DISC.INTANGIBLES] }
    AXIS.PROVISION_TYPE_DOC: { contexts: [DISC.PROVISIONS] }
    AXIS.PROVISION_TYPE_STD: { contexts: [DISC.PROVISIONS] }
    AXIS.ENTITY_DOC:      { contexts: [DISC.ASSOCIATES, DISC.RELATED_PARTIES] }
    AXIS.MATURITY:        { concepts: [FS.SFP.LOANS_BORROWINGS, FS.SFP.LEASE_LIABILITIES, FS.SFP.PROVISIONS] }
    AXIS.MATURITY_BUCKET: { contexts: [DISC.BORROWINGS, DISC.UGB] }
    AXIS.FAIR_VALUE_LEVEL: { contexts: [DISC.FAIR_VALUE] }
    AXIS.ECL_STAGE:       { contexts: [DISC.BANK] }
    AXIS.SCOPE:           { trigger: "discontinued_operations_exist" }
    AXIS.FINANCIAL_INSTRUMENT_CLASSIFICATION: { contexts: [DISC.FIN_INST, DISC.BANK] }
    AXIS.INSURANCE_MEASUREMENT_MODEL: { contexts: [DISC.INS_REG] }

  policy:
    AXIS.VALUATION_METHOD:  { level: entity, concepts: [FS.SFP.INVENTORIES] }
    AXIS.MEASUREMENT_MODEL: { level: entity_asset_class }
    AXIS.DEPRECIATION_METHOD: { level: entity_asset_class }
    AXIS.GOODWILL_TREATMENT: { level: close, source: close_policy_snapshot }
    AXIS.NCI_MEASUREMENT:   { level: acquisition }
    AXIS.CONSOLIDATION_METHOD: { level: entity, source: control_intervals }
    AXIS.LEASE_TREATMENT:   { level: entity }
    AXIS.BORROWING_COSTS:   { level: entity }
    AXIS.ACQUISITION_COST_TREATMENT: { level: close, source: close_policy_snapshot }
    AXIS.REVENUE_RECOGNITION: { level: entity_contract_type }
    AXIS.INSURANCE_FINANCE_DISAGG: { level: entity }
```

## What the tagger sees

For a typical SFP row like "Trade receivables: 890,000":

```
Concept: FS.SFP.TRADE_RECEIVABLES
Amount: 890,000

Inherited (auto):     EUR | TEUR | PERK.001 | PREL.CURRENT | TIME.INSTANT
Contextual (hidden):  none (not a dimensional breakdown row)
Policy (hidden):      set on entity profile
```

For a PPE rollforward row like "Land and buildings — additions: 45,000":

```
Concept: DISC.PPE.COST_ADDITIONS
Amount: 45,000

Inherited (auto):     EUR | TEUR | PERK.001 | PREL.CURRENT | TIME.DURATION
Contextual (shown):   AXIS.PPE_CLASS_DOC: [PPEDOC.001 ▾] "Land and buildings"
Policy (hidden):      MEAS.COST_MODEL (set on entity)
```

For a segment revenue row like "Europe: 680,000":

```
Concept: DISC.SEGMENTS.EXTERNAL_REVENUE
Amount: 680,000

Inherited (auto):     EUR | TEUR | PERK.001 | PREL.CURRENT | TIME.DURATION
Contextual (shown):   AXIS.SEGMENT_DOC: [SEG.001 ▾] "Europe"
Policy (hidden):      none
```

## Result

Out of 33 axes:
- 7 are always auto-populated (tagger never sees them)
- ~12 are policy axes (set once per entity, never per row)
- ~14 are contextual (shown only for specific concepts/contexts)
- A typical row shows **0-2 axis dropdowns**, not 33
