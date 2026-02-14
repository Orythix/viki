import { useState, useEffect, useRef } from 'react'
import './index.css'

const API_BASE = 'http://localhost:5000/api'

function App() {
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

  const fetchMemory = async () => {
    try {
      const res = await fetch(`${API_BASE}/memory`)
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
      await fetch(`${API_BASE}/memory`, { method: 'DELETE' })
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
            <p>Intelligence</p>
          </div>
        </div>

        <div className="sidebar-section">
          <h3>Kernel Diagnostics</h3>
          <div className="model-pill">
            <span>Core Status</span>
            <span className={`status-badge ${status}`}>{status}</span>
          </div>
          <div className="model-pill">
            <span>Sovereign Version</span>
            <span style={{ color: 'var(--text-dim)', fontWeight: 600 }}>{vikiInfo.version}</span>
          </div>
          <button 
            onClick={clearMemory}
            style={{ 
              width: '100%', 
              background: 'hsla(350, 100%, 50%, 0.1)', 
              border: '1px solid hsla(350, 100%, 50%, 0.2)',
              color: 'hsl(350, 100%, 60%)',
              padding: '0.75rem',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.75rem',
              fontWeight: 700,
              cursor: 'pointer',
              marginTop: '0.5rem',
              transition: 'var(--transition-fast)'
            }}
            onMouseOver={(e) => e.target.style.background = 'hsla(350, 100%, 50%, 0.2)'}
            onMouseOut={(e) => e.target.style.background = 'hsla(350, 100%, 50%, 0.1)'}
          >
            ERASE EPISODIC LOGS
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
              <span style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>{model.name}</span>
              <span style={{ color: 'var(--text-mute)', fontSize: '0.7rem' }}>{model.provider}</span>
            </div>
          ))}
        </div>
      </aside>

      <main className="main-view">
        <div className="chat-scroller">
          {messages.length === 0 && (
            <div className="empty-state">
              <h1 className="text-gradient">VIKI</h1>
              <p>SOVEREIGN DIRECTIVE INTERFACE</p>
              <div style={{ marginTop: '3rem', display: 'flex', gap: '2rem' }}>
                 <div className="status-badge online" style={{ fontSize: '0.7rem' }}>NEURAL NET ACTIVE</div>
                 <div className="status-badge online" style={{ fontSize: '0.7rem' }}>ENCRYPTION STABLE</div>
              </div>
            </div>
          )}

          {messages.map((msg, idx) => (
            <div key={idx} className={`message-node ${msg.role}`}>
              <div className="message-header">
                <span style={{ color: msg.role === 'user' ? 'var(--accent-purple)' : 'var(--accent-cyan)' }}>
                  {msg.role === 'user' ? 'DIRECTIVE' : 'RESPONSE'}
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
              <div className="message-header"><span style={{ color: 'var(--accent-cyan)' }}>DELIBERATING</span></div>
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
              placeholder="Inject command string or data stream..."
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
