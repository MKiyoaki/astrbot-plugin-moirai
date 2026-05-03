'use strict';
/* Event Flow — timeline rendering, CRUD, search/filter, recycle bin */

// ---------- Data loading ----------

async function reloadEventFlow() {
  let data;
  try {
    data = await fetchJson('/api/events?limit=500');
  } catch {
    const c = document.getElementById('tl-container');
    if (c) c.innerHTML = '<div class="tl-empty error">事件流加载失败</div>';
    return;
  }
  State.rawEvents = data.items || [];
  _applyEventsView();
}

// ---------- View toggle ----------

function setEventsView(view) {
  State.eventsView = view;
  const btnTL   = document.getElementById('btn-events-timeline-view');
  const btnList = document.getElementById('btn-events-list-view');
  if (btnTL)   btnTL.classList.toggle('active',   view === 'timeline');
  if (btnList) btnList.classList.toggle('active', view === 'list');

  const tlScroll = document.getElementById('tl-scroll');
  const listView = document.getElementById('events-list-view');
  if (tlScroll) tlScroll.style.display = view === 'timeline' ? '' : 'none';
  if (listView) listView.style.display = view === 'list'     ? '' : 'none';

  if (view === 'list') renderEventsList();
  else {
    const density = parseInt(document.getElementById('event-density')?.value || '200');
    renderTimeline(density);
  }
}

function _applyEventsView() {
  if (State.eventsView === 'list') renderEventsList();
  else {
    const density = parseInt(document.getElementById('event-density')?.value || '200');
    renderTimeline(density);
  }
}

// ---------- Search / filter ----------

function filterEvents(query) {
  State.eventsFilter = (query || '').toLowerCase();
  _applyEventsView();
}

function _filteredEvents() {
  const q = State.eventsFilter;
  if (!q) return State.rawEvents;
  return State.rawEvents.filter(ev =>
    (ev.content || '').toLowerCase().includes(q) ||
    (ev.topic   || '').toLowerCase().includes(q) ||
    (ev.group   || '').toLowerCase().includes(q) ||
    (ev.tags    || []).some(t => t.toLowerCase().includes(q)) ||
    (ev.participants || []).some(p => p.toLowerCase().includes(q))
  );
}

// ---------- Timeline rendering ----------

function renderTimeline(maxCount) {
  const container = document.getElementById('tl-container');
  if (!container) return;

  const sorted = [..._filteredEvents()]
    .sort((a, b) => b.salience - a.salience)
    .slice(0, maxCount)
    .sort((a, b) => new Date(a.start) - new Date(b.start));

  container.innerHTML = '';
  if (!sorted.length) {
    container.innerHTML = '<div class="tl-empty">暂无事件数据<br><small>在设置 → 演示数据 中注入模拟数据可预览效果</small></div>';
    return;
  }

  sorted.forEach((ev, i) => {
    const side = i % 2 === 0 ? 'left' : 'right';
    const hasParent = ev.inherit_from && ev.inherit_from.length > 0;
    const timeStr = new Date(ev.start).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    const tagsHtml = (ev.tags || []).slice(0, 3).map(t => `<span class="tl-badge tag">${_esc(t)}</span>`).join('');

    const item = document.createElement('div');
    item.className = `tl-item ${side}`;
    item.dataset.eventId = ev.id;
    item.innerHTML = `
      <div class="tl-dot${hasParent ? ' has-parent' : ''}" data-event-id="${ev.id}" onclick="showEventDetail('${ev.id}')"></div>
      <div class="tl-card" onclick="showEventDetail('${ev.id}')">
        <div class="tl-card-header">
          <div class="tl-card-title-wrap">
            <div class="tl-card-title">${_esc(ev.content)}</div>
            <div class="tl-card-time">${timeStr}</div>
          </div>
          <div class="tl-card-actions" onclick="event.stopPropagation()">
            <button class="btn btn-ghost btn-sm btn-icon" onclick="showEditEventModal('${ev.id}')" title="编辑">
              <i data-lucide="pencil"></i>
            </button>
            <button class="btn btn-danger btn-sm btn-icon" onclick="deleteEvent('${ev.id}')" title="删除">
              <i data-lucide="trash-2"></i>
            </button>
          </div>
        </div>
        <div class="tl-card-body">
          <span class="tl-badge salience">${(ev.salience * 100).toFixed(0)}%</span>
          ${ev.group ? `<span class="tl-badge group">${_esc(ev.group.slice(0, 12))}</span>` : '<span class="tl-badge group">私聊</span>'}
          ${(ev.participants || []).length ? `<span class="tl-badge participants">${ev.participants.length} 人</span>` : ''}
          ${tagsHtml}
        </div>
      </div>`;
    container.appendChild(item);
  });

  requestAnimationFrame(drawBridges);
  renderIcons();
}

// ---------- Bridge lines ----------

function drawBridges() {
  const container = document.getElementById('tl-container');
  if (!container) return;
  container.querySelectorAll('.tl-bridge').forEach(b => b.remove());

  State.rawEvents.forEach(ev => {
    if (!ev.inherit_from || !ev.inherit_from.length) return;
    ev.inherit_from.forEach(parentId => {
      const parentDot = container.querySelector(`.tl-dot[data-event-id="${parentId}"]`);
      const childDot  = container.querySelector(`.tl-dot[data-event-id="${ev.id}"]`);
      if (!parentDot || !childDot) return;
      const parentItem = parentDot.closest('.tl-item');
      const childItem  = childDot.closest('.tl-item');
      if (!parentItem || !childItem) return;

      const parentY = parentItem.offsetTop + parentDot.offsetTop + parentDot.offsetHeight / 2;
      const childY  = childItem.offsetTop  + childDot.offsetTop  + childDot.offsetHeight  / 2;
      const top = Math.min(parentY, childY);
      const height = Math.abs(childY - parentY);
      if (height < 4) return;

      const parentEv = State.rawEvents.find(e => e.id === parentId);
      const bridge = document.createElement('div');
      bridge.className = 'tl-bridge';
      bridge.style.top    = top + 'px';
      bridge.style.height = height + 'px';
      bridge.dataset.from = parentId;
      bridge.dataset.to   = ev.id;
      bridge.addEventListener('mouseenter', e => showBridgePopup(e, parentEv, ev));
      bridge.addEventListener('mouseleave', hideBridgePopup);
      container.appendChild(bridge);
    });
  });
}

// Bridge hover popup
function showBridgePopup(mouseEvt, parentEv, childEv) {
  const popup = document.getElementById('bridge-popup');
  if (!popup) return;
  popup.innerHTML = `
    <div class="bp-label">承接关系</div>
    <div class="bp-row"><div class="bp-dot"></div><div class="bp-text">父：${_esc(parentEv ? parentEv.content : '未知')}</div></div>
    <div class="bp-row"><div class="bp-dot" style="background:#f97316"></div><div class="bp-text">子：${_esc(childEv.content)}</div></div>`;
  popup.style.left = (mouseEvt.clientX + 12) + 'px';
  popup.style.top  = (mouseEvt.clientY - 12) + 'px';
  popup.classList.add('show');
}
function hideBridgePopup() {
  const popup = document.getElementById('bridge-popup');
  if (popup) popup.classList.remove('show');
}

if (typeof ResizeObserver !== 'undefined') {
  const _roTarget = () => document.getElementById('tl-container');
  const _ro = new ResizeObserver(() => {
    if (State.currentPanel === 'events') drawBridges();
  });
  // Attach after DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    const t = _roTarget();
    if (t) _ro.observe(t);
  });
}

// ---------- Highlight ----------

function highlightEvents(eventIds) {
  const idSet = new Set(eventIds);
  document.querySelectorAll('.tl-dot').forEach(dot => {
    dot.classList.toggle('highlighted', idSet.has(dot.dataset.eventId));
  });
  document.querySelectorAll('.tl-item').forEach(item => {
    const card = item.querySelector('.tl-card');
    const dot  = item.querySelector('.tl-dot');
    if (card && dot) card.classList.toggle('highlighted', idSet.has(dot.dataset.eventId));
  });
  if (eventIds.length) {
    const first = document.querySelector(`.tl-dot[data-event-id="${eventIds[0]}"]`);
    if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

// ---------- Detail panel ----------

function showEventDetail(eventId) {
  const ev = State.rawEvents.find(e => e.id === eventId);
  if (!ev) return;
  const html = `
    <h3><i data-lucide="calendar-days" class="detail-title-icon"></i>事件详情</h3>
    <div class="detail-field"><span class="k">话题</span><span class="v">${_esc(ev.content)}</span></div>
    <div class="detail-field"><span class="k">ID</span><span class="v">${ev.id.slice(0, 12)}…</span></div>
    <div class="detail-field"><span class="k">群组</span><span class="v">${_esc(ev.group || '私聊')}</span></div>
    <div class="detail-field"><span class="k">起始</span><span class="v">${new Date(ev.start).toLocaleString()}</span></div>
    <div class="detail-field"><span class="k">结束</span><span class="v">${new Date(ev.end).toLocaleString()}</span></div>
    <div class="detail-field"><span class="k">重要度</span><span class="v">${(ev.salience * 100).toFixed(0)}%</span></div>
    <div class="detail-field"><span class="k">置信度</span><span class="v">${(ev.confidence * 100).toFixed(0)}%</span></div>
    <div class="detail-field"><span class="k">参与者</span><span class="v">${(ev.participants || []).map(p => _esc(p.slice(0, 10))).join(', ') || '—'}</span></div>
    ${(ev.inherit_from || []).length ? `<div class="detail-field"><span class="k">承接自</span><span class="v">${ev.inherit_from.map(id => id.slice(0, 8)).join(', ')}</span></div>` : ''}
    <div style="margin-top:8px">${(ev.tags || []).map(t => `<span class="detail-tag">${_esc(t)}</span>`).join('')}</div>
    <div class="detail-actions">
      <button class="btn btn-secondary btn-sm" onclick="showEditEventModal('${ev.id}')">
        <i data-lucide="pencil"></i> 编辑
      </button>
      <button class="btn btn-danger btn-sm" onclick="deleteEvent('${ev.id}')">
        <i data-lucide="trash-2"></i> 删除
      </button>
    </div>`;
  showDetail(html);
}

// ---------- List view ----------

function renderEventsList() {
  const tbody = document.getElementById('events-table-body');
  if (!tbody) return;
  const items = _filteredEvents().sort((a, b) => new Date(b.start) - new Date(a.start));
  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-dim);padding:24px">暂无数据</td></tr>`;
    return;
  }
  tbody.innerHTML = items.map(ev => `
    <tr>
      <td><input type="checkbox" class="ev-chk" data-id="${ev.id}"></td>
      <td title="${_esc(ev.topic || ev.id)}">${_esc((ev.content || '').slice(0, 30))}</td>
      <td>${_esc(ev.group || '私聊')}</td>
      <td>${new Date(ev.start).toLocaleDateString('zh-CN')}</td>
      <td>${(ev.salience * 100).toFixed(0)}%</td>
      <td>${(ev.tags || []).slice(0, 2).map(t => `<span class="tl-badge tag">${_esc(t)}</span>`).join(' ')}</td>
      <td class="td-actions">
        <button class="btn btn-ghost btn-sm btn-icon" onclick="showEditEventModal('${ev.id}')" title="编辑"><i data-lucide="pencil"></i></button>
        <button class="btn btn-danger btn-sm btn-icon" onclick="deleteEvent('${ev.id}')" title="删除"><i data-lucide="trash-2"></i></button>
      </td>
    </tr>`).join('');
  renderIcons();
}

function toggleSelectAll() {
  const master = document.getElementById('events-select-all');
  document.querySelectorAll('.ev-chk').forEach(cb => { cb.checked = master.checked; });
}

async function deleteSelectedEvents() {
  const ids = [...document.querySelectorAll('.ev-chk:checked')].map(cb => cb.dataset.id);
  if (!ids.length) { toast('未选择任何事件'); return; }
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  if (!confirm(`确认删除选中的 ${ids.length} 条事件？将移入回收站。`)) return;
  let ok = 0;
  for (const id of ids) {
    try { await fetchJson(`/api/events/${id}`, { method: 'DELETE' }); ok++; } catch {}
  }
  toast(`已删除 ${ok} 条事件`);
  await reloadEventFlow();
  renderIcons();
}

// ---------- CRUD ----------

function showCreateEventModal() {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  const now = new Date();
  const iso = d => d.toISOString().slice(0, 16);
  document.getElementById('cev-topic').value = '';
  document.getElementById('cev-group').value = '';
  document.getElementById('cev-start').value = iso(now);
  document.getElementById('cev-end').value   = iso(new Date(now.getTime() + 1800000));
  document.getElementById('cev-salience').value = '0.5';
  document.getElementById('cev-salience-val').textContent = '0.50';
  document.getElementById('cev-confidence').value = '0.8';
  document.getElementById('cev-confidence-val').textContent = '0.80';
  document.getElementById('cev-tags').value = '';
  document.getElementById('cev-participants').value = '';
  document.getElementById('cev-inherit').value = '';
  openModal('modal-create-event');
}

async function submitCreateEvent() {
  const topic = document.getElementById('cev-topic').value.trim();
  if (!topic) { toast('话题不能为空'); return; }
  const body = {
    topic,
    group_id:        document.getElementById('cev-group').value.trim() || null,
    start_time:      new Date(document.getElementById('cev-start').value).getTime() / 1000,
    end_time:        new Date(document.getElementById('cev-end').value).getTime() / 1000,
    salience:        parseFloat(document.getElementById('cev-salience').value),
    confidence:      parseFloat(document.getElementById('cev-confidence').value),
    chat_content_tags: document.getElementById('cev-tags').value.split(',').map(s => s.trim()).filter(Boolean),
    participants:    document.getElementById('cev-participants').value.split(',').map(s => s.trim()).filter(Boolean),
    inherit_from:    document.getElementById('cev-inherit').value.split(',').map(s => s.trim()).filter(Boolean),
  };
  try {
    await fetchJson('/api/events', { method: 'POST', body: JSON.stringify(body) });
    closeModal('modal-create-event');
    toast('事件已创建');
    await reloadEventFlow();
  } catch (e) {
    toast('创建失败：' + (e.body || e.status), 4000);
  }
}

function showEditEventModal(eventId) {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  const ev = State.rawEvents.find(e => e.id === eventId);
  if (!ev) return;
  const iso = ts => new Date(ts * 1000).toISOString().slice(0, 16);
  document.getElementById('eev-id').value    = ev.id;
  document.getElementById('eev-topic').value = ev.topic || ev.content || '';
  document.getElementById('eev-group').value = ev.group || '';
  document.getElementById('eev-start').value = iso(ev.start_ts || new Date(ev.start).getTime() / 1000);
  document.getElementById('eev-end').value   = iso(ev.end_ts   || new Date(ev.end).getTime()   / 1000);
  const sal = parseFloat(ev.salience);
  const con = parseFloat(ev.confidence);
  document.getElementById('eev-salience').value  = sal.toFixed(2);
  document.getElementById('eev-salience-val').textContent  = sal.toFixed(2);
  document.getElementById('eev-confidence').value  = con.toFixed(2);
  document.getElementById('eev-confidence-val').textContent = con.toFixed(2);
  document.getElementById('eev-tags').value    = (ev.tags || []).join(', ');
  document.getElementById('eev-participants').value = (ev.participants || []).join(', ');
  document.getElementById('eev-inherit').value = (ev.inherit_from || []).join(', ');
  openModal('modal-edit-event');
}

async function submitEditEvent() {
  const id = document.getElementById('eev-id').value;
  const body = {
    topic:            document.getElementById('eev-topic').value.trim(),
    group_id:         document.getElementById('eev-group').value.trim() || null,
    start_time:       new Date(document.getElementById('eev-start').value).getTime() / 1000,
    end_time:         new Date(document.getElementById('eev-end').value).getTime() / 1000,
    salience:         parseFloat(document.getElementById('eev-salience').value),
    confidence:       parseFloat(document.getElementById('eev-confidence').value),
    chat_content_tags: document.getElementById('eev-tags').value.split(',').map(s => s.trim()).filter(Boolean),
    participants:     document.getElementById('eev-participants').value.split(',').map(s => s.trim()).filter(Boolean),
    inherit_from:     document.getElementById('eev-inherit').value.split(',').map(s => s.trim()).filter(Boolean),
  };
  try {
    await fetchJson(`/api/events/${id}`, { method: 'PUT', body: JSON.stringify(body) });
    closeModal('modal-edit-event');
    hideDetail();
    toast('事件已更新');
    await reloadEventFlow();
  } catch (e) {
    toast('更新失败：' + (e.body || e.status), 4000);
  }
}

async function deleteEvent(eventId) {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  const ev = State.rawEvents.find(e => e.id === eventId);
  if (!confirm(`确认删除事件「${ev ? ev.content : eventId}」？将移入回收站。`)) return;
  try {
    await fetchJson(`/api/events/${eventId}`, { method: 'DELETE' });
    hideDetail();
    toast('事件已移入回收站');
    await reloadEventFlow();
  } catch (e) {
    toast('删除失败：' + (e.body || e.status), 4000);
  }
}

// ---------- Recycle bin ----------

async function showRecycleBin() {
  let data;
  try { data = await fetchJson('/api/recycle_bin'); } catch { toast('加载回收站失败'); return; }
  const items = data.items || [];
  const listEl = document.getElementById('recycle-bin-list');
  if (!listEl) return;
  if (!items.length) {
    listEl.innerHTML = '<div class="placeholder">回收站为空</div>';
  } else {
    listEl.innerHTML = items.map(ev => `
      <div class="rb-item">
        <div class="rb-item-meta">
          <div class="rb-item-topic">${_esc(ev.content || ev.topic || ev.id)}</div>
          <div class="rb-item-sub">${_esc(ev.group || '私聊')} · 删除于 ${ev.deleted_at ? new Date(ev.deleted_at).toLocaleString() : '未知'}</div>
        </div>
        <button class="btn btn-ghost btn-sm" onclick="restoreEvent('${ev.id}')">
          <i data-lucide="undo-2"></i> 还原
        </button>
      </div>`).join('');
  }
  renderIcons();
  openModal('modal-recycle-bin');
}

async function restoreEvent(eventId) {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  try {
    await fetchJson('/api/recycle_bin/restore', { method: 'POST', body: JSON.stringify({ event_id: eventId }) });
    toast('事件已还原');
    await reloadEventFlow();
    showRecycleBin();
  } catch (e) {
    toast('还原失败：' + (e.body || e.status), 4000);
  }
}

async function clearRecycleBin() {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  if (!confirm('确认清空回收站？此操作不可撤销。')) return;
  try {
    await fetchJson('/api/recycle_bin', { method: 'DELETE' });
    toast('回收站已清空');
    showRecycleBin();
  } catch (e) {
    toast('清空失败：' + (e.body || e.status), 4000);
  }
}

// ---------- Utilities ----------

function _esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
