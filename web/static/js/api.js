'use strict';
/* Shared fetch helper and API wrappers */

const $ = sel => document.querySelector(sel);

async function fetchJson(url, opts = {}) {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) {
    const raw = await res.text();
    let detail = raw;
    try { const j = JSON.parse(raw); detail = j.error || raw; } catch {}
    throw { status: res.status, body: detail, raw };
  }
  return res.json();
}

/* Render Lucide icons — must be called after any dynamic DOM insertion */
function renderIcons() {
  if (window.lucide) window.lucide.createIcons();
}

/* Toast notification */
function toast(msg, ms = 2800) {
  const t = $('#toast');
  if (!t) return;
  t.textContent = msg;
  t.style.display = 'block';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => (t.style.display = 'none'), ms);
}

/* Modal helpers */
function openModal(id) {
  const el = document.getElementById(id);
  if (el) { el.style.display = 'flex'; renderIcons(); }
}
function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

/* Close modal on backdrop click */
document.addEventListener('click', e => {
  if (e.target.classList.contains('modal-overlay')) closeModal(e.target.id);
});
/* Close modal on Escape */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay[style*="flex"]').forEach(m => {
      m.style.display = 'none';
    });
  }
});
