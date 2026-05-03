'use strict';
/* Summarised Memory panel */

async function initSummaryPanel() {
  let summaries;
  try {
    summaries = await fetchJson('/api/summaries');
  } catch {
    const el = document.getElementById('summary-list');
    if (el) el.innerHTML = '<div class="placeholder error">加载失败</div>';
    return;
  }

  const listEl = document.getElementById('summary-list');
  if (!listEl) return;
  if (!summaries.length) {
    listEl.innerHTML = '<div class="placeholder">暂无摘要<br>运行群组摘要任务后出现</div>';
    return;
  }

  listEl.innerHTML = summaries.map(s =>
    `<div class="s-item" data-group-id="${s.group_id ?? ''}" data-date="${s.date}"
      onclick='loadSummary(${JSON.stringify(s.group_id)},${JSON.stringify(s.date)},this)'>
      <div class="s-group">${s.label}</div>
      <div class="s-date">${s.date}</div>
    </div>`
  ).join('');

  if (summaries.length) loadSummary(summaries[0].group_id, summaries[0].date, listEl.querySelector('.s-item'));
}

async function loadSummary(groupId, date, el) {
  document.querySelectorAll('.s-item').forEach(i => i.classList.remove('active'));
  if (el) el.classList.add('active');
  const qs = groupId
    ? `group_id=${encodeURIComponent(groupId)}&date=${encodeURIComponent(date)}`
    : `date=${encodeURIComponent(date)}`;
  try {
    const { content } = await fetchJson(`/api/summary?${qs}`);
    State.currentSummary = { groupId, date, content };
    if (!State.summaryEditing) {
      document.getElementById('summary-content').innerHTML = marked.parse(content);
    }
  } catch {
    document.getElementById('summary-content').innerHTML = '<div class="placeholder error">摘要加载失败</div>';
    State.currentSummary = { groupId, date, content: '' };
  }
}

function toggleSummaryEdit() {
  if (!State.currentSummary.date) { toast('请先选择一条摘要'); return; }
  State.summaryEditing = true;
  document.getElementById('summary-textarea').value = State.currentSummary.content;
  document.getElementById('summary-content').style.display = 'none';
  document.getElementById('summary-editor').style.display  = 'flex';
  const btn = document.getElementById('btn-edit-summary');
  if (btn) { btn.textContent = '预览'; btn.onclick = cancelSummaryEdit; }
}

function cancelSummaryEdit() {
  State.summaryEditing = false;
  document.getElementById('summary-editor').style.display  = 'none';
  document.getElementById('summary-content').style.display = 'block';
  const btn = document.getElementById('btn-edit-summary');
  if (btn) { btn.textContent = '编辑'; btn.onclick = toggleSummaryEdit; }
}

async function saveSummary() {
  const { groupId, date } = State.currentSummary;
  const content = document.getElementById('summary-textarea').value;
  try {
    await fetchJson('/api/summary', {
      method: 'PUT',
      body: JSON.stringify({ group_id: groupId, date, content }),
    });
    State.currentSummary.content = content;
    cancelSummaryEdit();
    document.getElementById('summary-content').innerHTML = marked.parse(content);
    toast('摘要已保存');
  } catch (e) {
    toast('保存失败：' + (e.body || e.status), 4000);
  }
}
