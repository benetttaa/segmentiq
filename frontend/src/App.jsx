import { useCallback, useEffect, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { api } from './api'

const COL = ['#4f46e5', '#10b981', '#f59e0b', '#ef4444', '#6b7280']
const SEG_ORDER = ['Champions', 'Loyal', 'Promising', 'At-Risk', 'Lost']

function useAuth() {
  const [role, setRole] = useState(localStorage.getItem('siq_role') || '')
  const [email, setEmail] = useState(localStorage.getItem('siq_email') || '')
  const login = async () => {
    const e = prompt('Email (admin@segmentiq.com or c{id}@example.com)')
    if (!e) return
    const j = await api('/api/login', { method: 'POST', body: JSON.stringify({ email: e }) })
    localStorage.setItem('siq_token', j.token)
    localStorage.setItem('siq_role', j.role)
    localStorage.setItem('siq_email', j.email)
    setRole(j.role)
    setEmail(j.email)
  }
  const logout = () => {
    ;['siq_token', 'siq_role', 'siq_email'].forEach((k) => localStorage.removeItem(k))
    setRole('')
    setEmail('')
  }
  return { role, email, login, logout }
}

export default function App() {
  const { role, email, login, logout } = useAuth()
  const [msg, setMsg] = useState('')
  const [tab, setTab] = useState('dash')
  const [summary, setSummary] = useState(null)
  const [modelCmp, setModelCmp] = useState(null)
  const [customers, setCustomers] = useState([])
  const [q, setQ] = useState('')
  const [segFilter, setSegFilter] = useState('')
  const [inbox, setInbox] = useState(null)
  const [history, setHistory] = useState([])
  const [account, setAccount] = useState(null)

  const say = (t) => {
    setMsg(t)
    setTimeout(() => setMsg(''), 4000)
  }

  const loadSummary = useCallback(async () => {
    const s = await api('/api/summary')
    setSummary(s)
    const h = await api('/api/campaigns')
    setHistory(h)
  }, [])

  const loadModel = useCallback(async () => {
    setModelCmp(await api('/api/model-comparison'))
  }, [])

  const loadCustomers = useCallback(async () => {
    const l = await api(
      `/api/customers?segment=${encodeURIComponent(segFilter)}&q=${encodeURIComponent(q)}`,
    )
    setCustomers(l)
  }, [q, segFilter])

  const loadAccount = useCallback(async () => {
    setAccount(await api('/api/account'))
  }, [])

  useEffect(() => {
    if (role === 'customer') loadAccount().catch((e) => say(e.message))
    else loadSummary().catch((e) => say(e.message))
  }, [role, loadSummary, loadAccount])

  useEffect(() => {
    if (role !== 'customer' && tab === 'cust') loadCustomers().catch((e) => say(e.message))
  }, [role, tab, loadCustomers])

  useEffect(() => {
    if (role !== 'customer' && tab === 'model') loadModel().catch((e) => say(e.message))
  }, [role, tab, loadModel])

  const post = async (path, okMsg) => {
    try {
      const j = await api(path, { method: 'POST' })
      say(`${okMsg} ${JSON.stringify(j)}`)
      await loadSummary()
    } catch (e) {
      say(e.message)
    }
  }

  const upload = async (file) => {
    const fd = new FormData()
    fd.append('file', file)
    try {
      const j = await api('/api/upload', { method: 'POST', body: fd })
      say(`Uploaded ${j.customers} customers. Run segmentation.`)
      await loadSummary()
    } catch (e) {
      say(e.message)
    }
  }

  const sendCamp = async (segment) => {
    try {
      const j = await api(`/api/campaign/${encodeURIComponent(segment)}`, { method: 'POST' })
      say(`Campaign sent ${JSON.stringify(j)}`)
      await loadSummary()
    } catch (e) {
      if (String(e.message).includes('24h') && confirm('Sent within 24h. Admin override?')) {
        await api(`/api/campaign/${encodeURIComponent(segment)}?override=true`, { method: 'POST' })
        say('Campaign sent (override)')
        await loadSummary()
      } else say(e.message)
    }
  }

  const markRead = async (id) => {
    await api(`/api/notifications/${id}/read`, { method: 'POST' })
    await loadAccount()
  }

  if (role === 'customer') {
    return (
      <>
        <header>
          <h1>SegmentIQ</h1>
          <span className="mut">{email}</span>
          <button className="g" onClick={logout}>
            Log out
          </button>
        </header>
        {msg && <div id="msg">{msg}</div>}
        <main className="card">
          <h2>My account</h2>
          {!account ? (
            <p className="mut">Loading…</p>
          ) : (
            <>
              {account.notifications.map((n) => (
                <div key={n.id} className="card" style={{ margin: '8px 0', opacity: n.read_flag ? 0.65 : 1 }}>
                  <b>{n.title}</b> {n.read_flag ? '(read)' : ''}
                  <p>{n.message}</p>
                  <p className="mut">{n.created}</p>
                  {!n.read_flag && (
                    <button className="g" onClick={() => markRead(n.id)}>
                      Mark read
                    </button>
                  )}
                </div>
              ))}
              {!account.notifications.length && <p className="mut">No notifications yet.</p>}
              {account.coupons.length > 0 && (
                <>
                  <h3>Coupons</h3>
                  <ul>
                    {account.coupons.map((c, i) => (
                      <li key={i}>
                        <b>{c.code}</b> — {c.discount}% ({c.created})
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </main>
      </>
    )
  }

  const sg = summary?.segments || []
  const segNames = sg.map((x) => x.segment)
  const scatterGroups = segNames.map((name, i) => ({
    name,
    color: COL[i % COL.length],
    data: (summary?.points || []).filter((p) => p.segment === name),
  }))

  return (
    <>
      <header>
        <h1>SegmentIQ</h1>
        <button className="g" onClick={() => post('/api/load-sample', 'Sample loaded')}>
          Load sample data
        </button>
        <label className="g card" style={{ padding: '7px 12px', cursor: 'pointer' }}>
          Upload CSV
          <input
            type="file"
            hidden
            accept=".csv"
            onChange={(e) => e.target.files[0] && upload(e.target.files[0])}
          />
        </label>
        <button onClick={() => post('/api/segment', 'Segmentation complete')}>Run segmentation</button>
        <span className="mut">{role ? email : 'Log in as admin to send campaigns'}</span>
        {!role ? (
          <button className="g" onClick={() => login().catch((e) => say(e.message))}>
            Log in
          </button>
        ) : (
          <button className="g" onClick={logout}>
            Log out
          </button>
        )}
      </header>
      {msg && <div id="msg">{msg}</div>}
      <main>
        <div className="tabs">
          {['dash', 'model', 'cust', 'camp'].map((t) => (
            <button key={t} className={tab === t ? 'on' : 'g'} onClick={() => setTab(t)}>
              {t === 'dash' ? 'Dashboard' : t === 'model' ? 'Model comparison' : t === 'cust' ? 'Customers' : 'Campaigns'}
            </button>
          ))}
        </div>

        {tab === 'dash' && summary && (
          <>
            <div className="grid">
              <div className="card">
                <div className="mut">Customers</div>
                <div className="stat">{summary.total}</div>
              </div>
              <div className="card">
                <div className="mut">Segments (k)</div>
                <div className="stat">{summary.meta.k || '—'}</div>
              </div>
              <div className="card">
                <div className="mut">Notifications sent</div>
                <div className="stat">{summary.sent}</div>
              </div>
              <div className="card">
                <div className="mut">Silhouette by k</div>
                <div>{summary.meta.silhouette || '—'}</div>
              </div>
            </div>
            <div className="grid" style={{ marginTop: 16 }}>
              <div className="card">
                <b>Segment sizes</b>
                <div className="chart">
                  <ResponsiveContainer>
                    <PieChart>
                      <Pie data={sg} dataKey="n" nameKey="segment" label>
                        {sg.map((_, i) => (
                          <Cell key={i} fill={COL[i % COL.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div className="card">
                <b>Clusters (PCA 2D)</b>
                <div className="chart">
                  <ResponsiveContainer>
                    <ScatterChart>
                      <XAxis dataKey="x" name="PC1" />
                      <YAxis dataKey="y" name="PC2" />
                      <ZAxis range={[40, 40]} />
                      <Tooltip cursor={{ strokeDasharray: '3 3' }} />
                      <Legend />
                      {scatterGroups.map((g) => (
                        <Scatter key={g.name} name={g.name} data={g.data} fill={g.color} />
                      ))}
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              </div>
              <div className="card">
                <b>Avg monetary value</b>
                <div className="chart">
                  <ResponsiveContainer>
                    <BarChart data={sg}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="segment" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="monetary" fill={COL[0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
            <div className="card wrap" style={{ marginTop: 16 }}>
              <b>Segment profiles</b>
              <table>
                <thead>
                  <tr>
                    <th>Segment</th>
                    <th>Customers</th>
                    <th>Recency</th>
                    <th>Frequency</th>
                    <th>Monetary</th>
                  </tr>
                </thead>
                <tbody>
                  {sg.map((x) => (
                    <tr key={x.segment}>
                      <td>
                        <b>{x.segment}</b>
                      </td>
                      <td>{x.n}</td>
                      <td>{x.recency}</td>
                      <td>{x.frequency}</td>
                      <td>{x.monetary}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {tab === 'model' && modelCmp && (
          <div className="grid">
            <div className="card">
              <b>K-Means elbow (inertia)</b>
              <div className="chart">
                <ResponsiveContainer>
                  <LineChart data={modelCmp.elbow}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="k" />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="inertia" stroke={COL[0]} dot />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="card wrap">
              <b>Model metrics</b>
              <p className="mut">Segments use K-Means; GMM and DBSCAN are compared here only.</p>
              <table>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Clusters</th>
                    <th>Silhouette ↑</th>
                    <th>Davies-Bouldin ↓</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(modelCmp.models).map(([n, v]) => (
                    <tr key={n}>
                      <td>
                        <b>{n}</b>
                      </td>
                      <td>{v.n_clusters}</td>
                      <td>{v.silhouette ?? '—'}</td>
                      <td>{v.davies_bouldin ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {tab === 'cust' && (
          <>
            <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
              <input placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
              <select value={segFilter} onChange={(e) => setSegFilter(e.target.value)}>
                <option value="">All segments</option>
                {segNames.map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </div>
            <div className="grid">
              <div className="card wrap" style={{ gridColumn: 'span 2' }}>
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Email</th>
                      <th>Recency</th>
                      <th>Freq</th>
                      <th>Spend</th>
                      <th>Segment</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customers.map((c) => (
                      <tr
                        key={c.id}
                        style={{ cursor: 'pointer' }}
                        onClick={async () => setInbox(await api(`/api/customers/${c.id}/inbox`))}
                      >
                        <td>{c.id}</td>
                        <td>{c.email}</td>
                        <td>{c.recency.toFixed(0)}</td>
                        <td>{c.frequency.toFixed(0)}</td>
                        <td>{c.monetary.toFixed(0)}</td>
                        <td>
                          <span className="tag">{c.segment || '—'}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="card">
                <b>Customer inbox</b>
                {!inbox ? (
                  <p className="mut">Click a customer</p>
                ) : (
                  <>
                    {inbox.notifications.map((n, i) => (
                      <p key={i}>
                        <b>{n.title}</b>
                        <br />
                        {n.message}
                      </p>
                    ))}
                    {inbox.coupons.length > 0 && (
                      <p className="mut">Coupons: {inbox.coupons.map((c) => `${c.code} (${c.discount}%)`).join(', ')}</p>
                    )}
                  </>
                )}
              </div>
            </div>
          </>
        )}

        {tab === 'camp' && (
          <>
            <div className="card wrap" style={{ marginBottom: 16 }}>
              <b>Campaign history</b>
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Segment</th>
                    <th>Customers</th>
                    <th>Discount</th>
                  </tr>
                </thead>
                <tbody>
                  {history.length ? (
                    history.map((h) => (
                      <tr key={h.id}>
                        <td>{h.sent_at}</td>
                        <td>{h.segment}</td>
                        <td>{h.num_customers}</td>
                        <td>{h.discount}%</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4} className="mut">
                        No campaigns yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="grid">
              {sg.length ? (
                [...sg]
                  .sort((a, b) => SEG_ORDER.indexOf(a.segment) - SEG_ORDER.indexOf(b.segment))
                  .map((x) => (
                    <div className="card" key={x.segment}>
                      <span className="tag">{x.segment}</span>{' '}
                      <span className="mut">{x.n} customers</span>
                      <h3>{x.action[0]}</h3>
                      <p>{x.action[1]}</p>
                      <p className="mut">Discount: {x.action[2]}%</p>
                      <button onClick={() => sendCamp(x.segment)}>Send to segment</button>
                    </div>
                  ))
              ) : (
                <p className="mut">Run segmentation first.</p>
              )}
            </div>
          </>
        )}
      </main>
    </>
  )
}
