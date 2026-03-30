import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'

const AuthContext = createContext(null)

const TOKEN_KEY = 'fobe_session'

function loadSession() {
  try {
    const raw = localStorage.getItem(TOKEN_KEY)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

function saveSession(session) {
  if (session) {
    localStorage.setItem(TOKEN_KEY, JSON.stringify(session))
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [session, setSession] = useState(loadSession)
  const [loading, setLoading] = useState(true)

  // On mount, validate stored session
  useEffect(() => {
    if (!session?.access_token) {
      setLoading(false)
      return
    }
    fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${session.access_token}` },
    })
      .then(r => r.json())
      .then(data => {
        if (data.user) {
          setUser(data.user)
        } else {
          // Token expired — try refresh
          if (session.refresh_token) {
            return refreshToken(session.refresh_token)
          }
          setSession(null)
          saveSession(null)
        }
      })
      .catch(() => {
        setSession(null)
        saveSession(null)
      })
      .finally(() => setLoading(false))
  }, [])

  const refreshToken = useCallback(async (refreshTok) => {
    try {
      const resp = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshTok }),
      })
      const data = await resp.json()
      if (data.session) {
        setSession(data.session)
        saveSession(data.session)
        // Re-fetch user with new token
        const me = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${data.session.access_token}` },
        }).then(r => r.json())
        if (me.user) setUser(me.user)
      }
    } catch {
      setSession(null)
      saveSession(null)
      setUser(null)
    }
  }, [])

  const login = useCallback(async (email, password) => {
    const resp = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    const data = await resp.json()
    if (data.error) throw new Error(data.error)
    if (data.session) {
      setSession(data.session)
      saveSession(data.session)
    }
    if (data.user) setUser(data.user)
    return data
  }, [])

  const signup = useCallback(async (email, password) => {
    const resp = await fetch('/api/auth/signup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    const data = await resp.json()
    if (data.error) throw new Error(data.error)
    if (data.session) {
      setSession(data.session)
      saveSession(data.session)
    }
    if (data.user) setUser(data.user)
    return data
  }, [])

  const logout = useCallback(() => {
    setUser(null)
    setSession(null)
    saveSession(null)
  }, [])

  const getToken = useCallback(() => session?.access_token || null, [session])

  return (
    <AuthContext.Provider value={{ user, session, loading, login, signup, logout, getToken }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
