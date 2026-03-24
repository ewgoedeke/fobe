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

## Directory layout

```
fobe/
├── ontology.yaml           # Master file — meta, imports
├── contexts.yaml           # Statement contexts (SFP, PNL, OCI, CFS, SOCIE, DISC.*)
├── concepts/
│   ├── sfp.yaml            # FS.SFP.* — balance sheet
│   ├── pnl.yaml            # FS.PNL.* — income statement
│   ├── oci.yaml            # FS.OCI.* — other comprehensive income
│   ├── cfs.yaml            # FS.CFS.* — cash flow statement
│   ├── socie.yaml          # FS.SOCIE.* — changes in equity
│   └── disc/
│       ├── ppe.yaml        # DISC.PPE.* — PPE disclosure
│       ├── fin_inst.yaml   # DISC.FIN_INST.* — financial instruments
│       ├── tax.yaml        # DISC.TAX.*
│       ├── leases.yaml     # DISC.LEASES.* — IFRS 16
│       └── segment.yaml    # DISC.SEGMENT.* — IFRS 8
├── axes.yaml               # Dimension axes (STD + DOC dual-axis model)
├── relations.yaml          # Calculation links, note links, cross-statement ties
├── aliases.yaml            # Multilingual label → concept_id lookup
├── gaap/
│   ├── ifrs.yaml           # IFRS labels, refs, presentation trees
│   ├── ugb.yaml            # UGB (Austrian) labels, refs
│   └── hgb.yaml            # HGB (German) labels, refs
├── industry/
│   ├── banks.yaml          # IFRS 9/7, Basel III concepts
│   └── insurers.yaml       # IFRS 17 concepts
├── eval/
│   ├── lossless.py         # Losslessness invariant checks
│   ├── cross_ref.py        # Amount cross-referencing, entity validation
│   └── comparability.py    # Cross-document consistency
└── build.py                # Generate SQL seeds for finparse-platform
```

## Concept naming convention

Namespaced IDs: `{family}.{statement}.{concept}`

```
FS.SFP.CASH_AND_EQUIVALENTS     # balance sheet concept
FS.PNL.REVENUE                   # income statement concept
FS.OCI.FX_TRANSLATION            # OCI concept
FS.CFS.NET_CASH_OPERATING        # cash flow concept
FS.SOCIE.DIVIDENDS_PAID          # changes in equity concept
DISC.PPE.PPE_GROSS               # disclosure concept
```

## Axis model (STD/DOC dual pattern)

- **STD axes**: normalized vocabulary (e.g., `PPESTD.LAND_BUILDINGS`)
- **DOC axes**: document-specific labels (e.g., `PPEDOC.001`)
- STD axes defined here; DOC axes defined per document in doc_tag

## Relation types

1. **Summation**: `total_assets = non_current_assets + current_assets`
2. **Division**: `eps_basic = profit_attr_owners / weighted_avg_shares`
3. **Cross-statement ties**: `pnl.net_profit == socie.net_profit`
4. **Disaggregation**: face amount = SUM(note detail along dimension)
5. **Reconciliation**: opening + movements = closing
6. **Derived metrics**: EBITDA, net debt, net debt/EBITDA

## Evaluation (losslessness invariants)

No dense ground truth needed — all checks are structural:

- Balance equation: SUM(SFP facts) = 0
- Tag uniqueness: (concept, entity, period, axes) → one amount
- Amount preservation: source amounts = tagged amounts
- Cross-statement ties: PNL↔SOCIE, CFS↔SFP, OCI↔SOCIE
- Amount cross-referencing: same value across tables must have consistent tags
- Period consistency: comparative[year N] = reported[year N-1]

## License

MIT
