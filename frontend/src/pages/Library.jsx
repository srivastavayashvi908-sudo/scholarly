import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, fmtDuration } from '../api'

const STATUSES = [['', 'All'], ['to_read', 'To read'], ['reading', 'Reading'], ['done', 'Done']]

export function StatusChip({ status }) {
  return <span className={`chip ${status}`}>{status.replace('_', ' ')}</span>
}

export default function Library() {
  const [papers, setPapers] = useState(null)
  const [status, setStatus] = useState('')
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState(null)

  const load = () =>
    api.get('/papers' + (status ? `?status=${status}` : '')).then(setPapers).catch(e => setError(e.message))
  useEffect(() => { load() }, [status])

  return (
    <div>
      <div className="spread page-head">
        <div>
          <h1>Library</h1>
          <div className="muted">{papers ? `${papers.length} papers` : '…'}</div>
        </div>
        <button className="primary" onClick={() => setAdding(true)}>+ Add paper</button>
      </div>
      <div className="row" style={{ marginBottom: 14 }}>
        {STATUSES.map(([v, l]) => (
          <button key={v} className={status === v ? 'primary small' : 'small'} onClick={() => setStatus(v)}>{l}</button>
        ))}
      </div>
      {error && <div className="error">{error}</div>}
      {papers?.length === 0 && (
        <div className="card muted">No papers yet. Click <b>Add paper</b> and paste a DOI or an arXiv link to get started.</div>
      )}
      <div className="list">
        {papers?.map(p => (
          <Link key={p.id} to={`/papers/${p.id}`} className="item" style={{ color: 'inherit', textDecoration: 'none' }}>
            <div className="spread">
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 600 }}>{p.title}</div>
                <div className="muted small">
                  {[p.authors && truncate(p.authors, 80), p.venue, p.year].filter(Boolean).join(' · ')}
                </div>
              </div>
              <div className="row">
                {p.role !== 'owner' && <span className="chip">shared by {p.owner_name}</span>}
                {p.has_pdf && <span className="chip">PDF</span>}
                {p.highlight_count > 0 && <span className="chip">{p.highlight_count} highlights</span>}
                {p.seconds_read > 0 && <span className="chip">{fmtDuration(p.seconds_read)}</span>}
                <StatusChip status={p.status} />
              </div>
            </div>
            {p.num_pages && p.status !== 'to_read' && (
              <div className="progress" style={{ marginTop: 8 }}>
                <div style={{ width: `${Math.min(100, (p.current_page / p.num_pages) * 100)}%` }} />
              </div>
            )}
          </Link>
        ))}
      </div>
      {adding && <AddPaperModal onClose={() => setAdding(false)} />}
    </div>
  )
}

const truncate = (s, n) => (s.length > n ? s.slice(0, n) + '…' : s)

function AddPaperModal({ onClose }) {
  const nav = useNavigate()
  const [tab, setTab] = useState('import')
  const [identifier, setIdentifier] = useState('')
  const [form, setForm] = useState({ title: '', authors: '', year: '', venue: '', doi: '', abstract: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const done = (paper) => nav(`/papers/${paper.id}`, { state: { pdfNote: paper.pdf_note } })

  const doImport = async (e) => {
    e.preventDefault(); setBusy(true); setError(null)
    try { done(await api.post('/papers/import', { identifier })) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const doManual = async (e) => {
    e.preventDefault(); setBusy(true); setError(null)
    const body = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''))
    if (body.year) body.year = Number(body.year)
    try { done(await api.post('/papers', body)) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  return (
    <div className="modal-bg" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal stack">
        <div className="spread"><h2 style={{ margin: 0 }}>Add a paper</h2><button className="link" onClick={onClose}>Close</button></div>
        <div className="tabs">
          <button className={tab === 'import' ? 'active' : ''} onClick={() => setTab('import')}>Import by DOI / arXiv</button>
          <button className={tab === 'manual' ? 'active' : ''} onClick={() => setTab('manual')}>Enter manually</button>
        </div>
        {tab === 'import' ? (
          <form className="stack" onSubmit={doImport}>
            <label className="field">DOI, doi.org link, arXiv ID or arXiv link
              <input autoFocus value={identifier} onChange={e => setIdentifier(e.target.value)}
                placeholder="e.g. 1706.03762  or  10.1145/3292500.3330701" required />
            </label>
            <div className="muted small">
              Title, authors, year, venue and abstract are filled in automatically. For arXiv papers the PDF is downloaded too,
              and references are linked to papers already in your library.
            </div>
            {error && <div className="error">{error}</div>}
            <button className="primary" disabled={busy}>{busy ? 'Looking it up…' : 'Import'}</button>
          </form>
        ) : (
          <form className="stack" onSubmit={doManual}>
            <label className="field">Title<input value={form.title} onChange={set('title')} required /></label>
            <label className="field">Authors<input value={form.authors} onChange={set('authors')} /></label>
            <div className="row">
              <label className="field" style={{ flex: 1 }}>Year<input type="number" value={form.year} onChange={set('year')} /></label>
              <label className="field" style={{ flex: 2 }}>Venue<input value={form.venue} onChange={set('venue')} /></label>
            </div>
            <label className="field">DOI<input value={form.doi} onChange={set('doi')} /></label>
            <label className="field">Abstract<textarea value={form.abstract} onChange={set('abstract')} /></label>
            {error && <div className="error">{error}</div>}
            <button className="primary" disabled={busy}>Save paper</button>
          </form>
        )}
      </div>
    </div>
  )
}
