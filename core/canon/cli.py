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

from .importer import Importer, encoder_identity
from .prompt import PROMPT_VERSION
from .store import CanonStore

CHANNEL_LABEL = {"experienced": "亲历", "witnessed": "在场目睹", "told": "听人讲述",
                 "recalled": "回忆", "unstated": "文本未表明是否知情"}


def read_keys(path: str) -> set[str]:
    return {ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()}


def read_key_list(path: str) -> list[str]:
    return list(dict.fromkeys(ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()))


def make_encoder(name: str | None):
    if not name:
        return None
    from ..embedding.encoder import SentenceTransformerEncoder  # noqa: PLC0415
    return SentenceTransformerEncoder(name)


async def cmd_import(args) -> int:
    encoder = make_encoder(args.encoder)
    if encoder is not None and hasattr(encoder, "load"):
        await encoder.load()
    dim, enc_id = encoder_identity(encoder)
    store = CanonStore(args.db)
    await store.open(vec_dim=dim, encoder_id=enc_id)
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

    done = [0]

    def progress(key: str, status: str) -> None:
        done[0] += 1
        print(f"  [{done[0]}] {status:6} {key}", flush=True)

    importer = Importer(store, call, model=args.model or "", character=args.character,
                        concurrency=args.concurrency, timeout=args.timeout, encoder=encoder, progress=progress)
    try:
        report = await importer.run(args.pack, only=read_keys(args.only) if args.only else None)
    finally:
        await store.close()
    print("\n".join(report.lines()))
    return 0 if not report.failed else 1


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
        return " ".join(f'<a class="ref" data-l="{idx.get(k, 0)}">L{idx.get(k, "?")}</a>' for k in keys)

    left = []
    for ln in d["lines"]:
        spk = f'<b>{_esc(ln["speaker"])}</b>：' if ln["speaker"] else ""
        left.append(f'<div class="ln" id="{_esc(d["scene_key"])}-L{ln["idx"]}" data-l="{ln["idx"]}">'
                    f'<span class="no">L{ln["idx"]}</span><span class="k">{_esc(ln["kind"])}</span>'
                    f'{spk}{_esc(ln["text"])}</div>')
    x = d.get("extraction") or {}
    right = [f'<p class="meta">抽取：{_esc(x.get("status"))}，尝试 {_esc(x.get("attempts"))} 次，'
             f'模型 {_esc(x.get("model"))}，{_esc(x.get("prompt_version"))}，'
             f'token {_esc(x.get("prompt_tokens"))}/{_esc(x.get("completion_tokens"))}</p>']
    if x.get("error"):
        right.append(f'<p class="err">{_esc(x["error"])}</p>')
    for ev in d["events"]:
        views = "".join(
            f'<div class="view">{_esc(v["character"])}：<b>{_esc(CHANNEL_LABEL.get(v["channel"], v["channel"]))}</b>'
            f'（{_esc(v["channel"])}）{_esc(v["note"] or "")} {refs(v["evidence"])}</div>' for v in ev["views"])
        ents = "、".join(f'{_esc(e["name"])}<small>/{_esc(e["type"])}</small>' for e in ev["entities"])
        lines_attr = " ".join(str(idx.get(k, 0)) for k in ev["evidence"])
        beats = "".join(f'<li>{_esc(b["text"])} {refs(b["evidence"])}</li>' for b in ev.get("beats") or [])
        right.append(
            f'<div class="ev" data-lines="{lines_attr}"><div class="t">{_esc(ev["local_id"])} · {_esc(ev["topic"])}'
            f' <small>{_esc(ev["in_world_time"])}{(" · " + _esc(ev["in_world_note"])) if ev["in_world_note"] else ""}</small></div>'
            f'<div>{_esc(ev["summary"])}</div>'
            + (f'<ul class="beats">{beats}</ul>' if beats else "") +
            f'<div class="sub">参与：{_esc("、".join(json.loads(ev["participants"])))}；实体：{ents or "无"}</div>'
            f'<div class="sub">证据：{refs(ev["evidence"])}</div>{views}</div>')
    for ep in d["episodes"]:
        right.append(f'<div class="box"><div class="t">第一人称摘要（{_esc(ep["character"])}）</div>{_esc(ep["text"])}</div>')
    if d["cognitions"]:
        items = "".join(f'<li>{_esc(c["target"])}：{_esc(c["stance"])} {refs(json.loads(c["evidence"]))}</li>'
                        for c in d["cognitions"])
        right.append(f'<div class="box"><div class="t">认知</div><ul>{items}</ul></div>')
    if d["edges"]:
        local = {ev["event_id"]: ev["local_id"] for ev in d["events"]}
        items = "".join(
            f'<li>{_esc(local.get(e["src"]))} → {_esc(local.get(e["dst"]))} {_esc(e["type"])}'
            f'（{"明说" if e["explicit"] else "推断"}，{e["confidence"]:.2f}）{refs(json.loads(e["evidence"]))}</li>'
            for e in d["edges"])
        right.append(f'<div class="box"><div class="t">事件关系</div><ul>{items}</ul></div>')
    return (f'<section class="scene"><h2>{_esc(d["anchor"])}</h2><p class="meta">{_esc(d["scene_key"])} · '
            f'hash {_esc(d["scene_hash"])} · 叙事位置 {d["narrative_pos"]}</p>'
            f'<p class="meta">官方简介：{_esc(d["official_summary"] or "无")}</p>'
            f'<div class="cols"><div class="left">{"".join(left)}</div><div class="right">{"".join(right)}</div></div></section>')


PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>canon 抽取审阅</title>
<style>
body{font:14px/1.6 system-ui,sans-serif;margin:0;padding:16px;background:#fafafa;color:#222}
h2{margin:24px 0 4px}.meta{color:#666;margin:2px 0}.err{color:#b00}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.left,.right{max-height:85vh;overflow:auto;background:#fff;border:1px solid #ddd;border-radius:6px;padding:8px}
.ln{padding:1px 4px;border-radius:3px}.ln.hl{background:#fff3b0}
.no{display:inline-block;width:44px;color:#999}.k{display:inline-block;width:84px;color:#8a8;font-size:12px}
.ev,.box{border:1px solid #e3e3e3;border-radius:6px;padding:6px 8px;margin:6px 0}.ev:hover{border-color:#e0b000}
.t{font-weight:600}.sub,.view,.beats{font-size:13px;color:#444}.beats{margin:2px 0;padding-left:18px}.ref{color:#06c;cursor:pointer;font-size:12px}
nav a{margin-right:10px}
@media (max-width:900px){.cols{grid-template-columns:1fr}}
</style></head><body><h1>canon 抽取审阅</h1><nav>%s</nav>%s
<script>
function hl(sec,ls){sec.querySelectorAll('.ln.hl').forEach(e=>e.classList.remove('hl'));
 ls.forEach(n=>{const e=sec.querySelector('.ln[data-l="'+n+'"]');if(e)e.classList.add('hl')});
 const f=sec.querySelector('.ln[data-l="'+ls[0]+'"]');if(f)f.scrollIntoView({block:'center',behavior:'smooth'})}
document.querySelectorAll('.ev').forEach(ev=>ev.addEventListener('mouseenter',()=>
 hl(ev.closest('.scene'),ev.dataset.lines.split(' ').filter(Boolean))));
document.querySelectorAll('.ref').forEach(r=>r.addEventListener('click',e=>{e.stopPropagation();
 hl(r.closest('.scene'),[r.dataset.l])}));
</script></body></html>"""


def review_page(dumps: list[dict]) -> str:
    """把 scene_dump 的结果按叙事顺序拼成一个审阅页。"""
    found = sorted(dumps, key=lambda d: d["narrative_pos"])
    nav = "".join(f'<a href="#s{i}">{_esc(d["anchor"])}</a>' for i, d in enumerate(found))
    body = "".join(render_scene(d).replace('<section class="scene">', f'<section class="scene" id="s{i}">', 1)
                   for i, d in enumerate(found))
    return PAGE % (nav, body)


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
    out_root = Path(args.out) if args.out else bench_dir("replay" if args.replay else "api", repeats)
    if repeats > 1:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        out_root = out_root / f"{stamp}-{slug(args.label or args.model or 'replay')}-x{repeats}"

    async def run_all(call, mode: str, model: str, api_url: str, source: str = "") -> list[Path]:
        dirs = []
        for i in range(1, repeats + 1):
            if repeats > 1:
                print(f"第 {i}/{repeats} 次运行")
            dirs.append(await run_bench(args.pack, keys, out_root, call=call, mode=mode, model=model, api_url=api_url,
                                        label=f"r{i}" if repeats > 1 else (args.label or ""), source=source, **common))
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
    p.add_argument("--encoder", help="本地 sentence-transformers 模型名；不给就不编码向量")
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
    p.add_argument("--out", help="运行目录的上级目录；默认按类别放在 .dev_data/canon/bench/ 的 api/、replay/ 或 repeats/ 下")
    p.add_argument("--baseline", help="对比用的 summary.json 或运行目录")
    p.add_argument("--price-in", type=float, help="输入单价，每百万 token")
    p.add_argument("--price-out", type=float, help="输出单价，每百万 token")
    p.add_argument("--label", help="运行目录名里的标签，默认是模式加模型名")
    p.add_argument("--probes", help="金标准探针文件（JSONL），例如 Arknights-Texts/eval/canon_extract_probes.jsonl")
    p.add_argument("--repeats", type=int, default=1, help="同一配置跑几次并报告重测信度（费用随之翻倍）")
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
    args = ap.parse_args(argv)
    if args.cmd == "compare" and len(args.runs) < 2:
        ap.error("compare 至少需要两个运行")
    handler = {"import": cmd_import, "status": cmd_status, "dump": cmd_dump, "bench": cmd_bench,
               "compare": cmd_compare, "judge": cmd_judge}[args.cmd]
    return asyncio.run(handler(args))


if __name__ == "__main__":
    sys.exit(main())
