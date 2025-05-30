/**
 * Standard news updates via SSE
 */
document.addEventListener('DOMContentLoaded', () => {
  console.log("Initializing news publication system")
  
  let sseConnection = null
  const newsContainer = document.querySelector('.news-container')
  
  if (!newsContainer) {
    console.error("News container not found")
    return
  }
  
  // Add news message to container
  const addNewsMessage = (message, addToTop = true) => {
    // Check for duplicates
    if (message.news_id && document.querySelector(`.news-item[data-news-id="${message.news_id}"]`)) {
      console.log(`Skipping duplicate: ${message.news_id}`)
      return
    }
    
    // Hide no messages indicator
    const noMessages = newsContainer.querySelector('p[style*="text-align: center"]')
    noMessages?.remove()
    
    // Hide loading animation
    const loading = newsContainer.querySelector('.quantum-loading')
    if (loading) loading.style.display = 'none'
    
    // Create and add element
    const html = window.NewsSSE.createNewsElement(message, 'standard')
    newsContainer.insertAdjacentHTML(addToTop ? 'afterbegin' : 'beforeend', html)
    
    // Limit messages
    const messages = newsContainer.querySelectorAll('.news-item')
    if (messages.length > 50) {
      for (let i = 50; i < messages.length; i++) {
        messages[i].remove()
      }
    }
  }
  
  // Clear all news
  window.clearNewsMessages = () => {
    const messages = newsContainer.querySelectorAll('.news-item')
    messages.forEach(msg => msg.remove())
    
    if (messages.length > 0) {
      newsContainer.innerHTML = '<p style="text-align: center; padding: 20px;">Wiadomości zostały wyczyszczone.</p>'
    }
  }
  
  // Setup SSE connection
  const setupConnection = () => {
    sseConnection = new window.NewsSSE.SSEConnection({
      url: '/api/news/stream',
      onMessage: data => {
        console.log("Received news via SSE:", data)
        addNewsMessage(data, true)
      },
      onError: () => {
        // Error handling done by SSEConnection class
      },
      onOpen: () => {
        // Remove any error messages
        const errorMsg = newsContainer.querySelector('.connection-error')
        errorMsg?.remove()
      }
    })
    
    sseConnection.connect()
  }
  
  // Initialize
  const loadingDiv = newsContainer.querySelector('.quantum-loading div:last-child')
  if (loadingDiv) {
    loadingDiv.textContent = 'Oczekiwanie na nowe wiadomości...'
  }
  
  setupConnection()
  
  // Refresh button
  const refreshBtn = document.getElementById('refresh-btn')
  refreshBtn?.addEventListener('click', function() {
    const icon = this.querySelector('i')
    icon?.classList.add('fa-spin')
    this.disabled = true
    
    sseConnection.reconnectAttempt = 0
    sseConnection.disconnect()
    sseConnection.connect()
    
    setTimeout(() => {
      icon?.classList.remove('fa-spin')
      this.disabled = false
    }, 1000)
  })
  
  // Clear button
  const clearBtn = document.getElementById('clear-btn')
  clearBtn?.addEventListener('click', window.clearNewsMessages)
  
  // Cleanup on unload
  window.addEventListener('beforeunload', () => {
    sseConnection?.disconnect()
  })
})
