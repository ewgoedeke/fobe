import React, { useState, useEffect, useMemo, useRef } from 'react'
import { useTables } from '../api.js'

/**
 * Right pane: shows table images from source documents.
 * When a concept is selected, shows all tables where that concept is tagged
 * with the row label annotated on the image.
 * Toggle between Images view and Data (HTML table) view.
 */
export default function PdfPane({ documents, activeDoc, page, conceptPages, selected, onDocChange, onPageClick }) {
  const [viewMode, setViewMode] = useState('images') // 'images' | 'data'
  const highlightRef = useRef(null)

  const docsWithTables = useMemo(() =>
    (documents || []).filter(d => d.tagged_concepts > 0),
    [documents]
  )

  // Pages with images for the selected concept
  const pagesWithImages = useMemo(() =>
    (conceptPages || []).filter(p => p.image_url),
    [conceptPages]
  )

  // Determine which documents to load for data view
  const docsToShow = useMemo(() => {
    if (!selected || !conceptPages?.length) return activeDoc ? [activeDoc] : []
    const docIds = [...new Set(conceptPages.map(p => p.doc_id))]
    return docIds.filter(id => docsWithTables.find(d => d.id === id))
  }, [selected, conceptPages, activeDoc, docsWithTables])

  // Load tables for active doc (data view) — TanStack Query handles caching
  const primaryDocId = viewMode === 'data' && docsToShow.length > 0 ? docsToShow[0] : null
  const { data: primaryTables, isLoading: loading } = useTables(primaryDocId)

  // Build allTables map from query result
  const allTables = useMemo(() => {
    const map = {}
    if (primaryDocId && primaryTables) map[primaryDocId] = primaryTables
    return map
  }, [primaryDocId, primaryTables])

  // Scroll to first highlighted element
  useEffect(() => {
    const timer = setTimeout(() => {
      highlightRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }, 100)
    return () => clearTimeout(timer)
  }, [selected, viewMode])

  const selectedTag = selected?.id || ''

  return (
    <div style={styles.container}>
      {/* Toolbar */}
      <div style={styles.toolbar}>
        {selected && !selected.error ? (
          <div style={styles.selectionInfo}>
            <span style={{ ...styles.badge, background: selected.color }}>{selected.context}</span>
            <span style={styles.selLabel}>{selected.label}</span>
            <span style={styles.selCount}>
              {pagesWithImages.length > 0
                ? `${pagesWithImages.length} table image${pagesWithImages.length > 1 ? 's' : ''}`
                : `${conceptPages?.length || 0} tag${(conceptPages?.length || 0) !== 1 ? 's' : ''}`}
            </span>
          </div>
        ) : (
          <select
            style={styles.docSelect}
            value={activeDoc || ''}
            onChange={e => onDocChange(e.target.value)}
          >
            {docsWithTables.map(d => (
              <option key={d.id} value={d.id}>{d.name} ({d.tagged_concepts} tags)</option>
            ))}
          </select>
        )}
        <span style={{ flex: 1 }} />
        {/* View toggle */}
        <div style={styles.viewToggle}>
          <button
            style={{ ...styles.toggleBtn, ...(viewMode === 'images' ? styles.toggleActive : {}) }}
            onClick={() => setViewMode('images')}
          >Images</button>
          <button
            style={{ ...styles.toggleBtn, ...(viewMode === 'data' ? styles.toggleActive : {}) }}
            onClick={() => setViewMode('data')}
          >Data</button>
        </div>
      </div>

      {/* Content */}
      <div style={styles.scrollArea}>
        {viewMode === 'images'
          ? <ImagesView
              pagesWithImages={pagesWithImages}
              conceptPages={conceptPages || []}
              selected={selected}
              documents={documents}
              activeDoc={activeDoc}
              highlightRef={highlightRef}
            />
          : <DataView
              docsToShow={docsToShow}
              allTables={allTables}
              selectedTag={selectedTag}
              selected={selected}
              docsWithTables={docsWithTables}
              loading={loading}
              highlightRef={highlightRef}
            />
        }
      </div>
    </div>
  )
}

/* ── Images View ─────────────────────────────────────────── */
function ImagesView({ pagesWithImages, conceptPages, selected, documents, activeDoc, highlightRef }) {
  if (!selected) {
    return (
      <div style={styles.empty}>
        <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.3 }}>&#128196;</div>
        <div>Select a concept in the graph</div>
        <div style={{ fontSize: 12, color: '#475569', marginTop: 4 }}>
          Table images from source documents will appear here
        </div>
      </div>
    )
  }

  if (pagesWithImages.length === 0) {
    // No images — show text-only list of where the concept appears
    return (
      <div style={styles.empty}>
        <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.3 }}>&#128247;</div>
        <div>No table images available</div>
        {conceptPages.length > 0 && (
          <div style={{ fontSize: 12, color: '#475569', marginTop: 8, textAlign: 'center' }}>
            Tagged in {conceptPages.length} location{conceptPages.length > 1 ? 's' : ''}:
            {conceptPages.map((p, i) => (
              <div key={i} style={{ marginTop: 4, color: '#94a3b8' }}>
                {p.doc_id.replace(/_/g, ' ')} — "{p.label}"
              </div>
            ))}
          </div>
        )}
        <div style={{ fontSize: 11, color: '#475569', marginTop: 12 }}>
          Run: python3 eval/extract_table_images.py
        </div>
      </div>
    )
  }

  // Group images by doc_id
  const byDoc = {}
  pagesWithImages.forEach(p => {
    byDoc[p.doc_id] = byDoc[p.doc_id] || []
    byDoc[p.doc_id].push(p)
  })

  let isFirst = true

  return (
    <>
      {Object.entries(byDoc).map(([docId, pages]) => {
        const doc = (documents || []).find(d => d.id === docId)
        const docName = doc?.name || docId.replace(/_/g, ' ')

        return (
          <div key={docId}>
            <div style={styles.docHeader}>
              <span style={styles.docName}>{docName}</span>
            </div>
            {pages.map((p, i) => {
              const setRef = isFirst
              if (isFirst) isFirst = false
              return (
                <div key={i} style={styles.imageCard} ref={setRef ? highlightRef : null}>
                  {/* Annotation bar: shows what was tagged */}
                  <div style={styles.annotation}>
                    <span style={styles.annotCtx}>{p.context}</span>
                    <span style={styles.annotLabel}>"{p.label}"</span>
                    <span style={styles.annotTag}>→ {selected.id}</span>
                  </div>
                  {/* Table page image */}
                  <img
                    src={p.image_url}
                    alt={`${docName} — ${p.context} (page ${p.source_page})`}
                    style={styles.tableImage}
                    loading="lazy"
                  />
                </div>
              )
            })}
          </div>
        )
      })}
    </>
  )
}

/* ── Data View (HTML tables) ─────────────────────────────── */
function DataView({ docsToShow, allTables, selectedTag, selected, docsWithTables, loading, highlightRef }) {
  let firstHighlightDone = false

  if (loading) return <div style={styles.loading}>Loading tables...</div>

  if (docsToShow.length === 0) {
    return (
      <div style={styles.empty}>
        <div style={{ fontSize: 32, marginBottom: 8, opacity: 0.3 }}>&#9638;</div>
        <div>Select a concept to see tagged data</div>
      </div>
    )
  }

  return (
    <>
      {docsToShow.map(docId => {
        const tables = allTables[docId] || []
        const doc = docsWithTables.find(d => d.id === docId)
        const docName = doc?.name || docId
        const relevantTables = selected
          ? tables.filter(t => t.rows.some(r => r.tag === selectedTag))
          : tables
        if (relevantTables.length === 0 && selected) return null

        return (
          <div key={docId}>
            <div style={styles.docHeader}>
              <span style={styles.docName}>{docName}</span>
            </div>
            {relevantTables.map((table, ti) => (
              <div key={ti} style={styles.tableBlock}>
                <div style={styles.tableHeader}>
                  <span style={styles.tableCtx}>{table.context}</span>
                  <span style={styles.tableMeta}>{table.table_id}</span>
                </div>
                <table style={styles.table}>
                  <tbody>
                    {table.rows.map((row, ri) => {
                      const isTagged = !!row.tag
                      const isSelected = row.tag === selectedTag
                      const isSection = row.row_type === 'SECTION' || row.row_type === 'HEADER'
                      const isTotal = row.row_type === 'TOTAL' || row.label.toLowerCase().startsWith('total')
                      let ref = null
                      if (isSelected && !firstHighlightDone) { ref = highlightRef; firstHighlightDone = true }
                      return (
                        <tr key={ri} ref={ref} style={{
                          ...(isSelected ? styles.rowSelected : {}),
                          ...(isTagged && !isSelected ? styles.rowTagged : {}),
                          ...(isSection ? styles.rowSection : {}),
                        }}>
                          <td style={styles.tagCell}>
                            {isTagged && <span style={{ ...styles.tagDot, background: isSelected ? '#fbbf24' : '#3b82f6' }} title={row.tag} />}
                          </td>
                          <td style={{
                            ...styles.labelCell, paddingLeft: 8 + row.indent * 16,
                            fontWeight: (isSection || isTotal) ? 600 : 400,
                            color: isSection ? 'var(--page-text-muted)' : (isSelected ? '#fbbf24' : 'var(--page-text)'),
                          }}>{row.label}</td>
                          {row.cells.slice(1).map((cell, ci) => (
                            <td key={ci} style={{
                              ...styles.amountCell, fontWeight: isTotal ? 600 : 400,
                              color: cell.negative ? '#ef4444' : (isSelected ? '#fbbf24' : 'var(--page-text)'),
                            }}>{cell.text}</td>
                          ))}
                          <td style={styles.tagIdCell}>
                            {isTagged && <span style={{ ...styles.tagId, color: isSelected ? '#fbbf24' : 'var(--page-text-secondary)' }}>{row.tag.split('.').pop()}</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )
      })}
    </>
  )
}

const styles = {
  container: {
    height: '100%', display: 'flex', flexDirection: 'column',
    background: 'var(--page-bg)', borderLeft: '1px solid var(--page-bg-raised)',
  },
  toolbar: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
    background: 'var(--page-bg-raised)', borderBottom: '1px solid var(--page-border)',
    flexShrink: 0, minHeight: 36,
  },
  selectionInfo: {
    display: 'flex', alignItems: 'center', gap: 8, overflow: 'hidden', minWidth: 0,
  },
  badge: {
    padding: '1px 8px', borderRadius: 8, fontSize: 10, fontWeight: 600,
    color: '#fff', flexShrink: 0,
  },
  selLabel: {
    fontSize: 13, fontWeight: 600, color: 'var(--page-text)',
    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
  },
  selCount: { fontSize: 11, color: 'var(--page-text-secondary)', flexShrink: 0 },
  docSelect: {
    background: 'var(--page-input-bg)', border: '1px solid var(--page-border)', borderRadius: 4,
    color: 'var(--page-text)', padding: '3px 8px', fontSize: 12, maxWidth: 260, cursor: 'pointer',
  },
  viewToggle: {
    display: 'flex', border: '1px solid var(--page-border)', borderRadius: 4, overflow: 'hidden', flexShrink: 0,
  },
  toggleBtn: {
    background: 'var(--page-input-bg)', border: 'none', color: 'var(--page-text-secondary)', padding: '3px 10px',
    fontSize: 11, cursor: 'pointer',
  },
  toggleActive: { background: 'var(--page-border)', color: 'var(--page-text)' },
  scrollArea: { flex: 1, overflow: 'auto', padding: '0 0 20px' },
  loading: { padding: 20, textAlign: 'center', color: 'var(--page-text-secondary)' },
  empty: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', color: 'var(--page-text-secondary)', fontSize: 13, minHeight: 300,
  },
  // Image view
  docHeader: {
    display: 'flex', alignItems: 'center', gap: 6, padding: '12px 12px 4px',
    fontSize: 13, fontWeight: 600, color: 'var(--page-text-muted)',
  },
  docName: {},
  imageCard: {
    margin: '6px 10px', border: '1px solid var(--page-bg-raised)', borderRadius: 6, overflow: 'hidden',
    background: 'var(--page-bg-raised)',
  },
  annotation: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
    background: 'rgba(251,191,36,0.1)', borderBottom: '1px solid rgba(251,191,36,0.2)',
  },
  annotCtx: {
    padding: '1px 6px', borderRadius: 6, fontSize: 10, fontWeight: 600,
    background: 'var(--page-border)', color: 'var(--page-text-muted)',
  },
  annotLabel: { fontSize: 12, color: '#fbbf24', fontStyle: 'italic' },
  annotTag: { fontSize: 10, color: 'var(--page-text-secondary)', fontFamily: 'monospace' },
  tableImage: {
    width: '100%', display: 'block', background: '#fff',
  },
  // Data view
  tableBlock: {
    margin: '6px 10px 0', border: '1px solid var(--page-bg-raised)', borderRadius: 6, overflow: 'hidden',
  },
  tableHeader: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '4px 10px', background: 'var(--page-bg-raised)',
  },
  tableCtx: {
    padding: '1px 8px', borderRadius: 8, fontSize: 10, fontWeight: 600,
    background: 'var(--page-border)', color: 'var(--page-text-muted)',
  },
  tableMeta: { fontSize: 11, color: 'var(--page-text-secondary)' },
  table: { width: '100%', borderCollapse: 'collapse' },
  tagCell: { width: 14, padding: '2px 2px 2px 6px', verticalAlign: 'middle' },
  tagDot: { display: 'inline-block', width: 6, height: 6, borderRadius: 3 },
  labelCell: { padding: '3px 8px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 280 },
  amountCell: { padding: '3px 12px 3px 8px', textAlign: 'right', fontFamily: 'monospace', fontSize: 12, whiteSpace: 'nowrap' },
  tagIdCell: { padding: '3px 8px', width: 90 },
  tagId: { fontSize: 9, fontFamily: 'monospace' },
  rowSelected: { background: 'rgba(251,191,36,0.15)', borderTop: '1px solid rgba(251,191,36,0.3)', borderBottom: '1px solid rgba(251,191,36,0.3)' },
  rowTagged: { background: 'rgba(59,130,246,0.05)' },
  rowSection: { borderTop: '1px solid var(--page-bg-raised)' },
}
