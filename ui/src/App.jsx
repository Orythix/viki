import { useState, useEffect, useRef } from 'react'
import './index.css'
import HologramFace from './HologramFace'

const API_BASE = import.meta.env.VITE_VIKI_API_BASE || 'http://localhost:5000/api'

function getApiHeaders() {
  const key = import.meta.env.VITE_VIKI_API_KEY
  const base = import.meta.env.VITE_VIKI_API_BASE
  console.log(`[VIKI DEBUG] API_BASE: ${base}, Has Key: ${!!key}`)
  if (!key) return {}
  return { Authorization: `Bearer ${key}` }
}

function App() {
  const [view, setView] = useState('hologram') // 'hologram' | 'dashboard' (default: hologram)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [status, setStatus] = useState('offline')
  const [vikiInfo, setVikiInfo] = useState({ name: 'VIKI', version: '7.1.0' })
  const [skills, setSkills] = useState([])
  const [models, setModels] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    fetchHealth()
    fetchSkills()
    fetchModels()
    fetchMemory()
    const interval = setInterval(fetchHealth, 10000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const fetchHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, { headers: getApiHeaders() })
      if (!res.ok) throw new Error('Offline')
      const data = await res.json()
      setStatus('online')
      setVikiInfo(data)
    } catch (error) {
      setStatus('offline')
    }
  }

  const fetchSkills = async () => {
    try {
      const res = await fetch(`${API_BASE}/skills`, { headers: getApiHeaders() })
      const data = await res.json()
      setSkills(data.skills || [])
    } catch (error) {
      console.error('Failed to fetch skills:', error)
    }
  }

  const fetchModels = async () => {
    try {
      const res = await fetch(`${API_BASE}/models`, { headers: getApiHeaders() })
      const data = await res.json()
      setModels(data.models || [])
    } catch (error) {
      console.error('Failed to fetch models:', error)
    }
  }

  const fetchMemory = async () => {
    try {
      const res = await fetch(`${API_BASE}/memory`, { headers: getApiHeaders() })
      const data = await res.json()
      if (data.messages && data.messages.length > 0) {
        const formatted = data.messages.map(m => ({
          role: m.role,
          content: m.content,
          timestamp: m.timestamp || new Date().toISOString()
        }))
        setMessages(formatted)
      }
    } catch (error) {
      console.error('Failed to fetch memory:', error)
    }
  }

  const clearMemory = async () => {
    if (!window.confirm('Erase episodic memory? This cannot be undone.')) return
    try {
      await fetch(`${API_BASE}/memory`, { method: 'DELETE', headers: getApiHeaders() })
      setMessages([])
    } catch (error) {
      console.error('Failed to clear memory:', error)
    }
  }

  const sendMessage = async (e) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return

    const userMessage = {
      role: 'user',
      content: input,
      timestamp: new Date().toISOString()
    }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getApiHeaders() },
        body: JSON.stringify({ message: input })
      })
      const data = await res.json()

      if (data.error) throw new Error(data.error)

      const vikiMessage = {
        role: 'assistant',
        content: data.response,
        timestamp: data.timestamp || new Date().toISOString()
      }
      setMessages(prev => [...prev, vikiMessage])
    } catch (error) {
      const errorMessage = {
        role: 'assistant',
        content: `CRITICAL SYSTEM ERROR: ${error.message}`,
        timestamp: new Date().toISOString()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  if (view === 'hologram') {
    return (
      <div className="app app-hologram">
        <aside className="sidebar sidebar-compact">
          <div className="logo-container">
            <div className="logo-orb">V</div>
            <div className="logo-text">
              <h1 className="text-gradient">{vikiInfo.name}</h1>
              <p>Intelligence</p>
            </div>
          </div>
          <div className="sidebar-section">
            <div className="model-pill">
              <span>Status</span>
              <span className={`status-badge ${status}`}>{status}</span>
            </div>
          </div>
          <button
            type="button"
            className="view-switch-btn"
            onClick={() => setView('dashboard')}
          >
            Dashboard
          </button>
        </aside>
        <main className="main-view main-view-hologram">
          <HologramFace apiBase={API_BASE} getApiHeaders={getApiHeaders} status={status} />
        </main>
      </div>
    )
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo-container">
          <div className="logo-orb">V</div>
          <div className="logo-text">
            <h1 className="text-gradient">{vikiInfo.name}</h1>
            <p>Intelligence</p>
          </div>
        </div>
        <div className="sidebar-section">
          <button
            type="button"
            className="view-switch-btn view-switch-inline"
            onClick={() => setView('hologram')}
          >
            Hologram
          </button>
        </div>
        <div className="sidebar-section">
          <h3>Kernel Diagnostics</h3>
          <div className="model-pill">
            <span>Core Status</span>
            <span className={`status-badge ${status}`}>{status}</span>
          </div>
          <div className="model-pill">
            <span>Sovereign Version</span>
            <span style={{ color: 'var(--text-secondary)', fontWeight: 600 }}>{vikiInfo.version}</span>
          </div>
          <button type="button" className="btn-danger" onClick={clearMemory}>
            Erase episodic logs
          </button>
        </div>

        <div className="sidebar-section" style={{ flex: 1 }}>
          <h3>Neural Skills Registry</h3>
          <div className="skills-list" style={{ maxHeight: '30vh', overflowY: 'auto', paddingRight: '4px' }}>
            {skills.map(skill => (
              <div key={skill.name} className="skill-card">
                <div className="skill-name">{skill.name}</div>
                <div className="skill-desc">{skill.description}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="sidebar-section">
          <h3>Intelligence Tiers</h3>
          {models.slice(0, 3).map(model => (
            <div key={model.name} className="model-pill">
              <span style={{ color: 'var(--accent)', fontWeight: 600 }}>{model.name}</span>
              <span style={{ color: 'var(--text-tertiary)', fontSize: 'var(--text-xs)' }}>{model.provider}</span>
            </div>
          ))}
        </div>
      </aside>

      <main className="main-view">
        <div className="chat-scroller">
          {messages.length === 0 && (
            <div className="empty-state">
              <h1 className="text-gradient">VIKI</h1>
              <p>Sovereign intelligence interface</p>
              <div style={{ marginTop: 'var(--space-8)', display: 'flex', gap: 'var(--space-4)', flexWrap: 'wrap', justifyContent: 'center' }}>
                <span className="status-badge online">Online</span>
                <span className="status-badge online">Secure</span>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div key={idx} className={`message-node ${msg.role}`}>
              <div className="message-header">
                <span style={{ color: msg.role === 'user' ? 'var(--accent-alt)' : 'var(--accent)' }}>
                  {msg.role === 'user' ? 'You' : 'VIKI'}
                </span>
                <span>{new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
              </div>
              <div className="message-bubble">
                {msg.content.includes('```') ? (
                  <div dangerouslySetInnerHTML={{
                    __html: msg.content.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>').replace(/\n/g, '<br/>')
                  }} />
                ) : (
                  msg.content.split('\n').map((line, i) => (
                    <p key={i} style={{ marginBottom: line.trim() === '' ? '0.8rem' : '0.4rem' }}>
                      {line}
                    </p>
                  ))
                )}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="message-node assistant">
              <div className="message-header"><span style={{ color: 'var(--accent)' }}>Thinking</span></div>
              <div className="message-bubble loading-bubble">
                <div className="loading-dot"></div>
                <div className="loading-dot"></div>
                <div className="loading-dot"></div>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="input-wrapper">
          <form onSubmit={sendMessage} className="input-container">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message VIKI..."
              disabled={isLoading}
              autoFocus
            />
            <button type="submit" className="btn-send" disabled={isLoading || !input.trim()}>
              {isLoading ? '…' : 'Send'}
            </button>
          </form>
        </div>
      </main>
    </div>
  )
}

export default App
