/**
 * Frontend/static/js/narrative_clusters.js
 * Interactive D3.js narrative cluster visualization
 */

class NarrativeClusterVisualization {
  constructor(containerId) {
    this.containerId = containerId
    this.container = document.getElementById(containerId)
    
    if (!this.container) {
      console.error(`Container ${containerId} not found`)
      return
    }
    
    // Configuration
    this.config = {
      width: 800,
      height: 600,
      minNodeSize: 20,
      maxNodeSize: 80,
      linkDistance: 150,
      linkStrength: 0.1,
      chargeStrength: -300,
      collisionRadius: 1.2,
      transitionDuration: 750
    }
    
    // Color schemes
    this.colors = {
      positive: '#3ec931',
      negative: '#fd1e1e',
      neutral: '#ffcb45',
      link: 'rgba(0, 229, 255, 0.3)',
      text: {
        light: '#1a1f2a',
        dark: '#ffffff'
      },
      background: {
        light: '#f7f8fa',
        dark: 'transparent'
      }
    }
    
    // Data
    this.nodes = []
    this.links = []
    this.simulation = null
    
    // Selected narrative
    this.selectedNarrative = null
    
    // Initialize
    this.init()
  }
  
  init() {
    // Clear container
    this.container.innerHTML = ''
    
    // Create main wrapper
    const wrapper = document.createElement('div')
    wrapper.className = 'narrative-clusters-wrapper'
    this.container.appendChild(wrapper)
    
    // Create header
    const header = document.createElement('div')
    header.className = 'narrative-header'
    header.innerHTML = `
      <h3><i class="fas fa-network-wired"></i> Narrative Clusters</h3>
      <div class="narrative-controls">
        <button id="refresh-narratives" class="narrative-btn">
          <i class="fas fa-sync-alt"></i> Refresh
        </button>
        <button id="reset-zoom" class="narrative-btn">
          <i class="fas fa-compress"></i> Reset View
        </button>
      </div>
    `
    wrapper.appendChild(header)
    
    // Create visualization container
    const vizContainer = document.createElement('div')
    vizContainer.className = 'narrative-viz-container'
    wrapper.appendChild(vizContainer)
    
    // Create detail panel
    const detailPanel = document.createElement('div')
    detailPanel.className = 'narrative-detail-panel'
    detailPanel.style.display = 'none'
    wrapper.appendChild(detailPanel)
    
    // Setup SVG
    this.setupSVG(vizContainer)
    
    // Setup event handlers
    this.setupEventHandlers()
    
    // Load initial data
    this.loadData()
    
    // Setup auto-refresh
    this.startAutoRefresh()
  }
  
  setupSVG(container) {
    // Get container dimensions
    const rect = container.getBoundingClientRect()
    this.config.width = rect.width || 800
    this.config.height = Math.max(400, rect.height || 600)
    
    // Create SVG
    this.svg = d3.select(container)
      .append('svg')
      .attr('width', this.config.width)
      .attr('height', this.config.height)
      .attr('viewBox', `0 0 ${this.config.width} ${this.config.height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
    
    // Add background
    const isDark = document.body.classList.contains('dark-theme')
    this.svg.append('rect')
      .attr('width', this.config.width)
      .attr('height', this.config.height)
      .attr('fill', isDark ? this.colors.background.dark : this.colors.background.light)
      .attr('opacity', isDark ? 0 : 1)
    
    // Create groups
    this.g = this.svg.append('g')
    
    // Links group (behind nodes)
    this.linkGroup = this.g.append('g').attr('class', 'links')
    
    // Nodes group
    this.nodeGroup = this.g.append('g').attr('class', 'nodes')
    
    // Setup zoom
    this.zoom = d3.zoom()
      .scaleExtent([0.5, 3])
      .on('zoom', (event) => {
        this.g.attr('transform', event.transform)
      })
    
    this.svg.call(this.zoom)
  }
  
  setupEventHandlers() {
    // Refresh button
    document.getElementById('refresh-narratives')?.addEventListener('click', () => {
      this.loadData()
    })
    
    // Reset zoom button
    document.getElementById('reset-zoom')?.addEventListener('click', () => {
      this.resetZoom()
    })
    
    // Theme change listener
    const themeObserver = new MutationObserver(() => {
      this.updateTheme()
    })
    themeObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] })
    
    // Window resize
    let resizeTimer
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer)
      resizeTimer = setTimeout(() => this.handleResize(), 250)
    })
  }
  
  async loadData() {
    try {
      // Show loading state
      this.showLoading()
      
      // Fetch narrative data
      const response = await window.fetchWithAuth('/api/narratives/active?limit=30')
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      
      const data = await response.json()
      
      // Process data
      this.processData(data)
      
      // Update visualization
      this.updateVisualization()
      
      // Hide loading
      this.hideLoading()
      
    } catch (error) {
      console.error('Failed to load narrative data:', error)
      this.hideLoading()
      this.showError('Failed to load narratives')
    }
  }
  
  processData(data) {
    // Clear existing data
    this.nodes = []
    this.links = []
    
    if (!data.clusters || data.clusters.length === 0) {
      return
    }
    
    // Create nodes
    const nodeMap = new Map()
    
    data.clusters.forEach(cluster => {
      const node = {
        id: cluster.id,
        title: cluster.title,
        strength: cluster.strength,
        sentiment: cluster.sentiment,
        messageCount: cluster.message_count,
        entities: cluster.entities,
        summary: cluster.summary,
        radius: this.calculateNodeRadius(cluster.strength),
        color: this.colors[cluster.sentiment] || this.colors.neutral
      }
      
      this.nodes.push(node)
      nodeMap.set(cluster.id, node)
    })
    
    // Create links
    if (data.connections) {
      data.connections.forEach(conn => {
        if (nodeMap.has(conn.source) && nodeMap.has(conn.target)) {
          this.links.push({
            source: conn.source,
            target: conn.target,
            strength: conn.strength
          })
        }
      })
    }
  }
  
  calculateNodeRadius(strength) {
    // Scale strength (0-1) to radius
    const { minNodeSize, maxNodeSize } = this.config
    return minNodeSize + (maxNodeSize - minNodeSize) * Math.sqrt(strength)
  }
  
  updateVisualization() {
    // Update simulation
    this.updateSimulation()
    
    // Update links
    this.updateLinks()
    
    // Update nodes
    this.updateNodes()
  }
  
  updateSimulation() {
    // Create or update force simulation
    if (!this.simulation) {
      this.simulation = d3.forceSimulation(this.nodes)
        .force('link', d3.forceLink(this.links)
          .id(d => d.id)
          .distance(this.config.linkDistance)
          .strength(d => d.strength * this.config.linkStrength)
        )
        .force('charge', d3.forceManyBody()
          .strength(this.config.chargeStrength)
        )
        .force('center', d3.forceCenter(this.config.width / 2, this.config.height / 2))
        .force('collision', d3.forceCollide()
          .radius(d => d.radius * this.config.collisionRadius)
        )
        .on('tick', () => this.ticked())
    } else {
      // Update existing simulation
      this.simulation.nodes(this.nodes)
      this.simulation.force('link').links(this.links)
      this.simulation.alpha(0.3).restart()
    }
  }
  
  updateLinks() {
    // Data join
    const link = this.linkGroup.selectAll('.link')
      .data(this.links, d => `${d.source.id || d.source}-${d.target.id || d.target}`)
    
    // Remove old links
    link.exit()
      .transition()
      .duration(this.config.transitionDuration)
      .style('opacity', 0)
      .remove()
    
    // Add new links
    const linkEnter = link.enter()
      .append('line')
      .attr('class', 'link')
      .style('stroke', this.colors.link)
      .style('stroke-width', d => Math.sqrt(d.strength) * 3)
      .style('opacity', 0)
    
    // Update all links
    link.merge(linkEnter)
      .transition()
      .duration(this.config.transitionDuration)
      .style('opacity', d => 0.3 + d.strength * 0.4)
  }
  
  updateNodes() {
    const isDark = document.body.classList.contains('dark-theme')
    
    // Data join
    const node = this.nodeGroup.selectAll('.node')
      .data(this.nodes, d => d.id)
    
    // Remove old nodes
    node.exit()
      .transition()
      .duration(this.config.transitionDuration)
      .attr('r', 0)
      .style('opacity', 0)
      .remove()
    
    // Add new nodes
    const nodeEnter = node.enter()
      .append('g')
      .attr('class', 'node')
      .call(this.drag())
      .on('click', (event, d) => this.handleNodeClick(d))
      .on('mouseenter', (event, d) => this.handleNodeHover(d, true))
      .on('mouseleave', (event, d) => this.handleNodeHover(d, false))
    
    // Add circles
    nodeEnter.append('circle')
      .attr('r', 0)
      .style('fill', d => d.color)
      .style('stroke', isDark ? 'rgba(255, 255, 255, 0.2)' : 'rgba(0, 0, 0, 0.1)')
      .style('stroke-width', 2)
      .style('cursor', 'pointer')
      .transition()
      .duration(this.config.transitionDuration)
      .attr('r', d => d.radius)
    
    // Add labels
    nodeEnter.append('text')
      .attr('class', 'node-label')
      .attr('text-anchor', 'middle')
      .attr('dy', '.35em')
      .style('fill', isDark ? this.colors.text.dark : this.colors.text.light)
      .style('font-size', d => Math.min(d.radius / 3, 14) + 'px')
      .style('font-weight', '600')
      .style('pointer-events', 'none')
      .text(d => this.truncateText(d.title, d.radius))
      .style('opacity', 0)
      .transition()
      .duration(this.config.transitionDuration)
      .style('opacity', 1)
    
    // Update existing nodes
    node.select('circle')
      .transition()
      .duration(this.config.transitionDuration)
      .attr('r', d => d.radius)
      .style('fill', d => d.color)
    
    node.select('text')
      .text(d => this.truncateText(d.title, d.radius))
      .style('font-size', d => Math.min(d.radius / 3, 14) + 'px')
  }
  
  ticked() {
    // Update link positions
    this.linkGroup.selectAll('.link')
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y)
    
    // Update node positions
    this.nodeGroup.selectAll('.node')
      .attr('transform', d => `translate(${d.x},${d.y})`)
  }
  
  drag() {
    const dragstarted = (event, d) => {
      if (!event.active) this.simulation.alphaTarget(0.3).restart()
      d.fx = d.x
      d.fy = d.y
    }
    
    const dragged = (event, d) => {
      d.fx = event.x
      d.fy = event.y
    }
    
    const dragended = (event, d) => {
      if (!event.active) this.simulation.alphaTarget(0)
      d.fx = null
      d.fy = null
    }
    
    return d3.drag()
      .on('start', dragstarted)
      .on('drag', dragged)
      .on('end', dragended)
  }
  
  handleNodeClick(node) {
    if (this.selectedNarrative === node.id) {
      // Deselect
      this.selectedNarrative = null
      this.hideDetailPanel()
    } else {
      // Select new narrative
      this.selectedNarrative = node.id
      this.showDetailPanel(node)
    }
    
    // Update node highlighting
    this.updateNodeHighlighting()
  }
  
  handleNodeHover(node, isHovering) {
    if (isHovering) {
      // Show tooltip
      this.showTooltip(node)
    } else {
      // Hide tooltip
      this.hideTooltip()
    }
  }
  
  updateNodeHighlighting() {
    const selected = this.selectedNarrative
    
    this.nodeGroup.selectAll('.node')
      .style('opacity', d => {
        if (!selected) return 1
        return d.id === selected ? 1 : 0.3
      })
    
    this.linkGroup.selectAll('.link')
      .style('opacity', d => {
        if (!selected) return d => 0.3 + d.strength * 0.4
        return (d.source.id === selected || d.target.id === selected) ? 0.6 : 0.1
      })
  }
  
  async showDetailPanel(node) {
    const panel = document.querySelector('.narrative-detail-panel')
    if (!panel) return
    
    // Show loading
    panel.innerHTML = '<div class="loading">Loading details...</div>'
    panel.style.display = 'block'
    
    try {
      // Fetch detailed data
      const response = await window.fetchWithAuth(`/api/narratives/${node.id}`)
      if (!response.ok) throw new Error('Failed to load details')
      
      const data = await response.json()
      
      // Render details
      this.renderDetailPanel(data)
      
    } catch (error) {
      console.error('Failed to load narrative details:', error)
      panel.innerHTML = '<div class="error">Failed to load details</div>'
    }
  }
  
  renderDetailPanel(data) {
    const panel = document.querySelector('.narrative-detail-panel')
    if (!panel) return
    
    const narrative = data.narrative
    const messages = data.messages || []
    const related = data.related_narratives || []
    
    // Build HTML
    let html = `
      <div class="detail-header">
        <h4>${narrative.title}</h4>
        <button class="close-detail" onclick="narrativeViz.hideDetailPanel()">
          <i class="fas fa-times"></i>
        </button>
      </div>
      
      <div class="detail-content">
        <div class="detail-section">
          <h5>Overview</h5>
          <p class="summary">${narrative.summary}</p>
          <div class="narrative-stats">
            <span class="stat">
              <i class="fas fa-comment"></i> ${narrative.message_count} messages
            </span>
            <span class="stat sentiment-${narrative.sentiment}">
              <i class="fas fa-chart-line"></i> ${narrative.sentiment}
            </span>
            <span class="stat">
              <i class="fas fa-signal"></i> ${Math.round(narrative.strength * 100)}% strength
            </span>
          </div>
        </div>
        
        <div class="detail-section">
          <h5>Key Entities</h5>
          <div class="entity-tags">
            ${narrative.entities.slice(0, 10).map(entity => 
              `<span class="entity-tag">${entity}</span>`
            ).join('')}
          </div>
        </div>
        
        <div class="detail-section">
          <h5>Recent Messages</h5>
          <div class="message-list">
            ${messages.slice(0, 5).map(msg => `
              <div class="message-item">
                <div class="message-title">${msg.title}</div>
                <div class="message-time">${new Date(msg.time_reported).toLocaleString()}</div>
              </div>
            `).join('')}
          </div>
        </div>
        
        ${related.length > 0 ? `
          <div class="detail-section">
            <h5>Related Narratives</h5>
            <div class="related-list">
              ${related.map(r => `
                <div class="related-item" onclick="narrativeViz.selectNarrative('${r.id}')">
                  <span class="related-title">${r.title}</span>
                  <span class="related-similarity">${Math.round(r.similarity * 100)}% similar</span>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    `
    
    panel.innerHTML = html
  }
  
  hideDetailPanel() {
    const panel = document.querySelector('.narrative-detail-panel')
    if (panel) {
      panel.style.display = 'none'
    }
    this.selectedNarrative = null
    this.updateNodeHighlighting()
  }
  
  selectNarrative(id) {
    const node = this.nodes.find(n => n.id === id)
    if (node) {
      this.handleNodeClick(node)
    }
  }
  
    showTooltip(node) {
    // Create or update tooltip
    let tooltip = document.getElementById('narrative-tooltip')
    if (!tooltip) {
        tooltip = document.createElement('div')
        tooltip.id = 'narrative-tooltip'
        tooltip.className = 'narrative-tooltip'
        document.body.appendChild(tooltip)
    }
    
    // Get top entities for display
    const topEntities = Array.from(node.entities || [])
        .slice(0, 5)
        .map(e => e.charAt(0).toUpperCase() + e.slice(1))
        .join(', ');
    
    tooltip.innerHTML = `
        <strong>${node.title}</strong><br>
        <div style="margin: 4px 0; font-size: 0.85em; opacity: 0.9;">
        <strong>Entities:</strong> ${topEntities || 'None'}
        </div>
        <div style="margin: 4px 0;">
        <span style="color: ${node.color}">●</span> ${node.sentiment} sentiment<br>
        ${node.messageCount} messages • ${Math.round(node.strength * 100)}% strength
        </div>
        <em style="font-size: 0.8em; opacity: 0.7;">Click for details</em>
    `
    
    // Position tooltip
    const event = d3.event || window.event
    tooltip.style.left = (event.pageX + 10) + 'px'
    tooltip.style.top = (event.pageY - 10) + 'px'
    tooltip.style.display = 'block'
    }
// Add this method to the NarrativeClusterVisualization class
createLegend() {
  const legendData = [
    { label: 'Positive', color: this.colors.positive },
    { label: 'Negative', color: this.colors.negative },
    { label: 'Neutral', color: this.colors.neutral }
  ]
  
  const legend = this.svg.append('g')
    .attr('class', 'legend')
    .attr('transform', `translate(20, 20)`)
  
  const legendItems = legend.selectAll('.legend-item')
    .data(legendData)
    .enter().append('g')
    .attr('class', 'legend-item')
    .attr('transform', (d, i) => `translate(0, ${i * 25})`)
  
  legendItems.append('circle')
    .attr('r', 8)
    .style('fill', d => d.color)
    .style('stroke', 'rgba(255, 255, 255, 0.3)')
    .style('stroke-width', 1)
  
  legendItems.append('text')
    .attr('x', 15)
    .attr('y', 0)
    .attr('dy', '0.35em')
    .style('font-size', '12px')
    .style('fill', document.body.classList.contains('dark-theme') ? '#fff' : '#333')
    .text(d => d.label)
}

// Call it in the init method after setupSVG
this.createLegend()
  hideTooltip() {
    const tooltip = document.getElementById('narrative-tooltip')
    if (tooltip) {
      tooltip.style.display = 'none'
    }
  }
  
    // Update the truncateText method to be less aggressive
    truncateText(text, radius) {
    // Calculate max characters based on radius
    // More generous with space
    const charsPerPixel = 0.15; // Increased from 0.25
    const maxLength = Math.floor(radius * 2 * charsPerPixel);
    
    if (text.length <= maxLength) return text;
    
    // Try to break at word boundary
    const truncated = text.substring(0, maxLength - 3);
    const lastSpace = truncated.lastIndexOf(' ');
    if (lastSpace > maxLength * 0.6) {
        return truncated.substring(0, lastSpace) + '...';
    }
    
    return truncated + '...';
    }

    // Add method to get display text for a node
    getNodeDisplayText(node) {
    // For small nodes, show just the main entity
    if (node.radius < 30) {
        const entities = Array.from(node.entities || []);
        if (entities.length > 0) {
        // Get the shortest meaningful entity
        const sorted = entities
            .filter(e => e.length > 2)
            .sort((a, b) => a.length - b.length);
        return sorted[0] ? sorted[0].toUpperCase() : node.title;
        }
    }
    
    // For medium nodes, show abbreviated title
    if (node.radius < 50) {
        // Try to get first two words or main entity
        const words = node.title.split(/[\s\-\(]/);
        if (words.length >= 2) {
        return words.slice(0, 2).join(' ');
        }
    }
    
    // For large nodes, show more of the title
    return node.title;
    }

    // In updateNodes method, replace the text setting part:
    nodeEnter.append('text')
    .attr('class', 'node-label')
    .attr('text-anchor', 'middle')
    .attr('dy', '.35em')
    .style('fill', isDark ? this.colors.text.dark : this.colors.text.light)
    .style('font-size', d => Math.min(d.radius / 3, 14) + 'px')
    .style('font-weight', '600')
    .style('pointer-events', 'none')
    .text(d => this.truncateText(this.getNodeDisplayText(d), d.radius))
    .style('opacity', 0)
    .transition()
    .duration(this.config.transitionDuration)
    .style('opacity', 1)

    // Update existing nodes text
    node.select('text')
    .text(d => this.truncateText(this.getNodeDisplayText(d), d.radius))
    .style('font-size', d => Math.min(d.radius / 3, 14) + 'px')

    
  
  resetZoom() {
    this.svg.transition()
      .duration(750)
      .call(this.zoom.transform, d3.zoomIdentity)
  }
  
  handleResize() {
    const container = document.querySelector('.narrative-viz-container')
    if (!container) return
    
    const rect = container.getBoundingClientRect()
    this.config.width = rect.width || 800
    this.config.height = Math.max(400, rect.height || 600)
    
    this.svg
      .attr('width', this.config.width)
      .attr('height', this.config.height)
      .attr('viewBox', `0 0 ${this.config.width} ${this.config.height}`)
    
    // Update center force
    if (this.simulation) {
      this.simulation.force('center', d3.forceCenter(this.config.width / 2, this.config.height / 2))
      this.simulation.alpha(0.3).restart()
    }
  }
  
  updateTheme() {
    const isDark = document.body.classList.contains('dark-theme')
    
    // Update background
    this.svg.select('rect')
      .attr('fill', isDark ? this.colors.background.dark : this.colors.background.light)
      .attr('opacity', isDark ? 0 : 1)
    
    // Update node strokes
    this.nodeGroup.selectAll('circle')
      .style('stroke', isDark ? 'rgba(255, 255, 255, 0.2)' : 'rgba(0, 0, 0, 0.1)')
    
    // Update text colors
    this.nodeGroup.selectAll('text')
      .style('fill', isDark ? this.colors.text.dark : this.colors.text.light)
  }
  
  showLoading() {
    // Add loading overlay
    let loading = this.container.querySelector('.narrative-loading')
    if (!loading) {
      loading = document.createElement('div')
      loading.className = 'narrative-loading'
      loading.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading narratives...'
      this.container.appendChild(loading)
    }
    loading.style.display = 'flex'
  }
  
  hideLoading() {
    const loading = this.container.querySelector('.narrative-loading')
    if (loading) {
      loading.style.display = 'none'
    }
  }
  
  showError(message) {
    let error = this.container.querySelector('.narrative-error')
    if (!error) {
      error = document.createElement('div')
      error.className = 'narrative-error'
      this.container.appendChild(error)
    }
    error.innerHTML = `<i class="fas fa-exclamation-triangle"></i> ${message}`
    error.style.display = 'block'
    
    setTimeout(() => {
      error.style.display = 'none'
    }, 5000)
  }
  
  startAutoRefresh() {
    // Refresh every 5 minutes
    this.refreshInterval = setInterval(() => {
      this.loadData()
    }, 5 * 60 * 1000)
  }
  
  destroy() {
    // Clean up
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval)
    }
    
    if (this.simulation) {
      this.simulation.stop()
    }
    
    // Remove tooltip
    const tooltip = document.getElementById('narrative-tooltip')
    if (tooltip) {
      tooltip.remove()
    }
    
    // Clear container
    this.container.innerHTML = ''
  }
}

// Initialize when document is ready
document.addEventListener('DOMContentLoaded', () => {
  // Wait for auth to be ready
  const checkReady = setInterval(() => {
    if (typeof window.fetchWithAuth === 'function' && 
        document.querySelector('.dashboard-container')) {
      clearInterval(checkReady)
      
      // Create narrative visualization
      window.narrativeViz = new NarrativeClusterVisualization('dashboard-container')
    }
  }, 100)
  
  // Stop checking after 10 seconds
  setTimeout(() => clearInterval(checkReady), 10000)
})