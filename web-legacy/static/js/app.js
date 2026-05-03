'use strict';
/* App bootstrap — panel switching, page loading, theme, global detail panel */

// ---------- Detail panel (global, in index.html) ----------

function showDetail(html) {
  document.getElementById('detail-content').innerHTML = html;
  document.getElementById('detail-panel').classList.add('show');
  renderIcons();
}
function hideDetail() {
  document.getElementById('detail-panel').classList.remove('show');
}

// ---------- Panel switching ----------

async function switchPanel(name, btnEl) {
  State.currentPanel = name;

  document.querySelectorAll('.panel-view').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));

  const panel = document.getElementById('panel-' + name);
  if (panel) panel.classList.add('active');

  const btn = btnEl || document.querySelector(`.nav-item[data-panel="${name}"]`);
  if (btn) btn.classList.add('active');

  // Load page HTML on first visit
  if (!State.pagesLoaded.has(name)) {
    await _loadPage(name);
    // First-time initialization
    if (name === 'events')   await reloadEventFlow();
    if (name === 'graph')    await initRelationGraph();
    if (name === 'summary')  await initSummaryPanel();
    if (name === 'recall')   initRecallPanel();
    if (name === 'settings') { refreshSettingsView(); renderColorPresets(); }
    if (name === 'landing')  _initLanding();
  }

  if (name === 'graph' && State.cy) setTimeout(() => State.cy.fit(), 50);
  if (name === 'events') requestAnimationFrame(drawBridges);
  if (name === 'settings') { refreshSettingsView(); renderColorPresets(); }

  renderIcons();
}

async function _loadPage(name) {
  const panel = document.getElementById('panel-' + name);
  if (!panel) return;
  try {
    const html = await fetch(`/static/pages/${name}.html`).then(r => r.text());
    panel.innerHTML = html;
  } catch (e) {
    panel.innerHTML = `<div class="placeholder error">页面加载失败：${name}</div>`;
  }
  State.pagesLoaded.add(name);
  renderIcons();
}

// ---------- Landing panel init ----------

function _initLanding() {
  refreshStats(); // update stat cards
}

// ---------- Theme ----------

function toggleTheme() {
  const isLight = document.documentElement.getAttribute('data-theme') === 'light';
  if (isLight) {
    document.documentElement.removeAttribute('data-theme');
    localStorage.setItem('em_theme', 'dark');
  } else {
    document.documentElement.setAttribute('data-theme', 'light');
    localStorage.setItem('em_theme', 'light');
  }
}
if (localStorage.getItem('em_theme') === 'light') {
  document.documentElement.setAttribute('data-theme', 'light');
}

// ---------- Boot ----------

async function boot() {
  renderIcons();
  await refreshAuthStatus();

  if (State.authEnabled && !State.authenticated) {
    showLogin(!State.passwordSet);
    return;
  }
  hideLogin();

  // Load modals component once
  await _loadModals();

  // Show landing panel first (fast)
  await switchPanel('landing');
  await refreshStats();

  // Pre-load remaining panels in background
  await Promise.all([
    _loadPage('events'),
    _loadPage('graph'),
    _loadPage('summary'),
    _loadPage('recall'),
    _loadPage('settings'),
  ]);

  // Initialize data for all panels
  await Promise.all([
    reloadEventFlow(),
    initRelationGraph(),
    initSummaryPanel(),
  ]);

  updateSudoUI(0);
  renderIcons();
}

async function _loadModals() {
  try {
    const html = await fetch('/static/components/modals.html').then(r => r.text());
    document.getElementById('modals-container').innerHTML = html;
  } catch {}
  renderIcons();
}

async function reloadAll() {
  await Promise.all([reloadEventFlow(), initRelationGraph(), initSummaryPanel(), refreshStats()]);
  toast('已刷新');
  renderIcons();
}

// ---------- Event bindings ----------

document.getElementById('login-btn').addEventListener('click', handleLoginSubmit);
document.getElementById('login-pw').addEventListener('keypress',  e => e.key === 'Enter' && handleLoginSubmit());
document.getElementById('login-pw2').addEventListener('keypress', e => e.key === 'Enter' && handleLoginSubmit());

// Clicking the logo navigates to landing
document.getElementById('sb-logo-btn').addEventListener('click', () => switchPanel('landing'));

boot();
