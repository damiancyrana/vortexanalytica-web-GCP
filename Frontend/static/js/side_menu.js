document.addEventListener('DOMContentLoaded', function() {
  // Constants
  const STORAGE_KEYS = {
    SIDEBAR_PINNED: 'vortex_sidebar_pinned',
    SIDEBAR_EXPANDED: 'vortex_sidebar_expanded',
    THEME: 'theme'
  };
  
  const BREAKPOINTS = {
    MOBILE: 768,
    TABLET: 1024
  };

  // Elements
  const sidebar = document.getElementById('sidebar');
  const menuToggle = document.getElementById('menu-toggle');
  const pinButton = document.getElementById('sidebar-pin-btn');
  const overlay = document.getElementById('sidebar-overlay');
  const body = document.body;
  const themeToggle = document.getElementById('sidebar-theme-toggle');
  const themeIcon = document.getElementById('theme-icon');
  const feedbackBtn = document.getElementById('feedback-btn');

  // State
  let isMobile = window.innerWidth < BREAKPOINTS.MOBILE;
  let isTablet = window.innerWidth >= BREAKPOINTS.MOBILE && window.innerWidth < BREAKPOINTS.TABLET;
  let isDesktop = window.innerWidth >= BREAKPOINTS.TABLET;
  let isPinned = false;
  let isExpanded = false;

  // Only load saved states on desktop
  if (isDesktop) {
    isPinned = localStorage.getItem(STORAGE_KEYS.SIDEBAR_PINNED) === 'true';
    isExpanded = localStorage.getItem(STORAGE_KEYS.SIDEBAR_EXPANDED) === 'true';
  }

  // Initialize sidebar state based on device
  function initializeSidebar() {
    if (isMobile) {
      // Mobile: always start closed, no pin functionality
      sidebar.classList.remove('pinned', 'expanded', 'mobile-open');
      body.classList.remove('sidebar-pinned', 'sidebar-expanded');
      overlay.classList.remove('active');
      
      // Ensure mobile menu toggle is visible
      if (menuToggle) {
        menuToggle.style.display = 'flex';
      }
    } else if (isTablet) {
      // Tablet: collapsed by default, can expand on hover or click
      sidebar.classList.remove('pinned', 'mobile-open');
      body.classList.remove('sidebar-pinned', 'sidebar-expanded');
      
      if (isPinned) {
        sidebar.classList.add('pinned');
        body.classList.add('sidebar-pinned');
        pinButton?.classList.add('pinned');
        
        if (isExpanded) {
          sidebar.classList.add('expanded');
          body.classList.add('sidebar-expanded');
        }
      }
    } else {
      // Desktop: restore saved state
      if (isPinned) {
        sidebar.classList.add('pinned');
        body.classList.add('sidebar-pinned');
        pinButton?.classList.add('pinned');
        
        if (isExpanded) {
          sidebar.classList.add('expanded');
          body.classList.add('sidebar-expanded');
        }
      }
      
      // Hide mobile menu toggle on desktop
      if (menuToggle) {
        menuToggle.style.display = 'none';
      }
    }
  }

  // Toggle sidebar for mobile/tablet
  function toggleSidebar() {
    if (isMobile) {
      // Mobile: slide in from left with overlay
      const isOpen = sidebar.classList.contains('mobile-open');
      
      if (isOpen) {
        closeMobileSidebar();
      } else {
        openMobileSidebar();
      }
    } else if (isTablet) {
      // Tablet: expand/collapse behavior
      if (isPinned) {
        isExpanded = !isExpanded;
        
        if (isExpanded) {
          sidebar.classList.add('expanded');
          body.classList.add('sidebar-expanded');
        } else {
          sidebar.classList.remove('expanded');
          body.classList.remove('sidebar-expanded');
        }
        
        localStorage.setItem(STORAGE_KEYS.SIDEBAR_EXPANDED, isExpanded);
      } else {
        // If not pinned, just toggle expansion temporarily
        sidebar.classList.toggle('expanded');
      }
    } else {
      // Desktop: toggle expansion if pinned
      if (isPinned) {
        isExpanded = !isExpanded;
        
        if (isExpanded) {
          sidebar.classList.add('expanded');
          body.classList.add('sidebar-expanded');
        } else {
          sidebar.classList.remove('expanded');
          body.classList.remove('sidebar-expanded');
        }
        
        localStorage.setItem(STORAGE_KEYS.SIDEBAR_EXPANDED, isExpanded);
      }
    }
  }

  // Open mobile sidebar
  function openMobileSidebar() {
    sidebar.classList.add('mobile-open');
    overlay.classList.add('active');
    body.style.overflow = 'hidden'; // Prevent body scroll
    
    // Add touch event to close on swipe
    let touchStartX = 0;
    let touchEndX = 0;
    
    const handleTouchStart = (e) => {
      touchStartX = e.changedTouches[0].screenX;
    };
    
    const handleTouchEnd = (e) => {
      touchEndX = e.changedTouches[0].screenX;
      handleSwipe();
    };
    
    const handleSwipe = () => {
      if (touchStartX - touchEndX > 50) { // Swipe left
        closeMobileSidebar();
        sidebar.removeEventListener('touchstart', handleTouchStart);
        sidebar.removeEventListener('touchend', handleTouchEnd);
      }
    };
    
    sidebar.addEventListener('touchstart', handleTouchStart);
    sidebar.addEventListener('touchend', handleTouchEnd);
  }

  // Close mobile sidebar
  function closeMobileSidebar() {
    sidebar.classList.remove('mobile-open');
    overlay.classList.remove('active');
    body.style.overflow = ''; // Restore body scroll
  }

  // Pin/unpin sidebar (tablet/desktop only)
  function togglePin() {
    if (isMobile) return; // No pin functionality on mobile
    
    isPinned = !isPinned;
    
    if (isPinned) {
      sidebar.classList.add('pinned');
      body.classList.add('sidebar-pinned');
      pinButton?.classList.add('pinned');
      
      // Auto-expand when pinning
      if (!sidebar.classList.contains('expanded')) {
        sidebar.classList.add('expanded');
        body.classList.add('sidebar-expanded');
        isExpanded = true;
        localStorage.setItem(STORAGE_KEYS.SIDEBAR_EXPANDED, 'true');
      }
    } else {
      sidebar.classList.remove('pinned', 'expanded');
      body.classList.remove('sidebar-pinned', 'sidebar-expanded');
      pinButton?.classList.remove('pinned');
      isExpanded = false;
    }
    
    localStorage.setItem(STORAGE_KEYS.SIDEBAR_PINNED, isPinned);
  }

  // Handle window resize with debouncing
  let resizeTimeout;
  function handleResize() {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
      const wasMobile = isMobile;
      const wasTablet = isTablet;
      
      isMobile = window.innerWidth < BREAKPOINTS.MOBILE;
      isTablet = window.innerWidth >= BREAKPOINTS.MOBILE && window.innerWidth < BREAKPOINTS.TABLET;
      isDesktop = window.innerWidth >= BREAKPOINTS.TABLET;
      
      // Only reinitialize if breakpoint changed
      if (wasMobile !== isMobile || wasTablet !== isTablet) {
        // Close mobile sidebar if open
        if (sidebar.classList.contains('mobile-open')) {
          closeMobileSidebar();
        }
        
        // Reinitialize for new breakpoint
        initializeSidebar();
      }
    }, 250);
  }

  // Handle menu item clicks
  function handleMenuItemClick(event) {
    const link = event.target.closest('a');
    if (!link) return;
    
    event.preventDefault();
    
    // Update active state
    document.querySelectorAll('.sidebar-menu a').forEach(item => {
      item.classList.remove('active');
    });
    link.classList.add('active');
    
    // Handle view switching
    const view = link.dataset.view;
    if (view) {
      // Hide all view sections
      document.querySelectorAll('.view-section').forEach(section => {
        section.style.display = 'none';
        section.classList.remove('active');
      });
      
      // Show the selected view
      const targetView = document.getElementById(`${view}-view`);
      if (targetView) {
        targetView.style.display = 'flex';
        targetView.classList.add('active');
        
        // Special handling for specific views
        if (view === 'overview') {
          targetView.style.flexDirection = 'column';
        }
      }
      
      // Update navigation buttons if they exist
      document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.view === view) {
          btn.classList.add('active');
        }
      });
    }
    
    // Close sidebar on mobile after selection
    if (isMobile) {
      setTimeout(() => {
        closeMobileSidebar();
      }, 150);
    }
  }

  // Handle theme toggle
  function toggleTheme() {
    const isDark = body.classList.toggle('dark-theme');
    localStorage.setItem(STORAGE_KEYS.THEME, isDark ? 'dark' : 'light');
    
    // Update icon
    if (themeIcon) {
      themeIcon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
    }
    
    // Update theme toggle text
    const themeText = themeToggle?.querySelector('span');
    if (themeText) {
      themeText.textContent = isDark ? 'Light theme' : 'Dark theme';
    }
    
    // Update footer theme toggle if exists
    const footerThemeBtn = document.getElementById('theme-toggle-btn');
    if (footerThemeBtn) {
      const footerIcon = footerThemeBtn.querySelector('i');
      if (footerIcon) {
        footerIcon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
      }
    }
    
    // Call any global theme update functions
    if (typeof window.updateThemeColors === 'function') {
      window.updateThemeColors();
    }
  }

  // Initialize theme
  function initializeTheme() {
    const savedTheme = localStorage.getItem(STORAGE_KEYS.THEME);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const isDark = savedTheme === 'dark' || (savedTheme === null && prefersDark);
    
    body.classList.toggle('dark-theme', isDark);
    
    if (themeIcon) {
      themeIcon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
    }
    
    const themeText = themeToggle?.querySelector('span');
    if (themeText) {
      themeText.textContent = isDark ? 'Light theme' : 'Dark theme';
    }
  }

  // Handle feedback button
  function handleFeedback() {
    if (isMobile) {
      closeMobileSidebar();
    }
    
    // Create a simple modal or redirect
    const message = 'Feedback feature coming soon! For now, please email us at: feedback@vortexanalytica.com';
    
    if (window.confirm(message)) {
      window.location.href = 'mailto:feedback@vortexanalytica.com';
    }
  }

  // Prevent body scroll when mobile menu is open
  function preventBodyScroll(prevent) {
    if (prevent) {
      body.style.overflow = 'hidden';
      body.style.position = 'fixed';
      body.style.width = '100%';
    } else {
      body.style.overflow = '';
      body.style.position = '';
      body.style.width = '';
    }
  }

  // Event listeners
  if (menuToggle) {
    menuToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleSidebar();
    });
  }

  if (pinButton) {
    pinButton.addEventListener('click', (e) => {
      e.stopPropagation();
      togglePin();
    });
  }

  if (overlay) {
    overlay.addEventListener('click', () => {
      closeMobileSidebar();
    });
  }
  
  // Menu item clicks
  if (sidebar) {
    sidebar.addEventListener('click', handleMenuItemClick);
    
    // Prevent sidebar from closing when clicking inside on mobile
    sidebar.addEventListener('click', (e) => {
      if (isMobile && !e.target.closest('a')) {
        e.stopPropagation();
      }
    });
  }
  
  // Theme toggle
  if (themeToggle) {
    themeToggle.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleTheme();
    });
  }

  // Feedback button
  if (feedbackBtn) {
    feedbackBtn.addEventListener('click', handleFeedback);
  }
  
  // Window resize with debouncing
  window.addEventListener('resize', handleResize);
  
  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    // Escape to close mobile sidebar
    if (e.key === 'Escape' && isMobile && sidebar.classList.contains('mobile-open')) {
      closeMobileSidebar();
    }
    
    // Ctrl/Cmd + B to toggle sidebar
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
      e.preventDefault();
      toggleSidebar();
    }
    
    // Ctrl/Cmd + \ to toggle pin (desktop/tablet only)
    if ((e.ctrlKey || e.metaKey) && e.key === '\\' && !isMobile) {
      e.preventDefault();
      togglePin();
    }
  });
  
  // Touch gesture support for mobile
  if ('ontouchstart' in window) {
    let touchStartX = 0;
    
    // Detect edge swipe to open sidebar
    document.addEventListener('touchstart', (e) => {
      touchStartX = e.touches[0].clientX;
    });
    
    document.addEventListener('touchmove', (e) => {
      if (!sidebar.classList.contains('mobile-open') && 
          touchStartX < 20 && 
          e.touches[0].clientX > touchStartX + 50) {
        openMobileSidebar();
      }
    });
  }
  
  // Initialize on load
  initializeSidebar();
  initializeTheme();
  
  // Update background effect when theme changes
  if (typeof window.updateThemeColors === 'function') {
    window.updateThemeColors();
  }
  
  // Focus management for accessibility
  if (sidebar) {
    sidebar.addEventListener('transitionend', () => {
      if (sidebar.classList.contains('mobile-open')) {
        // Focus first menu item when sidebar opens
        const firstLink = sidebar.querySelector('.sidebar-menu a');
        if (firstLink) {
          firstLink.focus();
        }
      }
    });
  }
})