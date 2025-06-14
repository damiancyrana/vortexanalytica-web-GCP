/**
 * Narrative Clusters Visualization
 * Interactive D3.js visualization showing news narratives as bubbles
 */

class NarrativeClusters {
  constructor(containerId) {
    this.container = document.getElementById(containerId)
    if (!this.container) {
      console.error(`Container ${containerId} not found`)
      return
    }
    
    // Configuration
    this.config = {
      width: 800,
      height: 600,
      margin: { top: 20, right: 20, bottom: 20, left: 20 },
      minBubbleSize: 20,
      maxBubbleSize: 80,
      forceStrength: 0.03,
      collideStrength: 1.2,
      linkDistance: 100,
      linkStrength: 0.1,
      colors: {
        positive: '#3ec931',
        negative: '#fd1e1e',
        neutral: '#ffcb45'
      }
    }
    
    // State
    this.data = null
    this.simulation = null
    this.selectedNarrative = null
    
    // Initialize
    this.init()
  }
  
  init() {
    // Clear container
    this.container.innerHTML = ''
    
    // Create main structure
    const wrapper = document.createElement('div')
    wrapper.className = 'narrative-clusters-wrapper'
    
    // Create overview container
    this.overviewContainer = document.createElement('div')
    this.overviewContainer.className = 'narrative-overview'
    this.overviewContainer.innerHTML = `
      <div class="narrative-header">
        <h3 class="narrative-title">
          <i class="fas fa-project-diagram"></i>
          Market Narrative Clusters
        </h3>
        <div class="narrative-controls">
          <select class="narrative-timeframe" id="narrative-timeframe">
            <option value="1">Last 1 hour</option>
            <option value="6">Last 6 hours</option>
            <option value="24" selected>Last 24 hours</option>
            <option value="48">Last 48 hours</option>
            <option value="168">Last 7 days</option>
          </select>
          <button class="narrative-refresh" id="narrative-refresh">
            <i class="fas fa-sync-alt"></i>
          </button>
        </div>
      </div>
      <div class="narrative-viz" id="narrative-viz"></div>
      <div class="narrative-legend">
        <div class="legend-item">
          <span class="legend-color positive"></span>
          <span class="legend-label">Bullish</span>
        </div>
        <div class="legend-item">
          <span class="legend-color negative"></span>
          <span class="legend-label">Bearish</span>
        </div>
        <div class="legend-item">
          <span class="legend-color neutral"></span>
          <span class="legend-label">Neutral</span>
        </div>
      </div>
    `
    
    // Create detail container
    this.detailContainer = document.createElement('div')
    this.detailContainer.className = 'narrative-detail'
    this.detailContainer.style.display = 'none'
    
    wrapper.appendChild(this.overviewContainer)
    wrapper.appendChild(this.detailContainer)
    this.container.appendChild(wrapper)
    
    // Setup event listeners
    this.setupEventListeners()
    
    // Load initial data
    this.loadNarratives()
    
    // Setup auto-refresh
    this.refreshInterval = setInterval(() => this.loadNarratives(), 60000) // Every minute
  }
  
  setupEventListeners() {
    // Timeframe change
    const timeframeSelect = document.getElementById('narrative-timeframe')
    timeframeSelect?.addEventListener('change', () => this.loadNarratives())
    
    // Refresh button
    const refreshBtn = document.getElementById('narrative-refresh')
    refreshBtn?.addEventListener('click', () => {
      refreshBtn.classList.add('spinning')
      this.loadNarratives().finally(() => {
        refreshBtn.classList.remove('spinning')
      })
    })
    
    // Window resize
    window.addEventListener('resize', () => this.handleResize())
  }
  
  async loadNarratives() {
    try {
      const hours = document.getElementById('narrative-timeframe')?.value || 24
      const response = await window.fetchWithAuth(`/api/narratives/active?hours=${hours}`)
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      const data = await response.json()
      
      // Load connections
      const connectionsResponse = await window.fetchWithAuth(`/api/narratives/graph/connections?hours=${hours}`)
      if (!connectionsResponse.ok) {
        throw new Error(`HTTP ${connectionsResponse.status}`)
      }
      const connections = await connectionsResponse.json()
      
      this.data = {
        nodes: connections.nodes,
        links: connections.edges,
        narratives: data.narratives
      }
      
      this.render()
    } catch (error) {
      console.error('Failed to load narratives:', error)
      this.showError('Failed to load narrative data. Please try again.')
    }
  }
  
  render() {
    if (!this.data || this.data.nodes.length === 0) {
      this.showEmptyState()
      return
    }
    
    // Clear previous visualization
    const vizContainer = document.getElementById('narrative-viz')
    if (!vizContainer) return
    
    vizContainer.innerHTML = ''
    
    // Calculate dimensions
    const rect = vizContainer.getBoundingClientRect()
    this.config.width = rect.width
    this.config.height = Math.max(400, rect.height)
    
    // Create SVG
    const svg = d3.select(vizContainer)
      .append('svg')
      .attr('width', this.config.width)
      .attr('height', this.config.height)
    
    // Create zoom behavior
    const zoom = d3.zoom()
      .scaleExtent([0.5, 3])
      .on('zoom', (event) => {
        container.attr('transform', event.transform)
      })
    
    svg.call(zoom)
    
    // Create container for zoom/pan
    const container = svg.append('g')
    
    // Create scales
    const strengthScale = d3.scaleLinear()
      .domain([0, 1])
      .range([this.config.minBubbleSize, this.config.maxBubbleSize])
    
    // Process nodes - add radius based on strength
    this.data.nodes.forEach(node => {
      node.radius = strengthScale(node.strength)
      node.color = this.config.colors[node.sentiment.toLowerCase()] || this.config.colors.neutral
    })
    
    // Create force simulation
    this.simulation = d3.forceSimulation(this.data.nodes)
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(this.config.width / 2, this.config.height / 2))
      .force('collision', d3.forceCollide().radius(d => d.radius * this.config.collideStrength))
      .force('link', d3.forceLink(this.data.links)
        .id(d => d.id)
        .distance(this.config.linkDistance)
        .strength(this.config.linkStrength)
      )
    
    // Create links
    const links = container.append('g')
      .attr('class', 'links')
      .selectAll('line')
      .data(this.data.links)
      .enter().append('line')
      .attr('stroke', '#999')
      .attr('stroke-opacity', d => d.weight * 0.6)
      .attr('stroke-width', d => Math.max(1, d.weight * 3))
    
    // Create node groups
    const nodeGroups = container.append('g')
      .attr('class', 'nodes')
      .selectAll('g')
      .data(this.data.nodes)
      .enter().append('g')
      .attr('class', 'node-group')
      .call(this.drag(this.simulation))
    
    // Add circles
    nodeGroups.append('circle')
      .attr('r', d => d.radius)
      .attr('fill', d => d.color)
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .on('click', (event, d) => this.showNarrativeDetail(d.id))
      .on('mouseover', function(event, d) {
        d3.select(this)
          .transition()
          .duration(200)
          .attr('r', d.radius * 1.1)
        
        // Show tooltip
        const tooltip = d3.select('body').append('div')
          .attr('class', 'narrative-tooltip')
          .style('opacity', 0)
        
        tooltip.transition()
          .duration(200)
          .style('opacity', .9)
        
        tooltip.html(`
          <strong>${d.label}</strong><br/>
          ${d.message_count} messages<br/>
          Market Impact: ${(d.market_impact * 100).toFixed(0)}%<br/>
          Sentiment: ${d.sentiment}
        `)
          .style('left', (event.pageX + 10) + 'px')
          .style('top', (event.pageY - 28) + 'px')
      })
      .on('mouseout', function(event, d) {
        d3.select(this)
          .transition()
          .duration(200)
          .attr('r', d.radius)
        
        d3.selectAll('.narrative-tooltip').remove()
      })
    
    // Add labels
    nodeGroups.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '.35em')
      .style('font-size', d => Math.max(10, Math.min(16, d.radius / 3)) + 'px')
      .style('pointer-events', 'none')
      .style('fill', '#fff')
      .style('font-weight', '600')
      .text(d => {
        // Truncate label if too long
        const maxLength = Math.floor(d.radius / 5)
        return d.label.length > maxLength ? d.label.substring(0, maxLength) + '...' : d.label
      })
    
    // Add message count badges
    nodeGroups.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', d => d.radius - 5)
      .style('font-size', '11px')
      .style('pointer-events', 'none')
      .style('fill', '#fff')
      .style('opacity', 0.8)
      .text(d => d.message_count)
    
    // Update positions on tick
    this.simulation.on('tick', () => {
      links
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y)
      
      nodeGroups
        .attr('transform', d => `translate(${d.x},${d.y})`)
    })
  }
  
  drag(simulation) {
    function dragstarted(event, d) {
      if (!event.active) simulation.alphaTarget(0.3).restart()
      d.fx = d.x
      d.fy = d.y
    }
    
    function dragged(event, d) {
      d.fx = event.x
      d.fy = event.y
    }
    
    function dragended(event, d) {
      if (!event.active) simulation.alphaTarget(0)
      d.fx = null
      d.fy = null
    }
    
    return d3.drag()
      .on('start', dragstarted)
      .on('drag', dragged)
      .on('end', dragended)
  }
  
  async showNarrativeDetail(narrativeId) {
    try {
      const response = await window.fetchWithAuth(`/api/narratives/${narrativeId}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      
      const narrative = await response.json()
      
      // Hide overview, show detail
      this.overviewContainer.style.display = 'none'
      this.detailContainer.style.display = 'block'
      
      // Render detail view
      this.renderDetail(narrative)
      
      // Load related narratives
      const relatedResponse = await window.fetchWithAuth(`/api/narratives/${narrativeId}/related`)
      if (relatedResponse.ok) {
        const related = await relatedResponse.json()
        this.renderRelated(related.related_narratives)
      }
    } catch (error) {
      console.error('Failed to load narrative detail:', error)
      this.showError('Failed to load narrative details.')
    }
  }
  
  renderDetail(narrative) {
    // Calculate sentiment percentages
    const totalSentiment = Object.values(narrative.sentiment_distribution).reduce((a, b) => a + b, 0)
    const sentimentPercentages = {}
    for (const [sentiment, count] of Object.entries(narrative.sentiment_distribution)) {
      sentimentPercentages[sentiment] = totalSentiment > 0 ? (count / totalSentiment * 100).toFixed(1) : 0
    }
    
    this.detailContainer.innerHTML = `
      <div class="narrative-detail-header">
        <button class="back-btn" onclick="narrativeClusters.showOverview()">
          <i class="fas fa-arrow-left"></i> Back to Overview
        </button>
        <h3>${narrative.primary_theme}</h3>
      </div>
      
      <div class="narrative-stats">
        <div class="stat-card">
          <div class="stat-value">${narrative.message_count}</div>
          <div class="stat-label">Messages</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${(narrative.strength * 100).toFixed(0)}%</div>
          <div class="stat-label">Strength</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${(narrative.market_impact * 100).toFixed(0)}%</div>
          <div class="stat-label">Market Impact</div>
        </div>
      </div>
      
      <div class="narrative-sentiment">
        <h4>Sentiment Distribution</h4>
        <div class="sentiment-bars">
          <div class="sentiment-bar positive" style="width: ${sentimentPercentages.Positive}%">
            <span>${sentimentPercentages.Positive}%</span>
          </div>
          <div class="sentiment-bar neutral" style="width: ${sentimentPercentages.Neutral}%">
            <span>${sentimentPercentages.Neutral}%</span>
          </div>
          <div class="sentiment-bar negative" style="width: ${sentimentPercentages.Negative}%">
            <span>${sentimentPercentages.Negative}%</span>
          </div>
        </div>
      </div>
      
      <div class="narrative-entities">
        <h4>Key Entities</h4>
        <div class="entity-list">
          ${narrative.top_entities.map(([entity, count]) => `
            <span class="entity-tag">
              ${entity} <span class="entity-count">${count}</span>
            </span>
          `).join('')}
        </div>
      </div>
      
      <div class="narrative-tags">
        <h4>Topics</h4>
        <div class="tag-list">
          ${narrative.top_tags.map(([tag, count]) => `
            <span class="topic-tag">
              ${tag} <span class="tag-count">${count}</span>
            </span>
          `).join('')}
        </div>
      </div>
      
      <div class="narrative-messages">
        <h4>Recent Messages</h4>
        <div class="message-timeline">
          ${narrative.messages.slice(0, 10).map(msg => `
            <div class="timeline-item ${msg.sentiment.label.toLowerCase()}">
              <div class="timeline-time">${this.formatTime(msg.time_reported)}</div>
              <div class="timeline-content">
                <div class="timeline-title">${msg.title}</div>
                ${msg.summary ? `<div class="timeline-summary">${msg.summary}</div>` : ''}
              </div>
            </div>
          `).join('')}
        </div>
      </div>
      
      <div class="related-narratives" id="related-narratives"></div>
    `
  }
  
  renderRelated(relatedNarratives) {
    const container = document.getElementById('related-narratives')
    if (!container || relatedNarratives.length === 0) return
    
    container.innerHTML = `
      <h4>Related Narratives</h4>
      <div class="related-list">
        ${relatedNarratives.map(item => `
          <div class="related-item" onclick="narrativeClusters.showNarrativeDetail('${item.narrative.id}')">
            <div class="related-theme">${item.narrative.primary_theme}</div>
            <div class="related-stats">
              <span>${item.narrative.message_count} messages</span>
              <span class="similarity">${(item.similarity * 100).toFixed(0)}% similar</span>
            </div>
          </div>
        `).join('')}
      </div>
    `
  }
  
  showOverview() {
    this.detailContainer.style.display = 'none'
    this.overviewContainer.style.display = 'block'
  }
  
  showEmptyState() {
    const vizContainer = document.getElementById('narrative-viz')
    if (!vizContainer) return
    
    vizContainer.innerHTML = `
      <div class="empty-state">
        <i class="fas fa-project-diagram"></i>
        <p>No narrative clusters found in the selected timeframe.</p>
        <p>Try expanding the time window or wait for more news.</p>
      </div>
    `
  }
  
  showError(message) {
    const vizContainer = document.getElementById('narrative-viz')
    if (!vizContainer) return
    
    vizContainer.innerHTML = `
      <div class="error-state">
        <i class="fas fa-exclamation-triangle"></i>
        <p>${message}</p>
        <button onclick="narrativeClusters.loadNarratives()">Retry</button>
      </div>
    `
  }
  
  formatTime(timeStr) {
    try {
      const date = new Date(timeStr)
      const now = new Date()
      const diff = now - date
      
      if (diff < 3600000) { // Less than 1 hour
        return `${Math.floor(diff / 60000)}m ago`
      } else if (diff < 86400000) { // Less than 1 day
        return `${Math.floor(diff / 3600000)}h ago`
      } else {
        return date.toLocaleDateString()
      }
    } catch {
      return timeStr
    }
  }
  
  handleResize() {
    if (this.data) {
      this.render()
    }
  }
  
  destroy() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval)
    }
    if (this.simulation) {
      this.simulation.stop()
    }
    this.container.innerHTML = ''
  }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  // Check if we're on the dashboard page
  const dashboardContainer = document.querySelector('.dashboard-container')
  if (dashboardContainer) {
    // Create container for narrative clusters
    const clustersContainer = document.createElement('div')
    clustersContainer.id = 'narrative-clusters-container'
    clustersContainer.className = 'narrative-clusters-container'
    dashboardContainer.appendChild(clustersContainer)
    
    // Initialize narrative clusters
    window.narrativeClusters = new NarrativeClusters('narrative-clusters-container')
  }
})