import { useState } from 'react'
import { useAuth } from '../auth'

export default function Login() {
  const { login, register } = useAuth()
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      if (mode === 'login') await login(form.email, form.password)
      else await register(form.name, form.email, form.password)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <div className="center">
      <form className="card stack" style={{ width: 'min(380px, 92vw)' }} onSubmit={submit}>
        <div>
          <h1>📑 Schol<span style={{ color: 'var(--accent)' }}>arly</span></h1>
          <div className="muted">Store, highlight and connect your research papers.</div>
        </div>
        {mode === 'register' && (
          <label className="field">Name<input value={form.name} onChange={set('name')} required /></label>
        )}
        <label className="field">Email<input type="email" value={form.email} onChange={set('email')} required /></label>
        <label className="field">Password
          <input type="password" value={form.password} onChange={set('password')} minLength={6} required />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="primary" disabled={busy}>{mode === 'login' ? 'Log in' : 'Create account'}</button>
        <div className="small muted">
          {mode === 'login' ? 'No account yet? ' : 'Already registered? '}
          <button type="button" className="link" onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>
            {mode === 'login' ? 'Register' : 'Log in'}
          </button>
        </div>
      </form>
    </div>
  )
}
