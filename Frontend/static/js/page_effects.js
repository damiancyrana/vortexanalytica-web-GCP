// Landing page interactions

// Loader fade out
window.addEventListener('load', () => {
  const loader = document.getElementById('loader');
  if (loader) {
    loader.classList.add('fade');
    setTimeout(() => loader.remove(), 800);
  }
});

// Intersection animations
const observer = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (e.isIntersecting) {
      e.target.classList.add('visible');
      observer.unobserve(e.target);
    }
  }
}, { threshold: 0.2 });

for (const section of document.querySelectorAll('section')) {
  observer.observe(section);
}

// Card tilt
for (const card of document.querySelectorAll('.info-card')) {
  card.addEventListener('mousemove', (ev) => {
    const rect = card.getBoundingClientRect();
    const x = ev.clientX - rect.left - rect.width / 2;
    const y = ev.clientY - rect.top - rect.height / 2;
    card.style.setProperty('--rx', (-y / rect.height * 10).toFixed(2) + 'deg');
    card.style.setProperty('--ry', (x / rect.width * 10).toFixed(2) + 'deg');
  });
  card.addEventListener('mouseleave', () => {
    card.style.setProperty('--rx', '0deg');
    card.style.setProperty('--ry', '0deg');
  });
}

// Ripple buttons
for (const btn of document.querySelectorAll('.btn')) {
  btn.style.position = 'relative';
  btn.style.overflow = 'hidden';
  btn.addEventListener('click', (ev) => {
    const r = document.createElement('span');
    r.className = 'ripple';
    btn.appendChild(r);
    const d = Math.max(btn.clientWidth, btn.clientHeight);
    r.style.width = r.style.height = d + 'px';
    r.style.left = ev.clientX - btn.getBoundingClientRect().left - d/2 + 'px';
    r.style.top = ev.clientY - btn.getBoundingClientRect().top - d/2 + 'px';
    setTimeout(() => r.remove(), 600);
  });
}
