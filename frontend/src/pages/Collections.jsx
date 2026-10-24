import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'

export default function Collections() {
  const [collections, setCollections] = useState(null)
  const [form, setForm] = useState({ name: '', description: '' })
  const load = () => api.get('/collections').then(setCollections)
  useEffect(() => { load() }, [])

  const create = async (e) => {
    e.preventDefault()
    await api.post('/collections', { name: form.name, description: form.description || null })
    setForm({ name: '', description: '' }); load()
  }

  return (
    <div>
      <div className="page-head">
        <h1>Collections</h1>
        <div className="muted">Group papers and highlights, compare papers side by side, and share with classmates.</div>
      </div>
      <form className="row card" onSubmit={create} style={{ marginBottom: 16 }}>
        <input placeholder="New collection name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required style={{ flex: 1, minWidth: 160 }} />
        <input placeholder="Description (optional)" value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} style={{ flex: 2, minWidth: 160 }} />
        <button className="primary">Create</button>
      </form>
      <div className="grid2">
        {collections?.map(c => (
          <Link key={c.id} to={`/collections/${c.id}`} className="item" style={{ color: 'inherit', display: 'block' }}>
            <div className="spread">
              <b>{c.name}</b>
              {c.role !== 'owner'
                ? <span className="chip">{c.role} · from {c.owner_name}</span>
                : c.member_count > 0 && <span className="chip">shared with {c.member_count}</span>}
            </div>
            {c.description && <div className="muted small" style={{ marginTop: 4 }}>{c.description}</div>}
            <div className="small muted" style={{ marginTop: 8 }}>{c.paper_count} papers · {c.highlight_count} highlights</div>
          </Link>
        ))}
      </div>
      {collections?.length === 0 && <div className="muted">No collections yet.</div>}
    </div>
  )
}
