import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const dark = () => window.matchMedia?.('(prefers-color-scheme: dark)').matches

/**
 * Interactive force-directed graph. Drag nodes, scroll to zoom, click a node to select it.
 * Edges point source -> target (e.g. "concept needs prerequisite", "paper cites paper").
 * `showLabel(n)` hides labels in busy graphs; hovering a node always shows its name.
 */
export default function Graph({ nodes, edges, onNodeClick, selectedId, highlightIds, nodeColor, nodeSize, height = 520, showLabel }) {
  const box = useRef(null)
  const fg = useRef(null)
  const [width, setWidth] = useState(600)

  useEffect(() => {
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(box.current)
    return () => ro.disconnect()
  }, [])

  // ForceGraph mutates link objects, so give it fresh copies when data changes.
  const data = useMemo(() => ({
    nodes: nodes.map(n => ({ ...n })),
    links: edges.map(e => ({ source: e.source, target: e.target })),
  }), [nodes, edges])

  // Fit the whole graph into view once the layout settles, but never zoom in so far
  // that a small graph turns into a few giant circles.
  const fitted = useRef(false)
  const settled = useRef(false)
  useEffect(() => {
    fitted.current = false
    settled.current = false
    // Spread nodes out so labels don't overlap: longer links, stronger repulsion.
    fg.current?.d3Force('link')?.distance(80)
    fg.current?.d3Force('charge')?.strength(-160)
    fg.current?.d3ReheatSimulation()
  }, [data])
  const fit = () => {
    settled.current = true
    if (fitted.current || !fg.current) return
    fitted.current = true
    fg.current.zoomToFit(0, 60)
    if (fg.current.zoom() > 2.2) fg.current.zoom(2.2)
  }
  // The first layout can finish before the box's real width is known: re-centre when it changes.
  useEffect(() => { if (settled.current) { fitted.current = false; fit() } }, [width])

  const isDark = dark()
  const text = isDark ? '#f0efec' : '#17171a'
  const edge = isDark ? 'rgba(240,239,236,0.25)' : 'rgba(23,23,26,0.22)'
  const hot = highlightIds ? new Set(highlightIds) : null

  return (
    <div ref={box} className="graph-box">
      <ForceGraph2D
        ref={fg}
        width={width}
        height={height}
        graphData={data}
        backgroundColor={isDark ? '#1a1a19' : '#ffffff'}
        linkColor={(l) => (hot && hot.has(id(l.source)) && hot.has(id(l.target)) ? '#2a78d6' : edge)}
        linkWidth={(l) => (hot && hot.has(id(l.source)) && hot.has(id(l.target)) ? 2.5 : 1)}
        linkDirectionalArrowLength={5}
        linkDirectionalArrowRelPos={0.92}
        cooldownTicks={120}
        nodeLabel={(n) => n.label}
        onEngineStop={fit}
        onNodeClick={(n) => onNodeClick?.(n)}
        nodeCanvasObject={(n, ctx, scale) => {
          const r = nodeSize ? nodeSize(n) : 6
          const dim = hot && !hot.has(n.id)
          ctx.globalAlpha = dim ? 0.3 : 1
          ctx.beginPath()
          ctx.arc(n.x, n.y, r, 0, 2 * Math.PI)
          ctx.fillStyle = nodeColor ? nodeColor(n) : '#2a78d6'
          ctx.fill()
          if (n.id === selectedId) {
            ctx.lineWidth = 2.5 / scale * 1.5
            ctx.strokeStyle = text
            ctx.stroke()
          }
          if (showLabel && !showLabel(n)) { ctx.globalAlpha = 1; return }
          const label = n.label.length > 40 ? n.label.slice(0, 38) + '…' : n.label
          ctx.font = `${Math.max(10 / scale, 3)}px Inter, sans-serif`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'top'
          ctx.fillStyle = text
          ctx.fillText(label, n.x, n.y + r + 2)
          ctx.globalAlpha = 1
        }}
        nodePointerAreaPaint={(n, color, ctx) => {
          ctx.fillStyle = color
          ctx.beginPath(); ctx.arc(n.x, n.y, (nodeSize ? nodeSize(n) : 6) + 4, 0, 2 * Math.PI); ctx.fill()
        }}
      />
    </div>
  )
}

const id = (x) => (typeof x === 'object' ? x.id : x)
