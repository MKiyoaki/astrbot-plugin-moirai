'use strict';
/* Memory Recall Test panel */

function initRecallPanel() {
  const input = document.getElementById('recall-input');
  if (input) input.focus();
}

async function performRecall() {
  const q = (document.getElementById('recall-input')?.value || '').trim();
  if (!q) { toast('请输入查询内容'); return; }
  const limitEl = document.getElementById('recall-limit');
  const limit   = parseInt(limitEl?.value || '5');
  const resultsEl = document.getElementById('recall-results');
  const metaEl    = document.getElementById('recall-meta');
  if (resultsEl) resultsEl.innerHTML = '<div class="placeholder">查询中…</div>';

  try {
    const data = await fetchJson(`/api/recall?q=${encodeURIComponent(q)}&limit=${limit}`);
    if (metaEl) {
      metaEl.innerHTML = `
        <span>找到 <b>${data.count}</b> 条</span>
        <span class="recall-algo">${data.algorithm || 'fts5'}</span>`;
    }
    renderRecallResults(data.items || []);
  } catch (e) {
    if (resultsEl) resultsEl.innerHTML = '<div class="placeholder error">查询失败：' + (e.body || e.status) + '</div>';
  }
}

function renderRecallResults(items) {
  const el = document.getElementById('recall-results');
  if (!el) return;
  if (!items.length) {
    el.innerHTML = '<div class="placeholder">无匹配结果</div>';
    return;
  }
  el.innerHTML = items.map(ev => `
    <div class="recall-item" onclick="showEventDetail('${ev.id}'); switchPanel('events')">
      <div class="recall-item-title">${_escR(ev.content || ev.topic || ev.id)}</div>
      <div class="recall-item-meta">
        <span>${new Date(ev.start).toLocaleDateString('zh-CN')}</span>
        <span>${_escR(ev.group || '私聊')}</span>
        <span>重要度 ${(ev.salience * 100).toFixed(0)}%</span>
        ${(ev.tags || []).slice(0, 2).map(t => `<span class="tl-badge tag">${_escR(t)}</span>`).join('')}
      </div>
    </div>`).join('');
  renderIcons();
}

function _escR(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
