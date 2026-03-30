import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Allotment } from 'allotment'
import { useReviewStatus, useReviewDoc } from '../api.js'

// Statement types for the classification dropdown
const STATEMENT_TYPES = [
  '', 'PNL', 'SFP', 'OCI', 'CFS', 'SOCIE',
  'DISC.PPE', 'DISC.INTANGIBLES', 'DISC.GOODWILL', 'DISC.LEASES',
  'DISC.SEGMENTS', 'DISC.REVENUE', 'DISC.TAX', 'DISC.EPS',
  'DISC.FIN_INST', 'DISC.FAIR_VALUE', 'DISC.BORROWINGS',
  'DISC.PROVISIONS', 'DISC.CONTINGENCIES', 'DISC.EMPLOYEE_BENEFITS',
  'DISC.SHARE_BASED', 'DISC.EQUITY', 'DISC.RELATED_PARTIES',
  'DISC.ASSOCIATES', 'DISC.NCI', 'DISC.CREDIT_RISK',
  'DISC.FX_RISK', 'DISC.HEDGE', 'DISC.IMPAIRMENT',
  'DISC.INVENTORIES', 'DISC.HELD_FOR_SALE', 'DISC.PERSONNEL',
  'DISC.AUDITOR', 'NOTES',
]

const METHOD_COLORS = {
  toc: '#22c55e',
  keyword: '#eab308',
  note_section: '#3b82f6',
  llm: '#a78bfa',
  human_review: '#f97316',
  unclassified: '#64748b',
  section_path: '#06b6d4',
}

const CONFIDENCE_BADGES = {
  high: { bg: '#166534', color: '#86efac' },
  medium: { bg: '#854d0e', color: '#fde047' },
  low: { bg: '#7f1d1d', color: '#fca5a5' },
  none: { bg: '#334155', color: '#94a3b8' },
}

export default function ReviewPage({ documents, onBack }) {
  const [activeDoc, setActiveDoc] = useState(null)
  const [overrides, setOverrides] = useState({}) // tableId -> statementComponent
  const [confirmedTables, setConfirmedTables] = useState(new Set())
  const [pageRanges, setPageRanges] = useState([])
  const [pdfPage, setPdfPage] = useState(1)
  const [filterMethod, setFilterMethod] = useState('all')
  const [filterFlagged, setFilterFlagged] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState('')
  const [bulkMode, setBulkMode] = useState(false)
  const [bulkSelection, setBulkSelection] = useState(new Set())
  const [bulkComponent, setBulkComponent] = useState('')
  const iframeRef = useRef(null)

  // Cached queries
  const { data: fixtures = [] } = useReviewStatus()
  const { data: reviewData } = useReviewDoc(activeDoc)

  const tables = reviewData?.tables || []
  const manifest = reviewData?.manifest || null

  // Apply loaded human review data when doc changes
  useEffect(() => {
    if (!reviewData) return
    const humanData = reviewData.human
    if (humanData?.exists) {
      const ovr = humanData.overrides || {}
      const tableOverrides = {}
      Object.entries(ovr.tables || {}).forEach(([tid, v]) => {
        tableOverrides[tid] = v.statementComponent
      })
      setOverrides(tableOverrides)
      setConfirmedTables(new Set(humanData.confirmed_tables || []))
      setPageRanges(ovr.page_ranges || [])
    } else {
      setOverrides({})
      setConfirmedTables(new Set())
      setPageRanges([])
    }
    setBulkSelection(new Set())
  }, [reviewData])

  // Navigate PDF to a page
  const goToPage = useCallback((page) => {
    setPdfPage(page)
  }, [])

  // Set override for a single table
  const setOverride = useCallback((tableId, value) => {
    setOverrides(prev => {
      const next = { ...prev }
      if (value === undefined) {
        delete next[tableId]
      } else {
        next[tableId] = value
      }
      return next
    })
  }, [])

  // Toggle confirm
  const toggleConfirm = useCallback((tableId) => {
    setConfirmedTables(prev => {
      const next = new Set(prev)
      if (next.has(tableId)) next.delete(tableId)
      else next.add(tableId)
      return next
    })
  }, [])

  // Bulk apply
  const applyBulk = useCallback(() => {
    if (bulkSelection.size === 0) return
    setOverrides(prev => {
      const next = { ...prev }
      bulkSelection.forEach(tid => {
        next[tid] = bulkComponent || null
      })
      return next
    })
    setBulkSelection(new Set())
    setBulkMode(false)
  }, [bulkSelection, bulkComponent])

  // Toggle bulk selection
  const toggleBulkSelect = useCallback((tableId) => {
    setBulkSelection(prev => {
      const next = new Set(prev)
      if (next.has(tableId)) next.delete(tableId)
      else next.add(tableId)
      return next
    })
  }, [])

  // Select all visible tables for bulk (defined after filteredTables below)
  const selectAllVisible = useCallback(() => {
    // Uses tables + filter state directly to avoid stale closure
    let result = tables
    if (filterMethod !== 'all') {
      result = result.filter(t => t.classification_method === filterMethod)
    }
    setBulkSelection(new Set(result.map(t => t.tableId)))
  }, [tables, filterMethod])

  // Save human_review.json
  const save = useCallback(async () => {
    if (!activeDoc) return
    setSaving(true)
    const tableOverrides = {}
    Object.entries(overrides).forEach(([tid, sc]) => {
      const table = tables.find(t => t.tableId === tid)
      const label = table?.first_labels?.[0] || ''
      tableOverrides[tid] = {
        statementComponent: sc,
        comment: `page ${table?.pageNo || '?'}: ${label.slice(0, 60)}`,
      }
    })
    const body = {
      version: 1,
      reviewed_at: new Date().toISOString(),
      reviewer: '',
      overrides: {
        tables: tableOverrides,
        page_ranges: pageRanges,
        patterns: [],
      },
      confirmed_tables: [...confirmedTables],
      gate_override: false,
    }
    try {
      const res = await fetch(`/api/review/${activeDoc}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      setSaveMsg(data.saved ? 'Saved' : 'Error: ' + (data.error || 'unknown'))
    } catch (e) {
      setSaveMsg('Error: ' + e.message)
    }
    setSaving(false)
    setTimeout(() => setSaveMsg(''), 3000)
  }, [activeDoc, overrides, confirmedTables, pageRanges, tables])

  // Filter tables
  const filteredTables = useMemo(() => {
    let result = tables
    if (filterMethod !== 'all') {
      result = result.filter(t => t.classification_method === filterMethod)
    }
    if (filterFlagged) {
      // Flagged = inflated primary types (>8 of same primary type)
      const primaryCounts = {}
      tables.forEach(t => {
        const sc = t.statementComponent
        if (['PNL', 'SFP', 'OCI', 'CFS', 'SOCIE'].includes(sc)) {
          primaryCounts[sc] = (primaryCounts[sc] || 0) + 1
        }
      })
      const inflated = new Set(Object.entries(primaryCounts)
        .filter(([, n]) => n > 8).map(([t]) => t))
      result = result.filter(t =>
        inflated.has(t.statementComponent) || !t.statementComponent
      )
    }
    return result
  }, [tables, filterMethod, filterFlagged])

  // Stats
  const stats = useMemo(() => {
    const methods = {}
    const types = {}
    tables.forEach(t => {
      methods[t.classification_method] = (methods[t.classification_method] || 0) + 1
      const sc = t.statementComponent || 'unclassified'
      types[sc] = (types[sc] || 0) + 1
    })
    return { methods, types, total: tables.length, overrideCount: Object.keys(overrides).length }
  }, [tables, overrides])

  // PDF URL with page anchor
  const pdfUrl = activeDoc ? `/api/pdf/${activeDoc}#page=${pdfPage}` : null

  // Document dashboard (when no doc is active)
  if (!activeDoc) {
    return (
      <div style={s.container}>
        <div style={s.header}>
          <button style={s.backBtn} onClick={onBack}>Back to Explorer</button>
          <span style={s.headerTitle}>Classification Review Dashboard</span>
          <span style={s.statsText}>{fixtures.length} documents</span>
        </div>
        <div style={s.tableContainer}>
          <table style={s.table}>
            <thead>
              <tr>
                <th style={{ ...s.th, width: 180 }}>Document</th>
                <th style={{ ...s.th, width: 50 }}>Tables</th>
                <th style={{ ...s.th, width: 60 }}>Pages</th>
                <th style={{ ...s.th, width: 50 }}>TOC</th>
                <th style={{ ...s.th, width: 160 }}>Primary Statements</th>
                <th style={{ ...s.th, width: 50 }}>DISC</th>
                <th style={{ ...s.th, width: 50 }}>Uncl.</th>
                <th style={{ ...s.th, width: 50 }}>Notes</th>
                <th style={{ ...s.th, width: 100 }}>Methods</th>
                <th style={{ ...s.th, width: 50 }}>GAAP</th>
                <th style={{ ...s.th, width: 70 }}>Industry</th>
                <th style={{ ...s.th, width: 80 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {fixtures.map(f => {
                const primary = f.primary_types || {}
                const primaryStr = Object.entries(primary)
                  .map(([t, n]) => {
                    const isInflated = n > 8
                    return { type: t, count: n, inflated: isInflated }
                  })
                const methods = f.methods || {}
                const topMethods = Object.entries(methods)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 3)

                return (
                  <tr
                    key={f.id}
                    className="hoverable-row"
                    style={{ cursor: 'pointer' }}
                    onClick={() => setActiveDoc(f.id)}
                  >
                    <td style={s.td}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ color: 'var(--page-text)', fontWeight: 500 }}>{f.id}</span>
                        {f.has_pdf && <span style={{ ...s.badgeInfo, fontSize: 9 }}>PDF</span>}
                      </div>
                      {f.entity && (
                        <div style={{ fontSize: 10, color: 'var(--page-text-secondary)' }}>{f.entity}</div>
                      )}
                    </td>
                    <td style={{ ...s.td, textAlign: 'center' }}>{f.total_tables}</td>
                    <td style={{ ...s.td, textAlign: 'center', fontSize: 11, color: 'var(--page-text-muted)' }}>
                      {f.page_range}
                    </td>
                    <td style={{ ...s.td, textAlign: 'center' }}>
                      {f.has_toc ? (
                        <span style={{ color: '#22c55e' }}>{f.toc_tables}</span>
                      ) : (
                        <span style={{ color: '#64748b' }}>-</span>
                      )}
                    </td>
                    <td style={s.td}>
                      <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
                        {primaryStr.map(p => (
                          <span
                            key={p.type}
                            style={{
                              fontSize: 10, padding: '1px 4px', borderRadius: 3,
                              background: p.inflated ? '#7f1d1d' : '#1e3a5f',
                              color: p.inflated ? '#fca5a5' : '#93c5fd',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {p.type}:{p.count}
                          </span>
                        ))}
                        {primaryStr.length === 0 && (
                          <span style={{ color: '#64748b', fontSize: 10 }}>none</span>
                        )}
                      </div>
                    </td>
                    <td style={{ ...s.td, textAlign: 'center', color: 'var(--page-text-muted)' }}>
                      {f.disc_types || '-'}
                    </td>
                    <td style={{ ...s.td, textAlign: 'center' }}>
                      <span style={{
                        color: f.unclassified > f.total_tables * 0.5 ? '#fca5a5' :
                               f.unclassified > 0 ? '#fde047' : '#86efac',
                      }}>
                        {f.unclassified}
                      </span>
                    </td>
                    <td style={{ ...s.td, textAlign: 'center' }}>
                      {f.total_note_refs > 0 ? (
                        <span style={{ color: '#22c55e' }}>{f.total_note_refs}</span>
                      ) : (
                        <span style={{ color: '#64748b' }}>-</span>
                      )}
                    </td>
                    <td style={s.td}>
                      <div style={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                        {topMethods.map(([m, n]) => (
                          <span
                            key={m}
                            style={{
                              fontSize: 9, padding: '0px 3px', borderRadius: 2,
                              background: METHOD_COLORS[m] || '#475569',
                              color: '#000', whiteSpace: 'nowrap',
                            }}
                          >
                            {m}:{n}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td style={{ ...s.td, textAlign: 'center', fontSize: 11 }}>
                      {f.gaap || '-'}
                    </td>
                    <td style={{ ...s.td, fontSize: 10, color: 'var(--page-text-muted)' }}>
                      {f.industry || '-'}
                    </td>
                    <td style={s.td}>
                      <div style={{ display: 'flex', gap: 3 }}>
                        {f.has_human_review && <span style={s.badgeSuccess}>reviewed</span>}
                        {f.has_manifest && !f.has_human_review && <span style={s.badgeWarning}>needs review</span>}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  return (
    <div style={s.container}>
      {/* Top bar */}
      <div style={s.header}>
        <button style={s.backBtn} onClick={onBack}>Explorer</button>
        <span style={{ color: 'var(--page-text-secondary)', margin: '0 4px' }}>/</span>
        <button style={s.backBtn} onClick={() => setActiveDoc(null)}>Review</button>
        <span style={{ color: 'var(--page-text-secondary)', margin: '0 4px' }}>/</span>
        <span style={s.headerTitle}>{activeDoc}</span>

        <div style={{ flex: 1 }} />

        {/* Filters */}
        <select
          style={s.select}
          value={filterMethod}
          onChange={e => setFilterMethod(e.target.value)}
        >
          <option value="all">All methods</option>
          {Object.keys(METHOD_COLORS).map(m => (
            <option key={m} value={m}>{m} ({stats.methods[m] || 0})</option>
          ))}
        </select>

        <label style={s.checkLabel}>
          <input
            type="checkbox"
            checked={filterFlagged}
            onChange={e => setFilterFlagged(e.target.checked)}
          />
          Flagged only
        </label>

        <button
          style={{ ...s.backBtn, background: bulkMode ? '#1d4ed8' : '#334155' }}
          onClick={() => { setBulkMode(!bulkMode); setBulkSelection(new Set()) }}
        >
          {bulkMode ? 'Exit bulk' : 'Bulk edit'}
        </button>

        {/* Stats */}
        <span style={s.statsText}>
          {filteredTables.length}/{stats.total} tables
          {stats.overrideCount > 0 && ` | ${stats.overrideCount} overrides`}
        </span>

        <button
          style={{ ...s.saveBtn, opacity: saving ? 0.5 : 1 }}
          onClick={save}
          disabled={saving}
        >
          {saving ? 'Saving...' : 'Save Review'}
        </button>
        {saveMsg && <span style={s.saveMsg}>{saveMsg}</span>}
      </div>

      {/* Bulk toolbar */}
      {bulkMode && (
        <div style={s.bulkBar}>
          <span style={{ color: '#94a3b8', fontSize: 12 }}>
            {bulkSelection.size} selected
          </span>
          <button style={s.backBtn} onClick={selectAllVisible}>Select all visible</button>
          <select style={s.select} value={bulkComponent} onChange={e => setBulkComponent(e.target.value)}>
            <option value="">Set to... (null = not a table)</option>
            {STATEMENT_TYPES.filter(t => t).map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <button style={s.saveBtn} onClick={applyBulk}>Apply to selected</button>
        </div>
      )}

      {/* Gate findings banner */}
      {manifest?.gate_findings?.length > 0 && (
        <div style={s.findingsBanner}>
          {manifest.gate_findings.map((f, i) => (
            <span key={i} style={s.finding}>
              {f.type}: {f.detail}
            </span>
          ))}
        </div>
      )}

      {/* Main split: table list | PDF */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <Allotment defaultSizes={[55, 45]}>
          {/* Left: classification table */}
          <Allotment.Pane minSize={400}>
            <div style={s.tableContainer}>
              <table style={s.table}>
                <thead>
                  <tr>
                    {bulkMode && <th style={s.th}>Sel</th>}
                    <th style={{ ...s.th, width: 40 }}>Page</th>
                    <th style={{ ...s.th, width: 90 }}>Table ID</th>
                    <th style={{ ...s.th, width: 130 }}>Classification</th>
                    <th style={{ ...s.th, width: 80 }}>Method</th>
                    <th style={{ ...s.th, width: 50 }}>Conf</th>
                    <th style={s.th}>Labels</th>
                    <th style={{ ...s.th, width: 80 }}>Override</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTables.map(t => {
                    const hasOverride = t.tableId in overrides
                    const isConfirmed = confirmedTables.has(t.tableId)
                    const isBulkSelected = bulkSelection.has(t.tableId)
                    const rowBg = hasOverride ? '#1e3a5f' :
                                  isConfirmed ? '#14532d' :
                                  isBulkSelected ? '#312e81' :
                                  'transparent'
                    return (
                      <tr key={t.tableId} style={{ background: rowBg }}>
                        {bulkMode && (
                          <td style={s.td}>
                            <input
                              type="checkbox"
                              checked={isBulkSelected}
                              onChange={() => toggleBulkSelect(t.tableId)}
                            />
                          </td>
                        )}
                        <td style={s.td}>
                          <button
                            style={s.pageBtn}
                            onClick={() => goToPage(t.pageNo)}
                            title="View in PDF"
                          >
                            {t.pageNo}
                          </button>
                        </td>
                        <td style={{ ...s.td, fontSize: 11, color: 'var(--page-text-muted)' }}>
                          {t.tableId}
                        </td>
                        <td style={s.td}>
                          <select
                            style={s.classSelect}
                            value={hasOverride ? (overrides[t.tableId] || '') : (t.statementComponent || '')}
                            onChange={e => {
                              const val = e.target.value === '' ? null : e.target.value
                              setOverride(t.tableId, val)
                            }}
                          >
                            <option value="">- unclassified -</option>
                            {STATEMENT_TYPES.filter(v => v).map(v => (
                              <option key={v} value={v}>{v}</option>
                            ))}
                          </select>
                        </td>
                        <td style={s.td}>
                          <span style={{
                            ...s.methodBadge,
                            background: METHOD_COLORS[t.classification_method] || '#475569',
                          }}>
                            {t.classification_method}
                          </span>
                        </td>
                        <td style={s.td}>
                          <span style={{
                            ...s.confBadge,
                            ...(CONFIDENCE_BADGES[t.classification_confidence] || CONFIDENCE_BADGES.none),
                          }}>
                            {t.classification_confidence}
                          </span>
                        </td>
                        <td style={{ ...s.td, fontSize: 12, maxWidth: 300 }}>
                          <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {t.first_labels?.[0] || '(no labels)'}
                          </div>
                          {t.col_headers?.length > 0 && (
                            <div style={{ fontSize: 10, color: 'var(--page-text-secondary)', marginTop: 1 }}>
                              cols: {t.col_headers.slice(0, 3).join(', ')}
                            </div>
                          )}
                        </td>
                        <td style={s.td}>
                          <div style={{ display: 'flex', gap: 2 }}>
                            <button
                              style={{
                                ...s.actionBtn,
                                background: isConfirmed ? '#166534' : '#334155',
                                color: isConfirmed ? '#86efac' : '#94a3b8',
                              }}
                              onClick={() => toggleConfirm(t.tableId)}
                              title={isConfirmed ? 'Unconfirm' : 'Confirm classification'}
                            >
                              {isConfirmed ? 'OK' : 'Cfm'}
                            </button>
                            {hasOverride && (
                              <button
                                style={{ ...s.actionBtn, background: '#7f1d1d', color: '#fca5a5' }}
                                onClick={() => setOverride(t.tableId, undefined)}
                                title="Remove override"
                              >
                                X
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </Allotment.Pane>

          {/* Right: PDF viewer */}
          <Allotment.Pane minSize={300}>
            <div style={s.pdfContainer}>
              {pdfUrl ? (
                <iframe
                  ref={iframeRef}
                  key={pdfUrl}
                  src={pdfUrl}
                  style={s.pdfIframe}
                  title="PDF Viewer"
                />
              ) : (
                <div style={s.noPdf}>
                  <p>No PDF available for this document</p>
                </div>
              )}
            </div>
          </Allotment.Pane>
        </Allotment>
      </div>

      {/* Bottom status bar */}
      <div style={s.statusBar}>
        <span>
          Classification: {Object.entries(stats.types)
            .sort(([, a], [, b]) => b - a)
            .slice(0, 8)
            .map(([t, n]) => `${t}:${n}`)
            .join('  ')}
        </span>
        <span style={{ flex: 1 }} />
        <span>PDF page: {pdfPage}</span>
      </div>
    </div>
  )
}


const s = {
  container: {
    height: '100%', display: 'flex', flexDirection: 'column',
    background: 'var(--page-bg)', color: 'var(--page-text)',
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  header: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '6px 12px',
    background: 'var(--page-bg-raised)', borderBottom: '1px solid var(--page-border)', flexShrink: 0,
    minHeight: 42, flexWrap: 'wrap',
  },
  headerTitle: { fontSize: 14, fontWeight: 600, color: 'var(--page-text)' },
  backBtn: {
    background: 'var(--page-border)', border: '1px solid var(--page-text-secondary)', borderRadius: 4,
    color: 'var(--page-text-muted)', padding: '3px 8px', fontSize: 12, cursor: 'pointer',
  },
  saveBtn: {
    background: '#1d4ed8', border: 'none', borderRadius: 4,
    color: '#fff', padding: '4px 12px', fontSize: 12, cursor: 'pointer',
    fontWeight: 600,
  },
  saveMsg: { fontSize: 11, color: '#86efac' },
  select: {
    background: 'var(--page-bg-raised)', border: '1px solid var(--page-text-secondary)', borderRadius: 4,
    color: 'var(--page-text)', padding: '3px 6px', fontSize: 12,
  },
  checkLabel: { fontSize: 12, color: 'var(--page-text-muted)', display: 'flex', alignItems: 'center', gap: 4 },
  statsText: { fontSize: 11, color: 'var(--page-text-secondary)', whiteSpace: 'nowrap' },
  bulkBar: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '4px 12px',
    background: '#312e81', borderBottom: '1px solid #4338ca', flexShrink: 0,
  },
  findingsBanner: {
    padding: '4px 12px', background: '#7f1d1d', borderBottom: '1px solid #991b1b',
    display: 'flex', flexWrap: 'wrap', gap: 8, flexShrink: 0,
  },
  finding: { fontSize: 12, color: '#fca5a5' },
  tableContainer: {
    height: '100%', overflow: 'auto', background: 'var(--page-bg)',
  },
  table: {
    width: '100%', borderCollapse: 'collapse', fontSize: 13,
  },
  th: {
    position: 'sticky', top: 0, background: 'var(--page-bg-raised)', color: 'var(--page-text-muted)',
    padding: '6px 8px', textAlign: 'left', fontSize: 11, fontWeight: 600,
    borderBottom: '2px solid var(--page-border)', whiteSpace: 'nowrap', zIndex: 1,
  },
  td: {
    padding: '4px 8px', borderBottom: '1px solid var(--page-bg-raised)',
    verticalAlign: 'middle',
  },
  pageBtn: {
    background: 'none', border: 'none', color: '#3b82f6', cursor: 'pointer',
    fontSize: 13, padding: 0, textDecoration: 'underline',
  },
  classSelect: {
    background: 'var(--page-bg-raised)', border: '1px solid var(--page-border)', borderRadius: 3,
    color: 'var(--page-text)', padding: '2px 4px', fontSize: 12, width: '100%',
  },
  methodBadge: {
    fontSize: 10, padding: '1px 5px', borderRadius: 3, color: '#000',
    fontWeight: 600, whiteSpace: 'nowrap',
  },
  confBadge: {
    fontSize: 10, padding: '1px 5px', borderRadius: 3,
    whiteSpace: 'nowrap',
  },
  actionBtn: {
    border: 'none', borderRadius: 3, padding: '2px 6px', fontSize: 10,
    cursor: 'pointer', fontWeight: 600,
  },
  pdfContainer: { height: '100%', background: 'var(--page-bg-raised)' },
  pdfIframe: { width: '100%', height: '100%', border: 'none' },
  noPdf: {
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    height: '100%', color: 'var(--page-text-secondary)',
  },
  statusBar: {
    display: 'flex', alignItems: 'center', gap: 12, padding: '4px 12px',
    background: 'var(--page-bg-raised)', borderTop: '1px solid var(--page-border)', flexShrink: 0,
    fontSize: 11, color: 'var(--page-text-secondary)',
  },
  docList: { padding: 20, maxWidth: 800, margin: '0 auto' },
  docItem: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '8px 12px', margin: '4px 0', background: 'var(--page-bg-raised)',
    borderRadius: 6, cursor: 'pointer', border: '1px solid var(--page-border)',
  },
  docName: { fontSize: 14, color: 'var(--page-text)' },
  docBadges: { display: 'flex', gap: 6 },
  badgeWarning: {
    fontSize: 10, padding: '2px 6px', borderRadius: 3,
    background: '#854d0e', color: '#fde047',
  },
  badgeSuccess: {
    fontSize: 10, padding: '2px 6px', borderRadius: 3,
    background: '#166534', color: '#86efac',
  },
  badgeInfo: {
    fontSize: 10, padding: '2px 6px', borderRadius: 3,
    background: '#1e3a5f', color: '#93c5fd',
  },
}
