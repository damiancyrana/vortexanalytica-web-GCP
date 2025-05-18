    // Obsługa menu bocznego
    document.addEventListener('DOMContentLoaded', function() {
        const menuToggle = document.getElementById('menu-toggle');
        const sidebar = document.getElementById('sidebar');
        const themeToggleCheckbox = document.getElementById('theme-toggle-checkbox');
        const feedbackBtn = document.getElementById('feedback-btn');
        
        // Ustaw początkowy stan motywu
        if (localStorage.getItem('theme') === 'light') {
          document.body.classList.remove('dark-theme');
          if (themeToggleCheckbox) themeToggleCheckbox.checked = false;
          const themeIcon = document.querySelector('.sidebar-theme-toggle i');
          if (themeIcon) themeIcon.className = 'fas fa-moon';
        }
        
        // Obsługa przycisku hamburger
        menuToggle.addEventListener('click', function() {
          sidebar.classList.toggle('active');
        });
        
        // Zamknij menu po kliknięciu poza nim
        document.addEventListener('click', function(event) {
          if (!sidebar.contains(event.target) && !menuToggle.contains(event.target)) {
            sidebar.classList.remove('active');
          }
        });
        
        // Obsługa przełączania motywu z menu bocznego
        if (themeToggleCheckbox) {
          themeToggleCheckbox.addEventListener('change', function() {
            document.body.classList.toggle('dark-theme');
            const isDark = document.body.classList.contains('dark-theme');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            
            // Zmień ikonę w menu bocznym
            const themeIcon = document.querySelector('.sidebar-theme-toggle i');
            if (themeIcon) {
              themeIcon.className = isDark ? 'fas fa-sun' : 'fas fa-moon';
            }
            
            // Wywołaj funkcję aktualizacji kolorów w tle Three.js
            if (typeof window.updateThemeColors === 'function') {
              window.updateThemeColors();
            }
          });
        }
        
        // Obsługa przycisku Feedback (tylko placeholder zgodnie z wymaganiami)
        if (feedbackBtn) {
          feedbackBtn.addEventListener('click', function() {
            alert('Funkcja "Feedback" zostanie zaimplementowana w przyszłości.');
          });
        }
        
        // Modyfikacja tła w trybie jasnym dla spiralnego efektu
        function updateBackgroundEffect() {
          if (typeof window.updateThemeColors === 'function') {
            // Gdy funkcja jest dostępna, wywołujemy ją przy każdej zmianie motywu
            window.updateThemeColors();
          } else {
            // Polling do sprawdzenia, czy funkcja updateThemeColors stała się dostępna
            const checkInterval = setInterval(() => {
              if (typeof window.updateThemeColors === 'function') {
                window.updateThemeColors();
                clearInterval(checkInterval);
              }
            }, 200);
            
            // Zatrzymaj polling po 5 sekundach, jeśli funkcja nie zostanie znaleziona
            setTimeout(() => clearInterval(checkInterval), 5000);
          }
        }
        
        // Uruchom aktualizację tła przy inicjalizacji
        updateBackgroundEffect();
      });