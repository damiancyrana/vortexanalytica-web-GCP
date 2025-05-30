/**
 * Critical news alerts via SSE
 */
(() => {
  let sseConnection = null
  const criticalMessages = []
  const messageTimers = {}
  const MESSAGE_LIFETIME = 3600000 // 1 hour
  
  // Inject styles
  const injectStyles = () => {
    const style = document.createElement('style')
    style.textContent = `
      .critical-news-wrapper {
        display: none;
        width: 100%;
        margin-bottom: 50px;
      }
      
      .critical-news-wrapper.visible {
        display: block;
      }
      
      .critical-news-container {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
        width: 100%;
      }
      
      .critical-news-alert {
        background: rgba(24, 28, 36, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 8px;
        padding: 12px 20px;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.1);
        position: relative;
        animation: slideIn 0.3s ease-out;
        transition: all 0.3s ease;
        min-height: 50px;
      }
      
      .critical-news-alert.signal-buy {
        background: rgba(34, 139, 34, 0.85);
        border-color: rgba(50, 205, 50, 0.4);
      }
      
      .critical-news-alert.signal-sell {
        background: rgba(220, 20, 60, 0.85);
        border-color: rgba(255, 69, 0, 0.4);
      }
      
      .critical-news-alert.signal-hold {
        background: rgba(238, 181, 8, 0.92);
        border-color: rgba(255, 215, 0, 0.4);
      }
      
      .critical-news-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
      }
      
      .critical-news-signal {
        font-size: 1rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        display: flex;
        align-items: center;
        gap: 6px;
        color: #fff;
      }
      
      .critical-news-signal i {
        font-size: 1rem;
      }
      
      .critical-news-time {
        font-size: 0.85rem;
        padding-right: 30px;
        opacity: 0.8;
        color: #fff;
      }
      
      .critical-news-title {
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 5px;
        line-height: 1.3;
        color: #fff;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      
      .critical-news-meta {
        display: flex;
        align-items: center;
        gap: 15px;
        margin-top: 5px;
      }
      
      .critical-news-symbol {
        background: rgba(255, 255, 255, 0.15);
        padding: 3px 10px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
        color: #fff;
      }
      
      .critical-news-confidence {
        font-size: 1rem;
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
        font-size: 0.9rem;
        padding: 4px 8px;
        border-radius: 4px;
        transition: all 0.2s;
        z-index: 10;
      }
      
      .critical-news-close:hover {
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
      
      @media (max-width: 900px) {
        .critical-news-container {
          grid-template-columns: 1fr;
        }
      }
      
      @media (max-width: 768px) {
        .critical-news-alert {
          padding: 12px 16px;
          min-height: 80px;
        }
        
        .critical-news-signal {
          font-size: 0.9rem;
        }
        
        .critical-news-title {
          font-size: 0.8rem;
        }
      }
    `
    document.head.appendChild(style)
  }
  
  // Create wrapper
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
    
    // Remove oldest if at capacity
    if (criticalMessages.length >= 2) {
      const oldest = criticalMessages.shift()
      removeMessage(oldest.news_id)
    }
    
    // Add new message
    const html = window.NewsSSE.createNewsElement(message, 'critical')
    const tempDiv = document.createElement('div')
    tempDiv.innerHTML = html
    const element = tempDiv.firstElementChild
    container.appendChild(element)
    
    messageObj.element = element
    criticalMessages.push(messageObj)
    
    // Show wrapper
    wrapper.classList.add('visible')
    
    // Auto-remove after 1 hour
    messageTimers[messageId] = setTimeout(() => {
      removeMessage(messageId)
    }, MESSAGE_LIFETIME)
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
      }
    }, 100)
  })
  
  // Cleanup
  window.addEventListener('beforeunload', () => {
    sseConnection?.disconnect()
    Object.values(messageTimers).forEach(clearTimeout)
  })
})()
