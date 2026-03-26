# Structural Consistency Model

The FOBE consistency engine classifies every cross-table observation in a
tagged financial document using a three-pass detection model.

## Architecture

```
Document (table_graphs.json)
    │
    ▼
┌──────────────────────┐
│  Fact Indexer         │  Extract (context, concept, period) → amount
│  index_facts()       │  from preTagged rows across all tables
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐     ┌──────────────────────┐
│  Relationship Graph  │◄────│  counterparts.yaml   │
│  build_graph()       │     │  concepts/*.yaml     │
└──────────┬───────────┘     └──────────────────────┘
           │
    ┌──────┼──────┐
    │      │      │
    ▼      ▼      ▼
  Pass 1  Pass 2  Pass 3
```

## Pass 1: Validate Declared Relationships

Uses the ontology graph (counterparts.yaml + concept metadata) to check:

| Edge type | Source | Check |
|---|---|---|
| **SUMMATION** | `summation_trees` | parent = SUM(children) |
| **DISAGGREGATION** | `disaggregation_ties` + concept `disaggregation_targets` | face = SUM(details along axis) |
| **CROSS_STATEMENT_TIE** | `cross_statement_ties` | trigger amount = requires amount |
| **IC_DECOMPOSITION** | `ic_decomposition` | face = external + IC |

Results: `VALID_DISAGGREGATION`, `VALID_TIE`, `BROKEN_RELATIONSHIP`, `DECOMPOSITION_RESIDUAL`

**Same-table preference**: When a concept appears in multiple tables
(e.g., 10-year overview vs primary statement), the engine prefers the
primary statement (fewer value columns, classified as PNL/SFP/OCI/CFS/SOCIE).

**Tolerance**: 1 TEUR (1,000 EUR normalized) for rounding.

## Pass 2: Explain Known Mismatch Patterns

For cross-table observations not explained by Pass 1, checks against
`mismatch_patterns.yaml`:

| Pattern | Detects |
|---|---|
| `UNIT_SCALE` | Same amount at different scales (TEUR vs Mio) |
| `SHARE_COUNT_VS_MONETARY` | Note shows # shares, face shows EUR |
| `GROSS_VS_NET` | Face shows net, note shows gross cost |
| `ASSOCIATE_OWN_FIGURES` | Associate's own P&L/SFP figures (IAS 28) |
| `SEGMENT_COMPONENT` | Segment-level partial amount |
| `PERIOD_SUBSET` | Quarterly vs annual amount |
| `DISCONTINUED_OPS_ADJUSTMENT` | Continuing ops vs total |
| `GENERIC_LABEL_COLLISION` | "Other", "Total" match across tables (suppressed) |

Result: `EXPLAINED_MISMATCH` with pattern ID.

## Pass 3: Flag Unexplained Inconsistencies

Two checks:

1. **Context-concept validation** (preTagged facts): If a concept's
   `valid_contexts` list doesn't include the table's `statementComponent`,
   flag as `UNEXPLAINED_INCONSISTENCY`.

2. **Label-based classification** (all tables): Detect misclassified
   tables — e.g., OCI table with PNL-structure labels (revenue, EBITDA)
   indicates an IAS 28 associate summary or segment P&L.

Result: `UNEXPLAINED_INCONSISTENCY`

## Output Categories

| Category | Meaning | Action |
|---|---|---|
| `VALID_DISAGGREGATION` | Declared relationship holds | None |
| `VALID_TIE` | Cross-statement tie holds | None |
| `BROKEN_RELATIONSHIP` | Declared relationship fails | ERROR — investigate |
| `DECOMPOSITION_RESIDUAL` | face ≠ external + IC | WARNING — unexplained residual |
| `EXPLAINED_MISMATCH` | Known pattern explains difference | INFO — document |
| `UNEXPLAINED_INCONSISTENCY` | No relationship, no pattern | WARNING — investigate |

## Concept Enrichment

Key concepts in `concepts/*.yaml` are enriched with:

- `valid_contexts`: Which statement contexts this concept can appear in
- `unit_type`: `monetary`, `shares`, `per_share`, `percentage`, etc.
- `note_unit_type`: If different in note vs face (e.g., treasury shares)
- `has_ic_variant`: Whether IC decomposition applies
- `ic_concept`: The IC counterpart concept
- `disaggregation_targets`: Where this amount is broken down in notes
- `measurement_variants`: Cost model vs fair value model variants

## Usage

```bash
# Human-readable output
python3 eval/check_consistency.py <table_graphs.json>

# JSON output
python3 eval/check_consistency.py <table_graphs.json> --json

# Check against expected violations fixture
python3 eval/check_consistency.py <table_graphs.json> \
  --check eval/fixtures/wienerberger_2024/expected_violations.json

# Run as part of full evaluation suite
python3 eval/run_all.py <table_graphs.json>
```

## Evaluation Catalogue

`eval/catalogue.yaml` maintains a running registry of discovered issues
across all evaluated documents. Each entry records:

- The finding category and pattern
- Root cause analysis
- Resolution status
- Whether the finding is detectable with current preTagging coverage

Issues marked `NOT_YET_DETECTABLE` become regression tests once the
tagging pipeline is improved.

## Limitations

The engine can only validate relationships for concepts that are
**preTagged** in the document. Currently this covers:

- PNL face concepts (revenue, PBT, operating profit, etc.)
- SFP face concepts (PPE, investment property, equity, etc.)
- Some OCI, SOCIE, and CFS concepts

Not yet covered (requires improved preTagging):

- Segment-level disaggregation data
- Note rollforward details (PPE, intangibles, provisions)
- Share count vs monetary amounts in equity notes
- IC elimination figures

## Corroboration Scoring

Every indexed fact gets a per-fact confidence status based on how many
independent checks corroborate it:

| Status | Meaning | Criteria |
|---|---|---|
| **CONFIRMED** | High confidence | ≥2 independent checks pass |
| **CORROBORATED** | Medium confidence | Exactly 1 check passes |
| **UNCONFIRMED** | No signal | No checks testable (missing counterpart data) |
| **CONTRADICTED** | Investigation needed | ≥1 check fails with no explaining ambiguity |

### Check types that contribute to scoring

1. **Ontology checks** (Pass 1): summation, disaggregation, cross-statement
   tie, note-to-face, IC decomposition — each passing check adds one
   corroboration signal to every fact that participated.

2. **Table arithmetic** (Pass 0): for every row with `childIds` in the
   source data, checks that `parsedValue(parent) = SUM(parsedValue(children))`
   per VALUE column. No ontology needed — pure structural validation.
   When a passing arithmetic check involves an indexed fact (matched by
   `row_id`), both parent and child facts receive a `TABLE_ARITHMETIC`
   check result.

3. **Mismatch patterns** (Pass 2): explained mismatches (UNIT_SCALE,
   GROSS_VS_NET, etc.) are informational — they don't contradict a fact
   but they don't confirm it either.

### Scoring flow

```
Pass 0: Table arithmetic (structural, no ontology)
   ↓
Pass 1: Ontology relationship checks
   ↓
Pass 2: Mismatch pattern explanation
   ↓
Pass 3: Context/label validation
   ↓
Score: aggregate all CheckResults per fact → status
```

### Corpus example

```
Fact Scores            Wienerberger    VERBUND    voestalpine
  CONFIRMED                   32           0            28
  CORROBORATED               186          15           174
  UNCONFIRMED                 90         267            96
  CONTRADICTED                12           9            46
  Table arithmetic hits      224           0           208
```
