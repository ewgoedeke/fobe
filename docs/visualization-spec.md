# FOBE Ontology Visualization Spec for Group Reporting

## Library Selection

| View | Primary | Supporting |
|---|---|---|
| Concept tree browser | Custom tree + react-window | @xyflow (graph toggle), cmdk (search) |
| Entity mapping dashboard | AG Grid Enterprise | Recharts (progress bars) |
| Cross-statement flow | @xyflow/react | Custom (variance panel) |
| Segment reporting | AG Grid | Recharts (geo treemap) |
| Losslessness dashboard | AG Grid (tables) | Tailwind cards (status) |
| Ontology diff | Custom (diff entries) | Recharts (breakdown bars) |

## 6 Views

### 1. Concept Tree Browser
- Left sidebar: statement/disclosure tabs with concept counts
- Center: collapsible tree following ontology hierarchy (summation edges = parent-child)
- Coverage mini-bars per concept: filled segments = entities with data
- Cmd+K search (cmdk): fuzzy match on concept_id + label + GAAP aliases
- Detail panel on click: metadata, relations, entity amounts, GAAP variants
- Optional graph toggle: switches subtree to @xyflow DAG

### 2. Entity Mapping Dashboard
- AG Grid matrix: ontology concepts (rows, tree-grouped) × entities (columns)
- Cell colors: green (confirmed), blue (auto-proposed), red (unmapped)
- Drill-through on click: source accounts, IC tags, mapping history
- Sigma check column: subtotal validation per concept
- Entity coverage footer: progress bars per entity
- Statement tabs filter concept rows

### 3. Cross-Statement Flow Diagram
- @xyflow/react with 5 fixed-position statement nodes (PNL, OCI, SOCIE, CFS, SFP)
- Animated flow edges with amounts: PNL→SOCIE→SFP, OCI→SOCIE→SFP, CFS→SFP
- Variance badges on edges (red if tie breaks)
- Entity filter dropdown
- Animate flows mode for audit walkthrough

### 4. Segment Reporting
- AG Grid matrix: concepts (rows) × segments (columns) + TOTAL
- Inline proportion bars per cell (% of row total)
- Reconciliation accordion: segment total + adjustments = consolidated
- Geographic treemap (Recharts)
- Entity-to-segment mapping list

### 5. Losslessness Dashboard
- 4 status cards: balance equation, cross-statement ties, amount x-ref, tag uniqueness
- Per-entity balance check table (Dr + Cr = 0)
- Cross-statement tie pairs with variance
- Amount cross-reference issues (expandable cards)
- Tag uniqueness violations

### 6. Ontology Diff (Version Comparison)
- Version selector (like git diff)
- Summary: added/removed/modified/affected mappings counts
- Statement breakdown bar (Recharts)
- Change entries with impact panels (affected entity mappings)
- Side-by-side summation tree diff
- Generate migration proposals action for removed concepts
