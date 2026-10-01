"""Read-only, in-memory terminal chat over a local canon database."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import os
import re
import sqlite3
import time
from contextlib import ExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import httpx

from core.canon.gateway import CheckReport, EvidencePack, check_reply
from core.canon.lexical import terms
from core.canon.assembly import EvidenceSettings
from core.canon.packing import CHANNEL_LABEL, estimate_tokens
from core.canon.query import GENERIC_CHARS
from core.canon.reader import CanonReader
from core.canon.recall import TURN_BUDGET
from core.canon.turn import (ARCHIVE_CHARS, ARCHIVE_DEFAULT, ARCHIVE_KIND, ARCHIVE_RULE, ARCHIVE_SECTIONS,
                             ARCHIVE_TOOL, FALLBACK, MAX_TOOL_ROUNDS, MEMORY_NOTE, OUTLINE_NOTE, OUTPUT_RULES,
                             RECALL_POLICY, SKELETONS, STYLE, TIME_RULE, WRAP_UP, CanonTurn, archive_names,
                             between, build_system, empty_blocks, knowledge, outline_note, spoken,
                             supplement_recall, tier_label)

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / ".dev_data/canon/v11/chat/full-20260928.sqlite"
DEFAULT_PERSONA = ROOT / "devtools/canon/amiya_persona.txt"
DEFAULT_QUESTIONS = ROOT.parent / "Arknights-Texts" / "eval" / "canon_retrieval_bank.jsonl"
TRACE_DIR = ROOT / ".dev_data/canon/traces"
ISSUE_LABEL = {"entity": "记忆外的名字", "meta": "出戏", "quote": "引号", "number": "数字", "quantity": "说过头",
               "stale": "旧事说成现在", "denial": "否认记得的事", "order": "先后", "causal": "因果",
               "closing": "客套收尾"}
TASK_LABEL = {"recount": "讲经过", "lookup": "查档案", "fact": "问事实", "reason": "问原因"}
RETRY_NOTE = "请直接用中文回答，不要输出任何工具调用。"
TOOL_MARKUP = re.compile(r"<[｜|]+\s*DSML|<tool_call>|<function_calls>|<[｜|]tool[▁_ ]calls?[▁_ ]begin")
MODEL_TYPE_ALIASES = {"oai": "openai"}


def _model_settings(model_type: str | None) -> tuple[str, str, str, float]:
    try:
        import run_config as config
    except ImportError as exc:
        raise ValueError("找不到 run_config.py；请按 run_config.py.example 配置模型") from exc
    chosen = model_type or getattr(config, "CANON_CHAT_MODEL_TYPE", "") or getattr(
        config, "CANON_MODEL_TYPE", "") or getattr(config, "MODEL_TYPE", "lmstudio")
    chosen = MODEL_TYPE_ALIASES.get(chosen, chosen)
    if chosen == "kcl":
        url = getattr(config, "KCL_API_URL", "https://ai.create.kcl.ac.uk/api/v1")
        key = os.environ.get("CANON_CHAT_API_KEY") or getattr(config, "KCL_API_KEY", "")
        model = getattr(config, "KCL_MODEL", "")
    elif chosen == "deepseek":
        url = "https://api.deepseek.com"
        key = os.environ.get("CANON_CHAT_API_KEY") or getattr(config, "DEEPSEEK_API_KEY", "")
        model = getattr(config, "DEEPSEEK_MODEL", "")
    elif chosen == "openai":
        url = getattr(config, "OPENAI_API_URL", "https://api.openai.com/v1")
        key = os.environ.get("CANON_CHAT_API_KEY") or getattr(config, "OPENAI_API_KEY", "")
        model = getattr(config, "OPENAI_MODEL", "")
    elif chosen == "lmstudio":
        url = getattr(config, "LMSTUDIO_API_URL", "http://localhost:1234/v1")
        key = "lm-studio"
        model = getattr(config, "LMSTUDIO_MODEL", "")
    else:
        raise ValueError(f"不支持的模型类型：{chosen}")
    if not key or key in ("your_deepseek_api_key_here", "your_openai_api_key_here") or not model:
        raise ValueError(f"run_config.py 中 {chosen} 的模型名或 API key 未配置")
    timeout = float(getattr(config, "CANON_TIMEOUT", None) or getattr(config, "TIMEOUT", 300))
    return str(url).rstrip("/"), str(key), str(model), timeout


class ToolsRejected(RuntimeError):
    pass


class ModelClient:
    def __init__(self, url: str, key: str, model: str, timeout: float) -> None:
        self.url, self.key, self.model = url, key, model
        self.client = httpx.Client(timeout=timeout)
        self.request_metrics: list[dict] = []
        self.omit_temperature = False

    def close(self) -> None:
        self.client.close()

    def _detail(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        detail = ""
        if isinstance(payload, dict):
            error = payload.get("error", payload.get("detail", payload.get("message")))
            if isinstance(error, dict):
                error = error.get("message", error.get("code", ""))
            if isinstance(error, str):
                detail = re.sub(r"\s+", " ", error.replace(self.key, "[API key hidden]")).strip()[:240]
        return f"：{detail}" if detail else "（接口未提供可显示的原因）"

    def _post(self, body: dict) -> httpx.Response:
        return self.client.post(
            f"{self.url}/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json=body,
        )

    def chat(self, messages: list[dict], temperature: float,
             tools: list[dict] | None = None, tool_choice: str = "auto") -> dict:
        body: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        if self.omit_temperature:
            body.pop("temperature")
        started = time.perf_counter()
        response = self._post(body)
        if response.status_code == 400 and "temperature" in body and "temperature" in self._detail(response).lower():
            body.pop("temperature")
            self.omit_temperature = True
            response = self._post(body)
        elapsed = time.perf_counter() - started
        try:
            usage = response.json().get("usage") or {}
        except (ValueError, AttributeError):
            usage = {}
        self.request_metrics.append({"seconds": elapsed, "status": response.status_code,
                                     "prompt_tokens": usage.get("prompt_tokens"),
                                     "completion_tokens": usage.get("completion_tokens")})
        if response.status_code != 200:
            message = f"模型接口返回 HTTP {response.status_code}{self._detail(response)}"
            if tools and response.status_code in (400, 422):
                raise ToolsRejected(message)
            raise RuntimeError(message)
        message = response.json()["choices"][0]["message"]
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return {
            "content": content.strip() if isinstance(content, str) else "",
            "tool_calls": message.get("tool_calls") or [],
        }

    def complete(self, messages: list[dict], temperature: float) -> str:
        return self.chat(messages, temperature)["content"]


@dataclass
class Session:
    tools: bool
    history: list[dict[str, str]] = field(default_factory=list)
    pack: EvidencePack | None = None
    recall_log: list[dict] = field(default_factory=list)
    tool_queries: list[str] = field(default_factory=list)
    report: CheckReport | None = None
    metrics: dict = field(default_factory=dict)
    active_history: list[dict[str, str]] = field(default_factory=list)
    draft: str = ""
    outline: str = ""
    task: str = "fact"


def conversation_history(history: list[dict], query: str, budget: int = 5000) -> list[dict]:
    """Keep the opening, recent exchanges and relevant older exchanges within one shared budget."""
    pairs = [history[i:i + 2] for i in range(0, len(history), 2)]
    chosen = {}
    used = 0
    if pairs:
        cost = sum(estimate_tokens(m["content"]) for m in pairs[0])
        if cost <= budget // 4:
            chosen[0] = pairs[0]
            used = cost
    for index in range(len(pairs) - 1, max(-1, len(pairs) - 9), -1):
        if index in chosen:
            continue
        cost = sum(estimate_tokens(m["content"]) for m in pairs[index])
        if used + cost > budget:
            break
        chosen[index] = pairs[index]
        used += cost
    query_words = set(terms(query, GENERIC_CHARS))
    older = [(len(query_words & set(terms(" ".join(m["content"] for m in pair), GENERIC_CHARS))), i)
             for i, pair in enumerate(pairs) if i not in chosen]
    for score, index in sorted(older, reverse=True):
        if not score or len(chosen) >= 10:
            break
        cost = sum(estimate_tokens(m["content"]) for m in pairs[index])
        if used + cost <= budget:
            chosen[index] = pairs[index]
            used += cost
    return [message for index in sorted(chosen) for message in chosen[index]]


def _tool_args(call: dict) -> dict:
    arguments = (call.get("function") or {}).get("arguments")
    try:
        parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def generate(llm: ModelClient, session: Session, system: str | Callable[[], str], query: str,
             tools: list[dict], handlers: dict, temperature: float) -> tuple[str, int]:
    """Let the model call its tools on its own; tool rounds stay out of the saved history.

    A callable system prompt is rebuilt before every request, so memories a tool just added appear once, in the
    prompt, rather than again in each tool result.
    """
    compose = system if callable(system) else (lambda: system)
    messages = [{"role": "system", "content": ""}, *session.active_history, {"role": "user", "content": query}]
    calls = rounds = 0
    retried_empty = False
    while True:
        offer = session.tools and rounds < MAX_TOOL_ROUNDS
        wrap_up = bool(session.tools and tools and not offer)
        messages[0] = {"role": "system", "content": compose()}
        if wrap_up and messages[-1]["role"] == "tool" and WRAP_UP not in messages[-1]["content"]:
            messages[-1] = {**messages[-1], "content": f"{messages[-1]['content']}\n{WRAP_UP}"}
        try:
            if wrap_up:
                try:
                    message = llm.chat(messages, temperature, tools, tool_choice="none")
                except ToolsRejected:
                    message = llm.chat(messages, temperature, None)
            else:
                message = llm.chat(messages, temperature, tools if offer and tools else None)
        except ToolsRejected as exc:
            session.tools = False
            print(f"[canon] 接口不接受工具调用，本次会话改为不带工具：{exc}")
            continue
        calls += 1
        if offer and message["tool_calls"]:
            rounds += 1
            messages.append({"role": "assistant", "content": message["content"],
                             "tool_calls": message["tool_calls"]})
            for call in message["tool_calls"]:
                name = (call.get("function") or {}).get("name", "")
                handler = handlers.get(name)
                result = handler(_tool_args(call)) if handler else f"没有名为 {name} 的工具。"
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
            continue
        unusable = not message["content"] or (wrap_up and TOOL_MARKUP.search(message["content"]))
        if unusable and not retried_empty:
            retried_empty = True
            if wrap_up:
                messages = [*messages, {"role": "user", "content": RETRY_NOTE}]
            continue
        return message["content"], calls


def trace_line(session: Session, calls: int) -> str:
    report = session.report
    parts = [tier_label(session.recall_log), f"讲法：{TASK_LABEL.get(session.task, session.task)}"]
    if session.tool_queries:
        parts.append("调用工具：" + "、".join(session.tool_queries))
    if report.refetched:
        parts.append("按回复补查：" + "、".join(report.refetched))
    if report.reviewed:
        parts.append("对齐：" + (issue_counts(report) if report.issues else "通过"))
    if report.revised:
        parts.append("已定点修补")
    if report.replaced:
        parts.append(f"换回记忆原句 {report.replaced} 句")
    if report.dropped:
        parts.append(f"去掉无依据句 {report.dropped} 句")
    parts.append(f"模型调用 {calls} 次")
    if session.metrics:
        parts.append(f"证据 {session.metrics['evidence_tokens']}/{session.metrics['evidence_budget']} token（估算"
                     + ("，含补查" if session.metrics["evidence_tokens"] > session.metrics["evidence_budget"] else "")
                     + "）")
        parts.append(f"本轮 {session.metrics['seconds']:.1f}s")
        if session.metrics.get("prompt_tokens") is not None:
            parts.append(f"API 输入/输出 {session.metrics['prompt_tokens']}/{session.metrics['completion_tokens']}")
    return "[canon] " + "｜".join(parts)


def issue_counts(report: CheckReport) -> str:
    counts: dict[str, int] = {}
    for kind in report.issues.values():
        counts[kind] = counts.get(kind, 0) + 1
    return "、".join(f"{ISSUE_LABEL.get(kind, kind)} {count} 句" for kind, count in counts.items())


def problem_lines(report: CheckReport) -> list[str]:
    return [f"第 {index} 句「{report.sentences[index - 1].strip()}」："
            + (f"[{ISSUE_LABEL.get(report.issues[index], report.issues[index])}] " if index in report.issues else "")
            + reason for index, reason in sorted(report.problems.items())]


def write_trace(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def print_sources(session: Session) -> None:
    if session.pack is None:
        print("  [canon] 还没有对话")
        return
    print(f"  {tier_label(session.recall_log)}")
    for item in session.pack.items if session.pack else ():
        print(f"  {item.eid} {CHANNEL_LABEL.get(item.channel, item.channel)} {item.source}｜{item.summary[:40]}")
    if session.pack is not None and not session.pack.items:
        print("  [canon] 没有调出记忆")
    if session.report and session.report.problems:
        for line in problem_lines(session.report):
            print(f"  {line}")


def run_turn(query: str, *, reader: CanonReader, llm: ModelClient | None, session: Session,
             args: argparse.Namespace, persona: str, memory_block: str = "") -> None:
    """One canon turn; results stay on the session (pack, report, recall log, metrics, answer in history).

    memory_block is host-side context (e.g. ordinary chat memory injected by the plugin) shown to the model
    ahead of the user's words. Routing, recall and the reply check still read only the user's query.
    """
    started = time.perf_counter()
    prompt = f"{memory_block}\n\n{query}" if memory_block else query
    request_offset = len(getattr(llm, "request_metrics", []))
    session.active_history = conversation_history(session.history, query)
    turn = CanonTurn(reader, EvidenceSettings(
        doctor=args.doctor, top_k=args.top_k, evidence_lines=args.evidence_lines,
        token_budget=args.token_budget), query=query, persona=persona, history=session.active_history,
        prompt=prompt, tools=session.tools, archive_all=args.archive_all)
    recall, pack = turn.recall, turn.pack
    session.pack, session.report, session.recall_log = pack, None, recall.log
    session.tool_queries = turn.tool_queries
    session.task = turn.task
    if args.dry_run or llm is None:
        print(f"  讲法：{TASK_LABEL[session.task]}；由模型决定是否回忆；范围探查结果：")
        print(recall.probe(query))
        return
    turn.start()
    draft, calls = generate(llm, session, turn.system, prompt, turn.tools() if turn.offer else [], turn.handlers,
                            args.temperature)
    reply, extra = turn.settle(draft, llm.complete, args.temperature, supplement=supplement_recall)
    calls += extra
    draft = turn.draft
    session.draft, session.outline = turn.draft, turn.outline
    if reader.retrieval and any(entry["tool"] == "canon_recall" for entry in recall.log):
        trace = reader.retrieval.last_trace
        print(f"[retrieval] {reader.retrieval.mode}；{'降级' if trace.get('degraded') else '就绪'}；"
              f"{trace.get('seconds', 0):.3f}s")
    answer, report = turn.check(reply, llm.complete, args.temperature, check=check_reply)
    request_metrics = getattr(llm, "request_metrics", [])[request_offset:]
    usage = {key: sum(row[key] for row in request_metrics) if request_metrics and
             all(row[key] is not None for row in request_metrics) else None
             for key in ("prompt_tokens", "completion_tokens")}
    session.report = report
    session.metrics = {"seconds": round(time.perf_counter() - started, 3),
                       "calls": calls + report.calls,
                       "history_tokens": sum(estimate_tokens(m["content"]) for m in session.active_history),
                       "evidence_tokens": estimate_tokens(pack.render()) if pack.items else 0,
                       "evidence_budget": args.token_budget,
                       "tier": tier_label(recall.log), "task": session.task, "recalls": list(recall.log),
                       **usage,
                       "first_response_seconds": request_metrics[0]["seconds"] if request_metrics else None,
                       "expansion_candidates": reader.last_expansion_trace.get("candidates", 0)}
    print(trace_line(session, calls + report.calls))
    for line in problem_lines(report):
        print(f"  {line}")
    print(f"阿米娅> {answer}")
    if getattr(args, "trace", None):
        write_trace(args.trace, {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "db": str(getattr(args, "db", "")),
            "model": getattr(llm, "model", None), "query": query, "task": session.task,
            "history": session.active_history, "tools": session.tool_queries, "recalls": recall.log,
            "evidence": [{"eid": item.eid, "event_id": item.event_id, "channel": item.channel,
                          "source": item.source, "when": reader.time_label(item.event_id),
                          "said": reader.time_phrase(item.event_id)}
                         for item in pack.items],
            "evidence_text": pack.render(), "draft": draft, "outline": session.outline, "check": report.stages,
            "problems": {str(index): {"sentence": report.sentences[index - 1].strip(), "reason": reason,
                                      "status": report.issues.get(index, "")}
                         for index, reason in sorted(report.problems.items())},
            "answer": answer, "metrics": session.metrics})
    session.history.extend(({"role": "user", "content": query},
                            {"role": "assistant", "content": answer}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="临时 canon 对话：数据库只读，聊天只在内存")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--persona-file", type=Path, default=DEFAULT_PERSONA)
    parser.add_argument("--model-type", choices=("kcl", "deepseek", "openai", "oai", "lmstudio"))
    parser.add_argument("--not-doctor", dest="doctor", action="store_false", help="对照测试：当前对话者不是博士")
    parser.set_defaults(doctor=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--token-budget", type=int, default=TURN_BUDGET,
                        help="每轮所有回忆合计的原文上限，不含人设；预算扫描后锚定为 2000")
    parser.add_argument("--evidence-lines", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--no-tools", action="store_true", help="不向模型提供 canon_recall、canon_overview 和档案查询工具")
    parser.add_argument("--archive-all", action="store_true",
                        help="档案查询也返回升变档案、其他形态和隐藏段（默认只返回本体形态）")
    parser.add_argument("--show-sources", action="store_true")
    parser.add_argument("--trace", nargs="?", const=TRACE_DIR, type=Path, metavar="JSONL",
                        help="每轮追加一行完整过程记录（工具调用、证据、初稿、逐句核验、修订与最终回复）；"
                             "不填路径写到 .dev_data/canon/traces/ 下的新文件")
    parser.add_argument("--dry-run", action="store_true", help="只显示路线、检索与注入片段，不调用模型")
    parser.add_argument("--question", help="只问一次；不填则进入连续对话")
    parser.add_argument("--questions", nargs="?", const=DEFAULT_QUESTIONS, type=Path, metavar="JSONL",
                        help="按题库批量评测检索；不填路径使用 Arknights-Texts/eval/canon_retrieval_bank.jsonl（200 题）")
    parser.add_argument("--out", type=Path, help="题库评测的 JSON 报告路径")
    parser.add_argument("--retrieval", choices=("auto", "baseline", "hybrid", "hybrid-rerank"), default="auto",
                        help="auto：有向量索引就用 hybrid，否则用 baseline；离线单轮或题库评测默认 baseline")
    parser.add_argument("--index", type=Path, help="Derived vector index; shared Moirai provider identity")
    parser.add_argument("--allow-remote", action="store_true", help="允许单轮干跑或题库评测调用远程检索")
    parser.add_argument("--allow-retrieval-fallback", action="store_true")
    args = parser.parse_args(argv)
    if args.questions is not None and args.question is not None:
        parser.error("--questions 与 --question 不能同时使用")
    if args.out is not None and args.questions is None:
        parser.error("--out 仅用于 --questions")
    if args.questions is not None and not args.questions.is_file():
        parser.error(f"找不到题库：{args.questions}")
    if not args.db.is_file():
        parser.error(f"找不到 canon 数据库：{args.db}；用 --db 指定")
    if args.retrieval == "auto":
        from devtools.canon.retrieval import index_available
        offline = (args.dry_run or args.questions is not None) and not args.allow_remote
        args.retrieval = "hybrid" if not offline and index_available(args.db, args.index) else "baseline"
    if (args.dry_run or args.questions is not None) and args.retrieval != "baseline" and not args.allow_remote:
        parser.error("远程检索需要显式 --allow-remote")
    if args.top_k < 1 or args.token_budget < 0 or args.evidence_lines < 0:
        parser.error("top-k 需为正数；token-budget 和 evidence-lines 不能为负")
    if args.trace == TRACE_DIR:
        args.trace = TRACE_DIR / f"chat-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    if args.questions is not None:
        from devtools.canon.retrieval import main as retrieval_main
        probe_args = ["probe", "--db", str(args.db), "--mode", args.retrieval,
                      "--questions", str(args.questions), "--top-k", str(args.top_k),
                      "--token-budget", str(args.token_budget),
                      "--evidence-lines", str(args.evidence_lines)]
        if args.index is not None:
            probe_args.extend(("--index", str(args.index)))
        if args.out is not None:
            probe_args.extend(("--out", str(args.out)))
        if args.doctor is False:
            probe_args.append("--not-doctor")
        if args.allow_remote:
            probe_args.append("--allow-remote")
        if args.allow_retrieval_fallback:
            probe_args.append("--allow-fallback")
        try:
            return retrieval_main(probe_args)
        except (OSError, sqlite3.Error, httpx.HTTPError, ValueError, RuntimeError) as exc:
            print(f"[canon test] 题库评测失败：{exc}", file=sys.stderr)
            return 2
    resources = ExitStack()
    try:
        persona = args.persona_file.read_text(encoding="utf-8").strip()
        if not persona:
            raise ValueError("人格提示词文件为空")
        retrieval = None
        if args.retrieval != "baseline":
            from devtools.canon.retrieval import setup
            retrieval, _, _ = setup(args.db, args.index, args.retrieval, resources,
                                     allow_fallback=args.allow_retrieval_fallback)
        reader = CanonReader(args.db, retrieval=retrieval)
        resources.callback(reader.close)
        llm = None
        if not args.dry_run:
            llm = ModelClient(*_model_settings(args.model_type))
            resources.callback(llm.close)
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
        resources.close()
        print(f"无法启动：{exc}", file=sys.stderr)
        return 2
    print(f"[canon] 数据库：{args.db}；检索：{args.retrieval}")
    print(f"[canon] {reader.scene_count} 场景、{reader.event_count} 事件；"
          f"prompt {reader.meta.get('prompt_version', '?')}；"
          f"{'只看检索' if llm is None else llm.model}；"
          f"{'博士模式' if args.doctor else '普通对话者模式'}")
    print(f"[canon] 过程记录：{args.trace}（含剧情原文，只留在本机）" if args.trace and llm is not None else
          "本工具不写本地聊天记录；调用远程接口时，请以接口服务方的留存规则为准。")
    if llm is not None:
        print(f"[canon] 由模型决定是否回忆：闲聊和日常不回忆、只调用一次；需要原作时用 canon_probe / canon_recall"
              f"（轻量或深度）{'或 operator_archive' if reader.has_archives else ''}；用到回忆才核验。"
              f"每轮原文预算 {args.token_budget} token，多次回忆合计，不含人设。"
              if not args.no_tools else "[canon] 未提供工具：不回忆原作。")
    if args.question is None:
        print("输入 /quit 退出，/clear 清空内存中的对话，/sources 查看上一轮的路线、记忆和核验。")
    session = Session(tools=not args.no_tools)
    try:
        while True:
            try:
                query = args.question if args.question is not None else input("你> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if query in {"/quit", "/exit"}:
                break
            if query == "/clear":
                session = Session(tools=session.tools)
                print("[canon] 已清空本次进程内的对话。")
                if args.question is not None:
                    break
                continue
            if query == "/sources":
                print_sources(session)
                if args.question is not None:
                    break
                continue
            if not query:
                if args.question is not None:
                    break
                continue
            try:
                run_turn(query, reader=reader, llm=llm, session=session, args=args, persona=persona)
            except (sqlite3.Error, httpx.HTTPError, KeyError, ValueError, RuntimeError) as exc:
                print(f"[canon] 本轮失败：{exc}", file=sys.stderr)
                if args.question is not None:
                    return 1
            if args.question is not None:
                break
    finally:
        resources.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
