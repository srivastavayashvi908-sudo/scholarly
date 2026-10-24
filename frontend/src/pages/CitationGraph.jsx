import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import Graph from '../components/Graph'

export default function CitationGraph() {
  const [graph, setGraph] = useState(null)
  const [selected, setSelected] = useState(null)
  const [lineage, setLineage] = useState([])

  useEffect(() => { api.get('/citations/graph').then(setGraph) }, [])
  useEffect(() => {
    if (selected) api.get(`/papers/${selected}/citation-lineage`).then(setLineage)
  }, [selected])

  if (!graph) return <div className="muted">Loading…</div>
  const sel = graph.nodes.find(n => n.id === selected)

  return (
    <div>
      <div className="page-head">
        <h1>Citation graph</h1>
        <div className="muted">Arrows point from a paper to the papers it cites. Bigger nodes are cited more. Click a paper to light up its lineage.</div>
      </div>
      {graph.edges.length === 0 && (
        <div className="card muted small" style={{ marginBottom: 12 }}>
          No citations yet. Import papers by DOI (references are linked automatically) or add them in a paper's Citations tab.
        </div>
      )}
      <div className="paper-layout">
        <Graph
          nodes={graph.nodes.map(n => ({ id: n.id, label: `${n.title}${n.year ? ` (${n.year})` : ''}`, cited: n.cited_by_count }))}
          edges={graph.edges}
          selectedId={selected}
          highlightIds={selected ? [selected, ...lineage.map(l => l.id)] : null}
          onNodeClick={(n) => setSelected(n.id)}
          nodeSize={(n) => 4 + Math.min(n.cited * 2, 12)}
          height={600}
        />
        <div className="card side-panel">
          {!sel ? <div className="muted small">Select a paper.</div> : (
            <div className="stack">
              <h2 style={{ margin: 0 }}><Link to={`/papers/${sel.id}`}>{sel.title}</Link></h2>
              <div className="muted small">Cited by {sel.cited_by_count} paper(s) in your library</div>
              <h3>Builds on ({lineage.length})</h3>
              {lineage.length === 0 && <div className="muted small">Nothing recorded.</div>}
              {lineage.map(p => (
                <div key={p.id} className="small" style={{ paddingLeft: (p.depth - 1) * 14 }}>
                  <span className="chip">{p.depth === 1 ? 'direct' : `${p.depth} hops`}</span>{' '}
                  <button className="link small" onClick={() => setSelected(p.id)}>{p.title}</button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
