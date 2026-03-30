# FOBE — Framework for Ontology Building and Evaluation

Multi-GAAP financial concept taxonomy for tagging, validating, and consolidating
financial statements. Shared by [doc_tag](https://github.com/ewgoedeke/doc_tag)
(tagging) and [finparse-platform](https://github.com/ewgoedeke/finparse-platform)
(consolidation).

## Architecture

```
doc_tag (produces)  →  fobe (ontology)  ←  finparse-platform (consumes)
   tags PDFs/CSVs       concepts            consolidates entities
   expands ontology      axes                validates with relations
   grows aliases         relations           imports tagged data
   evaluates quality     aliases             generates SQL seeds
```

## Eval pipeline

6-stage pipeline for extracting, classifying, tagging, and validating financial tables from PDF annual reports.

```
STAGE 1: PDF → Docling → raw tables (table_graphs.json)
    ↓
STAGE 2: Structure extraction
    2a. TOC identification (page-reference patterns, multi-language)
    2b. Table classification (TOC-aware → keyword fallback → "unclassified")
    2c. Meta extraction (entity, GAAP, periods, axes — from classified tables only)
    ↓
STAGE 3: Numeric conversion (format normalization, scale detection)
    ↓
STAGE 4: Table structure extraction
    4a. Multipage table stitching
    4b. Row/column hierarchy (summation detection, total identification)
    4c. Axis member validation (hierarchy-informed)
    ↓
STAGE 5: Fact tagging (structure-aware, GAAP-constrained)
    5a. Label matching (pretag_all.py, scoped to context)
    5b. Structural inference (hierarchy + summation trees)
    5c. LLM tagging (Claude Sonnet, constrained concept set)
    ↓
STAGE 6: Validation & scoring
    Consistency checks, fact scoring, anomaly detection
```

See `eval/runs/27032026EVAL002/learnings.md` for the full target architecture and current gap analysis.

## Ontology coverage

| Layer | Count |
|---|---|
| Core concepts (PNL, SFP, OCI, CFS, SOCIE + 26 disclosure families) | 564 |
| UGB-specific concepts (§ 224/231 line items) | 42 |
| **Total concept IDs** | **606** |
| Label index entries (EN + DE + aliases) | 966 |
| EKR account → concept mappings (Austrian chart of accounts) | 127 |
| Counterpart edges (summation, disaggregation, ties, IC, note-to-face) | 23 |
| Mismatch patterns (unit scale, gross vs net, etc.) | 8 |

### Frameworks
- **IFRS** — full concept coverage, validated against 4 ATX companies + KPMG IFS
- **UGB** (Austrian) — 42 concepts, 48 labels with § references, validated against EuroTeleSites + CA Immo
- **HGB** (German) — labels mapped, not yet validated

### Industry extensions
- Banking (IFRS 9/7, Basel III) — 46 concepts, PDF ready (ICBC Austria)
- Insurance (IFRS 17, VAG) — 39 concepts, PDF ready (VIG Holding)

## Structural Consistency Engine

Three-pass checker that classifies every cross-table observation:

| Pass | What | Output |
|---|---|---|
| **Pass 0** | Table arithmetic — parent/child row summations | CONFIRMED / CONTRADICTED |
| **Pass 1** | Ontology relationship validation | VALID_DISAGGREGATION, VALID_TIE, BROKEN, IC_LEAKAGE |
| **Pass 2** | Mismatch pattern explanation | EXPLAINED_MISMATCH (unit scale, gross/net, etc.) |
| **Pass 3** | Context-concept + label validation | UNEXPLAINED_INCONSISTENCY |

### Per-fact corroboration scoring

Every indexed fact gets a confidence status:
- **CONFIRMED** — ≥2 independent checks pass
- **CORROBORATED** — 1 check passes
- **UNCONFIRMED** — no checks testable
- **CONTRADICTED** — ≥1 unexplained failure

### Sign normalization

Documents declare source sign convention (`signConvention: PRESENTATION` or `NATURAL_DRCR`).
The engine normalizes to Dr+/Cr- during fact indexing using `concept.balance_type`.
Context-aware: PNL negates all amounts, SFP negates credit concepts only.

## Evaluation corpus

**39 documents, 6,342 tables, 44,226 data rows** — parsed via Docling into `table_graphs.json`
fixtures. Each fixture runs through the full pipeline for classification, tagging, and validation.

Latest eval run: `27032026EVAL002` (2026-03-27) — see `eval/runs/` for results.

### Validation test subset (8 documents)

For quick pipeline validation without running the full corpus:

| Document | GAAP | Lang | Sector | Tables | Covers |
|---|---|---|---|---|---|
| amag_2024 | UGB | DE | Manufacturing | 246 | SEG/GEO noise |
| evn_2024 | IFRS | DE | Utilities | 189 | PPE axis errors, GEO paragraphs |
| vig_holding_2024 | UGB | DE | Insurance | 20 | GEO all wrong; smallest doc |
| pierer_mobility_2024 | IFRS | EN/DE | Manufacturing | 216 | SFP overclassification |
| kapsch_2024 | IFRS | EN | Technology | 205 | Compound headers; good baseline |
| a1_group (stitched) | IFRS | DE | Telecom | 202 | Stitched table format |
| rbi_ugb_2024 | UGB | DE | Banking | 75 | Bank-specific; dual GAAP |
| lenzing_2025 | UGB | DE | Manufacturing | 322 | German totals; large doc |

### Real errors found

1. **Wienerberger IC leakage** — 909 TEUR intercompany revenue in 2023 comparative not eliminated, confirmed by tagged intersegment line
2. **Wienerberger OCI misclassification** — table classified as OCI contains PNL labels (IAS 28 associate summary)
3. **Wienerberger mistagging** — "Profit after tax" preTagged as GROSS_PROFIT in 10-year overview

## Directory layout

```
fobe/
├── ontology.yaml               # Master file — meta, imports
├── contexts.yaml               # Statement contexts (SFP, PNL, OCI, CFS, SOCIE, DISC.*)
├── concepts/
│   ├── sfp.yaml                # FS.SFP.* — 56 balance sheet concepts
│   ├── pnl.yaml                # FS.PNL.* — 44 income statement concepts
│   ├── oci.yaml                # FS.OCI.* — 22 OCI concepts
│   ├── cfs.yaml                # FS.CFS.* — 72 cash flow concepts
│   ├── socie.yaml              # FS.SOCIE.* — 34 changes in equity concepts
│   └── disc/                   # 26 disclosure families (336 concepts)
│       ├── ppe.yaml            # DISC.PPE.* — PPE rollforward
│       ├── segment.yaml        # DISC.SEGMENTS.* — IFRS 8 / § 237 UGB
│       ├── revenue.yaml        # DISC.REVENUE.* — IFRS 15
│       ├── tax.yaml            # DISC.TAX.* — income tax
│       └── ...                 # + 22 more families
├── axes.yaml                   # 33 dimension axes (STD + DOC dual-axis model)
├── counterparts.yaml           # Cross-statement ties, disaggregation, IC, note-to-face
├── constraints.yaml            # Context-concept rules, sign rules, anomaly detection
├── aliases.yaml                # 130+ label variants (EN + DE)
├── mismatch_patterns.yaml      # 8 known cross-table mismatch patterns
├── completeness.yaml           # 3-tier completeness graph
├── provenance.yaml             # 7 fact provenance types
├── document_meta.yaml          # Document metadata schema (sign convention, periods)
├── gaap/
│   ├── ifrs.yaml               # IFRS concept labels and references
│   ├── ugb.yaml                # UGB labels with § references + 42 UGB-specific concepts
│   └── hgb.yaml                # HGB labels
├── industry/
│   ├── banks.yaml              # Banking regulatory (46 concepts)
│   └── insurers.yaml           # Insurance regulatory (39 concepts)
├── accounts/
│   └── ekr_austria.yaml        # Austrian EKR chart of accounts (127 mappings)
├── eval/
│   ├── ISSUES.md               # Running issue tracker (findings → GitHub issues → status)
│   ├── classify_tables.py      # Table classification (TOC + keyword heuristics)
│   ├── table_classifier.py     # Keyword-based classification logic
│   ├── generate_document_meta.py # Meta extraction (entity, GAAP, periods, axes)
│   ├── pretag_all.py           # Label matching against ontology
│   ├── structural_inference.py # Hierarchy-based tag propagation (4 passes)
│   ├── llm_tagger.py           # LLM-assisted row tagging (Claude Sonnet)
│   ├── check_consistency.py    # Three-pass consistency checker
│   ├── check_classification.py # Table classification validator
│   ├── relationship_graph.py   # Ontology graph builder
│   ├── reference_graph.py      # Document reference graph (TOC, note refs)
│   ├── fact_scoring.py         # Per-fact corroboration scoring
│   ├── table_arithmetic.py     # Pass 0 — same-table parent/child validation
│   ├── run_eval.py             # Full pipeline runner → timestamped run folders
│   ├── run_corpus.py           # Cross-document comparison report
│   ├── run_all.py              # Single-document validation
│   ├── convert_isg.py          # ISG format → table_graphs.json converter
│   ├── convert_saldenliste.py  # EKR trial balance → UGB statements converter
│   ├── visualize.py            # Mermaid diagram generator
│   ├── catalogue.yaml          # Running regression test set
│   ├── fixtures/               # Per-document table_graphs.json (39 parsed)
│   └── runs/                   # Timestamped eval run results
│       └── 27032026EVAL002/    # Latest run (39 docs, per-doc results + learnings)
├── sources/
│   ├── kpmg/                   # KPMG reference PDFs (IFRS IFS, UGB, Banks, Insurers)
│   └── ugb/                    # Austrian UGB annual report PDFs
├── test_data/
│   └── sample_saldenliste_gmbh.csv  # Sample Austrian trial balance
└── docs/
    ├── consistency-model.md    # Three-pass model + corroboration scoring
    ├── diagram_full.md         # Cross-statement ties (Mermaid)
    ├── diagram_ppe.md          # PPE rollforward hierarchy (Mermaid)
    ├── diagram_revenue.md      # Revenue disaggregation (Mermaid)
    ├── fact-identity.md        # Fact identity model
    ├── axis-governance.md      # Three-tier axis visibility
    └── mapping-granularity.md  # Account-level vs reporting-line-level
```

## Running the evaluation

```bash
# Full pipeline run (all documents → timestamped results in eval/runs/)
python3 eval/run_eval.py

# Test subset only (8 documents covering all issue types)
python3 eval/run_eval.py --documents amag_2024 evn_2024 vig_holding_2024 \
    pierer_mobility_2024 kapsch_2024 a1_group_A1_2024_tables_stitched \
    rbi_ugb_2024 lenzing_2025

# Individual pipeline stages
python3 eval/classify_tables.py <table_graphs.json> [--reclassify] [--verbose]
python3 eval/pretag_all.py <table_graphs.json>
python3 eval/structural_inference.py <table_graphs.json> [--verbose]
python3 eval/llm_tagger.py <table_graphs.json> [--strip-bad]

# Consistency checks
python3 eval/check_consistency.py <table_graphs.json> [--json]

# Corpus comparison
python3 eval/run_corpus.py --all

# Visualize reporting hierarchies
python3 eval/visualize.py ppe | revenue | full

# Convert formats
python3 eval/convert_isg.py <isg_result.json> [output.json]
python3 eval/convert_saldenliste.py <saldenliste.csv> [output.json]
```

## Issue tracking

Open issues and their resolution status are tracked in `eval/ISSUES.md`. This maps eval run findings to GitHub issues with current status. See also `eval/runs/*/learnings.md` for per-run analysis.

## License

MIT
