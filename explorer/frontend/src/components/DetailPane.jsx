import React, { useState, useEffect } from 'react'

const EDGE_COLORS = {
  SUMMATION: '#94a3b8',
  CROSS_STATEMENT_TIE: '#3b82f6',
  DISAGGREGATION: '#a78bfa',
  NOTE_TO_FACE: '#64748b',
  IC_DECOMPOSITION: '#f97316',
}

const SEVERITY_COLORS = {
  ERROR: '#ef4444',
  WARNING: '#f59e0b',
  INFO: '#3b82f6',
}

export default function DetailPane({ selected, onNavigate, onClose }) {
  const [pages, setPages] = useState([])
  const [activeDoc, setActiveDoc] = useState(null) // { doc_id, page }
  const [documents, setDocuments] = useState([])
  const [showInfo, setShowInfo] = useState(true)

  // Load documents list once
  useEffect(() => {
    fetch('/api/documents').then(r => r.json()).then(d => setDocuments(d.documents || []))
  }, [])

  // When a concept is selected, fetch its page references
  useEffect(() => {
    if (selected?.type === 'concept' && selected.data?.id) {
      fetch(`/api/concept-pages/${selected.data.id}`)
        .then(r => r.json())
        .then(data => {
          setPages(data.pages || [])
          // Auto-open first page that has a PDF
          const firstWithPdf = (data.pages || []).find(p => {
            const doc = documents.find(d => d.id === p.doc_id)
            return doc?.has_pdf
          })
          if (firstWithPdf) {
            setActiveDoc({ doc_id: firstWithPdf.doc_id, page: firstWithPdf.page })
          } else {
            setActiveDoc(null)
          }
        })
    } else {
      setPages([])
      setActiveDoc(null)
    }
  }, [selected, documents])

  if (!selected) {
    return (
      <div style={styles.container}>
        <DocumentList documents={documents} onSelect={(doc) => setActiveDoc({ doc_id: doc.id, page: 1 })} />
      </div>
    )
  }

  const pdfUrl = activeDoc ? `/api/pdf/${activeDoc.doc_id}#page=${activeDoc.page || 1}` : null

  return (
    <div style={styles.container}>
      {/* Concept info header — collapsible */}
      <div style={styles.infoHeader}>
        <div style={styles.infoRow}>
          {selected.type === 'concept' && selected.data && (
            <>
              <span style={{ ...styles.badge, background: selected.data.color }}>{selected.data.context}</span>
              <span style={styles.conceptLabel}>{selected.data.label}</span>
              <span style={styles.conceptId}>{selected.data.id}</span>
            </>
          )}
          {selected.type === 'context' && (
            <>
              <span style={{ ...styles.badge, background: selected.data?.color }}>{selected.data?.label}</span>
              <span style={styles.conceptLabel}>{selected.data?.concept_count} concepts</span>
            </>
          )}
          {selected.type === 'edge' && (
            <>
              <span style={{ ...styles.badge, background: EDGE_COLORS[selected.data?.edge_type] || '#475569' }}>
                {(selected.data?.edge_type || '').replace(/_/g, ' ')}
              </span>
              <span style={styles.conceptLabel}>{selected.data?.edge_name}</span>
            </>
          )}
          <button style={styles.toggleBtn} onClick={() => setShowInfo(!showInfo)}>
            {showInfo ? '▾' : '▸'} info
          </button>
          <button style={styles.closeBtn} onClick={onClose}>&times;</button>
        </div>

        {showInfo && selected.type === 'concept' && selected.data && !selected.data.error && (
          <ConceptInfo data={selected.data} onNavigate={onNavigate} />
        )}

        {showInfo && selected.type === 'edge' && selected.data && (
          <EdgeInfo data={selected.data} onNavigate={onNavigate} />
        )}
      </div>

      {/* Page tabs — which documents/pages reference this concept */}
      {pages.length > 0 && (
        <div style={styles.pageTabs}>
          {pages.map((p, i) => {
            const doc = documents.find(d => d.id === p.doc_id)
            const isActive = activeDoc?.doc_id === p.doc_id && activeDoc?.page === p.page
            return (
              <button
                key={i}
                style={{
                  ...styles.pageTab,
                  ...(isActive ? styles.pageTabActive : {}),
                  opacity: doc?.has_pdf ? 1 : 0.4,
                }}
                onClick={() => doc?.has_pdf && setActiveDoc({ doc_id: p.doc_id, page: p.page })}
                title={`${p.doc_id} p.${p.page} — ${p.label}`}
              >
                <span style={styles.pageTabDoc}>{p.doc_id.replace(/_/g, ' ')}</span>
                <span style={styles.pageTabPage}>p.{p.page}</span>
              </button>
            )
          })}
        </div>
      )}

      {/* PDF viewer */}
      {pdfUrl ? (
        <iframe
          key={pdfUrl}
          src={pdfUrl}
          style={styles.pdfFrame}
          title="PDF Viewer"
        />
      ) : (
        <div style={styles.noPdf}>
          {pages.length > 0 ? (
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>📄</div>
              <div>No PDF available for this document</div>
              <div style={{ color: '#475569', fontSize: 12, marginTop: 4 }}>
                Tagged in {pages.length} location{pages.length > 1 ? 's' : ''}
              </div>
            </div>
          ) : selected.type === 'concept' ? (
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
              <div>No document references found</div>
              <div style={{ color: '#475569', fontSize: 12, marginTop: 4 }}>
                This concept hasn't been tagged in any fixture yet
              </div>
            </div>
          ) : (
            <DocumentList documents={documents} onSelect={(doc) => setActiveDoc({ doc_id: doc.id, page: 1 })} />
          )}
        </div>
      )}
    </div>
  )
}

function ConceptInfo({ data, onNavigate }) {
  return (
    <div style={styles.infoBody}>
      <div style={styles.infoGrid}>
        <span style={styles.infoKey}>Balance</span>
        <span style={{ color: data.balance_type === 'debit' ? '#22c55e' : '#ef4444' }}>
          {data.balance_type === 'debit' ? 'Dr+' : 'Cr-'}
        </span>
        <span style={styles.infoKey}>Unit</span>
        <span>{data.unit_type}</span>
        {data.is_total && (<><span style={styles.infoKey}>Role</span><span style={{ color: '#f59e0b' }}>TOTAL</span></>)}
      </div>

      {data.edges?.length > 0 && (
        <div style={styles.edgeList}>
          {data.edges.map((e, i) => (
            <span key={i} style={styles.edgeChip}>
              <span style={{ width: 6, height: 6, borderRadius: 3, background: EDGE_COLORS[e.edge_type] || '#475569', flexShrink: 0 }} />
              <span style={{ color: '#94a3b8', fontSize: 11 }}>{e.edge_type.replace(/_/g, ' ')}</span>
              {e.other_concepts.map((c, j) => (
                <span key={j} style={styles.infoLink} onClick={() => onNavigate(c)}>
                  {c.split('.').pop()}
                </span>
              ))}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function EdgeInfo({ data, onNavigate }) {
  const srcId = typeof data.source === 'object' ? data.source.id : data.source
  const tgtId = typeof data.target === 'object' ? data.target.id : data.target
  return (
    <div style={styles.infoBody}>
      <div style={styles.infoGrid}>
        <span style={styles.infoKey}>From</span>
        <span style={styles.infoLink} onClick={() => onNavigate(srcId)}>{srcId}</span>
        <span style={styles.infoKey}>To</span>
        <span style={styles.infoLink} onClick={() => onNavigate(tgtId)}>{tgtId}</span>
        {data.label && (<><span style={styles.infoKey}>Check</span><span>{data.label}</span></>)}
        {data.severity && (
          <><span style={styles.infoKey}>Severity</span>
          <span style={{ color: SEVERITY_COLORS[data.severity] || '#94a3b8' }}>{data.severity}</span></>
        )}
      </div>
      {data.ambiguities?.length > 0 && (
        <div style={{ marginTop: 4 }}>
          {data.ambiguities.map((a, i) => (
            <span key={i} style={{ ...styles.ambiguityTag }}>{a}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function DocumentList({ documents, onSelect }) {
  const withPdf = documents.filter(d => d.has_pdf)
  if (!withPdf.length) {
    return (
      <div style={styles.noPdf}>
        <div style={{ fontSize: 32, marginBottom: 8 }}>📊</div>
        <div>Select a concept to view its source document</div>
      </div>
    )
  }
  return (
    <div style={{ padding: 16 }}>
      <h3 style={styles.docListTitle}>Available Documents</h3>
      {withPdf.map(doc => (
        <div key={doc.id} style={styles.docItem} onClick={() => onSelect(doc)}>
          <span style={{ fontSize: 14 }}>📄</span>
          <div>
            <div style={{ fontSize: 13, color: '#e2e8f0' }}>{doc.name}</div>
            <div style={{ fontSize: 11, color: '#64748b' }}>
              {doc.tables} tables · {doc.tagged_concepts} tagged concepts
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

const styles = {
  container: {
    height: '100%', display: 'flex', flexDirection: 'column',
    background: '#0f172a', borderLeft: '1px solid #1e293b',
  },
  infoHeader: {
    background: '#1e293b', borderBottom: '1px solid #334155', flexShrink: 0,
  },
  infoRow: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
    minHeight: 32,
  },
  badge: {
    padding: '1px 8px', borderRadius: 8, fontSize: 11, fontWeight: 600, color: '#fff', flexShrink: 0,
  },
  conceptLabel: { fontSize: 13, fontWeight: 600, color: '#f1f5f9', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  conceptId: { fontSize: 10, color: '#64748b', fontFamily: 'monospace', flexShrink: 0 },
  toggleBtn: {
    marginLeft: 'auto', background: 'none', border: 'none', color: '#64748b',
    fontSize: 11, cursor: 'pointer', padding: '2px 6px', flexShrink: 0,
  },
  closeBtn: {
    background: 'none', border: 'none', color: '#64748b',
    fontSize: 16, cursor: 'pointer', padding: '0 4px', flexShrink: 0,
  },
  infoBody: { padding: '6px 12px 8px', },
  infoGrid: {
    display: 'grid', gridTemplateColumns: '70px 1fr', gap: '2px 8px',
    fontSize: 12, color: '#cbd5e1',
  },
  infoKey: { color: '#64748b' },
  infoLink: { color: '#3b82f6', cursor: 'pointer', fontSize: 11 },
  edgeList: {
    display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6,
  },
  edgeChip: {
    display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 6px',
    background: '#0f172a', borderRadius: 6, fontSize: 11,
  },
  ambiguityTag: {
    display: 'inline-block', padding: '1px 6px', borderRadius: 6,
    background: '#1e293b', border: '1px solid #f59e0b', color: '#f59e0b',
    fontSize: 10, marginRight: 4,
  },
  pageTabs: {
    display: 'flex', gap: 2, padding: '4px 8px', background: '#1e293b',
    borderBottom: '1px solid #334155', overflowX: 'auto', flexShrink: 0,
  },
  pageTab: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    padding: '3px 8px', borderRadius: 4, border: '1px solid #334155',
    background: '#0f172a', cursor: 'pointer', flexShrink: 0,
  },
  pageTabActive: { background: '#334155', borderColor: '#3b82f6' },
  pageTabDoc: { fontSize: 10, color: '#94a3b8', whiteSpace: 'nowrap' },
  pageTabPage: { fontSize: 11, color: '#e2e8f0', fontWeight: 600 },
  pdfFrame: {
    flex: 1, width: '100%', border: 'none', background: '#fff',
  },
  noPdf: {
    flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', color: '#64748b', fontSize: 13,
  },
  docListTitle: {
    fontSize: 12, fontWeight: 600, color: '#64748b', textTransform: 'uppercase',
    letterSpacing: 0.5, marginBottom: 8,
  },
  docItem: {
    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
    borderRadius: 6, cursor: 'pointer', marginBottom: 4,
    border: '1px solid #1e293b',
  },
}
