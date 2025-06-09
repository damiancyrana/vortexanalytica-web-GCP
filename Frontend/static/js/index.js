document.addEventListener('DOMContentLoaded', () => {
  // Security: Dynamic CSP
  const m = document.createElement('meta')
  const n = crypto.randomUUID().replace(/-/g, '')
  m.httpEquiv = 'Content-Security-Policy'
  m.content = `default-src 'self'; script-src 'self' 'nonce-${n}' 'strict-dynamic'; style-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`
  document.head.prepend(m)
  document.querySelectorAll('script:not([src])').forEach(s => s.setAttribute('nonce', n))

  // Global state
  let firebaseApp = null
  let firebaseAuth = null
  let idToken = null
  const AUTH_KEY = 'vortexAuthState'
  const TOKEN_REFRESH = 30 * 60 * 1e3
  let tokenTimer = null
  let sessTimer = null

  // Utility functions
  const getCookie = k => {
    const v = `; ${document.cookie}`.split(`; ${k}=`)
    return v.length === 2 ? v.pop().split(';')[0] : null
  }

  const getCSRFToken = async () => {
    const cookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='))
    if (cookie) return cookie.split('=')[1]

    const field = document.querySelector('input[name*="csrf"]')
    if (field) return field.value

    const meta = document.querySelector('meta[name*="csrf"]')
    if (meta) return meta.getAttribute('content')

    try {
      await fetch('/login', { method: 'GET', credentials: 'same-origin' })
      const newCookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='))
      return newCookie ? newCookie.split('=')[1] : null
    } catch {
      return null
    }
  }

  const saveAuth = st => st && sessionStorage.setItem(AUTH_KEY, JSON.stringify({ ...st, timestamp: Date.now() }))

  const loadAuth = () => {
    const raw = sessionStorage.getItem(AUTH_KEY)
    if (!raw) return null
    const st = JSON.parse(raw)
    if (Date.now() - st.timestamp > 12 * 60 * 60 * 1e3) { 
      clearAuth()
      return null 
    }
    return st
  }

  const clearAuth = () => { 
    idToken = null
    sessionStorage.removeItem(AUTH_KEY)
    clearInterval(tokenTimer) 
  }

  const updateUI = u => {
    const name = document.getElementById('user-display-name')
    const out = document.getElementById('logout-btn')
    if (!u) {
      name && (name.textContent = 'Logged out')
      out && (out.disabled = true, out.style.display = 'none')
      return
    }
    name && (name.textContent = u.name || u.email || u.user_id || 'Użytkownik')
    out && (out.disabled = false, out.style.display = '')
  }

  // Backend session check
  const checkBackendSession = async () => {
    try {
      const r = await fetch('/api/auth/session-status', { credentials: 'same-origin' })
      if (!r.ok) return false
      const d = await r.json()
      if (d.authenticated && d.user) { 
        updateUI(d.user)
        saveAuth({ authenticated: true, user: d.user, source: 'backend' })
        return true 
      }
      clearAuth()
      updateUI(null)
      return false
    } catch { 
      return false 
    }
  }

  // Token refresh logic
  const startTokenRefresh = u => {
    clearInterval(tokenTimer)
    const refresh = async () => { 
      try { 
        idToken = await u.getIdToken(true) 
      } catch { } 
    }
    refresh()
    tokenTimer = setInterval(refresh, TOKEN_REFRESH)
  }

  // Session monitoring
  const startSessionMonitor = () => {
    clearInterval(sessTimer)
    sessTimer = setInterval(async () => {
      if (!await checkBackendSession() && firebaseAuth?.currentUser) {
        await firebaseAuth.signOut()
      }
    }, 5 * 60 * 1e3)
  }

  // Enhanced fetch with auth
  async function fetchWithAuth(url, opt = {}) {
    const h = new Headers(opt.headers || {})
    
    // Add Firebase token for API endpoints
    if (url.startsWith('/api/')) {
      if (!idToken && firebaseAuth?.currentUser) {
        try { 
          idToken = await firebaseAuth.currentUser.getIdToken(true) 
        } catch { }
      }
      idToken && h.set('Authorization', `Bearer ${idToken}`)
    }
    
    // Auto-detect JSON content
    if (opt.body && typeof opt.body === 'string' && !h.has('Content-Type')) {
      try { 
        JSON.parse(opt.body)
        h.set('Content-Type', 'application/json') 
      } catch { }
    }
    
    const r = await fetch(url, { ...opt, headers: h, credentials: 'same-origin' })
    
    // Handle 401 - redirect to login
    if (r.status === 401) {
      if (await checkBackendSession()) { 
        h.delete('Authorization')
        return fetch(url, { ...opt, headers: h, credentials: 'same-origin' }) 
      }
      window.location.href = '/login'
      throw new Error('Unauthorized')
    }
    
    return r
  }
  window.fetchWithAuth = fetchWithAuth

  // Firebase auth state handler
  const handleFirebaseAuthState = async u => {
    if (u) {
      try {
        idToken = await u.getIdToken(true)
        updateUI({ name: u.displayName || u.email, email: u.email, user_id: u.uid })
        saveAuth({ 
          authenticated: true, 
          user: { name: u.displayName || u.email, email: u.email, user_id: u.uid }, 
          source: 'firebase' 
        })
        startTokenRefresh(u)
      } catch { 
        if (!await checkBackendSession()) {
          document.getElementById('contentWrapper').innerHTML = 
            DOMPurify.sanitize('<p style="color:red;text-align:center;padding:20px">Błąd sesji</p>')
        }
      }
    } else { 
      clearInterval(tokenTimer)
      idToken = null
      if (!await checkBackendSession()) { 
        updateUI(null)
        clearAuth() 
      }
    }
  }

  // Show error message
  const showError = m => {
    const w = document.getElementById('contentWrapper')
    w && (w.innerHTML = DOMPurify.sanitize(`<p style="color:red;text-align:center;padding:20px">${m}</p>`))
    const o = document.getElementById('logout-btn')
    o && (o.disabled = true, o.style.display = 'none')
  }

  // Initialize authentication
  const initAuth = async () => {
    const s = loadAuth()
    s?.authenticated && updateUI(s.user)
    
    const r = await fetch('/auth/firebase-config')
    if (!r.ok) { 
      showError('Błąd konfiguracji')
      return 
    }
    
    const cfg = await r.json()
    if (!cfg.apiKey || !cfg.authDomain) { 
      showError('Błędne dane Firebase')
      return 
    }
    
    firebaseApp = firebase.apps.length ? firebase.app() : firebase.initializeApp({ 
      apiKey: cfg.apiKey, 
      authDomain: cfg.authDomain 
    })
    firebaseAuth = firebase.auth()
    
    await checkBackendSession()
    startSessionMonitor()
    firebaseAuth.onAuthStateChanged(handleFirebaseAuthState)
  }

  // Logout
  const logout = async () => {
    const b = document.getElementById('logout-btn')
    b && (b.disabled = true)

    firebaseAuth && await firebaseAuth.signOut()

    const c = await getCSRFToken()
    const h = { 'Content-Type': 'application/json' }
    if (c) {
      h['X-CSRF-Token'] = c
      h['X-CSRFToken'] = c
    }
    
    await fetch('/logout', { method: 'POST', headers: h, credentials: 'same-origin' })
    clearAuth()
    window.location.href = '/login'
  }

  // Setup UI event handlers
  const setupUIHandlers = () => {
    // Navigation buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.addEventListener('click', function () {
        const v = this.dataset.view
        if (!v) return
        
        document.querySelectorAll('.nav-btn').forEach(x => x.classList.remove('active'))
        this.classList.add('active')
        
        document.querySelectorAll('.view-section').forEach(s => {
          const a = s.id === `${v}-view`
          s.style.display = a ? 'flex' : 'none'
          a && v === 'overview' && (s.style.flexDirection = 'column')
          s.classList.toggle('active', a)
        })
      })
    })
    
    // Activate default view
    const def = document.querySelector('.nav-btn.active') || document.querySelector('.nav-btn[data-view="feed"]')
    def && def.click()

    // Theme toggle
    const theme = document.getElementById('theme-toggle-btn')
    if (theme) {
      const ic = theme.querySelector('i')
      const applyTheme = () => {
        const saved = localStorage.getItem('theme')
        const dark = saved === 'dark' || (saved === null && window.matchMedia('(prefers-color-scheme: dark)').matches)
        document.body.classList.toggle('dark-theme', dark)
        ic && (ic.className = dark ? 'fas fa-sun' : 'fas fa-moon')
        window.updateThemeColors && window.updateThemeColors()
      }
      
      applyTheme()
      theme.addEventListener('click', () => {
        const d = document.body.classList.toggle('dark-theme')
        ic && (ic.className = d ? 'fas fa-sun' : 'fas fa-moon')
        localStorage.setItem('theme', d ? 'dark' : 'light')
        window.updateThemeColors && window.updateThemeColors()
      })
    }

    // Logout button
    const out = document.getElementById('logout-btn')
    out && out.addEventListener('click', e => { 
      e.preventDefault()
      !out.disabled && logout() 
    })
  }

  // Initialize
  initAuth()
  setupUIHandlers()
  
  // Cleanup on unload
  window.addEventListener('beforeunload', () => { 
    clearInterval(tokenTimer)
    clearInterval(sessTimer) 
  })
})