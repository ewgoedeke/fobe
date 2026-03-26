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

**30 PDFs, 22 companies, 16 industries** — parsed via Docling into `table_graphs.json`
fixtures. Each fixture runs through the consistency engine for tag corroboration.

### Parsed and evaluated (22 fixtures)

| Document | Tables | Rows | Framework | Industry |
|---|---|---|---|---|
| Wienerberger 2024 | 220 | 3000+ | IFRS | Building materials |
| KPMG IFRS IFS 2025 | 210 | 2305 | IFRS | Illustrative |
| Lenzing 2025 | 322 | 2953 | IFRS+UGB | Chemicals / fibres |
| Lenzing 2024 | 304 | 2979 | IFRS+UGB | Chemicals / fibres |
| Flughafen Wien 2024 | 291 | 2546 | IFRS+UGB | Airport |
| AGRANA 2024 | 217 | 2349 | IFRS+UGB | Food / sugar |
| AMAG 2024 | 246 | 1909 | IFRS+UGB | Aluminium |
| Kapsch TrafficCom 2024 | 205 | 2240 | IFRS+UGB | ITS |
| Frequentis 2024 | 199 | 1814 | IFRS+UGB | Defence tech / ATM |
| EVN 2024 | 189 | 1864 | IFRS+UGB | Energy / utilities |
| Mayr-Melnhof 2024 (full) | 186 | 1862 | IFRS+UGB | Packaging |
| FACC 2024 | 168 | 1296 | IFRS+UGB | Aerospace |
| DO & CO 2024 | 145 | 1393 | IFRS+UGB | Airline catering |
| Andritz UGB 2024 | 45 | 586 | **UGB** | Plant engineering |
| CA Immo 2024 (EN) | 38 | 360 | **UGB** | Real estate |
| ICBC Austria 2024 | 33 | 368 | **UGB+BWG** | Banking |
| Marinomed 2024 | 25 | 251 | IFRS+UGB | Pharma / biotech |
| BAWAG UGB 2024 | 20 | 157 | **UGB+BWG** | Banking |
| Mayr-Melnhof UGB 2024 | 15 | 158 | **UGB** | Packaging |
| Andritz 2024 | 10 | 51 | IFRS | Plant engineering |
| EuroTeleSites 2024 | 2 | 49 | **UGB** | Telecom infra |
| CA Immo 2024 (DE) | 2 | 81 | **UGB** | Real estate |
| Saldenliste GmbH | 2 | 44 | **UGB** | Test (EKR trial balance) |

### Awaiting Docling processing (11 PDFs)

| Company | Framework | Industry | UGB Einzelabschluss |
|---|---|---|---|
| **OMV** | UGB | Oil & gas | **separate PDF** |
| **STRABAG** | UGB | Construction | **separate PDF** |
| **RBI** | UGB+BWG | Banking | **separate PDF** |
| Palfinger | UGB | Cranes / lifting | bundled |
| Zumtobel | UGB | Lighting | bundled |
| Pierer Mobility | UGB | Motorcycles (KTM) | bundled |
| S IMMO | UGB | Real estate | bundled |
| Warimpex | UGB | Real estate / hotels | bundled |
| VIG Holding | UGB+VAG | Insurance | bundled |
| Wolford | UGB | Luxury textiles | bundled |
| Kapsch | UGB | ITS | bundled |

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
│   ├── check_consistency.py    # Three-pass consistency checker
│   ├── check_classification.py # Table classification validator
│   ├── relationship_graph.py   # Ontology graph builder
│   ├── fact_scoring.py         # Per-fact corroboration scoring
│   ├── table_arithmetic.py     # Pass 0 — same-table parent/child validation
│   ├── run_corpus.py           # Cross-document comparison report
│   ├── run_all.py              # Full evaluation suite
│   ├── convert_isg.py          # ISG format → table_graphs.json converter
│   ├── convert_saldenliste.py  # EKR trial balance → UGB statements converter
│   ├── visualize.py            # Mermaid diagram generator
│   ├── catalogue.yaml          # Running regression test set
│   ├── process_corpus.sh       # Batch PDF → Docling → fixtures pipeline
│   └── fixtures/               # Per-document table_graphs.json (22 parsed)
│       ├── wienerberger_2024/  # + agrana, amag, andritz, bawag, ca_immo,
│       ├── eurotelesites_2024/ #   doco, evn, facc, flughafen_wien,
│       ├── kpmg_ifs_2025/      #   frequentis, icbc_austria, kapsch,
│       ├── lenzing_2025/       #   lenzing, marinomed, mayr_melnhof
│       └── saldenliste_gmbh/
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
# Single document
python3 eval/check_consistency.py <table_graphs.json>
python3 eval/check_consistency.py <table_graphs.json> --json
python3 eval/check_consistency.py <table_graphs.json> --check eval/fixtures/.../expected_violations.json

# Corpus comparison
python3 eval/run_corpus.py --all

# Visualize reporting hierarchies
python3 eval/visualize.py ppe
python3 eval/visualize.py revenue
python3 eval/visualize.py full

# Convert formats
python3 eval/convert_isg.py <isg_result.json> [output.json]
python3 eval/convert_saldenliste.py <saldenliste.csv> [output.json]
```

## License

MIT
