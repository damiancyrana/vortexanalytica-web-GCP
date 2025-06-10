/**
 * Critical news alerts via SSE - Mobile/Tablet Optimized
 */
(() => {
  let sseConnection = null
  const criticalMessages = []
  const messageTimers = {}
  const MESSAGE_LIFETIME = 3600000 // 1 hour
  
  // Mobile detection
  const isMobile = () => window.innerWidth <= 768
  const isTablet = () => window.innerWidth > 768 && window.innerWidth <= 1023
  
  // Inject responsive styles
  const injectStyles = () => {
    const style = document.createElement('style')
    style.textContent = `
      .critical-news-wrapper {
        display: none;
        width: 100%;
        margin-bottom: 1rem;
        padding: 0 0.5rem;
        box-sizing: border-box;
      }
      
      .critical-news-wrapper.visible {
        display: block;
      }
      
      .critical-news-container {
        display: grid;
        grid-template-columns: 1fr;
        gap: 0.7rem;
        width: 100%;
      }
      
      .critical-news-alert {
        background: rgba(24, 28, 36, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 8px;
        padding: 12px 16px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.1);
        position: relative;
        animation: slideIn 0.3s ease-out;
        transition: all 0.3s ease;
        min-height: 50px;
        overflow: hidden;
      }
      
      .critical-news-alert[data-signal="BUY"] {
        background: rgba(34, 139, 34, 0.85);
        border-color: rgba(50, 205, 50, 0.4);
      }

      .critical-news-alert[data-signal="SELL"] {
        background: rgba(220, 20, 60, 0.85);
        border-color: rgba(255, 69, 0, 0.4);
      }

      .critical-news-alert[data-signal="HOLD"] {
        background: rgba(238, 181, 8, 0.92);
        border-color: rgba(255, 215, 0, 0.4);
      }
      
      .critical-news-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 5px;
        padding-right: 30px;
      }
      
      .critical-news-signal {
        font-size: 0.8rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        display: flex;
        align-items: center;
        gap: 5px;
        color: #fff;
      }
      
      .critical-news-signal i {
        font-size: 0.8rem;
      }
      
      .critical-news-time {
        font-size: 0.7rem;
        opacity: 0.8;
        color: #fff;
        white-space: nowrap;
      }
      
      .critical-news-title {
        font-size: 0.8rem;
        font-weight: 600;
        margin-bottom: 5px;
        line-height: 1.3;
        color: #fff;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
        word-wrap: break-word;
        overflow-wrap: break-word;
      }
      
      .critical-news-meta {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 5px;
        flex-wrap: wrap;
      }
      
      .critical-news-symbol {
        background: rgba(255, 255, 255, 0.15);
        padding: 3px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #fff;
      }
      
      .critical-news-confidence {
        font-size: 0.8rem;
        opacity: 0.8;
        color: #fff;
      }
      
      .critical-news-close {
        position: absolute;
        top: 8px;
        right: 8px;
        background: rgba(255, 255, 255, 0.1);
        border: none;
        color: rgba(255, 255, 255, 0.8);
        cursor: pointer;
        font-size: 0.8rem;
        padding: 4px 8px;
        border-radius: 4px;
        transition: all 0.2s;
        z-index: 10;
        -webkit-tap-highlight-color: transparent;
      }
      
      .critical-news-close:hover,
      .critical-news-close:active {
        color: #fff;
        background: rgba(255, 255, 255, 0.2);
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
        }
        
        .critical-news-container {
          gap: 1rem;
        }
        
        .critical-news-alert {
          padding: 14px 20px;
          min-height: 70px;
        }
        
        .critical-news-signal {
          font-size: 1rem;
        }
        
        .critical-news-title {
          font-size: 1.05rem;
        }
        
        .critical-news-time {
          font-size: 0.8rem;
        }
        
        .critical-news-meta {
          gap: 12px;
        }
        
        .critical-news-symbol {
          font-size: 0.8rem;
          padding: 4px 10px;
        }
        
        .critical-news-confidence {
          font-size: 0.9rem;
        }
      }
      
      /* Desktop Styles */
      @media (min-width: 1024px) {
        .critical-news-wrapper {
          padding: 0;
          margin-bottom: 2rem;
        }
        
        .critical-news-container {
          grid-template-columns: 1fr 1fr;
          gap: 1rem;
        }
        
        .critical-news-alert {
          padding: 16px 24px;
          min-height: 80px;
        }
        
        .critical-news-signal {
          font-size: 1.1rem;
        }
        
        .critical-news-signal i {
          font-size: 1rem;
        }
        
        .critical-news-title {
          font-size: 1.15rem;
          -webkit-line-clamp: 3;
        }
        
        .critical-news-time {
          font-size: 0.85rem;
        }
        
        .critical-news-meta {
          gap: 15px;
        }
        
        .critical-news-symbol {
          font-size: 0.85rem;
          padding: 4px 12px;
        }
        
        .critical-news-confidence {
          font-size: 1rem;
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
        }
        
        .critical-news-alert {
          padding: 10px 12px;
          min-height: 50px;
        }
        
        .critical-news-signal {
          font-size: 0.8rem;
        }
        
        .critical-news-signal i {
          font-size: 0.8rem;
        }
        
        .critical-news-title {
          font-size: 0.85rem;
        }
        
        .critical-news-time {
          font-size: 0.7rem;
        }
        
        .critical-news-symbol {
          font-size: 0.7rem;
          padding: 2px 6px;
        }
        
        .critical-news-confidence {
          font-size: 0.75rem;
        }
        
        .critical-news-close {
          font-size: 0.75rem;
          padding: 3px 6px;
          top: 6px;
          right: 6px;
        }
      }
      
      /* Landscape Mobile */
      @media (max-width: 900px) and (max-height: 600px) and (orientation: landscape) {
        .critical-news-wrapper {
          margin-bottom: 0.5rem;
        }
        
        .critical-news-container {
          gap: 0.5rem;
        }
        
        .critical-news-alert {
          padding: 8px 12px;
          min-height: 45px;
        }
        
        .critical-news-header {
          margin-bottom: 4px;
        }
        
        .critical-news-signal {
          font-size: 0.75rem;
        }
        
        .critical-news-signal i {
          font-size: 0.75rem;
        }
        
        .critical-news-title {
          font-size: 0.8rem;
          margin-bottom: 3px;
          -webkit-line-clamp: 1;
        }
        
        .critical-news-time {
          font-size: 0.65rem;
        }
        
        .critical-news-meta {
          gap: 8px;
          margin-top: 3px;
        }
        
        .critical-news-symbol {
          font-size: 0.65rem;
          padding: 2px 5px;
        }
        
        .critical-news-confidence {
          font-size: 0.7rem;
        }
      }
    `
    document.head.appendChild(style)
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
    const html = window.NewsSSE.createNewsElement(message, 'critical')
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