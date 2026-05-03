'use strict';
/* Settings panel — stats, tasks, demo, color schemes */

async function refreshStats() {
  try {
    const s = await fetchJson('/api/stats');
    const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    setTxt('stat-personas',    `人格 ${s.personas}`);
    setTxt('stat-events',      `事件 ${s.events}`);
    setTxt('stat-impressions', `印象 ${s.impressions}`);
    setTxt('app-version-sb',     s.version);
    setTxt('app-version-badge',  s.version);
    setTxt('app-version-landing', s.version);
    // landing stats
    setTxt('landing-stat-personas',    s.personas);
    setTxt('landing-stat-events',      s.events);
    setTxt('landing-stat-impressions', s.impressions);
    setTxt('landing-stat-groups',      s.groups || 0);
  } catch {}
}

async function refreshSettingsView() {
  const statusEl = document.getElementById('auth-status-line');
  if (statusEl) statusEl.textContent = State.sudo
    ? '已登录 + Sudo' : (State.authenticated ? '已登录（普通模式）' : '未登录');
  try {
    const { panels } = await fetchJson('/api/panels');
    const el = document.getElementById('ext-panels-list');
    if (el) el.innerHTML = panels.length
      ? panels.map(p => `<div style="padding:4px 0"><b>${p.title}</b> — ${p.plugin_id}</div>`).join('')
      : '暂无第三方插件注册面板';
  } catch {}
  renderIcons();
}

async function runTask(name) {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  toast(`触发 ${name}…`);
  try {
    const r = await fetchJson('/api/admin/run_task', { method: 'POST', body: JSON.stringify({ name }) });
    toast(r.ok ? `${name} 已完成` : `${name} 失败`);
    setTimeout(refreshStats, 1500);
  } catch (e) {
    toast(`${name} 错误：${e.body || e.status}`, 4000);
  }
}

async function injectDemo() {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  toast('注入演示数据…');
  try {
    const r = await fetchJson('/api/admin/demo', { method: 'POST' });
    const s = r.seeded || {};
    toast(`注入成功：${s.personas || 0} 人格, ${s.events || 0} 事件, ${s.impressions || 0} 印象`);
    await reloadAll();
  } catch (e) {
    toast('注入失败：' + (e.body || e.status), 4000);
  }
}

/* Color scheme presets */
const COLOR_PRESETS = [
  { id: 'sky',    color: '#38bdf8', label: '天蓝（默认）' },
  { id: 'red',    color: '#ef4444', label: '红色' },
  { id: 'orange', color: '#f97316', label: '橙色' },
  { id: 'green',  color: '#22c55e', label: '绿色' },
  { id: 'purple', color: '#a855f7', label: '紫色' },
  { id: 'zinc',   color: '#71717a', label: '灰色' },
];

function renderColorPresets() {
  const container = document.getElementById('color-presets-container');
  if (!container) return;
  container.innerHTML = COLOR_PRESETS.map(p => `
    <div class="color-preset${State.colorScheme === p.id ? ' active' : ''}"
         style="background:${p.color}"
         title="${p.label}"
         onclick="applyColorScheme('${p.id}')">
    </div>`).join('');
}

function applyColorScheme(scheme) {
  State.colorScheme = scheme;
  document.documentElement.dataset.colorScheme = scheme;
  localStorage.setItem('em_color_scheme', scheme);
  renderColorPresets();
}

// Apply saved color scheme on load
(function () {
  const saved = localStorage.getItem('em_color_scheme');
  if (saved) {
    State.colorScheme = saved;
    document.documentElement.dataset.colorScheme = saved;
  }
})();
