/**
 * Script for login.html
 * Initializes Firebase, handles login/registration,
 * sends token to backend for cookie session, handles OAuth.
 */
document.addEventListener('DOMContentLoaded', () => {
    // Check if canvas exists for the animation background
    const canvas = document.getElementById('quantum-field');
    if (!canvas) {
      console.warn("Canvas element #quantum-field not found");
    }
  
    // Global Firebase references (initialized in initializeLoginAuth)
    let firebaseApp = null;
    let firebaseAuth = null;
  
    // --- DOM Elements ---
    const elements = {
      // Forms
      loginForm: document.getElementById('login-form'),
      registerForm: document.getElementById('register-form'),
      
      // Login form elements
      loginEmailInput: document.getElementById('login-email'),
      loginPasswordInput: document.getElementById('login-password'),
      loginButton: document.getElementById('login-button'),
      loginMessageArea: document.getElementById('login-message-area'),
      
      // Registration form elements
      regNameInput: document.getElementById('reg-name'),
      regEmailInput: document.getElementById('reg-email'),
      regPasswordInput: document.getElementById('reg-password'),
      regConfirmPasswordInput: document.getElementById('reg-confirm-password'),
      regTermsCheckbox: document.getElementById('reg-terms'),
      registerButton: document.getElementById('register-button'),
      registerMessageArea: document.getElementById('register-message-area'),
      
      // Other UI elements
      forgotPasswordLink: document.querySelector('.forgot-password'),
      strengthBar: document.querySelector('#register-form .strength-bar'),
      
      // Social buttons (collected when needed)
      getSocialButtons: (provider) => document.querySelectorAll(`.social-btn.${provider}`)
    };
  
    // --- Cookie and CSRF handling ---
    const cookieUtils = {
      // Get cookie value by name
      getCookie: (name) => {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
      },
      
      // Extract CSRF token from HTML form fields or meta tags
      extractCSRFFromHTML: () => {
        const csrfField = document.querySelector('input[name="csrf_token"], input[name="csrftoken"], input[name="csrf"], input[name="_csrf"], input[name="_csrf_token"]');
        if (csrfField) {
          return csrfField.value;
        }
        
        const csrfMeta = document.querySelector('meta[name="csrf-token"], meta[name="csrf"]');
        if (csrfMeta) {
          return csrfMeta.getAttribute('content');
        }
        
        return null;
      },
      
      // Fetch CSRF token using various methods
      fetchCSRFToken: async () => {
        try {
          // Check if CSRF token is already available in HTML
          const htmlToken = cookieUtils.extractCSRFFromHTML();
          if (htmlToken) {
            return htmlToken;
          }
          
          // Check cookies
          let csrfToken = cookieUtils.getCookie("csrftoken");
          if (csrfToken) {
            return csrfToken;
          }
          
          // Perform GET request to login page to fetch CSRF token
          const response = await fetch('/login', {
            method: 'GET',
            credentials: 'same-origin'
          });
          
          if (response.ok) {
            // After GET request, CSRF cookie should be set
            csrfToken = cookieUtils.getCookie("csrftoken");
            
            if (csrfToken) {
              return csrfToken;
            } else {
              // Check alternative cookie names
              const alternativeNames = ["XSRF-TOKEN", "CSRF-TOKEN", "_csrf", "csrf", "CSRF"];
              for (const name of alternativeNames) {
                const token = cookieUtils.getCookie(name);
                if (token) {
                  return token;
                }
              }
              return null;
            }
          } else {
            return null;
          }
        } catch (error) {
          return null;
        }
      }
    };
  
    // --- UI Helper Functions ---
    const uiHelpers = {
      // Get active message area ID based on which form is active
      getActiveMessageAreaId: () => {
        const activeForm = document.querySelector('.auth-form.active');
        return activeForm ? activeForm.id.replace('-form', '-message-area') : 'login-message-area';
      },
      
      // Set button loading state
      setButtonLoading: (button, isLoading, loadingText = '', originalText = null) => {
        if (!button) return;
        
        // Store original HTML if not already saved
        if (!button.dataset.originalHTML) {
          button.dataset.originalHTML = button.innerHTML;
        }
        const originalHTML = originalText || button.dataset.originalHTML;
        
        if (isLoading) {
          button.disabled = true;
          button.classList.add('loading');
          // We use ::after for spinner, don't change innerHTML unless text is provided
        } else {
          button.disabled = false;
          button.classList.remove('loading');
          button.innerHTML = originalHTML; // Restore original HTML
        }
      },
      
      // Show message (success, error, etc.)
      showMessage: (message, type, areaId = null) => {
        const targetAreaId = areaId || uiHelpers.getActiveMessageAreaId();
        const messageElement = document.getElementById(targetAreaId);
        if (!messageElement) return;
        
        // Use textContent for safety (avoid HTML injection)
        messageElement.textContent = message;
        messageElement.className = `auth-message ${type}`;
        messageElement.style.display = 'block';
        
        // Hide error message after a while
        if (type === 'error') {
          setTimeout(() => {
            // Check if message still exists and is visible
            if (messageElement.style.display === 'block' && messageElement.textContent === message) {
              messageElement.style.display = 'none';
              messageElement.textContent = '';
            }
          }, 7000); // Hide after 7 seconds
        }
      },
      
      // Helper functions for specific message types
      showError: (message, areaId = null) => uiHelpers.showMessage(message, 'error', areaId),
      showSuccess: (message, areaId = null) => uiHelpers.showMessage(message, 'success', areaId),
      
      // Clear messages
      clearMessages: (areaId = null) => {
        const targetAreaId = areaId || uiHelpers.getActiveMessageAreaId();
        const messageElement = document.getElementById(targetAreaId);
        if (messageElement) {
          messageElement.innerHTML = '';
          messageElement.style.display = 'none';
          messageElement.className = 'auth-message'; // Reset classes
        }
        
        // Also clear other area if areaId not provided
        if (!areaId) {
          const otherAreaId = (targetAreaId === 'login-message-area') ? 'register-message-area' : 'login-message-area';
          const otherMessageElement = document.getElementById(otherAreaId);
          if (otherMessageElement) {
            otherMessageElement.innerHTML = '';
            otherMessageElement.style.display = 'none';
            otherMessageElement.className = 'auth-message';
          }
        }
      }
    };
  
    // --- Password Strength Utilities ---
    const passwordUtils = {
      // Check if password meets strength requirements
      isStrongPassword: (password) => {
        // Min. 8 chars, uppercase, lowercase, digit, special char
        const strongPasswordRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&^#()_+=\-[\]{}|\\:;"'<>,.?/~`])[A-Za-z\d@$!%*?&^#()_+=\-[\]{}|\\:;"'<>,.?/~`]{8,}$/;
        return strongPasswordRegex.test(password);
      },
      
      // Update password strength indicator
      updatePasswordStrength: (event) => {
        const password = event.target.value;
        const strengthBar = elements.strengthBar;
        if (!strengthBar) return;
        
        if (!password) {
          strengthBar.style.width = '0%';
          strengthBar.style.backgroundColor = '#ddd'; // Default bar color
          return;
        }
        
        let strength = 0;
        if (password.length >= 8) strength++;
        if (/[A-Z]/.test(password)) strength++;
        if (/[a-z]/.test(password)) strength++;
        if (/\d/.test(password)) strength++;
        if (/[^A-Za-z0-9]/.test(password)) strength++; // Checks for special character
        
        // Simple point system (max 5 points) -> percentage
        const percentage = Math.min((strength / 5) * 100, 100);
        strengthBar.style.width = `${percentage}%`;
        
        // Bar coloring
        if (strength <= 1) strengthBar.style.backgroundColor = '#FF4B4B';      // Very weak
        else if (strength <= 2) strengthBar.style.backgroundColor = '#FFA500'; // Weak
        else if (strength <= 3) strengthBar.style.backgroundColor = '#FFD700'; // Medium
        else if (strength <= 4) strengthBar.style.backgroundColor = '#90EE90'; // Good
        else strengthBar.style.backgroundColor = '#4CAF50';                   // Very good
      }
    };
  
    // --- Firebase Auth Handler ---
    const authHandler = {
      // Create backend session after Firebase authentication
      createBackendSession: async (user) => {
        if (!user) {
          uiHelpers.showError("Authentication error (missing user data).", uiHelpers.getActiveMessageAreaId());
          return;
        }
        
        const activeFormButton = document.querySelector('.auth-form.active button[type="submit"]');
        const originalButtonText = activeFormButton ? activeFormButton.dataset.originalHTML : null;
        
        // Block active form button
        if (activeFormButton) uiHelpers.setButtonLoading(activeFormButton, true, '', originalButtonText);
        
        // Block social buttons
        document.querySelectorAll('.social-btn').forEach(btn => uiHelpers.setButtonLoading(btn, true));
        
        uiHelpers.clearMessages(); // Hide previous messages
        
        try {
          // Get CSRF token
          const csrfToken = await cookieUtils.fetchCSRFToken();
          
          // Get fresh token before sending to backend
          const idToken = await user.getIdToken(true);
          
          // Prepare headers with various CSRF token variants
          const headers = { 'Content-Type': 'application/json' };
          
          // Add CSRF token in various header formats, if it exists
          if (csrfToken) {
            // Standard and popular CSRF header name variants
            headers['X-CSRF-Token'] = csrfToken;
            headers['X-CSRFToken'] = csrfToken;
            headers['CSRF-Token'] = csrfToken;
            headers['CSRFToken'] = csrfToken;
          }
          
          const response = await fetch('/auth/firebase-session-login', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ token: idToken }),
            credentials: 'same-origin' // Important: include cookies in request
          });
          
          if (response.ok) {
            // Save information that login succeeded, to display message after reload (optional)
            sessionStorage.setItem('authActionCompleted', 'true');
            // Redirect to application main page
            window.location.href = '/index';
          } else {
            // Backend error
            const errorData = await response.json().catch(() => ({ detail: `Server error ${response.status}` }));
            const errorMessage = `Login error (${response.status}): ${errorData.detail || 'Cannot create session.'}`;
            uiHelpers.showError(errorMessage, uiHelpers.getActiveMessageAreaId());
            
            // Sign out from Firebase if backend rejected session
            if (firebaseAuth) {
              await firebaseAuth.signOut();
            }
            
            // Unblock buttons after error
            if (activeFormButton) uiHelpers.setButtonLoading(activeFormButton, false, '', originalButtonText);
            document.querySelectorAll('.social-btn').forEach(btn => uiHelpers.setButtonLoading(btn, false));
          }
        } catch (error) {
          uiHelpers.showError(`An error occurred: ${error.message || 'Check your internet connection.'}`, uiHelpers.getActiveMessageAreaId());
          
          // Unblock buttons after error
          if (activeFormButton) uiHelpers.setButtonLoading(activeFormButton, false, '', originalButtonText);
          document.querySelectorAll('.social-btn').forEach(btn => uiHelpers.setButtonLoading(btn, false));
        }
      },
      
      // Email/Password Login Logic
      handleLogin: async (event) => {
        event.preventDefault();
        const { loginEmailInput, loginPasswordInput, loginButton } = elements;
        const email = loginEmailInput ? loginEmailInput.value.trim() : null;
        const password = loginPasswordInput ? loginPasswordInput.value : null;
        const messageAreaId = 'login-message-area';
        
        uiHelpers.clearMessages(messageAreaId);
        
        if (!email || !password) {
          uiHelpers.showError('Please enter email and password.', messageAreaId);
          return;
        }
        
        if (!firebaseAuth) {
          uiHelpers.showError('Login system is not ready.', messageAreaId);
          return;
        }
        
        uiHelpers.setButtonLoading(loginButton, true);
        
        try {
          // Call Firebase login - the rest will be handled by onAuthStateChanged -> createBackendSession
          await firebaseAuth.signInWithEmailAndPassword(email, password);
          // Do nothing more, onAuthStateChanged will take over
        } catch (error) {
          let msg = 'An error occurred during login.';
          switch (error.code) {
            case 'auth/invalid-email': msg = 'Invalid email format.'; break;
            case 'auth/user-disabled': msg = 'This account has been disabled.'; break;
            case 'auth/user-not-found':
            case 'auth/wrong-password':
            case 'auth/invalid-credential': // Newer error code for bad credentials
              msg = 'Invalid email or password.'; break;
            case 'auth/network-request-failed': msg = 'Network error. Check your connection.'; break;
            default: msg = `Login error (${error.code || 'unknown'})`;
          }
          uiHelpers.showError(msg, messageAreaId);
          uiHelpers.setButtonLoading(loginButton, false); // Unblock button after error
        }
        // Don't unblock button on success, onAuthStateChanged will handle it
      },
      
      // Registration Logic
      handleRegister: async (event) => {
        event.preventDefault();
        const { regNameInput, regEmailInput, regPasswordInput, regConfirmPasswordInput, regTermsCheckbox, registerButton } = elements;
        
        const name = regNameInput ? regNameInput.value.trim() : null;
        const email = regEmailInput ? regEmailInput.value.trim() : null;
        const password = regPasswordInput ? regPasswordInput.value : null;
        const confirmPassword = regConfirmPasswordInput ? regConfirmPasswordInput.value : null;
        const termsAccepted = regTermsCheckbox ? regTermsCheckbox.checked : false;
        const messageAreaId = 'register-message-area';
        
        uiHelpers.clearMessages(messageAreaId);
        
        if (!name || !email || !password || !confirmPassword) {
          uiHelpers.showError('Please fill in all fields.', messageAreaId);
          return;
        }
        
        if (password !== confirmPassword) {
          uiHelpers.showError('Passwords do not match.', messageAreaId);
          return;
        }
        
        if (!passwordUtils.isStrongPassword(password)) {
          uiHelpers.showError('Password does not meet security requirements.', messageAreaId);
          return;
        }
        
        if (!termsAccepted) {
          uiHelpers.showError('You must accept the Terms of Service and Privacy Policy.', messageAreaId);
          return;
        }
        
        if (!firebaseAuth) {
          uiHelpers.showError('Registration system is not ready.', messageAreaId);
          return;
        }
        
        uiHelpers.setButtonLoading(registerButton, true);
        
        try {
          const userCredential = await firebaseAuth.createUserWithEmailAndPassword(email, password);
          const user = userCredential.user;
          
          // Set displayName
          await user.updateProfile({ displayName: name });
          
          // Success - the rest will be handled by onAuthStateChanged -> createBackendSession
        } catch (error) {
          let msg = 'An error occurred during registration.';
          switch (error.code) {
            case 'auth/email-already-in-use': msg = 'This email address is already registered.'; break;
            case 'auth/invalid-email': msg = 'Invalid email format.'; break;
            case 'auth/operation-not-allowed': msg = 'Registration is currently disabled.'; break;
            case 'auth/weak-password': msg = 'Password is too weak.'; break;
            default: msg = `Registration error (${error.code || 'unknown'})`;
          }
          uiHelpers.showError(msg, messageAreaId);
          uiHelpers.setButtonLoading(registerButton, false); // Unblock after error
        }
        // Don't unblock button on success
      },
      
      // OAuth Sign-in Logic (Google, Microsoft)
      handleOAuthSignIn: async (providerName) => {
        let provider;
        const buttonSelector = `.auth-form.active .social-btn.${providerName}`;
        const button = document.querySelector(buttonSelector);
        
        if (!button) return;
        
        if (!firebaseAuth) {
          uiHelpers.showError('Login system is not ready.', uiHelpers.getActiveMessageAreaId());
          return;
        }
        
        switch(providerName) {
          case 'google':
            provider = new firebase.auth.GoogleAuthProvider();
            break;
          case 'microsoft':
            provider = new firebase.auth.OAuthProvider('microsoft.com');
            break;
          default:
            uiHelpers.showError(`Provider "${providerName}" is not supported.`, uiHelpers.getActiveMessageAreaId());
            return;
        }
        
        uiHelpers.clearMessages();
        uiHelpers.setButtonLoading(button, true);
        
        try {
          // Call Firebase popup login - onAuthStateChanged will handle the rest
          await firebaseAuth.signInWithPopup(provider);
        } catch (error) {
          let msg = `An error occurred while signing in with ${providerName}.`;
          switch(error.code) {
            case 'auth/account-exists-with-different-credential': 
              msg = 'An account with this email already exists and is linked to a different sign-in method.'; 
              break;
            case 'auth/popup-closed-by-user': 
              msg = `${providerName} sign-in was cancelled.`; 
              break;
            case 'auth/popup-blocked': 
              msg = `${providerName} sign-in popup was blocked. Please unblock it and try again.`; 
              break;
            case 'auth/cancelled-popup-request': 
              msg = 'Cancelled additional popup request.'; 
              break;
            case 'auth/operation-not-allowed': 
              msg = `${providerName} sign-in is not enabled in Firebase.`; 
              break;
            case 'auth/unauthorized-domain': 
              msg = `This domain is not authorized for Firebase operations.`; 
              break;
            default: 
              msg = `${providerName} sign-in error (${error.code || 'unknown'})`;
          }
          uiHelpers.showError(msg, uiHelpers.getActiveMessageAreaId());
          uiHelpers.setButtonLoading(button, false); // Unblock after error
        }
        // Don't unblock button on success
      },
      
      // "Forgot password?" Logic
      handleForgotPassword: (event) => {
        event.preventDefault();
        const { loginEmailInput } = elements;
        const email = loginEmailInput ? loginEmailInput.value.trim() : null;
        const messageAreaId = 'login-message-area';
        
        uiHelpers.clearMessages(messageAreaId);
        
        if (!email) {
          uiHelpers.showError('Enter your email address in the field above to reset your password.', messageAreaId);
          return;
        }
        
        if (!firebaseAuth) {
          uiHelpers.showError('Password reset system is not ready.', messageAreaId);
          return;
        }
        
        // Show temporary loading message
        uiHelpers.showSuccess('Sending password reset instructions...', messageAreaId);
        
        firebaseAuth.sendPasswordResetEmail(email)
          .then(() => {
            uiHelpers.showSuccess('Password reset link has been sent to your email address. Check your inbox (and spam folder).', messageAreaId);
          })
          .catch((error) => {
            let msg = 'Failed to send password reset link.';
            if (error.code === 'auth/invalid-email') {
              msg += ' Check email format.';
            } else if (error.code === 'auth/user-not-found') {
              msg = 'No account found with this email address.';
            } else {
              msg += ` (Error: ${error.code || 'unknown'})`;
            }
            uiHelpers.showError(msg, messageAreaId);
          });
      }
    };
  
    // --- Firebase Initialization ---
    const initializeLoginAuth = async () => {
      try {
        const response = await fetch('/auth/firebase-config');
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ detail: response.statusText }));
          throw new Error(errorData.detail || `Error ${response.status} fetching Firebase configuration`);
        }
        
        const config = await response.json();
        
        if (!config.apiKey || !config.authDomain) {
          throw new Error('Incomplete Firebase configuration data from backend.');
        }
        
        if (firebase.apps.length === 0) {
          firebaseApp = firebase.initializeApp({ apiKey: config.apiKey, authDomain: config.authDomain });
        } else {
          firebaseApp = firebase.app();
        }
        
        firebaseAuth = firebase.auth();
        
        // --- Key Authentication State Handling ---
        firebaseAuth.onAuthStateChanged(async (user) => {
          if (user) {
            // User is signed in to Firebase (fresh or from memory)
            // Check if we're already creating session or redirecting
            if (sessionStorage.getItem('creatingSession') === 'true') {
              return;
            }
            
            // Set flag that we're starting backend session creation
            sessionStorage.setItem('creatingSession', 'true');
            
            // Call backend session creation function
            await authHandler.createBackendSession(user);
            
            // Remove flag after completion (even if there was an error and no redirect)
            sessionStorage.removeItem('creatingSession');
          } else {
            // User is not signed in to Firebase
            // Make sure buttons are unblocked if no user
            const activeFormButton = document.querySelector('.auth-form.active button[type="submit"]');
            if (activeFormButton && activeFormButton.classList.contains('loading')) {
              uiHelpers.setButtonLoading(activeFormButton, false);
            }
            
            document.querySelectorAll('.social-btn.loading').forEach(btn => 
              uiHelpers.setButtonLoading(btn, false)
            );
            
            // Clear session flags
            sessionStorage.removeItem('creatingSession');
            sessionStorage.removeItem('authActionCompleted');
          }
        });
        
        // After successful Firebase initialization, set up forms
        setupAuthForms();
      } catch (error) {
        const errorMessage = `Authentication system error: ${error.message}`;
        uiHelpers.showError(errorMessage, 'login-message-area');
        uiHelpers.showError(errorMessage, 'register-message-area');
        
        // Disable all buttons
        if (elements.loginButton) elements.loginButton.disabled = true;
        if (elements.registerButton) elements.registerButton.disabled = true;
        document.querySelectorAll('.social-btn').forEach(btn => btn.disabled = true);
      }
    };
  
    // --- Setup Auth Forms and Event Listeners ---
    const setupAuthForms = () => {
      const { loginForm, registerForm, regPasswordInput, forgotPasswordLink } = elements;
      
      if (loginForm) {
        loginForm.addEventListener('submit', authHandler.handleLogin);
      }
      
      if (registerForm) {
        registerForm.addEventListener('submit', authHandler.handleRegister);
      }
      
      if (regPasswordInput) {
        regPasswordInput.addEventListener('input', passwordUtils.updatePasswordStrength);
      }
      
      // Google Sign-in
      document.querySelectorAll('.social-btn.google').forEach(button => {
        button.addEventListener('click', () => authHandler.handleOAuthSignIn('google'));
      });
      
      // Microsoft Sign-in
      document.querySelectorAll('.social-btn.microsoft').forEach(button => {
        button.addEventListener('click', () => authHandler.handleOAuthSignIn('microsoft'));
      });
      
      // LinkedIn Sign-in (placeholder)
      document.querySelectorAll('.social-btn.linkedin').forEach(button => {
        button.addEventListener('click', () => {
          uiHelpers.showError('LinkedIn sign-in is not yet implemented.', uiHelpers.getActiveMessageAreaId());
        });
      });
      
      // "Forgot password?" link
      if (forgotPasswordLink) {
        forgotPasswordLink.addEventListener('click', authHandler.handleForgotPassword);
      }
      
      // --- Tab switching logic ---
      const tabButtons = document.querySelectorAll('.tab-btn');
      const authForms = document.querySelectorAll('.auth-form');
      
      tabButtons.forEach(button => {
        button.addEventListener('click', () => {
          // Deselect all buttons and hide forms
          tabButtons.forEach(btn => btn.classList.remove('active'));
          authForms.forEach(form => form.classList.remove('active'));
          
          // Clear messages when switching tabs
          uiHelpers.clearMessages();
          
          // Mark clicked button and show corresponding form
          button.classList.add('active');
          const targetFormId = button.dataset.target;
          const targetForm = document.getElementById(targetFormId);
          
          if (targetForm) {
            targetForm.classList.add('active');
          }
        });
      });
    };
  
    // Initialize Firebase auth
    initializeLoginAuth();
  }); // End of DOMContentLoaded
  