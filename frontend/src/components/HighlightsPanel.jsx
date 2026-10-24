import { useEffect, useState } from 'react'
import { api, highlightColor, TAGS } from '../api'
import { useAuth } from '../auth'

export default function HighlightsPanel({ paper, highlights, focusedId, onFocus, onCreate, onChange, collections }) {
  const [filter, setFilter] = useState('')
  const [adding, setAdding] = useState(!paper.has_pdf)
  const shown = highlights.filter(h => !filter || h.tag === filter || (filter === 'none' && !h.tag))

  return (
    <div className="stack">
      <div className="row">
        <select value={filter} onChange={e => setFilter(e.target.value)}>
          <option value="">All tags ({highlights.length})</option>
          {Object.entries(TAGS).map(([k, t]) => (
            <option key={k} value={k}>{t.label} ({highlights.filter(h => h.tag === k).length})</option>
          ))}
          <option value="none">Untagged</option>
        </select>
        <button className="small" onClick={() => setAdding(a => !a)}>{adding ? 'Hide form' : '+ Type a quote'}</button>
      </div>
      {adding && <ManualHighlight onCreate={onCreate} />}
      {shown.length === 0 && (
        <div className="muted small">
          {paper.has_pdf ? 'Select text in the PDF to create your first highlight.' : 'No highlights yet.'}
        </div>
      )}
      {shown.map(h => (
        <HighlightItem key={h.id} h={h} focused={h.id === focusedId} onFocus={onFocus}
                       onChange={onChange} collections={collections} />
      ))}
    </div>
  )
}

function ManualHighlight({ onCreate }) {
  const [quote, setQuote] = useState('')
  const [tag, setTag] = useState('')
  const [page, setPage] = useState('')
  const submit = async (e) => {
    e.preventDefault()
    await onCreate({ quote, tag: tag || null, page: page ? Number(page) : null })
    setQuote(''); setPage('')
  }
  return (
    <form className="card stack" onSubmit={submit}>
      <textarea placeholder="Paste or type the passage…" value={quote} onChange={e => setQuote(e.target.value)} required />
      <div className="row">
        <select value={tag} onChange={e => setTag(e.target.value)}>
          <option value="">No tag</option>
          {Object.entries(TAGS).map(([k, t]) => <option key={k} value={k}>{t.label}</option>)}
        </select>
        <input type="number" min="1" placeholder="Page" value={page} onChange={e => setPage(e.target.value)} style={{ width: 80 }} />
        <button className="primary small">Save highlight</button>
      </div>
    </form>
  )
}

function HighlightItem({ h, focused, onFocus, onChange, collections }) {
  const { user } = useAuth()
  const mine = h.user_id === user.id
  const [showComments, setShowComments] = useState(false)
  const [msg, setMsg] = useState(null)
  const color = highlightColor(h)

  const update = async (body) => { await api.patch(`/highlights/${h.id}`, body); onChange() }
  const remove = async () => { await api.del(`/highlights/${h.id}`); onChange() }
  const addToCollection = async (cid) => {
    if (!cid) return
    try { await api.post(`/collections/${cid}/highlights/${h.id}`); setMsg('Added ✓') } catch (e) { setMsg(e.message) }
  }

  return (
    <div className="hl-item" style={{ borderLeftColor: color, outline: focused ? `2px solid ${color}` : 'none' }}
         id={`hl-${h.id}`}>
      <blockquote onClick={() => onFocus(h.id)} style={{ cursor: h.position ? 'pointer' : 'default' }}>“{h.quote}”</blockquote>
      <div className="spread small">
        <div className="row">
          {mine ? (
            <select className="small" value={h.tag || ''} onChange={e => update({ tag: e.target.value || null })}
                    style={{ padding: '2px 6px', fontSize: 12 }}>
              <option value="">No tag</option>
              {Object.entries(TAGS).map(([k, t]) => <option key={k} value={k}>{t.label}</option>)}
            </select>
          ) : <span className="chip">{TAGS[h.tag]?.label || 'No tag'}</span>}
          {mine && (
            <input type="color" value={color} title="Highlight colour"
                   onChange={e => update({ color: e.target.value })}
                   style={{ width: 26, height: 22, padding: 0, border: 'none', background: 'none' }} />
          )}
          {h.page && <span className="muted">p. {h.page}</span>}
          {!mine && <span className="muted">by {h.user_name}</span>}
        </div>
        <div className="row">
          <button className="link small" onClick={() => setShowComments(s => !s)}>
            💬 {h.comment_count || ''}
          </button>
          {mine && <button className="link small" style={{ color: 'var(--danger)' }} onClick={remove}>Delete</button>}
        </div>
      </div>
      {collections.length > 0 && (
        <div className="row small" style={{ marginTop: 6 }}>
          <select value="" onChange={e => addToCollection(e.target.value)} style={{ padding: '2px 6px', fontSize: 12 }}>
            <option value="">Add to collection…</option>
            {collections.filter(c => c.role !== 'viewer').map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          {msg && <span className="muted">{msg}</span>}
        </div>
      )}
      {showComments && <Comments highlightId={h.id} onChange={onChange} />}
    </div>
  )
}

function Comments({ highlightId, onChange }) {
  const { user } = useAuth()
  const [comments, setComments] = useState([])
  const [body, setBody] = useState('')
  const [replyTo, setReplyTo] = useState(null)

  const load = () => api.get(`/highlights/${highlightId}/comments`).then(setComments)
  useEffect(() => { load() }, [highlightId])

  const submit = async (e) => {
    e.preventDefault()
    await api.post(`/highlights/${highlightId}/comments`, { body, parent_id: replyTo?.id ?? null })
    setBody(''); setReplyTo(null); load(); onChange()
  }
  const remove = async (id) => { await api.del(`/comments/${id}`); load(); onChange() }

  return (
    <div style={{ marginTop: 8 }}>
      {comments.map(c => (
        <div key={c.id} className="comment" style={{ marginLeft: Math.min(c.depth, 4) * 14 }}>
          <b>{c.user_name}</b> <span className="muted">{new Date(c.created_at).toLocaleString()}</span>
          <div>{c.body}</div>
          <div className="row">
            <button className="link small" onClick={() => setReplyTo(c)}>Reply</button>
            {c.user_id === user.id && <button className="link small" style={{ color: 'var(--danger)' }} onClick={() => remove(c.id)}>Delete</button>}
          </div>
        </div>
      ))}
      <form onSubmit={submit} className="row" style={{ marginTop: 6 }}>
        <input style={{ flex: 1, minWidth: 0 }} value={body} onChange={e => setBody(e.target.value)}
               placeholder={replyTo ? `Reply to ${replyTo.user_name}…` : 'Add a comment…'} required />
        {replyTo && <button type="button" className="small" onClick={() => setReplyTo(null)}>×</button>}
        <button className="small primary">Post</button>
      </form>
    </div>
  )
}
