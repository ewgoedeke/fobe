import React, { useState, useEffect, useRef, useCallback } from 'react'
import { Allotment } from 'allotment'
import PageWithOverlays from './PageWithOverlays.jsx'
import PageBrowserModal from './PageBrowserModal.jsx'

const TYPE_LABELS = {
  TOC: 'TOC',
  PNL: 'Income Statement (PNL)',
  SFP: 'Balance Sheet (SFP)',
  OCI: 'Other Comprehensive Income',
  CFS: 'Cash Flow Statement',
  SOCIE: 'Changes in Equity',
  NOTES: 'Notes',
  MANAGEMENT_REPORT: 'Management Report',
  AUDITOR_REPORT: 'Auditor Report',
  FRONT_MATTER: 'Front Matter',
  ESG: 'ESG / Sustainability',
  RISK_REPORT: 'Risk Report',
  CORPORATE_GOVERNANCE: 'Corporate Governance',
  UNCLASSIFIED: 'Unclassified',
}

// Priority order for sorting element types in dropdown
const TYPE_ORDER = ['PNL', 'SFP', 'OCI', 'CFS', 'SOCIE', 'TOC', 'NOTES',
  'MANAGEMENT_REPORT', 'AUDITOR_REPORT', 'FRONT_MATTER', 'ESG', 'RISK_REPORT',
  'CORPORATE_GOVERNANCE']

const GAAP_COLORS = { IFRS: '#059669', UGB: '#2563eb' }

export default function ElementBrowser({ onBack }) {
  const [data, setData] = useState(null)
  const [selectedType, setSelectedType] = useState('PNL')
  const [activeDocId, setActiveDocId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [editModal, setEditModal] = useState(null) // { docId, pageCount, pageDims, section }
  const docRefs = useRef({})

  const loadData = useCallback(() => {
    setLoading(true)
    fetch('/api/elements/browse')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const handleEditSection = useCallback((doc) => {
    // Find current section in ground truth for this type
    const section = {
      statement_type: selectedType,
      start_page: doc.pages[0] || 1,
      end_page: doc.pages[doc.pages.length - 1] || 1,
      label: '',
    }
    setEditModal({
      docId: doc.doc_id,
      pageCount: doc.page_count,
      pageDims: doc.page_dims,
      section,
    })
  }, [selectedType])

  const handleSaveSection = useCallback(async (updated) => {
    const { docId } = editModal
    // Load existing ground truth, update the section, save back
    const res = await fetch(`/api/annotate/${docId}/toc`)
    const existing = await res.json()
    const gt = existing.ground_truth || {
      version: 1, annotator: '', has_page_numbers: false,
      toc_table_id: null, toc_pages: [], sections: [],
      notes_start_page: null, notes_end_page: null, has_toc: true,
    }

    // Find and update or insert section for this type
    const sections = gt.sections || []
    const idx = sections.findIndex(s => s.statement_type === updated.statement_type)
    const newSection = {
      label: updated.label,
      statement_type: updated.statement_type,
      start_page: updated.start_page,
      end_page: updated.end_page,
      note_number: null,
      validated: true,
    }
    if (idx >= 0) {
      sections[idx] = newSection
    } else {
      sections.push(newSection)
    }
    gt.sections = sections
    gt.annotated_at = new Date().toISOString()

    await fetch(`/api/annotate/${docId}/toc`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(gt),
    })

    setEditModal(null)
    loadData() // Refresh data
  }, [editModal, loadData])

  const scrollToDoc = useCallback((docId) => {
    setActiveDocId(docId)
    const el = docRefs.current[docId]
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  const documents = data?.documents || []

  // Filter docs that have pages for selected type
  const docsWithType = documents.map(doc => {
    const el = doc.elements[selectedType]
    const pages = el?.pages || []
    const tables = el?.tables || []
    return { ...doc, pages, tables }
  })

  // Collect all element types found across documents with counts
  const typeCounts = {}
  for (const doc of documents) {
    for (const etype of Object.keys(doc.elements)) {
      const pages = doc.elements[etype]?.pages || []
      if (pages.length > 0) {
        typeCounts[etype] = (typeCounts[etype] || 0) + 1
      }
    }
  }

  // Build sorted element type list (known types first, then discovered DISC.* etc.)
  const allTypes = Object.keys(typeCounts)
  const sortedTypes = allTypes.sort((a, b) => {
    const ai = TYPE_ORDER.indexOf(a)
    const bi = TYPE_ORDER.indexOf(b)
    if (ai >= 0 && bi >= 0) return ai - bi
    if (ai >= 0) return -1
    if (bi >= 0) return 1
    return a.localeCompare(b)
  })

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#0f172a', color: '#e2e8f0' }}>
      {/* Header bar */}
      <div style={styles.topBar}>
        <button style={styles.backBtn} onClick={onBack}>&larr; Back</button>
        <span style={styles.title}>Element Browser</span>
        <select
          value={selectedType}
          onChange={e => setSelectedType(e.target.value)}
          style={styles.select}
        >
          {sortedTypes.map(t => (
            <option key={t} value={t}>
              {TYPE_LABELS[t] || t} ({typeCounts[t]} doc{typeCounts[t] !== 1 ? 's' : ''})
            </option>
          ))}
        </select>
        <span style={{ fontSize: 12, color: '#64748b', marginLeft: 'auto' }}>
          {documents.length} documents
        </span>
      </div>

      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>Loading...</div>
      ) : (
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <Allotment defaultSizes={[25, 75]}>
            {/* Left: Document list */}
            <Allotment.Pane minSize={200}>
              <div style={styles.docList}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Document</th>
                      <th style={styles.th}>GAAP</th>
                      <th style={styles.th}>Pages</th>
                      <th style={styles.th}>Tables</th>
                    </tr>
                  </thead>
                  <tbody>
                    {docsWithType.map(doc => {
                      const hasPages = doc.pages.length > 0
                      const isActive = doc.doc_id === activeDocId
                      return (
                        <tr
                          key={doc.doc_id}
                          onClick={() => hasPages && doc.has_pdf && scrollToDoc(doc.doc_id)}
                          style={{
                            cursor: hasPages && doc.has_pdf ? 'pointer' : 'default',
                            opacity: hasPages ? 1 : 0.4,
                            background: isActive ? '#1e293b' : 'transparent',
                          }}
                        >
                          <td style={styles.td}>
                            <span style={{ fontSize: 12 }}>{doc.doc_id}</span>
                          </td>
                          <td style={styles.td}>
                            <span style={{
                              ...styles.badge,
                              background: GAAP_COLORS[doc.gaap] || '#6b7280',
                            }}>
                              {doc.gaap}
                            </span>
                          </td>
                          <td style={{ ...styles.td, textAlign: 'right' }}>
                            {doc.pages.length || '-'}
                          </td>
                          <td style={{ ...styles.td, textAlign: 'right' }}>
                            {doc.tables.length || '-'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </Allotment.Pane>

            {/* Right: Page gallery */}
            <Allotment.Pane minSize={400}>
              <div style={styles.gallery}>
                {docsWithType.filter(d => d.pages.length > 0 && d.has_pdf).map(doc => (
                  <div
                    key={doc.doc_id}
                    ref={el => docRefs.current[doc.doc_id] = el}
                    style={styles.docSection}
                  >
                    {/* Document header */}
                    <div style={styles.docHeader}>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{doc.doc_id}</span>
                      <span style={{
                        ...styles.badge,
                        background: GAAP_COLORS[doc.gaap] || '#6b7280',
                        marginLeft: 8,
                      }}>
                        {doc.gaap}
                      </span>
                      <span style={{ fontSize: 11, color: '#64748b', marginLeft: 8 }}>
                        {doc.pages.length} page{doc.pages.length !== 1 ? 's' : ''}
                        {' '}&middot;{' '}
                        {doc.tables.length} table{doc.tables.length !== 1 ? 's' : ''}
                        {' '}&middot;{' '}
                        source: {doc.source}
                      </span>
                      <button
                        style={styles.editBtn}
                        onClick={(e) => { e.stopPropagation(); handleEditSection(doc) }}
                        title="Edit page range for this section"
                      >
                        Edit pages
                      </button>
                    </div>

                    {/* Pages grid */}
                    <div style={styles.pagesGrid}>
                      {doc.pages.map(pageNo => {
                        const dims = doc.page_dims[pageNo] || doc.page_dims[String(pageNo)]
                        // Show ALL Docling-detected tables on the page, not just type-filtered ones
                        const tablesOnPage = (doc.all_tables || []).filter(t => t.pageNo === pageNo)
                        return (
                          <div key={pageNo} style={styles.pageWrapper}>
                            <PageWithOverlays
                              docId={doc.doc_id}
                              pageNo={pageNo}
                              pageDims={dims}
                              tables={tablesOnPage}
                            />
                          </div>
                        )
                      })}
                    </div>
                  </div>
                ))}
                {docsWithType.filter(d => d.pages.length > 0 && d.has_pdf).length === 0 && (
                  <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
                    No pages found for {selectedType} across documents.
                  </div>
                )}
              </div>
            </Allotment.Pane>
          </Allotment>
        </div>
      )}

      {/* Page browser modal for editing section page ranges */}
      {editModal && (
        <PageBrowserModal
          docId={editModal.docId}
          pageCount={editModal.pageCount}
          pageDims={editModal.pageDims}
          currentSection={editModal.section}
          onSave={handleSaveSection}
          onClose={() => setEditModal(null)}
        />
      )}
    </div>
  )
}

const styles = {
  topBar: {
    display: 'flex', alignItems: 'center', gap: 12, padding: '6px 16px',
    background: '#1e293b', borderBottom: '1px solid #334155', flexShrink: 0,
    minHeight: 42,
  },
  backBtn: {
    background: '#334155', border: '1px solid #475569', borderRadius: 6,
    color: '#94a3b8', padding: '3px 10px', fontSize: 12, cursor: 'pointer',
  },
  title: { fontSize: 15, fontWeight: 700, color: '#94a3b8', whiteSpace: 'nowrap' },
  select: {
    background: '#334155', border: '1px solid #475569', borderRadius: 6,
    color: '#e2e8f0', padding: '4px 10px', fontSize: 13, cursor: 'pointer',
  },
  docList: {
    height: '100%', overflowY: 'auto', padding: 0,
    background: '#0f172a',
  },
  th: {
    textAlign: 'left', padding: '6px 8px', fontSize: 11, color: '#64748b',
    borderBottom: '1px solid #1e293b', position: 'sticky', top: 0,
    background: '#0f172a', fontWeight: 600,
  },
  td: {
    padding: '5px 8px', fontSize: 12, borderBottom: '1px solid #1e293b22',
    color: '#cbd5e1',
  },
  badge: {
    display: 'inline-block', padding: '1px 6px', borderRadius: 3,
    fontSize: 10, fontWeight: 600, color: '#fff',
  },
  gallery: {
    height: '100%', overflowY: 'auto', padding: 16,
    background: '#0f172a',
  },
  docSection: {
    marginBottom: 24, borderBottom: '1px solid #1e293b',
    paddingBottom: 16,
  },
  docHeader: {
    display: 'flex', alignItems: 'center', marginBottom: 12,
    padding: '6px 0', borderBottom: '1px solid #1e293b',
  },
  pagesGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
    gap: 12,
  },
  pageWrapper: {
    borderRadius: 4, overflow: 'hidden',
    border: '1px solid #1e293b',
  },
  editBtn: {
    background: '#334155', border: '1px solid #475569', borderRadius: 4,
    color: '#94a3b8', padding: '2px 8px', fontSize: 11, cursor: 'pointer',
    marginLeft: 'auto',
  },
}
