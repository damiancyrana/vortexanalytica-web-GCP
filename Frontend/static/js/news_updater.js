/**
 * Standard news updates via SSE - Enhanced version
 * Features:
 * - Initial load of 50 recent messages
 * - Proper newest-to-oldest ordering
 * - Better duplicate handling
 * - Loading states
 */
document.addEventListener('DOMContentLoaded', () => {
  console.log("Initializing news publication system")
  
  let sseConnection = null
  const newsContainer = document.querySelector('.news-container')
  const MAX_MESSAGES = 50
  let isLoading = false
  let messageIds = new Set() // Track message IDs to prevent duplicates
  
  if (!newsContainer) {
    console.error("News container not found")
    return
  }
  
  // Show loading indicator
  const showLoading = (message = 'Loading news...') => {
    if (isLoading) return
    isLoading = true
    
    const loadingHtml = `
      <div class="news-loading" style="
        text-align: center; 
        padding: 40px 20px; 
        color: var(--text-dim); 
        font-style: italic;
      ">
        <i class="fas fa-spinner fa-spin" style="margin-right: 10px;"></i>
        ${message}
      </div>
    `
    newsContainer.innerHTML = loadingHtml
  }
  
  // Hide loading indicator
  const hideLoading = () => {
    isLoading = false
    const loading = newsContainer.querySelector('.news-loading')
    loading?.remove()
  }
  
  // Show empty state
  const showEmptyState = () => {
    if (newsContainer.querySelectorAll('.news-item').length === 0) {
      newsContainer.innerHTML = `
        <div class="news-empty" style="
          text-align: center; 
          padding: 40px 20px; 
          color: var(--text-dim);
        ">
          <i class="fas fa-rss" style="font-size: 2em; margin-bottom: 15px; opacity: 0.5;"></i>
          <p>No news messages yet. Waiting for updates...</p>
        </div>
      `
    }
  }
  
  // Load initial news messages
  const loadInitialNews = async () => {
    try {
      showLoading('Loading recent news...')
      
      const response = await window.fetchWithAuth('/api/news?limit=50')
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }
      
      const data = await response.json()
      hideLoading()
      
      if (data.news && Array.isArray(data.news) && data.news.length > 0) {
        console.log(`Loading ${data.news.length} initial news messages`)
        
        // Clear any existing content
        newsContainer.innerHTML = ''
        messageIds.clear()
        
        // Add messages in order (they should already be newest first from backend)
        data.news.forEach(message => {
          addNewsMessage(message, false) // Add to bottom to maintain order
        })
        
        console.log(`Loaded ${data.news.length} initial messages`)
      } else {
        showEmptyState()
      }
    } catch (error) {
      console.error('Failed to load initial news:', error)
      hideLoading()
      
      newsContainer.innerHTML = `
        <div class="news-error" style="
          text-align: center; 
          padding: 40px 20px; 
          color: var(--error-color, #ff6b6b);
        ">
          <i class="fas fa-exclamation-triangle" style="margin-right: 10px;"></i>
          Failed to load news. Please try refreshing the page.
        </div>
      `
    }
  }
  
  // Add news message to container
  const addNewsMessage = (message, addToTop = true) => {
    // Validate message
    if (!message || typeof message !== 'object') {
      console.warn('Invalid message received:', message)
      return
    }
    
    const messageId = message.news_id || `msg_${Date.now()}_${Math.random()}`
    
    // Check for duplicates
    if (messageIds.has(messageId)) {
      console.log(`Skipping duplicate message: ${messageId}`)
      return
    }
    
    // Remove empty state and loading
    const noMessages = newsContainer.querySelector('.news-empty')
    const loading = newsContainer.querySelector('.news-loading')
    const error = newsContainer.querySelector('.news-error')
    noMessages?.remove()
    loading?.remove()
    error?.remove()
    
    // Create and add element
    try {
      const html = window.NewsSSE.createNewsElement(message, 'standard')
      const template = document.createElement('template')
      template.innerHTML = html.trim()
      const element = template.content.firstElementChild
      element.newsId = messageId

      if (addToTop) {
        newsContainer.prepend(element)
      } else {
        newsContainer.appendChild(element)
      }
      
      // Track this message ID
      messageIds.add(messageId)
      
      // Limit total messages (keep newest 50)
      const messages = newsContainer.querySelectorAll('.news-item')
      if (messages.length > MAX_MESSAGES) {
        for (let i = MAX_MESSAGES; i < messages.length; i++) {
          const removedElement = messages[i]
          const removedId = removedElement.newsId
          if (removedId) {
            messageIds.delete(removedId)
          }
          removedElement.remove()
        }
        console.log(`Trimmed to ${MAX_MESSAGES} messages`)
      }
      
      console.log(`Added news message: ${messageId} (${addToTop ? 'top' : 'bottom'})`)
    } catch (error) {
      console.error('Error creating news element:', error, message)
    }
  }
  
  // Clear all news
  window.clearNewsMessages = () => {
    const messages = newsContainer.querySelectorAll('.news-item')
    console.log(`Clearing ${messages.length} news messages`)
    
    messages.forEach(msg => msg.remove())
    messageIds.clear()
    
    if (messages.length > 0) {
      showEmptyState()
    }
  }
  
  // Setup SSE connection
  const setupConnection = () => {
    sseConnection = new window.NewsSSE.SSEConnection({
      url: '/api/news/stream',
      onMessage: data => {
        console.log("Received news via SSE:", data)
        
        // Only add new messages to top (SSE provides real-time updates)
        addNewsMessage(data, true)
      },
      onError: (error) => {
        console.error("News SSE connection error:", error)
        
        // Show connection error if no messages are displayed
        if (newsContainer.querySelectorAll('.news-item').length === 0) {
          newsContainer.innerHTML = `
            <div class="connection-error" style="
              text-align: center; 
              padding: 40px 20px; 
              color: var(--error-color, #ff6b6b);
            ">
              <i class="fas fa-wifi" style="margin-right: 10px;"></i>
              Connection lost. Retrying automatically...
            </div>
          `
        }
      },
      onOpen: () => {
        console.log("News SSE connection opened")
        
        // Remove any connection error messages
        const errorMsg = newsContainer.querySelector('.connection-error')
        errorMsg?.remove()
      }
    })
    
    sseConnection.connect()
  }
  
  // Initialize
  const initialize = async () => {
    console.log("Initializing news system...")
    
    // First load initial messages
    await loadInitialNews()
    
    // Then setup real-time connection
    setupConnection()
  }
  
  // Wait for auth system to be ready
  const checkReady = setInterval(() => {
    if (typeof window.fetchWithAuth === 'function') {
      clearInterval(checkReady)
      initialize()
    }
  }, 100)
  
  // Stop checking after 10 seconds
  setTimeout(() => {
    clearInterval(checkReady)
    if (typeof window.fetchWithAuth !== 'function') {
      console.error('Auth system not ready, falling back to SSE only')
      setupConnection()
    }
  }, 10000)
  
  // Refresh button
  const refreshBtn = document.getElementById('refresh-btn')
  refreshBtn?.addEventListener('click', function() {
    const icon = this.querySelector('i')
    icon?.classList.add('fa-spin')
    this.disabled = true
    
    console.log('Manual refresh triggered')
    
    // Reconnect SSE
    sseConnection?.disconnect()
    
    // Reload initial messages
    loadInitialNews().then(() => {
      setupConnection()
    }).finally(() => {
      setTimeout(() => {
        icon?.classList.remove('fa-spin')
        this.disabled = false
      }, 1000)
    })
  })
  
  // Clear button
  const clearBtn = document.getElementById('clear-btn')
  clearBtn?.addEventListener('click', () => {
    if (confirm('Are you sure you want to clear all news messages?')) {
      window.clearNewsMessages()
    }
  })
  
  // Cleanup on unload
  window.addEventListener('beforeunload', () => {
    sseConnection?.disconnect()
  })
  
  // Expose for debugging
  window.newsDebug = {
    messageIds,
    criticalMessages: () => messageIds.size,
    reload: initialize,
    clear: window.clearNewsMessages
  }
})