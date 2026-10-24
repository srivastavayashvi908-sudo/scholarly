import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, TAGS } from '../api'

// ts_headline marks matches with ⟦ ⟧; turn them into <mark> elements without using raw HTML.
function Snippet({ text }) {
  return text.split(/(⟦[^⟧]*⟧)/).map((part, i) =>
    part.startsWith('⟦') ? <mark key={i}>{part.slice(1, -1)}</mark> : <span key={i}>{part}</span>)
}

// Turn "[1][3]" citations in the AI answer into links to the matching source.
function Answer({ text, sources }) {
  return (
    <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
      {text.split(/(\[\d+\])/).map((part, i) => {
        const m = part.match(/^\[(\d+)\]$/)
        const src = m && sources.find(s => s.n === Number(m[1]))
        return src
          ? <Link key={i} to={`/papers/${src.paper_id}`} title={src.paper_title}><sup>[{m[1]}]</sup></Link>
          : <span key={i}>{part}</span>
      })}
    </div>
  )
}

export default function SearchPage() {
  const [mode, setMode] = useState('search')
  const [q, setQ] = useState('')
  const [kind, setKind] = useState('')
  const [results, setResults] = useState(null)
  const [answer, setAnswer] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const run = async (e) => {
    e.preventDefault(); setBusy(true); setError(null)
    try {
      if (mode === 'search') {
        setResults(await api.get(`/search?q=${encodeURIComponent(q)}${kind ? `&kind=${kind}` : ''}`))
      } else {
        setAnswer(await api.post('/ask', { question: q }))
      }
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <div style={{ maxWidth: 860 }}>
      <div className="page-head">
        <h1>Search & Ask</h1>
        <div className="muted">Keyword search across all your papers, highlights and notes, or ask a question and get an answer built from your own library.</div>
      </div>
      <div className="tabs">
        <button className={mode === 'search' ? 'active' : ''} onClick={() => setMode('search')}>🔎 Keyword search</button>
        <button className={mode === 'ask' ? 'active' : ''} onClick={() => setMode('ask')}>✨ Ask your library</button>
      </div>
      <form className="row" onSubmit={run} style={{ marginBottom: 16 }}>
        <input style={{ flex: 1, minWidth: 200 }} value={q} onChange={e => setQ(e.target.value)} autoFocus required
               placeholder={mode === 'search' ? 'e.g. "transfer learning" -vision' : 'e.g. Which papers used ImageNet, and what accuracy did they get?'} />
        {mode === 'search' && (
          <select value={kind} onChange={e => setKind(e.target.value)}>
            <option value="">Everything</option><option value="paper">Papers</option>
            <option value="highlight">Highlights</option><option value="note">Notes</option>
          </select>
        )}
        <button className="primary" disabled={busy}>{busy ? '…' : mode === 'search' ? 'Search' : 'Ask'}</button>
      </form>
      {error && <div className="error">{error}</div>}

      {mode === 'search' && results && (
        <div className="list">
          <div className="muted small">{results.length} results, ranked by relevance</div>
          {results.map(r => (
            <Link key={r.kind + r.id} to={`/papers/${r.paper_id}`} className="item" style={{ color: 'inherit', display: 'block' }}>
              <div className="row small" style={{ marginBottom: 4 }}>
                <span className="chip">{r.kind}</span>
                {r.tag && <span className="chip" style={{ color: TAGS[r.tag]?.color }}>{TAGS[r.tag]?.label}</span>}
                <span className="muted">{r.paper_title}{r.page ? ` · p. ${r.page}` : ''}</span>
              </div>
              <div style={{ lineHeight: 1.5 }}><Snippet text={r.snippet} /></div>
            </Link>
          ))}
        </div>
      )}

      {mode === 'ask' && answer && (
        <div className="stack">
          <div className="card"><Answer text={answer.answer} sources={answer.sources} /></div>
          <h3>Sources the answer was built from</h3>
          <div className="list">
            {answer.sources.map(s => (
              <Link key={s.n} to={`/papers/${s.paper_id}`} className="item small" style={{ color: 'inherit', display: 'block' }}>
                <b>[{s.n}]</b> <span className="chip">{s.kind}</span> <span className="muted">{s.paper_title}{s.page ? ` · p. ${s.page}` : ''} · {Math.round(s.similarity * 100)}% match</span>
                <div style={{ marginTop: 4 }}>{s.text.length > 300 ? s.text.slice(0, 300) + '…' : s.text}</div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
