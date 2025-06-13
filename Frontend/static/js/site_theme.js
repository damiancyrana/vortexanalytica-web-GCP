// Shared theme toggle for landing and login pages
// independent from dashboard theme

document.addEventListener('DOMContentLoaded', () => {
  const KEY = 'va_site_theme';
  const toggleBtn = document.getElementById('themeToggleBtn');

  const applyTheme = () => {
    const saved = localStorage.getItem(KEY);
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = saved || (prefersDark ? 'dark' : 'light');
    document.body.setAttribute('data-theme', theme);
    if (toggleBtn) toggleBtn.textContent = theme === 'dark' ? 'Light mode' : 'Dark mode';
  };

  applyTheme();

  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const current = document.body.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      document.body.setAttribute('data-theme', current);
      localStorage.setItem(KEY, current);
      toggleBtn.textContent = current === 'dark' ? 'Light mode' : 'Dark mode';
    });
  }
});
