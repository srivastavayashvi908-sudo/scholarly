import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, fmtDuration } from '../api'
import PdfViewer from '../components/PdfViewer'
import HighlightsPanel from '../components/HighlightsPanel'
import { CitationsPanel, InfoPanel, NotesPanel, SimilarPanel } from '../components/PaperPanels'

const TABS = ['Highlights', 'Notes', 'Info', 'Similar', 'Citations']

export default function PaperPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const location = useLocation()
  const [paper, setPaper] = useState(null)
  const [highlights, setHighlights] = useState([])
  const [collections, setCollections] = useState([])
  const [tab, setTab] = useState('Highlights')
  const [focusedId, setFocusedId] = useState(null)
  const [focusTick, setFocusTick] = useState(0)   // bumps on every click so re-clicking still scrolls
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(location.state?.pdfNote || null)
  const page = useRef(1)

  const loadPaper = useCallback(() => api.get(`/papers/${id}`).then(setPaper).catch(e => setError(e.message)), [id])
  const loadHighlights = useCallback(() => api.get(`/papers/${id}/highlights`).then(setHighlights), [id])

  useEffect(() => {
    setPaper(null); setFocusedId(null)
    loadPaper(); loadHighlights()
    api.get('/collections').then(setCollections)
  }, [id])

  useReadingSession(id, page)

  const onPageChange = useCallback((n) => { page.current = n }, [])

  const createHighlight = async (body) => {
    try {
      const h = await api.post(`/papers/${id}/highlights`, body)
      await loadHighlights()
      setTab('Highlights'); setFocusedId(h.id)
    } catch (e) { setNotice(e.message) }
  }

  const focus = (hid) => {
    setFocusedId(hid); setFocusTick(t => t + 1); setTab('Highlights')
    setTimeout(() => document.getElementById(`hl-${hid}`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), 50)
  }

  if (error) return <div className="error">{error}</div>
  if (!paper) return <div className="muted">Loading…</div>

  const setStatus = async (status) => setPaper(await api.put(`/papers/${id}/state`, { status }))
  const remove = async () => {
    if (!window.confirm('Delete this paper and all its highlights and notes?')) return
    await api.del(`/papers/${id}`); nav('/')
  }
  const addToCollection = async (cid) => {
    if (!cid) return
    try { await api.post(`/collections/${cid}/papers/${id}`); setNotice('Added to collection ✓') } catch (e) { setNotice(e.message) }
  }

  return (
    <div>
      <div className="page-head">
        <div className="small"><Link to="/">← Library</Link></div>
        <h1 style={{ marginTop: 6 }}>{paper.title}</h1>
        <div className="muted">{[paper.authors, paper.venue, paper.year].filter(Boolean).join(' · ')}</div>
        <div className="row" style={{ marginTop: 10 }}>
          <select value={paper.status} onChange={e => setStatus(e.target.value)}>
            <option value="to_read">To read</option>
            <option value="reading">Reading</option>
            <option value="done">Done</option>
          </select>
          {paper.num_pages && (
            <span className="chip">page {paper.current_page} of {paper.num_pages} · {Math.round((paper.current_page / paper.num_pages) * 100)}%</span>
          )}
          <span className="chip">⏱ {fmtDuration(paper.seconds_read)} read</span>
          {paper.role !== 'owner' && <span className="chip">{paper.role} · shared by {paper.owner_name}</span>}
          <select value="" onChange={e => addToCollection(e.target.value)}>
            <option value="">+ Add to collection</option>
            {collections.filter(c => c.role !== 'viewer').map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {paper.role === 'owner' && <button className="danger small" onClick={remove}>Delete</button>}
        </div>
        {notice && <div className="card small" style={{ marginTop: 10 }}>{notice} <button className="link small" onClick={() => setNotice(null)}>dismiss</button></div>}
      </div>

      <div className="paper-layout">
        <div>
          {paper.has_pdf ? (
            <PdfViewer
              paperId={id}
              highlights={highlights}
              focusedId={focusedId}
              focusTick={focusTick}
              onFocus={focus}
              onCreate={createHighlight}
              initialPage={paper.current_page}
              onPageChange={onPageChange}
            />
          ) : (
            <UploadPdf paper={paper} onDone={(p) => setPaper(p)} />
          )}
        </div>
        <div className="card side-panel">
          <div className="tabs">
            {TABS.map(t => (
              <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
                {t}{t === 'Highlights' && highlights.length ? ` (${highlights.length})` : ''}
              </button>
            ))}
          </div>
          {tab === 'Highlights' && (
            <HighlightsPanel paper={paper} highlights={highlights} focusedId={focusedId} onFocus={focus}
                             onCreate={createHighlight} onChange={loadHighlights} collections={collections} />
          )}
          {tab === 'Notes' && <NotesPanel paperId={id} />}
          {tab === 'Info' && <InfoPanel paper={paper} onChange={loadPaper} />}
          {tab === 'Similar' && <SimilarPanel paperId={id} />}
          {tab === 'Citations' && <CitationsPanel paper={paper} />}
        </div>
      </div>
    </div>
  )
}

function UploadPdf({ paper, onDone }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const canEdit = paper.role !== 'viewer'

  const upload = async (file) => {
    if (!file) return
    setBusy(true); setError(null)
    const fd = new FormData(); fd.append('file', file)
    try { onDone(await api.post(`/papers/${paper.id}/pdf`, fd)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const fetchUrl = async () => {
    setBusy(true); setError(null)
    try { onDone(await api.post(`/papers/${paper.id}/pdf/fetch`)) } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="card center stack" style={{ minHeight: 320, textAlign: 'center' }}
         onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); canEdit && upload(e.dataTransfer.files[0]) }}>
      <div>
        <div style={{ fontSize: 36 }}>📄</div>
        <h2>No PDF yet</h2>
        {canEdit ? (
          <>
            <div className="muted" style={{ marginBottom: 12 }}>Drop a PDF here or choose a file to read and highlight it in the browser.</div>
            <div className="row" style={{ justifyContent: 'center' }}>
              <label className="btn" style={{ cursor: 'pointer' }}>
                {busy ? 'Uploading…' : 'Choose PDF'}
                <input type="file" accept="application/pdf" hidden onChange={e => upload(e.target.files[0])} />
              </label>
              {paper.pdf_url && <button onClick={fetchUrl} disabled={busy}>Download from {new URL(paper.pdf_url).hostname}</button>}
            </div>
          </>
        ) : <div className="muted">The owner hasn't uploaded a PDF.</div>}
        {error && <div className="error" style={{ marginTop: 12 }}>{error}</div>}
      </div>
    </div>
  )
}

/** Start a reading session when the paper opens; heartbeat every 30s while the tab is visible. */
function useReadingSession(paperId, pageRef) {
  useEffect(() => {
    let sessionId = null
    let cancelled = false
    api.post(`/papers/${paperId}/sessions`, { page: pageRef.current }).then(s => { if (!cancelled) sessionId = s.id })
    const beat = () => {
      if (sessionId && document.visibilityState === 'visible') {
        api.post(`/sessions/${sessionId}/heartbeat`, { page: pageRef.current }).catch(() => {})
      }
    }
    const timer = setInterval(beat, 30000)
    return () => { cancelled = true; clearInterval(timer); beat() }
  }, [paperId])
}
