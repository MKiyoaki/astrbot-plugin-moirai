"""canon 命令行：导入 story_pack、查看状态、导出审阅页、跑抽取基准。

用法（在插件根目录下）：
  python -m core.canon.cli import --pack <story_pack> --db <canon.sqlite> --api-url <url> --model <name> [--only pilot.txt]
  python -m core.canon.cli status --db <canon.sqlite>
  python -m core.canon.cli dump --db <canon.sqlite> (--scene <key> ... | --only pilot.txt) [--out review.html]
  python -m core.canon.cli bench --pack <story_pack> (--only pilot.txt | --scene <key> ...) \
      (--estimate | --replay <试跑目录或运行目录> | --api-url <url> --model <name>) \
      [--probes <探针文件>] [--baseline <运行目录>] [--repeats N]
  python -m core.canon.cli compare <运行目录> <运行目录> [...]
  python -m core.canon.cli judge --run <运行目录> --pack <story_pack> --api-url <url> --model <name> [--repeats 3]

API key 只从环境变量读取：抽取用 CANON_API_KEY，裁判用 CANON_JUDGE_API_KEY（没有就用 CANON_API_KEY）。审阅页和基准输出里有剧情原文，只能留在本机。
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import html
import json
import os
import sys
from pathlib import Path

from .bench import version_tag
from .importer import Importer, encoder_identity, import_archives
from .prompt import PROMPT_VERSION
from .store import CanonStore

CHANNEL_LABEL = {"experienced": "亲历", "witnessed": "在场目睹", "told": "听人讲述",
                 "recalled": "回忆", "unstated": "文本未表明是否知情"}


def read_keys(path: str) -> set[str]:
    return {ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()}


def read_key_list(path: str) -> list[str]:
    return list(dict.fromkeys(ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()))


async def open_shared_encoder():
    """canon 向量和普通记忆走同一个 Moirai embedding 入口；配置取 run_config.py 的 RETRIEVAL_*。"""
    from devtools.retrieval import development_config  # noqa: PLC0415
    from ..retrieval.providers import build_retrieval_providers  # noqa: PLC0415
    config = development_config()
    if not config.embedding_enabled:
        raise ValueError("共享 embedding 已关闭（RETRIEVAL_ENCODER_ENABLED = False）")
    providers = build_retrieval_providers(config)
    try:
        await providers.start()
        if not await providers.encoder.prepare(0) and not providers.encoder.dim:
            raise ValueError(f"共享 embedding 不可用：{providers.encoder.disabled_reason or '维度为 0'}")
    except BaseException:
        await providers.close()
        raise
    return providers


async def cmd_import(args) -> int:
    call = None
    if args.api_url and args.model:
        key = os.environ.get("CANON_API_KEY", "")
        if not key:
            print("缺少环境变量 CANON_API_KEY", file=sys.stderr)
            return 2
        from ..utils.llm import SimpleLLMClient  # noqa: PLC0415
        client = SimpleLLMClient(args.api_url, key, args.model, timeout=args.timeout)

        async def call(prompt: str, system_prompt: str):
            return await client.text_chat(prompt, system_prompt)

    providers = await open_shared_encoder() if args.embed else None
    encoder = providers.encoder if providers else None
    dim, enc_id = encoder_identity(encoder)
    store = CanonStore(args.db)
    try:
        await store.open(vec_dim=dim, encoder_id=enc_id)
    except BaseException:
        if providers:
            await providers.close()
        raise

    done = [0]

    def progress(key: str, status: str) -> None:
        done[0] += 1
        print(f"  [{done[0]}] {status:6} {key}", flush=True)

    importer = Importer(store, call, model=args.model or "", character=args.character,
                        concurrency=args.concurrency, timeout=args.timeout, encoder=encoder, progress=progress)
    fact_report = None
    try:
        report = await importer.run(args.pack, only=read_keys(args.only) if args.only else None)
        if args.facts:
            if call is None:
                raise ValueError("--facts 需要 --api-url 和 --model")
            async with store.db.execute("SELECT scene_key FROM scenes ORDER BY narrative_pos") as cur:
                keys = [row["scene_key"] for row in await cur.fetchall()]
            out = Path(args.facts_out) if args.facts_out else Path(args.db).with_name(
                "facts-candidates-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + ".jsonl")
            fact_report = await run_fact_pipeline(store, keys, call, args.model, out,
                                                  concurrency=args.concurrency)
            await write_fact_review_page(store, keys, fact_report, out,
                                         Path(args.db).with_name("review.html"))
    finally:
        await store.close()
        if providers:
            await providers.close()
    print("\n".join(report.lines()))
    if fact_report:
        print(f"时间事实：候选 {fact_report['candidates']} 条，"
              f"完成 {fact_report['complete']}/{fact_report['selected']}，"
              f"失败 {fact_report['failed']}，跳过 {len(fact_report['skipped'])}，"
              f"审阅组 {fact_report['review_groups']}")
        print(f"审阅页：{Path(args.db).with_name('review.html')}")
    return 0 if not report.failed and (not fact_report or
           (fact_report["failed"] == 0 and not fact_report["skipped"])) else 1


async def cmd_status(args) -> int:
    store = CanonStore(args.db)
    await store.open()
    try:
        meta = await store.get_meta()
        counts = await store.counts(PROMPT_VERSION)
    finally:
        await store.close()
    print(f"数据库：{args.db}")
    print("、".join(f"{k} {v}" for k, v in counts.items()))
    print("meta：" + json.dumps(meta, ensure_ascii=False))
    return 0


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
            f'<div class="ref-list">{refs(v["evidence"])}</div></div>' for v in ev["views"])
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
            f'（{_esc(f["event_id"])}；{_esc("肯定" if f["polarity"] else "否定")}） '
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


async def cmd_dump(args) -> int:
    keys = list(args.scene or [])
    if args.only:
        keys += sorted(read_keys(args.only) - set(keys))
    if not keys:
        print("需要 --scene 或 --only", file=sys.stderr)
        return 2
    store = CanonStore(args.db)
    await store.open()
    try:
        dumps = [await store.scene_dump(k) for k in keys]
    finally:
        await store.close()
    for k, d in zip(keys, dumps):
        if d is None:
            print(f"库里没有场景 {k}", file=sys.stderr)
    found = [d for d in dumps if d]
    out = Path(args.out or Path(args.db).with_name("review.html"))
    out.write_text(review_page(found), encoding="utf-8")
    print(f"已写出 {len(found)} 个场景：{out}")
    return 0


async def cmd_bench(args) -> int:
    from ..utils.llm import SimpleLLMClient  # noqa: PLC0415
    from .bench import ReplayServer, bench_dir, estimate, load_replay, replay_answers, run_bench, slug  # noqa: PLC0415
    from .compare import load_results, stability  # noqa: PLC0415
    from .probes import load_probes  # noqa: PLC0415

    keys = list(dict.fromkeys((read_key_list(args.only) if args.only else []) + list(args.scene or [])))
    if not keys:
        print("需要 --only 或 --scene", file=sys.stderr)
        return 2
    if args.estimate:
        est = estimate(args.pack, keys, args.character)
        lo, hi = est["input_tokens_range"]
        print(f"场景 {est['scenes']}，首轮调用 {est['calls']} 次，输入约 {est['input_chars']:,} 字"
              f"（约 {lo:,}–{hi:,} token，按每字 0.7–1.3 token 粗估；输出和重试另计）")
        if est["chunked"]:
            print("会切块的场景：" + "、".join(est["chunked"]))
        return 0
    baseline = baseline_results = None
    if args.baseline:
        path = Path(args.baseline)
        summary_file = path / "summary.json" if path.is_dir() else path
        if summary_file.exists():
            baseline = json.loads(summary_file.read_text(encoding="utf-8"))
        if path.is_dir():
            baseline_results = load_results(path)
    prices = (args.price_in, args.price_out) if args.price_in is not None and args.price_out is not None else None
    common = dict(character_id=args.character, concurrency=args.concurrency, timeout=args.timeout, prices=prices,
                  baseline=baseline, baseline_results=baseline_results, baseline_name=str(args.baseline or ""),
                  probes=load_probes(args.probes) if args.probes else None)
    repeats = max(1, args.repeats)
    sample = Path(args.only).stem if args.only else str(len(keys))
    out_root = Path(args.out) if args.out else bench_dir("replay" if args.replay else "api", repeats, sample=sample)
    if repeats > 1:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        out_root = out_root / f"{stamp}-{slug(args.label or args.model or 'replay')}-x{repeats}"

    async def run_all(call, mode: str, model: str, api_url: str, source: str = "") -> list[Path]:
        from .bench import write_fact_summary
        dirs = []
        for i in range(1, repeats + 1):
            if repeats > 1:
                print(f"第 {i}/{repeats} 次运行")
            run_dir = await run_bench(args.pack, keys, out_root, call=call, mode=mode, model=model, api_url=api_url,
                                      label=f"r{i}" if repeats > 1 else (args.label or ""), source=source, **common)
            if mode == "api" and not args.no_facts:
                fact_client = SimpleLLMClient(api_url, key, model, timeout=args.timeout, temperature=0)
                fact_report = await run_fact_benchmark(run_dir, keys, fact_client.text_chat, model,
                                                       concurrency=args.concurrency)
                print(f"时间事实候选：{fact_report['complete']}/{fact_report['selected']} 场景，"
                      f"模型调用 {fact_report['model_calls']} 次")
            else:
                write_fact_summary(run_dir, None, reason="回放模式" if mode == "replay" else "显式 --no-facts")
            dirs.append(run_dir)
        return dirs

    if args.replay:
        answers, skipped = replay_answers(args.pack, keys, load_replay(args.replay), args.character)
        if skipped:
            print("回放数据里没有、或需要切块而无法回放的场景（会记为失败）：" + "、".join(skipped))
        with ReplayServer(answers) as server:
            client = SimpleLLMClient(server.url, "replay", args.model or "replay", timeout=args.timeout)
            run_dirs = await run_all(client.text_chat, "replay", args.model or "replay", server.url, source=args.replay)
    else:
        if not (args.api_url and args.model):
            print("需要 --api-url 和 --model，或者用 --replay / --estimate", file=sys.stderr)
            return 2
        key = os.environ.get("CANON_API_KEY", "")
        if not key:
            print("缺少环境变量 CANON_API_KEY", file=sys.stderr)
            return 2
        client = SimpleLLMClient(args.api_url, key, args.model, timeout=args.timeout)
        run_dirs = await run_all(client.text_chat, "api", args.model, args.api_url)
    failed = 0
    for run_dir in run_dirs:
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        failed += summary["failed"]
        facts = summary.get("facts") or {}
        failed += facts.get("failed", 0) + len(facts.get("skipped", {}))
        print(f"成功 {summary['ok']}/{summary['scenes']}，首次通过 {summary['first_pass']}，"
              f"共调用 {summary['calls']} 次，总耗时 {summary['wall_seconds']}s")
        print(f"报告：{run_dir / 'report.md'}")
    if repeats > 1:
        stab = stability([load_results(d) for d in run_dirs])
        (out_root / "stability.json").write_text(json.dumps(stab, ensure_ascii=False, indent=1), encoding="utf-8")
        (out_root / "stability.md").write_text("\n".join(render_stability(stab, run_dirs)), encoding="utf-8")
        print(f"重测信度：{out_root / 'stability.md'}")
    return 0 if failed == 0 else 1


def render_stability(stab: dict, run_dirs: list) -> list[str]:
    def cell(v):
        return f"{v['mean']}（最低 {v['min']}）" if v else "—"

    return [f"# canon 抽取重测信度（{stab['runs']} 次运行，两两对比 {stab['pairs']} 组）", "",
            "同一配置多次运行之间的一致程度。事件按证据行对齐，κ 是机会校正后的渠道一致性。", "",
            "| 指标 | 平均（最低） |", "|---|---|",
            f"| 事件 F1 | {cell(stab['event_f1'])} |",
            f"| 渠道一致率 | {cell(stab['channel_agreement'])} |",
            f"| 渠道 Cohen's κ | {cell(stab['channel_kappa'])} |",
            f"| 每次的事件数 | {' / '.join(str(n) for n in stab['events_per_run'])} |", "",
            "运行：", "", *[f"- {d}" for d in run_dirs], ""]


async def cmd_compare(args) -> int:
    from .compare import compare_results, load_results, render_comparison, stability  # noqa: PLC0415

    runs = [load_results(p) for p in args.runs]
    if len(runs) == 2:
        lines = render_comparison(compare_results(runs[0], runs[1]), args.runs[0], args.runs[1])
    else:
        lines = render_stability(stability(runs), args.runs)
    text = "\n".join(lines)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已写出：{args.out}")
    else:
        print(text)
    return 0


async def judge_into(run_dir: Path, pack: Path | str, call, *, model: str, character_id: str = "amiya",
                     repeats: int = 1, concurrency: int = 2, timeout: float = 300, labels: str | None = None,
                     progress=None) -> tuple[dict, dict[str, str]]:
    """给一次基准运行跑 LLM 裁判：写 judge.jsonl，更新 summary.json 和 report.md，返回裁判汇总和失败的场景。"""
    from .bench import find_character, write_summary  # noqa: PLC0415
    from .compare import load_results  # noqa: PLC0415
    from .importer import load_pack  # noqa: PLC0415
    from .judge import judge_run, summarize_judge  # noqa: PLC0415

    _, scenes, characters, _ = load_pack(pack)
    character = find_character(characters, character_id)
    results = load_results(run_dir)
    label_map = None
    if labels:
        rows = (json.loads(ln) for ln in Path(labels).read_text(encoding="utf-8").splitlines() if ln.strip())
        label_map = {(x["scene"], x["event"]): x for x in rows}
    records, failures = await judge_run(call, scenes, results, character, repeats=repeats,
                                        concurrency=concurrency, timeout=timeout, progress=progress)
    with open(run_dir / "judge.jsonl", "w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    summary["judge"] = summarize_judge(records, failures, model=model, repeats=repeats, labels=label_map)
    write_summary(run_dir, summary)
    return summary["judge"], failures


async def cmd_judge(args) -> int:
    from ..utils.llm import SimpleLLMClient  # noqa: PLC0415
    from .compare import load_results  # noqa: PLC0415

    run_dir = Path(args.run)
    if not (run_dir / "summary.json").exists():
        print(f"{run_dir} 不是基准运行目录（没有 summary.json）", file=sys.stderr)
        return 2
    key = os.environ.get("CANON_JUDGE_API_KEY") or os.environ.get("CANON_API_KEY", "")
    if not key:
        print("缺少环境变量 CANON_JUDGE_API_KEY（或 CANON_API_KEY）", file=sys.stderr)
        return 2
    client = SimpleLLMClient(args.api_url, key, args.model, timeout=args.timeout, temperature=0)
    total = len(load_results(run_dir))
    done = [0]

    def progress(scene_key: str, status: str) -> None:
        done[0] += 1
        print(f"  [{done[0]}/{total}] {status:4} {scene_key}", flush=True)

    j, failures = await judge_into(run_dir, args.pack, client.text_chat, model=args.model, character_id=args.character,
                                   repeats=args.repeats, concurrency=args.concurrency, timeout=args.timeout,
                                   labels=args.labels, progress=progress)
    print(f"裁判 {j['events']} 个事件：引证召回率 {j['citation_recall']}，引证精确率 {j['citation_precision']}，"
          f"渠道支撑率 {j['channel_support']}")
    print(f"报告已更新：{run_dir / 'report.md'}")
    return 0 if not failures else 1



async def run_fact_pipeline(store, keys: list[str], call, model: str, out: Path,
                            *, concurrency: int = 2) -> dict:
    """Extract all eligible scenes and write resumable review artifacts."""
    import sqlite3
    import time
    from .fact_extract import suggest_all
    from .fact_review import build_review_bundle

    if any(path.exists() for path in (out, out.with_suffix(".review.json"), out.with_suffix(".report.json"))):
        raise ValueError(f"事实输出文件已存在，拒绝覆盖：{out}")
    eligible, skipped = [], {}
    for scene_key in keys:
        async with store.db.execute(
            "SELECT x.status FROM scenes s LEFT JOIN extractions x ON "
            "x.scene_key=s.scene_key AND x.scene_hash=s.scene_hash AND x.prompt_version=? "
            "WHERE s.scene_key=?", (PROMPT_VERSION, scene_key),
        ) as cur:
            row = await cur.fetchone()
        if row and row["status"] == "ok":
            eligible.append(scene_key)
        else:
            skipped[scene_key] = "缺少当前版本的成功事件抽取"
    done = [0]
    def progress(key, status, detail):
        done[0] += 1
        print(f"  [facts {done[0]}/{len(eligible)}] {status:6} {key}：{detail}", flush=True)
    calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    async def measured_call(prompt, system_prompt):
        nonlocal calls, prompt_tokens, completion_tokens
        calls += 1
        response = await call(prompt, system_prompt)
        usage = getattr(response, "usage", None)
        if isinstance(usage, dict):
            prompt_tokens += usage.get("prompt_tokens") or 0
            completion_tokens += usage.get("completion_tokens") or 0
        return response
    started = time.monotonic()
    report = await suggest_all(store, eligible, measured_call, model,
                               concurrency=concurrency, progress=progress)
    report["selected"] = len(keys)
    report["skipped"] = skipped
    report["model_calls"] = calls
    report["prompt_tokens"] = prompt_tokens
    report["completion_tokens"] = completion_tokens
    report["wall_seconds"] = round(time.monotonic() - started, 2)
    results = report.pop("results")
    report["scenes_with_candidates"] = sum(bool(result["facts"]) for result in results)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for result in results:
            fh.write(json.dumps(result, ensure_ascii=False) + "\n")
    db = sqlite3.connect(store.path)
    db.row_factory = sqlite3.Row
    try:
        bundle = build_review_bundle(db, results)
    finally:
        db.close()
    report["review_groups"] = len(bundle["review_groups"])
    out.with_suffix(".review.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def write_fact_review_page(store, keys: list[str], report: dict, out: Path,
                                 review_out: Path) -> None:
    """Render the event and fact-candidate review page from one completed fact pass."""
    candidates = {item["scene_key"]: item["facts"] for item in
                  (json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line)}
    dumps = []
    for key in keys:
        scene = await store.scene_dump(key)
        if scene is None:
            continue
        if key in candidates:
            scene["fact_candidates"] = candidates[key]
        scene["fact_error"] = report["errors"].get(key) or report["skipped"].get(key)
        dumps.append(scene)
    review_out.write_text(review_page(dumps), encoding="utf-8")


async def run_fact_benchmark(run_dir: Path, keys: list[str], call, model: str,
                             *, concurrency: int = 2, out: Path | None = None) -> dict:
    """Run the candidate stage and add its result to the benchmark report."""
    from .bench import write_fact_summary
    out = out or run_dir / "facts-candidates.jsonl"
    store = CanonStore(run_dir / "canon.sqlite")
    await store.open()
    try:
        report = await run_fact_pipeline(store, keys, call, model, out, concurrency=concurrency)
        await write_fact_review_page(store, keys, report, out, run_dir / "review.html")
    finally:
        await store.close()
    write_fact_summary(run_dir, report, out)
    return report


async def cmd_fact_suggest(args) -> int:
    from ..utils.llm import SimpleLLMClient
    key = os.environ.get("CANON_API_KEY", "")
    if not key:
        raise ValueError("缺少环境变量 CANON_API_KEY")
    store = CanonStore(args.db)
    await store.open()
    client = SimpleLLMClient(args.api_url, key, args.model, timeout=args.timeout, temperature=0)
    out = Path(args.out) if args.out else (
        Path(__file__).parents[2] / ".dev_data/canon" / version_tag(PROMPT_VERSION) / "facts" /
        (datetime.datetime.now().strftime("%Y%m%d-%H%M%S") + "-candidates.jsonl")
    )
    try:
        async with store.db.execute("SELECT scene_key FROM scenes ORDER BY narrative_pos") as cur:
            keys = [row["scene_key"] for row in await cur.fetchall()]
        chosen = read_keys(args.only) if args.only else set(keys)
        unknown = chosen - set(keys)
        if unknown:
            raise ValueError(f"场景不在数据库中：{sorted(unknown)[:5]}")
        report = await run_fact_pipeline(store, [k for k in keys if k in chosen], client.text_chat,
                                         args.model, out, concurrency=args.concurrency)
    finally:
        await store.close()
    print(f"事实候选与审阅包：{out}、{out.with_suffix('.review.json')}")
    print(f"完成 {report['complete']}/{report['selected']}，失败 {report['failed']}，跳过 {len(report['skipped'])}")
    return 0 if not report["failed"] and not report["skipped"] else 1


async def cmd_archive_import(args) -> int:
    store = CanonStore(args.db)
    await store.open()
    try:
        counts = await import_archives(store, args.pack, story_pack=args.story_pack)
    finally:
        await store.close()
    print(f"档案：新增 {counts['added']}，更新 {counts['updated']}，删除 {counts['deleted']}，"
          f"未变 {counts['unchanged']}")
    if args.story_pack:
        print(f"实体种子：新增 {counts['seed_added']}，更正类型 {counts['seed_retyped']}，"
              f"档案链接 {counts['seed_archive_links']}")
    return 0


async def cmd_fact_apply(args) -> int:
    import sqlite3
    from .temporal import apply_reviewed_facts
    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    try:
        version = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if version is None or version[0] not in ("3", "4"):
            raise ValueError("facts-apply 需要 schema_version 3 或以上；请先在数据库副本上运行 canon status")
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if payload.get("format") == "canon-fact-review-v1":
            from .fact_review import approved_payload
            payload = approved_payload(payload)
        apply_reviewed_facts(db, payload)
    finally:
        db.close()
    print("已导入经过审阅的时间点、事实与证据链")
    return 0


async def cmd_fact_query(args) -> int:
    import sqlite3
    from .temporal import resolve
    uri = Path(args.db).resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    try:
        decision = resolve(db, args.subject, args.predicate, as_of=args.as_of)
    finally:
        db.close()
    print(json.dumps({
        "status": decision.status, "as_of": decision.as_of,
        "reason": decision.reason, "facts": decision.facts,
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m core.canon.cli", description="canon 原作剧情记忆")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import", help="导入 story_pack")
    p.add_argument("--pack", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--api-url")
    p.add_argument("--model")
    p.add_argument("--only", help="只处理这个文件里列出的 scene_key（每行一个），例如 pilot.txt")
    p.add_argument("--character", default="amiya")
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--embed", action="store_true",
                   help="用 Moirai 共享 embedding（run_config.py 的 RETRIEVAL_*）给事件编码向量；不给就不编码")
    p.add_argument("--facts", action="store_true", help="事件导入后抽取全范围时间事实候选")
    p.add_argument("--facts-out", help="时间事实候选输出文件")
    p = sub.add_parser("status", help="查看 canon.sqlite 状态")
    p.add_argument("--db", required=True)
    p = sub.add_parser("dump", help="导出审阅页（HTML）")
    p.add_argument("--db", required=True)
    p.add_argument("--scene", action="append")
    p.add_argument("--only")
    p.add_argument("--out")
    p = sub.add_parser("bench", help="抽取基准：真实接口、回放或只做估算")
    p.add_argument("--pack", required=True)
    p.add_argument("--only", help="场景清单文件（每行一个 scene_key），例如 pilot.txt")
    p.add_argument("--scene", action="append", help="追加单个场景，可重复")
    p.add_argument("--estimate", action="store_true", help="只估算调用次数和输入量，不调用接口")
    p.add_argument("--replay", help="回放已有结果：试跑目录（index.json + out/）或上次基准的运行目录")
    p.add_argument("--api-url")
    p.add_argument("--model")
    p.add_argument("--character", default="amiya")
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--out", help="运行目录的上级目录；默认 .dev_data/canon/<prompt 版本>/<样本>/ 下的 api/、replay/ 或 repeats/")
    p.add_argument("--baseline", help="对比用的 summary.json 或运行目录")
    p.add_argument("--price-in", type=float, help="输入单价，每百万 token")
    p.add_argument("--price-out", type=float, help="输出单价，每百万 token")
    p.add_argument("--label", help="运行目录名里的标签，默认是模式加模型名")
    p.add_argument("--probes", help="金标准探针文件（JSONL），例如 Arknights-Texts/eval/canon_extract_probes.jsonl")
    p.add_argument("--repeats", type=int, default=1, help="同一配置跑几次并报告重测信度（费用随之翻倍）")
    p.add_argument("--no-facts", action="store_true", help="仅跑事件基准；真实接口默认抽取时间事实候选")
    p = sub.add_parser("compare", help="对比两次运行（逐事件），或三次以上运行的重测信度")
    p.add_argument("runs", nargs="+", help="基准运行目录、试跑目录或 canon.sqlite")
    p.add_argument("--out", help="把结果写到这个 Markdown 文件")
    p = sub.add_parser("judge", help="用 LLM 裁判给一次基准运行打分（会把引用的原文行发给裁判接口）")
    p.add_argument("--run", required=True, help="基准运行目录")
    p.add_argument("--pack", required=True)
    p.add_argument("--api-url", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--character", default="amiya")
    p.add_argument("--repeats", type=int, default=1, help="每个场景判几次，≥2 时报告重测一致性（建议 3）")
    p.add_argument("--labels", help="人工标注（JSONL：scene、event、support、channel_ok），报告和裁判的一致性")
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--timeout", type=float, default=300)
    p = sub.add_parser("facts-suggest", help="单独抽取时间事实候选，需要人工审阅；会调用模型")
    p.add_argument("--db", required=True)
    p.add_argument("--api-url", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--only", help="场景清单文件")
    p.add_argument("--out", help="候选 JSONL 输出；默认 .dev_data/canon/<prompt 版本>/facts/时间戳-candidates.jsonl")
    p.add_argument("--timeout", type=float, default=300)
    p.add_argument("--concurrency", type=int, default=2)
    p = sub.add_parser("archive-import", help="导入 archive_pack（干员档案、NPC 情报、敌人图鉴）；不调用模型")
    p.add_argument("--pack", required=True, help="archive_pack 目录")
    p.add_argument("--db", required=True)
    p.add_argument("--story-pack", help="同时按这个 story_pack 的实体种子刷新实体类型和档案链接")
    p = sub.add_parser("facts-apply", help="原子导入经人工审阅的时间事实包")
    p.add_argument("--db", required=True)
    p.add_argument("--input", required=True)
    p = sub.add_parser("facts-query", help="查询事实的世界时间有效性与证据链")
    p.add_argument("--db", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--predicate", required=True, choices=("location","custody","affiliation","life_status"))
    p.add_argument("--as-of", help="世界时间点 ID；省略表示查询覆盖锚点")
    args = ap.parse_args(argv)
    if args.cmd == "compare" and len(args.runs) < 2:
        ap.error("compare 至少需要两个运行")
    handler = {"import": cmd_import, "status": cmd_status, "dump": cmd_dump, "bench": cmd_bench,
               "compare": cmd_compare, "judge": cmd_judge,
               "facts-suggest": cmd_fact_suggest, "facts-apply": cmd_fact_apply,
               "facts-query": cmd_fact_query, "archive-import": cmd_archive_import}[args.cmd]
    return asyncio.run(handler(args))


if __name__ == "__main__":
    sys.exit(main())
