import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

export function NotesPanel({ paperId }) {
  const [notes, setNotes] = useState([])
  const [content, setContent] = useState('')
  const [editing, setEditing] = useState(null)
  const load = () => api.get(`/papers/${paperId}/notes`).then(setNotes)
  useEffect(() => { load() }, [paperId])

  const add = async (e) => {
    e.preventDefault()
    await api.post(`/papers/${paperId}/notes`, { content }); setContent(''); load()
  }
  const save = async () => { await api.patch(`/notes/${editing.id}`, { content: editing.content }); setEditing(null); load() }
  const remove = async (id) => { await api.del(`/notes/${id}`); load() }

  return (
    <div className="stack">
      <form className="stack" onSubmit={add}>
        <textarea placeholder="Your private notes on this paper…" value={content} onChange={e => setContent(e.target.value)} required />
        <button className="primary small">Add note</button>
      </form>
      {notes.map(n => (
        <div key={n.id} className="item">
          {editing?.id === n.id ? (
            <div className="stack">
              <textarea value={editing.content} onChange={e => setEditing({ ...editing, content: e.target.value })} />
              <div className="row"><button className="primary small" onClick={save}>Save</button><button className="small" onClick={() => setEditing(null)}>Cancel</button></div>
            </div>
          ) : (
            <>
              <div style={{ whiteSpace: 'pre-wrap' }}>{n.content}</div>
              <div className="spread small" style={{ marginTop: 6 }}>
                <span className="muted">{new Date(n.updated_at).toLocaleString()}</span>
                <div className="row">
                  <button className="link small" onClick={() => setEditing(n)}>Edit</button>
                  <button className="link small" style={{ color: 'var(--danger)' }} onClick={() => remove(n.id)}>Delete</button>
                </div>
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  )
}

export function InfoPanel({ paper, onChange }) {
  const canEdit = paper.role !== 'viewer'
  const [summarizing, setSummarizing] = useState(false)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(false)

  const summarize = async () => {
    setSummarizing(true); setError(null)
    try { await api.post(`/papers/${paper.id}/summarize`); onChange() } catch (e) { setError(e.message) } finally { setSummarizing(false) }
  }

  return (
    <div className="stack">
      {editing ? <EditPaper paper={paper} onDone={() => { setEditing(false); onChange() }} /> : (
        <>
          {canEdit && <button className="small" onClick={() => setEditing(true)}>Edit details</button>}
          <div>
            <h3>AI summary</h3>
            {paper.summary
              ? <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{paper.summary}</div>
              : <div className="muted small">No summary yet.</div>}
            {canEdit && (
              <button className="small" style={{ marginTop: 8 }} onClick={summarize} disabled={summarizing}>
                {summarizing ? 'Summarizing…' : paper.summary ? '↻ Regenerate summary' : '✨ Summarize with AI'}
              </button>
            )}
            {error && <div className="error small" style={{ marginTop: 8 }}>{error}</div>}
          </div>
          <div>
            <h3>Abstract</h3>
            <div style={{ lineHeight: 1.5 }} className={paper.abstract ? '' : 'muted small'}>{paper.abstract || 'No abstract.'}</div>
          </div>
          {paper.doi && <div className="small">DOI: <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer">{paper.doi}</a></div>}
        </>
      )}
      <Attributes paper={paper} canEdit={canEdit} />
      <PaperConcepts paperId={paper.id} />
    </div>
  )
}

function EditPaper({ paper, onDone }) {
  const [form, setForm] = useState({
    title: paper.title, authors: paper.authors || '', year: paper.year || '', venue: paper.venue || '',
    doi: paper.doi || '', abstract: paper.abstract || '', pdf_url: paper.pdf_url || '',
  })
  const [error, setError] = useState(null)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })
  const save = async (e) => {
    e.preventDefault()
    const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === '' ? null : v]))
    body.title = form.title
    if (body.year) body.year = Number(body.year)
    try { await api.patch(`/papers/${paper.id}`, body); onDone() } catch (err) { setError(err.message) }
  }
  return (
    <form className="stack" onSubmit={save}>
      {['title', 'authors', 'year', 'venue', 'doi', 'pdf_url'].map(k => (
        <label key={k} className="field">{k.replace('_', ' ')}<input value={form[k]} onChange={set(k)} required={k === 'title'} /></label>
      ))}
      <label className="field">abstract<textarea value={form.abstract} onChange={set('abstract')} rows={6} /></label>
      {error && <div className="error">{error}</div>}
      <div className="row"><button className="primary small">Save</button><button type="button" className="small" onClick={onDone}>Cancel</button></div>
    </form>
  )
}

function Attributes({ paper, canEdit }) {
  const [attrs, setAttrs] = useState([])
  const [name, setName] = useState('')
  const [value, setValue] = useState('')
  const load = () => api.get(`/papers/${paper.id}/attributes`).then(setAttrs)
  useEffect(() => { load() }, [paper.id])
  const add = async (e) => {
    e.preventDefault()
    await api.put(`/papers/${paper.id}/attributes`, { attr_name: name, attr_value: value }); setName(''); setValue(''); load()
  }
  return (
    <div>
      <h3>Comparison attributes</h3>
      <div className="muted small" style={{ marginBottom: 6 }}>Shown side by side in collection comparison tables.</div>
      {attrs.map(a => (
        <div key={a.id} className="spread small" style={{ padding: '3px 0' }}>
          <span><b>{a.attr_name}</b>: {a.attr_value}</span>
          {canEdit && <button className="link small" onClick={() => api.del(`/papers/${paper.id}/attributes/${a.id}`).then(load)}>×</button>}
        </div>
      ))}
      {canEdit && (
        <form className="row" onSubmit={add} style={{ marginTop: 6 }}>
          <input placeholder="dataset" value={name} onChange={e => setName(e.target.value)} required style={{ width: 100 }} />
          <input placeholder="ImageNet" value={value} onChange={e => setValue(e.target.value)} required style={{ flex: 1, minWidth: 80 }} />
          <button className="small">Set</button>
        </form>
      )}
    </div>
  )
}

function PaperConcepts({ paperId }) {
  const [linked, setLinked] = useState([])
  const [all, setAll] = useState([])
  const [conceptId, setConceptId] = useState('')
  const [relation, setRelation] = useState('introduces')
  const load = () => api.get(`/papers/${paperId}/concepts`).then(setLinked)
  useEffect(() => { load(); api.get('/concepts').then(setAll) }, [paperId])
  const add = async (e) => {
    e.preventDefault()
    await api.put(`/papers/${paperId}/concepts`, { concept_id: conceptId, relation }); setConceptId(''); load()
  }
  return (
    <div>
      <h3>Concepts</h3>
      <div className="muted small" style={{ marginBottom: 6 }}>Used by “Read next” to work out what you're ready for.</div>
      {linked.map(c => (
        <div key={c.id} className="spread small" style={{ padding: '3px 0' }}>
          <span><span className="chip">{c.relation}</span> {c.name}</span>
          <button className="link small" onClick={() => api.del(`/papers/${paperId}/concepts/${c.id}`).then(load)}>×</button>
        </div>
      ))}
      {all.length === 0 ? (
        <div className="small muted">Create concepts on the <Link to="/concepts">Concepts</Link> page first.</div>
      ) : (
        <form className="row" onSubmit={add} style={{ marginTop: 6 }}>
          <select value={relation} onChange={e => setRelation(e.target.value)}>
            <option value="introduces">introduces</option>
            <option value="assumes">assumes</option>
          </select>
          <select value={conceptId} onChange={e => setConceptId(e.target.value)} required style={{ flex: 1, minWidth: 0 }}>
            <option value="">Concept…</option>
            {all.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button className="small">Link</button>
        </form>
      )}
    </div>
  )
}

export function SimilarPanel({ paperId }) {
  const [similar, setSimilar] = useState(null)
  useEffect(() => { api.get(`/papers/${paperId}/similar`).then(setSimilar).catch(() => setSimilar([])) }, [paperId])
  if (!similar) return <div className="muted">Finding similar papers…</div>
  if (!similar.length) return <div className="muted small">Add more papers with abstracts to see similar ones here.</div>
  return (
    <div className="stack">
      <div className="muted small">Ranked by meaning (embedding cosine similarity), not just shared keywords.</div>
      {similar.map(s => (
        <Link key={s.id} to={`/papers/${s.id}`} className="item" style={{ color: 'inherit', display: 'block' }}>
          <div style={{ fontWeight: 600 }}>{s.title}</div>
          <div className="spread small">
            <span className="muted">{s.year}</span>
            <span>{Math.round(s.similarity * 100)}% similar</span>
          </div>
          <div className="progress" style={{ marginTop: 4 }}><div style={{ width: `${Math.max(0, s.similarity) * 100}%` }} /></div>
        </Link>
      ))}
    </div>
  )
}

export function CitationsPanel({ paper }) {
  const [data, setData] = useState(null)
  const [lineage, setLineage] = useState([])
  const [papers, setPapers] = useState([])
  const [cited, setCited] = useState('')
  const load = () => {
    api.get(`/papers/${paper.id}/citations`).then(setData)
    api.get(`/papers/${paper.id}/citation-lineage`).then(setLineage)
  }
  useEffect(() => { load(); api.get('/papers').then(setPapers) }, [paper.id])
  const add = async (e) => {
    e.preventDefault(); await api.post(`/papers/${paper.id}/citations`, { cited_paper_id: cited }); setCited(''); load()
  }
  if (!data) return null
  const canEdit = paper.role !== 'viewer'

  return (
    <div className="stack">
      <div>
        <h3>Cites ({data.cites.length})</h3>
        {data.cites.map(p => (
          <div key={p.id} className="spread small" style={{ padding: '3px 0' }}>
            <Link to={`/papers/${p.id}`}>{p.title}</Link>
            {canEdit && <button className="link small" onClick={() => api.del(`/papers/${paper.id}/citations/${p.id}`).then(load)}>×</button>}
          </div>
        ))}
        {canEdit && (
          <form className="row" onSubmit={add} style={{ marginTop: 6 }}>
            <select value={cited} onChange={e => setCited(e.target.value)} required style={{ flex: 1, minWidth: 0 }}>
              <option value="">This paper cites…</option>
              {papers.filter(p => p.id !== paper.id && !data.cites.some(c => c.id === p.id))
                .map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
            </select>
            <button className="small">Add</button>
          </form>
        )}
      </div>
      <div>
        <h3>Cited by ({data.cited_by.length})</h3>
        {data.cited_by.map(p => <div key={p.id} className="small" style={{ padding: '3px 0' }}><Link to={`/papers/${p.id}`}>{p.title}</Link></div>)}
      </div>
      <div>
        <h3>Lineage: everything this builds on</h3>
        <div className="muted small" style={{ marginBottom: 6 }}>Found with a recursive SQL query over the citation graph.</div>
        {lineage.length === 0 && <div className="muted small">No citations recorded yet.</div>}
        {lineage.map(p => (
          <div key={p.id} className="small" style={{ padding: '3px 0', paddingLeft: (p.depth - 1) * 16 }}>
            <span className="chip">{p.depth === 1 ? 'direct' : `${p.depth} hops`}</span>{' '}
            <Link to={`/papers/${p.id}`}>{p.title}</Link> <span className="muted">{p.year}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
