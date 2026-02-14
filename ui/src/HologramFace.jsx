import { useState, useRef, useEffect, Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import './HologramFace.css'
import HologramGirl3D from './HologramGirl3D'

const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition
const speechSynth = window.speechSynthesis

export default function HologramFace({ apiBase, getApiHeaders, status }) {
  const [mode, setMode] = useState('idle') // 'idle' | 'listening' | 'thinking' | 'speaking'
  const [lastTranscript, setLastTranscript] = useState('')
  const [lastResponse, setLastResponse] = useState('')
  const [error, setError] = useState(null)
  const recognitionRef = useRef(null)
  const utteranceRef = useRef(null)

  const isSttSupported = !!SpeechRecognitionAPI
  const isTtsSupported = !!speechSynth

  useEffect(() => {
    if (!isTtsSupported) return
    const u = new SpeechSynthesisUtterance()
    u.rate = 0.95
    u.pitch = 1
    u.volume = 1
    utteranceRef.current = u

    const onEnd = () => setMode('idle')
    u.addEventListener('end', onEnd)
    return () => u.removeEventListener('end', onEnd)
  }, [isTtsSupported])

  const startListening = () => {
    if (!isSttSupported) {
      setError('Speech recognition is not supported in this browser. Try Chrome or Edge.')
      return
    }
    setError(null)
    setMode('listening')
    setLastTranscript('')
    setLastResponse('')

    const recognition = new SpeechRecognitionAPI()
    recognition.continuous = false
    recognition.interimResults = true
    recognition.lang = 'en-US'

    recognition.onresult = (event) => {
      const result = event.results[event.results.length - 1]
      const transcript = result[0].transcript
      if (result.isFinal) {
        setLastTranscript(transcript)
        sendToViki(transcript)
      }
    }

    recognition.onend = () => {
      setMode((m) => (m === 'listening' ? 'idle' : m))
    }
    recognition.onerror = (event) => {
      setMode('idle')
      if (event.error === 'not-allowed') setError('Microphone access denied.')
      else setError(`Speech recognition error: ${event.error}`)
    }

    recognitionRef.current = recognition
    recognition.start()
  }

  const sendToViki = async (text) => {
    if (!text?.trim()) {
      setMode('idle')
      return
    }
    setMode('thinking')
    setError(null)

    try {
      const headers = { 'Content-Type': 'application/json', ...getApiHeaders() }
      const res = await fetch(`${apiBase}/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ message: text })
      })
      const data = await res.json()

      if (!res.ok) throw new Error(data.error || 'Request failed')
      const responseText = data.response || ''
      setLastResponse(responseText)

      if (isTtsSupported && responseText) {
        setMode('speaking')
        const u = utteranceRef.current
        u.text = responseText
        speechSynth.speak(u)
      } else {
        setMode('idle')
      }
    } catch (err) {
      setError(err.message || 'Failed to get response from VIKI.')
      setMode('idle')
    }
  }

  const stopSpeaking = () => {
    speechSynth.cancel()
    setMode('idle')
  }

  return (
    <div className="hologram-view">
      <div className={`hologram-container hologram-mode-${mode}`}>
        <div className="hologram-face hologram-3d-wrapper">
          <Canvas
            camera={{ position: [0, 0, 2.8], fov: 38 }}
            gl={{ alpha: true, antialias: true }}
            dpr={[1, 2]}
          >
            <color attach="background" args={['transparent']} />
            <Suspense fallback={null}>
              <HologramGirl3D mode={mode} />
              <OrbitControls
                enableZoom={false}
                enablePan={false}
                minPolarAngle={Math.PI / 3}
                maxPolarAngle={Math.PI / 2.2}
                minAzimuthAngle={-Math.PI / 4}
                maxAzimuthAngle={Math.PI / 4}
              />
            </Suspense>
          </Canvas>
          <div className="hologram-scanlines" />
          <div className="hologram-grid" />
        </div>
        <div className="hologram-glow" />
      </div>

      <div className="hologram-controls">
        {mode === 'speaking' && (
          <button type="button" className="hologram-btn hologram-btn-stop" onClick={stopSpeaking}>
            Stop
          </button>
        )}
        {(mode === 'idle' || mode === 'listening') && (
          <button
            type="button"
            className={`hologram-btn hologram-btn-mic ${mode === 'listening' ? 'active' : ''}`}
            onClick={startListening}
            disabled={status !== 'online'}
            title={status !== 'online' ? 'Connect to VIKI first' : 'Hold to talk'}
          >
            <span className="mic-icon" aria-hidden="true" />
            {mode === 'listening' ? 'Listening…' : 'Talk to VIKI'}
          </button>
        )}
        {mode === 'thinking' && (
          <span className="hologram-status">Thinking…</span>
        )}
      </div>

      {!isSttSupported && (
        <p className="hologram-fallback">Voice input needs Chrome or Edge. Use the Dashboard to type.</p>
      )}
      {error && <p className="hologram-error">{error}</p>}
      {lastTranscript && <p className="hologram-transcript">You: {lastTranscript}</p>}
      {lastResponse && mode === 'idle' && !lastTranscript && <p className="hologram-response-preview">{lastResponse.slice(0, 120)}{lastResponse.length > 120 ? '…' : ''}</p>}
    </div>
  )
}
