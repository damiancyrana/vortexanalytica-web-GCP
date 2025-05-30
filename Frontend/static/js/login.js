/**
 * Login page script - handles authentication with Firebase and backend session creation
 */
document.addEventListener('DOMContentLoaded', () => {
  // Global Firebase references
  let firebaseApp = null
  let firebaseAuth = null

  // DOM Elements cache
  const elements = {
    loginForm: document.getElementById('login-form'),
    registerForm: document.getElementById('register-form'),
    loginEmail: document.getElementById('login-email'),
    loginPassword: document.getElementById('login-password'),
    loginButton: document.getElementById('login-button'),
    loginMessage: document.getElementById('login-message-area'),
    regName: document.getElementById('reg-name'),
    regEmail: document.getElementById('reg-email'),
    regPassword: document.getElementById('reg-password'),
    regConfirmPassword: document.getElementById('reg-confirm-password'),
    regTerms: document.getElementById('reg-terms'),
    registerButton: document.getElementById('register-button'),
    registerMessage: document.getElementById('register-message-area'),
    forgotPassword: document.querySelector('.forgot-password'),
    strengthBar: document.querySelector('#register-form .strength-bar')
  }

  // CSRF utilities
  const getCSRFToken = async () => {
    // Try cookie first
    const cookie = document.cookie.split('; ')
      .find(row => row.startsWith('csrftoken='))
    if (cookie) return cookie.split('=')[1]
    
    // Try HTML elements
    const field = document.querySelector('input[name*="csrf"]')
    if (field) return field.value
    
    const meta = document.querySelector('meta[name*="csrf"]')
    if (meta) return meta.getAttribute('content')
    
    // Fetch from server
    try {
      await fetch('/login', { method: 'GET', credentials: 'same-origin' })
      const newCookie = document.cookie.split('; ')
        .find(row => row.startsWith('csrftoken='))
      return newCookie ? newCookie.split('=')[1] : null
    } catch {
      return null
    }
  }

  // UI utilities
  const ui = {
    getActiveMessageArea: () => {
      const activeForm = document.querySelector('.auth-form.active')
      return activeForm?.id.replace('-form', '-message-area') || 'login-message-area'
    },
    
    setLoading: (button, loading) => {
      if (!button) return
      if (!button.dataset.originalHTML) {
        button.dataset.originalHTML = button.innerHTML
      }
      button.disabled = loading
      button.classList.toggle('loading', loading)
      if (!loading) button.innerHTML = button.dataset.originalHTML
    },
    
    showMessage: (message, type, areaId = null) => {
      const area = document.getElementById(areaId || ui.getActiveMessageArea())
      if (!area) return
      area.textContent = message
      area.className = `auth-message ${type}`
      area.style.display = 'block'
      if (type === 'error') {
        setTimeout(() => {
          if (area.textContent === message) {
            area.style.display = 'none'
            area.textContent = ''
          }
        }, 7000)
      }
    },
    
    showError: (msg, area) => ui.showMessage(msg, 'error', area),
    showSuccess: (msg, area) => ui.showMessage(msg, 'success', area),
    
    clearMessages: () => {
      ['login-message-area', 'register-message-area'].forEach(id => {
        const area = document.getElementById(id)
        if (area) {
          area.innerHTML = ''
          area.style.display = 'none'
          area.className = 'auth-message'
        }
      })
    }
  }

  // Password strength checker
  const checkPasswordStrength = password => {
    if (!password) return 0
    let strength = 0
    if (password.length >= 8) strength++
    if (/[A-Z]/.test(password)) strength++
    if (/[a-z]/.test(password)) strength++
    if (/\d/.test(password)) strength++
    if (/[^A-Za-z0-9]/.test(password)) strength++
    return strength
  }

  const updatePasswordStrength = event => {
    const password = event.target.value
    const bar = elements.strengthBar
    if (!bar) return
    
    const strength = checkPasswordStrength(password)
    const percentage = (strength / 5) * 100
    bar.style.width = `${percentage}%`
    
    const colors = ['#FF4B4B', '#FFA500', '#FFD700', '#90EE90', '#4CAF50']
    bar.style.backgroundColor = colors[Math.max(0, strength - 1)] || '#ddd'
  }

  // Create backend session after Firebase auth
  const createBackendSession = async user => {
    if (!user) {
      ui.showError('Authentication error', ui.getActiveMessageArea())
      return
    }
    
    const activeButton = document.querySelector('.auth-form.active button[type="submit"]')
    ui.setLoading(activeButton, true)
    document.querySelectorAll('.social-btn').forEach(btn => ui.setLoading(btn, true))
    ui.clearMessages()
    
    try {
      const csrfToken = await getCSRFToken()
      const idToken = await user.getIdToken(true)
      
      const headers = { 'Content-Type': 'application/json' }
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken
        headers['X-CSRFToken'] = csrfToken
      }
      
      const response = await fetch('/auth/firebase-session-login', {
        method: 'POST',
        headers,
        body: JSON.stringify({ token: idToken }),
        credentials: 'same-origin'
      })
      
      if (response.ok) {
        sessionStorage.setItem('authActionCompleted', 'true')
        window.location.href = '/index'
      } else {
        const error = await response.json().catch(() => ({ detail: `Server error ${response.status}` }))
        ui.showError(`Login error: ${error.detail || 'Cannot create session'}`, ui.getActiveMessageArea())
        firebaseAuth && await firebaseAuth.signOut()
        ui.setLoading(activeButton, false)
        document.querySelectorAll('.social-btn').forEach(btn => ui.setLoading(btn, false))
      }
    } catch (error) {
      ui.showError(`Error: ${error.message || 'Check your connection'}`, ui.getActiveMessageArea())
      ui.setLoading(activeButton, false)
      document.querySelectorAll('.social-btn').forEach(btn => ui.setLoading(btn, false))
    }
  }

  // Auth handlers
  const authHandlers = {
    login: async event => {
      event.preventDefault()
      const email = elements.loginEmail?.value.trim()
      const password = elements.loginPassword?.value
      
      ui.clearMessages()
      
      if (!email || !password) {
        ui.showError('Please enter email and password', 'login-message-area')
        return
      }
      
      if (!firebaseAuth) {
        ui.showError('Login system is not ready', 'login-message-area')
        return
      }
      
      ui.setLoading(elements.loginButton, true)
      
      try {
        await firebaseAuth.signInWithEmailAndPassword(email, password)
      } catch (error) {
        const errors = {
          'auth/invalid-email': 'Invalid email format',
          'auth/user-disabled': 'This account has been disabled',
          'auth/user-not-found': 'Invalid email or password',
          'auth/wrong-password': 'Invalid email or password',
          'auth/invalid-credential': 'Invalid email or password',
          'auth/network-request-failed': 'Network error. Check your connection'
        }
        ui.showError(errors[error.code] || `Login error (${error.code || 'unknown'})`, 'login-message-area')
        ui.setLoading(elements.loginButton, false)
      }
    },
    
    register: async event => {
      event.preventDefault()
      const name = elements.regName?.value.trim()
      const email = elements.regEmail?.value.trim()
      const password = elements.regPassword?.value
      const confirmPassword = elements.regConfirmPassword?.value
      const termsAccepted = elements.regTerms?.checked
      
      ui.clearMessages()
      
      if (!name || !email || !password || !confirmPassword) {
        ui.showError('Please fill in all fields', 'register-message-area')
        return
      }
      
      if (password !== confirmPassword) {
        ui.showError('Passwords do not match', 'register-message-area')
        return
      }
      
      if (checkPasswordStrength(password) < 5) {
        ui.showError('Password does not meet security requirements', 'register-message-area')
        return
      }
      
      if (!termsAccepted) {
        ui.showError('You must accept the Terms of Service', 'register-message-area')
        return
      }
      
      if (!firebaseAuth) {
        ui.showError('Registration system is not ready', 'register-message-area')
        return
      }
      
      ui.setLoading(elements.registerButton, true)
      
      try {
        const { user } = await firebaseAuth.createUserWithEmailAndPassword(email, password)
        await user.updateProfile({ displayName: name })
      } catch (error) {
        const errors = {
          'auth/email-already-in-use': 'This email is already registered',
          'auth/invalid-email': 'Invalid email format',
          'auth/operation-not-allowed': 'Registration is currently disabled',
          'auth/weak-password': 'Password is too weak'
        }
        ui.showError(errors[error.code] || `Registration error (${error.code || 'unknown'})`, 'register-message-area')
        ui.setLoading(elements.registerButton, false)
      }
    },
    
    oauth: async provider => {
      const button = document.querySelector(`.auth-form.active .social-btn.${provider}`)
      if (!button || !firebaseAuth) return
      
      const providers = {
        google: () => new firebase.auth.GoogleAuthProvider(),
        microsoft: () => new firebase.auth.OAuthProvider('microsoft.com')
      }
      
      if (!providers[provider]) {
        ui.showError(`Provider "${provider}" is not supported`, ui.getActiveMessageArea())
        return
      }
      
      ui.clearMessages()
      ui.setLoading(button, true)
      
      try {
        await firebaseAuth.signInWithPopup(providers[provider]())
      } catch (error) {
        const errors = {
          'auth/account-exists-with-different-credential': 'Account exists with different sign-in method',
          'auth/popup-closed-by-user': `${provider} sign-in was cancelled`,
          'auth/popup-blocked': `${provider} sign-in popup was blocked`,
          'auth/cancelled-popup-request': 'Cancelled popup request',
          'auth/operation-not-allowed': `${provider} sign-in is not enabled`,
          'auth/unauthorized-domain': 'This domain is not authorized'
        }
        ui.showError(errors[error.code] || `${provider} sign-in error (${error.code || 'unknown'})`, ui.getActiveMessageArea())
        ui.setLoading(button, false)
      }
    },
    
    forgotPassword: event => {
      event.preventDefault()
      const email = elements.loginEmail?.value.trim()
      
      ui.clearMessages()
      
      if (!email) {
        ui.showError('Enter your email address above', 'login-message-area')
        return
      }
      
      if (!firebaseAuth) {
        ui.showError('Password reset system is not ready', 'login-message-area')
        return
      }
      
      ui.showSuccess('Sending password reset instructions...', 'login-message-area')
      
      firebaseAuth.sendPasswordResetEmail(email)
        .then(() => ui.showSuccess('Password reset link sent. Check your email', 'login-message-area'))
        .catch(error => {
          const msg = error.code === 'auth/user-not-found' 
            ? 'No account found with this email' 
            : `Failed to send reset link (${error.code || 'unknown'})`
          ui.showError(msg, 'login-message-area')
        })
    }
  }

  // Initialize Firebase
  const initializeAuth = async () => {
    try {
      const response = await fetch('/auth/firebase-config')
      if (!response.ok) throw new Error(`Error ${response.status} fetching Firebase configuration`)
      
      const config = await response.json()
      if (!config.apiKey || !config.authDomain) throw new Error('Incomplete Firebase configuration')
      
      firebaseApp = firebase.apps.length === 0 
        ? firebase.initializeApp({ apiKey: config.apiKey, authDomain: config.authDomain })
        : firebase.app()
      
      firebaseAuth = firebase.auth()
      
      // Handle auth state changes
      firebaseAuth.onAuthStateChanged(async user => {
        if (user) {
          if (sessionStorage.getItem('creatingSession') === 'true') return
          sessionStorage.setItem('creatingSession', 'true')
          await createBackendSession(user)
          sessionStorage.removeItem('creatingSession')
        } else {
          document.querySelectorAll('.loading').forEach(btn => ui.setLoading(btn, false))
          sessionStorage.removeItem('creatingSession')
          sessionStorage.removeItem('authActionCompleted')
        }
      })
      
      setupEventHandlers()
    } catch (error) {
      const msg = `Authentication system error: ${error.message}`
      ui.showError(msg, 'login-message-area')
      ui.showError(msg, 'register-message-area')
      
      // Disable all buttons
      ;[elements.loginButton, elements.registerButton, ...document.querySelectorAll('.social-btn')]
        .forEach(btn => btn && (btn.disabled = true))
    }
  }

  // Setup event handlers
  const setupEventHandlers = () => {
    // Form submissions
    elements.loginForm?.addEventListener('submit', authHandlers.login)
    elements.registerForm?.addEventListener('submit', authHandlers.register)
    
    // Password strength
    elements.regPassword?.addEventListener('input', updatePasswordStrength)
    
    // OAuth buttons
    document.querySelectorAll('.social-btn.google').forEach(btn => 
      btn.addEventListener('click', () => authHandlers.oauth('google')))
    document.querySelectorAll('.social-btn.microsoft').forEach(btn => 
      btn.addEventListener('click', () => authHandlers.oauth('microsoft')))
    
    // Forgot password
    elements.forgotPassword?.addEventListener('click', authHandlers.forgotPassword)
    
    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(button => {
      button.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'))
        document.querySelectorAll('.auth-form').forEach(form => form.classList.remove('active'))
        ui.clearMessages()
        button.classList.add('active')
        const target = document.getElementById(button.dataset.target)
        target && target.classList.add('active')
      })
    })
  }

  // Initialize
  initializeAuth()
})
