"""canon 抽取基准：用真实或回放的模型接口跑一组场景，统计成功率、重试、耗时、token 与质量指标。

每次运行都在独立目录里新建 canon.sqlite，不读取也不写入已有的抽取缓存，
走的是和正式导入完全相同的 Importer → extract_scene → CanonStore 路径。
运行目录里有剧情原文（审阅页、失败时的原始回复），只能留在本机。
"""
from __future__ import annotations

import collections
import datetime
import json
import re
import sqlite3
import statistics
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .audit import audit_scene, person_lexicon, summarize_audits
from .compare import compare_results, render_comparison
from .extract import Call, quality_flags
from .importer import Importer, load_pack
from .probes import evaluate_probes
from .prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt, chunk_ranges
from .store import CanonStore

RETRY_MARK = "\n\n[上次输出的问题]"
TOKENS_PER_CHAR = (0.7, 1.3)
CANON_ROOT = Path(".dev_data/canon")


def version_tag(prompt_version: str) -> str:
    """canon-extract-v7 → v7。"""
    return "v" + prompt_version.rpartition("-v")[2] if "-v" in prompt_version else prompt_version


def bench_dir(mode: str, repeats: int = 1, root: Path | str = CANON_ROOT, *,
              version: str | None = None, sample: str = "custom") -> Path:
    """运行目录按抽取 prompt 版本、样本和运行方式分层，例如 v7/100/api/；同一配置的多次运行在 repeats/。"""
    return Path(root) / (version or version_tag(PROMPT_VERSION)) / sample / ("repeats" if repeats > 1 else mode)


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_")[:60] or "run"


def find_character(characters: list[dict], character_id: str) -> dict:
    character = next((c for c in characters if c["character"] == character_id), None)
    if character is None:
        raise ValueError(f"story_pack 里没有目标角色 {character_id}")
    return character


def estimate(pack_dir: Path | str, keys: list[str], character_id: str) -> dict:
    """不调用接口，估算一次运行的调用次数和输入量（按每块第一次调用算，重试另计）。"""
    _, scenes, characters, _ = load_pack(pack_dir)
    character = find_character(characters, character_id)
    rows = []
    for key in keys:
        scene = scenes[key]
        prev = scenes.get(scene.get("prev_scene_key") or "")
        ranges = chunk_ranges(scene["lines"])
        chars = sum(len(SYSTEM_PROMPT) + len(build_user_prompt(scene, character, prev, a, b)) for a, b in ranges)
        rows.append({"scene": key, "chunks": len(ranges), "input_chars": chars})
    total = sum(r["input_chars"] for r in rows)
    return {"scenes": len(rows), "calls": sum(r["chunks"] for r in rows), "input_chars": total,
            "input_tokens_range": [round(total * TOKENS_PER_CHAR[0]), round(total * TOKENS_PER_CHAR[1])],
            "chunked": [r["scene"] for r in rows if r["chunks"] > 1], "rows": rows}


def load_replay(path: Path | str) -> dict[str, str]:
    """读取可回放的抽取结果：试跑目录（index.json + out/）或者一个 canon.sqlite（含上次基准的运行目录）。"""
    path = Path(path)
    if (path / "index.json").exists() and (path / "out").is_dir():
        index = json.loads((path / "index.json").read_text(encoding="utf-8"))
        return {meta["scene_key"]: (path / "out" / f"{no}.json").read_text(encoding="utf-8")
                for no, meta in index.items() if (path / "out" / f"{no}.json").exists()}
    db = path / "canon.sqlite" if path.is_dir() else path
    if not db.exists():
        raise ValueError(f"{path} 既不是试跑目录，也没有 canon.sqlite")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT scene_key, raw_json FROM extractions WHERE status='ok' ORDER BY created_at").fetchall()
    finally:
        con.close()
    return {key: raw for key, raw in rows}


class ReplayServer:
    """本机的 OpenAI 兼容接口：按 user prompt 返回事先保存的回复，零成本走一遍真实的 HTTP 调用路径。

    usage 里的 token 数是字符数，不是真实计费。没有对应回复的请求返回 404，按接口失败处理。
    """

    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = answers
        self.requests = 0
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                server.requests += 1
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                messages = body.get("messages") or []
                user = next((m["content"] for m in messages if m.get("role") == "user"), "")
                system = next((m["content"] for m in messages if m.get("role") == "system"), "")
                text = server.answers.get(user.split(RETRY_MARK)[0])
                if text is None:
                    payload, status = {"error": {"message": "回放数据里没有这个 prompt"}}, 404
                else:
                    payload, status = {"choices": [{"message": {"role": "assistant", "content": text}}],
                                       "usage": {"prompt_tokens": len(system) + len(user),
                                                 "completion_tokens": len(text)}}, 200
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:
                return None

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._httpd.server_address[1]}/v1"

    def __enter__(self) -> "ReplayServer":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


def replay_answers(pack_dir: Path | str, keys: list[str], stored: dict[str, str], character_id: str) -> tuple[dict, list]:
    """把按场景保存的回复换成按 user prompt 查找。切块的场景回放不了，原样返回在第二个值里。"""
    _, scenes, characters, _ = load_pack(pack_dir)
    character = find_character(characters, character_id)
    answers, skipped = {}, []
    for key in keys:
        scene = scenes[key]
        if key not in stored or len(chunk_ranges(scene["lines"])) > 1:
            skipped.append(key)
            continue
        prev = scenes.get(scene.get("prev_scene_key") or "")
        answers[build_user_prompt(scene, character, prev)] = stored[key]
    return answers, skipped


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int(round(q * (len(values) - 1))))], 2)


def error_kind(errors: list[str]) -> str:
    """一次失败调用的类型：接口失败（没拿到回复）、JSON 格式错（拿到了但解析不了）、校验不通过。"""
    if any(e.startswith("调用失败") for e in errors):
        return "接口失败"
    if any("不是合法的 JSON" in e for e in errors):
        return "JSON 格式错"
    return "校验不通过"


async def run_bench(pack_dir: Path | str, keys: list[str], out_root: Path | str, *, call: Call, mode: str,
                    model: str, api_url: str = "", character_id: str = "amiya", concurrency: int = 2,
                    timeout: float = 300, prices: tuple[float, float] | None = None,
                    baseline: dict | None = None, baseline_results: dict[str, dict] | None = None,
                    baseline_name: str = "", probes: list[dict] | None = None, label: str = "",
                    source: str = "", echo=print, on_call=None, on_scene=None) -> Path:
    """跑一次基准，返回运行目录。目录里有 summary.json、results.jsonl、report.md、review.html 和 canon.sqlite。

    probes 给了就用金标准探针评分；baseline_results 给了就和基线逐事件对齐对比。
    on_call(key, 记录) 在每次模型调用后、on_scene(key, 状态) 在每个场景结束后调用，供实时显示进度。
    """
    _, scenes, characters, seeds = load_pack(pack_dir)
    character = find_character(characters, character_id)
    lexicon = person_lexicon(seeds, character)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(out_root) / f"{stamp}-{slug(label or f'{mode}-{model}')}"
    run_dir.mkdir(parents=True, exist_ok=False)
    calls: dict[str, list[dict]] = collections.defaultdict(list)

    def observer(key: str, record: dict) -> None:
        record = dict(record)
        text = record.pop("response", None)
        if not record["ok"] and text:
            name = f"{slug(key)}-c{record['chunk']}-a{record['attempt']}.txt"
            (run_dir / "failures").mkdir(exist_ok=True)
            (run_dir / "failures" / name).write_text(text, encoding="utf-8")
            record["response_file"] = f"failures/{name}"
        calls[key].append(record)
        if on_call:
            on_call(key, record)

    done = [0]

    def progress(key: str, status: str) -> None:
        done[0] += 1
        seconds = sum(c["seconds"] for c in calls[key])
        echo(f"  [{done[0]}/{len(keys)}] {status:6} 调用 {len(calls[key])} 次 {seconds:6.1f}s  {key}")
        if on_scene:
            on_scene(key, status)

    store = CanonStore(run_dir / "canon.sqlite")
    await store.open()
    started_at = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    started = time.monotonic()
    results: dict[str, dict | None] = {}
    try:
        report = await Importer(store, call, model=model, character=character_id, concurrency=concurrency,
                                timeout=timeout, progress=progress, observer=observer).run(pack_dir, only=set(keys))
        wall = time.monotonic() - started
        rows = []
        crashed = dict(report.failures)
        for key in keys:
            scene = scenes[key]
            async with store.db.execute(
                    "SELECT status, error, attempts, prompt_tokens, completion_tokens, raw_json FROM extractions "
                    "WHERE scene_key=? AND scene_hash=? AND prompt_version=?",
                    (key, scene["scene_hash"], PROMPT_VERSION)) as cur:
                ext = await cur.fetchone()
            result = json.loads(ext["raw_json"]) if ext and ext["raw_json"] else None
            results[key] = result
            chunks = len(chunk_ranges(scene["lines"]))
            status = ext["status"] if ext else "error"
            prev = scenes.get(scene.get("prev_scene_key") or "") or {}
            rows.append({
                "scene": key, "anchor": scene["anchor"], "status": status, "chunks": chunks,
                "calls": len(calls[key]), "first_pass": status == "ok" and len(calls[key]) == chunks,
                "seconds": round(sum(c["seconds"] for c in calls[key]), 2),
                "prompt_tokens": ext["prompt_tokens"] if ext else None,
                "completion_tokens": ext["completion_tokens"] if ext else None,
                "error": (ext["error"] if ext else None) or crashed.get(key),
                "call_log": calls[key],
                "quality": quality_flags(result) if result else {},
                "audit": audit_scene(scene, result, character, lexicon=lexicon,
                                     context=prev.get("official_summary") or "") if result else None,
            })
        dumps = [d for d in [await store.scene_dump(k) for k in keys] if d]
    finally:
        await store.close()

    summary = summarize_run(rows, mode=mode, model=model, api_url=api_url, wall=wall, started_at=started_at,
                            concurrency=concurrency, timeout=timeout, prices=prices, run=run_dir.name,
                            source=source)
    if probes is not None:
        summary["probes"] = evaluate_probes(probes, scenes, results)
    if baseline is not None:
        summary["baseline"] = slim(baseline)
    if baseline_results is not None:
        summary["baseline_name"] = baseline_name or (baseline or {}).get("run", "")
        summary["baseline_compare"] = compare_results(baseline_results, {k: v for k, v in results.items() if v})
    if summary["tokens"] and mode != "replay":
        summary["projection"] = project_full(pack_dir, [r["scene"] for r in rows if r["prompt_tokens"] is not None],
                                             character_id, summary["tokens"], prices)
    with open(run_dir / "results.jsonl", "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    write_summary(run_dir, summary, rows)
    from .cli import review_page  # noqa: PLC0415
    (run_dir / "review.html").write_text(review_page(dumps), encoding="utf-8")
    return run_dir


def slim(summary: dict) -> dict:
    """作为基线嵌进别的运行时，去掉逐条明细和嵌套的基线。"""
    out = {k: v for k, v in summary.items() if k not in ("baseline", "baseline_compare")}
    if out.get("probes"):
        out["probes"] = {k: v for k, v in out["probes"].items() if k != "items"}
    if out.get("judge"):
        out["judge"] = {k: v for k, v in out["judge"].items() if k != "flagged"}
    return out


def write_summary(run_dir: Path, summary: dict, rows: list[dict] | None = None) -> None:
    """写 summary.json 并重新生成 report.md；rows 为空时从 results.jsonl 读。"""
    if rows is None:
        rows = [json.loads(x) for x in (run_dir / "results.jsonl").read_text(encoding="utf-8").splitlines() if x]
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (run_dir / "report.md").write_text(render_report(summary, rows), encoding="utf-8")


def write_fact_summary(run_dir: Path, report: dict | None, out: Path | None = None,
                       *, reason: str = "") -> None:
    """Keep fact-stage status visible in the benchmark summary and report."""
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    if report is None:
        summary["facts"] = {"status": "not_run", "reason": reason}
    else:
        summary["facts"] = {
            **report,
            "status": "complete" if report["failed"] == 0 and not report["skipped"] else "partial",
            "candidates_file": out.name,
            "review_file": out.with_suffix(".review.json").name,
            "report_file": out.with_suffix(".report.json").name,
        }
    write_summary(run_dir, summary)


def project_full(pack_dir: Path | str, keys: list[str], character_id: str, tokens: dict,
                 prices: tuple[float, float] | None) -> dict:
    """按这次运行每个输入字的 token 用量（含重试），外推全量导入整个 story_pack 的 token 和费用。"""
    manifest, *_ = load_pack(pack_dir)
    run_chars = estimate(pack_dir, keys, character_id)["input_chars"]
    full = estimate(pack_dir, list(manifest["scenes"]), character_id)
    scale = full["input_chars"] / run_chars if run_chars else 0
    prompt, completion = round(tokens["prompt"] * scale), round(tokens["completion"] * scale)
    cost = round(prompt / 1e6 * prices[0] + completion / 1e6 * prices[1], 2) if prices else None
    return {"pack_scenes": full["scenes"], "pack_input_chars": full["input_chars"], "scale": round(scale, 2),
            "prompt_tokens": prompt, "completion_tokens": completion, "cost": cost}


def summarize_run(rows: list[dict], *, mode: str, model: str, api_url: str, wall: float, started_at: str,
                  concurrency: int, timeout: float, prices: tuple[float, float] | None, run: str,
                  source: str = "") -> dict:
    ok = [r for r in rows if r["status"] == "ok"]
    log = [c for r in rows for c in r["call_log"]]
    answered = [c["seconds"] for c in log if c.get("errors") is not None and not
                any(e.startswith("调用失败") for e in c["errors"])]
    kinds = collections.Counter(error_kind(c["errors"]) for c in log if not c["ok"])
    messages = collections.Counter(re.sub(r"\d+", "N", e) for c in log if not c["ok"] for e in c["errors"])
    known = [r for r in rows if r["prompt_tokens"] is not None]
    prompt_tokens = sum(r["prompt_tokens"] or 0 for r in known)
    completion_tokens = sum(r["completion_tokens"] or 0 for r in known)
    tokens = None
    if known:
        tokens = {"prompt": prompt_tokens, "completion": completion_tokens, "scenes_with_usage": len(known),
                  "per_scene_prompt": round(prompt_tokens / len(known)),
                  "per_scene_completion": round(completion_tokens / len(known))}
    cost = None
    if prices and tokens:
        cost = round(prompt_tokens / 1e6 * prices[0] + completion_tokens / 1e6 * prices[1], 4)
    return {
        "run": run, "mode": mode, "model": model, "api_url": api_url, "prompt_version": PROMPT_VERSION,
        "source": source,
        "started_at": started_at, "wall_seconds": round(wall, 1), "concurrency": concurrency, "timeout": timeout,
        "scenes": len(rows), "ok": len(ok), "failed": len(rows) - len(ok),
        "first_pass": sum(r["first_pass"] for r in rows),
        "calls": len(log), "calls_per_scene": round(len(log) / len(rows), 2) if rows else 0,
        "quote_fixes": {"fixes": sum(c.get("quote_fixes") or 0 for c in log),
                        "calls": sum(1 for c in log if c.get("quote_fixes"))},
        "format_fixes": {"fixes": sum(c.get("format_fixes") or 0 for c in log),
                         "calls": sum(1 for c in log if c.get("format_fixes"))},
        "dropped": {"items": sum(len(c.get("dropped") or []) for c in log),
                    "calls": sum(1 for c in log if c.get("dropped"))},
        "call_errors": dict(kinds), "top_error_messages": messages.most_common(8),
        "latency": {"mean": round(statistics.mean(answered), 2) if answered else None,
                    "p50": _percentile(answered, 0.5), "p95": _percentile(answered, 0.95),
                    "max": round(max(answered), 2) if answered else None},
        "tokens": tokens, "cost": cost, "prices_per_million": list(prices) if prices else None,
        "quality": summarize_audits([r["audit"] for r in ok]),
    }


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3g}" if value < 1 else f"{value:,.1f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _metrics(s: dict) -> list[tuple[str, object]]:
    q, t, lat = s["quality"], s.get("tokens") or {}, s["latency"]
    p, j, proj = s.get("probes") or {}, s.get("judge") or {}, s.get("projection") or {}
    rate = (lambda n: round(n / s["scenes"], 3) if s["scenes"] else None)
    return [
        ("成功场景", f"{s['ok']}/{s['scenes']}"),
        ("首次通过率", rate(s["first_pass"])),
        ("平均每场景调用次数", s["calls_per_scene"]),
        ("JSON 引号修复（处 / 调用）", f"{qf['fixes']} / {qf['calls']}" if (qf := s.get("quote_fixes")) else None),
        ("格式规范（处 / 调用）", f"{ff['fixes']} / {ff['calls']}" if (ff := s.get("format_fixes")) else None),
        ("丢弃或降级的条目（条 / 调用）", f"{dr['items']} / {dr['calls']}" if (dr := s.get("dropped")) else None),
        ("单次调用耗时 p50（秒）", lat["p50"]),
        ("单次调用耗时 p95（秒）", lat["p95"]),
        ("总耗时（秒）", s["wall_seconds"]),
        ("输入 token（合计）", t.get("prompt")),
        ("输出 token（合计）", t.get("completion")),
        ("费用估算", s.get("cost")),
        ("全量导入外推 token（入 / 出）", f"{_fmt(proj.get('prompt_tokens'))} / {_fmt(proj.get('completion_tokens'))}"
         if proj else None),
        ("全量导入外推费用", proj.get("cost")),
        ("探针：渠道也正确的加权召回", p.get("weighted_recall")),
        ("探针：加权覆盖率（不看渠道）", p.get("weighted_coverage")),
        ("探针：边界准确率", p.get("boundary_accuracy")),
        ("探针：仿 KBF 调和分", p.get("kbf")),
        ("裁判：引证召回率", j.get("citation_recall")),
        ("裁判：引证精确率", j.get("citation_precision")),
        ("裁判：渠道支撑率", j.get("channel_support")),
        ("事件数 / 每场景", f"{q['events']} / {q['events_per_scene']}"),
        ("beats / 每事件", f"{q['beats']} / {round(q['beats'] / q['events'], 1) if q['events'] else 0}"
         if "beats" in q else None),
        ("渠道 E/W/T/R/U", "/".join(str(q["channels"][c]) for c in q["channels"])),
        ("episode", q["episodes"]),
        ("认知", q["cognitions"]),
        ("边（明说 / 全部）", f"{q['explicit_edges']} / {q['edges']}"),
        ("实体（concept 类）", f"{q['entities']}（{q['concept_entities']}）"),
        ("用 ta 指代博士的次数", q["ta"]),
        ("她的台词被引用的比例", q["target_line_coverage"]),
        ("单个事件最多证据行", q["evidence_max"]),
        ("事件覆盖的场景行比例", q.get("scene_coverage")),
        ("事件覆盖不到 90% 的场景", q.get("low_coverage_scenes") if "scene_coverage" in q else None),
    ]


def render_report(summary: dict, rows: list[dict]) -> str:
    s = summary
    baseline = s.get("baseline")
    out = [f"# canon 抽取基准 · {s['run']}", "",
           f"- 模式：{ {'api': '真实接口', 'replay': '回放（本机假接口，耗时和 token 没有参考意义）'}.get(s['mode'], s['mode']) }",
           f"- 模型：{s['model']}　接口：{s['api_url'] or '—'}　prompt：{s['prompt_version']}",
           f"- 开始：{s['started_at']}　并发 {s['concurrency']}　超时 {s['timeout']}s",
           *([f"- 回放来源：{s['source']}（回复内容来自这里，不是用当前 prompt 生成的）"] if s.get("source") else []),
           "", "本目录含剧情原文，只能留在本机。", "", "## 总览", ""]
    if baseline:
        base = dict(_metrics(baseline))
        origin = f"回放自 {baseline['source']}" if baseline.get("source") else baseline["prompt_version"]
        out += [f"基线：{baseline['run']}（{baseline['model']} · {origin}）", "",
                "| 指标 | 本次 | 基线 |", "|---|---|---|"]
        out += [f"| {k} | {_fmt(v)} | {_fmt(base.get(k))} |" for k, v in _metrics(s)
                if v is not None or base.get(k) is not None]
    else:
        out += ["| 指标 | 本次 |", "|---|---|"] + [f"| {k} | {_fmt(v)} |" for k, v in _metrics(s) if v is not None]
    out += ["", "## 失败的调用", ""]
    if s["call_errors"]:
        out += [f"- {k}：{v} 次" for k, v in s["call_errors"].items()]
        out += ["", "最常见的问题（数字已归一为 N）：", ""] + [f"- {m} ×{n}" for m, n in s["top_error_messages"]]
    else:
        out.append("没有失败的调用。")
    facts = s.get("facts")
    if facts:
        out += ["", "## 时间事实候选阶段", ""]
        if facts["status"] == "not_run":
            out.append("未运行：" + facts.get("reason", "未配置事实抽取"))
        else:
            out += [f"- 状态：{facts['status']}；场景完成 {facts['complete']}/{facts['selected']}，"
                    f"失败 {facts['failed']}，跳过 {len(facts['skipped'])}",
                    f"- 候选 {facts['candidates']} 条（其中 {facts['scenes_with_candidates']} 个场景有候选）；"
                    f"审阅分组 {facts['review_groups']} 组；分块 {facts['chunks']} 个",
                    f"- 模型调用 {facts['model_calls']} 次；耗时 {facts['wall_seconds']} 秒；"
                    f"token 入/出 {facts['prompt_tokens']}/{facts['completion_tokens']}",
                    f"- 候选：`{facts['candidates_file']}`；待审阅包：`{facts['review_file']}`；"
                    f"阶段报告：`{facts['report_file']}`",
                    "- 候选尚未经人工核实，不进入已审阅事实查询或当前状态判断。"]
            out += [f"- 失败 `{key}`：{error}" for key, error in facts["errors"].items()]
            out += [f"- 跳过 `{key}`：{error}" for key, error in facts["skipped"].items()]
    out += _probe_section(s.get("probes"))
    if s.get("baseline_compare"):
        out += ["", "## 与基线逐事件对比", ""]
        out += render_comparison(s["baseline_compare"], s.get("baseline_name") or "基线", s["run"])
    out += _judge_section(s.get("judge"))
    out += ["", "## 质量检查（成功的场景）", ""]
    issues = s["quality"]["issues"]
    out += [f"- {k}：{v}" for k, v in issues.items()] if issues else ["没有发现问题。"]
    bins = s["quality"].get("coverage_by_density") or {}
    if bins:
        out += ["", "她的台词被引用的比例，按场景里她的台词数分段（台词越密越容易被压缩掉）：", "",
                "| 她的台词数 | 场景 | 台词 | 被引用比例 |", "|---|---|---|---|"]
        out += [f"| {k} | {v['scenes']} | {v['target_lines']} | {_fmt(v['coverage'])} |" for k, v in bins.items()]
    if s.get("projection"):
        pr = s["projection"]
        out += ["", "## 全量导入外推", "",
                f"按这次每个输入字的 token 用量（含重试）外推到整个 story_pack：{pr['pack_scenes']} 个场景、"
                f"输入约 {pr['pack_input_chars']:,} 字，是这次的 {pr['scale']} 倍；"
                f"约输入 {pr['prompt_tokens']:,} / 输出 {pr['completion_tokens']:,} token"
                + (f"，费用约 {pr['cost']}" if pr.get("cost") is not None else "") + "。"]
    out += ["", "## 逐场景", "", "| # | 场景 | 状态 | 块 | 调用 | 秒 | token 入/出 | 事件 | E/W/T/R/U | 问题 |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        a = r["audit"]
        chans = "/".join(str(v) for v in a["channels"].values()) if a else "—"
        tok = f"{_fmt(r['prompt_tokens'])}/{_fmt(r['completion_tokens'])}"
        out.append(f"| {i:02d} | `{r['scene']}` | {r['status']} | {r['chunks']} | {r['calls']} | {r['seconds']} | "
                   f"{tok} | {a['events'] if a else '—'} | {chans} | {len(a['issues']) if a else '—'} |")
    out += ["", "## 需要人工看的条目", ""]
    for i, r in enumerate(rows, 1):
        if r["status"] != "ok":
            out.append(f"- **{i:02d} 失败** `{r['scene']}`：{(r['error'] or '')[:300]}")
            files = [c["response_file"] for c in r["call_log"] if c.get("response_file")]
            if files:
                out.append(f"  - 原始回复：{'、'.join(files)}")
            continue
        for it in r["audit"]["issues"]:
            out.append(f"- {i:02d} {it['where']} · {it['kind']}：{it['detail'][:120]}")
    out += ["", "逐条对照原文请打开同目录的 `review.html`。", ""]
    return "\n".join(out)


def _probe_section(p: dict | None) -> list[str]:
    if not p:
        return []
    out = ["", "## 金标准探针", ""]
    if p["draft"]:
        out += [f"> {p['draft']} 条探针还是草稿（agent 起草、未经人工审定），分数只能当参考。", ""]
    out += [f"- 覆盖探针 {p['cover_probes']} 条：加权覆盖率 {_fmt(p['weighted_coverage'])}，"
            f"渠道也正确的加权召回 {_fmt(p['weighted_recall'])}，覆盖到的探针里渠道正确 {_fmt(p['channel_accuracy'])}",
            f"- 边界探针 {p['boundary_probes']} 条：准确率 {_fmt(p['boundary_accuracy'])}",
            f"- 仿 KBF 调和分：{_fmt(p['kbf'])}（覆盖和边界两组按条数加权的调和平均）"]
    if p["stale"] or p["skipped"]:
        out.append(f"- 过期（line_key 不在场景里）{p['stale']} 条，不在本次运行范围 {p['skipped']} 条，均未计入")
    if p["failures"]:
        out += ["", "失败的探针：", ""]
        out += [f"- `{i['id']}` {i['outcome']}：{i['note']}（{i['detail'] or '—'}"
                + (f"；事件 {i['event']} 渠道 {i['channel']}" if i["event"] else "") + "）"
                for i in p["items"] if not i["ok"]]
    return out


def _judge_section(j: dict | None) -> list[str]:
    if not j:
        return []
    out = ["", "## LLM 裁判", "",
           f"裁判模型 {j['model']}（{j['version']}），每个场景判 {j['repeats']} 次，共 {j['events']} 个事件。"
           "裁判未经人工校准前，数字只能当参考。", "",
           f"- 引证召回率（证据完全支撑摘要的事件占比）：{_fmt(j['citation_recall'])}；支撑程度分布 {j['support']}",
           f"- 引证精确率（完全支撑的事件里，证据行不多余的比例）：{_fmt(j['citation_precision'])}",
           f"- 渠道支撑率（视角证据支撑给出渠道的事件占比）：{_fmt(j['channel_support'])}"]
    if j.get("retest"):
        out.append(f"- 重测一致性 κ：支撑程度 {_fmt(j['retest']['support_kappa'])}，渠道 {_fmt(j['retest']['channel_kappa'])}")
    if j.get("human"):
        h = j["human"]
        out.append(f"- 和人工标注的一致性（{h['events']} 个事件）κ：支撑程度 {_fmt(h['support_kappa'])}，"
                   f"渠道 {_fmt(h['channel_kappa'])}")
    if j.get("failed_scenes"):
        out.append(f"- 裁判失败的场景：{'、'.join(j['failed_scenes'])}")
    if j.get("flagged"):
        out += ["", "裁判标出的问题：", ""]
        for f in j["flagged"]:
            parts = []
            if f["support"] != "full":
                parts.append(f"支撑 {f['support']}：{'；'.join(f['unsupported']) or '—'}")
            if not f["channel_ok"]:
                parts.append(f"渠道 {f['channel']} 存疑：{f['channel_note'] or '—'}")
            out.append(f"- `{f['scene']}` {f['event']}「{f['topic']}」" + "　".join(parts))
    return out
