import { useState, useEffect, useRef } from 'react'
import './index.css'

const API_BASE = 'http://localhost:5000/api'

function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [status, setStatus] = useState('offline')
  const [vikiInfo, setVikiInfo] = useState({ name: 'VIKI', version: '2.3.0' })
  const [skills, setSkills] = useState([])
  const [models, setModels] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    fetchHealth()
    fetchSkills()
    fetchModels()
    const interval = setInterval(fetchHealth, 10000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const fetchHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`)
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
      const res = await fetch(`${API_BASE}/skills`)
      const data = await res.json()
      setSkills(data.skills || [])
    } catch (error) {
      console.error('Failed to fetch skills:', error)
    }
  }

  const fetchModels = async () => {
    try {
      const res = await fetch(`${API_BASE}/models`)
      const data = await res.json()
      setModels(data.models || [])
    } catch (error) {
      console.error('Failed to fetch models:', error)
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
        headers: { 'Content-Type': 'application/json' },
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

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="logo-container">
          <div className="logo-orb">V</div>
          <div className="logo-text">
            <h1 className="text-gradient">{vikiInfo.name}</h1>
            <p>Sovereign Intelligence</p>
          </div>
        </div>

        <div className="sidebar-section">
          <h3>Core Diagnostics</h3>
          <div className="model-pill">
            <span>Status</span>
            <span className={`status-badge ${status}`}>{status.toUpperCase()}</span>
          </div>
          <div className="model-pill">
            <span>Kernel</span>
            <span className="muted">v{vikiInfo.version}</span>
          </div>
        </div>

        <div className="sidebar-section">
          <h3>Neural Capabilities</h3>
          <div className="skills-list">
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
              <span style={{ color: 'var(--accent-cyan)' }}>{model.name}</span>
              <span className="muted">{model.provider}</span>
            </div>
          ))}
        </div>
      </aside>

      <main className="main-view">
        <div className="chat-scroller">
          {messages.length === 0 && (
            <div className="empty-state">
              <h1 className="text-gradient">VIKI</h1>
              <p className="muted">SOVEREIGN DIRECTIVE INTERFACE v2.3.0</p>
              <div style={{ marginTop: '2rem', fontSize: '0.8rem', opacity: 0.3 }}>
                Awaiting Initial Input ...
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div key={idx} className={`message-node ${msg.role}`}>
              <div className="message-header">
                <span>{msg.role.toUpperCase()}</span>
                <span>{new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
              </div>
              <div className="message-bubble">
                {msg.content.split('\n').map((line, i) => (
                  <p key={i} style={{ marginBottom: '0.4rem' }}>
                    {line}
                  </p>
                ))}
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="message-node assistant">
              <div className="message-header"><span>DELIBERATING</span></div>
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
              placeholder="Inject command string..."
              disabled={isLoading}
              autoFocus
            />
            <button type="submit" className="btn-send" disabled={isLoading || !input.trim()}>
              {isLoading ? '...' : 'EXECUTE'}
            </button>
          </form>
        </div>
      </main>
    </div>
  )
}

export default App
