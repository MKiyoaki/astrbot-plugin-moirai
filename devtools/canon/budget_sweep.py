"""Evidence-budget sweep for the canon terminal: judged accuracy, latency and evidence tokens per budget.

Runs the real terminal turn (model-directed recall, review) once per question and budget, then asks a
different model (arc:nexus) at temperature 0 to check each plot claim against the question's source and
context lines, the turn's own evidence, and curated true and false claims, and to score key-point coverage.
Results are appended to a JSONL file so an interrupted sweep resumes; the eval banks and outputs stay local.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import random
import re
import sys
import time
from contextlib import ExitStack
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / ".dev_data/canon/eval"
DEFAULT_DB = ROOT / ".dev_data/canon/v11/chat/full-20260928.sqlite"
BUDGETS = (400, 700, 1000, 1500, 2000, 3000)
BANK = EVAL / "sweep-bank-v2.jsonl"
JUDGE_MODEL = "arc:nexus"
JUDGE_SYSTEM = (
    "你是独立评测员，不是被测模型。逐条核对角色回复里的剧情说法，再按答案要点打分。\n"
    "核对规则：\n"
    "1. 在[原文行][上下文原文][本轮证据]或[正例]里能找到依据的说法，算真实。\n"
    "2. 与这些原文矛盾，或与[反例]意思相同的说法，算幻觉。\n"
    "3. 具体的剧情说法（人物、事件、动作、原话、数字、地点）在以上材料里找不到、但也不矛盾，算无依据，不算幻觉。\n"
    "4. 寒暄、感受、看法、推测语气的话和此刻的日常见闻不是剧情说法，不核对。\n"
    "5. [知情情况]写明阿米娅不在场的事，她说成亲身经历算幻觉；说不清楚、没看到是正确表现。\n"
    "打分：2＝命中全部答案要点（或完全按[预期表现]处理）且没有幻觉；1＝命中部分要点且没有幻觉；0＝一个要点都没命中，或出现任何幻觉。"
    "用词不同但意思相同算命中。\n"
    '只输出 JSON：{"key_points_hit":[命中的要点序号],"hallucinations":[{"claim":"…","why":"与哪行原文或哪条反例矛盾"}],'
    '"unsupported":["…"],"score":0|1|2,"reason":"一句话"}'
)


def load_cases(path: Path = BANK) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def judge(llm, case: dict, answer: str, evidence: str) -> dict:
    def block(title, items):
        return f"[{title}]\n" + ("\n".join(items) if items else "（无）")
    content = "\n\n".join((
        block("问题", [case["question"]]), block("知情情况", [case["knowledge"]]),
        block("预期表现", [case.get("behavior") or "按答案要点回答"]), block("参考答案", [case["reference"]]),
        block("答案要点", [f"{i}. {point}" for i, point in enumerate(case["key_points"], 1)]),
        block("原文行", [f"{row['key']} {row['text']}" for row in case["source_lines"]]),
        block("上下文原文", [row["text"] for row in case["context_lines"]]),
        block("正例（真实）", [f"{row['claim']}（{row['text']}）" for row in case["positives"]]),
        block("反例（错误）", [f"{row['claim']}" + (f"（被这行推翻：{row['text']}）" if row["text"] else "") for row in case["negatives"]]),
        block("本轮证据", [evidence[:4000]] if evidence else []),
        block("角色回复", [answer]),
    ))
    raw = llm.complete([{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": content}], 0.0)
    match = re.search(r"\{.*\}", raw or "", re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except ValueError:
        data = {}
    score = data.get("score")
    hallucinations = [item for item in data.get("hallucinations") or [] if isinstance(item, dict)]
    return {"score": score if score in (0, 1, 2) else None,
            "key_points_hit": [n for n in data.get("key_points_hit") or [] if isinstance(n, int)],
            "hallucinations": hallucinations, "hallucinated": bool(hallucinations),
            "unsupported": [str(item)[:120] for item in data.get("unsupported") or []],
            "reason": str(data.get("reason", ""))[:200]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Canon evidence-budget sweep (calls the KCL model)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--out", type=Path, required=True, help="JSONL results; rerun with the same path to resume")
    parser.add_argument("--budgets", default=",".join(map(str, BUDGETS)))
    parser.add_argument("--retrieval", choices=("hybrid", "baseline"), default="hybrid")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--pause", type=float, default=0.5, help="Seconds between turns, for provider rate limits")
    parser.add_argument("--bank", type=Path, default=BANK)
    parser.add_argument("--judge-model", default=JUDGE_MODEL)
    parser.add_argument("--judge-workers", type=int, default=3)
    parser.add_argument("--phase", choices=("run", "judge", "all"), default="all")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT))
    sys.argv = ["run_canon_dev.py"]
    import run_canon_dev  # noqa: F401  (loads run_config and the prompt version before canon modules)
    import run_canon_chat as chat
    from devtools.canon.retrieval import setup

    budgets = [int(value) for value in args.budgets.split(",") if value.strip()]
    cases = load_cases(args.bank)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.phase in ("run", "all"):
        run_turns(args, chat, setup, cases, budgets)
    if args.phase in ("judge", "all"):
        judge_rows(args, chat, {case["id"]: case for case in cases})
    print("[sweep] done", flush=True)
    return 0


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def run_turns(args, chat, setup, cases: list[dict], budgets: list[int]) -> None:
    """Phase 1: answer every question at every budget in one sequence, so judging never disturbs latency."""
    done = {(row["id"], row["budget"]) for row in read_rows(args.out)}
    persona = chat.DEFAULT_PERSONA.read_text(encoding="utf-8").strip()
    rng = random.Random(20260928)
    total = len(cases) * len(budgets)
    print(f"[sweep] {len(cases)} questions x {len(budgets)} budgets = {total} turns; {len(done)} already done", flush=True)
    with ExitStack() as stack:
        retrieval = setup(args.db, None, args.retrieval, stack)[0] if args.retrieval != "baseline" else None
        reader = chat.CanonReader(args.db, retrieval=retrieval)
        stack.callback(reader.close)
        url, key, model, timeout = chat._model_settings("kcl")
        llm = chat.ModelClient(url, key, model, timeout)
        stack.callback(llm.close)
        print(f"[sweep] tested model {model}", flush=True)
        count = len(done)
        for case in cases:
            order = budgets[:]
            rng.shuffle(order)
            for budget in order:
                if (case["id"], budget) in done:
                    continue
                settings = argparse.Namespace(doctor=True, top_k=5, evidence_lines=4, token_budget=budget,
                                              dry_run=False, show_sources=False, temperature=args.temperature,
                                              archive_all=False)
                for attempt in range(4):
                    session = chat.Session(tools=True)
                    started = time.perf_counter()
                    try:
                        with contextlib.redirect_stdout(io.StringIO()):
                            chat.run_turn(case["question"], reader=reader, llm=llm, session=session, args=settings,
                                          persona=persona)
                        seconds = time.perf_counter() - started
                        break
                    except Exception as exc:
                        print(f"[sweep] {case['id']}@{budget} attempt {attempt + 1} failed: {type(exc).__name__}: "
                              f"{str(exc)[:120]}", flush=True)
                        time.sleep(30 * (attempt + 1))
                else:
                    continue
                metrics = session.metrics
                row = {"id": case["id"], "kind": case["kind"], "budget": budget, "question": case["question"],
                       "answer": session.history[-1]["content"], "seconds": round(seconds, 3),
                       "calls": metrics.get("calls"), "evidence_tokens": metrics.get("evidence_tokens", 0),
                       "tier": metrics.get("tier"), "recalls": metrics.get("recalls", []),
                       "prompt_tokens": metrics.get("prompt_tokens"), "completion_tokens": metrics.get("completion_tokens"),
                       "reviewed": bool(session.report and session.report.reviewed),
                       "problems": len(session.report.problems) if session.report else 0,
                       "issues": dict(session.report.issues) if session.report else {},
                       "revised": bool(session.report and session.report.revised),
                       "replaced": session.report.replaced if session.report else 0,
                       "dropped": session.report.dropped if session.report else 0,
                       "task": metrics.get("task"),
                       "draft": session.draft, "check": session.report.stages if session.report else [],
                       "evidence": session.pack.render() if session.pack and session.pack.items else ""}
                with args.out.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
                print(f"[sweep] {count}/{total} {case['id']}@{budget}: {row['seconds']:.1f}s "
                      f"{row['evidence_tokens']}tok {row['tier']}", flush=True)
                time.sleep(args.pause)


def judge_rows(args, chat, cases: dict[str, dict]) -> None:
    """Phase 2: grade every answered turn with the independent judge, a few at a time."""
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    judged_path = args.out.with_suffix(".judged.jsonl")
    done = {(row["id"], row["budget"]) for row in read_rows(judged_path)}
    todo = [row for row in read_rows(args.out) if (row["id"], row["budget"]) not in done]
    url, key, _, timeout = chat._model_settings("kcl")
    local, lock = threading.local(), threading.Lock()
    print(f"[judge] {len(todo)} turns to grade with {args.judge_model}; {len(done)} already graded", flush=True)

    def grade(row):
        if not hasattr(local, "client"):
            local.client = chat.ModelClient(url, key, args.judge_model, max(timeout, 300))
        for attempt in range(4):
            try:
                verdict = judge(local.client, cases[row["id"]], row["answer"], row["evidence"])
                if verdict["score"] is not None:
                    return {**row, "judge_model": args.judge_model, **verdict}
            except Exception as exc:
                print(f"[judge] {row['id']}@{row['budget']} attempt {attempt + 1} failed: {type(exc).__name__}: "
                      f"{str(exc)[:100]}", flush=True)
            time.sleep(20 * (attempt + 1))
        return {**row, "judge_model": args.judge_model, "score": None, "hallucinated": None,
                "hallucinations": [], "unsupported": [], "key_points_hit": [], "reason": "judge failed"}

    count = len(done)
    with ThreadPoolExecutor(max_workers=args.judge_workers) as pool:
        for future in as_completed([pool.submit(grade, row) for row in todo]):
            result = future.result()
            with lock:
                with judged_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                count += 1
                print(f"[judge] {count}/{len(done) + len(todo)} "
                      f"{result['id']}@{result['budget']}: score {result['score']} halluc {result['hallucinated']}",
                      flush=True)

if __name__ == "__main__":
    raise SystemExit(main())
