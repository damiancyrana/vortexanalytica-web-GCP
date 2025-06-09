/**
 * Shared SSE connection module for news updates
 */
window.NewsSSE = (() => {
  // Utility functions
  const utils = {
    formatDate: dateStr => {
      if (!dateStr) return 'N/A'
      try {
        return new Date(dateStr).toLocaleString()
      } catch (e) {
        console.warn("Cannot format date:", e)
        return dateStr
      }
    },
    
    escapeHtml: unsafe => {
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
  }

  // SSE Connection class
  class SSEConnection {
    constructor(config) {
      this.config = {
        url: config.url,
        initialBackoff: config.initialBackoff || 1000,
        maxBackoff: config.maxBackoff || 30000,
        backoffFactor: config.backoffFactor || 1.5,
        maxReconnectAttempts: config.maxReconnectAttempts || 10,
        onMessage: config.onMessage || (() => {}),
        onError: config.onError || (() => {}),
        onOpen: config.onOpen || (() => {}),
        messageLifetime: config.messageLifetime
      }
      
      this.eventSource = null
      this.reconnectAttempt = 0
      this.reconnectTimeout = null
    }
    
    connect() {
      if (this.eventSource) {
        this.eventSource.close()
        this.eventSource = null
      }
      
      try {
        this.eventSource = new EventSource(this.config.url)
        
        this.eventSource.onopen = event => {
          console.log(`SSE connection opened: ${this.config.url}`)
          this.reconnectAttempt = 0
          this.config.onOpen(event)
        }
        
        this.eventSource.onmessage = event => {
          try {
            const data = JSON.parse(event.data)
            
            // Handle control messages
            if (data.type === "heartbeat") {
              console.debug("SSE heartbeat received")
              return
            }
            
            if (data.type === "connected") {
              console.log("SSE connection established:", data.message)
              return
            }
            
            this.config.onMessage(data)
          } catch (error) {
            console.error("Error processing SSE message:", error, event.data)
          }
        }
        
        this.eventSource.onerror = error => {
          console.error("SSE connection error:", error)
          
          if (this.eventSource) {
            this.eventSource.close()
            this.eventSource = null
          }
          
          this.config.onError(error)
          this.reconnect()
        }
      } catch (error) {
        console.error("Cannot create SSE connection:", error)
        this.reconnect()
      }
    }
    
    reconnect() {
      if (this.reconnectAttempt >= this.config.maxReconnectAttempts) {
        console.error(`Maximum SSE reconnect attempts reached (${this.config.maxReconnectAttempts})`)
        return
      }
      
      const backoff = Math.min(
        this.config.initialBackoff * Math.pow(this.config.backoffFactor, this.reconnectAttempt),
        this.config.maxBackoff
      )
      
      console.log(`SSE reconnecting in ${backoff}ms (attempt ${this.reconnectAttempt + 1}/${this.config.maxReconnectAttempts})`)
      
      this.reconnectTimeout = setTimeout(() => {
        this.reconnectAttempt++
        this.connect()
      }, backoff)
    }
    
    disconnect() {
      if (this.eventSource) {
        this.eventSource.close()
        this.eventSource = null
      }
      
      if (this.reconnectTimeout) {
        clearTimeout(this.reconnectTimeout)
        this.reconnectTimeout = null
      }
    }
  }

  // Create news display element
  const createNewsElement = (message, type = 'standard') => {
    if (type === 'critical') {
      return createCriticalElement(message)
    }
    
    // Standard news element
    let impactClass = 'neutral'
    const sentiment = message.sentiment?.toLowerCase()
    if (sentiment === 'positive') {
      impactClass = 'positive'
    } else if (sentiment === 'negative') {
      impactClass = 'negative'
    }
    
    const entitiesHtml = (message.extracted_entities || [])
      .map(entity => {
        const name = entity.normalized_name || entity.text || 'N/A'
        const type = entity.type || 'Unknown'
        return `<span class="news-label">${utils.escapeHtml(name)} (${utils.escapeHtml(type)})</span>`
      })
      .join('')
    
    return `
      <div class="news-item ${impactClass} fade-in">
        <div class="news-header">
          <div class="news-title">${utils.escapeHtml(message.title || 'No title')}</div>
          <div class="news-date">${utils.formatDate(message.time_reported)}</div>
        </div>
        <div class="news-content">
          <p>${utils.escapeHtml(message.interpretation || '')}</p>
        </div>
        <div class="news-labels">${entitiesHtml}</div>
      </div>
    `
  }
  
  const createCriticalElement = message => {
    const signalMap = {
      'BUY': { text: 'UP', icon: 'fa-arrow-up' },
      'SELL': { text: 'DOWN', icon: 'fa-arrow-down' },
      'HOLD': { text: 'HOLD', icon: 'fa-pause' }
    }

    const sigKey = (message.signal || 'HOLD').toUpperCase()
    const signal = signalMap[sigKey] || signalMap['HOLD']

    return `
      <div class="critical-news-alert" data-message-id="${utils.escapeHtml(message.news_id || '')}" data-signal="${sigKey}">
        <button class="critical-news-close" data-message-id="${utils.escapeHtml(message.news_id || '')}">
          <i class="fas fa-times"></i>
        </button>
        <div class="critical-news-header">
          <div class="critical-news-signal">
            <i class="fas ${signal.icon}"></i>
            ${signal.text}
          </div>
          <div class="critical-news-time">${utils.formatDate(message.time_reported)}</div>
        </div>
        <div class="critical-news-title">${utils.escapeHtml(message.title || '')}</div>
        <div class="critical-news-meta">
          <span class="critical-news-symbol">${utils.escapeHtml(message.symbol || 'N/A')}</span>
          ${message.confidence ? `<span class="critical-news-confidence">Confidence: ${message.confidence}%</span>` : ''}
        </div>
      </div>
    `
  }

  return {
    SSEConnection,
    utils,
    createNewsElement
  }
})()
