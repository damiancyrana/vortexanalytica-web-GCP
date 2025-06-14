/**
 * Critical news alerts via SSE - Mobile/Tablet Optimized with Liquid Glass Effect
 */
(() => {
  let sseConnection = null
  const criticalMessages = []
  const messageTimers = {}
  const MESSAGE_LIFETIME = 3600000 // 1 hour
  
  // Mobile detection
  const isMobile = () => window.innerWidth <= 768
  const isTablet = () => window.innerWidth > 768 && window.innerWidth <= 1023
  
  // Inject responsive styles with liquid glass effect
  const injectStyles = () => {
    const style = document.createElement('style')
    style.textContent = `
      .critical-news-wrapper {
        display: none;
        width: 100%;
        margin-bottom: 1rem;
        padding: 0 0.5rem;
        box-sizing: border-box;
        font-size: 0.80rem;
        font-family: 'Roboto', 'Open Sans', 'Helvetica Neue', Arial, sans-serif;
      }
      
      .critical-news-wrapper.visible {
        display: block;
      }
      
      .critical-news-container {
        display: grid;
        grid-template-columns: 1fr;
        gap: 20px;
        width: 100%;
      }
      
      .critical-news-alert {
        backdrop-filter: blur(20px) saturate(180%);
        -webkit-backdrop-filter: blur(20px) saturate(180%);
        border-radius: 16px;
        padding: 0.3rem 0.5rem 0.4rem 0.6rem;
        border: 1px solid rgba(255, 255, 255, 0.1);
        position: relative;
        animation: slideIn 0.3s ease-out;
        min-height: 50px;
        overflow: hidden;
        font-size: 1em;
      }
      
      /* Liquid glass base effect */
      .critical-news-alert::before {
        content: '';
        position: absolute;
        inset: 0;
        background: linear-gradient(
          135deg,
          rgba(255, 255, 255, 0.1) 0%,
          rgba(255, 255, 255, 0.05) 40%,
          rgba(255, 255, 255, 0.02) 100%
        );
        pointer-events: none;
        z-index: 1;
      }
      
      /* Ensure content is above the glass effect */
      .critical-news-alert > * {
        position: relative;
        z-index: 2;
      }
      
      /* Light theme styles */
      body:not(.dark-theme) .critical-news-alert {
        background: rgba(255, 255, 255, 0.95);
        border: 1px solid rgba(0, 0, 0, 0.08);
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
      }
      
      body:not(.dark-theme) .critical-news-alert[data-signal="BUY"] {
        background: rgba(34, 139, 34, 0.1);
        border-color: rgba(34, 139, 34, 0.3);
        border-left: 3px solid #228b22;
      }

      body:not(.dark-theme) .critical-news-alert[data-signal="SELL"] {
        background: rgba(220, 20, 60, 0.1);
        border-color: rgba(220, 20, 60, 0.3);
        border-left: 3px solid #dc143c;
      }

      body:not(.dark-theme) .critical-news-alert[data-signal="HOLD"] {
        background: rgba(238, 181, 8, 0.1);
        border-color: rgba(238, 181, 8, 0.3);
        border-left: 3px solid #eeb508;
      }
      
      /* Dark theme styles */
      body.dark-theme .critical-news-alert {
        background: rgba(24, 28, 36, 0.6);
        box-shadow: 
          0 8px 32px rgba(0, 0, 0, 0.3),
          inset 0 0 0 1px rgba(255, 255, 255, 0.1),
          0 2px 4px rgba(0, 0, 0, 0.5);
      }
      
      body.dark-theme .critical-news-alert[data-signal="BUY"] {
        background: rgba(34, 139, 34, 0.25);
        border-color: rgba(50, 205, 50, 0.4);
        border-left: 3px solid #32cd32;
      }

      body.dark-theme .critical-news-alert[data-signal="SELL"] {
        background: rgba(220, 20, 60, 0.25);
        border-color: rgba(255, 69, 0, 0.4);
        border-left: 3px solid #ff4500;
      }

      body.dark-theme .critical-news-alert[data-signal="HOLD"] {
        background: rgba(238, 181, 8, 0.3);
        border-color: rgba(255, 215, 0, 0.4);
        border-left: 3px solid #ffd700;
      }
      
      /* Dark theme liquid glass effect adjustment */
      body.dark-theme .critical-news-alert::before {
        background: linear-gradient(
          135deg,
          rgba(255, 255, 255, 0.05) 0%,
          rgba(255, 255, 255, 0.02) 40%,
          rgba(255, 255, 255, 0.01) 100%
        );
      }
      
      .critical-news-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 5px;
        padding-right: 45px; /* Increased to prevent overlap with close button */
      }
      
      .critical-news-symbol {
        background: rgba(255, 255, 255, 0.15);
        padding: .20rem .35rem;
        border-radius: 10px;
        font-size: .8em;
        font-weight: 400;
      }
      
      body:not(.dark-theme) .critical-news-symbol {
        background: rgba(0, 0, 0, 0.08);
      }
      
      /* Light theme text colors */
      body:not(.dark-theme) .critical-news-time,
      body:not(.dark-theme) .critical-news-title,
      body:not(.dark-theme) .critical-news-symbol,
      body:not(.dark-theme) .critical-news-confidence {
        color: #1a1f2a;
      }
      
      /* Dark theme text colors */
      body.dark-theme .critical-news-time,
      body.dark-theme .critical-news-title,
      body.dark-theme .critical-news-symbol,
      body.dark-theme .critical-news-confidence {
        color: #fff;
      }
      
      .critical-news-time {
        font-size: 0.9em;
        font-weight: 500;
        opacity: 0.8;
        white-space: nowrap;
      }
      
      .critical-news-title {
        font-size: 1.1em;
        font-weight: 600;
        letter-spacing: .04em;
        margin-bottom: 5px;
        line-height: 1.3;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
        word-wrap: break-word;
        overflow-wrap: break-word;
        padding-right: 35px; /* Added to prevent overlap with close button */
      }
      
      .critical-news-meta {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 5px;
        flex-wrap: wrap;
      }
      
      .critical-news-confidence {
        font-size: .8em;
        opacity: 0.8;
      }
      
      .critical-news-close {
        position: absolute;
        top: 8px;
        right: 8px;
        background: rgba(255, 255, 255, 0.1);
        border: none;
        cursor: pointer;
        font-size: 0.8rem;
        padding: 4px 8px;
        border-radius: 4px;
        transition: all 0.2s;
        z-index: 20; /* Increased from 10 to ensure it's above all content */
        -webkit-tap-highlight-color: transparent;
        min-width: 30px;
        min-height: 30px;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      
      body:not(.dark-theme) .critical-news-close {
        background: rgba(0, 0, 0, 0.05);
        color: rgba(0, 0, 0, 0.6);
      }
      
      body.dark-theme .critical-news-close {
        color: rgba(255, 255, 255, 0.8);
      }
      
      .critical-news-close:hover,
      .critical-news-close:active {
        background: rgba(255, 255, 255, 0.2);
      }
      
      body:not(.dark-theme) .critical-news-close:hover,
      body:not(.dark-theme) .critical-news-close:active {
        color: #000;
        background: rgba(0, 0, 0, 0.1);
      }
      
      body.dark-theme .critical-news-close:hover,
      body.dark-theme .critical-news-close:active {
        color: #fff;
      }
      
      @keyframes slideIn {
        from {
          opacity: 0;
          transform: translateY(-10px);
        }
        to {
          opacity: 1;
          transform: translateY(0);
        }
      }
      
      /* Tablet Styles */
      @media (min-width: 768px) and (max-width: 1023px) {
        .critical-news-wrapper {
          padding: 0 1rem;
          margin-bottom: 1.5rem;
          font-size: 0.6rem;
        }
        
        .critical-news-container {
          gap: 20px;
        }
        
        .critical-news-alert {
          padding: 0.3rem 0.5rem 0.4rem 0.6rem;
          min-height: 70px;
        }
        
        .critical-news-title {
          font-size: 1.1em;
        }
        
        .critical-news-time {
          font-size: 0.9em;
        }
        
        .critical-news-meta {
          gap: 12px;
        }
        
        .critical-news-symbol {
          font-size: .8em;
          padding: .20rem .35rem;
        }
        
        .critical-news-confidence {
          font-size: .8em;
        }
      }
      
      /* Desktop Styles */
      @media (min-width: 1024px) {
        .critical-news-wrapper {
          padding: 0;
          margin-bottom: 2rem;
          font-size: 0.80rem;
        }
        
        .critical-news-container {
          grid-template-columns: 1fr 1fr;
          gap: 20px;
        }
        
        .critical-news-alert {
          padding: 0.3rem 0.5rem 0.4rem 0.6rem;
          min-height: 80px;
        }
        
        .critical-news-title {
          font-size: 1.1em;
          -webkit-line-clamp: 3;
        }
        
        .critical-news-time {
          font-size: 0.9em;
        }
        
        .critical-news-meta {
          gap: 15px;
        }
        
        .critical-news-symbol {
          font-size: .8em;
          padding: .20rem .35rem;
        }
        
        .critical-news-confidence {
          font-size: .8em;
        }
        
        .critical-news-close {
          font-size: 0.9rem;
          padding: 6px 10px;
        }
      }
      
      /* Small Mobile */
      @media (max-width: 380px) {
        .critical-news-wrapper {
          padding: 0 0.25rem;
          font-size: 0.5rem;
        }
        
        .critical-news-alert {
          padding: 0.3rem 0.5rem 0.4rem 0.6rem;
          min-height: 50px;
        }
        
        .critical-news-title {
          font-size: 1.1em;
        }
        
        .critical-news-time {
          font-size: 0.9em;
        }
        
        .critical-news-symbol {
          font-size: .8em;
          padding: .20rem .35rem;
        }
        
        .critical-news-confidence {
          font-size: .8em;
        }
        
        .critical-news-close {
          font-size: 0.75rem;
          padding: 3px 6px;
          top: 6px;
          right: 6px;
        }
      }
      
      /* Match news.css responsive breakpoints */
      @media (max-width: 980px) {
        .critical-news-wrapper {
          font-size: 0.6rem;
        }
      }
      
      @media (max-width: 560px) {
        .critical-news-wrapper {
          font-size: 0.5rem;
        }
      }
      @media (max-width: 900px) and (max-height: 600px) and (orientation: landscape) {
        .critical-news-wrapper {
          margin-bottom: 0.5rem;
          font-size: 0.5rem;
        }
        
        .critical-news-container {
          gap: 20px;
        }
        
        .critical-news-alert {
          padding: 0.3rem 0.5rem 0.4rem 0.6rem;
          min-height: 45px;
        }
        
        .critical-news-header {
          margin-bottom: 4px;
        }
        
        .critical-news-signal {
          width: 16px;
          height: 16px;
        }
        
        .critical-news-signal i {
          font-size: 0.9em;
        }
        
        .critical-news-title {
          font-size: 1.1em;
          margin-bottom: 3px;
          -webkit-line-clamp: 1;
        }
        
        .critical-news-time {
          font-size: 0.9em;
        }
        
        .critical-news-meta {
          gap: 8px;
          margin-top: 3px;
        }
        
        .critical-news-symbol {
          font-size: .8em;
          padding: .20rem .35rem;
        }
        
        .critical-news-confidence {
          font-size: .8em;
        }
      }
    `
    document.head.appendChild(style)
  }
  
  // Create critical message element
  const createCriticalElement = message => {
    const sigKey = (message.signal || 'HOLD').toUpperCase()
    
    const escapeHtml = unsafe => {
      if (typeof unsafe !== 'string') return unsafe
      const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
      }
      return unsafe.replace(/[&<>"']/g, m => map[m])
    }
    
    const formatDate = dateStr => {
      if (!dateStr) return 'N/A'
      try {
        return new Date(dateStr).toLocaleString()
      } catch (e) {
        return dateStr
      }
    }

    return `
      <div class="critical-news-alert" data-signal="${sigKey}">
        <button class="critical-news-close">
          <i class="fas fa-times"></i>
        </button>
        <div class="critical-news-header">
          <span class="critical-news-symbol">${escapeHtml(message.symbol || 'N/A')}</span>
          <div class="critical-news-time">${formatDate(message.time_reported)}</div>
        </div>
        <div class="critical-news-title">${escapeHtml(message.title || '')}</div>
        <div class="critical-news-meta">
          ${message.confidence ? `<span class="critical-news-confidence">Confidence: ${message.confidence}%</span>` : ''}
        </div>
      </div>
    `
  }
  
  // Create wrapper with responsive behavior
  const createWrapper = () => {
    const dashboard = document.querySelector('.dashboard-container')
    if (!dashboard) {
      console.error("Dashboard container not found")
      return null
    }
    
    let wrapper = document.querySelector('.critical-news-wrapper')
    if (!wrapper) {
      wrapper = document.createElement('div')
      wrapper.className = 'critical-news-wrapper'
      wrapper.innerHTML = '<div class="critical-news-container"></div>'
      dashboard.insertBefore(wrapper, dashboard.firstChild)
    }
    
    return wrapper
  }
  
  // Display critical message
  const displayMessage = message => {
    const wrapper = createWrapper()
    if (!wrapper) return
    
    const container = wrapper.querySelector('.critical-news-container')
    const messageId = message.news_id || Date.now().toString()
    
    // Check for duplicates
    if (criticalMessages.find(m => m.news_id === messageId)) {
      console.log("Critical message already displayed:", messageId)
      return
    }
    
    // Create message object
    const messageObj = {
      news_id: messageId,
      element: null,
      timestamp: Date.now()
    }
    
    // Determine max messages based on screen size
    const maxMessages = isMobile() ? 1 : (isTablet() ? 2 : 2)
    
    // Remove oldest if at capacity
    if (criticalMessages.length >= maxMessages) {
      const oldest = criticalMessages.shift()
      removeMessage(oldest.news_id)
    }
    
    // Add new message
    const html = createCriticalElement(message)
    const tempDiv = document.createElement('div')
    tempDiv.innerHTML = html
    const element = tempDiv.firstElementChild
    container.appendChild(element)

    const btn = element.querySelector('.critical-news-close')
    btn && btn.addEventListener('click', e => {
      e.preventDefault()
      removeMessage(messageId)
    })

    messageObj.element = element
    criticalMessages.push(messageObj)
    
    // Show wrapper
    wrapper.classList.add('visible')
    
    // Auto-remove after 1 hour
    messageTimers[messageId] = setTimeout(() => {
      removeMessage(messageId)
    }, MESSAGE_LIFETIME)
    
    // On mobile, scroll to critical message
    if (isMobile()) {
      element.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }
  
  // Remove message
  const removeMessage = messageId => {
    const index = criticalMessages.findIndex(m => m.news_id === messageId)
    if (index === -1) return
    
    const message = criticalMessages[index]
    if (message.element) {
      message.element.style.opacity = '0'
      message.element.style.transform = 'scale(0.95)'
      setTimeout(() => {
        message.element.remove()
        
        if (criticalMessages.length === 0) {
          const wrapper = document.querySelector('.critical-news-wrapper')
          wrapper?.classList.remove('visible')
        }
      }, 300)
    }
    
    // Clear timer
    if (messageTimers[messageId]) {
      clearTimeout(messageTimers[messageId])
      delete messageTimers[messageId]
    }
    
    // Remove from array
    criticalMessages.splice(index, 1)
  }
  
  // Global close function
  window.closeCriticalMessage = removeMessage
  
  // Hide all messages
  const hideAllMessages = () => {
    const ids = criticalMessages.map(m => m.news_id)
    ids.forEach(removeMessage)
  }
  
  // Handle window resize
  const handleResize = () => {
    const container = document.querySelector('.critical-news-container')
    if (!container) return
    
    // Adjust grid columns based on screen size
    if (isMobile()) {
      container.style.gridTemplateColumns = '1fr'
      // Keep only one message on mobile
      while (criticalMessages.length > 1) {
        const oldest = criticalMessages.shift()
        removeMessage(oldest.news_id)
      }
    } else if (isTablet()) {
      container.style.gridTemplateColumns = '1fr'
    } else {
      container.style.gridTemplateColumns = '1fr 1fr'
    }
  }
  
  // Setup SSE connection
  const setupConnection = () => {
    sseConnection = new window.NewsSSE.SSEConnection({
      url: '/api/news/critical/stream',
      onMessage: data => {
        if (data.type === "clear_critical") {
          hideAllMessages()
          return
        }
        
        if (data.type === "critical") {
          console.log("Received critical message:", data)
          displayMessage(data)
        }
      }
    })
    
    sseConnection.connect()
  }
  
  // Initialize
  document.addEventListener('DOMContentLoaded', () => {
    console.log("Initializing critical news system")
    
    injectStyles()
    
    // Wait for dashboard
    const checkDashboard = setInterval(() => {
      if (document.querySelector('.dashboard-container')) {
        clearInterval(checkDashboard)
        setupConnection()
        
        // Add resize listener
        let resizeTimeout
        window.addEventListener('resize', () => {
          clearTimeout(resizeTimeout)
          resizeTimeout = setTimeout(handleResize, 250)
        })
        
        // Initial resize check
        handleResize()
      }
    }, 100)
  })
  
  // Cleanup
  window.addEventListener('beforeunload', () => {
    sseConnection?.disconnect()
    Object.values(messageTimers).forEach(clearTimeout)
  })
})()