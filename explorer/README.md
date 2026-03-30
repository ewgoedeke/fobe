# FOBE Ontology Explorer

Interactive force-directed graph explorer for the FOBE financial ontology.
Split-pane UI: graph on the left, concept detail on the right.

## Quick start

```bash
# Install (one-time)
pip install fastapi uvicorn
cd explorer/frontend && npm install && npx vite build && cd ..

# Run
python explorer/server.py
# Open http://localhost:8787
```

## Development mode

```bash
# Terminal 1: API server
python explorer/server.py

# Terminal 2: Vite dev server (hot reload)
cd explorer/frontend && npm run dev
# Open http://localhost:5173 (proxies API to :8787)
```

## Interaction

- **Overview**: 31 context nodes (PNL, SFP, OCI, CFS, SOCIE + 26 disclosures)
- **Click** a context node → expands into individual concepts
- **Click again** → collapses back
- **Click** a concept → shows detail panel (metadata, relationships, ambiguities)
- **Double-click** a concept → neighborhood view (all directly connected concepts)
- **Drag** nodes to rearrange
- **Cmd+K** → search concepts by ID or label
- **Back to overview** → returns to collapsed context view

## API

| Endpoint | Description |
|---|---|
| `GET /api/overview` | Collapsed context nodes + cross-context edges |
| `GET /api/expand/{context}` | Individual concepts within a context |
| `GET /api/neighborhood/{concept_id}?depth=1` | N-hop neighborhood of a concept |
| `GET /api/concept/{concept_id}` | Full metadata for a concept |
| `GET /api/search?q=revenue` | Fuzzy search by ID or label |
| `GET /api/stats` | Summary statistics |
