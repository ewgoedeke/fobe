import React, { useRef, useEffect, useCallback, forwardRef, useImperativeHandle, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const EDGE_COLORS = {
  SUMMATION: '#94a3b8',
  CROSS_STATEMENT_TIE: '#3b82f6',
  DISAGGREGATION: '#a78bfa',
  NOTE_TO_FACE: '#64748b',
  IC_DECOMPOSITION: '#f97316',
}

const EDGE_DASH = {
  CROSS_STATEMENT_TIE: [6, 3],
  DISAGGREGATION: [3, 3],
  NOTE_TO_FACE: [4, 4],
}

function nodeRadius(node) {
  if (node.type === 'context') {
    if (node.is_primary) return 22
    if (node.is_connected) return 12
    return 8
  }
  if (node.is_center) return 7
  if (node.is_total) return 6
  return 4
}

const GraphPane = forwardRef(function GraphPane(
  { data, onNodeClick, onNodeDblClick, onLinkClick, selectedId },
  ref
) {
  const fgRef = useRef()
  const containerRef = useRef()
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })

  useImperativeHandle(ref, () => ({
    zoomToFit: () => fgRef.current?.zoomToFit(400, 60),
  }))

  // Resize handling
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const obs = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      setDimensions({ width, height })
    })
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  // Apply fixed positions from server (fx/fy) and configure forces
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return

    // Pin nodes that have fx/fy from the server
    data.nodes.forEach(n => {
      if (n.fx != null && n.fy != null) {
        n.fx = n.fx
        n.fy = n.fy
      }
    })

    // Configure forces — gentle for overview (positions are fixed),
    // stronger for neighborhood (positions are free)
    const hasFixedNodes = data.nodes.some(n => n.fx != null)
    if (hasFixedNodes) {
      // Overview mode: minimal forces, nodes are pinned
      fg.d3Force('charge').strength(-30)
      fg.d3Force('link').distance(100)
    } else {
      // Neighborhood mode: spread nodes apart
      fg.d3Force('charge').strength(n =>
        n.type === 'context' ? -300 : -100
      )
      fg.d3Force('link').distance(link => {
        const t = link.edge_type || ''
        if (t === 'CROSS_STATEMENT_TIE') return 180
        return 100
      })
    }
    fg.d3ReheatSimulation()
  }, [data])

  // Zoom to fit
  useEffect(() => {
    const timer = setTimeout(() => fgRef.current?.zoomToFit(400, 50), 500)
    return () => clearTimeout(timer)
  }, [data])

  // Node rendering
  const paintNode = useCallback((node, ctx, globalScale) => {
    if (node.x == null || node.y == null) return
    const isContext = node.type === 'context'
    const label = node.label || node.id
    const r = nodeRadius(node)

    ctx.beginPath()

    if (isContext) {
      if (node.is_primary) {
        // Large hexagon for primary statements
        const sides = 6
        const a = Math.PI / sides
        ctx.moveTo(node.x + r * Math.cos(0), node.y + r * Math.sin(0))
        for (let i = 1; i <= sides; i++) {
          ctx.lineTo(node.x + r * Math.cos(i * 2 * a), node.y + r * Math.sin(i * 2 * a))
        }
        ctx.closePath()
        ctx.fillStyle = node.color || '#475569'
        ctx.fill()
        ctx.strokeStyle = 'rgba(255,255,255,0.25)'
        ctx.lineWidth = 1.5 / globalScale
        ctx.stroke()

        // Count
        ctx.font = `bold ${Math.max(9, 12 / globalScale)}px sans-serif`
        ctx.fillStyle = 'rgba(255,255,255,0.9)'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(String(node.concept_count), node.x, node.y)

        // Label below
        ctx.font = `bold ${Math.max(9, 13 / globalScale)}px sans-serif`
        ctx.fillStyle = '#e2e8f0'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText(label, node.x, node.y + r + 4 / globalScale)
      } else {
        // Small circle for disclosure contexts
        ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
        ctx.fillStyle = node.is_connected ? '#475569' : '#334155'
        ctx.fill()
        if (node.is_connected) {
          ctx.strokeStyle = 'rgba(255,255,255,0.15)'
          ctx.lineWidth = 1 / globalScale
          ctx.stroke()
        }

        // Count inside
        ctx.font = `${Math.max(7, 9 / globalScale)}px sans-serif`
        ctx.fillStyle = 'rgba(255,255,255,0.7)'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        ctx.fillText(String(node.concept_count), node.x, node.y)

        // Label — shorter name
        const shortName = label.replace('DISC.', '')
        ctx.font = `${Math.max(7, 9 / globalScale)}px sans-serif`
        ctx.fillStyle = node.is_connected ? '#94a3b8' : '#64748b'
        ctx.textAlign = 'center'
        ctx.textBaseline = 'top'
        ctx.fillText(shortName, node.x, node.y + r + 2 / globalScale)
      }
    } else {
      // Concept nodes (neighborhood view)
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
      ctx.fillStyle = node.color || '#475569'
      ctx.fill()

      if (node.id === selectedId) {
        ctx.strokeStyle = '#fbbf24'
        ctx.lineWidth = 3 / globalScale
        ctx.stroke()
      } else if (node.is_total) {
        ctx.strokeStyle = '#f59e0b'
        ctx.lineWidth = 2 / globalScale
        ctx.stroke()
      } else if (node.is_center) {
        ctx.strokeStyle = '#f472b6'
        ctx.lineWidth = 2.5 / globalScale
        ctx.stroke()
      }

      const fontSize = Math.max(7, 10 / globalScale)
      ctx.font = `${fontSize}px sans-serif`
      ctx.fillStyle = 'rgba(226,232,240,0.85)'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      const shortLabel = label.length > 28 ? label.slice(0, 25) + '…' : label
      ctx.fillText(shortLabel, node.x, node.y + r + 2 / globalScale)
    }
  }, [selectedId])

  // Link rendering
  const paintLink = useCallback((link, ctx, globalScale) => {
    const edgeType = link.edge_type || 'SUMMATION'
    const color = link.color || EDGE_COLORS[edgeType] || '#475569'
    const dash = EDGE_DASH[edgeType]

    const src = link.source
    const tgt = link.target
    if (src.x == null || tgt.x == null || src.y == null || tgt.y == null) return

    const baseWidth = edgeType === 'CROSS_STATEMENT_TIE' ? 3 : 1.5
    const lineWidth = Math.max(baseWidth / globalScale, 0.5 / globalScale)

    ctx.save()
    ctx.strokeStyle = color
    ctx.lineWidth = lineWidth
    ctx.globalAlpha = 0.8

    if (dash) ctx.setLineDash(dash.map(d => d / globalScale))
    else ctx.setLineDash([])

    ctx.beginPath()
    if (link.curvature) {
      const mx = (src.x + tgt.x) / 2, my = (src.y + tgt.y) / 2
      const dx = tgt.x - src.x, dy = tgt.y - src.y
      ctx.moveTo(src.x, src.y)
      ctx.quadraticCurveTo(mx - dy * link.curvature, my + dx * link.curvature, tgt.x, tgt.y)
    } else {
      ctx.moveTo(src.x, src.y)
      ctx.lineTo(tgt.x, tgt.y)
    }
    ctx.stroke()
    ctx.restore()

    // Arrow
    const arrowLen = Math.max(5 / globalScale, 3)
    const angle = Math.atan2(tgt.y - src.y, tgt.x - src.x)
    const tgtR = nodeRadius(tgt)
    const ax = tgt.x - Math.cos(angle) * (tgtR + 2)
    const ay = tgt.y - Math.sin(angle) * (tgtR + 2)
    ctx.beginPath()
    ctx.moveTo(ax, ay)
    ctx.lineTo(ax - arrowLen * Math.cos(angle - Math.PI / 6), ay - arrowLen * Math.sin(angle - Math.PI / 6))
    ctx.lineTo(ax - arrowLen * Math.cos(angle + Math.PI / 6), ay - arrowLen * Math.sin(angle + Math.PI / 6))
    ctx.closePath()
    ctx.fillStyle = color
    ctx.fill()

    // Edge label
    if (globalScale > 0.8 && link.label) {
      const lx = (src.x + tgt.x) / 2, ly = (src.y + tgt.y) / 2
      ctx.font = `${Math.max(7, 9 / globalScale)}px sans-serif`
      ctx.fillStyle = 'rgba(148,163,184,0.8)'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'bottom'
      ctx.fillText(link.label, lx, ly - 3 / globalScale)
    }
  }, [])

  const nodeLabel = useCallback((node) => {
    if (node.type === 'context') {
      return `<div style="background:#1e293b;padding:6px 10px;border-radius:6px;border:1px solid ${node.color || '#475569'}">
        <b style="color:${node.color || '#94a3b8'}">${node.label}</b><br/>
        <span style="color:#94a3b8">${node.concept_count} concepts</span><br/>
        <span style="color:#64748b;font-size:11px">double-click to explore</span>
      </div>`
    }
    return `<div style="background:#1e293b;padding:6px 10px;border-radius:6px;border:1px solid ${node.color}">
      <b style="color:${node.color}">${node.label}</b><br/>
      <span style="color:#64748b;font-size:11px">${node.id}</span><br/>
      <span style="color:#94a3b8">${node.balance_type || ''} · ${node.unit_type || ''}</span>
      ${node.is_total ? '<br/><span style="color:#f59e0b">TOTAL</span>' : ''}
    </div>`
  }, [])

  return (
    <div ref={containerRef} style={{ width: '100%', height: '100%', background: '#0f172a' }}>
      <ForceGraph2D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={data}
        nodeId="id"
        nodeCanvasObject={paintNode}
        nodePointerAreaPaint={(node, color, ctx) => {
          if (node.x == null || node.y == null) return
          const r = nodeRadius(node)
          ctx.beginPath()
          ctx.arc(node.x, node.y, r + 3, 0, 2 * Math.PI)
          ctx.fillStyle = color
          ctx.fill()
        }}
        linkCanvasObject={paintLink}
        linkPointerAreaPaint={(link, color, ctx) => {
          const src = link.source, tgt = link.target
          if (src.x == null || tgt.x == null) return
          ctx.beginPath()
          ctx.strokeStyle = color
          ctx.lineWidth = 8
          ctx.moveTo(src.x, src.y)
          ctx.lineTo(tgt.x, tgt.y)
          ctx.stroke()
        }}
        onNodeClick={onNodeClick}
        onNodeDragEnd={node => { node.fx = node.x; node.fy = node.y }}
        onLinkClick={onLinkClick}
        nodeLabel={nodeLabel}
        linkLabel={link => link.edge_name || ''}
        backgroundColor="#0f172a"
        d3AlphaDecay={0.03}
        d3VelocityDecay={0.3}
        cooldownTime={2000}
        enableNodeDrag={true}
        linkDirectionalArrowLength={0}
        onNodeRightClick={(node, event) => {
          event.preventDefault()
          if (node.type === 'concept') onNodeDblClick?.(node)
        }}
      />
      <DblClickHandler containerRef={containerRef} fgRef={fgRef} onNodeDblClick={onNodeDblClick} data={data} />
    </div>
  )
})

function DblClickHandler({ containerRef, fgRef, onNodeDblClick, data }) {
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const canvas = el.querySelector('canvas')
    if (!canvas) return

    let lastClick = 0
    const handler = (e) => {
      const now = Date.now()
      if (now - lastClick < 350) {
        const fg = fgRef.current
        if (!fg) return
        const coords = fg.screen2GraphCoords(e.offsetX, e.offsetY)
        let nearest = null, minDist = Infinity
        data.nodes.forEach(n => {
          if (n.x == null) return
          const d = Math.hypot(n.x - coords.x, n.y - coords.y)
          const r = nodeRadius(n)
          if (d < r + 8 && d < minDist) {
            minDist = d
            nearest = n
          }
        })
        if (nearest) onNodeDblClick?.(nearest)
      }
      lastClick = now
    }

    canvas.addEventListener('click', handler)
    return () => canvas.removeEventListener('click', handler)
  }, [containerRef, fgRef, onNodeDblClick, data])

  return null
}

export default GraphPane
