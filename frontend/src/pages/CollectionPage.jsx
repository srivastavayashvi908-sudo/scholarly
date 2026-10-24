import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, highlightColor, TAGS } from '../api'
import { useAuth } from '../auth'
import { StatusChip } from './Library'

export default function CollectionPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const [c, setC] = useState(null)
  const [tab, setTab] = useState('Papers')
  const [error, setError] = useState(null)

  useEffect(() => { api.get(`/collections/${id}`).then(setC).catch(e => setError(e.message)) }, [id])
  if (error) return <div className="error">{error}</div>
  if (!c) return <div className="muted">Loading…</div>
  const canEdit = c.role !== 'viewer'

  const remove = async () => {
    if (!window.confirm('Delete this collection? The papers themselves are kept.')) return
    await api.del(`/collections/${id}`); nav('/collections')
  }

  return (
    <div>
      <div className="page-head">
        <div className="small"><Link to="/collections">← Collections</Link></div>
        <div className="spread" style={{ marginTop: 6 }}>
          <h1>{c.name}</h1>
          <div className="row">
            <span className="chip">{c.role === 'owner' ? 'owner' : `${c.role} · owned by ${c.owner_name}`}</span>
            {c.role === 'owner' && <button className="danger small" onClick={remove}>Delete</button>}
          </div>
        </div>
        {c.description && <div className="muted">{c.description}</div>}
      </div>
      <div className="tabs">
        {['Papers', 'Comparison', 'Highlights', 'Sharing'].map(t => (
          <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>{t}</button>
        ))}
      </div>
      {tab === 'Papers' && <Papers id={id} canEdit={canEdit} />}
      {tab === 'Comparison' && <Comparison id={id} />}
      {tab === 'Highlights' && <VirtualDocument id={id} canEdit={canEdit} />}
      {tab === 'Sharing' && <Sharing id={id} role={c.role} />}
    </div>
  )
}

function Papers({ id, canEdit }) {
  const [papers, setPapers] = useState([])
  const [all, setAll] = useState([])
  const [pick, setPick] = useState('')
  const load = () => api.get(`/collections/${id}/papers`).then(setPapers)
  useEffect(() => { load(); api.get('/papers').then(setAll) }, [id])
  const add = async (e) => { e.preventDefault(); await api.post(`/collections/${id}/papers/${pick}`); setPick(''); load() }
  const remove = async (pid) => { await api.del(`/collections/${id}/papers/${pid}`); load() }

  return (
    <div className="stack">
      {canEdit && (
        <form className="row" onSubmit={add}>
          <select value={pick} onChange={e => setPick(e.target.value)} required style={{ flex: 1, minWidth: 0, maxWidth: 500 }}>
            <option value="">Add a paper from your library…</option>
            {all.filter(p => !papers.some(x => x.id === p.id)).map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
          </select>
          <button className="primary">Add</button>
        </form>
      )}
      {papers.length === 0 && <div className="muted">No papers in this collection yet.</div>}
      <div className="list">
        {papers.map(p => (
          <div key={p.id} className="item spread">
            <div>
              <Link to={`/papers/${p.id}`} style={{ fontWeight: 600 }}>{p.title}</Link>
              <div className="small muted">{[p.authors, p.year].filter(Boolean).join(' · ')} · {p.highlight_count} highlights</div>
            </div>
            <div className="row">
              <StatusChip status={p.status} />
              {canEdit && <button className="link small" onClick={() => remove(p.id)}>Remove</button>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Comparison({ id }) {
  const [data, setData] = useState(null)
  useEffect(() => { api.get(`/collections/${id}/comparison`).then(setData) }, [id])
  if (!data) return <div className="muted">Loading…</div>
  if (!data.rows.length) return <div className="muted">Add papers to this collection first.</div>
  return (
    <div className="stack">
      <div className="muted small">
        Built automatically from each paper's <b>comparison attributes</b> (Info tab on the paper page). Rows = papers, columns = attributes.
      </div>
      {data.columns.length === 0
        ? <div className="card muted small">No attributes yet. Open a paper → Info → add e.g. <i>dataset = ImageNet</i>, <i>metric = F1 0.89</i>.</div>
        : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th>Paper</th><th>Year</th>{data.columns.map(c => <th key={c}>{c}</th>)}</tr>
              </thead>
              <tbody>
                {data.rows.map(r => (
                  <tr key={r.id}>
                    <td><Link to={`/papers/${r.id}`}>{r.title}</Link></td>
                    <td>{r.year ?? '—'}</td>
                    {data.columns.map(c => <td key={c}>{r.attributes[c] ?? <span className="muted">—</span>}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  )
}

function VirtualDocument({ id, canEdit }) {
  const [hs, setHs] = useState(null)
  const load = () => api.get(`/collections/${id}/highlights`).then(setHs)
  useEffect(() => { load() }, [id])
  if (!hs) return <div className="muted">Loading…</div>
  if (!hs.length) return <div className="muted">No highlights here yet. On a paper, use “Add to collection…” under any highlight.</div>

  const groups = {}
  hs.forEach(h => (groups[h.tag || 'untagged'] ||= []).push(h))
  return (
    <div className="stack" style={{ maxWidth: 820 }}>
      <div className="muted small">Highlights from different papers gathered into one document, grouped by tag.</div>
      {Object.entries(groups).map(([tag, items]) => (
        <div key={tag}>
          <h2>{TAGS[tag]?.label || 'Untagged'}</h2>
          <div className="list">
            {items.map(h => (
              <div key={h.id} className="hl-item" style={{ borderLeftColor: highlightColor(h) }}>
                <blockquote>“{h.quote}”</blockquote>
                <div className="spread small">
                  <span className="muted">
                    <Link to={`/papers/${h.paper_id}`}>{h.paper_title}</Link>{h.page ? `, p. ${h.page}` : ''} · {h.user_name}
                  </span>
                  {canEdit && <button className="link small" onClick={() => api.del(`/collections/${id}/highlights/${h.id}`).then(load)}>Remove</button>}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function Sharing({ id, role }) {
  const { user } = useAuth()
  const nav = useNavigate()
  const [members, setMembers] = useState([])
  const [email, setEmail] = useState('')
  const [newRole, setNewRole] = useState('viewer')
  const [error, setError] = useState(null)
  const load = () => api.get(`/collections/${id}/members`).then(setMembers)
  useEffect(() => { load() }, [id])

  const share = async (e) => {
    e.preventDefault(); setError(null)
    try { setMembers(await api.put(`/collections/${id}/members`, { email, role: newRole })); setEmail('') } catch (err) { setError(err.message) }
  }
  const changeRole = async (m, r) => setMembers(await api.put(`/collections/${id}/members`, { email: m.email, role: r }))
  const removeMember = async (m) => {
    await api.del(`/collections/${id}/members/${m.user_id}`)
    if (m.user_id === user.id) nav('/collections'); else load()
  }

  return (
    <div className="stack" style={{ maxWidth: 640 }}>
      <div className="muted small">
        <b>Viewers</b> can read the papers, add their own highlights and comment. <b>Editors</b> can also add/remove papers and edit paper details.
        Everyone sees each other's highlights; notes stay private.
      </div>
      {role === 'owner' && (
        <form className="row" onSubmit={share}>
          <input type="email" placeholder="classmate@email.com" value={email} onChange={e => setEmail(e.target.value)} required style={{ flex: 1, minWidth: 180 }} />
          <select value={newRole} onChange={e => setNewRole(e.target.value)}><option value="viewer">Viewer</option><option value="editor">Editor</option></select>
          <button className="primary">Share</button>
        </form>
      )}
      {error && <div className="error">{error}</div>}
      <div className="list">
        {members.map(m => (
          <div key={m.user_id} className="item spread">
            <div><b>{m.name}</b> <span className="muted small">{m.email}</span></div>
            <div className="row">
              {m.role === 'owner' ? <span className="chip">owner</span> : role === 'owner' ? (
                <select value={m.role} onChange={e => changeRole(m, e.target.value)}><option value="viewer">Viewer</option><option value="editor">Editor</option></select>
              ) : <span className="chip">{m.role}</span>}
              {m.role !== 'owner' && (role === 'owner' || m.user_id === user.id) && (
                <button className="link small" style={{ color: 'var(--danger)' }} onClick={() => removeMember(m)}>
                  {m.user_id === user.id ? 'Leave' : 'Remove'}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
