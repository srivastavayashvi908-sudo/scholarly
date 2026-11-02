import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, DIFFICULTY_COLOR } from '../api'
import Graph from '../components/Graph'


export default function Concepts() {
  const [graph, setGraph] = useState({ nodes: [], edges: [] })
  const [selected, setSelected] = useState(null)
  const [form, setForm] = useState({ name: '', description: '', difficulty: '' })
  const [error, setError] = useState(null)

  const load = () => api.get('/concepts/graph').then(setGraph)
  useEffect(() => { load() }, [])

  const create = async (e) => {
    e.preventDefault(); setError(null)
    try {
      const c = await api.post('/concepts', { ...form, difficulty: form.difficulty || null })
      setForm({ name: '', description: '', difficulty: '' }); await load(); setSelected(c.id)
    } catch (err) { setError(err.message) }
  }

  return (
    <div>
      <div className="page-head">
        <h1>Concepts</h1>
        <div className="muted">Build a prerequisite graph: arrows point from a concept to what you need to know first. Click a node to see its full learning path.</div>
      </div>
      <div className="paper-layout">
        <div className="stack">
          {graph.nodes.length ? (
            <Graph
              nodes={graph.nodes.map(n => ({ id: n.id, label: n.name, difficulty: n.difficulty, deps: n.dependent_count }))}
              edges={graph.edges}
              selectedId={selected}
              highlightIds={selected ? chainIds(selected, graph.edges) : null}
              onNodeClick={(n) => setSelected(n.id)}
              nodeColor={(n) => DIFFICULTY_COLOR[n.difficulty] || '#2a78d6'}
              nodeSize={(n) => 5 + Math.min(n.deps, 6)}
            />
          ) : <div className="card muted">No concepts yet. Add one on the right.</div>}
          <div className="row small muted">
            {Object.entries(DIFFICULTY_COLOR).map(([k, c]) => <span key={k} className="row"><span className="dot" style={{ background: c }} />{k}</span>)}
            <span className="row"><span className="dot" style={{ background: '#2a78d6' }} />unspecified</span>
            <span>· bigger node = more concepts depend on it</span>
          </div>
        </div>
        <div className="card side-panel stack">
          {selected
            ? <ConceptDetail id={selected} all={graph.nodes} onChange={load} onSelect={setSelected} />
            : <div className="muted small">Select a concept in the graph.</div>}
          <hr style={{ border: 'none', borderTop: '1px solid var(--border)', width: '100%' }} />
          <form className="stack" onSubmit={create}>
            <h3>New concept</h3>
            <input placeholder="e.g. Self-attention" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
            <textarea placeholder="Short description (optional)" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
            <select value={form.difficulty} onChange={e => setForm({ ...form, difficulty: e.target.value })}>
              <option value="">Difficulty…</option><option>beginner</option><option>intermediate</option><option>advanced</option>
            </select>
            {error && <div className="error">{error}</div>}
            <button className="primary">Add concept</button>
          </form>
        </div>
      </div>
    </div>
  )
}

// All concepts reachable from `start` along prerequisite edges (client-side, for graph highlighting).
function chainIds(start, edges) {
  const seen = new Set([start]); const stack = [start]
  while (stack.length) {
    const cur = stack.pop()
    edges.filter(e => e.source === cur).forEach(e => { if (!seen.has(e.target)) { seen.add(e.target); stack.push(e.target) } })
  }
  return [...seen]
}

function ConceptDetail({ id, all, onChange, onSelect }) {
  const [c, setC] = useState(null)
  const [chain, setChain] = useState(null)
  const [similar, setSimilar] = useState([])
  const [prereq, setPrereq] = useState('')
  const [error, setError] = useState(null)

  const load = () => {
    api.get(`/concepts/${id}`).then(setC)
    api.get(`/concepts/${id}/prerequisites`).then(setChain)
    api.get(`/concepts/${id}/similar`).then(setSimilar)
  }
  useEffect(() => { setError(null); load() }, [id])

  const addPrereq = async (e) => {
    e.preventDefault(); setError(null)
    try { await api.post(`/concepts/${id}/prerequisites`, { prerequisite_id: prereq }); setPrereq(''); load(); onChange() }
    catch (err) { setError(err.message) }
  }
  const removePrereq = async (pid) => { await api.del(`/concepts/${id}/prerequisites/${pid}`); load(); onChange() }
  const remove = async () => { await api.del(`/concepts/${id}`); onSelect(null); onChange() }
  const toggleKnown = async () => { setC({ ...c, ...(await api.put(`/concepts/${id}/known`, { known: !c.known })) }) }

  if (!c || !chain) return <div className="muted">Loading…</div>
  return (
    <div className="stack">
      <div className="spread">
        <h2 style={{ margin: 0 }}>{c.name}</h2>
        <button className="link small" style={{ color: 'var(--danger)' }} onClick={remove}>Delete</button>
      </div>
      <div className="row">
        {c.difficulty && <span className="chip">{c.difficulty}</span>}
        {c.source === 'ai' && <span className="chip" title="Added by the AI from a paper">✨ AI</span>}
        <label className="small row" style={{ gap: 4 }}>
          <input type="checkbox" checked={c.known} onChange={toggleKnown} /> I already know this
        </label>
      </div>
      {c.description && <div>{c.description}</div>}

      <div>
        <h3>Learning path ({chain.learning_order.length} prerequisites)</h3>
        <div className="muted small" style={{ marginBottom: 6 }}>Full chain from a recursive SQL query, in the order to learn it.</div>
        {chain.learning_order.length === 0 && <div className="small muted">No prerequisites.</div>}
        <ol style={{ margin: 0, paddingLeft: 20 }}>
          {chain.learning_order.map(p => (
            <li key={p.id} className="small" style={{ padding: '2px 0' }}>
              <button className="link small" onClick={() => onSelect(p.id)}>{p.name}</button>
            </li>
          ))}
          <li className="small" style={{ padding: '2px 0' }}><b>{c.name}</b></li>
        </ol>
      </div>

      <div>
        <h3>Direct prerequisites</h3>
        {c.direct_prerequisites.map(p => (
          <div key={p.id} className="spread small" style={{ padding: '2px 0' }}>
            <span>{p.name}</span><button className="link small" onClick={() => removePrereq(p.id)}>×</button>
          </div>
        ))}
        <form className="row" onSubmit={addPrereq} style={{ marginTop: 6 }}>
          <select value={prereq} onChange={e => setPrereq(e.target.value)} required style={{ flex: 1, minWidth: 0 }}>
            <option value="">Requires…</option>
            {all.filter(o => o.id !== id && !c.direct_prerequisites.some(p => p.id === o.id))
              .map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
          <button className="small">Add</button>
        </form>
        {error && <div className="error small" style={{ marginTop: 6 }}>{error}</div>}
      </div>

      <div>
        <h3>Papers</h3>
        {c.papers.length === 0 && <div className="small muted">Link papers to this concept from a paper's Info tab.</div>}
        {c.papers.map(p => (
          <div key={p.id} className="small" style={{ padding: '2px 0' }}>
            <span className="chip">{p.relation}</span> <Link to={`/papers/${p.id}`}>{p.title}</Link>
          </div>
        ))}
      </div>

      {similar.length > 0 && (
        <div>
          <h3>Related concepts</h3>
          <div className="row">
            {similar.map(s => <button key={s.id} className="small" onClick={() => onSelect(s.id)}>{s.name}</button>)}
          </div>
        </div>
      )}
    </div>
  )
}
