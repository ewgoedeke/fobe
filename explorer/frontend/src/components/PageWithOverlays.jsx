import React, { useState, useRef, useEffect } from 'react'
import { useDoclingElements } from '../api.js'

const TYPE_COLORS = {
  PNL: '#2563eb',
  SFP: '#059669',
  OCI: '#7c3aed',
  CFS: '#0891b2',
  SOCIE: '#d97706',
  TOC: '#6366f1',
  NOTES: '#64748b',
  MANAGEMENT_REPORT: '#78716c',
  AUDITOR_REPORT: '#a1a1aa',
  OTHER: '#6b7280',
}

// Row bbox colors by state
const ROW_COLOR_TAGGED = '#22d3ee'    // cyan — preTagged concept assigned
const ROW_COLOR_UNTAGGED = '#f97316'  // orange — no tag yet
const ROW_COLOR_HEADER = '#a78bfa'    // purple — header rows
const COL_COLOR = '#facc15'           // yellow — column boundaries

// Convert PDF bbox [x1, y1, x2, y2] (bottom-left origin) to CSS percentages
function pdfToCSS(bbox, pageDims) {
  const [x1, y1, x2, y2] = bbox
  return {
    left: (x1 / pageDims.width) * 100,
    top: ((pageDims.height - y1) / pageDims.height) * 100,
    width: ((x2 - x1) / pageDims.width) * 100,
    height: ((y1 - y2) / pageDims.height) * 100,
  }
}

// Convert top-left origin bbox [x1, y1, x2, y2] to CSS percentages
function tlToCSS(bbox, pageDims) {
  const [x1, y1, x2, y2] = bbox
  return {
    left: (x1 / pageDims.width) * 100,
    top: (y1 / pageDims.height) * 100,
    width: ((x2 - x1) / pageDims.width) * 100,
    height: ((y2 - y1) / pageDims.height) * 100,
  }
}

// Docling element type colors — very subtle
const ELEMENT_COLORS = {
  section_header: '#f472b6',  // pink
  text: '#94a3b8',            // gray
  page_header: '#a78bfa',     // purple
  page_footer: '#a78bfa',     // purple
  picture: '#34d399',         // green
  table: '#60a5fa',           // blue
  list_item: '#fbbf24',       // amber
  caption: '#fb923c',         // orange
}

export default function PageWithOverlays({ docId, pageNo, pageDims, tables, showDoclingElements }) {
  const [loaded, setLoaded] = useState(false)
  const [errored, setErrored] = useState(false)
  const [visible, setVisible] = useState(false)
  const [tooltip, setTooltip] = useState(null)
  const containerRef = useRef(null)

  const { data: doclingElements = null } = useDoclingElements(docId, pageNo, showDoclingElements)

  // IntersectionObserver for lazy loading
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); obs.disconnect() } },
      { rootMargin: '200px' }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  const aspectRatio = pageDims ? (pageDims.height / pageDims.width) : (842 / 595)

  return (
    <div
      ref={containerRef}
      className="relative w-full rounded overflow-hidden bg-muted"
      style={{ paddingBottom: `${aspectRatio * 100}%` }}
    >
      {visible && (
        <>
          {errored ? (
            <div className="absolute inset-0 flex items-center justify-center text-muted-foreground text-xs">
              No PDF
            </div>
          ) : (
            <img
              src={`/api/page-image/${docId}/${pageNo}`}
              alt={`${docId} page ${pageNo}`}
              onLoad={() => setLoaded(true)}
              onError={() => setErrored(true)}
              style={{
                position: 'absolute', top: 0, left: 0,
                width: '100%', height: '100%',
                objectFit: 'contain',
                opacity: loaded ? 1 : 0.3,
                transition: 'opacity 0.2s',
              }}
            />
          )}
          {loaded && tables.map((t, i) => {
            // Table-level bbox: [x1, y1, x2, y2] in PDF coords (bottom-left origin)
            const tBox = t.bbox || [0, 0, 0, 0]
            const tc = pdfToCSS(tBox, pageDims)
            if (!tc.width || !tc.height || !pageDims) return null
            const color = TYPE_COLORS[t.statementComponent] || TYPE_COLORS.OTHER
            const hasDetail = (t.rows && t.rows.length > 0) || (t.columns && t.columns.length > 0)

            return (
              <React.Fragment key={t.tableId || i}>
                {/* Table-level bbox — subtle */}
                <div
                  onMouseEnter={() => setTooltip({ x: tBox[0], y: tBox[1], tableId: t.tableId, sc: t.statementComponent })}
                  onMouseLeave={() => setTooltip(null)}
                  style={{
                    position: 'absolute',
                    left: `${tc.left}%`, top: `${tc.top}%`,
                    width: `${tc.width}%`, height: `${tc.height}%`,
                    border: hasDetail ? `1px dashed ${color}44` : `1px solid ${color}66`,
                    background: hasDetail ? 'transparent' : `${color}08`,
                    borderRadius: 2,
                    pointerEvents: 'auto',
                    cursor: 'pointer',
                  }}
                />

                {/* Row-level bboxes (top-left origin from text extraction) */}
                {t.rows && t.rows.map((r, ri) => {
                  const rb = r.bbox || [0, 0, 0, 0]
                  const rc = tlToCSS(rb, pageDims)
                  if (!rc.width || !rc.height) return null
                  const rowColor = r.rowType === 'HEADER' ? ROW_COLOR_HEADER
                    : r.preTagged ? ROW_COLOR_TAGGED
                    : ROW_COLOR_UNTAGGED
                  return (
                    <div
                      key={`${t.tableId}-r${ri}`}
                      onMouseEnter={() => setTooltip({
                        x: tBox[0], y: tBox[1],
                        tableId: t.tableId, sc: t.statementComponent,
                        detail: `${r.label}${r.preTagged ? ` → ${r.preTagged}` : ''}`,
                      })}
                      onMouseLeave={() => setTooltip(null)}
                      style={{
                        position: 'absolute',
                        left: `${rc.left}%`, top: `${rc.top}%`,
                        width: `${rc.width}%`, height: `${rc.height}%`,
                        border: `1px solid ${rowColor}88`,
                        background: `${rowColor}18`,
                        borderRadius: 1,
                        pointerEvents: 'auto',
                        cursor: 'pointer',
                      }}
                    />
                  )
                })}

                {/* Column-level bboxes (top-left origin) */}
                {t.columns && t.columns.map((c, ci) => {
                  const cb = c.bbox || [0, 0, 0, 0]
                  const cc = tlToCSS(cb, pageDims)
                  if (!cc.width || !cc.height) return null
                  return (
                    <div
                      key={`${t.tableId}-c${ci}`}
                      style={{
                        position: 'absolute',
                        left: `${cc.left}%`, top: `${cc.top}%`,
                        width: `${cc.width}%`, height: `${cc.height}%`,
                        borderLeft: `1px dashed ${COL_COLOR}55`,
                        borderRight: `1px dashed ${COL_COLOR}55`,
                        pointerEvents: 'none',
                      }}
                    />
                  )
                })}
              </React.Fragment>
            )
          })}
          {/* Docling elements overlay — all detected elements on the page */}
          {showDoclingElements && doclingElements && doclingElements.map((el, idx) => {
            const bb = el.bbox || [0, 0, 0, 0]
            if (!bb.some(v => v !== 0) || !pageDims) return null
            const css = el.coord_origin === 'TOPLEFT' ? tlToCSS(bb, pageDims) : pdfToCSS(bb, pageDims)
            if (!css.width || !css.height) return null
            const color = ELEMENT_COLORS[el.label] || '#94a3b8'
            return (
              <div
                key={`dl-${idx}`}
                onMouseEnter={() => setTooltip({
                  x: bb[0], y: bb[1],
                  tableId: el.label,
                  detail: el.text,
                  isDoclng: true,
                  coordOrigin: el.coord_origin,
                })}
                onMouseLeave={() => setTooltip(null)}
                style={{
                  position: 'absolute',
                  left: `${css.left}%`, top: `${css.top}%`,
                  width: `${css.width}%`, height: `${css.height}%`,
                  border: `1px dashed ${color}66`,
                  borderRadius: 1,
                  pointerEvents: 'auto',
                  cursor: 'default',
                }}
              />
            )
          })}

          {tooltip && (
            <div style={{
              position: 'absolute',
              left: `${(tooltip.x / pageDims.width) * 100}%`,
              top: `${Math.max(0, (tooltip.isDoclng && tooltip.coordOrigin === 'TOPLEFT'
                ? (tooltip.y / pageDims.height) * 100 - 3
                : ((pageDims.height - tooltip.y) / pageDims.height) * 100 - 5))}%`,
              background: '#0f172a',
              color: '#e2e8f0',
              padding: '3px 8px',
              borderRadius: 4,
              fontSize: 11,
              whiteSpace: 'nowrap',
              maxWidth: '60%',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              zIndex: 10,
              pointerEvents: 'none',
              border: '1px solid #334155',
            }}>
              {tooltip.tableId} {tooltip.sc ? `(${tooltip.sc})` : ''}
              {tooltip.detail && <div style={{ color: '#94a3b8', fontSize: 10, marginTop: 1 }}>{tooltip.detail}</div>}
            </div>
          )}
          {/* Page number label */}
          <div style={{
            position: 'absolute', bottom: 4, right: 6,
            background: '#0f172acc', color: '#94a3b8',
            padding: '1px 6px', borderRadius: 3, fontSize: 10,
          }}>
            p.{pageNo}
          </div>
        </>
      )}
    </div>
  )
}
