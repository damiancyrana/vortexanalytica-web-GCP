/* contact_form.js – wysyłka AJAX do /contact */

const form   = document.getElementById('contact-form');
const status = document.getElementById('form-status');

if (form && status) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    status.style.display = 'block';
    status.textContent   = 'Sending…';
    status.className     = '';

    try {
      const res  = await fetch('/contact', { method:'POST', body:new FormData(form) });
      const json = await res.json();

      if (json.ok) {
        status.textContent = json.msg;
        status.classList.add('success');
        form.reset();
      } else {
        throw new Error(json.msg ?? 'Unknown error');
      }
    } catch (err) {
      status.textContent = `❌ ${err.message}`;
      status.classList.add('error');
    }
  });
}
