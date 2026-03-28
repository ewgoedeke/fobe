import React, { useState, useEffect, useRef } from 'react'

/**
 * Modal for browsing all pages of a document and selecting page range
 * for a given section type. Shows page thumbnails with lazy loading.
 */
export default function PageBrowserModal({ docId, pageCount, pageDims, currentSection, onSave, onClose }) {
  const [startPage, setStartPage] = useState(currentSection?.start_page || null)
  const [endPage, setEndPage] = useState(currentSection?.end_page || null)
  const [selectMode, setSelectMode] = useState(null) // 'start' | 'end' | 'range'
  const [label, setLabel] = useState(currentSection?.label || '')
  const [saving, setSaving] = useState(false)
  const galleryRef = useRef(null)

  const pages = Array.from({ length: pageCount }, (_, i) => i + 1)

  // Scroll to current start page on open
  useEffect(() => {
    if (startPage && galleryRef.current) {
      const el = galleryRef.current.querySelector(`[data-page="${startPage}"]`)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [])

  const handlePageClick = (pageNo) => {
    if (selectMode === 'start') {
      setStartPage(pageNo)
      if (endPage && pageNo > endPage) setEndPage(pageNo)
      setSelectMode('end')
    } else if (selectMode === 'end') {
      if (pageNo < startPage) {
        setEndPage(startPage)
        setStartPage(pageNo)
      } else {
        setEndPage(pageNo)
      }
      setSelectMode(null)
    } else {
      // Single click sets both start and end to same page
      setStartPage(pageNo)
      setEndPage(pageNo)
    }
  }

  const handleSave = async () => {
    if (!startPage || !endPage) return
    setSaving(true)
    try {
      await onSave({
        statement_type: currentSection.statement_type,
        start_page: startPage,
        end_page: endPage,
        label,
      })
    } finally {
      setSaving(false)
    }
  }

  const isInRange = (pageNo) => {
    if (!startPage || !endPage) return false
    return pageNo >= startPage && pageNo <= endPage
  }

  const isEndpoint = (pageNo) => pageNo === startPage || pageNo === endPage

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div style={styles.modal} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={styles.header}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontWeight: 700, fontSize: 15 }}>{docId}</span>
            <span style={styles.typeBadge}>{currentSection?.statement_type}</span>
          </div>
          <button style={styles.closeBtn} onClick={onClose}>&times;</button>
        </div>

        {/* Controls */}
        <div style={styles.controls}>
          <label style={{ fontSize: 12, color: '#94a3b8' }}>
            Label:
            <input
              type="text"
              value={label}
              onChange={e => setLabel(e.target.value)}
              style={styles.input}
              placeholder="Section label..."
            />
          </label>

          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 12, color: '#94a3b8' }}>Pages:</span>
            <button
              style={{ ...styles.rangeBtn, ...(selectMode === 'start' ? styles.rangeBtnActive : {}) }}
              onClick={() => setSelectMode('start')}
            >
              Start: {startPage || '?'}
            </button>
            <span style={{ color: '#475569' }}>&ndash;</span>
            <button
              style={{ ...styles.rangeBtn, ...(selectMode === 'end' ? styles.rangeBtnActive : {}) }}
              onClick={() => setSelectMode('end')}
            >
              End: {endPage || '?'}
            </button>
          </div>

          <div style={{ display: 'flex', gap: 8, marginLeft: 'auto' }}>
            <button style={styles.cancelBtn} onClick={onClose}>Cancel</button>
            <button
              style={{ ...styles.saveBtn, opacity: (startPage && endPage) ? 1 : 0.4 }}
              disabled={!startPage || !endPage || saving}
              onClick={handleSave}
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>

        {/* Instruction */}
        {selectMode && (
          <div style={styles.instruction}>
            Click a page to set the {selectMode} page
          </div>
        )}

        {/* Page gallery */}
        <div ref={galleryRef} style={styles.gallery}>
          {pages.map(pageNo => (
            <PageThumb
              key={pageNo}
              docId={docId}
              pageNo={pageNo}
              selected={isInRange(pageNo)}
              isEndpoint={isEndpoint(pageNo)}
              selectMode={selectMode}
              onClick={() => handlePageClick(pageNo)}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function PageThumb({ docId, pageNo, selected, isEndpoint, selectMode, onClick }) {
  const [visible, setVisible] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); obs.disconnect() } },
      { rootMargin: '300px' }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return (
    <div
      ref={ref}
      data-page={pageNo}
      onClick={onClick}
      style={{
        ...styles.thumb,
        border: isEndpoint ? '3px solid #3b82f6' :
                selected ? '2px solid #3b82f680' :
                '1px solid #334155',
        background: selected ? '#1e3a5f' : '#0f172a',
        cursor: selectMode ? 'crosshair' : 'pointer',
      }}
    >
      {visible ? (
        <img
          src={`/api/page-image/${docId}/${pageNo}?dpi=72`}
          alt={`p.${pageNo}`}
          loading="lazy"
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'contain', display: 'block', borderRadius: 2 }}
        />
      ) : (
        <div style={{ position: 'absolute', inset: 0, background: '#1e293b' }} />
      )}
      <div style={styles.pageLabel}>
        {pageNo}
      </div>
    </div>
  )
}

const styles = {
  backdrop: {
    position: 'fixed', inset: 0, background: '#000000cc',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 1000,
  },
  modal: {
    background: '#0f172a', borderRadius: 8, border: '1px solid #334155',
    width: '90vw', maxWidth: 1200, height: '85vh',
    display: 'flex', flexDirection: 'column',
    overflow: 'hidden',
  },
  header: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '10px 16px', borderBottom: '1px solid #1e293b',
    flexShrink: 0,
  },
  typeBadge: {
    background: '#6366f1', color: '#fff', padding: '2px 8px',
    borderRadius: 4, fontSize: 11, fontWeight: 600,
  },
  closeBtn: {
    background: 'none', border: 'none', color: '#64748b',
    fontSize: 22, cursor: 'pointer', padding: '0 4px',
  },
  controls: {
    display: 'flex', alignItems: 'center', gap: 16,
    padding: '8px 16px', borderBottom: '1px solid #1e293b',
    flexShrink: 0,
  },
  input: {
    background: '#1e293b', border: '1px solid #334155', borderRadius: 4,
    color: '#e2e8f0', padding: '3px 8px', fontSize: 12, marginLeft: 6,
    width: 200,
  },
  rangeBtn: {
    background: '#1e293b', border: '1px solid #334155', borderRadius: 4,
    color: '#e2e8f0', padding: '3px 10px', fontSize: 12, cursor: 'pointer',
    minWidth: 70, textAlign: 'center',
  },
  rangeBtnActive: {
    border: '2px solid #3b82f6', background: '#1e3a5f',
  },
  instruction: {
    padding: '4px 16px', fontSize: 11, color: '#3b82f6',
    background: '#1e293b', flexShrink: 0,
  },
  cancelBtn: {
    background: '#334155', border: '1px solid #475569', borderRadius: 6,
    color: '#94a3b8', padding: '4px 12px', fontSize: 12, cursor: 'pointer',
  },
  saveBtn: {
    background: '#2563eb', border: 'none', borderRadius: 6,
    color: '#fff', padding: '4px 14px', fontSize: 12, cursor: 'pointer',
    fontWeight: 600,
  },
  gallery: {
    flex: 1, overflowY: 'auto', padding: 16,
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: 12,
    alignContent: 'start',
  },
  thumb: {
    position: 'relative', borderRadius: 4, overflow: 'hidden',
    transition: 'border-color 0.15s',
    aspectRatio: '210 / 297', /* A4 portrait */
  },
  pageLabel: {
    position: 'absolute', bottom: 2, right: 4,
    background: '#0f172acc', color: '#94a3b8',
    padding: '0 5px', borderRadius: 3, fontSize: 10,
  },
}
