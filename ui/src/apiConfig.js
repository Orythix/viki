/** Shared API base URL, session id, and auth headers for the dashboard. */

export const API_BASE = import.meta.env.VITE_VIKI_API_BASE || 'http://localhost:5000/api'

const SESSION_STORAGE_KEY = 'viki-session-id'

export function getSessionId() {
  let sessionId = window.localStorage.getItem(SESSION_STORAGE_KEY)
  if (!sessionId) {
    sessionId =
      window.crypto?.randomUUID?.() || `viki-${Date.now()}-${Math.random().toString(16).slice(2)}`
    window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId)
  }
  return sessionId
}

/** True when VITE_VIKI_API_KEY is set (required for /api/* except local dev fallback on server). */
export function isApiKeyConfigured() {
  const k = import.meta.env.VITE_VIKI_API_KEY
  return typeof k === 'string' && k.trim().length > 0
}

export function getApiHeaders() {
  const key = import.meta.env.VITE_VIKI_API_KEY
  const headers = { 'X-Session-Id': getSessionId() }
  if (key) headers.Authorization = `Bearer ${key}`
  return headers
}
