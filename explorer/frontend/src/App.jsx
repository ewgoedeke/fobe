import React, { useState, useCallback, useEffect, useRef } from 'react'
import { Allotment } from 'allotment'
import 'allotment/dist/style.css'
import GraphPane from './components/GraphPane.jsx'
import PdfPane from './components/PdfPane.jsx'
import SearchBar from './components/SearchBar.jsx'
import ConceptOverlay from './components/ConceptOverlay.jsx'
import ReviewPage from './components/ReviewPage.jsx'
import TocAnnotator from './components/TocAnnotator.jsx'
import ElementBrowser from './components/ElementBrowser.jsx'

const EDGE_TYPE_COLORS = {
  SUMMATION: '#94a3b8',
  CROSS_STATEMENT_TIE: '#3b82f6',
  DISAGGREGATION: '#a78bfa',
  NOTE_TO_FACE: '#64748b',
  IC_DECOMPOSITION: '#f97316',
}

export default function App() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [selected, setSelected] = useState(null) // concept detail from API
  const [history, setHistory] = useState([])
  const [stats, setStats] = useState(null)
  const [viewMode, setViewMode] = useState('overview')
  const [documents, setDocuments] = useState([])
  const [activeDoc, setActiveDoc] = useState(null) // doc_id
  const [pdfPage, setPdfPage] = useState(1)
  const [conceptPages, setConceptPages] = useState([]) // pages for selected concept
  const graphRef = useRef(null)

  // Load initial data
  useEffect(() => {
    fetch('/api/stats').then(r => r.json()).then(setStats)
    fetch('/api/documents').then(r => r.json()).then(data => {
      const docs = data.documents || []
      setDocuments(docs)
      // Auto-select first doc with PDF
      const first = docs.find(d => d.has_pdf)
      if (first) setActiveDoc(first.id)
    })
    loadOverview()
  }, [])

  const loadOverview = useCallback(async () => {
    const res = await fetch('/api/overview')
    const data = await res.json()
    setGraphData(data)
    setViewMode('overview')
    setHistory([{ label: 'Overview', action: () => loadOverview() }])
  }, [])

  // Show neighborhood of a concept — the primary drill-down
  const showNeighborhood = useCallback(async (conceptId, depth = 1) => {
    const res = await fetch(`/api/neighborhood/${conceptId}?depth=${depth}`)
    const data = await res.json()
    setGraphData(data)
    setViewMode('neighborhood')
    setHistory(prev => [
      ...prev.slice(0, 5),
      { label: conceptId.split('.').pop(), action: () => showNeighborhood(conceptId, depth) }
    ])
  }, [])

  // Select a concept — loads detail + finds PDF pages
  const selectConcept = useCallback(async (conceptId) => {
    const [detailRes, pagesRes] = await Promise.all([
      fetch(`/api/concept/${conceptId}`).then(r => r.json()),
      fetch(`/api/concept-pages/${conceptId}`).then(r => r.json()),
    ])
    setSelected(detailRes)
    const pages = pagesRes.pages || []
    setConceptPages(pages)

    // Auto-navigate PDF to the first matching page in the active document
    const match = pages.find(p => p.doc_id === activeDoc)
    if (match) {
      setPdfPage(match.page)
    } else if (pages.length > 0) {
      // Switch to a document that has this concept
      const docWithPdf = pages.find(p => documents.find(d => d.id === p.doc_id && d.has_pdf))
      if (docWithPdf) {
        setActiveDoc(docWithPdf.doc_id)
        setPdfPage(docWithPdf.page)
      }
    }
  }, [activeDoc, documents])

  // Handle node click
  const onNodeClick = useCallback((node) => {
    if (node.type === 'context') {
      // Clicking a context in overview → show its neighborhood of key concepts
      // Don't expand into the overview (too messy with 56 nodes)
      return
    }
    selectConcept(node.id)
  }, [selectConcept])

  // Double-click: neighborhood view + auto-select anchor concept
  const onNodeDblClick = useCallback((node) => {
    if (node.type === 'context') {
      const ctx = node.id.replace('ctx:', '')
      const anchor = ctx === 'PNL' ? 'FS.PNL.NET_PROFIT' :
                     ctx === 'SFP' ? 'FS.SFP.TOTAL_ASSETS' :
                     ctx === 'OCI' ? 'FS.OCI.TOTAL_COMPREHENSIVE_INCOME' :
                     ctx === 'CFS' ? 'FS.CFS.CASH_CLOSING' :
                     ctx === 'SOCIE' ? 'FS.SOCIE.TOTAL_EQUITY' :
                     null
      if (anchor) {
        showNeighborhood(anchor, 2)
        selectConcept(anchor)
      }
      return
    }
    showNeighborhood(node.id)
    selectConcept(node.id)
  }, [showNeighborhood, selectConcept])

  // Handle link click
  const onLinkClick = useCallback((link) => {
    // Select the target concept of the edge
    const tgtId = typeof link.target === 'object' ? link.target.id : link.target
    if (tgtId && !tgtId.startsWith('ctx:')) {
      selectConcept(tgtId)
    }
  }, [selectConcept])

  // Search result click
  const onSearchSelect = useCallback((result) => {
    showNeighborhood(result.id)
    selectConcept(result.id)
  }, [showNeighborhood, selectConcept])

  // Switch document
  const onDocChange = useCallback((docId) => {
    setActiveDoc(docId)
    // If current concept exists in this doc, navigate to its page
    if (selected) {
      const match = conceptPages.find(p => p.doc_id === docId)
      if (match) setPdfPage(match.page)
      else setPdfPage(1)
    }
  }, [selected, conceptPages])

  // Review mode
  if (viewMode === 'review') {
    return (
      <div style={{ height: '100vh' }}>
        <ReviewPage
          documents={documents}
          onBack={() => { setViewMode('overview'); loadOverview() }}
        />
      </div>
    )
  }

  // Annotate mode
  if (viewMode === 'annotate') {
    return (
      <div style={{ height: '100vh' }}>
        <TocAnnotator
          onBack={() => { setViewMode('overview'); loadOverview() }}
        />
      </div>
    )
  }

  // Elements browser mode
  if (viewMode === 'elements') {
    return (
      <div style={{ height: '100vh' }}>
        <ElementBrowser
          onBack={() => { setViewMode('overview'); loadOverview() }}
        />
      </div>
    )
  }

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Top bar */}
      <div style={styles.topBar}>
        <span style={styles.title}>FOBE Explorer</span>

        <div style={styles.breadcrumbs}>
          {history.map((h, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span style={{ color: '#475569', margin: '0 4px' }}>/</span>}
              <span
                style={{ ...styles.crumb, ...(i === history.length - 1 ? { color: '#e2e8f0' } : {}) }}
                onClick={h.action}
              >
                {h.label}
              </span>
            </React.Fragment>
          ))}
        </div>

        <SearchBar onSelect={onSearchSelect} />

        {viewMode === 'neighborhood' && (
          <button style={styles.btn} onClick={loadOverview}>Overview</button>
        )}

        <button style={styles.btn} onClick={() => setViewMode('review')}>Review</button>
        <button style={styles.btn} onClick={() => setViewMode('annotate')}>Annotate</button>
        <button style={styles.btn} onClick={() => setViewMode('elements')}>Elements</button>

        {stats && (
          <span style={styles.stats}>
            {stats.concepts} concepts &middot; {stats.edges} edges
          </span>
        )}
      </div>

      {/* Split pane: graph | PDF */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <Allotment defaultSizes={[50, 50]}>
          <Allotment.Pane minSize={300}>
            <div style={{ position: 'relative', width: '100%', height: '100%' }}>
              <GraphPane
                ref={graphRef}
                data={graphData}
                onNodeClick={onNodeClick}
                onNodeDblClick={onNodeDblClick}
                onLinkClick={onLinkClick}
                selectedId={selected?.id}
              />
              {/* Floating concept info overlay */}
              {selected && !selected.error && (
                <ConceptOverlay
                  data={selected}
                  pages={conceptPages}
                  activeDoc={activeDoc}
                  onNavigate={(cid) => { showNeighborhood(cid); selectConcept(cid) }}
                  onClose={() => { setSelected(null); setConceptPages([]) }}
                />
              )}
            </div>
          </Allotment.Pane>
          <Allotment.Pane minSize={300}>
            <PdfPane
              documents={documents}
              activeDoc={activeDoc}
              page={pdfPage}
              conceptPages={conceptPages}
              selected={selected}
              onDocChange={onDocChange}
              onPageClick={(docId, page) => { setActiveDoc(docId); setPdfPage(page) }}
            />
          </Allotment.Pane>
        </Allotment>
      </div>

      {/* Legend bar */}
      <div style={styles.legend}>
        {Object.entries(EDGE_TYPE_COLORS).map(([type, color]) => (
          <span key={type} style={styles.legendItem}>
            <span style={{ ...styles.legendSwatch, background: color }} />
            {type.replace(/_/g, ' ').toLowerCase()}
          </span>
        ))}
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 11, color: '#475569' }}>
          click to select &middot; double-click to explore
        </span>
      </div>
    </div>
  )
}

const styles = {
  topBar: {
    display: 'flex', alignItems: 'center', gap: 12, padding: '6px 16px',
    background: '#1e293b', borderBottom: '1px solid #334155', flexShrink: 0,
    minHeight: 42,
  },
  title: { fontSize: 15, fontWeight: 700, color: '#94a3b8', whiteSpace: 'nowrap' },
  breadcrumbs: { display: 'flex', alignItems: 'center', gap: 0 },
  crumb: { fontSize: 12, color: '#64748b', cursor: 'pointer' },
  btn: {
    background: '#334155', border: '1px solid #475569', borderRadius: 6,
    color: '#94a3b8', padding: '3px 10px', fontSize: 12, cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  stats: { fontSize: 11, color: '#475569', whiteSpace: 'nowrap', marginLeft: 'auto' },
  legend: {
    display: 'flex', alignItems: 'center', gap: 14, padding: '4px 16px',
    background: '#1e293b', borderTop: '1px solid #334155', flexShrink: 0,
  },
  legendItem: { display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: '#94a3b8' },
  legendSwatch: { width: 14, height: 3, borderRadius: 2 },
}
