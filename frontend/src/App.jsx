import { Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import Login from './pages/Login'
import Library from './pages/Library'
import PaperPage from './pages/PaperPage'
import Collections from './pages/Collections'
import CollectionPage from './pages/CollectionPage'
import Concepts from './pages/Concepts'
import CitationGraph from './pages/CitationGraph'
import SearchPage from './pages/SearchPage'
import Dashboard from './pages/Dashboard'
import ReadNext from './pages/ReadNext'

const NAV = [
  ['/', 'Library'],
  ['/search', 'Search & Ask'],
  ['/collections', 'Collections'],
  ['/next', 'Read next'],
  ['/concepts', 'Concepts'],
  ['/citations', 'Citation graph'],
  ['/dashboard', 'Dashboard'],
]

export default function App() {
  const { user, loading, logout } = useAuth()
  if (loading) return <div className="center muted">Loading…</div>
  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<Login />} />
      </Routes>
    )
  }
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">📑 Schol<span>arly</span></div>
        <nav>
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'active' : '')}>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="muted small">{user.name}<br />{user.email}</div>
          <button className="link" onClick={logout}>Log out</button>
        </div>
      </aside>
      <main className="content">
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/papers/:id" element={<PaperPage />} />
          <Route path="/collections" element={<Collections />} />
          <Route path="/collections/:id" element={<CollectionPage />} />
          <Route path="/concepts" element={<Concepts />} />
          <Route path="/citations" element={<CitationGraph />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/next" element={<ReadNext />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  )
}
