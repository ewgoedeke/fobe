import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { Allotment } from 'allotment'
import { useAnnotateDocuments, useAnnotateToc, useAnnotateSave, useAnnotateDetect, useAnnotateValidate, useDocOverlayTables } from '../api.js'
import PageWithOverlays from './PageWithOverlays.jsx'

// Physical document structure sections for TOC ground truth.
// Every page in the PDF must be accounted for by one of these section types.
const SECTION_TYPES = [
  // Primary financial statements
  'PNL', 'SFP', 'OCI', 'CFS', 'SOCIE',
  // Document structure
  'TOC',
  'NOTES',
  'FRONT_MATTER',
  'MANAGEMENT_REPORT',
  'AUDITOR_REPORT',
  'CORPORATE_GOVERNANCE',
  'ESG',
  'RISK_REPORT',
  'REMUNERATION_REPORT',
  'SUPERVISORY_BOARD',
  'RESPONSIBILITY_STATEMENT',
  'APPENDIX',
  'OTHER',
]

// Colors for section type pills in the coverage bar
const TYPE_COLORS = {
  PNL: '#ef4444', SFP: '#f97316', OCI: '#eab308', CFS: '#22c55e', SOCIE: '#14b8a6',
  TOC: '#64748b', NOTES: '#8b5cf6', FRONT_MATTER: '#475569', MANAGEMENT_REPORT: '#0ea5e9',
  AUDITOR_REPORT: '#a855f7', CORPORATE_GOVERNANCE: '#ec4899', ESG: '#10b981',
  RISK_REPORT: '#f59e0b', REMUNERATION_REPORT: '#6366f1', SUPERVISORY_BOARD: '#d946ef',
  RESPONSIBILITY_STATEMENT: '#78716c', APPENDIX: '#06b6d4', OTHER: '#334155',
}

const GAAP_COLORS = { IFRS: '#3b82f6', UGB: '#22c55e' }
const STATUS_COLORS = {
  complete: '#22c55e',
  in_progress: '#eab308',
  not_started: '#64748b',
}

// Compute page coverage from sections
function computeCoverage(sections, totalPages) {
  if (!totalPages) return { covered: new Set(), gaps: [], percent: 0 }
  const covered = new Set()
  for (const sec of sections) {
    const start = sec.start_page
    const end = sec.end_page || start
    if (start && end) {
      for (let p = start; p <= end; p++) covered.add(p)
    }
  }
  const gaps = []
  let gapStart = null
  for (let p = 1; p <= totalPages; p++) {
    if (!covered.has(p)) {
      if (gapStart === null) gapStart = p
    } else {
      if (gapStart !== null) {
        gaps.push([gapStart, p - 1])
        gapStart = null
      }
    }
  }
  if (gapStart !== null) gaps.push([gapStart, totalPages])
  return { covered, gaps, percent: Math.round((covered.size / totalPages) * 100) }
}

export default function TocAnnotator({ onBack }) {
  const [activeDoc, setActiveDoc] = useState(null)
  const [groundTruth, setGroundTruth] = useState(null)
  const [totalPages, setTotalPages] = useState(0)
  const [saveMsg, setSaveMsg] = useState('')
  const [pdfPage, setPdfPage] = useState(1)
  const [validationResults, setValidationResults] = useState(null)
  const [pageDims, setPageDims] = useState({})
  const pageRefs = useRef({})
  const scrollContainerRef = useRef(null)

  const sections = groundTruth?.sections || []
  const hasPageNums = groundTruth?.has_page_numbers !== false

  const coverage = useMemo(
    () => computeCoverage(sections, totalPages),
    [sections, totalPages]
  )

  // Cached queries
  const { data: documents = [] } = useAnnotateDocuments()
  const { data: tocData } = useAnnotateToc(activeDoc)

  // Table overlay data for PageWithOverlays
  const { data: allTables = [] } = useDocOverlayTables(activeDoc, !!activeDoc)

  // Mutations
  const saveMutation = useAnnotateSave(activeDoc)
  const detectMutation = useAnnotateDetect(activeDoc)
  const validateMutation = useAnnotateValidate(activeDoc)

  const saving = saveMutation.isPending
  const detecting = detectMutation.isPending
  const validating = validateMutation.isPending

  // Load ground truth from query
  useEffect(() => {
    if (!tocData) return
    setGroundTruth(tocData.ground_truth || {})
    setTotalPages(tocData.page_count || 0)
    setPageDims(tocData.page_dims || {})
    setValidationResults(null)
  }, [tocData])

  const goToPage = useCallback((page) => {
    if (!page || page < 1) return
    setPdfPage(page)
    const el = pageRefs.current[page]
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [])

  // Build page→section map for coloring page borders
  const pageSectionMap = useMemo(() => {
    const map = {}
    for (const sec of sections) {
      const start = sec.start_page
      const end = sec.end_page || start
      if (start && end) {
        for (let p = start; p <= end; p++) {
          map[p] = sec.statement_type
        }
      }
    }
    return map
  }, [sections])

  // Auto-detect TOC
  const handleDetect = useCallback(async () => {
    if (!activeDoc) return
    try {
      const data = await detectMutation.mutateAsync()
      if (data.detected && data.sections?.length) {
        setGroundTruth(prev => {
          const existing = prev.sections || []
          const existingPages = new Set(existing.map(s => s.start_page))
          const newSections = data.sections.filter(s => !existingPages.has(s.start_page))
          const merged = [...existing, ...newSections].sort((a, b) =>
            (a.start_page || 0) - (b.start_page || 0)
          )
          return { ...prev, sections: merged, has_toc: true }
        })
        setSaveMsg(`Detected ${data.sections.length} sections`)
      } else {
        setSaveMsg(data.message || 'No TOC detected')
      }
    } catch (e) {
      setSaveMsg('Detection failed')
    }
    setTimeout(() => setSaveMsg(''), 3000)
  }, [activeDoc, detectMutation])

  // Save
  const handleSave = useCallback(async () => {
    if (!activeDoc || !groundTruth) return
    try {
      await saveMutation.mutateAsync(groundTruth)
      setSaveMsg('Saved')
    } catch (e) {
      setSaveMsg('Save failed')
    }
    setTimeout(() => setSaveMsg(''), 3000)
  }, [activeDoc, groundTruth, saveMutation])

  // Validate
  const handleValidate = useCallback(async () => {
    if (!activeDoc) return
    try {
      const data = await validateMutation.mutateAsync(groundTruth)
      setValidationResults(data)
      if (data.page_refs) {
        setGroundTruth(prev => {
          const secs = [...(prev.sections || [])]
          data.page_refs.forEach(f => {
            if (f.section_idx < secs.length) {
              secs[f.section_idx] = { ...secs[f.section_idx], validated: f.status === 'ok' }
            }
          })
          return { ...prev, sections: secs }
        })
      }
      setSaveMsg(`Validated: ${data.summary?.page_ok || 0} ok, ${data.summary?.page_warnings || 0} warnings`)
    } catch (e) {
      setSaveMsg('Validation failed')
    }
    setTimeout(() => setSaveMsg(''), 5000)
  }, [activeDoc, groundTruth])

  // Section CRUD
  const updateSection = (idx, field, value) => {
    setGroundTruth(prev => {
      const secs = [...(prev.sections || [])]
      secs[idx] = { ...secs[idx], [field]: value }
      return { ...prev, sections: secs }
    })
  }

  const addSection = () => {
    setGroundTruth(prev => ({
      ...prev,
      sections: [...(prev.sections || []), {
        label: '',
        statement_type: 'OTHER',
        start_page: pdfPage || 1,
        end_page: pdfPage || 1,
        note_number: null,
        validated: false,
      }],
    }))
  }

  // Add section to fill a specific gap
  const addSectionForGap = (gapStart, gapEnd) => {
    setGroundTruth(prev => ({
      ...prev,
      sections: [...(prev.sections || []), {
        label: '',
        statement_type: 'OTHER',
        start_page: gapStart,
        end_page: gapEnd,
        note_number: null,
        validated: false,
      }],
    }))
    goToPage(gapStart)
  }

  const removeSection = (idx) => {
    setGroundTruth(prev => ({
      ...prev,
      sections: (prev.sections || []).filter((_, i) => i !== idx),
    }))
  }

  const moveSection = (idx, dir) => {
    setGroundTruth(prev => {
      const secs = [...(prev.sections || [])]
      const target = idx + dir
      if (target < 0 || target >= secs.length) return prev
      ;[secs[idx], secs[target]] = [secs[target], secs[idx]]
      return { ...prev, sections: secs }
    })
  }

  // Sort sections by start page
  const sortSections = () => {
    setGroundTruth(prev => ({
      ...prev,
      sections: [...(prev.sections || [])].sort((a, b) => (a.start_page || 0) - (b.start_page || 0)),
    }))
  }

  // ── Dashboard view ───────────────────────────────────────
  if (!activeDoc) {
    return (
      <div style={s.container}>
        <div style={s.header}>
          <button onClick={onBack} style={s.backBtn}>Back</button>
          <h2 style={s.title}>TOC Ground Truth Annotation</h2>
          <span style={s.subtitle}>{documents.length} documents</span>
        </div>
        <div style={s.dashScroll}>
          <table style={s.dashTable}>
            <thead>
              <tr>
                <th style={s.th}>Document</th>
                <th style={s.th}>GAAP</th>
                <th style={s.th}>Pages</th>
                <th style={s.th}>Tables</th>
                <th style={s.th}>TOC</th>
                <th style={s.th}>Fixture</th>
                <th style={s.th}>Status</th>
              </tr>
            </thead>
            <tbody>
              {documents.map(doc => (
                <tr key={doc.doc_id} style={s.dashRow} onClick={() => setActiveDoc(doc.doc_id)}>
                  <td style={s.td}><span style={s.docName}>{doc.doc_id}</span></td>
                  <td style={s.td}>
                    <span style={{ ...s.badge, background: GAAP_COLORS[doc.gaap] || '#64748b' }}>{doc.gaap}</span>
                  </td>
                  <td style={{ ...s.td, textAlign: 'right', fontFamily: 'monospace' }}>
                    {doc.page_count || '--'}
                  </td>
                  <td style={{ ...s.td, textAlign: 'right', fontFamily: 'monospace' }}>
                    {doc.has_fixture ? doc.table_count : '--'}
                  </td>
                  <td style={{ ...s.td, textAlign: 'center' }}>
                    {doc.has_toc === true
                      ? <span style={{ color: '#22c55e', fontWeight: 600 }}>Yes</span>
                      : doc.has_toc === false
                        ? <span style={{ color: '#94a3b8' }}>No</span>
                        : <span style={{ color: '#64748b' }}>?</span>}
                  </td>
                  <td style={s.td}>
                    {doc.has_fixture
                      ? <span style={{ color: '#22c55e' }}>Yes</span>
                      : <span style={{ color: '#ef4444' }}>Missing</span>}
                  </td>
                  <td style={s.td}>
                    <span style={{ ...s.statusBadge, background: STATUS_COLORS[doc.annotation_status] }}>
                      {doc.annotation_status === 'complete'
                        ? `Done (${doc.section_count})`
                        : doc.annotation_status === 'in_progress' ? 'In progress' : 'Not started'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    )
  }

  // ── Document annotator view ──────────────────────────────
  return (
    <div style={s.container}>
      {/* Top bar */}
      <div style={s.header}>
        <button onClick={() => setActiveDoc(null)} style={s.backBtn}>Back</button>
        <h2 style={s.title}>{activeDoc}</h2>
        {totalPages > 0 && (
          <span style={s.pageInfo}>{totalPages} pages</span>
        )}
        {groundTruth && groundTruth.has_page_numbers === false && (
          <span style={s.noPageNumsBadge}>no printed page #</span>
        )}
        <span style={{ flex: 1 }} />
        <button onClick={handleDetect} style={s.detectBtn} disabled={detecting}>
          {detecting ? 'Detecting...' : 'Auto-detect'}
        </button>
        <button onClick={handleValidate} style={s.validateBtn} disabled={validating}>
          {validating ? 'Validating...' : 'Validate'}
        </button>
        <button onClick={handleSave} style={s.saveBtn} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
        {saveMsg && <span style={s.saveMsg}>{saveMsg}</span>}
      </div>

      <Allotment defaultSizes={[55, 45]}>
        {/* Left: Annotation form */}
        <Allotment.Pane minSize={400}>
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <div style={s.formScroll}>
            {/* Coverage bar */}
            {totalPages > 0 && (
              <div style={s.coverageSection}>
                <div style={s.coverageHeader}>
                  <span style={s.coverageLabel}>
                    Coverage: {coverage.covered.size}/{totalPages} pages ({coverage.percent}%)
                  </span>
                  {coverage.gaps.length > 0 && (
                    <span style={s.gapCount}>{coverage.gaps.length} gap{coverage.gaps.length > 1 ? 's' : ''}</span>
                  )}
                </div>
                {/* Visual page bar */}
                <div style={s.pageBar}>
                  {(() => {
                    // Build a map of page -> section type for coloring
                    const pageTypes = {}
                    for (const sec of sections) {
                      const start = sec.start_page
                      const end = sec.end_page || start
                      if (start && end) {
                        for (let p = start; p <= end; p++) {
                          pageTypes[p] = sec.statement_type
                        }
                      }
                    }
                    // Render segments — group consecutive pages of same type for efficiency
                    const segments = []
                    let segStart = 1, segType = pageTypes[1] || null
                    for (let p = 2; p <= totalPages + 1; p++) {
                      const t = p <= totalPages ? (pageTypes[p] || null) : '__END__'
                      if (t !== segType) {
                        segments.push({ start: segStart, end: p - 1, type: segType })
                        segStart = p
                        segType = t
                      }
                    }
                    return segments.map((seg, i) => (
                      <div
                        key={i}
                        style={{
                          flex: seg.end - seg.start + 1,
                          height: 14,
                          background: seg.type ? (TYPE_COLORS[seg.type] || '#475569') : 'var(--page-bg-raised)',
                          borderRight: '1px solid var(--page-bg)',
                          cursor: 'pointer',
                          minWidth: 1,
                        }}
                        title={`p.${seg.start}${seg.end !== seg.start ? `-${seg.end}` : ''}: ${seg.type || 'uncovered'}`}
                        onClick={() => goToPage(seg.start)}
                      />
                    ))
                  })()}
                </div>
                {/* Gap list */}
                {coverage.gaps.length > 0 && (
                  <div style={s.gapList}>
                    {coverage.gaps.map(([gs, ge], i) => (
                      <button
                        key={i}
                        style={s.gapBtn}
                        onClick={() => addSectionForGap(gs, ge)}
                        title={`Add section for pages ${gs}-${ge}`}
                      >
                        + p.{gs}{ge !== gs ? `-${ge}` : ''} ({ge - gs + 1})
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Annotator + metadata */}
            <div style={s.metaRow}>
              <label style={s.fieldLabel}>
                Annotator:
                <input
                  type="text"
                  value={groundTruth?.annotator || ''}
                  onChange={e => setGroundTruth(prev => ({ ...prev, annotator: e.target.value }))}
                  style={s.textInput}
                  placeholder="your name"
                />
              </label>
              <label style={s.fieldLabel}>
                TOC:
                <select
                  value={groundTruth?.has_toc === true ? 'yes' : groundTruth?.has_toc === false ? 'no' : '?'}
                  onChange={e => {
                    const v = e.target.value
                    setGroundTruth(prev => ({
                      ...prev,
                      has_toc: v === 'yes' ? true : v === 'no' ? false : undefined,
                    }))
                  }}
                  style={{ ...s.textInput, width: 60 }}
                >
                  <option value="?">?</option>
                  <option value="yes">Yes</option>
                  <option value="no">No</option>
                </select>
              </label>
              <label style={s.checkLabel}>
                <input
                  type="checkbox"
                  checked={groundTruth?.has_page_numbers ?? true}
                  onChange={e => setGroundTruth(prev => ({ ...prev, has_page_numbers: e.target.checked }))}
                />
                Has printed page #
              </label>
            </div>
            {groundTruth && groundTruth.has_page_numbers === false && (
              <div style={s.noPageNumsBanner}>
                No printed page numbers — using PDF page numbers only
              </div>
            )}

            {/* Section list */}
            <div style={s.sectionHeader}>
              <span style={s.sectionTitle}>Sections ({sections.length})</span>
              <div style={{ display: 'flex', gap: 6 }}>
                <button onClick={sortSections} style={s.sortBtn} title="Sort by start page">Sort</button>
                <button onClick={addSection} style={s.addBtn}>+ Add section</button>
              </div>
            </div>

            {sections.length === 0 && (
              <div style={s.emptyMsg}>
                No sections yet. Click "Auto-detect" to pre-fill, or "+ Add section" to start manually.
              </div>
            )}

            {sections.map((sec, idx) => (
              <div key={idx} style={{
                ...s.sectionCard,
                borderLeft: `3px solid ${sec.validated ? '#22c55e' : (TYPE_COLORS[sec.statement_type] || '#334155')}`,
              }}>
                <div style={s.sectionRow}>
                  <span style={s.sectionIdx}>{idx + 1}</span>
                  <input
                    type="text"
                    value={sec.label || ''}
                    onChange={e => updateSection(idx, 'label', e.target.value)}
                    style={s.labelInput}
                    placeholder="Section label (e.g. Konzernbilanz)"
                  />
                  <select
                    value={sec.statement_type || 'OTHER'}
                    onChange={e => updateSection(idx, 'statement_type', e.target.value)}
                    style={{
                      ...s.typeSelect,
                      borderColor: TYPE_COLORS[sec.statement_type] || '#334155',
                    }}
                  >
                    {SECTION_TYPES.map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div style={s.sectionRow}>
                  <span style={s.pageSeriesLabel}>PDF</span>
                  <label style={s.miniLabel}>
                    <input
                      type="number"
                      value={sec.start_page ?? ''}
                      onChange={e => updateSection(idx, 'start_page', e.target.value ? parseInt(e.target.value) : null)}
                      style={s.pageInput}
                    />
                  </label>
                  <span style={s.pageDash}>–</span>
                  <label style={s.miniLabel}>
                    <input
                      type="number"
                      value={sec.end_page ?? ''}
                      onChange={e => updateSection(idx, 'end_page', e.target.value ? parseInt(e.target.value) : null)}
                      style={s.pageInput}
                    />
                  </label>
                  {hasPageNums && (
                    <>
                      <span style={s.pageSeriesLabel}>Doc</span>
                      <label style={s.miniLabel}>
                        <input
                          type="text"
                          value={sec.start_page_doc ?? ''}
                          onChange={e => updateSection(idx, 'start_page_doc', e.target.value || null)}
                          style={s.pageInput}
                          placeholder="--"
                        />
                      </label>
                      <span style={s.pageDash}>–</span>
                      <label style={s.miniLabel}>
                        <input
                          type="text"
                          value={sec.end_page_doc ?? ''}
                          onChange={e => updateSection(idx, 'end_page_doc', e.target.value || null)}
                          style={s.pageInput}
                          placeholder="--"
                        />
                      </label>
                    </>
                  )}
                  <label style={s.miniLabel}>
                    Note #
                    <input
                      type="text"
                      value={sec.note_number || ''}
                      onChange={e => updateSection(idx, 'note_number', e.target.value || null)}
                      style={{ ...s.pageInput, width: 40 }}
                      placeholder="--"
                    />
                  </label>
                  <label style={s.checkLabel}>
                    <input
                      type="checkbox"
                      checked={sec.validated || false}
                      onChange={e => updateSection(idx, 'validated', e.target.checked)}
                    />
                    Verified
                  </label>
                  <span style={{ flex: 1 }} />
                  <button onClick={() => goToPage(sec.start_page)} style={s.gotoBtn} title="Go to page">Go</button>
                  <button onClick={() => moveSection(idx, -1)} style={s.moveBtn} title="Move up">Up</button>
                  <button onClick={() => moveSection(idx, 1)} style={s.moveBtn} title="Move down">Dn</button>
                  <button onClick={() => removeSection(idx)} style={s.deleteBtn} title="Remove">X</button>
                </div>
              </div>
            ))}
          </div>
          </div>
        </Allotment.Pane>

        {/* Right: PDF page gallery */}
        <Allotment.Pane minSize={300}>
          <div style={s.pdfContainer}>
            <div style={s.pdfToolbar}>
              <button onClick={() => goToPage(pdfPage - 1)} style={s.pdfBtn}>Prev</button>
              <input
                type="number"
                value={pdfPage}
                onChange={e => setPdfPage(parseInt(e.target.value) || 1)}
                onBlur={() => goToPage(pdfPage)}
                onKeyDown={e => e.key === 'Enter' && goToPage(pdfPage)}
                style={s.pdfPageInput}
              />
              {totalPages > 0 && <span style={s.pdfPageTotal}>/ {totalPages}</span>}
              {!hasPageNums && (
                <span style={s.noPageNumsToolbar}>no doc pg#</span>
              )}
              <button onClick={() => goToPage(pdfPage + 1)} style={s.pdfBtn}>Next</button>
            </div>
            <div ref={scrollContainerRef} style={s.pageGallery}>
              {totalPages > 0 ? (
                Array.from({ length: totalPages }, (_, i) => i + 1).map(pageNo => {
                  const dims = pageDims[pageNo] || pageDims[String(pageNo)] || { width: 595, height: 842 }
                  const tablesOnPage = allTables.filter(t => t.pageNo === pageNo)
                  const sectionType = pageSectionMap[pageNo]
                  const borderColor = sectionType ? (TYPE_COLORS[sectionType] || '#334155') : 'var(--page-border)'
                  return (
                    <div
                      key={pageNo}
                      ref={el => { pageRefs.current[pageNo] = el }}
                      style={{
                        ...s.pageCard,
                        borderColor,
                        borderWidth: sectionType ? 2 : 1,
                      }}
                    >
                      {sectionType && (
                        <div style={{
                          ...s.pageSectionLabel,
                          background: TYPE_COLORS[sectionType] || '#334155',
                        }}>
                          {sectionType}
                        </div>
                      )}
                      <PageWithOverlays
                        docId={activeDoc}
                        pageNo={pageNo}
                        pageDims={dims}
                        tables={tablesOnPage}
                        showDoclingElements={false}
                      />
                    </div>
                  )
                })
              ) : (
                <div style={s.noPdf}>No pages available</div>
              )}
            </div>
          </div>
        </Allotment.Pane>
      </Allotment>
    </div>
  )
}

const s = {
  container: {
    height: '100%', display: 'flex', flexDirection: 'column',
    background: 'var(--page-bg)', color: 'var(--page-text)',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px',
    background: 'var(--page-bg-raised)', borderBottom: '1px solid var(--page-border)', flexShrink: 0,
  },
  backBtn: {
    background: 'var(--page-border)', border: 'none', color: 'var(--page-text-muted)', padding: '4px 12px',
    borderRadius: 4, cursor: 'pointer', fontSize: 12,
  },
  title: { margin: 0, fontSize: 15, fontWeight: 600, color: 'var(--page-text)' },
  subtitle: { fontSize: 12, color: 'var(--page-text-secondary)' },
  pageInfo: {
    fontSize: 11, color: 'var(--page-text-secondary)', background: 'var(--page-border)', padding: '2px 8px',
    borderRadius: 8, fontFamily: 'monospace',
  },
  detectBtn: {
    background: '#1e40af', border: 'none', color: '#93c5fd', padding: '5px 14px',
    borderRadius: 4, cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  validateBtn: {
    background: '#854d0e', border: 'none', color: '#fde047', padding: '5px 14px',
    borderRadius: 4, cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  saveBtn: {
    background: '#166534', border: 'none', color: '#86efac', padding: '5px 14px',
    borderRadius: 4, cursor: 'pointer', fontSize: 12, fontWeight: 600,
  },
  saveMsg: { fontSize: 11, color: '#22c55e', fontWeight: 600 },

  // Dashboard
  dashScroll: { flex: 1, overflow: 'auto', padding: 12 },
  dashTable: { width: '100%', borderCollapse: 'collapse' },
  th: {
    textAlign: 'left', padding: '8px 12px', fontSize: 11, fontWeight: 600,
    color: 'var(--page-text-secondary)', borderBottom: '1px solid var(--page-border)', textTransform: 'uppercase',
  },
  dashRow: { cursor: 'pointer', borderBottom: '1px solid var(--page-bg-raised)' },
  td: { padding: '8px 12px', fontSize: 13 },
  docName: { fontWeight: 500, color: 'var(--page-text)' },
  badge: {
    padding: '1px 8px', borderRadius: 8, fontSize: 10, fontWeight: 600, color: '#fff',
  },
  statusBadge: {
    padding: '2px 10px', borderRadius: 10, fontSize: 10, fontWeight: 600, color: '#fff',
  },

  // Coverage bar
  coverageSection: {
    margin: '8px 0', padding: 10, background: 'var(--page-bg-raised)', borderRadius: 6,
  },
  coverageHeader: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    marginBottom: 6,
  },
  coverageLabel: { fontSize: 12, color: 'var(--page-text-muted)', fontWeight: 600 },
  gapCount: {
    fontSize: 10, color: '#fbbf24', background: '#78350f', padding: '1px 8px',
    borderRadius: 8, fontWeight: 600,
  },
  pageBar: {
    display: 'flex', height: 14, borderRadius: 3, overflow: 'hidden',
    background: 'var(--page-bg-raised)', border: '1px solid var(--page-border)',
  },
  gapList: {
    display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6,
  },
  gapBtn: {
    background: 'var(--page-bg-raised)', border: '1px solid #854d0e', color: '#fbbf24',
    padding: '2px 8px', borderRadius: 3, cursor: 'pointer', fontSize: 10,
    fontFamily: 'monospace',
  },

  // Form
  formScroll: { flex: 1, overflow: 'auto', padding: 12 },
  metaRow: {
    display: 'flex', alignItems: 'center', gap: 16, padding: '8px 0',
    borderBottom: '1px solid var(--page-bg-raised)',
  },
  fieldLabel: {
    display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--page-text-muted)',
  },
  checkLabel: {
    display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--page-text-muted)',
    cursor: 'pointer',
  },
  textInput: {
    background: 'var(--page-input-bg)', border: '1px solid var(--page-border)', borderRadius: 4,
    color: 'var(--page-text)', padding: '3px 8px', fontSize: 12, width: 120,
  },
  pageInput: {
    background: 'var(--page-input-bg)', border: '1px solid var(--page-border)', borderRadius: 4,
    color: 'var(--page-text)', padding: '3px 6px', fontSize: 12, width: 56, textAlign: 'center',
  },

  noPageNumsBadge: {
    background: '#78350f', color: '#fbbf24', padding: '2px 8px',
    borderRadius: 8, fontSize: 10, fontWeight: 600,
  },
  pageSeriesLabel: {
    fontSize: 10, color: 'var(--page-text-secondary)', fontWeight: 600, minWidth: 24,
  },
  pageDash: {
    fontSize: 11, color: 'var(--page-text-secondary)',
  },
  noPageNumsToolbar: {
    fontSize: 10, color: '#fbbf24', fontWeight: 500,
  },
  noPageNumsBanner: {
    background: '#78350f', color: '#fbbf24', padding: '6px 12px',
    borderRadius: 4, fontSize: 11, fontWeight: 500, marginBottom: 8,
    border: '1px solid #854d0e',
  },

  // Section list
  sectionHeader: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '12px 0 6px', borderBottom: '1px solid var(--page-border)',
  },
  sectionTitle: { fontSize: 13, fontWeight: 600, color: 'var(--page-text-muted)' },
  addBtn: {
    background: 'var(--page-border)', border: 'none', color: 'var(--page-text-muted)', padding: '4px 12px',
    borderRadius: 4, cursor: 'pointer', fontSize: 12,
  },
  sortBtn: {
    background: 'var(--page-bg-raised)', border: '1px solid var(--page-border)', color: 'var(--page-text-secondary)', padding: '4px 10px',
    borderRadius: 4, cursor: 'pointer', fontSize: 11,
  },
  emptyMsg: {
    padding: '24px 0', textAlign: 'center', color: 'var(--page-text-secondary)', fontSize: 13,
  },
  sectionCard: {
    margin: '6px 0', padding: '8px 10px', background: 'var(--page-bg-raised)',
    borderRadius: 4, display: 'flex', flexDirection: 'column', gap: 6,
  },
  sectionRow: {
    display: 'flex', alignItems: 'center', gap: 8,
  },
  sectionIdx: {
    width: 20, textAlign: 'center', fontSize: 11, color: 'var(--page-text-secondary)', fontWeight: 600,
  },
  labelInput: {
    flex: 1, background: 'var(--page-input-bg)', border: '1px solid var(--page-border)', borderRadius: 4,
    color: 'var(--page-text)', padding: '4px 8px', fontSize: 12,
  },
  typeSelect: {
    background: 'var(--page-input-bg)', border: '1px solid var(--page-border)', borderRadius: 4,
    color: 'var(--page-text)', padding: '4px 6px', fontSize: 12, width: 160,
  },
  miniLabel: {
    display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--page-text-secondary)',
  },
  gotoBtn: {
    background: '#1e3a5f', border: 'none', color: '#60a5fa', padding: '3px 8px',
    borderRadius: 3, cursor: 'pointer', fontSize: 10, fontWeight: 600,
  },
  moveBtn: {
    background: 'var(--page-border)', border: 'none', color: 'var(--page-text-secondary)', padding: '3px 6px',
    borderRadius: 3, cursor: 'pointer', fontSize: 10,
  },
  deleteBtn: {
    background: '#7f1d1d', border: 'none', color: '#fca5a5', padding: '3px 8px',
    borderRadius: 3, cursor: 'pointer', fontSize: 10, fontWeight: 600,
  },

  // PDF viewer
  pdfContainer: { height: '100%', display: 'flex', flexDirection: 'column' },
  pdfToolbar: {
    display: 'flex', alignItems: 'center', gap: 6, padding: '4px 8px',
    background: 'var(--page-bg-raised)', borderBottom: '1px solid var(--page-border)', flexShrink: 0,
  },
  pdfBtn: {
    background: 'var(--page-border)', border: 'none', color: 'var(--page-text-muted)', padding: '3px 10px',
    borderRadius: 3, cursor: 'pointer', fontSize: 11,
  },
  pdfPageInput: {
    background: 'var(--page-input-bg)', border: '1px solid var(--page-border)', borderRadius: 4,
    color: 'var(--page-text)', padding: '3px 6px', fontSize: 12, width: 52, textAlign: 'center',
  },
  pdfPageTotal: { fontSize: 11, color: 'var(--page-text-secondary)' },
  pageGallery: {
    flex: 1, overflow: 'auto', padding: 8,
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: 8,
    alignContent: 'start',
  },
  pageCard: {
    position: 'relative', borderRadius: 4, overflow: 'hidden',
    border: '1px solid var(--page-border)', flexShrink: 0,
  },
  pageSectionLabel: {
    position: 'absolute', top: 4, left: 4, zIndex: 10,
    color: '#fff', padding: '1px 8px', borderRadius: 3,
    fontSize: 10, fontWeight: 600, opacity: 0.85,
  },
  noPdf: {
    flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
    color: 'var(--page-text-secondary)', fontSize: 13,
  },
}
