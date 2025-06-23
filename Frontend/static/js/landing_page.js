        // Smooth scroll behavior for navigation
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            });
        });

        // Navigation background on scroll
        window.addEventListener('scroll', () => {
            const navbar = document.getElementById('navbar');
            if (window.scrollY > 50) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        });

        // Intersection Observer for animations
        const observerOptions = {
            threshold: 0.1,
            rootMargin: '0px 0px -100px 0px'
        };

        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                    
                    // Stagger animations for multiple elements
                    if (entry.target.classList.contains('feature-card') || 
                        entry.target.classList.contains('timeline-step') ||
                        entry.target.classList.contains('stat-item')) {
                        const siblings = Array.from(entry.target.parentElement.children);
                        siblings.forEach((sibling, index) => {
                            setTimeout(() => {
                                sibling.classList.add('visible');
                            }, index * 150);
                        });
                    }
                }
            });
        }, observerOptions);

        // Observe elements
        document.querySelectorAll('.feature-header, .feature-card, .timeline-step, .stat-item, .fade-in, .award-showcase, .press-item').forEach(el => {
            observer.observe(el);
        });

        // D3.js Engine Animation System
        class VortexEngineAnimation {
            constructor() {
                this.svg = null;
                this.container = null;
                this.particles = [];
                this.connectionPaths = [];
                this.swarmNodes = [];
                this.animationRunning = false;
                this.init();
            }

            init() {
                this.container = document.querySelector('.viz-container');
                if (!this.container) return;

                const rect = this.container.getBoundingClientRect();
                this.svg = d3.select('#viz-svg')
                    .attr('width', rect.width)
                    .attr('height', rect.height);

                // Initialize components
                this.initializeConnectionPaths();
                this.initializeSwarm();
            }

            // Get element positions relative to container
            getElementPosition(selector) {
                const element = document.querySelector(selector);
                if (!element) return null;
                
                const containerRect = this.container.getBoundingClientRect();
                const elementRect = element.getBoundingClientRect();
                
                return {
                    x: elementRect.left - containerRect.left + elementRect.width / 2,
                    y: elementRect.top - containerRect.top + elementRect.height / 2
                };
            }

            initializeConnectionPaths() {
                const pathData = [
                    // Data sources to chrono engine
                    { from: '.source-item[data-type="news"]', to: '.engine-core', color: '#125259' },
                    { from: '.source-item[data-type="satellite"]', to: '.engine-core', color: '#125259' },
                    { from: '.source-item[data-type="social"]', to: '.engine-core', color: '#125259' },
                    // Market sources to Market Loom only
                    { from: '.source-item[data-type="stocks"]', to: '.loom-core', color: '#69B7BF' },
                    { from: '.source-item[data-type="crypto"]', to: '.loom-core', color: '#69B7BF' },
                    { from: '.source-item[data-type="forex"]', to: '.loom-core', color: '#69B7BF' },
                    { from: '.source-item[data-type="options"]', to: '.loom-core', color: '#69B7BF' },
                    // Engine to Dashboard
                    { from: '.engine-core', to: '.dashboard-screen', color: '#125259' },
                    // Loom to Dashboard
                    { from: '.loom-core', to: '.dashboard-screen', color: '#69B7BF' }
                ];

                const paths = this.svg.append('g').attr('class', 'connection-paths');

                pathData.forEach((path, i) => {
                    const fromPos = this.getElementPosition(path.from);
                    const toPos = this.getElementPosition(path.to);

                    if (fromPos && toPos) {
                        const pathGenerator = d3.line()
                            .x(d => d.x)
                            .y(d => d.y)
                            .curve(d3.curveBasis);

                        const midX = (fromPos.x + toPos.x) / 2;
                        const midY = (fromPos.y + toPos.y) / 2 + 20;

                        const pathElement = paths.append('path')
                            .datum([fromPos, { x: midX, y: midY }, toPos])
                            .attr('class', 'connection-path')
                            .attr('d', pathGenerator)
                            .attr('stroke', path.color)
                            .attr('stroke-dasharray', function() {
                                return this.getTotalLength();
                            })
                            .attr('stroke-dashoffset', function() {
                                return this.getTotalLength();
                            });

                        // Animate path drawing
                        pathElement.transition()
                            .duration(2000)
                            .delay(i * 200)
                            .attr('stroke-dashoffset', 0);

                        this.connectionPaths.push({
                            element: pathElement,
                            from: fromPos,
                            to: toPos,
                            color: path.color,
                            path: [fromPos, { x: midX, y: midY }, toPos]
                        });
                    }
                });

                // Add bidirectional communication between Chrono Engine and Market Loom
                setTimeout(() => this.initializeBidirectionalCommunication(), 2000);
            }

            initializeBidirectionalCommunication() {
                const enginePos = this.getElementPosition('.engine-core');
                const loomPos = this.getElementPosition('.loom-core');

                if (enginePos && loomPos) {
                    // Create bidirectional group at the top level
                    const bidirectionalGroup = this.svg.append('g')
                        .attr('class', 'bidirectional-comm')
                        .style('z-index', 100);

                    // Create gradient for the path
                    const gradient = this.svg.append('defs')
                        .append('linearGradient')
                        .attr('id', 'bidirectional-gradient')
                        .attr('x1', '0%')
                        .attr('y1', '0%')
                        .attr('x2', '0%')
                        .attr('y2', '100%');

                    gradient.append('stop')
                        .attr('offset', '0%')
                        .attr('stop-color', '#125259')
                        .attr('stop-opacity', 1);

                    gradient.append('stop')
                        .attr('offset', '50%')
                        .attr('stop-color', '#408b94')
                        .attr('stop-opacity', 1);

                    gradient.append('stop')
                        .attr('offset', '100%')
                        .attr('stop-color', '#69B7BF')
                        .attr('stop-opacity', 1);

                    // Create the main communication path
                    const pathGenerator = d3.line()
                        .x(d => d.x)
                        .y(d => d.y)
                        .curve(d3.curveBasis);

                    // Calculate control points for a visible curve
                    const engineBottom = enginePos.y + 130;
                    const loomTop = loomPos.y - 130;
                    const gap = loomTop - engineBottom;
                    const midY = engineBottom + gap / 2;

                    // Simple curved path that avoids overlapping with components
                    const commPath = [
                        { x: enginePos.x + 20, y: engineBottom },     // Slightly offset from center
                        { x: enginePos.x + 150, y: engineBottom + 30 }, // Curve out
                        { x: loomPos.x + 150, y: loomTop - 30 },      // Continue curve
                        { x: loomPos.x + 20, y: loomTop }             // Back to loom
                    ];

                    // Draw the bidirectional path with glow effect
                    const glowPath = bidirectionalGroup.append('path')
                        .datum(commPath)
                        .attr('d', pathGenerator)
                        .attr('stroke', 'url(#bidirectional-gradient)')
                        .attr('stroke-width', 8)
                        .attr('fill', 'none')
                        .style('opacity', 0)
                        .style('filter', 'blur(3px)');

                    const bidirectionalPath = bidirectionalGroup.append('path')
                        .datum(commPath)
                        .attr('class', 'bidirectional-path')
                        .attr('d', pathGenerator)
                        .attr('stroke', 'url(#bidirectional-gradient)')
                        .attr('stroke-width', 4)
                        .attr('fill', 'none')
                        .style('opacity', 0);

                    // Animate path appearance
                    glowPath.transition()
                        .duration(1500)
                        .delay(3000)
                        .style('opacity', 0.4);

                    bidirectionalPath.transition()
                        .duration(1500)
                        .delay(3000)
                        .style('opacity', 0.9);

                    // Store path info for particle animation
                    this.bidirectionalPath = {
                        element: bidirectionalPath,
                        glowElement: glowPath,
                        path: commPath,
                        pathString: pathGenerator(commPath),
                        group: bidirectionalGroup
                    };

                    // Start bidirectional particle animation after paths are drawn
                    setTimeout(() => this.animateBidirectionalFlow(), 5000);
                }
            }

            animateBidirectionalFlow() {
                if (!this.bidirectionalPath) return;

                const createBidirectionalParticle = (direction) => {
                    const particleClass = direction === 'up' ? 'comm-particle-up' : 'comm-particle-down';
                    const path = this.bidirectionalPath.path;
                    const startY = direction === 'up' ? path[path.length - 1].y : path[0].y;
                    const startX = direction === 'up' ? path[path.length - 1].x : path[0].x;

                    const particle = this.bidirectionalPath.group.append('circle')
                        .attr('class', particleClass)
                        .attr('r', 7)
                        .attr('cx', startX)
                        .attr('cy', startY)
                        .style('opacity', 0);

                    const pathElement = this.svg.append('path')
                        .attr('d', this.bidirectionalPath.pathString)
                        .style('display', 'none');

                    const pathLength = pathElement.node().getTotalLength();

                    particle.transition()
                        .duration(2500)
                        .ease(d3.easeLinear)
                        .attrTween('transform', () => {
                            return (t) => {
                                const adjustedT = direction === 'up' ? (1 - t) : t;
                                const point = pathElement.node().getPointAtLength(adjustedT * pathLength);
                                return `translate(${point.x - startX}, ${point.y - startY})`;
                            };
                        })
                        .style('opacity', d3.scaleLinear().domain([0, 0.1, 0.9, 1]).range([0, 1, 1, 0]))
                        .on('end', () => {
                            particle.remove();
                            pathElement.remove();
                        });
                };

                // Create particles going both directions
                const bidirectionalFlow = () => {
                    createBidirectionalParticle('up');
                    setTimeout(() => createBidirectionalParticle('down'), 1000);
                };

                // Initial flow
                bidirectionalFlow();
                
                // Continuous flow
                this.bidirectionalInterval = setInterval(bidirectionalFlow, 3000);
            }

            initializeSwarm() {
                const swarmSvg = d3.select('#swarm-svg');
                const centerX = 90;
                const centerY = 90;
                const nodeCount = 8;

                // Create swarm nodes
                const nodes = d3.range(nodeCount).map((d, i) => {
                    const angle = (i / nodeCount) * Math.PI * 2;
                    const radius = 50 + (i % 3) * 10;
                    return {
                        id: i,
                        x: centerX + Math.cos(angle) * radius,
                        y: centerY + Math.sin(angle) * radius,
                        radius: 8,
                        angle: angle,
                        orbitRadius: radius
                    };
                });

                this.swarmNodes = nodes;

                // Create connections between nodes
                const links = [];
                nodes.forEach((node, i) => {
                    // Connect to next 2 nodes
                    for (let j = 1; j <= 2; j++) {
                        const targetIndex = (i + j) % nodeCount;
                        links.push({
                            source: node,
                            target: nodes[targetIndex]
                        });
                    }
                });

                // Draw connections
                const linkGroup = swarmSvg.append('g').attr('class', 'swarm-links');
                
                linkGroup.selectAll('.bee-connection')
                    .data(links)
                    .enter()
                    .append('line')
                    .attr('class', 'bee-connection')
                    .attr('x1', d => d.source.x)
                    .attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x)
                    .attr('y2', d => d.target.y)
                    .style('opacity', 0)
                    .transition()
                    .duration(1000)
                    .delay((d, i) => i * 50)
                    .style('opacity', 0.5);

                // Draw nodes
                const nodeGroup = swarmSvg.append('g').attr('class', 'swarm-nodes');
                
                const nodeElements = nodeGroup.selectAll('.bee-node')
                    .data(nodes)
                    .enter()
                    .append('g')
                    .attr('class', 'bee-node')
                    .attr('transform', d => `translate(${d.x}, ${d.y})`);

                nodeElements.append('circle')
                    .attr('r', 0)
                    .attr('fill', '#69B7BF')
                    .attr('filter', 'drop-shadow(0 0 8px #69B7BF)')
                    .transition()
                    .duration(800)
                    .delay((d, i) => i * 100)
                    .attr('r', d => d.radius);

                nodeElements.append('circle')
                    .attr('r', 0)
                    .attr('fill', '#fff')
                    .transition()
                    .duration(800)
                    .delay((d, i) => i * 100 + 200)
                    .attr('r', 4);

                // Animate swarm rotation
                this.animateSwarm(nodeElements, linkGroup, nodes, links, centerX, centerY);
            }

            animateSwarm(nodeElements, linkGroup, nodes, links, centerX, centerY) {
                const animate = () => {
                    nodes.forEach((node, i) => {
                        node.angle += 0.003 * (1 + (i % 3) * 0.2);
                        node.x = centerX + Math.cos(node.angle) * node.orbitRadius;
                        node.y = centerY + Math.sin(node.angle) * node.orbitRadius;
                    });

                    nodeElements
                        .attr('transform', d => `translate(${d.x}, ${d.y})`);

                    linkGroup.selectAll('.bee-connection')
                        .attr('x1', d => d.source.x)
                        .attr('y1', d => d.source.y)
                        .attr('x2', d => d.target.x)
                        .attr('y2', d => d.target.y);

                    if (this.animationRunning) {
                        requestAnimationFrame(animate);
                    }
                };

                this.animationRunning = true;
                animate();
            }

            startParticleFlow() {
                const createParticle = (pathData) => {
                    const particle = this.svg.append('circle')
                        .attr('class', 'particle')
                        .attr('r', 3)
                        .attr('cx', pathData.from.x)
                        .attr('cy', pathData.from.y);

                    const pathGenerator = d3.line()
                        .x(d => d.x)
                        .y(d => d.y)
                        .curve(d3.curveBasis);

                    const path = pathGenerator(pathData.path);
                    const pathElement = this.svg.append('path')
                        .attr('d', path)
                        .style('display', 'none');

                    const pathLength = pathElement.node().getTotalLength();

                    particle.transition()
                        .duration(2000)
                        .ease(d3.easeLinear)
                        .attrTween('transform', () => {
                            return (t) => {
                                const point = pathElement.node().getPointAtLength(t * pathLength);
                                return `translate(${point.x - pathData.from.x}, ${point.y - pathData.from.y})`;
                            };
                        })
                        .style('opacity', d3.scaleLinear().domain([0, 0.8, 1]).range([1, 1, 0]))
                        .on('end', () => {
                            particle.remove();
                            pathElement.remove();
                        });
                };

                // Create particles for each connection path
                const flowData = () => {
                    this.connectionPaths.forEach((pathData, i) => {
                        setTimeout(() => createParticle(pathData), i * 200);
                    });
                };

                // Initial flow
                flowData();
                
                // Continuous flow
                this.particleInterval = setInterval(flowData, 3000);
            }

            animateOutputs() {
                const outputs = d3.selectAll('.output');
                
                const pulseAnimation = () => {
                    outputs
                        .style('opacity', 0)
                        .transition()
                        .duration(600)
                        .delay((d, i) => i * 200)
                        .style('opacity', 1)
                        .style('transform', 'scale(1.1)')
                        .transition()
                        .duration(400)
                        .style('transform', 'scale(1)');
                };

                pulseAnimation();
                this.outputInterval = setInterval(pulseAnimation, 3000);
            }

            animateStreamData() {
                const streams = d3.selectAll('.stream');
                
                streams.each(function(d, i) {
                    const stream = d3.select(this);
                    const animate = () => {
                        stream
                            .style('transform', 'scaleY(0.8)')
                            .style('opacity', 0.6)
                            .transition()
                            .duration(1000)
                            .delay(i * 250)
                            .style('transform', 'scaleY(1)')
                            .style('opacity', 1)
                            .transition()
                            .duration(1000)
                            .style('transform', 'scaleY(0.8)')
                            .style('opacity', 0.6);
                    };
                    
                    animate();
                    setInterval(animate, 2000);
                });
            }

            animateTimeline() {
                const progress = d3.select('.timeline-progress');
                
                progress
                    .style('width', '0%')
                    .transition()
                    .duration(3000)
                    .delay(1500)
                    .style('width', '100%');
            }

            destroy() {
                this.animationRunning = false;
                if (this.particleInterval) clearInterval(this.particleInterval);
                if (this.outputInterval) clearInterval(this.outputInterval);
                if (this.bidirectionalInterval) clearInterval(this.bidirectionalInterval);
            }
        }

        // Initialize Engine Animation when Speed section is visible
        let engineAnimation = null;
        const speedSection = document.getElementById('speed');
        const engineObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting && !entry.target.classList.contains('animated')) {
                    entry.target.classList.add('animated');
                    
                    // Animate component appearances
                    const timeline = [
                        { selector: '.source-item', delay: 100 },
                        { selector: '.engine-core', delay: 500 },
                        { selector: '.truth-engine', delay: 1000 },
                        { selector: '.loom-core', delay: 700 },
                        { selector: '.dashboard-screen', delay: 1200 },
                        { selector: '.output', delay: 2000 },
                        { selector: '.explanation-card', delay: 2200 }
                    ];

                    timeline.forEach(item => {
                        d3.selectAll(item.selector)
                            .style('opacity', 0)
                            .transition()
                            .duration(800)
                            .delay((d, i) => item.delay + i * 150)
                            .style('opacity', 1)
                            .style('transform', 'translateY(0) scale(1)');
                    });

                    // Initialize D3 animations
                    setTimeout(() => {
                        engineAnimation = new VortexEngineAnimation();
                        engineAnimation.startParticleFlow();
                        engineAnimation.animateOutputs();
                        engineAnimation.animateStreamData();
                        engineAnimation.animateTimeline();
                    }, 1000);
                }
            });
        }, { threshold: 0.3 });

        if (speedSection) {
            engineObserver.observe(speedSection);
        }

        // Stats Counter Animation with D3
        const animateStats = () => {
            const statNumbers = document.querySelectorAll('.stat-number');

            statNumbers.forEach((element, index) => {
                const target = parseFloat(element.getAttribute('data-target'));
                const isLanguageCount = element.getAttribute('data-target') === "11";
                const isPercentage = element.getAttribute('data-target') === "95.0";
                const selection = d3.select(element);
                const interpolator = d3.interpolateNumber(0, target);

                selection
                    .transition()
                    .duration(2500)
                    .delay(index * 200)
                    .tween('text', function() {
                        return function(t) {
                            const value = interpolator(t);
                            if (isPercentage) {
                                this.textContent = value.toFixed(2) + '%';
                            } else if (target === 10000) {
                                this.textContent = Math.floor(value).toLocaleString() + (t === 1 ? '+' : '');
                            } else if (isLanguageCount) {
                                this.textContent = Math.floor(value);
                            } else {
                                this.textContent = Math.floor(value).toLocaleString();
                            }
                        };
                    });
            });
        };


        // Trigger stats animation when visible
        const statsSection = document.getElementById('stats');
        const statsObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    animateStats();
                    statsObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.5 });

        if (statsSection) {
            statsObserver.observe(statsSection);
        }

        // Contact form handling
        const contactForm = document.getElementById('contact-form');
        if (contactForm) {
            contactForm.addEventListener('submit', async (e) => {
                e.preventDefault();
                const formData = new FormData(contactForm);
                const button = contactForm.querySelector('button[type="submit"]');
                const originalText = button.innerHTML;
                
                try {
                    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
                    button.disabled = true;
                    
                    // Simulate form submission
                    await new Promise(resolve => setTimeout(resolve, 2000));
                    
                    button.innerHTML = '<i class="fas fa-check"></i> Message Sent!';
                    contactForm.reset();
                    
                    setTimeout(() => {
                        button.innerHTML = originalText;
                        button.disabled = false;
                    }, 3000);
                } catch (error) {
                    button.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error. Try again.';
                    button.disabled = false;
                    setTimeout(() => {
                        button.innerHTML = originalText;
                    }, 3000);
                }
            });
        }

        // Mobile menu toggle
        const mobileMenuBtn = document.querySelector('.mobile-menu');
        const navLinks = document.querySelector('.nav-links');
        
        mobileMenuBtn?.addEventListener('click', () => {
            navLinks.style.display = navLinks.style.display === 'flex' ? 'none' : 'flex';
            navLinks.style.position = 'absolute';
            navLinks.style.top = '48px';
            navLinks.style.left = '0';
            navLinks.style.right = '0';
            navLinks.style.background = 'white';
            navLinks.style.flexDirection = 'column';
            navLinks.style.padding = '20px';
            navLinks.style.boxShadow = '0 2px 10px rgba(0,0,0,0.1)';
        });

        // Clean up animations on page unload
        window.addEventListener('beforeunload', () => {
            if (engineAnimation) {
                engineAnimation.destroy();
            }
        });


document.addEventListener('DOMContentLoaded', function() {
    // Observe pricing cards for animation
    const pricingObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
            }
        });
    }, { threshold: 0.1 });

    document.querySelectorAll('.pricing-card, .pricing-trust').forEach(el => {
        pricingObserver.observe(el);
    });

    // Email trigger buttons
    document.querySelectorAll('.email-trigger').forEach(button => {
        button.addEventListener('click', async function() {
            const plan = this.getAttribute('data-plan');
            const originalContent = this.innerHTML;
            
            // Disable button and show loading state
            this.disabled = true;
            this.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Sending...';
            
            try {
                // Simulate sending email (in real implementation, this would be an API call)
                await new Promise(resolve => setTimeout(resolve, 2000));
                
                // Show success state
                this.innerHTML = '<i class="fas fa-check"></i> Sent!';
                
                // Show notification
                showNotification(plan === 'enterprise' ? 
                    'You\'re on the waitlist! We\'ll notify you when Enterprise launches.' : 
                    'Request received! Our team will contact you within 24 hours.');
                
                // Reset button after delay
                setTimeout(() => {
                    this.innerHTML = originalContent;
                    this.disabled = false;
                }, 3000);
                
            } catch (error) {
                // Handle error
                this.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Error. Try again.';
                setTimeout(() => {
                    this.innerHTML = originalContent;
                    this.disabled = false;
                }, 3000);
            }
        });
    });

    // Show notification function
    function showNotification(message) {
        const notification = document.getElementById('pricing-notification');
        const textElement = notification.querySelector('.notification-text');
        textElement.textContent = message;
        
        notification.classList.add('show');
        
        setTimeout(() => {
            notification.classList.remove('show');
        }, 5000);
    }
});