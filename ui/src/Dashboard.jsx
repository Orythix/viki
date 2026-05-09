import { useState, useEffect, useCallback } from 'react'
import PropTypes from 'prop-types'
import { API_BASE, getApiHeaders } from './apiConfig'

// ---------------------------------------------------------------------------
// Tiny presentational primitives
// ---------------------------------------------------------------------------

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

function Row({ label, value }) {
  return (
    <div className="dashboard-system-row">
      <span className="label">{label}</span>
      <span>{value}</span>
    </div>
  )
}

function ListBlock({ label, items, render }) {
  if (!items || items.length === 0) return null
  return (
    <div className="dashboard-system-list">
      <span className="label">{label}</span>
      <ul>
        {items.map((item) => (
          <li key={render(item).key}>{render(item).node}</li>
        ))}
      </ul>
    </div>
  )
}

/**
 * Renders one of three states for a panel: error, empty, or content.
 * Eliminates the nested-ternary pattern that Sonar flagged everywhere.
 */
function Panel({ error, isEmpty, emptyMessage, children }) {
  if (error) {
    return <p className="dashboard-error">{error}</p>
  }
  if (isEmpty) {
    return <p className="dashboard-empty">{emptyMessage}</p>
  }
  return children
}

// ---------------------------------------------------------------------------
// Per-section panels (small, single-purpose, low cognitive complexity each)
// ---------------------------------------------------------------------------

function SystemPanel({ health, error }) {
  if (!health) {
    return <p className="dashboard-error">{error || 'Not available'}</p>
  }
  const statusClass = health.status === 'online' ? 'online' : 'offline'
  return (
    <div className="dashboard-system">
      <Row label="Status" value={<span className={`badge ${statusClass}`}>{health.status}</span>} />
      <Row label="Version" value={health.version} />
      {health.tagline && <Row label="Tagline" value={health.tagline} />}
      {health.persona && <Row label="Persona" value={health.persona} />}
      <ListBlock
        label="Differentiators"
        items={health.differentiators || []}
        render={(d) => ({ key: String(d), node: d })}
      />
      <ListBlock
        label="Tools"
        items={health.tools || []}
        render={(t) => ({ key: String(t), node: t })}
      />
    </div>
  )
}

function SkillsPanel({ skills, error }) {
  return (
    <Panel
      error={error}
      isEmpty={!skills || skills.length === 0}
      emptyMessage="No skills registered"
    >
      <ul className="dashboard-skills-list">
        {skills.map((s) => (
          <li key={s.name} className="dashboard-skill-item">
            <strong>{s.name}</strong>
            <span className="skill-desc">{s.description}</span>
            {s.triggers && s.triggers.length > 0 && (
              <span className="skill-triggers">{s.triggers.join(', ')}</span>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  )
}

function ModelsPanel({ models, error }) {
  return (
    <Panel
      error={error}
      isEmpty={!models || models.length === 0}
      emptyMessage="No models configured"
    >
      <ul className="dashboard-models-list">
        {models.map((m) => (
          <li key={m.name} className="dashboard-model-item">
            <strong>{m.name}</strong>
            <span>{m.provider}</span>
            {m.capabilities && m.capabilities.length > 0 && (
              <span className="model-caps">{m.capabilities.join(', ')}</span>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  )
}

function PerformancePanel({ performance, error }) {
  return (
    <Panel
      error={error}
      isEmpty={!performance || performance.length === 0}
      emptyMessage="No performance data"
    >
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
            {performance.map((p) => (
              <tr key={p.name}>
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
    </Panel>
  )
}

function BrainPanel({ brain, error, onClearMemory }) {
  return (
    <Panel
      error={error}
      isEmpty={!brain}
      emptyMessage="Not available"
    >
      <div className="dashboard-brain">
        {brain?.mode && <Row label="Mode" value={brain.mode} />}
        {brain?.last_thought && (
          <div className="dashboard-brain-thought">
            <span className="label">Last thought</span>
            <p>{brain.last_thought}</p>
          </div>
        )}
        {brain?.signals && Object.keys(brain.signals).length > 0 && (
          <div className="dashboard-brain-signals">
            <span className="label">Signals</span>
            <pre>{JSON.stringify(brain.signals, null, 2)}</pre>
          </div>
        )}
        {brain?.trace && brain.trace.length > 0 && (
          <ListBlock
            label="Trace (last 5)"
            items={brain.trace.slice(-5)}
            render={(t) => ({
              key: typeof t === 'string' ? t : JSON.stringify(t),
              node: typeof t === 'string' ? t : JSON.stringify(t),
            })}
          />
        )}
        {onClearMemory && (
          <div className="forge-controls" style={{marginTop: '1rem'}}>
            <button
              type="button"
              className="dashboard-btn ghost"
              onClick={onClearMemory}
            >
              Clear Memory
            </button>
          </div>
        )}
      </div>
    </Panel>
  )
}

function WorldPanel({ world, error }) {
  return (
    <Panel
      error={error}
      isEmpty={!world}
      emptyMessage="Not available"
    >
      <div className="dashboard-world">
        {world?.codebase_graph_summary && (
          <>
            <Row label="Codebase graph nodes" value={world.codebase_graph_summary.count} />
            <ListBlock
              label="Active focus"
              items={world.codebase_graph_summary.active_focus || []}
              render={(a) => ({ key: String(a), node: String(a) })}
            />
          </>
        )}
        <ListBlock
          label="Active context"
          items={world?.active_context || []}
          render={(c) => ({ key: String(c), node: String(c) })}
        />
      </div>
    </Panel>
  )
}

function MissionListBlock({ heading, items, emptyText, onCancel }) {
  return (
    <div className="dashboard-missions-block">
      <h3>{heading}</h3>
      {items.length === 0 ? (
        <p className="dashboard-empty">{emptyText}</p>
      ) : (
        <ul>
          {items.map((m) => (
            <li key={m.id || m.description || JSON.stringify(m)}>
              <div className="mission-row">
                <div className="mission-meta">
                  <strong>{m.description || m.name || m.id}</strong>
                  <span className="mission-tags">
                    <span className={`mission-status status-${m.status || 'pending'}`}>{m.status || 'pending'}</span>
                    {m.type && <span className="mission-type">{m.type}</span>}
                    {typeof m.priority === 'number' && <span className="mission-prio">p{m.priority}</span>}
                  </span>
                </div>
                {onCancel && m.status !== 'cancelled' && m.status !== 'complete' && (
                  <button type="button" className="mission-cancel-btn" onClick={() => onCancel(m.id)}>
                    Cancel
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function MissionsPanel({ missions, error, onCreate, onCancel, draftDescription, onDraftChange }) {
  if (error) return <p className="dashboard-error">{error}</p>
  return (
    <div className="dashboard-missions">
      <form
        className="mission-create-form"
        onSubmit={(e) => {
          e.preventDefault()
          if (draftDescription.trim()) onCreate(draftDescription.trim())
        }}
      >
        <input
          type="text"
          placeholder="New mission description..."
          value={draftDescription}
          onChange={(e) => onDraftChange(e.target.value)}
        />
        <button type="submit" disabled={!draftDescription.trim()}>Queue</button>
      </form>
      <MissionListBlock heading="Queue" items={missions.queue} emptyText="Empty" onCancel={onCancel} />
      <MissionListBlock heading="Active" items={missions.active} emptyText="None" onCancel={onCancel} />
    </div>
  )
}

function SubAgentsPanel({ subagents, error, onCancel }) {
  if (error) return <p className="dashboard-error">{error}</p>
  const items = subagents?.subagents || []
  if (items.length === 0) return <p className="dashboard-empty">No active sub-agents.</p>
  return (
    <div className="dashboard-subagents">
      <ul>
        {items.map((a) => (
          <li key={a.id}>
            <div className="mission-row">
              <div className="mission-meta">
                <strong>{a.name}</strong>
                <span className="mission-tags">
                  <span className={`mission-status status-${a.is_running ? 'active' : 'idle'}`}>
                    {a.is_running ? 'running' : 'finished'}
                  </span>
                  {a.parent && <span className="mission-type">parent: {a.parent}</span>}
                  {(a.capabilities || []).slice(0, 3).map((c) => (
                    <span key={c} className="mission-prio">{c}</span>
                  ))}
                </span>
              </div>
              {a.is_running && onCancel && (
                <button type="button" className="mission-cancel-btn" onClick={() => onCancel(a.id)}>
                  Cancel
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

function formatSuiteScore(info) {
  const parts = []
  if (info.pass_rate !== undefined) {
    parts.push(`pass=${(info.pass_rate * 100).toFixed(1)}%`)
  }
  if (info.mean_score !== undefined) {
    parts.push(`score=${info.mean_score.toFixed(3)}`)
  }
  return parts.join(' ')
}

function CapabilityIndexPanel({ evals, error }) {
  return (
    <Panel
      error={error}
      isEmpty={!evals}
      emptyMessage="No evals run yet. Use scripts/evals/run_all.py."
    >
      <div className="dashboard-evals">
        <Row
          label="Capability Index"
          value={
            <span className="badge online">
              {(evals?.capability_index ?? 0).toFixed(3)}
            </span>
          }
        />
        {evals?.axes &&
          Object.entries(evals.axes).map(([axis, score]) => (
            <Row key={axis} label={axis} value={(score ?? 0).toFixed(3)} />
          ))}
        {evals?.suites &&
          Object.entries(evals.suites).map(([suite, info]) => (
            <Row key={suite} label={suite} value={formatSuiteScore(info)} />
          ))}
      </div>
    </Panel>
  )
}

function BudgetPanel({ budget, error }) {
  return (
    <Panel
      error={error}
      isEmpty={!budget}
      emptyMessage="Budget not configured"
    >
      <div className="dashboard-budget">
        <Row label="Daily cap" value={`$${budget?.daily_usd_cap ?? '—'}`} />
        <Row label="Spent today" value={`$${(budget?.spent_today ?? 0).toFixed(4)}`} />
        <Row label="Per-call cap" value={`$${budget?.per_call_usd_cap ?? '—'}`} />
        {budget?.circuit_breakers &&
          Object.entries(budget.circuit_breakers).map(([prov, st]) => (
            <Row
              key={prov}
              label={prov}
              value={
                <span className={st.tripped ? 'badge offline' : 'badge online'}>
                  {st.tripped ? 'tripped' : 'ok'}
                </span>
              }
            />
          ))}
      </div>
    </Panel>
  )
}

function PromotionHistory({ history }) {
  const recent = (history || []).slice(-5)
  return (
    <ListBlock
      label="Recent decisions"
      items={recent}
      render={(h) => ({
        key: `${h.ts}-${h.candidate}`,
        node: `${h.decision} ${h.candidate} (${(h.candidate_score ?? 0).toFixed(3)})`,
      })}
    />
  )
}

function PromotionPanel({ promotion, error, onPromote, onRollback }) {
  const [draft, setDraft] = useState('')
  return (
    <Panel
      error={error}
      isEmpty={!promotion}
      emptyMessage="No promotion data yet"
    >
      <div className="dashboard-promotion">
        <Row label="Schedule" value={promotion?.schedule} />
        <Row
          label="Lessons"
          value={`${promotion?.current_lessons} / ${promotion?.min_lessons}`}
        />
        {promotion?.promotion_state && (
          <>
            <Row
              label="Current default"
              value={promotion.promotion_state.current_default || 'unset'}
            />
            <Row
              label="Previous default"
              value={promotion.promotion_state.previous_default || '—'}
            />
            <PromotionHistory history={promotion.promotion_state.history} />
          </>
        )}
        {(onPromote || onRollback) && (
          <div className="forge-controls">
            <input
              type="text"
              placeholder="Model name (e.g. viki-evolved-2026-05)"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            {onPromote && (
              <button
                type="button"
                className="dashboard-btn primary"
                disabled={!draft.trim()}
                onClick={() => { onPromote(draft.trim()); setDraft('') }}
              >
                Force promote
              </button>
            )}
            {onRollback && (
              <button
                type="button"
                className="dashboard-btn ghost"
                onClick={() => onRollback(draft.trim() || null)}
              >
                Rollback
              </button>
            )}
          </div>
        )}
      </div>
    </Panel>
  )
}

function Sparkline({ values }) {
  if (!values || values.length < 2) return <span className="sparkline-empty">—</span>
  const w = 80
  const h = 18
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const step = w / (values.length - 1)
  const points = values
    .map((v, i) => `${(i * step).toFixed(2)},${(h - ((v - min) / range) * h).toFixed(2)}`)
    .join(' ')
  return (
    <svg className="sparkline" width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      <polyline fill="none" stroke="currentColor" strokeWidth="1.2" points={points} />
    </svg>
  )
}

Sparkline.propTypes = {
  values: PropTypes.arrayOf(PropTypes.number),
}

function ScorecardPanel({ scorecard, trends, error }) {
  return (
    <Panel
      error={error}
      isEmpty={!scorecard}
      emptyMessage="No scorecard data"
    >
      <div className="dashboard-scorecard">
        {scorecard &&
          Object.entries(scorecard).map(([model, metrics]) => {
            const modelTrends = (trends && trends[model]) || null
            const series = modelTrends?.series || {}
            const regressions = modelTrends?.regressions || []
            return (
              <div className="dashboard-system-list" key={model}>
                <span className="label">
                  {model}
                  {regressions.length > 0 && (
                    <span className="scorecard-regression-tag" title={regressions
                      .map((r) => `${r.metric}: ${r.delta}`)
                      .join('\n')}>
                      {' '}△ {regressions.length} regression{regressions.length === 1 ? '' : 's'}
                    </span>
                  )}
                </span>
                <ul>
                  {Object.entries(metrics).map(([metric, val]) => (
                    <li key={metric} className="scorecard-row">
                      <span className="scorecard-metric-name">{metric}</span>
                      <span className="scorecard-metric-value">{Number(val).toFixed(3)}</span>
                      <Sparkline values={series[metric] || []} />
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
      </div>
    </Panel>
  )
}

function TracesPanel({ traces, error }) {
  return (
    <Panel
      error={error}
      isEmpty={!traces || traces.length === 0}
      emptyMessage="No spans recorded yet"
    >
      <ul className="dashboard-traces">
        {traces.slice(0, 20).map((t) => (
          <li key={`${t.ts}-${t.name}`}>
            <strong>{t.name}</strong>
            <span> — {Number(t.elapsed_ms ?? 0).toFixed(2)} ms</span>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

function TraceTimelinePanel({ traces, error }) {
  if (error) return <p className="dashboard-error">{error}</p>
  const items = (traces || []).filter((t) => t.spans && t.spans.length > 0)
  if (items.length === 0) {
    return <p className="dashboard-empty">No persisted traces yet. Run a request to populate.</p>
  }
  return (
    <div className="trace-gantt">
      {items.slice(0, 5).map((trace) => {
        const start = Math.min(...trace.spans.map((s) => s.started_at || 0))
        const end = Math.max(...trace.spans.map((s) => (s.finished_at || s.started_at || 0)))
        const total = Math.max(0.001, end - start)
        return (
          <div key={trace.trace_id} className="trace-gantt-row">
            <div className="trace-gantt-meta">
              <strong>{trace.trace_id.slice(0, 8)}</strong>
              <span>{trace.span_count} spans · {(total * 1000).toFixed(1)} ms</span>
            </div>
            <div className="trace-gantt-bars">
              {trace.spans.map((s) => {
                const offset = ((s.started_at || start) - start) / total
                const width = ((s.elapsed_ms || 0) / 1000) / total
                return (
                  <div
                    key={s.span_id}
                    className="trace-gantt-bar"
                    style={{
                      left: `${Math.max(0, offset * 100).toFixed(2)}%`,
                      width: `${Math.max(0.5, width * 100).toFixed(2)}%`,
                    }}
                    title={`${s.name} — ${(s.elapsed_ms || 0).toFixed(2)} ms`}
                  >
                    <span>{s.name}</span>
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function MCPPanel({ mcp, error }) {
  return (
    <Panel
      error={error}
      isEmpty={!mcp || !mcp.enabled}
      emptyMessage={mcp?.reason || "MCP not configured"}
    >
      <div className="dashboard-system">
        <Row label="Skill Count" value={mcp?.skill_count || 0} />
        <ListBlock
          label="Servers"
          items={mcp?.servers || []}
          render={(s) => ({
            key: s.name,
            node: (
              <>
                <strong>{s.name}</strong> ({s.tools?.length || 0} tools)
              </>
            ),
          })}
        />
        {mcp?.connection_status && mcp.connection_status.length > 0 && (
          <ListBlock
            label="Connections"
            items={mcp.connection_status}
            render={(s) => ({
              key: s.name,
              node: (
                <>
                  <strong>{s.name}</strong>: <span className={`badge ${s.connected ? 'online' : 'offline'}`}>{s.connected ? 'connected' : 'disconnected'}</span>
                  {s.error && <span className="dashboard-error"> ({s.error})</span>}
                </>
              ),
            })}
          />
        )}
      </div>
    </Panel>
  )
}

function UsagePanel({ usage, error }) {
  return (
    <Panel
      error={error}
      isEmpty={!usage}
      emptyMessage="No usage data"
    >
      <div className="dashboard-system">
        <Row label="Session" value={usage?.session_id} />
        <Row label="Input Tokens" value={usage?.input_tokens} />
        <Row label="Output Tokens" value={usage?.output_tokens} />
        <Row label="Cost (USD)" value={`$${(usage?.total_cost_usd || 0).toFixed(4)}`} />
        {usage?.by_model && Object.keys(usage.by_model).length > 0 && (
          <ListBlock
            label="By Model"
            items={Object.entries(usage.by_model)}
            render={([m, u]) => ({
              key: m,
              node: `${m}: ${u.calls} calls, ${u.input_tokens} in, ${u.output_tokens} out ($${(u.cost_usd || 0).toFixed(4)})`,
            })}
          />
        )}
      </div>
    </Panel>
  )
}

function CodeSearchPanel({ scan, error }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [searching, setSearching] = useState(false)

  const handleSearch = async (e) => {
    e.preventDefault()
    if (!query.trim()) return
    setSearching(true)
    try {
      const res = await fetch(`${API_BASE}/code/search?q=${encodeURIComponent(query)}&top_k=5`, {
        headers: getApiHeaders()
      })
      const data = await res.json()
      setResults(data.chunks || [])
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  return (
    <Panel
      error={error}
      isEmpty={!scan}
      emptyMessage="Code index not available"
    >
      <div className="dashboard-system">
        <Row label="Indexed Files" value={scan?.n_files || 0} />
        <Row label="Indexed Chunks" value={scan?.n_chunks || 0} />
        <Row label="Indexed Symbols" value={scan?.n_symbols || 0} />
        
        <form className="forge-controls" onSubmit={handleSearch} style={{marginTop: '1rem'}}>
          <input 
            type="text" 
            placeholder="Search code..." 
            value={query} 
            onChange={(e) => setQuery(e.target.value)} 
          />
          <button type="button" className="dashboard-btn primary" onClick={handleSearch} disabled={!query.trim() || searching}>
            {searching ? '...' : 'Search'}
          </button>
        </form>

        {results && (
          <ListBlock
            label="Results"
            items={results}
            render={(r) => ({
              key: r.chunk_id || Math.random(),
              node: (
                <div style={{fontSize: '0.9em', marginTop: '4px'}}>
                  <strong>{r.file_path}</strong>
                  {r.score && <span style={{color: '#888'}}> ({(r.score).toFixed(2)})</span>}
                </div>
              ),
            })}
          />
        )}
      </div>
    </Panel>
  )
}

// ---------------------------------------------------------------------------
// Data layer
// ---------------------------------------------------------------------------

const ENDPOINTS = [
  { key: 'health', path: '/health', extract: (d) => d },
  { key: 'skills', path: '/skills', extract: (d) => d.skills || [] },
  { key: 'models', path: '/models', extract: (d) => d.models || [] },
  { key: 'performance', path: '/models/performance', extract: (d) => d.models || [] },
  { key: 'brain', path: '/brain', extract: (d) => d },
  { key: 'world', path: '/world', extract: (d) => d },
  { key: 'missions', path: '/missions', extract: (d) => ({ queue: d.queue || [], active: d.active || [] }) },
  { key: 'subagents', path: '/subagents', extract: (d) => d },
  { key: 'evals', path: '/evals', extract: (d) => d },
  { key: 'budget', path: '/models/budget', extract: (d) => d },
  { key: 'scorecard', path: '/scorecard/segmented', extract: (d) => d },
  { key: 'scorecardTrends', path: '/scorecard/trends?points=30', extract: (d) => d },
  { key: 'promotion', path: '/forge/promotion', extract: (d) => d },
  { key: 'traces', path: '/traces?limit=20', extract: (d) => d.spans || [] },
  { key: 'tracesGrouped', path: '/traces/grouped?limit=10', extract: (d) => d.traces || [] },
  { key: 'mcpServers', path: '/mcp/servers', extract: (d) => d },
  { key: 'usage', path: '/usage', extract: (d) => d },
  { key: 'codeScan', path: '/code/search?action=scan', extract: (d) => d },
]

async function fetchSection(spec) {
  try {
    const res = await fetch(`${API_BASE}${spec.path}`, { headers: getApiHeaders() })
    if (!res.ok) {
      return { key: spec.key, value: null, error: 'Failed to load' }
    }
    const json = await res.json()
    return { key: spec.key, value: spec.extract(json), error: null }
  } catch {
    return { key: spec.key, value: null, error: 'Failed to load' }
  }
}

// ---------------------------------------------------------------------------
// Top-level component
// ---------------------------------------------------------------------------

const INITIAL_DATA = {
  health: null,
  skills: [],
  models: [],
  performance: [],
  brain: null,
  world: null,
  missions: { queue: [], active: [] },
  subagents: { subagents: [] },
  evals: null,
  budget: null,
  scorecard: null,
  scorecardTrends: null,
  promotion: null,
  traces: [],
  tracesGrouped: [],
  mcpServers: null,
  usage: null,
  codeScan: null,
}

// ---------------------------------------------------------------------------
// PropTypes — defined adjacent to each component to satisfy SonarQube S6774.
// ---------------------------------------------------------------------------

Section.propTypes = {
  title: PropTypes.node.isRequired,
  children: PropTypes.node,
  className: PropTypes.string,
}

Card.propTypes = {
  children: PropTypes.node,
  className: PropTypes.string,
}

Row.propTypes = {
  label: PropTypes.node.isRequired,
  value: PropTypes.node,
}

ListBlock.propTypes = {
  label: PropTypes.node.isRequired,
  items: PropTypes.array,
  render: PropTypes.func.isRequired,
}

Panel.propTypes = {
  error: PropTypes.string,
  isEmpty: PropTypes.bool,
  emptyMessage: PropTypes.node,
  children: PropTypes.node,
}

// We use `PropTypes.object` for API-shaped payloads on purpose: these are
// dynamic JSON blobs whose nested keys are documented server-side, so we treat
// the entire object as opaque from React's perspective. This silences the
// `react/prop-types` heuristic (and SonarQube S6774) without forcing us to
// re-declare every backend field here.
const errorProp = PropTypes.string
const apiObject = PropTypes.object

SystemPanel.propTypes = { health: apiObject, error: errorProp }
SkillsPanel.propTypes = { skills: PropTypes.array, error: errorProp }
ModelsPanel.propTypes = { models: PropTypes.array, error: errorProp }
PerformancePanel.propTypes = { performance: PropTypes.array, error: errorProp }
BrainPanel.propTypes = { brain: apiObject, error: errorProp, onClearMemory: PropTypes.func }
WorldPanel.propTypes = { world: apiObject, error: errorProp }
MCPPanel.propTypes = { mcp: apiObject, error: errorProp }
UsagePanel.propTypes = { usage: apiObject, error: errorProp }
CodeSearchPanel.propTypes = { scan: apiObject, error: errorProp }
MissionsPanel.propTypes = {
  missions: PropTypes.shape({
    queue: PropTypes.array,
    active: PropTypes.array,
  }).isRequired,
  error: errorProp,
  onCreate: PropTypes.func,
  onCancel: PropTypes.func,
  draftDescription: PropTypes.string,
  onDraftChange: PropTypes.func,
}
MissionListBlock.propTypes = {
  heading: PropTypes.string.isRequired,
  items: PropTypes.array.isRequired,
  emptyText: PropTypes.string.isRequired,
  onCancel: PropTypes.func,
}
SubAgentsPanel.propTypes = {
  subagents: apiObject,
  error: errorProp,
  onCancel: PropTypes.func,
}
CapabilityIndexPanel.propTypes = { evals: apiObject, error: errorProp }
BudgetPanel.propTypes = { budget: apiObject, error: errorProp }
PromotionPanel.propTypes = {
  promotion: apiObject,
  error: errorProp,
  onPromote: PropTypes.func,
  onRollback: PropTypes.func,
}
PromotionHistory.propTypes = { history: PropTypes.array }
ScorecardPanel.propTypes = { scorecard: apiObject, trends: apiObject, error: errorProp }
TracesPanel.propTypes = { traces: PropTypes.array, error: errorProp }
TraceTimelinePanel.propTypes = { traces: PropTypes.array, error: errorProp }

export default function Dashboard({ onNavigateChat, onNavigateHologram }) {
  const [data, setData] = useState(INITIAL_DATA)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(true)
  const [missionDraft, setMissionDraft] = useState('')

  const applyResults = useCallback((results) => {
    const nextData = { ...INITIAL_DATA }
    const nextErrors = {}
    for (const r of results) {
      if (r.error) {
        nextErrors[r.key] = r.error
      } else {
        nextData[r.key] = r.value
      }
    }
    setData(nextData)
    setErrors(nextErrors)
    setLoading(false)
  }, [])

  const fetchAll = useCallback(async () => {
    setLoading(true)
    setErrors({})
    const results = await Promise.all(ENDPOINTS.map(fetchSection))
    applyResults(results)
  }, [applyResults])

  const createMission = useCallback(async (description) => {
    try {
      await fetch(`${API_BASE}/missions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getApiHeaders() },
        body: JSON.stringify({ description, priority: 50, type: 'maintenance' }),
      })
      setMissionDraft('')
      fetchAll()
    } catch (e) {
      console.error('mission create failed', e)
    }
  }, [fetchAll])

  const cancelMission = useCallback(async (id) => {
    try {
      await fetch(`${API_BASE}/missions/${id}/cancel`, {
        method: 'POST',
        headers: getApiHeaders(),
      })
      fetchAll()
    } catch (e) {
      console.error('mission cancel failed', e)
    }
  }, [fetchAll])

  const cancelSubagent = useCallback(async (id) => {
    try {
      await fetch(`${API_BASE}/subagents/${id}/cancel`, {
        method: 'POST',
        headers: getApiHeaders(),
      })
      fetchAll()
    } catch (e) {
      console.error('subagent cancel failed', e)
    }
  }, [fetchAll])

  const clearMemory = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/memory`, {
        method: 'DELETE',
        headers: getApiHeaders(),
      })
      fetchAll()
    } catch (e) {
      console.error('memory clear failed', e)
    }
  }, [fetchAll])

  const forgePromote = useCallback(async (model) => {
    try {
      await fetch(`${API_BASE}/forge/promote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getApiHeaders() },
        body: JSON.stringify({ model }),
      })
      fetchAll()
    } catch (e) {
      console.error('forge promote failed', e)
    }
  }, [fetchAll])

  const forgeRollback = useCallback(async (model) => {
    try {
      await fetch(`${API_BASE}/forge/rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getApiHeaders() },
        body: JSON.stringify({ model }),
      })
      fetchAll()
    } catch (e) {
      console.error('forge rollback failed', e)
    }
  }, [fetchAll])

  // Initial mount: kick off the network load without flipping `loading`
  // synchronously inside the effect (the initial state is already `true`).
  useEffect(() => {
    let cancelled = false
    Promise.all(ENDPOINTS.map(fetchSection)).then((results) => {
      if (!cancelled) applyResults(results)
    })
    return () => {
      cancelled = true
    }
  }, [applyResults])

  if (loading) {
    return (
      <div className="dashboard dashboard-loading">
        <div className="dashboard-loading-dots">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <p>Loading dashboard…</p>
      </div>
    )
  }

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>VIKI Dashboard</h1>
        <p className="dashboard-subtitle">
          System status, models, skills, and cognitive state
        </p>
        <div className="dashboard-actions">
          <button type="button" className="dashboard-btn primary" onClick={onNavigateChat}>
            Open Chat
          </button>
          <button type="button" className="dashboard-btn secondary" onClick={onNavigateHologram}>
            Hologram
          </button>
          <button type="button" className="dashboard-btn ghost" onClick={fetchAll}>
            Refresh
          </button>
        </div>
      </header>

      <div className="dashboard-grid">
        <Section title="System" className="span-2">
          <Card>
            <SystemPanel health={data.health} error={errors.health} />
          </Card>
        </Section>

        <Section title="Neural Skills">
          <Card>
            <SkillsPanel skills={data.skills} error={errors.skills} />
          </Card>
        </Section>

        <Section title="Models">
          <Card>
            <ModelsPanel models={data.models} error={errors.models} />
          </Card>
        </Section>

        <Section title="Model Performance">
          <Card>
            <PerformancePanel performance={data.performance} error={errors.performance} />
          </Card>
        </Section>

        <Section title="Brain (Cognitive State)">
          <Card>
            <BrainPanel brain={data.brain} error={errors.brain} onClearMemory={clearMemory} />
          </Card>
        </Section>

        <Section title="World Engine">
          <Card>
            <WorldPanel world={data.world} error={errors.world} />
          </Card>
        </Section>

        <Section title="Missions">
          <Card>
            <MissionsPanel
              missions={data.missions}
              error={errors.missions}
              onCreate={createMission}
              onCancel={cancelMission}
              draftDescription={missionDraft}
              onDraftChange={setMissionDraft}
            />
          </Card>
        </Section>

        <Section title="Sub-Agents">
          <Card>
            <SubAgentsPanel
              subagents={data.subagents}
              error={errors.subagents}
              onCancel={cancelSubagent}
            />
          </Card>
        </Section>

        <Section title="Capability Index" className="span-2">
          <Card>
            <CapabilityIndexPanel evals={data.evals} error={errors.evals} />
          </Card>
        </Section>

        <Section title="LLM Budget">
          <Card>
            <BudgetPanel budget={data.budget} error={errors.budget} />
          </Card>
        </Section>

        <Section title="Promotion Gate">
          <Card>
            <PromotionPanel
              promotion={data.promotion}
              error={errors.promotion}
              onPromote={forgePromote}
              onRollback={forgeRollback}
            />
          </Card>
        </Section>

        <Section title="Per-Model Scorecard" className="span-2">
          <Card>
            <ScorecardPanel
              scorecard={data.scorecard}
              trends={data.scorecardTrends}
              error={errors.scorecard}
            />
          </Card>
        </Section>

        <Section title="Recent Trace Spans" className="span-2">
          <Card>
            <TracesPanel traces={data.traces} error={errors.traces} />
          </Card>
        </Section>

        <Section title="Trace Timeline (Gantt)" className="span-2">
          <Card>
            <TraceTimelinePanel traces={data.tracesGrouped} error={errors.tracesGrouped} />
          </Card>
        </Section>

        <Section title="MCP Servers">
          <Card>
            <MCPPanel mcp={data.mcpServers} error={errors.mcpServers} />
          </Card>
        </Section>

        <Section title="Session Usage">
          <Card>
            <UsagePanel usage={data.usage} error={errors.usage} />
          </Card>
        </Section>

        <Section title="Code Search" className="span-2">
          <Card>
            <CodeSearchPanel scan={data.codeScan} error={errors.codeScan} />
          </Card>
        </Section>
      </div>
    </div>
  )
}

Dashboard.propTypes = {
  onNavigateChat: PropTypes.func,
  onNavigateHologram: PropTypes.func,
}
