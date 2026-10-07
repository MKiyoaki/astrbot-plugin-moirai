"""canon 数据集处理：导入 story_pack 与 archive_pack、跑抽取基准与裁判、写回人工审阅过的时间事实与历法坐标。

用法（在插件根目录下；也可以经 src/main.py 的 canon_* 实验调用）：
  python src/tools/canon_data.py import --pack <story_pack> --db <canon.sqlite> --api-url <url> --model <name> [--only pilot.txt]
  python src/tools/canon_data.py bench --pack <story_pack> (--only pilot.txt | --scene <key> ...) \
      (--estimate | --replay <试跑目录或运行目录> | --api-url <url> --model <name>) \
      [--probes <探针文件>] [--baseline <运行目录>] [--repeats N]
  python src/tools/canon_data.py compare <运行目录> <运行目录> [...]
  python src/tools/canon_data.py judge --run <运行目录> --pack <story_pack> --api-url <url> --model <name> [--repeats 3]
  python src/tools/canon_data.py facts-suggest --db <canon.sqlite> --api-url <url> --model <name>
  python src/tools/canon_data.py archive-import --pack <archive_pack> --db <canon.sqlite>
  python src/tools/canon_data.py facts-apply --db <canon.sqlite> --input <审阅过的事实包>
  python src/tools/canon_data.py calendar-apply --db <canon.sqlite> --entries <年表 JSON>

API key 只从环境变量读取：抽取用 CANON_API_KEY，裁判用 CANON_JUDGE_API_KEY（没有就用 CANON_API_KEY）。审阅页和基准输出里有剧情原文，只能留在本机。
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core_eval.canon.bench import version_tag
from core.canon.builder.importer import Importer, encoder_identity, import_archives
from core.utils.prompts.prompt_canon_utils import PROMPT_VERSION
from core.canon.storage.store import CanonStore
from core.utils.paths import PLUGIN_ROOT
from core_eval.canon.judge import judge_into
from core_eval.canon.compare import render_stability
from core_eval.canon.fact_bench import run_fact_benchmark, run_fact_pipeline, write_fact_review_page
from core.api.retrieval import open_shared_encoder


def read_keys(path: str) -> set[str]:
    return {ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()}


def read_key_list(path: str) -> list[str]:
    return list(dict.fromkeys(ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines() if ln.strip()))


async def cmd_import(args) -> int:
    call = None
    if args.api_url and args.model:
        key = os.environ.get("CANON_API_KEY", "")
        if not key:
            print("缺少环境变量 CANON_API_KEY", file=sys.stderr)
            return 2
        from core.utils.llm import SimpleLLMClient  # noqa: PLC0415
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


async def cmd_bench(args) -> int:
    from core.utils.llm import SimpleLLMClient  # noqa: PLC0415
    from core_eval.canon.bench import ReplayServer, bench_dir, estimate, load_replay, replay_answers, run_bench, slug  # noqa: PLC0415
    from core_eval.canon.compare import load_results, stability  # noqa: PLC0415
    from core_eval.canon.probes import load_probes  # noqa: PLC0415

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
        from core_eval.canon.bench import write_fact_summary
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


async def cmd_compare(args) -> int:
    from core_eval.canon.compare import compare_results, load_results, render_comparison, stability  # noqa: PLC0415

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


async def cmd_judge(args) -> int:
    from core.utils.llm import SimpleLLMClient  # noqa: PLC0415
    from core_eval.canon.compare import load_results  # noqa: PLC0415

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


async def cmd_fact_suggest(args) -> int:
    from core.utils.llm import SimpleLLMClient
    key = os.environ.get("CANON_API_KEY", "")
    if not key:
        raise ValueError("缺少环境变量 CANON_API_KEY")
    store = CanonStore(args.db)
    await store.open()
    client = SimpleLLMClient(args.api_url, key, args.model, timeout=args.timeout, temperature=0)
    out = Path(args.out) if args.out else (
        PLUGIN_ROOT / ".dev_data/canon" / version_tag(PROMPT_VERSION) / "facts" /
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
    from core.canon.domain.temporal import apply_reviewed_facts
    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    try:
        version = db.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        if version is None or version[0] not in ("3", "4", "5", "6"):
            raise ValueError("facts-apply 需要 schema_version 3 或以上；请先在数据库副本上运行 canon status")
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if payload.get("format") == "canon-fact-review-v1":
            from core.canon.builder.fact_review import approved_payload
            payload = approved_payload(payload)
        apply_reviewed_facts(db, payload)
    finally:
        db.close()
    print("已导入经过审阅的时间点、事实与证据链")
    return 0


async def cmd_calendar_apply(args) -> int:
    import sqlite3
    from collections import Counter
    from core.canon.domain.calendar import apply_event_times, resolve_event_times
    from core.canon.storage.store import ensure_schema
    payload = json.loads(Path(args.entries).read_text(encoding="utf-8"))
    db = sqlite3.connect(args.db)
    try:
        ensure_schema(db)
        times = resolve_event_times(db, payload["entries"])
        apply_event_times(db, times, payload.get("source") or Path(args.entries).name)
        total = db.execute("SELECT count(*) FROM events").fetchone()[0]
    finally:
        db.close()
    origins = Counter(item.origin for item in times.values())
    print(f"已定位 {len(times)}/{total} 个事件的世界时间；来源："
          + "、".join(f"{name} {count}" for name, count in origins.most_common()))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python src/tools/canon_data.py", description="canon 数据集处理：导入、基准、裁判与人工审阅后的写回")
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
                   help="用 Moirai 共享 embedding（configs/retrieval/）给事件编码向量；不给就不编码")
    p.add_argument("--facts", action="store_true", help="事件导入后抽取全范围时间事实候选")
    p.add_argument("--facts-out", help="时间事实候选输出文件")
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
    p = sub.add_parser("calendar-apply", help="按场景字幕和外部年表给事件定世界时间坐标；不调用模型，只存坐标")
    p.add_argument("--db", required=True)
    p.add_argument("--entries", required=True, help="年表条目 JSON，例如 src/tools/canon_terra_timeline.py 的输出")
    args = ap.parse_args(argv)
    if args.cmd == "compare" and len(args.runs) < 2:
        ap.error("compare 至少需要两个运行")
    handler = {"import": cmd_import, "bench": cmd_bench, "compare": cmd_compare, "judge": cmd_judge,
               "facts-suggest": cmd_fact_suggest, "facts-apply": cmd_fact_apply,
               "archive-import": cmd_archive_import, "calendar-apply": cmd_calendar_apply}[args.cmd]
    return asyncio.run(handler(args))


if __name__ == "__main__":
    sys.exit(main())
