import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import './index.css'
import HologramFace from './HologramFace'
import Dashboard from './Dashboard'
import AlertUI from './AlertUI'
import { API_BASE, getApiHeaders, isApiKeyConfigured } from './apiConfig'

function App() {
  const [view, setView] = useState('chat') // 'chat' | 'hologram' | 'dashboard'
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [status, setStatus] = useState('offline')
  const [vikiInfo, setVikiInfo] = useState({ name: 'VIKI', version: '7.3.0' })
  const [, setSkills] = useState([])
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [isLoading, setIsLoading] = useState(false)
  const [streamingPhase, setStreamingPhase] = useState('') // 'received' | 'thinking' | 'final' | ''
  const [apiKeyMissing, setApiKeyMissing] = useState(() => !isApiKeyConfigured())
  const [confirmDialog, setConfirmDialog] = useState(null) // { message, onConfirm }
  const [attachedFiles, setAttachedFiles] = useState([]) // { id, file }[]
  const [retryPayload, setRetryPayload] = useState(null) // { messageText, attachedFiles } | null
  const messagesEndRef = useRef(null)
  const fileInputRef = useRef(null)
  const chatInputRef = useRef(null)
  const abortRef = useRef(null)

  const a11yStreamStatus = useMemo(() => {
    if (!isLoading) return ''
    if (streamingPhase === 'received') return 'Viki received your message.'
    if (streamingPhase === 'thinking') return 'Viki is thinking.'
    if (streamingPhase === 'final') return 'Viki is finishing the reply.'
    if (streamingPhase) return 'Viki is working on a reply.'
    return 'Waiting for Viki.'
  }, [isLoading, streamingPhase])

  useEffect(() => {
    setApiKeyMissing(!isApiKeyConfigured())
    fetchHealth()
    fetchSkills()
    fetchMemory()
    const interval = setInterval(fetchHealth, 10000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  useEffect(() => {
    if (!isLoading) return
    const onKey = (e) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      abortRef.current?.abort()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [isLoading])

  const fetchHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, { headers: getApiHeaders() })
      if (!res.ok) throw new Error('Offline')
      const data = await res.json()
      setStatus('online')
      setVikiInfo(data)
    } catch {
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

  const fetchMemory = async () => {
    try {
      const res = await fetch(`${API_BASE}/memory`, { headers: getApiHeaders() })
      const data = await res.json()
      if (data.messages && data.messages.length > 0) {
        setMessages(data.messages.map(m => ({
          role: m.role,
          content: m.content,
          timestamp: m.timestamp || new Date().toISOString()
        })))
      }
    } catch (error) {
      console.error('Failed to fetch memory:', error)
    }
  }

  const clearMemory = () => {
    setConfirmDialog({
      message: 'Start a new chat? Current messages will be cleared.',
      onConfirm: async () => {
        setConfirmDialog(null)
        try {
          await fetch(`${API_BASE}/memory`, { method: 'DELETE', headers: getApiHeaders() })
          setMessages([])
          setRetryPayload(null)
        } catch (error) {
          console.error('Failed to clear memory:', error)
        }
      },
      onCancel: () => setConfirmDialog(null),
    })
  }

  const addFiles = (e) => {
    const list = e.target.files
    if (!list?.length) return
    const newEntries = Array.from(list).map(file => ({ id: `${Date.now()}-${file.name}-${file.size}`, file }))
    setAttachedFiles(prev => [...prev, ...newEntries])
    e.target.value = ''
  }

  const removeAttachedFile = (id) => {
    setAttachedFiles(prev => prev.filter(x => x.id !== id))
  }

  const stopInFlightRequest = useCallback(() => {
    abortRef.current?.abort()
    queueMicrotask(() => chatInputRef.current?.focus())
  }, [])

  // Parse a Server-Sent Events stream from a fetch response body. Calls
  // `onEvent({event, data})` for each complete event. Resolves on stream end.
  const consumeSSE = async (response, onEvent, signal) => {
    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    let currentEvent = 'message'
    while (true) {
      if (signal?.aborted) {
        try { await reader.cancel() } catch { /* ignore */ }
        throw new DOMException('Aborted', 'AbortError')
      }
      let readResult
      try {
        readResult = await reader.read()
      } catch (err) {
        if (signal?.aborted || err?.name === 'AbortError') {
          throw new DOMException('Aborted', 'AbortError')
        }
        throw err
      }
      const { value, done } = readResult
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let nlIndex
      while ((nlIndex = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, nlIndex)
        buffer = buffer.slice(nlIndex + 2)
        const lines = raw.split('\n')
        let dataPayload = ''
        currentEvent = 'message'
        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            dataPayload += line.slice(5).trim()
          }
        }
        if (dataPayload) {
          let parsed = dataPayload
          try { parsed = JSON.parse(dataPayload) } catch { /* keep as string */ }
          onEvent({ event: currentEvent, data: parsed })
        }
      }
    }
  }

  const sendMessageStreaming = async (messageText, controller) => {
    setStreamingPhase('received')
    let assistantText = ''
    let inserted = false

    try {
      const res = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getApiHeaders() },
        body: JSON.stringify({ message: messageText }),
        signal: controller.signal,
      })
      if (!res.ok || !res.body) {
        throw new Error(`Stream failed (${res.status})`)
      }

      await consumeSSE(res, ({ event, data }) => {
        const payload = data?.payload ?? data
        if (event === 'status') {
          setStreamingPhase(payload?.phase || 'thinking')
        } else if (event === 'partial' || event === 'thought') {
          const chunk = typeof payload === 'string' ? payload : (payload?.text || '')
          if (!chunk) return
          assistantText += chunk
          setMessages(prev => {
            if (!inserted) {
              inserted = true
              return [...prev, {
                role: 'assistant',
                content: assistantText,
                timestamp: new Date().toISOString(),
                streaming: true,
              }]
            }
            const out = prev.slice(0, -1)
            out.push({ ...prev[prev.length - 1], content: assistantText })
            return out
          })
        } else if (event === 'final') {
          const finalText = data?.response ?? payload?.response ?? assistantText
          setMessages(prev => {
            if (inserted) {
              const out = prev.slice(0, -1)
              out.push({
                role: 'assistant',
                content: finalText,
                timestamp: new Date().toISOString(),
              })
              return out
            }
            return [...prev, {
              role: 'assistant',
              content: finalText,
              timestamp: new Date().toISOString(),
            }]
          })
          setStreamingPhase('final')
        } else if (event === 'error') {
          throw new Error(data?.error || payload?.error || 'Streaming error')
        }
      }, controller.signal)
    } catch (error) {
      if (error.name === 'AbortError') {
        setMessages(prev => {
          if (!inserted || prev.length === 0) return prev
          const last = prev[prev.length - 1]
          if (last?.role === 'assistant' && last?.streaming) {
            const suffix = (last.content || '').trim() ? '\n\n_(Stopped.)_' : '_(Stopped.)_'
            return [...prev.slice(0, -1), {
              ...last,
              streaming: false,
              content: `${last.content || ''}${suffix}`,
            }]
          }
          return prev
        })
        return
      }
      if (inserted) {
        setMessages(prev => {
          const last = prev[prev.length - 1]
          if (last?.role === 'assistant' && last?.streaming) {
            return prev.slice(0, -1)
          }
          return prev
        })
      }
      throw error
    } finally {
      setStreamingPhase('')
    }
  }

  const dispatchChat = async (messageText, fileEntries) => {
    const filesToSend = [...fileEntries]
    const userContent = filesToSend.length > 0
      ? `${messageText.trim() || 'Attached file(s)'} (${filesToSend.length} file(s) attached)`
      : messageText
    const userMessage = { role: 'user', content: userContent, timestamp: new Date().toISOString() }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setAttachedFiles([])
    setRetryPayload(null)
    setIsLoading(true)

    const controller = new AbortController()
    abortRef.current = controller
    const retrySnapshot = { messageText, attachedFiles: filesToSend }

    try {
      if (filesToSend.length === 0) {
        await sendMessageStreaming(messageText, controller)
        return
      }

      const formData = new FormData()
      formData.append('message', messageText)
      filesToSend.forEach(({ file }) => formData.append('files', file, file.name))
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: getApiHeaders(),
        body: formData,
        signal: controller.signal,
      })
      const data = await res.json()
      if (data.error) throw new Error(data.error)
      if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: data.response,
        timestamp: data.timestamp || new Date().toISOString(),
      }])
    } catch (error) {
      if (error.name === 'AbortError') {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: '_(Request cancelled.)_',
          timestamp: new Date().toISOString(),
        }])
        return
      }
      const msg = error.message || 'Request failed.'
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${msg}`,
        timestamp: new Date().toISOString(),
        isError: true,
      }])
      setRetryPayload(retrySnapshot)
    } finally {
      abortRef.current = null
      setIsLoading(false)
    }
  }

  const sendMessage = async (e) => {
    e.preventDefault()
    if ((!input.trim() && attachedFiles.length === 0) || isLoading) return
    await dispatchChat(input, attachedFiles)
  }

  const retryLastMessage = () => {
    const p = retryPayload
    if (!p || isLoading) return
    void dispatchChat(p.messageText, p.attachedFiles)
  }

  const dismissRetry = () => setRetryPayload(null)

  const suggestions = [
    'What can you help me with?',
    'Summarize my last message',
    'Run a quick research query',
  ]

  if (view === 'hologram') {
    return (
      <div className="app app-hologram">
        {apiKeyMissing && (
          <div className="api-key-banner" role="status">
            Set <code>VITE_VIKI_API_KEY</code> in <code>ui/.env</code> to match server <code>VIKI_API_KEY</code>.
          </div>
        )}
        <aside className="sidebar sidebar-compact">
          <div className="sidebar-header">
            <div className="logo-wrap">
              <div className="logo-icon">V</div>
              <span className="logo-name">{vikiInfo.name}</span>
            </div>
            <span className={`status-dot ${status}`} title={status} />
          </div>
          <button type="button" className="sidebar-btn primary" onClick={() => setView('chat')}>
            Chat
          </button>
          <button type="button" className="sidebar-btn primary" onClick={() => setView('dashboard')}>
            Dashboard
          </button>
        </aside>
        <main className="main-view main-view-hologram">
          <HologramFace apiBase={API_BASE} getApiHeaders={getApiHeaders} status={status} />
        </main>
        {confirmDialog && (
          <AlertUI
            open
            message={confirmDialog.message}
            variant="confirm"
            confirmLabel="Start new chat"
            cancelLabel="Cancel"
            onConfirm={confirmDialog.onConfirm}
            onCancel={confirmDialog.onCancel}
          />
        )}
      </div>
    )
  }

  return (
    <div className="app chatgpt-layout">
      {apiKeyMissing && (
        <div className="api-key-banner" role="status">
          Set <code>VITE_VIKI_API_KEY</code> in <code>ui/.env</code> (same value as server <code>VIKI_API_KEY</code>) so API calls authenticate. See repo file <code>viki/SECURITY_SETUP.md</code>.
        </div>
      )}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {a11yStreamStatus}
      </div>
      <aside className={`sidebar sidebar-chatgpt ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="sidebar-header">
          <button type="button" className="new-chat-btn" onClick={clearMemory}>
            <span className="new-chat-icon">+</span>
            New chat
          </button>
          <button type="button" className="sidebar-toggle" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'}>
            {sidebarOpen ? '←' : '→'}
          </button>
        </div>
        {sidebarOpen && (
          <>
            <nav className="sidebar-nav" aria-label="Primary navigation">
              <button type="button" className={`sidebar-btn ${view === 'chat' ? 'active' : ''}`} onClick={() => setView('chat')}>
                Chat
              </button>
              <button type="button" className={`sidebar-btn ${view === 'hologram' ? 'active' : ''}`} onClick={() => setView('hologram')}>
                Hologram
              </button>
              <button type="button" className={`sidebar-btn ${view === 'dashboard' ? 'active' : ''}`} onClick={() => setView('dashboard')}>
                Dashboard
              </button>
            </nav>
            <div className="sidebar-footer">
              <div className="sidebar-status">
                <span className={`status-dot ${status}`} />
                <span>{status}</span>
              </div>
              <span className="sidebar-version">v{vikiInfo.version}</span>
            </div>
          </>
        )}
      </aside>

      <main className={`chat-main ${view === 'dashboard' ? 'chat-main-dashboard' : ''}`}>
        {!sidebarOpen && (
          <button
            type="button"
            className="sidebar-open-btn"
            onClick={() => setSidebarOpen(true)}
            aria-label="Open menu"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
            <span>Menu</span>
          </button>
        )}
        {view === 'dashboard' ? (
          <Dashboard onNavigateChat={() => setView('chat')} onNavigateHologram={() => setView('hologram')} />
        ) : (
          <>
            <div
              className="chat-messages"
              role="log"
              aria-label="Chat messages"
              aria-busy={isLoading}
            >
              {messages.length === 0 && (
                <div className="chat-welcome">
                  <div className="chat-welcome-icon">V</div>
                  <h1>{vikiInfo.name}</h1>
                  <p>Sovereign Digital Intelligence. Ask me anything.</p>
                  <div className="suggestions">
                    {suggestions.map((text) => (
                      <button key={text} type="button" className="suggestion-chip" onClick={() => setInput(text)}>
                        {text}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg, idx) => (
                <div
                  key={`${msg.timestamp}-${idx}`}
                  className={`chat-message ${msg.role}`}
                >
                  {msg.role === 'assistant' && <div className="message-avatar" aria-hidden="true">V</div>}
                  <div className="message-body">
                    <div className={`message-content${msg.isError ? ' message-content-error' : ''}`}>
                      {msg.content.split('\n').map((line, i) => (
                        <p key={`${msg.timestamp}-line-${i}`}>{line || '\u00A0'}</p>
                      ))}
                      {msg.streaming && <span className="streaming-cursor" aria-hidden="true">▍</span>}
                    </div>
                  </div>
                  {msg.role === 'user' && <div className="message-avatar user" aria-hidden="true">You</div>}
                </div>
              ))}

              {isLoading && streamingPhase === 'received' && (
                <div className="chat-message assistant" aria-hidden="true">
                  <div className="message-avatar">V</div>
                  <div className="message-body">
                    <div className="message-content typing">
                      <span></span><span></span><span></span>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            <div className="chat-input-wrap">
              {attachedFiles.length > 0 && (
                <div className="chat-file-chips">
                  {attachedFiles.map(({ id, file }) => (
                    <span key={id} className="chat-file-chip">
                      <span className="chat-file-chip-name">{file.name}</span>
                      <button type="button" className="chat-file-chip-remove" onClick={() => removeAttachedFile(id)} aria-label={`Remove ${file.name}`}>×</button>
                    </span>
                  ))}
                </div>
              )}
              {retryPayload && (
                <div className="chat-retry-bar" role="region" aria-label="Retry options">
                  <button type="button" className="chat-retry-btn" onClick={retryLastMessage} disabled={isLoading}>
                    Retry last message
                  </button>
                  <button type="button" className="chat-retry-dismiss" onClick={dismissRetry} disabled={isLoading}>
                    Dismiss
                  </button>
                </div>
              )}
              <form onSubmit={sendMessage} className="chat-input-form">
                <label htmlFor="viki-chat-input" className="sr-only">Message to {vikiInfo.name}</label>
                <input ref={fileInputRef} type="file" multiple accept=".txt,.pdf,.md,.csv,.json,image/*" onChange={addFiles} className="chat-file-input-hidden" aria-hidden="true" tabIndex={-1} />
                <button type="button" className="chat-attach-btn" onClick={() => fileInputRef.current?.click()} disabled={isLoading} aria-label="Attach files">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
                </button>
                <input
                  ref={chatInputRef}
                  id="viki-chat-input"
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Message VIKI..."
                  disabled={isLoading}
                  autoComplete="off"
                  aria-describedby="viki-chat-disclaimer"
                  autoFocus
                />
                {isLoading ? (
                  <button
                    type="button"
                    className="chat-send-btn chat-stop-btn"
                    onClick={stopInFlightRequest}
                    aria-label="Stop generating. Press Escape to stop."
                  >
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="1.5"/></svg>
                  </button>
                ) : (
                  <button type="submit" className="chat-send-btn" disabled={!input.trim() && attachedFiles.length === 0} aria-label="Send message">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M22 2L11 13"/><path d="M22 2L15 22L11 13L2 9L22 2Z"/></svg>
                  </button>
                )}
              </form>
              <p id="viki-chat-disclaimer" className="chat-disclaimer">VIKI can make mistakes. Check important info.</p>
            </div>
          </>
        )}
      </main>
      {confirmDialog && (
        <AlertUI
          open
          message={confirmDialog.message}
          variant="confirm"
          confirmLabel="Start new chat"
          cancelLabel="Cancel"
          onConfirm={confirmDialog.onConfirm}
          onCancel={confirmDialog.onCancel}
        />
      )}
    </div>
  )
}

export default App
