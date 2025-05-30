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
    strengthBar: document.querySelector('#register-form .strength-bar'),
    emailVerificationModal: document.getElementById('email-verification-modal'),
    resendVerificationBtn: document.getElementById('resend-verification-btn'),
    passwordResetModal: document.getElementById('password-reset-modal'),
    resetEmailInput: document.getElementById('reset-email'),
    resetPasswordBtn: document.getElementById('reset-password-btn'),
    closeModalBtns: document.querySelectorAll('.close-modal')
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
    },
    
    showModal: (modalId) => {
      const modal = document.getElementById(modalId)
      if (modal) {
        modal.style.display = 'flex'
        document.body.style.overflow = 'hidden'
      }
    },
    
    hideModal: (modalId) => {
      const modal = document.getElementById(modalId)
      if (modal) {
        modal.style.display = 'none'
        document.body.style.overflow = 'auto'
      }
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

  // Email verification functions
  const sendVerificationEmail = async (user) => {
    try {
      await user.sendEmailVerification({
        url: 'https://vortexanalytica.com/login',
        handleCodeInApp: false
      })
      ui.showModal('email-verification-modal')
      return true
    } catch (error) {
      console.error('Error sending verification email:', error)
      const errors = {
        'auth/too-many-requests': 'Too many requests. Please try again later',
        'auth/invalid-email': 'Invalid email address.',
        'auth/user-not-found': 'User not found.'
      }
      ui.showError(errors[error.code] || 'Failed to send verification email', 'register-message-area')
      return false
    }
  }

  const checkEmailVerification = async (user) => {
    try {
      await user.reload()
      return user.emailVerified
    } catch (error) {
      console.error('Error checking email verification:', error)
      return false
    }
  }

  // Create backend session after Firebase auth
  const createBackendSession = async user => {
    if (!user) {
      ui.showError('Authentication error', ui.getActiveMessageArea())
      return
    }
    
    // Check if email is verified
    if (!user.emailVerified) {
      ui.showError('Please verify your email before logging in. Check your inbox', 'login-message-area')
      ui.setLoading(elements.loginButton, false)
      await firebaseAuth.signOut()
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
        const result = await firebaseAuth.signInWithEmailAndPassword(email, password)
        
        // Check if email is verified
        if (!result.user.emailVerified) {
          ui.showError('Please verify your email before logging in. Check your inbox', 'login-message-area')
          
          // Offer to resend verification email
          const resendBtn = document.createElement('button')
          resendBtn.textContent = 'Resend verification email'
          resendBtn.className = 'auth-button secondary'
          resendBtn.style.marginTop = '10px'
          resendBtn.onclick = async () => {
            await sendVerificationEmail(result.user)
          }
          
          const messageArea = document.getElementById('login-message-area')
          messageArea.appendChild(resendBtn)
          
          await firebaseAuth.signOut()
          ui.setLoading(elements.loginButton, false)
          return
        }
        
        await createBackendSession(result.user)
        
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
        
        // Send verification email
        await sendVerificationEmail(user)
        
        // Sign out the user until they verify their email
        await firebaseAuth.signOut()
        
        ui.setLoading(elements.registerButton, false)
        
        // Switch to login tab
        document.querySelector('.tab-btn[data-target="login-form"]').click()
        
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
        const result = await firebaseAuth.signInWithPopup(providers[provider]())
        
        // OAuth providers usually verify email automatically
        if (!result.user.emailVerified) {
          await sendVerificationEmail(result.user)
          await firebaseAuth.signOut()
          ui.setLoading(button, false)
          return
        }
        
        await createBackendSession(result.user)
        
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
      ui.showModal('password-reset-modal')
      
      // Pre-fill email if available
      const email = elements.loginEmail?.value.trim()
      if (email && elements.resetEmailInput) {
        elements.resetEmailInput.value = email
      }
    },
    
    resetPassword: async event => {
      event.preventDefault()
      
      const email = elements.resetEmailInput?.value.trim()
      const resetMessage = document.getElementById('reset-message-area')
      
      if (!email) {
        ui.showError('Please enter your email address', 'reset-message-area')
        return
      }
      
      if (!firebaseAuth) {
        ui.showError('Password reset system is not ready', 'reset-message-area')
        return
      }
      
      ui.setLoading(elements.resetPasswordBtn, true)
      resetMessage.style.display = 'none'
      
      try {
        await firebaseAuth.sendPasswordResetEmail(email, {
          url: window.location.origin + '/login',
          handleCodeInApp: false
        })
        
        ui.showSuccess('Password reset link sent! Check your email.', 'reset-message-area')
        
        // Auto-close modal after 3 seconds
        setTimeout(() => {
          ui.hideModal('password-reset-modal')
          elements.resetEmailInput.value = ''
          resetMessage.style.display = 'none'
        }, 3000)
        
      } catch (error) {
        const errors = {
          'auth/invalid-email': 'Invalid email format',
          'auth/user-not-found': 'No account found with this email',
          'auth/too-many-requests': 'Too many requests. Please try again later.'
        }
        ui.showError(errors[error.code] || `Failed to send reset link (${error.code || 'unknown'})`, 'reset-message-area')
      } finally {
        ui.setLoading(elements.resetPasswordBtn, false)
      }
    },
    
    resendVerification: async () => {
      const currentUser = firebaseAuth?.currentUser
      
      if (!currentUser) {
        ui.showError('Please log in first', 'login-message-area')
        ui.hideModal('email-verification-modal')
        return
      }
      
      ui.setLoading(elements.resendVerificationBtn, true)
      
      const success = await sendVerificationEmail(currentUser)
      
      if (success) {
        ui.showSuccess('Verification email sent! Check your inbox.', 'verification-message-area')
      }
      
      ui.setLoading(elements.resendVerificationBtn, false)
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
        if (user && user.emailVerified) {
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
    
    // Reset password button
    elements.resetPasswordBtn?.addEventListener('click', authHandlers.resetPassword)
    
    // Resend verification button
    elements.resendVerificationBtn?.addEventListener('click', authHandlers.resendVerification)
    
    // Close modal buttons
    elements.closeModalBtns?.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const modal = e.target.closest('.modal')
        if (modal) {
          ui.hideModal(modal.id)
        }
      })
    })
    
    // Close modal on outside click
    document.querySelectorAll('.modal').forEach(modal => {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          ui.hideModal(modal.id)
        }
      })
    })
    
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