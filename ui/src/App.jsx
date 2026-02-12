import { useState, useEffect, useRef } from 'react'
import './App.css'

const API_BASE = 'http://localhost:5000/api'

function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [status, setStatus] = useState('offline')
  const [vikiInfo, setVikiInfo] = useState({ name: 'VIKI', version: '...' })
  const [skills, setSkills] = useState([])
  const [models, setModels] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    fetchHealth()
    fetchSkills()
    fetchModels()
    const interval = setInterval(fetchHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const fetchHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`)
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

    const userMessage = { role: 'user', content: input, timestamp: new Date().toISOString() }
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

      const vikiMessage = {
        role: 'assistant',
        content: data.response,
        timestamp: data.timestamp || new Date().toISOString()
      }
      setMessages(prev => [...prev, vikiMessage])
    } catch (error) {
      const errorMessage = {
        role: 'error',
        content: `Error: ${error.message}`,
        timestamp: new Date().toISOString()
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const clearMemory = async () => {
    try {
      await fetch(`${API_BASE}/memory`, { method: 'DELETE' })
      setMessages([])
    } catch (error) {
      console.error('Failed to clear memory:', error)
    }
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="header glass">
        <div className="header-content">
          <div className="logo-section">
            <div className="logo-icon">VIKI</div>
            <div>
              <h1 className="text-gradient">{vikiInfo.name}</h1>
              <p className="version">v{vikiInfo.version}</p>
            </div>
          </div>
          <div className="status-section">
            <div className={`status-indicator ${status}`}></div>
            <span className="status-text">{status}</span>
          </div>
        </div>
      </header>

      <div className="main-container">
        {/* Sidebar */}
        <aside className="sidebar glass">
          <section className="sidebar-section">
            <h3>Active Skills</h3>
            <div className="skills-list">
              {skills.map(skill => (
                <div key={skill.name} className="skill-item">
                  <div className="skill-info">
                    <div className="skill-name">{skill.name}</div>
                    <div className="skill-desc">{skill.description}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="sidebar-section">
            <h3>Models</h3>
            <div className="models-list">
              {models.map(model => (
                <div key={model.name} className="model-item">
                  <div className="model-name">{model.name}</div>
                  <div className="model-capabilities">
                    {model.capabilities.slice(0, 2).map(cap => (
                      <span key={cap} className="capability-tag">{cap}</span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <button onClick={clearMemory} className="btn-clear">
            Clear Memory
          </button>
        </aside>

        {/* Chat Area */}
        <main className="chat-container">
          <div className="messages-area">
            {messages.length === 0 && (
              <div className="welcome-message">
                <h2 className="text-gradient">VIKI Interface</h2>
                <p>Virtual Intelligence Knowledge Interface</p>
                <p className="muted">Send a message to begin</p>
              </div>
            )}
            {messages.map((msg, idx) => (
              <div key={idx} className={`message message-${msg.role}`}>
                <div className="message-header">
                  <span className="message-role">{msg.role === 'user' ? 'YOU' : msg.role === 'assistant' ? 'VIKI' : 'SYSTEM'}</span>
                  <span className="message-time">{new Date(msg.timestamp).toLocaleTimeString()}</span>
                </div>
                <div className="message-content">{msg.content}</div>
              </div>
            ))}
            {isLoading && (
              <div className="message message-loading">
                <div className="message-header">
                  <span className="message-role">VIKI</span>
                </div>
                <div className="message-content">
                  <span className="loading-dots">Processing</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={sendMessage} className="input-area glass">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Send a directive to VIKI..."
              className="message-input"
              disabled={isLoading}
            />
            <button type="submit" className="btn-send" disabled={isLoading || !input.trim()}>
              <span>SEND</span>
            </button>
          </form>
        </main>
      </div>
    </div>
  )
}

export default App
