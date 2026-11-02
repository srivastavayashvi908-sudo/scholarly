import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, DIFFICULTY_COLOR } from '../api'
import Graph from './Graph'

const PAPER_COLOR = '#6250d6'
const KNOWN_COLOR = '#1baf7a'
const TODO_COLOR = '#eda100'

/** "Before you read this paper": AI-extracted concepts, what to learn first, and a mini graph. */
export default function LearnFirst({ paper }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const [hideKnown, setHideKnown] = useState(false)

  const load = () => api.get(`/papers/${paper.id}/learning-path`).then(setData).catch(e => setError(e.message))
  useEffect(() => { setData(null); setMessage(null); setError(null); load() }, [paper.id])

  const extract = async () => {
    setBusy(true); setError(null); setMessage(null)
    try {
      const r = await api.post(`/papers/${paper.id}/extract-concepts`)
      setMessage(`Found ${r.concepts_found} concepts (${r.new_concepts} new to your graph) and ` +
                 `${r.links_added} new prerequisite links.` +
                 (r.cycles_skipped ? ` Skipped ${r.cycles_skipped} that would have made a loop.` : ''))
      await load()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  const toggleKnown = async (c) => {
    await api.put(`/concepts/${c.id}/known`, { known: !c.known })
    load()
  }

  if (!data) return <div className="muted">{error ? <span className="error">{error}</span> : 'Loading…'}</div>

  const { paper_concepts: used, learn_first: before, edges } = data
  const knownCount = before.filter(c => c.known).length
  const shown = hideKnown ? before.filter(c => !c.known) : before
  const paperIds = new Set(used.map(c => c.id))
  // Concepts the paper assumes are in both lists; one node each.
  const byId = new Map([...before, ...used].map(c => [c.id, c]))
  const teaches = new Set(used.filter(c => c.relation === 'introduces').map(c => c.id))
  const nodes = [...byId.values()].map(c => ({ id: c.id, label: c.name, known: c.known, ofPaper: paperIds.has(c.id) }))

  return (
    <div className="stack">
      <div>
        <h3>Before you read this paper</h3>
        <div className="muted small">
          The AI reads the paper, finds the concepts it uses, and works out everything you need to know first,
          down to the basics. It all goes into your <Link to="/concepts">concept graph</Link>.
        </div>
      </div>
      <button className="primary small" onClick={extract} disabled={busy}>
        {busy ? 'Reading the paper… (up to a minute)' : used.length ? '↻ Re-extract concepts' : '✨ Extract concepts with AI'}
      </button>
      {message && <div className="card small">{message}</div>}
      {error && <div className="error small">{error}</div>}

      {used.length === 0 ? (
        <div className="muted small">No concepts linked to this paper yet.</div>
      ) : (
        <>
          <div>
            <h3>This paper</h3>
            <div className="row">
              {used.map(c => (
                <span key={c.id} className="chip" title={c.description || ''}>
                  {c.relation === 'introduces' ? '★ teaches' : 'assumes'} · {c.name}
                </span>
              ))}
            </div>
          </div>

          <div>
            <div className="spread">
              <h3 style={{ margin: 0 }}>Learn these first ({before.length})</h3>
              <label className="small row" style={{ gap: 4 }}>
                <input type="checkbox" checked={hideKnown} onChange={e => setHideKnown(e.target.checked)} /> hide known
              </label>
            </div>
            {before.length > 0 && (
              <div style={{ margin: '8px 0' }}>
                <div className="small muted">You know {knownCount} of {before.length}</div>
                <div className="progress"><div style={{ width: `${(knownCount / before.length) * 100}%` }} /></div>
              </div>
            )}
            {before.length === 0 && <div className="small muted">Nothing to learn first. You're ready to read it.</div>}
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              {shown.map(c => (
                <li key={c.id} style={{ padding: '5px 0', opacity: c.known ? 0.55 : 1 }}>
                  <label className="row" style={{ gap: 6, alignItems: 'flex-start', flexWrap: 'nowrap' }}>
                    <input type="checkbox" checked={c.known} onChange={() => toggleKnown(c)} title="I already know this" style={{ marginTop: 3 }} />
                    <span>
                      <span style={{ fontWeight: 600, textDecoration: c.known ? 'line-through' : 'none' }}>{c.name}</span>{' '}
                      {c.difficulty && <span className="chip" style={{ color: DIFFICULTY_COLOR[c.difficulty] }}>{c.difficulty}</span>}
                      {c.description && <div className="small muted">{c.description}</div>}
                      {c.taught_by.length > 0 && (
                        <div className="small">Explained in: {c.taught_by.map((p, i) => (
                          <span key={p.id}>{i > 0 && ', '}<Link to={`/papers/${p.id}`}>{p.title}</Link></span>
                        ))}</div>
                      )}
                    </span>
                  </label>
                </li>
              ))}
            </ol>
            {before.length > 0 && <div className="small muted" style={{ marginTop: 6 }}>Tick what you already know. It also counts for “Read next”.</div>}
          </div>

          <div>
            <h3>Graph</h3>
            <div className="small muted" style={{ marginBottom: 6 }}>
              Arrows point to what you need first. Hover a dot to see its name; scroll to zoom.
              The full graph is on the <Link to="/concepts">Concepts</Link> page.
            </div>
            <Graph
              nodes={nodes}
              edges={edges}
              height={340}
              showLabel={(n) => teaches.has(n.id) || nodes.length <= 15}
              nodeColor={(n) => (n.ofPaper ? PAPER_COLOR : n.known ? KNOWN_COLOR : TODO_COLOR)}
              nodeSize={(n) => (n.ofPaper ? 8 : 5)}
            />
            <div className="row small muted" style={{ marginTop: 6 }}>
              <span className="row"><span className="dot" style={{ background: PAPER_COLOR }} />this paper</span>
              <span className="row"><span className="dot" style={{ background: TODO_COLOR }} />to learn</span>
              <span className="row"><span className="dot" style={{ background: KNOWN_COLOR }} />known</span>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
