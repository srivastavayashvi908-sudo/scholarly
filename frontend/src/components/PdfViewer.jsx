import { useEffect, useMemo, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import { api, highlightColor, TAGS } from '../api'

// Must be set in the same module that renders <Document>/<Page>.
pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

/**
 * Renders the paper's PDF with a selectable text layer.
 * Selecting text pops up the tag buttons; picking one creates a highlight whose position is
 * stored as rectangles in 0..1 page coordinates, so it redraws correctly at any zoom level.
 */
export default function PdfViewer({ paperId, highlights, focusedId, focusTick, onFocus, onCreate, initialPage, onPageChange }) {
  const [file, setFile] = useState(null)
  const [error, setError] = useState(null)
  const [numPages, setNumPages] = useState(0)
  const [width, setWidth] = useState(700)
  const [zoom, setZoom] = useState(1)
  const [popup, setPopup] = useState(null)   // { x, y, quote, page, rects }
  const scrollRef = useRef(null)
  const pageRefs = useRef({})
  const scrolledToStart = useRef(false)

  useEffect(() => {
    api.blob(`/papers/${paperId}/pdf`).then(setFile).catch(e => setError(e.message))
  }, [paperId])

  // Fit the page width to the container.
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.min(900, e.contentRect.width - 32)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Track which page is most visible -> reading progress.
  useEffect(() => {
    if (!numPages) return
    const ratios = {}
    const io = new IntersectionObserver((entries) => {
      entries.forEach(e => { ratios[e.target.dataset.page] = e.intersectionRatio })
      const best = Object.entries(ratios).sort((a, b) => b[1] - a[1])[0]
      if (best && best[1] > 0) onPageChange?.(Number(best[0]))
    }, { root: scrollRef.current, threshold: [0, 0.25, 0.5, 0.75, 1] })
    Object.values(pageRefs.current).forEach(el => el && io.observe(el))
    return () => io.disconnect()
  }, [numPages, onPageChange])

  // Scroll to a highlight when it's clicked in the side panel.
  useEffect(() => {
    const h = highlights.find(h => h.id === focusedId)
    if (!h?.page) return
    const pageEl = pageRefs.current[h.page]
    if (!pageEl) return
    const top = h.position?.rects?.[0]?.y ?? 0
    scrollRef.current.scrollTo({
      // instant: a smooth scroll gets cancelled when the side panel scrolls the item into view
      top: pageEl.offsetTop + top * pageEl.offsetHeight - 120,
    })
  }, [focusedId, focusTick])

  const byPage = useMemo(() => {
    const m = {}
    highlights.forEach(h => { if (h.page && h.position?.rects) (m[h.page] ||= []).push(h) })
    return m
  }, [highlights])

  const onMouseUp = () => {
    const sel = window.getSelection()
    const quote = sel?.toString().replace(/\s+/g, ' ').trim()
    if (!sel || sel.isCollapsed || !quote) return setPopup(null)
    const range = sel.getRangeAt(0)
    const startPage = closestPage(range.startContainer)
    const endPage = closestPage(range.endContainer)
    if (!startPage || startPage !== endPage) {
      setPopup({ error: 'Highlights must stay on one page. Select a shorter passage.', ...popupPos(range) })
      return
    }
    const box = startPage.getBoundingClientRect()
    const rects = mergeRects(
      [...range.getClientRects()]
        .filter(r => r.width > 1 && r.height > 1)
        .map(r => ({
          x: (r.left - box.left) / box.width,
          y: (r.top - box.top) / box.height,
          w: r.width / box.width,
          h: r.height / box.height,
        })),
    )
    setPopup({ quote, page: Number(startPage.dataset.page), rects, ...popupPos(range) })
  }

  const save = async (tag) => {
    const { quote, page, rects } = popup
    setPopup(null)
    window.getSelection()?.removeAllRanges()
    await onCreate({ quote, page, tag, position: { rects } })
  }

  if (error) return <div className="error">{error}</div>

  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <button className="small" onClick={() => setZoom(z => Math.max(0.5, z - 0.15))}>−</button>
        <span className="small muted">{Math.round(zoom * 100)}%</span>
        <button className="small" onClick={() => setZoom(z => Math.min(2.5, z + 0.15))}>+</button>
        <span className="small muted" style={{ marginLeft: 8 }}>Select text in the PDF to highlight it.</span>
      </div>
      <div className="pdf-scroll" ref={scrollRef} onMouseUp={onMouseUp}
           onScroll={() => popup && setPopup(null)}>
        {!file && <div className="muted">Loading PDF…</div>}
        {file && (
          <Document
            file={file}
            onLoadSuccess={({ numPages }) => setNumPages(numPages)}
            onLoadError={(e) => setError('Could not open this PDF: ' + e.message)}
            loading={<div className="muted">Loading PDF…</div>}
          >
            {Array.from({ length: numPages }, (_, i) => i + 1).map(n => (
              <div key={n} className="pdf-page" data-page={n} ref={el => { pageRefs.current[n] = el }}>
                <Page
                  pageNumber={n}
                  width={width * zoom}
                  renderAnnotationLayer={false}
                  onRenderSuccess={() => {
                    if (n === initialPage && !scrolledToStart.current && initialPage > 1) {
                      scrolledToStart.current = true
                      scrollRef.current.scrollTo({ top: pageRefs.current[n].offsetTop - 16 })
                    }
                  }}
                />
                <div className="hl-layer">
                  {(byPage[n] || []).flatMap(h => h.position.rects.map((r, i) => (
                    <div
                      key={h.id + i}
                      className={'hl-rect' + (h.id === focusedId ? ' focused' : '')}
                      title={`${TAGS[h.tag]?.label || 'Highlight'}${h.user_name ? ' · ' + h.user_name : ''}`}
                      onClick={() => onFocus(h.id)}
                      style={{
                        left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.w * 100}%`, height: `${r.h * 100}%`,
                        background: highlightColor(h), color: highlightColor(h),
                      }}
                    />
                  )))}
                </div>
              </div>
            ))}
          </Document>
        )}
      </div>
      {popup && (
        <div className="sel-popup" style={{ left: popup.x, top: popup.y }} onMouseUp={e => e.stopPropagation()}>
          {popup.error ? <span className="small">{popup.error}</span> : (
            <>
              {Object.entries(TAGS).map(([tag, t]) => (
                <button key={tag} onClick={() => save(tag)}><span className="dot" style={{ background: t.color }} />{t.label}</button>
              ))}
              <button onClick={() => save(null)}>No tag</button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function closestPage(node) {
  const el = node.nodeType === 1 ? node : node.parentElement
  return el?.closest('.pdf-page')
}

function popupPos(range) {
  const r = range.getBoundingClientRect()
  return {
    x: Math.max(8, Math.min(window.innerWidth - 340, r.left)),
    y: r.bottom + 120 > window.innerHeight ? r.top - 110 : r.bottom + 8,
  }
}

// The text layer gives one rectangle per text span; join neighbours on the same line.
function mergeRects(rects) {
  const sorted = [...rects].sort((a, b) => a.y - b.y || a.x - b.x)
  const out = []
  for (const r of sorted) {
    const last = out[out.length - 1]
    const sameLine = last && Math.abs(last.y - r.y) < Math.min(last.h, r.h) * 0.5
    if (sameLine && r.x <= last.x + last.w + 0.01) {
      const right = Math.max(last.x + last.w, r.x + r.w)
      const bottom = Math.max(last.y + last.h, r.y + r.h)
      last.x = Math.min(last.x, r.x); last.y = Math.min(last.y, r.y)
      last.w = right - last.x; last.h = bottom - last.y
    } else {
      out.push({ ...r })
    }
  }
  return out.map(r => Object.fromEntries(Object.entries(r).map(([k, v]) => [k, Math.round(v * 10000) / 10000])))
}
