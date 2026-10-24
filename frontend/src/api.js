// Tiny fetch wrapper: adds the login token and turns API errors into readable messages.

const TOKEN_KEY = 'rpt_token'

export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export const setToken = (t) => {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY) } catch { /* private mode */ }
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

async function request(method, path, body, { raw = false } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (body instanceof FormData) payload = body
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }

  const res = await fetch('/api' + path, { method, headers, body: payload })
  if (res.status === 401 && token) {
    setToken(null)
    window.location.href = '/login'
  }
  if (!res.ok) {
    let msg = res.statusText
    try {
      const data = await res.json()
      msg = typeof data.detail === 'string'
        ? data.detail
        : (data.detail || []).map(d => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join('; ')
    } catch { /* not JSON */ }
    throw new ApiError(res.status, msg)
  }
  if (raw) return res
  return res.status === 204 ? null : res.json()
}

export const api = {
  get: (p) => request('GET', p),
  post: (p, b) => request('POST', p, b ?? {}),
  put: (p, b) => request('PUT', p, b),
  patch: (p, b) => request('PATCH', p, b),
  del: (p) => request('DELETE', p),
  blob: async (p) => (await request('GET', p, undefined, { raw: true })).blob(),
}

export const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

// Highlight tags and their default colours (categorical palette, fixed order).
export const TAGS = {
  methodology: { label: 'Methodology', color: '#2a78d6' },
  result:      { label: 'Result',      color: '#1baf7a' },
  limitation:  { label: 'Limitation',  color: '#e34948' },
  dataset:     { label: 'Dataset',     color: '#eda100' },
  definition:  { label: 'Definition',  color: '#6250d6' },
  quote:       { label: 'Quote',       color: '#e87ba4' },
  future_work: { label: 'Future work', color: '#eb6834' },
}
export const DEFAULT_HIGHLIGHT = '#f5c542'
export const highlightColor = (h) => h.color || TAGS[h.tag]?.color || DEFAULT_HIGHLIGHT

export const fmtDuration = (s) => {
  if (!s) return '0m'
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60)
  return h ? `${h}h ${m}m` : `${m}m`
}
