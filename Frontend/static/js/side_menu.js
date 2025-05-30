document.addEventListener('DOMContentLoaded', function() {
  // Constants
  const STORAGE_KEYS = {
    SIDEBAR_PINNED: 'vortex_sidebar_pinned',
    SIDEBAR_EXPANDED: 'vortex_sidebar_expanded',
    THEME: 'theme'
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
  let isMobile = window.innerWidth <= 768;
  let isPinned = localStorage.getItem(STORAGE_KEYS.SIDEBAR_PINNED) === 'true';
  let isExpanded = localStorage.getItem(STORAGE_KEYS.SIDEBAR_EXPANDED) === 'true';

  // Initialize sidebar state
  function initializeSidebar() {
    if (!isMobile) {
      // Desktop behavior
      if (isPinned) {
        sidebar.classList.add('pinned');
        body.classList.add('sidebar-pinned');
        pinButton.classList.add('pinned');
        
        if (isExpanded) {
          sidebar.classList.add('expanded');
          body.classList.add('sidebar-expanded');
        }
      }
    } else {
      // Mobile - always start closed
      sidebar.classList.remove('pinned', 'expanded');
      body.classList.remove('sidebar-pinned', 'sidebar-expanded');
    }
  }

  // Toggle sidebar expansion
  function toggleSidebar() {
    if (isMobile) {
      // Mobile behavior - full overlay
      const isOpen = sidebar.classList.contains('mobile-open');
      
      if (isOpen) {
        sidebar.classList.remove('mobile-open');
        overlay.classList.remove('active');
      } else {
        sidebar.classList.add('mobile-open');
        overlay.classList.add('active');
      }
    } else {
      // Desktop behavior
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

  // Pin/unpin sidebar
  function togglePin() {
    isPinned = !isPinned;
    
    if (isPinned) {
      sidebar.classList.add('pinned');
      body.classList.add('sidebar-pinned');
      pinButton.classList.add('pinned');
      
      // If not expanded, expand it when pinning
      if (!sidebar.classList.contains('expanded')) {
        sidebar.classList.add('expanded');
        body.classList.add('sidebar-expanded');
        isExpanded = true;
        localStorage.setItem(STORAGE_KEYS.SIDEBAR_EXPANDED, 'true');
      }
    } else {
      sidebar.classList.remove('pinned', 'expanded');
      body.classList.remove('sidebar-pinned', 'sidebar-expanded');
      pinButton.classList.remove('pinned');
      isExpanded = false;
    }
    
    localStorage.setItem(STORAGE_KEYS.SIDEBAR_PINNED, isPinned);
  }

  // Handle window resize
  function handleResize() {
    const wasMobile = isMobile;
    isMobile = window.innerWidth <= 768;
    
    if (wasMobile !== isMobile) {
      if (isMobile) {
        // Switching to mobile
        sidebar.classList.remove('pinned', 'expanded', 'mobile-open');
        body.classList.remove('sidebar-pinned', 'sidebar-expanded');
        overlay.classList.remove('active');
      } else {
        // Switching to desktop
        initializeSidebar();
      }
    }
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
      sidebar.classList.remove('mobile-open');
      overlay.classList.remove('active');
    }
  }

  // Handle theme toggle
  function toggleTheme() {
    const isDark = body.classList.toggle('dark-theme');
    localStorage.setItem(STORAGE_KEYS.THEME, isDark ? 'dark' : 'light');
    
    // Update icon
    themeIcon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
    
    // Update theme toggle text
    const themeText = themeToggle.querySelector('span');
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
    const isDark = savedTheme === 'dark' || (savedTheme === null && window.matchMedia('(prefers-color-scheme: dark)').matches);
    
    body.classList.toggle('dark-theme', isDark);
    themeIcon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
    
    const themeText = themeToggle.querySelector('span');
    if (themeText) {
      themeText.textContent = isDark ? 'Light theme' : 'Dark theme';
    }
  }

  // Handle feedback button
  function handleFeedback() {
    alert('Funkcja "Feedback" zostanie zaimplementowana w przyszłości.');
  }

  // Event listeners
  if (menuToggle) {
    menuToggle.addEventListener('click', toggleSidebar);
  }

  if (pinButton) {
    pinButton.addEventListener('click', togglePin);
  }

  if (overlay) {
    overlay.addEventListener('click', () => {
      sidebar.classList.remove('mobile-open');
      overlay.classList.remove('active');
    });
  }
  
  // Menu item clicks
  if (sidebar) {
    sidebar.addEventListener('click', handleMenuItemClick);
  }
  
  // Theme toggle
  if (themeToggle) {
    themeToggle.addEventListener('click', toggleTheme);
  }

  // Feedback button
  if (feedbackBtn) {
    feedbackBtn.addEventListener('click', handleFeedback);
  }
  
  // Window resize
  window.addEventListener('resize', handleResize);
  
  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + B to toggle sidebar
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
      e.preventDefault();
      toggleSidebar();
    }
    
    // Ctrl/Cmd + \ to toggle pin
    if ((e.ctrlKey || e.metaKey) && e.key === '\\') {
      e.preventDefault();
      if (!isMobile && sidebar) {
        togglePin();
      }
    }
  });
  
  // Prevent sidebar hover on touch devices
  if ('ontouchstart' in window) {
    sidebar.style.pointerEvents = 'none';
    sidebar.addEventListener('touchstart', () => {
      sidebar.style.pointerEvents = 'auto';
    });
  }
  
  // Initialize
  initializeSidebar();
  initializeTheme();
  
  // Update background effect when theme changes
  if (typeof window.updateThemeColors === 'function') {
    window.updateThemeColors();
  } else {
    // Polling to check if updateThemeColors becomes available
    const checkInterval = setInterval(() => {
      if (typeof window.updateThemeColors === 'function') {
        window.updateThemeColors();
        clearInterval(checkInterval);
      }
    }, 200);
    
    // Stop polling after 5 seconds
    setTimeout(() => clearInterval(checkInterval), 5000);
  }
});
