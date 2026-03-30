import React, { useState } from 'react'

const EDGE_COLORS = {
  SUMMATION: '#94a3b8',
  CROSS_STATEMENT_TIE: '#3b82f6',
  DISAGGREGATION: '#a78bfa',
  NOTE_TO_FACE: '#64748b',
  IC_DECOMPOSITION: '#f97316',
}

export default function ConceptOverlay({ data, pages, activeDoc, onNavigate, onClose }) {
  const [expanded, setExpanded] = useState(false)

  if (!data || data.error) return null

  return (
    <div style={styles.container}>
      {/* Header — always visible */}
      <div style={styles.header}>
        <span style={{ ...styles.badge, background: data.color }}>{data.context}</span>
        <span style={styles.label}>{data.label}</span>
        <span style={styles.balanceType}>
          {data.balance_type === 'debit' ? 'Dr+' : 'Cr-'}
        </span>
        {data.is_total && <span style={styles.totalTag}>TOTAL</span>}
        <span style={{ flex: 1 }} />
        <button style={styles.expandBtn} onClick={() => setExpanded(!expanded)}>
          {expanded ? '▾' : '▸'}
        </button>
        <button style={styles.closeBtn} onClick={onClose}>&times;</button>
      </div>

      <div style={styles.idRow}>{data.id}</div>

      {/* Expanded: show relationships */}
      {expanded && data.edges?.length > 0 && (
        <div style={styles.edgeList}>
          {data.edges.map((e, i) => (
            <div key={i} style={styles.edgeRow}>
              <span style={{ ...styles.edgeDot, background: EDGE_COLORS[e.edge_type] || '#475569' }} />
              <span style={styles.edgeType}>{e.edge_type.replace(/_/g, ' ')}</span>
              {e.other_concepts.map((c, j) => (
                <span key={j} style={styles.edgeLink} onClick={() => onNavigate(c)}>
                  {c.split('.').pop()}
                </span>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Page references count */}
      {pages?.length > 0 && (
        <div style={styles.pageInfo}>
          Tagged in {pages.length} location{pages.length > 1 ? 's' : ''}
          {pages.find(p => p.doc_id === activeDoc) && (
            <span style={{ color: '#22c55e' }}> — visible in current doc</span>
          )}
        </div>
      )}
    </div>
  )
}

const styles = {
  container: {
    position: 'absolute', bottom: 12, left: 12, right: 12,
    background: 'rgba(15,23,42,0.92)', backdropFilter: 'blur(8px)',
    border: '1px solid #334155', borderRadius: 8,
    padding: 0, maxHeight: '40%', overflow: 'auto',
    zIndex: 50, boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
  },
  header: {
    display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px',
  },
  badge: {
    padding: '1px 8px', borderRadius: 8, fontSize: 10, fontWeight: 600, color: '#fff', flexShrink: 0,
  },
  label: { fontSize: 13, fontWeight: 600, color: '#f1f5f9', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  balanceType: { fontSize: 11, color: '#64748b', flexShrink: 0 },
  totalTag: {
    padding: '0 6px', borderRadius: 6, fontSize: 9, fontWeight: 600,
    background: '#f59e0b', color: '#000', flexShrink: 0,
  },
  expandBtn: {
    background: 'none', border: 'none', color: '#64748b', fontSize: 11,
    cursor: 'pointer', padding: '2px 4px',
  },
  closeBtn: {
    background: 'none', border: 'none', color: '#64748b', fontSize: 16,
    cursor: 'pointer', padding: '0 4px',
  },
  idRow: {
    fontSize: 10, color: '#475569', fontFamily: 'monospace', padding: '0 10px 4px',
  },
  edgeList: { padding: '4px 10px 6px', borderTop: '1px solid #1e293b' },
  edgeRow: {
    display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3, fontSize: 11,
  },
  edgeDot: { width: 6, height: 6, borderRadius: 3, flexShrink: 0 },
  edgeType: { color: '#64748b', fontSize: 10, minWidth: 80 },
  edgeLink: { color: '#3b82f6', cursor: 'pointer' },
  pageInfo: {
    fontSize: 10, color: '#64748b', padding: '3px 10px 5px', borderTop: '1px solid #1e293b',
  },
}
