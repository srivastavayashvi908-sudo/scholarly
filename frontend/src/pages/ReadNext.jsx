import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { StatusChip } from './Library'

export default function ReadNext() {
  const [data, setData] = useState(null)
  useEffect(() => { api.get('/recommendations').then(setData) }, [])
  if (!data) return <div className="muted">Working out what you're ready for…</div>

  return (
    <div style={{ maxWidth: 900 }}>
      <div className="page-head">
        <h1>What should I read next?</h1>
        <div className="muted">
          A paper is <b>ready</b> when you've already learned every concept it assumes, from papers you've marked
          <i> done</i> plus their prerequisites. Link concepts to papers in each paper's Info tab.
        </div>
      </div>

      <h2>✅ Ready to read ({data.ready.length})</h2>
      <div className="list" style={{ marginBottom: 24 }}>
        {data.ready.length === 0 && <div className="muted small">Nothing yet. Finish a paper or link concepts to papers.</div>}
        {data.ready.map(p => (
          <div key={p.id} className="item">
            <div className="spread">
              <Link to={`/papers/${p.id}`} style={{ fontWeight: 600 }}>{p.title}</Link>
              <StatusChip status={p.status} />
            </div>
            <div className="small muted" style={{ marginTop: 4 }}>
              {p.teaches.length ? <>Teaches you: {p.teaches.join(', ')}</> : p.concept_links ? 'No new concepts.' : 'No concepts linked yet.'}
            </div>
          </div>
        ))}
      </div>

      <h2>🔒 Not ready yet ({data.blocked.length})</h2>
      <div className="list">
        {data.blocked.map(p => (
          <div key={p.id} className="item">
            <div className="spread">
              <Link to={`/papers/${p.id}`} style={{ fontWeight: 600 }}>{p.title}</Link>
              <StatusChip status={p.status} />
            </div>
            <div className="small" style={{ marginTop: 6 }}>
              {p.missing.map(m => (
                <div key={m.id} style={{ padding: '2px 0' }}>
                  Missing <b>{m.name}</b>
                  {m.read_first.length
                    ? <> → read first: {m.read_first.map((t, i) => <span key={t.id}>{i > 0 && ', '}<Link to={`/papers/${t.id}`}>{t.title}</Link></span>)}</>
                    : <span className="muted"> (no paper in your library introduces it)</span>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
