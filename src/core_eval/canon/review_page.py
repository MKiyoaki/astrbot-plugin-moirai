"""canon 抽取结果的 HTML 审阅页：逐场景列出事件、证据行、视角和认知，供人工核对。"""
from __future__ import annotations

import html
import json

from core.canon.constant_utils import CHANNEL_LABEL


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def render_scene(d: dict) -> str:
    idx = {ln["line_key"]: ln["idx"] for ln in d["lines"]}

    def refs(keys) -> str:
        return " ".join(f'<button type="button" class="ref" data-l="{idx[k]}">L{idx[k]}</button>'
                        if k in idx else '<span class="bad-ref">L?</span>' for k in keys)

    def span(keys) -> str:
        numbers = [idx[k] for k in keys if k in idx]
        if not numbers:
            return "无证据行"
        interval = f"L{min(numbers)}" if min(numbers) == max(numbers) else f"L{min(numbers)}–L{max(numbers)}"
        return f"{interval} · {len(numbers)} 行"

    left = [f'<div class="pane-title"><strong>原文</strong><span>{len(d["lines"])} 行</span></div>']
    for ln in d["lines"]:
        spk = f'<b>{_esc(ln["speaker"])}</b>：' if ln["speaker"] else ""
        left.append(f'<div class="ln" id="{_esc(d["scene_key"])}-L{ln["idx"]}" data-l="{ln["idx"]}">'
                    f'<span class="no">L{ln["idx"]}</span><span class="k">{_esc(ln["kind"])}</span>'
                    f'<span class="line-text">{spk}{_esc(ln["text"])}</span></div>')
    x = d.get("extraction") or {}
    right = [f'<div class="pane-title"><strong>事件 <span>{len(d["events"])} 个</span></strong>'
             '<div class="pane-actions"><button type="button" class="pane-action" data-action="expand">展开全部</button>'
             '<button type="button" class="pane-action" data-action="collapse">收起全部</button></div></div>',
             f'<p class="run-meta">{_esc(x.get("model"))} · {_esc(x.get("prompt_version"))} · '
             f'{_esc(x.get("status"))} · 尝试 {_esc(x.get("attempts"))} 次 · '
             f'token {_esc(x.get("prompt_tokens"))}/{_esc(x.get("completion_tokens"))}</p>']
    if x.get("error"):
        right.append(f'<p class="err">{_esc(x["error"])}</p>')
    for ev in d["events"]:
        channel = ev["views"][0]["channel"] if ev["views"] else "unstated"
        channel_class = channel if channel in CHANNEL_LABEL else "unknown"
        views = "".join(
            f'<div class="view"><span class="field-label">角色视角</span> '
            f'{_esc(v["character"])}：{_esc(v["note"] or "无补充说明")}'
            f'<div class="ref-list">{refs(v["evidence"])}</div>'
            + "".join(
                f'<div><b>{_esc(a["kind"])}</b> · {_esc(a["recipient"])}：'
                f'{_esc(a["content"])} <span class="ref-list">{refs(a["evidence"])}</span></div>'
                for a in v.get("access", [])) + '</div>' for v in ev["views"])
        ents = "、".join(f'{_esc(e["name"])}<small>/{_esc(e["type"])}</small>' for e in ev["entities"])
        lines_attr = " ".join(str(idx[k]) for k in ev["evidence"] if k in idx)
        beats = "".join(f'<li>{_esc(b["text"])} <span class="ref-list">{refs(b["evidence"])}</span></li>'
                        for b in ev.get("beats") or [])
        right.append(
            f'<details class="ev" data-lines="{lines_attr}"><summary class="ev-head">'
            f'<span class="event-id">{_esc(ev["local_id"])}</span>'
            f'<span class="event-main"><strong>{_esc(ev["topic"])}</strong>'
            f'<span class="preview">{_esc(ev["summary"][:130])}</span></span>'
            f'<span class="event-tags"><span class="channel {channel_class}">'
            f'{_esc(CHANNEL_LABEL.get(channel, channel))}</span>'
            f'<span class="span-label">{span(ev["evidence"])}</span></span></summary>'
            f'<div class="ev-body"><p class="event-summary">{_esc(ev["summary"])}</p>'
            + (f'<div class="field-label">关键细节</div><ol class="beats">{beats}</ol>' if beats else "") +
            f'{views}<details class="minor"><summary>参与者与实体</summary>'
            f'<div>参与：{_esc("、".join(json.loads(ev["participants"]))) or "无"}</div>'
            f'<div>实体：{ents or "无"}</div></details>'
            f'<details class="minor"><summary>事件证据 · {span(ev["evidence"])}</summary>'
            f'<div class="ref-list">{refs(ev["evidence"])}</div></details>'
            f'<div class="time-note">时间：{_esc(ev["in_world_time"])}'
            f'{(" · " + _esc(ev["in_world_note"])) if ev["in_world_note"] else ""}</div>'
            f'</div></details>')
    if "fact_candidates" in d or d.get("fact_error"):
        candidates = d.get("fact_candidates") or []
        items = "".join(
            f'<li><b>{_esc(f["subject"])} · {_esc(f["predicate"])} · {_esc(f["object"])}</b> '
            f'（{_esc(f["event_id"])}；{_esc("肯定" if f["polarity"] else "否定")}；'
            f'{_esc(f.get("source_mode", "observed"))}；{_esc(f.get("time_scope", "event"))}） '
            f'{refs([f["line_key"]])}</li>' for f in candidates)
        body = f'<ul>{items}</ul>' if items else '<p>没有抽取到状态事实候选。</p>'
        if d.get("fact_error"):
            body += f'<p class="err">{_esc(d["fact_error"])}</p>'
        right.append(
            f'<details class="aux" open><summary>待审阅时间事实 · {len(candidates)} 条</summary>'
            f'<div class="aux-body">{body}</div></details>')
    if d.get("facts"):
        items = []
        for fact in d["facts"]:
            evidence = refs([ev["line_key"] for ev in fact["evidence"]])
            changes = "".join(
                f'<div>变更：{_esc(t["earlier_fact_id"])} → {_esc(fact["fact_id"])} '
                f'{_esc(t["relation"])}；证据 {_esc(t["evidence_event_id"])} '
                f'{_esc(t["evidence_line_key"])}</div>'
                for t in fact["transitions"])
            items.append(
                f'<li><b>{_esc(fact["subject"])} · {_esc(fact["predicate"])} · '
                f'{_esc(fact["object"])}</b>（{_esc(fact["review_status"])}；'
                f'{_esc(fact["persistence"])}；{_esc(fact["point_label"])}） '
                f'{evidence}{changes}</li>')
        right.append(
            f'<details class="aux"><summary>时间事实 · {len(items)} 条</summary>'
            f'<div class="aux-body"><ul>{"".join(items)}</ul></div></details>')
    for ep in d["episodes"]:
        right.append(f'<details class="aux"><summary>第一人称摘要（{_esc(ep["character"])}）</summary>'
                     f'<div class="aux-body">{_esc(ep["text"])}</div></details>')
    if d["cognitions"]:
        items = "".join(f'<li>{_esc(c["target"])}：{_esc(c["stance"])} {refs(json.loads(c["evidence"]))}</li>'
                        for c in d["cognitions"])
        right.append(f'<details class="aux"><summary>认知 · {len(d["cognitions"])} 条</summary>'
                     f'<div class="aux-body"><ul>{items}</ul></div></details>')
    if d["edges"]:
        local = {ev["event_id"]: ev["local_id"] for ev in d["events"]}
        items = "".join(
            f'<li>{_esc(local.get(e["src"]))} → {_esc(local.get(e["dst"]))} {_esc(e["type"])}'
            f'（{"明说" if e["explicit"] else "推断"}，{e["confidence"]:.2f}）{refs(json.loads(e["evidence"]))}</li>'
            for e in d["edges"])
        right.append(f'<details class="aux"><summary>事件关系 · {len(d["edges"])} 条</summary>'
                     f'<div class="aux-body"><ul>{items}</ul></div></details>')
    return (f'<section class="scene"><div class="scene-heading"><h2>{_esc(d["anchor"])}</h2>'
            f'<p class="meta">{_esc(d["scene_key"])} · 叙事位置 {d["narrative_pos"]}</p>'
            f'<p class="meta">官方简介：{_esc(d["official_summary"] or "无")}</p></div>'
            f'<div class="cols"><div class="pane left">{"".join(left)}</div>'
            f'<div class="pane right">{"".join(right)}</div></div></section>')


PAGE = r"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>canon 抽取审阅</title>
<style>
:root{color-scheme:light;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#202a36;background:#f3f5f8}
*{box-sizing:border-box}body{margin:0;font-size:14px;line-height:1.55}
button,select{font:inherit}button{cursor:pointer}.appbar{position:sticky;top:0;z-index:10;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 20px;background:#fff;border-bottom:1px solid #dce2ea;box-shadow:0 2px 10px #1d2e4410}
.brand h1{font-size:17px;line-height:1.25;margin:0}.brand p{font-size:12px;color:#687587;margin:2px 0 0}.controls{display:flex;align-items:center;gap:8px;min-width:0}.controls select{width:min(52vw,520px);min-width:240px;padding:8px 10px;border:1px solid #bdc8d5;border-radius:8px;background:#fff;color:#202a36}.nav-btn,.pane-action{border:1px solid #bdc8d5;border-radius:8px;background:#fff;padding:7px 10px;color:#34465b}.nav-btn:hover,.pane-action:hover{background:#edf3f9}.nav-btn:disabled{opacity:.4;cursor:default}.count{white-space:nowrap;color:#687587;font-size:12px}
.hint{margin:12px 20px 0;color:#566579;font-size:12px}main{padding:0 20px 20px}.scene[hidden]{display:none}.scene-heading{margin:14px 0}.scene-heading h2{font-size:20px;line-height:1.35;margin:0 0 4px}.meta{color:#687587;font-size:12px;margin:2px 0}.err{color:#b42318}
.cols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:14px}.pane{position:relative;min-width:0;height:calc(100vh - 180px);min-height:360px;overflow:auto;background:#fff;border:1px solid #dce2ea;border-radius:10px;box-shadow:0 1px 3px #1d2e4408}.pane-title{position:sticky;top:0;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 14px;background:#fff;border-bottom:1px solid #e7ebf0}.pane-title strong{font-size:14px}.pane-title span,.run-meta{color:#687587;font-size:12px}.pane-actions{display:flex;gap:6px}.pane-action{padding:4px 8px;font-size:12px}.run-meta{margin:10px 14px}
.ln{display:grid;grid-template-columns:42px 68px minmax(0,1fr);gap:4px;padding:3px 12px;border-left:3px solid transparent;overflow-wrap:anywhere}.ln:nth-child(even){background:#fafbfd}.ln.hl{background:#fff3cb;border-left-color:#e1a70a}.no{color:#758396;font-variant-numeric:tabular-nums}.k{color:#8995a4;font-size:11px}.line-text b{color:#263c59}
.ev,.aux{margin:8px 12px;border:1px solid #e0e6ed;border-radius:9px;background:#fff}.ev[open]{border-color:#a9bfd7;box-shadow:0 2px 8px #1d2e440c}.ev:hover{border-color:#8eaeca}.ev-head{display:flex;align-items:flex-start;gap:9px;padding:10px 12px;cursor:pointer;list-style:none}.ev-head::-webkit-details-marker,.aux>summary::-webkit-details-marker{display:none}.ev-head::before{content:"▸";color:#6d829a;margin-top:1px}.ev[open]>.ev-head::before{content:"▾"}.event-id{font-weight:700;color:#486a91;flex:none}.event-main{display:flex;flex-direction:column;min-width:0;flex:1}.event-main strong{font-size:14px;line-height:1.35}.preview{color:#627185;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ev[open] .preview{display:none}.event-tags{display:flex;flex-direction:column;align-items:flex-end;gap:3px;white-space:nowrap}.channel{font-size:11px;font-weight:600;border-radius:20px;padding:2px 7px;background:#eef1f5;color:#526173}.channel.experienced{background:#e8f2ff;color:#17569a}.channel.witnessed{background:#e8f6ed;color:#20714d}.channel.recalled{background:#f3eaff;color:#7341a0}.channel.told{background:#fff0dc;color:#8d591a}.span-label{font-size:11px;color:#8290a1}.ev-body{padding:0 14px 12px 36px}.event-summary{margin:2px 0 10px;white-space:pre-wrap}.field-label{font-size:12px;font-weight:700;color:#566579}.beats{margin:5px 0 10px;padding-left:20px}.beats li{padding:2px 0}.ref-list{display:inline-flex;flex-wrap:wrap;gap:3px;vertical-align:middle}.ref{border:0;background:#eef4fb;color:#1763a3;border-radius:4px;padding:1px 4px;font-size:11px;line-height:1.5}.ref:hover,.ref:focus-visible{background:#cfe5fb;outline:1px solid #1763a3}.bad-ref{color:#b42318}.view{padding:8px 10px;margin:10px 0;background:#f3f7fc;border-left:3px solid #8eb6db;border-radius:4px}.view .ref-list{display:flex;margin-top:5px}.minor{margin:5px 0;color:#566579;font-size:12px}.minor>summary{cursor:pointer;color:#496b8d}.minor>div{padding:4px 0}.time-note{color:#8290a1;font-size:11px;margin-top:8px}.aux>summary{cursor:pointer;padding:9px 12px;font-weight:600;color:#405a75}.aux-body{padding:0 12px 10px;white-space:pre-wrap}.aux-body ul{margin:4px 0;padding-left:20px}
@media(max-width:900px){.appbar{position:static;align-items:stretch;flex-direction:column}.controls select{flex:1;width:auto;min-width:0}.cols{grid-template-columns:1fr}.pane{height:48vh;min-height:260px}.scene-heading h2{font-size:17px}.hint{margin:10px 14px 0}main{padding:0 14px 14px}}
</style></head><body>
<header class="appbar"><div class="brand"><h1>canon 抽取审阅</h1><p>本地结果 · 原文与事件对照</p></div><div class="controls"><button class="nav-btn" id="prev-scene" type="button">上一场</button><select id="scene-select" aria-label="选择场景"><!--OPTIONS--></select><button class="nav-btn" id="next-scene" type="button">下一场</button><span class="count" id="scene-count"></span></div></header>
<p class="hint">选择场景后，展开右侧事件查看摘要和细节；悬停事件可定位原文，点击蓝色行号可精确跳转。</p><main><!--SCENES--></main>
<script>
const scenes=Array.from(document.querySelectorAll('.scene'));
const select=document.getElementById('scene-select');
function showScene(index,updateHash=true){
 index=Math.max(0,Math.min(index,scenes.length-1));
 scenes.forEach((scene,i)=>{scene.hidden=i!==index});
 select.selectedIndex=index;
 document.getElementById('scene-count').textContent=(index+1)+' / '+scenes.length;
 document.getElementById('prev-scene').disabled=index===0;
 document.getElementById('next-scene').disabled=index===scenes.length-1;
 if(updateHash)history.replaceState(null,'','#s'+index);
 window.scrollTo(0,0);
}
const start=Number(location.hash.match(/^#s(\d+)$/)?.[1]??0);
showScene(Number.isInteger(start)?start:0,false);
select.addEventListener('change',()=>showScene(select.selectedIndex));
document.getElementById('prev-scene').addEventListener('click',()=>showScene(select.selectedIndex-1));
document.getElementById('next-scene').addEventListener('click',()=>showScene(select.selectedIndex+1));
window.addEventListener('hashchange',()=>{const match=location.hash.match(/^#s(\d+)$/);if(match)showScene(Number(match[1]),false)});
function highlight(scene,lines){
 scene.querySelectorAll('.ln.hl').forEach(line=>line.classList.remove('hl'));
 const first=lines[0];
 lines.forEach(n=>{const line=scene.querySelector('.ln[data-l="'+n+'"]');if(line)line.classList.add('hl')});
 const line=scene.querySelector('.ln[data-l="'+first+'"]');
 if(line)line.scrollIntoView({block:'center',behavior:'smooth'});
}
document.querySelectorAll('.ev').forEach(ev=>{
 const focus=()=>highlight(ev.closest('.scene'),ev.dataset.lines.split(' ').filter(Boolean));
 ev.addEventListener('mouseenter',focus);
 ev.querySelector('.ev-head').addEventListener('focus',focus);
});
document.querySelectorAll('.ref').forEach(ref=>ref.addEventListener('click',event=>{
 event.stopPropagation();highlight(ref.closest('.scene'),[ref.dataset.l]);
}));
document.querySelectorAll('.pane-action').forEach(button=>button.addEventListener('click',()=>{
 const open=button.dataset.action==='expand';
 button.closest('.scene').querySelectorAll('.ev').forEach(ev=>{ev.open=open});
}));
</script></body></html>"""


def review_page(dumps: list[dict]) -> str:
    """把 scene_dump 的结果按叙事顺序拼成一个审阅页。"""
    found = sorted(dumps, key=lambda d: d["narrative_pos"])
    options = "".join(f'<option value="s{i}">{i + 1:02d} · {_esc(d["anchor"])}</option>'
                      for i, d in enumerate(found))
    body = "".join(render_scene(d).replace('<section class="scene">', f'<section class="scene" id="s{i}">', 1)
                   for i, d in enumerate(found))
    return PAGE.replace("<!--OPTIONS-->", options).replace("<!--SCENES-->", body)
