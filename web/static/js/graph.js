'use strict';
/* Relation Graph — Cytoscape rendering, personas/impressions CRUD */

// ---------- Data loading ----------

async function initRelationGraph() {
  let data;
  try {
    data = await fetchJson('/api/graph');
  } catch {
    const cy = document.getElementById('cy');
    if (cy) cy.innerHTML = '<div class="placeholder error">关系图加载失败</div>';
    return;
  }
  State.rawGraph = data;
  _applyGraphView();
}

// ---------- View toggle ----------

function setGraphView(view) {
  State.graphView = view;
  const btnGraph = document.getElementById('btn-graph-view');
  const btnList  = document.getElementById('btn-graph-list-view');
  if (btnGraph) btnGraph.classList.toggle('active', view === 'graph');
  if (btnList)  btnList.classList.toggle('active',  view === 'list');

  const cyEl   = document.getElementById('cy');
  const listEl = document.getElementById('graph-list-view');
  if (cyEl)   cyEl.style.display   = view === 'graph' ? '' : 'none';
  if (listEl) listEl.style.display = view === 'list'  ? '' : 'none';

  if (view === 'list') renderGraphList();
  else if (State.cy) setTimeout(() => State.cy.fit(), 30);
}

function _applyGraphView() {
  if (State.graphView === 'list') renderGraphList();
  else renderGraph();
}

// ---------- Cytoscape rendering ----------

function renderGraph() {
  const { nodes, edges } = State.rawGraph;
  const cyEl = document.getElementById('cy');
  if (!cyEl) return;
  if (State.cy) State.cy.destroy();

  State.cy = cytoscape({
    container: cyEl,
    elements: [...nodes, ...edges],
    style: [
      {
        selector: 'node',
        style: {
          label: 'data(label)',
          'background-color': 'var(--accent)',
          color: 'var(--text)',
          'text-valign': 'center', 'text-halign': 'center',
          'font-size': '11px',
          width: 48, height: 48,
          'text-wrap': 'wrap', 'text-max-width': 46,
          'border-width': 1, 'border-color': 'rgba(255,255,255,0.3)',
        },
      },
      { selector: 'node[?is_bot]', style: { 'background-color': '#e91e63', 'border-width': 2 } },
      {
        selector: 'edge',
        style: {
          label: 'data(label)',
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          'font-size': '9px', color: 'var(--text-dim)',
          width: 'mapData(intensity, 0, 1, 1, 5)',
          'line-color':         'mapData(affect, -1, 1, #ef4444, #22c55e)',
          'target-arrow-color': 'mapData(affect, -1, 1, #ef4444, #22c55e)',
          opacity: 0.85,
        },
      },
      { selector: '.dim',     style: { opacity: 0.14 } },
      { selector: '.focused', style: { opacity: 1, 'border-width': 3, 'border-color': 'var(--warn)' } },
      { selector: 'edge.focused', style: { width: 4, opacity: 1 } },
    ],
    layout: { name: 'cose', animate: false, randomize: false, idealEdgeLength: 100 },
  });

  State.cy.on('tap', 'node', evt => {
    const node = evt.target;
    State.cy.elements().addClass('dim');
    node.closedNeighborhood().removeClass('dim').addClass('focused');
    showPersonaDetail(node.data());
  });

  State.cy.on('tap', 'edge', evt => {
    const data = evt.target.data();
    State.cy.elements().addClass('dim');
    evt.target.removeClass('dim').addClass('focused');
    evt.target.connectedNodes().removeClass('dim');
    showImpressionDetail(data);
    if (data.evidence_event_ids?.length) highlightEvents(data.evidence_event_ids);
  });

  State.cy.on('tap', evt => {
    if (evt.target === State.cy) clearHighlight();
  });

  State.cy.on('zoom', () => {
    const z = State.cy.zoom();
    State.cy.style().selector('node').style('font-size', z < 0.6 ? 0 : 11).update();
  });
}

function clearHighlight() {
  if (State.cy) State.cy.elements().removeClass('dim focused');
  highlightEvents([]);
  hideDetail();
}

// ---------- Graph list view ----------

function renderGraphList() {
  const listEl = document.getElementById('graph-list-view');
  if (!listEl) return;
  const { nodes, edges } = State.rawGraph;

  const q = (document.getElementById('graph-search')?.value || '').toLowerCase();
  const filtNodes = nodes.filter(n =>
    !q || (n.data.label || '').toLowerCase().includes(q)
  );

  let html = '';
  if (filtNodes.length) {
    html += '<div class="graph-section-title">人格节点</div>';
    html += filtNodes.map(n => {
      const d = n.data;
      const initials = (d.label || '?').slice(0, 1).toUpperCase();
      return `
        <div class="graph-persona-row" onclick="showPersonaDetail(${JSON.stringify(d).replace(/"/g, '&quot;')})">
          <div class="graph-persona-avatar">${_esc(initials)}</div>
          <div class="graph-persona-info">
            <div class="graph-persona-name">${_esc(d.label)}</div>
            <div class="graph-persona-sub">${_esc((d.attrs?.description || '').slice(0, 60))}</div>
          </div>
          <div class="graph-persona-actions" onclick="event.stopPropagation()">
            <button class="btn btn-ghost btn-sm btn-icon" onclick="showEditPersonaModal('${d.id}')" title="编辑"><i data-lucide="pencil"></i></button>
            <button class="btn btn-danger btn-sm btn-icon" onclick="deletePersona('${d.id}')" title="删除"><i data-lucide="trash-2"></i></button>
          </div>
        </div>`;
    }).join('');
  }

  const filtEdges = edges.filter(e =>
    !q || (e.data.label || '').toLowerCase().includes(q)
  );
  if (filtEdges.length) {
    html += '<div class="graph-section-title">印象关系</div>';
    html += filtEdges.map(e => {
      const d = e.data;
      const srcNode = nodes.find(n => n.data.id === d.source);
      const tgtNode = nodes.find(n => n.data.id === d.target);
      const affColor = d.affect > 0 ? 'var(--positive)' : (d.affect < 0 ? 'var(--negative)' : 'var(--text-dim)');
      return `
        <div class="graph-impression-row">
          <div class="graph-imp-nodes">
            <span>${_esc(srcNode?.data.label || d.source.slice(0, 8))}</span>
            <i data-lucide="arrow-right" style="width:11px;height:11px;color:var(--text-dim)"></i>
            <span>${_esc(tgtNode?.data.label || d.target.slice(0, 8))}</span>
          </div>
          <span class="graph-imp-label">${_esc(d.label)}</span>
          <span class="graph-imp-affect" style="color:${affColor}">${(d.affect >= 0 ? '+' : '') + d.affect.toFixed(2)}</span>
          <div class="graph-imp-actions">
            <button class="btn btn-ghost btn-sm btn-icon" onclick="showEditImpressionModal('${d.source}','${d.target}','${d.scope}')" title="编辑"><i data-lucide="pencil"></i></button>
          </div>
        </div>`;
    }).join('');
  }

  if (!html) html = '<div class="placeholder">暂无数据</div>';
  listEl.innerHTML = html;
  renderIcons();
}

// ---------- Detail panel ----------

function showPersonaDetail(data) {
  const attrs = data.attrs || {};
  const bindings = (data.bound_identities || [])
    .map(b => `<span class="detail-tag">${_esc(b.platform)}:${_esc(b.physical_id)}</span>`)
    .join('');
  const html = `
    <h3><i data-lucide="user-round" class="detail-title-icon"></i>${_esc(data.label)}</h3>
    <div class="detail-field"><span class="k">UID</span><span class="v">${data.id.slice(0, 12)}…</span></div>
    <div class="detail-field"><span class="k">置信度</span><span class="v">${(data.confidence * 100).toFixed(0)}%</span></div>
    ${attrs.description ? `<div class="detail-field"><span class="k">描述</span><span class="v">${_esc(attrs.description)}</span></div>` : ''}
    ${attrs.affect_type ? `<div class="detail-field"><span class="k">情感类型</span><span class="v">${_esc(attrs.affect_type)}</span></div>` : ''}
    ${(attrs.content_tags || []).length ? `<div style="margin-top:6px">${attrs.content_tags.map(t => `<span class="detail-tag">${_esc(t)}</span>`).join('')}</div>` : ''}
    ${bindings ? `<div style="margin-top:6px">${bindings}</div>` : ''}
    <div class="detail-actions">
      <button class="btn btn-secondary btn-sm" onclick="showEditPersonaModal('${data.id}')">
        <i data-lucide="pencil"></i> 编辑
      </button>
      <button class="btn btn-danger btn-sm" onclick="deletePersona('${data.id}')">
        <i data-lucide="trash-2"></i> 删除
      </button>
    </div>`;
  showDetail(html);
}

function showImpressionDetail(data) {
  const affectColor = data.affect > 0 ? 'var(--positive)' : (data.affect < 0 ? 'var(--negative)' : 'var(--text-dim)');
  const evidenceItems = (data.evidence_event_ids || []).map(eid => {
    const ev = State.rawEvents.find(e => e.id === eid);
    return `<div class="evidence-item" onclick="jumpToEvent('${eid}')">
      <i data-lucide="calendar-days" style="width:11px;height:11px"></i>
      ${_esc(ev ? ev.content : eid.slice(0, 12))}
    </div>`;
  }).join('');

  const html = `
    <h3><i data-lucide="link-2" class="detail-title-icon"></i>印象详情</h3>
    <div class="detail-field"><span class="k">关系类型</span><span class="v">${_esc(data.label)}</span></div>
    <div class="detail-field"><span class="k">情感</span><span class="v" style="color:${affectColor}">${data.affect.toFixed(2)}</span></div>
    <div class="detail-field"><span class="k">强度</span><span class="v">${(data.intensity * 100).toFixed(0)}%</span></div>
    <div class="detail-field"><span class="k">置信度</span><span class="v">${(data.confidence * 100).toFixed(0)}%</span></div>
    <div class="detail-field"><span class="k">范围</span><span class="v">${_esc(data.scope)}</span></div>
    ${evidenceItems ? `<div class="evidence-card"><div class="evidence-card-title">证据事件（点击跳转时间线）</div>${evidenceItems}</div>` : ''}
    <div class="detail-actions">
      <button class="btn btn-secondary btn-sm" onclick="showEditImpressionModal('${data.source}','${data.target}','${data.scope}')">
        <i data-lucide="pencil"></i> 编辑
      </button>
    </div>`;
  showDetail(html);
}

function jumpToEvent(eventId) {
  switchPanel('events');
  setTimeout(() => {
    highlightEvents([eventId]);
    const dot = document.querySelector(`.tl-dot[data-event-id="${eventId}"]`);
    if (dot) dot.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, 300);
}

// ---------- Persona CRUD ----------

function showCreatePersonaModal() {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  document.getElementById('cp-name').value        = '';
  document.getElementById('cp-description').value = '';
  document.getElementById('cp-affect-type').value = '中性';
  document.getElementById('cp-tags').value        = '';
  document.getElementById('cp-bindings').value    = '';
  document.getElementById('cp-confidence').value  = '0.8';
  document.getElementById('cp-confidence-val').textContent = '0.80';
  openModal('modal-create-persona');
}

async function submitCreatePersona() {
  const name = document.getElementById('cp-name').value.trim();
  if (!name) { toast('姓名不能为空'); return; }
  const rawBindings = document.getElementById('cp-bindings').value.trim();
  const bound_identities = rawBindings
    ? rawBindings.split('\n').map(line => {
        const [platform, physical_id] = line.split(':').map(s => s.trim());
        return platform && physical_id ? { platform, physical_id } : null;
      }).filter(Boolean)
    : [];
  const body = {
    primary_name: name,
    description:  document.getElementById('cp-description').value.trim(),
    affect_type:  document.getElementById('cp-affect-type').value,
    content_tags: document.getElementById('cp-tags').value.split(',').map(s => s.trim()).filter(Boolean),
    confidence:   parseFloat(document.getElementById('cp-confidence').value),
    bound_identities,
  };
  try {
    await fetchJson('/api/personas', { method: 'POST', body: JSON.stringify(body) });
    closeModal('modal-create-persona');
    toast('人格已创建');
    await initRelationGraph();
  } catch (e) {
    toast('创建失败：' + (e.body || e.status), 4000);
  }
}

function showEditPersonaModal(uid) {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  const node = State.rawGraph.nodes.find(n => n.data.id === uid);
  if (!node) return;
  const d = node.data;
  const attrs = d.attrs || {};
  document.getElementById('ep-uid').value         = d.id;
  document.getElementById('ep-name').value        = d.label || '';
  document.getElementById('ep-description').value = attrs.description || '';
  document.getElementById('ep-affect-type').value = attrs.affect_type || '中性';
  document.getElementById('ep-tags').value        = (attrs.content_tags || []).join(', ');
  document.getElementById('ep-bindings').value    = (d.bound_identities || [])
    .map(b => `${b.platform}:${b.physical_id}`).join('\n');
  const con = parseFloat(d.confidence);
  document.getElementById('ep-confidence').value  = con.toFixed(2);
  document.getElementById('ep-confidence-val').textContent = con.toFixed(2);
  openModal('modal-edit-persona');
}

async function submitEditPersona() {
  const uid  = document.getElementById('ep-uid').value;
  const name = document.getElementById('ep-name').value.trim();
  if (!name) { toast('姓名不能为空'); return; }
  const rawBindings = document.getElementById('ep-bindings').value.trim();
  const bound_identities = rawBindings
    ? rawBindings.split('\n').map(line => {
        const [platform, physical_id] = line.split(':').map(s => s.trim());
        return platform && physical_id ? { platform, physical_id } : null;
      }).filter(Boolean)
    : [];
  const body = {
    primary_name: name,
    description:  document.getElementById('ep-description').value.trim(),
    affect_type:  document.getElementById('ep-affect-type').value,
    content_tags: document.getElementById('ep-tags').value.split(',').map(s => s.trim()).filter(Boolean),
    confidence:   parseFloat(document.getElementById('ep-confidence').value),
    bound_identities,
  };
  try {
    await fetchJson(`/api/personas/${uid}`, { method: 'PUT', body: JSON.stringify(body) });
    closeModal('modal-edit-persona');
    hideDetail();
    toast('人格已更新');
    await initRelationGraph();
  } catch (e) {
    toast('更新失败：' + (e.body || e.status), 4000);
  }
}

async function deletePersona(uid) {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  const node = State.rawGraph.nodes.find(n => n.data.id === uid);
  const name = node?.data.label || uid;
  if (!confirm(`确认删除人格「${name}」？相关印象也会丢失显示。`)) return;
  try {
    await fetchJson(`/api/personas/${uid}`, { method: 'DELETE' });
    hideDetail();
    toast('人格已删除');
    await initRelationGraph();
  } catch (e) {
    toast('删除失败：' + (e.body || e.status), 4000);
  }
}

// ---------- Impression CRUD ----------

function showEditImpressionModal(observer, subject, scope) {
  if (!State.sudo) { toast('需要 Sudo 模式'); return; }
  const edge = State.rawGraph.edges.find(e =>
    e.data.source === observer && e.data.target === subject && e.data.scope === scope
  );
  const d = edge?.data || {};
  document.getElementById('ei-observer').value = observer;
  document.getElementById('ei-subject').value  = subject;
  document.getElementById('ei-scope').value    = scope;
  document.getElementById('ei-relation').value = d.label || '';
  const aff = parseFloat(d.affect || 0);
  const int_ = parseFloat(d.intensity || 0.5);
  const con  = parseFloat(d.confidence || 0.8);
  document.getElementById('ei-affect').value      = aff.toFixed(2);
  document.getElementById('ei-affect-val').textContent = (aff >= 0 ? '+' : '') + aff.toFixed(2);
  document.getElementById('ei-intensity').value   = int_.toFixed(2);
  document.getElementById('ei-intensity-val').textContent = int_.toFixed(2);
  document.getElementById('ei-confidence').value  = con.toFixed(2);
  document.getElementById('ei-confidence-val').textContent = con.toFixed(2);
  document.getElementById('ei-evidence').value    = (d.evidence_event_ids || []).join(', ');
  openModal('modal-edit-impression');
}

async function submitEditImpression() {
  const observer = document.getElementById('ei-observer').value;
  const subject  = document.getElementById('ei-subject').value;
  const scope    = document.getElementById('ei-scope').value;
  const body = {
    relation_type:     document.getElementById('ei-relation').value.trim(),
    affect:            parseFloat(document.getElementById('ei-affect').value),
    intensity:         parseFloat(document.getElementById('ei-intensity').value),
    confidence:        parseFloat(document.getElementById('ei-confidence').value),
    scope,
    evidence_event_ids: document.getElementById('ei-evidence').value.split(',').map(s => s.trim()).filter(Boolean),
  };
  try {
    await fetchJson(`/api/impressions/${observer}/${subject}/${scope}`, { method: 'PUT', body: JSON.stringify(body) });
    closeModal('modal-edit-impression');
    hideDetail();
    toast('印象已更新');
    await initRelationGraph();
  } catch (e) {
    toast('更新失败：' + (e.body || e.status), 4000);
  }
}

// ---------- Utilities ----------

function _esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
