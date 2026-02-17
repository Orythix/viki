import { useState, useEffect } from 'react'

const API_BASE = import.meta.env.VITE_VIKI_API_BASE || 'http://localhost:5000/api'

function getApiHeaders() {
  const key = import.meta.env.VITE_VIKI_API_KEY
  if (!key) return {}
  return { Authorization: `Bearer ${key}` }
}

function Section({ title, children, className = '' }) {
  return (
    <section className={`dashboard-section ${className}`}>
      <h2 className="dashboard-section-title">{title}</h2>
      {children}
    </section>
  )
}

function Card({ children, className = '' }) {
  return <div className={`dashboard-card ${className}`}>{children}</div>
}

export default function Dashboard({ onNavigateChat, onNavigateHologram }) {
  const [health, setHealth] = useState(null)
  const [skills, setSkills] = useState([])
  const [models, setModels] = useState([])
  const [performance, setPerformance] = useState([])
  const [brain, setBrain] = useState(null)
  const [world, setWorld] = useState(null)
  const [missions, setMissions] = useState({ queue: [], active: [] })
  const [loading, setLoading] = useState(true)
  const [errors, setErrors] = useState({})

  const fetchAll = async () => {
    setLoading(true)
    setErrors({})
    const e = {}

    try {
      const [healthRes, skillsRes, modelsRes, perfRes, brainRes, worldRes, missionsRes] = await Promise.allSettled([
        fetch(`${API_BASE}/health`, { headers: getApiHeaders() }),
        fetch(`${API_BASE}/skills`, { headers: getApiHeaders() }),
        fetch(`${API_BASE}/models`, { headers: getApiHeaders() }),
        fetch(`${API_BASE}/models/performance`, { headers: getApiHeaders() }),
        fetch(`${API_BASE}/brain`, { headers: getApiHeaders() }),
        fetch(`${API_BASE}/world`, { headers: getApiHeaders() }),
        fetch(`${API_BASE}/missions`, { headers: getApiHeaders() }),
      ])

      if (healthRes.status === 'fulfilled' && healthRes.value.ok) {
        const data = await healthRes.value.json()
        setHealth(data)
      } else if (healthRes.status === 'fulfilled' && !healthRes.value.ok) e.health = 'Failed to load'
      else e.health = 'Failed to load'

      if (skillsRes.status === 'fulfilled' && skillsRes.value.ok) {
        const data = await skillsRes.value.json()
        setSkills(data.skills || [])
      } else e.skills = 'Failed to load'

      if (modelsRes.status === 'fulfilled' && modelsRes.value.ok) {
        const data = await modelsRes.value.json()
        setModels(data.models || [])
      } else e.models = 'Failed to load'

      if (perfRes.status === 'fulfilled' && perfRes.value.ok) {
        const data = await perfRes.value.json()
        setPerformance(data.models || [])
      } else e.performance = 'Failed to load'

      if (brainRes.status === 'fulfilled' && brainRes.value.ok) {
        const data = await brainRes.value.json()
        setBrain(data)
      } else e.brain = 'Failed to load'

      if (worldRes.status === 'fulfilled' && worldRes.value.ok) {
        const data = await worldRes.value.json()
        setWorld(data)
      } else e.world = 'Failed to load'

      if (missionsRes.status === 'fulfilled' && missionsRes.value.ok) {
        const data = await missionsRes.value.json()
        setMissions({ queue: data.queue || [], active: data.active || [] })
      } else e.missions = 'Failed to load'
    } catch (err) {
      e.general = err.message
    }
    setErrors(e)
    setLoading(false)
  }

  useEffect(() => {
    fetchAll()
  }, [])

  if (loading) {
    return (
      <div className="dashboard dashboard-loading">
        <div className="dashboard-loading-dots">
          <span></span><span></span><span></span>
        </div>
        <p>Loading dashboard…</p>
      </div>
    )
  }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>VIKI Dashboard</h1>
        <p className="dashboard-subtitle">System status, models, skills, and cognitive state</p>
        <div className="dashboard-actions">
          <button type="button" className="dashboard-btn primary" onClick={onNavigateChat}>Open Chat</button>
          <button type="button" className="dashboard-btn secondary" onClick={onNavigateHologram}>Hologram</button>
          <button type="button" className="dashboard-btn ghost" onClick={fetchAll}>Refresh</button>
        </div>
      </header>

      <div className="dashboard-grid">
        <Section title="System" className="span-2">
          <Card>
            {health ? (
              <div className="dashboard-system">
                <div className="dashboard-system-row">
                  <span className="label">Status</span>
                  <span className={`badge ${health.status === 'online' ? 'online' : 'offline'}`}>{health.status}</span>
                </div>
                <div className="dashboard-system-row">
                  <span className="label">Version</span>
                  <span>{health.version}</span>
                </div>
                {health.tagline && (
                  <div className="dashboard-system-row">
                    <span className="label">Tagline</span>
                    <span>{health.tagline}</span>
                  </div>
                )}
                {health.persona && (
                  <div className="dashboard-system-row">
                    <span className="label">Persona</span>
                    <span>{health.persona}</span>
                  </div>
                )}
                {health.differentiators && health.differentiators.length > 0 && (
                  <div className="dashboard-system-list">
                    <span className="label">Differentiators</span>
                    <ul>{health.differentiators.map((d, i) => <li key={i}>{d}</li>)}</ul>
                  </div>
                )}
                {health.tools && health.tools.length > 0 && (
                  <div className="dashboard-system-list">
                    <span className="label">Tools</span>
                    <ul>{health.tools.map((t, i) => <li key={i}>{t}</li>)}</ul>
                  </div>
                )}
              </div>
            ) : (
              <p className="dashboard-error">{errors.health || 'Not available'}</p>
            )}
          </Card>
        </Section>

        <Section title="Neural Skills">
          <Card>
            {errors.skills ? (
              <p className="dashboard-error">{errors.skills}</p>
            ) : skills.length === 0 ? (
              <p className="dashboard-empty">No skills registered</p>
            ) : (
              <ul className="dashboard-skills-list">
                {skills.map((s, i) => (
                  <li key={i} className="dashboard-skill-item">
                    <strong>{s.name}</strong>
                    <span className="skill-desc">{s.description}</span>
                    {s.triggers && s.triggers.length > 0 && (
                      <span className="skill-triggers">{s.triggers.join(', ')}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </Section>

        <Section title="Models">
          <Card>
            {errors.models ? (
              <p className="dashboard-error">{errors.models}</p>
            ) : models.length === 0 ? (
              <p className="dashboard-empty">No models configured</p>
            ) : (
              <ul className="dashboard-models-list">
                {models.map((m, i) => (
                  <li key={i} className="dashboard-model-item">
                    <strong>{m.name}</strong>
                    <span>{m.provider}</span>
                    {m.capabilities && m.capabilities.length > 0 && (
                      <span className="model-caps">{m.capabilities.join(', ')}</span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </Section>

        <Section title="Model Performance">
          <Card>
            {errors.performance ? (
              <p className="dashboard-error">{errors.performance}</p>
            ) : performance.length === 0 ? (
              <p className="dashboard-empty">No performance data</p>
            ) : (
              <div className="dashboard-perf-table-wrap">
                <table className="dashboard-perf-table">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Trust</th>
                      <th>Latency</th>
                      <th>Calls</th>
                      <th>Errors</th>
                    </tr>
                  </thead>
                  <tbody>
                    {performance.map((p, i) => (
                      <tr key={i}>
                        <td>{p.name}</td>
                        <td>{p.trust_score}</td>
                        <td>{p.avg_latency}s</td>
                        <td>{p.call_count}</td>
                        <td>{p.error_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </Section>

        <Section title="Brain (Cognitive State)">
          <Card>
            {errors.brain ? (
              <p className="dashboard-error">{errors.brain}</p>
            ) : !brain ? (
              <p className="dashboard-empty">Not available</p>
            ) : (
              <div className="dashboard-brain">
                {brain.mode && (
                  <div className="dashboard-system-row">
                    <span className="label">Mode</span>
                    <span>{brain.mode}</span>
                  </div>
                )}
                {brain.last_thought && (
                  <div className="dashboard-brain-thought">
                    <span className="label">Last thought</span>
                    <p>{brain.last_thought}</p>
                  </div>
                )}
                {brain.signals && Object.keys(brain.signals).length > 0 && (
                  <div className="dashboard-brain-signals">
                    <span className="label">Signals</span>
                    <pre>{JSON.stringify(brain.signals, null, 2)}</pre>
                  </div>
                )}
                {brain.trace && brain.trace.length > 0 && (
                  <div className="dashboard-brain-trace">
                    <span className="label">Trace (last 5)</span>
                    <ul>{brain.trace.map((t, i) => <li key={i}>{typeof t === 'string' ? t : JSON.stringify(t)}</li>)}</ul>
                  </div>
                )}
              </div>
            )}
          </Card>
        </Section>

        <Section title="World Engine">
          <Card>
            {errors.world ? (
              <p className="dashboard-error">{errors.world}</p>
            ) : !world ? (
              <p className="dashboard-empty">Not available</p>
            ) : (
              <div className="dashboard-world">
                {world.codebase_graph_summary && (
                  <>
                    <div className="dashboard-system-row">
                      <span className="label">Codebase graph nodes</span>
                      <span>{world.codebase_graph_summary.count}</span>
                    </div>
                    {world.codebase_graph_summary.active_focus && world.codebase_graph_summary.active_focus.length > 0 && (
                      <div className="dashboard-system-list">
                        <span className="label">Active focus</span>
                        <ul>{world.codebase_graph_summary.active_focus.map((a, i) => <li key={i}>{String(a)}</li>)}</ul>
                      </div>
                    )}
                  </>
                )}
                {world.active_context && world.active_context.length > 0 && (
                  <div className="dashboard-system-list">
                    <span className="label">Active context</span>
                    <ul>{world.active_context.map((c, i) => <li key={i}>{String(c)}</li>)}</ul>
                  </div>
                )}
              </div>
            )}
          </Card>
        </Section>

        <Section title="Missions">
          <Card>
            {errors.missions ? (
              <p className="dashboard-error">{errors.missions}</p>
            ) : (
              <div className="dashboard-missions">
                <div className="dashboard-missions-block">
                  <h3>Queue</h3>
                  {missions.queue.length === 0 ? (
                    <p className="dashboard-empty">Empty</p>
                  ) : (
                    <ul>{missions.queue.map((m, i) => <li key={i}>{m.name || m.id || JSON.stringify(m)}</li>)}</ul>
                  )}
                </div>
                <div className="dashboard-missions-block">
                  <h3>Active</h3>
                  {missions.active.length === 0 ? (
                    <p className="dashboard-empty">None</p>
                  ) : (
                    <ul>{missions.active.map((m, i) => <li key={i}>{m.name || m.id || JSON.stringify(m)}</li>)}</ul>
                  )}
                </div>
              </div>
            )}
          </Card>
        </Section>
      </div>
    </div>
  )
}
