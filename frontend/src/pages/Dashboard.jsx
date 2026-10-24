import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, fmtDuration, TAGS, tz } from '../api'

// Sequential blue ramp for the activity heatmap (light -> dark = more activity).
const HEAT_LIGHT = ['#ebeae6', '#b7d3f6', '#6da7ec', '#2a78d6', '#184f95']
const HEAT_DARK = ['#2a2a28', '#104281', '#1c5cab', '#3987e5', '#86b6ef']
const isDark = () => window.matchMedia?.('(prefers-color-scheme: dark)').matches

const axis = { fontSize: 11, fill: 'var(--muted)' }

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [streak, setStreak] = useState(null)
  const [calendar, setCalendar] = useState([])

  useEffect(() => {
    const q = `?tz=${encodeURIComponent(tz)}`
    api.get('/stats/overview' + q).then(setStats)
    api.get('/stats/streak' + q).then(setStreak)
    api.get('/stats/calendar' + q).then(setCalendar)
  }, [])

  if (!stats || !streak) return <div className="muted">Crunching numbers…</div>
  const t = stats.totals

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Dashboard</h1>
        <div className="muted">Your reading activity. Every number here comes from a SQL aggregate or window function.</div>
      </div>

      <div className="tiles">
        <Tile num={`🔥 ${streak.current}`} lbl={`day streak${streak.active_today ? '' : ' (read today to keep it)'}`} />
        <Tile num={streak.longest} lbl="longest streak (days)" />
        <Tile num={fmtDuration(t.seconds_read)} lbl="total reading time" />
        <Tile num={t.done} lbl={`papers finished of ${t.papers}`} />
        <Tile num={t.reading} lbl="currently reading" />
        <Tile num={t.highlights} lbl="highlights" />
        <Tile num={t.notes} lbl="notes" />
      </div>

      <div className="card">
        <div className="spread"><h2>Activity, last 53 weeks</h2><span className="small muted">{streak.total_active_days} active days</span></div>
        <Heatmap days={calendar} />
      </div>

      <div className="grid2">
        <ChartCard title="Minutes read per day (last 30 days)">
          <BarChart data={stats.daily_minutes} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="label" tick={axis} interval={6} tickLine={false} axisLine={false} />
            <YAxis tick={axis} allowDecimals={false} tickLine={false} axisLine={false} />
            <Tooltip content={<Tip unit="min" />} cursor={{ fill: 'var(--surface-2)' }} />
            <Bar dataKey="minutes" fill="var(--accent)" radius={[4, 4, 0, 0]} maxBarSize={18} />
          </BarChart>
        </ChartCard>
        <ChartCard title="Papers finished per month">
          <BarChart data={stats.finished_by_month} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--border)" />
            <XAxis dataKey="label" tick={axis} interval={1} tickLine={false} axisLine={false} />
            <YAxis tick={axis} allowDecimals={false} tickLine={false} axisLine={false} />
            <Tooltip content={<Tip unit="finished" extra={(d) => `${d.running_total} total this year`} />} cursor={{ fill: 'var(--surface-2)' }} />
            <Bar dataKey="finished" fill="var(--accent)" radius={[4, 4, 0, 0]} maxBarSize={28} />
          </BarChart>
        </ChartCard>
        <ChartCard title="Highlights by tag">
          {stats.tags.length === 0 ? <Empty /> : (
            <BarChart data={stats.tags.map(r => ({ ...r, label: TAGS[r.tag]?.label || 'Untagged' }))} layout="vertical"
                      margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
              <CartesianGrid horizontal={false} stroke="var(--border)" />
              <XAxis type="number" tick={axis} allowDecimals={false} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="label" tick={{ ...axis, fill: 'var(--text-2)' }} width={90} tickLine={false} axisLine={false} />
              <Tooltip content={<Tip unit="highlights" valueKey="n" />} cursor={{ fill: 'var(--surface-2)' }} />
              <Bar dataKey="n" radius={[0, 4, 4, 0]} maxBarSize={20}>
                {stats.tags.map(r => <Cell key={r.tag} fill={TAGS[r.tag]?.color || '#8a8984'} />)}
              </Bar>
            </BarChart>
          )}
        </ChartCard>
        <div className="card stack">
          <div>
            <h2>Most cited in your library</h2>
            {stats.most_cited.length === 0 ? <Empty /> : stats.most_cited.map(p => (
              <div key={p.id} className="spread small" style={{ padding: '4px 0' }}>
                <span><b>#{p.rank}</b> <Link to={`/papers/${p.id}`}>{p.title}</Link></span><span className="muted">{p.cited_by}×</span>
              </div>
            ))}
          </div>
          <div>
            <h2>Most highlighted</h2>
            {stats.most_highlighted.length === 0 ? <Empty /> : stats.most_highlighted.map(p => (
              <div key={p.id} className="spread small" style={{ padding: '4px 0' }}>
                <Link to={`/papers/${p.id}`}>{p.title}</Link><span className="muted">{p.highlights} · {p.pct_of_all}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

const Tile = ({ num, lbl }) => <div className="tile"><div className="num">{num}</div><div className="lbl">{lbl}</div></div>
const Empty = () => <div className="muted small">Nothing yet.</div>

function ChartCard({ title, children }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      <div style={{ height: 220 }}><ResponsiveContainer>{children}</ResponsiveContainer></div>
    </div>
  )
}

function Tip({ active, payload, unit, valueKey, extra }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="card small" style={{ padding: '6px 10px' }}>
      <div className="muted">{d.label}</div>
      <div><b>{d[valueKey || payload[0].dataKey]}</b> {unit}</div>
      {extra && <div className="muted">{extra(d)}</div>}
    </div>
  )
}

function Heatmap({ days }) {
  const ramp = isDark() ? HEAT_DARK : HEAT_LIGHT
  const level = (d) => {
    const m = d.seconds / 60
    if (m < 1 && !d.highlights) return 0
    if (m < 10) return 1
    if (m < 30) return 2
    if (m < 60) return 3
    return 4
  }
  // Pad the front so the first column starts on a Sunday, like GitHub.
  const pad = days.length ? new Date(days[0].day + 'T00:00').getDay() : 0
  return (
    <div>
      <div className="heatmap">
        {Array.from({ length: pad }, (_, i) => <div key={'p' + i} />)}
        {days.map(d => (
          <div key={d.day} style={{ background: ramp[level(d)] }}
               title={`${new Date(d.day + 'T00:00').toDateString()}: ${Math.round(d.seconds / 60)} min read, ${d.highlights} highlights`} />
        ))}
      </div>
      <div className="row small muted" style={{ marginTop: 6, gap: 4 }}>
        Less {ramp.map(c => <span key={c} style={{ width: 11, height: 11, borderRadius: 2, background: c, display: 'inline-block' }} />)} More
      </div>
    </div>
  )
}
