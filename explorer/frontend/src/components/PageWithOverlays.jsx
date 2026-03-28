import React, { useState, useRef, useEffect } from 'react'

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

export default function PageWithOverlays({ docId, pageNo, pageDims, tables }) {
  const [loaded, setLoaded] = useState(false)
  const [visible, setVisible] = useState(false)
  const [tooltip, setTooltip] = useState(null)
  const containerRef = useRef(null)

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
      style={{
        position: 'relative',
        width: '100%',
        paddingBottom: `${aspectRatio * 100}%`,
        background: '#1e293b',
        borderRadius: 4,
        overflow: 'hidden',
      }}
    >
      {visible && (
        <>
          <img
            src={`/api/page-image/${docId}/${pageNo}`}
            alt={`${docId} page ${pageNo}`}
            onLoad={() => setLoaded(true)}
            style={{
              position: 'absolute', top: 0, left: 0,
              width: '100%', height: '100%',
              objectFit: 'contain',
              opacity: loaded ? 1 : 0.3,
              transition: 'opacity 0.2s',
            }}
          />
          {loaded && tables.map((t, i) => {
            const [bx, by, bw, bh] = t.bbox || [0, 0, 0, 0]
            if (!bw || !bh || !pageDims) return null
            const color = TYPE_COLORS[t.statementComponent] || TYPE_COLORS.OTHER
            return (
              <div
                key={t.tableId || i}
                onMouseEnter={() => setTooltip({ x: bx, y: by, tableId: t.tableId, sc: t.statementComponent })}
                onMouseLeave={() => setTooltip(null)}
                style={{
                  position: 'absolute',
                  left: `${(bx / pageDims.width) * 100}%`,
                  top: `${(by / pageDims.height) * 100}%`,
                  width: `${(bw / pageDims.width) * 100}%`,
                  height: `${(bh / pageDims.height) * 100}%`,
                  border: `2px solid ${color}`,
                  background: `${color}22`,
                  borderRadius: 2,
                  pointerEvents: 'auto',
                  cursor: 'pointer',
                }}
              />
            )
          })}
          {tooltip && (
            <div style={{
              position: 'absolute',
              left: `${(tooltip.x / pageDims.width) * 100}%`,
              top: `${Math.max(0, (tooltip.y / pageDims.height) * 100 - 5)}%`,
              background: '#0f172a',
              color: '#e2e8f0',
              padding: '3px 8px',
              borderRadius: 4,
              fontSize: 11,
              whiteSpace: 'nowrap',
              zIndex: 10,
              pointerEvents: 'none',
              border: '1px solid #334155',
            }}>
              {tooltip.tableId} {tooltip.sc ? `(${tooltip.sc})` : ''}
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
