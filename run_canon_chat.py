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

import httpx

from core.canon.gateway import PAST_MARKERS, CheckReport, EvidencePack, Memory, check_reply
from core.canon.lexical import terms
from core.canon.overview import is_overview
from core.canon.assembly import EvidenceAssembler, EvidenceSettings
from core.canon.packing import CHANNEL_LABEL, clip, estimate_tokens, fill, overview_tool_result
from core.canon.query import GENERIC_CHARS, TurnPlan, plan_turn, route
from core.canon.reader import CanonReader

ROOT = Path(__file__).resolve().parent
NEXUS_DB = ROOT / ".dev_data/canon/v7/20/api/20260924-000545-kcl-arc_nexus/canon.sqlite"
TEMPORAL_DB = ROOT / ".dev_data/canon/v7/chat/nexus-v3.sqlite"
LATEST_DB = ROOT / ".dev_data/canon/v7/chat/nexus-20260924-045430.sqlite"
SAMPLE100_DB = ROOT / ".dev_data/canon/v7/chat/100-20260924-171238.sqlite"
FULL_DB = ROOT / ".dev_data/canon/v10/all/build/canon.sqlite"
DEFAULT_DB = next((path for path in (FULL_DB, SAMPLE100_DB, LATEST_DB, TEMPORAL_DB, NEXUS_DB)
                   if path.is_file()), FULL_DB)
DEFAULT_PERSONA = ROOT / "devtools/canon/amiya_persona_concise.txt"
DEFAULT_QUESTIONS = ROOT / ".dev_data/canon/eval/retrieval-200-v1.jsonl"
LANE_LABEL = {"chat": "闲聊", "canon": "剧情", "status": "近况"}
MAX_TOOL_ROUNDS = 2
FALLBACK = "嗯……这件事我记不太清了。"
RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "canon_recall",
        "description": "回忆你亲历或知道的过去事件、人物经历。只在回答需要具体的过去事件、人物或地点时调用；"
                       "寒暄、关心和闲聊不要调用。",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "要回忆的人物、事件或关键词"}},
            "required": ["query"],
        },
    },
}
OVERVIEW_TOOL = {
    "type": "function",
    "function": {
        "name": "canon_overview",
        "description": "回忆一个地点、篇章或人物历程中多次事件的脉络。用于发生了什么、如何发展、经历哪些冲突等综述问题。",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "需要综述的地点、篇章、事件或人物历程"}},
            "required": ["query"],
        },
    },
}
OUTPUT_RULES = (
    "[回复要求]\n"
    "· 先回应博士说的话；自然交流时可以顺势问一句，不要用反问代替回答。拿不准过去的事实时说清楚哪部分记不清。\n"
    "· 不要说出原作、剧情、章节、资料、编号、检索、数据库这类词。\n"
    "· 讲到过去的具体经历时，只说[你的记忆]里有的内容，不添加其中没有的动作、神情、情绪、数字或原因；过去的事要说成过去。\n"
    "· 回答原因要说明有依据的动机或目的；材料只有经过时，不要把经过冒充原因。"
    "\n· 先想清楚对方这一轮真正想聊的事，再直接回答。记忆是依据，不是必须逐条复述的清单。"
    "通常先说重点，再选一两件必要的事说明；没有要求详细经过时，优先用两到四句接住这一轮话题。对方明确要细节时再展开。不要展示回答提纲。"
    "\n· 延续本次交流，避免重复已经讲过的经历和同一句关心。不要凭几句话断定博士情绪反常，"
    "也不要编造博士平时的习惯。可以表达此刻的感受、立场和疑问，不必每轮都用问题收尾。"
    "\n· 对未来的判断只能基于你知道的事，并明确是判断；不知情的事件不能靠加上可能、记不清或不确定来透露。"
)
TOOL_RULE = ("\n· 需要具体的过去事件、人物或地点，而[你的记忆]里没有时，先调用 canon_recall。"
             "要回答跨多次事件的综述问题、现有记忆又不够时，调用 canon_overview。")
ARCHIVE_RULE = ("\n· 需要某人的出身、种族、生日、履历、体检、病情或作战情报时，调用 operator_archive；"
                "查到的是罗德岛档案上的记载，要说成“档案上写着”，不能说成自己亲身经历。")
ARCHIVE_TOOL = {
    "type": "function",
    "function": {
        "name": "operator_archive",
        "description": "查阅罗德岛档案：干员的人事档案、NPC 情报、敌人的作战情报。只在回答需要某人的出身、种族、生日、"
                       "履历、体检、病情或作战情报时调用；查到的是档案记载，不是你亲历的事。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "人物或敌人的名字"},
                "section": {"type": "string",
                            "description": "要看的档案段，例如 基础档案、客观履历、临床诊断分析、档案资料一；"
                                           "不填则返回概要和可查的段落"},
            },
            "required": ["name"],
        },
    },
}
ARCHIVE_KIND = {"operator": "干员档案", "npc": "情报资料", "enemy": "作战情报"}
ARCHIVE_DEFAULT = ("基础档案", "客观履历", "情报资料一", "作战情报")
ARCHIVE_SECTIONS = 2
ARCHIVE_CHARS = 600


def persona_profile(persona: str) -> str:
    rows = []
    for line in persona.splitlines():
        key, sep, value = line.partition("|")
        key, value = key.strip(), value.strip()
        if sep and key and value and len(key) <= 24 and key not in ("项目", "特点", "助词"):
            rows.append(f"{key}：{value}")
    return "\n".join(rows)


def knowledge(plan: TurnPlan, pack: EvidencePack, fact_block: str, fact_valid: bool,
              tools: bool) -> str:
    lines = ["[你的记忆]"]
    if plan.intent == "conversation":
        lines.append("这一轮是在谈本次聊天。根据对话记录回答，不把提到一个地名或人名误当成要求重讲那段经历。")
    if plan.intent == "prediction":
        lines.append("对方在问你的判断。先表达有依据的看法，区分已知与推测；不知道对方的计划时，不替她宣布下一步行动。")
    if pack.items:
        if plan.impression:
            lines.append("这些是你知道或亲历的片段。先回答自己的感受或看法，再选最贴近的一两件事说明，不要逐条复述材料，也不要把标为不知情的事说成自己亲历。编号只供你对照，不要说出来。")
        elif plan.overview:
            if is_overview(plan.search_query):
                lines.append("以下是按篇章和场景原文顺序整理的候选记忆。先抓主要冲突、行动与结果，挑必要的内容组织回答，不逐项汇报，也不必给每个缺口都加一句记不清。场景名只是资料位置，不是当时说出的台词；提纲里没有原文行的细节要谨慎。文本顺序不等于跨篇章的世界时间，只有原文明示时才能说后来、因此。不要混合回忆中的过去与当时的现实，不推断人物近况，也不补没有证据的人物命运。编号只供你对照，不要说出来。")
            else:
                lines.append("以下是同一问题的候选记忆；先抓住主要冲突、行动与结果，挑必要的内容组织回答，不逐项汇报。没有证据的因果不要补写，也不必给每个缺口都加一句记不清。材料按相关度排列，不代表事件先后；只有原文明示时才能说后来、因此。不要混合回忆中的过去与当时的现实，不推断跨篇章世界时间或人物近况；标为不知情的事不要说成自己亲历，也不补没有证据的人物命运。编号只供你对照，不要说出来。")
        else:
            lines.append("以下是和这句话有关的零散记忆，都是过去的事，不代表现在。记忆排列不代表事件先后；没有原文依据时，不用随后、因此连接两件事，也不要把概括写成原话引号。没有找到某句原话，不代表它从未说过。编号只供你对照，不要说出来。")
        lines.append("摘要中可能夹有博士未说出口的想法或感受；那不是你能直接回忆的见闻，只转述听见的台词和看见的行动。")
        if plan.reason:
            lines.append("先找能说明目的或动机的内容；材料只有经过时，就说原因不清楚，不要把经过当作原因。")
        lines.append(pack.render())
    else:
        lines.append("本轮没有调出记忆。不要主动讲具体的过去事件或别人的近况"
                     + ("；需要时调用 canon_recall。" if tools else "。"))
    if plan.lane == "status":
        if fact_valid:
            lines.append(fact_block)
        else:
            who = "、".join(plan.subjects)
            lines.append(
                f"[近况]\n关于{who}现在的情况，你没有可靠的消息。可以说最后记得的情况，只说那是之前的事，"
                f"不要说隔了多久；之后的情况说不清楚。不要猜测或暗示{who}现在在哪里、在做什么、身体怎样、能不能联系上。"
            )
    return "\n".join(lines)


def build_system(persona: str, doctor: bool, plan: TurnPlan, pack: EvidencePack,
                 fact_block: str, fact_valid: bool, tools: bool, archives: bool = False) -> str:
    identity = "当前对话者是博士。" if doctor else "当前对话者的博士身份未确认，不要自行认定。"
    rules = OUTPUT_RULES + (TOOL_RULE if tools else "") + (ARCHIVE_RULE if tools and archives else "")
    return "\n\n".join((persona, identity,
                        knowledge(plan, pack, fact_block, fact_valid, tools), rules))


def _model_settings(model_type: str | None) -> tuple[str, str, str, float]:
    try:
        import run_config as config
    except ImportError as exc:
        raise ValueError("找不到 run_config.py；请按 run_config.py.example 配置模型") from exc
    chosen = model_type or getattr(config, "CANON_CHAT_MODEL_TYPE", "") or getattr(
        config, "CANON_MODEL_TYPE", "") or getattr(config, "MODEL_TYPE", "lmstudio")
    if chosen == "kcl":
        url = getattr(config, "KCL_API_URL", "https://ai.create.kcl.ac.uk/api/v1")
        key = os.environ.get("CANON_CHAT_API_KEY") or getattr(config, "KCL_API_KEY", "")
        model = getattr(config, "KCL_MODEL", "")
    elif chosen == "deepseek":
        url = "https://api.deepseek.com"
        key = os.environ.get("CANON_CHAT_API_KEY") or getattr(config, "DEEPSEEK_API_KEY", "")
        model = getattr(config, "DEEPSEEK_MODEL", "")
    elif chosen == "lmstudio":
        url = getattr(config, "LMSTUDIO_API_URL", "http://localhost:1234/v1")
        key = "lm-studio"
        model = getattr(config, "LMSTUDIO_MODEL", "")
    else:
        raise ValueError(f"不支持的模型类型：{chosen}")
    if not key or key == "your_deepseek_api_key_here" or not model:
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

    def chat(self, messages: list[dict], temperature: float,
             tools: list[dict] | None = None) -> dict:
        body: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        started = time.perf_counter()
        response = self.client.post(
            f"{self.url}/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json=body,
        )
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
    focus: str | None = None
    topics: tuple[str, ...] = ()
    topic_idle: int = 0
    plan: TurnPlan | None = None
    pack: EvidencePack | None = None
    fact_block: str = ""
    tool_queries: list[str] = field(default_factory=list)
    report: CheckReport | None = None
    metrics: dict = field(default_factory=dict)
    active_history: list[dict[str, str]] = field(default_factory=list)


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


def generate(llm: ModelClient, session: Session, system: str, query: str,
             tools: list[dict], handlers: dict, temperature: float) -> tuple[str, int]:
    """Let the model call its tools on its own; tool rounds stay out of the saved history."""
    messages = [{"role": "system", "content": system}, *session.active_history,
                {"role": "user", "content": query}]
    calls = rounds = 0
    retried_empty = False
    while True:
        offer = session.tools and rounds < MAX_TOOL_ROUNDS
        try:
            message = llm.chat(messages, temperature, tools if offer else None)
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
        if not message["content"] and not retried_empty:
            retried_empty = True
            continue
        return message["content"], calls


def lane_label(plan: TurnPlan) -> str:
    who = "、".join(plan.subjects) or ("检索判定" if plan.by_retrieval else "")
    route_name = "剧情综述" if plan.overview else LANE_LABEL[plan.lane]
    return f"路线：{route_name}" + (f"（{who}）" if who else "")


def trace_line(session: Session, calls: int) -> str:
    plan, report = session.plan, session.report
    parts = [lane_label(plan)]
    if session.tool_queries:
        parts.append("调用工具：" + "、".join(session.tool_queries))
    if report.refetched:
        parts.append("按回复补查：" + "、".join(report.refetched))
    if report.reviewed:
        parts.append("核验：" + ("无效结果，按无依据处理" if report.review_failed
                                else f"{len(report.problems)} 句无依据" if report.problems else "通过"))
    if report.rewrote:
        parts.append(f"改写提问或出戏句 {report.rewrote} 句")
    if report.revised:
        parts.append("已修订")
    if report.rechecked:
        parts.append("已复核修订句")
    if report.dropped:
        parts.append(f"修订后又删去 {report.dropped} 句")
    if report.questions_removed:
        parts.append(f"删去结尾提问 {report.questions_removed} 句")
    if report.meta_removed:
        parts.append(f"删去出戏句 {report.meta_removed} 句")
    parts.append(f"模型调用 {calls} 次")
    if session.metrics:
        parts.append(f"证据 {session.metrics['evidence_tokens']}/{session.metrics['evidence_budget']} token（估算）")
        parts.append(f"本轮 {session.metrics['seconds']:.1f}s")
        if session.metrics.get("prompt_tokens") is not None:
            parts.append(f"API 输入/输出 {session.metrics['prompt_tokens']}/{session.metrics['completion_tokens']}")
    return "[canon] " + "｜".join(parts)


def print_sources(session: Session) -> None:
    if session.plan is None:
        print("  [canon] 还没有对话")
        return
    print(f"  {lane_label(session.plan)}")
    for item in session.pack.items if session.pack else ():
        print(f"  {item.eid} {CHANNEL_LABEL.get(item.channel, item.channel)} {item.source}｜{item.summary[:40]}")
    if session.pack is not None and not session.pack.items:
        print("  [canon] 没有调出记忆")
    if session.fact_block:
        print(session.fact_block)
    if session.report and session.report.problems:
        for index, reason in sorted(session.report.problems.items()):
            print(f"  第 {index} 句「{session.report.sentences[index - 1].strip()}」：{reason}")


def run_turn(query: str, *, reader: CanonReader, llm: ModelClient | None, session: Session,
             args: argparse.Namespace, persona: str, profile: str) -> None:
    started = time.perf_counter()
    request_offset = len(getattr(llm, "request_metrics", []))
    session.active_history = conversation_history(session.history, query)
    plan = route(reader, plan_turn(reader, query, session.focus, args.as_of, session.topics),
                 query, args.doctor)
    if plan.focus or plan.lane != "chat":
        session.focus = plan.focus
    if plan.topics:
        session.topics = plan.topics
        session.topic_idle = 0
    elif plan.lane == "chat":
        session.topic_idle += 1
        if session.topic_idle >= 3:
            session.focus = None
            session.topics = ()
    else:
        session.focus = None
        session.topics = ()
        session.topic_idle = 0
    evidence = EvidenceAssembler(reader, plan, EvidenceSettings(
        doctor=args.doctor, top_k=args.top_k, evidence_lines=args.evidence_lines,
        token_budget=args.token_budget, as_of=args.as_of))
    pack = evidence.pack
    session.plan, session.pack, session.report = plan, pack, None
    session.tool_queries = []
    evidence.prefetch()
    if reader.retrieval:
        trace = reader.retrieval.last_trace
        print(f"[retrieval] {reader.retrieval.mode}；"
              f"{'降级' if trace.get('degraded') else '就绪'}；"
              f"{trace.get('seconds', 0):.3f}s")
        if trace.get("degraded"):
            print(f"[retrieval] {trace.get('embedding_error') or trace.get('rerank_error')}")
    fact_block, fact_valid = evidence.facts()
    session.fact_block = fact_block
    if args.show_sources or args.dry_run:
        print_sources(session)
    if args.dry_run or llm is None:
        print(knowledge(plan, pack, fact_block, fact_valid, tools=False))
        return

    def recall(arguments: dict) -> str:
        wanted = str(arguments.get("query", "")).strip()[:100]
        session.tool_queries.append(f"回忆「{wanted or '空'}」")
        if not wanted:
            return "没有想起相关的事。"
        added = evidence.fetch(wanted)
        if added:
            return pack.render(added)
        return "没有想起新的相关的事；只根据上面已有的记忆回答，没有的就说记不清。"

    def overview(arguments: dict) -> str:
        wanted = str(arguments.get("query", "")).strip()[:100]
        session.tool_queries.append(f"综述「{wanted or '空'}」")
        if not wanted:
            return "没有指定要综述的经历。"
        added, trace = evidence.fetch_overview(wanted)
        return overview_tool_result(pack, added, trace, evidence.budget)

    def add_archive(key: str, source: str, body: str) -> Memory | None:
        if key in pack or not body:
            return None
        body = body[:ARCHIVE_CHARS]
        minimum = min(40, len(body))
        low, high, best = minimum, len(body), 0
        while low <= high:
            size = (low + high) // 2
            summary = f"{source}：{clip(body, size)}"
            item = pack.add(key, source, "archive", summary, (), prefix="A")
            fits = estimate_tokens(pack.render()) <= evidence.budget
            pack.pop()
            if fits:
                best = size
                low = size + 1
            else:
                high = size - 1
        if not best:
            return None
        return pack.add(key, source, "archive", f"{source}：{clip(body, best)}", (), prefix="A")

    def archive(arguments: dict) -> str:
        name = str(arguments.get("name", "")).strip()[:40]
        section = str(arguments.get("section", "")).strip()[:20]
        session.tool_queries.append(f"档案「{name or '空'}" + (f"·{section}" if section else "") + "」")
        ids = reader.archive_ids(name)
        if not ids:
            return f"罗德岛档案里没有找到“{name}”。"
        added, notes = [], []
        for archive_id in ids[:2]:
            rows = reader.archive_sections(archive_id, every_form=args.archive_all)
            if not rows:
                continue
            titles = list(dict.fromkeys(row["title"] for row in rows))
            chosen = ([row for row in rows if section and (section in row["title"] or row["title"] in section)]
                      or [row for row in rows if not section and row["title"] in ARCHIVE_DEFAULT]
                      or rows[:1])
            for row in chosen[:ARCHIVE_SECTIONS]:
                key = f"archive:{archive_id}#{row['seq']}.{row['version']}"
                if key in pack:
                    continue
                label = ARCHIVE_KIND.get(row["kind"], "档案")
                item = add_archive(key, f"{label} {row['name']}·{row['title']}", row["text"])
                if item:
                    added.append(item)
            notes.append(f"{rows[0]['name']}的{ARCHIVE_KIND.get(rows[0]['kind'], '档案')}可查的段："
                         f"{clip('、'.join(titles), 80)}")
        body = pack.render(added) if added else "本轮证据预算已满，或档案没有可加入的内容。"
        return body + "\n" + "\n".join(notes)

    def messages() -> list[dict]:
        system = build_system(persona, args.doctor, plan, pack, fact_block, fact_valid, False)
        return [{"role": "system", "content": system}, *session.active_history,
                {"role": "user", "content": query}]

    def refetch(names: list[str]) -> int:
        known = reader.topic_mentions(pack.render())
        identity_hits = [reader.identity_hit(name, prior) for name in names for prior in known]
        linked = fill(pack, [hit for hit in identity_hits if hit], None,
                      evidence.budget, total_budget=evidence.budget)
        return len(linked) + len(evidence.fetch(" ".join(names)))

    def sources() -> str:
        said = [m["content"] for m in session.active_history if m["role"] == "user"] + [query]
        dialogue = [*session.active_history, {"role": "user", "content": query}]
        identity = ("[对话者]\n当前对话者是博士；[资料]里的“对方（博士）”就是当前对话者。" if args.doctor else
                    "[对话者]\n当前对话者不是博士；[资料]里的“博士”是另一个人，与博士有关的经历不算和当前对话者的共同经历。")
        parts = [identity, "", "[资料]", pack.render() or "（本轮没有资料）"]
        if fact_valid:
            parts.append(fact_block)
        parts += ["", "[人设档案]", profile or "（无）", "", "[对话者本次说过的话]",
                  *(f"· {text}" for text in said), "", "[本次对话记录]",
                  "以下只证明本次谁说过什么，不证明所说的世界事实为真。",
                  *(f"C{i} {'对话者' if m['role'] == 'user' else '阿米娅'}：{m['content']}"
                    for i, m in enumerate(dialogue, 1))]
        return "\n".join(parts)

    archives = reader.has_archives
    tools = [RECALL_TOOL, OVERVIEW_TOOL, ARCHIVE_TOOL] if archives else [RECALL_TOOL, OVERVIEW_TOOL]
    handlers = {"canon_recall": recall, "canon_overview": overview, "operator_archive": archive}
    tool_offer = session.tools and estimate_tokens(pack.render()) + 80 < evidence.budget
    system = build_system(persona, args.doctor, plan, pack, fact_block, fact_valid, tool_offer, archives)
    draft, calls = generate(llm, session, system, query, tools if tool_offer else [], handlers,
                            args.temperature)
    answer, report = check_reply(
        draft, complete=llm.complete, messages=messages, pack=pack,
        find_entities=reader.entities_in, refetch=refetch, sources=sources,
        extra_ids={"F"} if fact_valid else None, current_ok=fact_valid,
        force_review=bool(pack.items), temperature=args.temperature,
        allow_questions=False, fallback=FALLBACK,
        coherent_revision=True, retry_review=True,
        conversation_ids={f"C{i}" for i in range(1, len(session.active_history) + 2)},
    )
    request_metrics = getattr(llm, "request_metrics", [])[request_offset:]
    usage = {key: sum(row[key] for row in request_metrics) if request_metrics and
             all(row[key] is not None for row in request_metrics) else None
             for key in ("prompt_tokens", "completion_tokens")}
    session.report = report
    session.metrics = {"seconds": round(time.perf_counter() - started, 3),
                       "calls": calls + report.calls,
                       "history_tokens": sum(estimate_tokens(m["content"]) for m in session.active_history),
                       "evidence_tokens": estimate_tokens(pack.render()),
                       "evidence_budget": evidence.budget,
                       "intent": plan.intent, "name_corrections": dict(plan.corrections),
                       **usage,
                       "first_response_seconds": request_metrics[0]["seconds"] if request_metrics else None,
                       "expansion_candidates": reader.last_expansion_trace.get("candidates", 0)}
    print(trace_line(session, calls + report.calls))
    for index, reason in sorted(report.problems.items()):
        print(f"  第 {index} 句「{report.sentences[index - 1].strip()}」：{reason}")
    print(f"阿米娅> {answer}")
    session.history.extend(({"role": "user", "content": query},
                            {"role": "assistant", "content": answer}))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="临时 canon 对话：数据库只读，聊天只在内存")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--persona-file", type=Path, default=DEFAULT_PERSONA)
    parser.add_argument("--model-type", choices=("kcl", "deepseek", "lmstudio"))
    parser.add_argument("--not-doctor", dest="doctor", action="store_false", help="对照测试：当前对话者不是博士")
    parser.set_defaults(doctor=True)
    parser.add_argument("--as-of", help="按已审阅的世界时间点 ID 查询状态事实")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--token-budget", type=int, default=900,
                        help="本轮证据基础上限；明确长剧情综述最多浮动至 2400，其余拥挤证据最多至 1200")
    parser.add_argument("--evidence-lines", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--no-tools", action="store_true", help="不向模型提供 canon_recall、canon_overview 和档案查询工具")
    parser.add_argument("--archive-all", action="store_true",
                        help="档案查询也返回升变档案、其他形态和隐藏段（默认只返回本体形态）")
    parser.add_argument("--show-sources", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="只显示路线、检索与注入片段，不调用模型")
    parser.add_argument("--question", help="只问一次；不填则进入连续对话")
    parser.add_argument("--questions", nargs="?", const=DEFAULT_QUESTIONS, type=Path, metavar="JSONL",
                        help="按题库批量评测检索；不填路径使用本地 retrieval-200-v1 题库")
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
    if args.questions is not None and args.as_of:
        parser.error("题库评测不使用 --as-of；请单独测试指定时间点")
    if args.retrieval == "auto":
        from devtools.canon.retrieval import index_available
        offline = (args.dry_run or args.questions is not None) and not args.allow_remote
        args.retrieval = "hybrid" if not offline and index_available(args.db, args.index) else "baseline"
    if (args.dry_run or args.questions is not None) and args.retrieval != "baseline" and not args.allow_remote:
        parser.error("远程检索需要显式 --allow-remote")
    if args.top_k < 1 or args.token_budget < 0 or args.evidence_lines < 0:
        parser.error("top-k 需为正数；token-budget 和 evidence-lines 不能为负")
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
    print("本工具不写本地聊天记录；调用远程接口时，请以接口服务方的留存规则为准。")
    if llm is not None:
        print("[canon] 闲聊只生成一次；回复涉及剧情时加一次核验，无依据句会修订，新剧情句再复核"
              + ("；模型可自行调用 canon_recall" + ("和 operator_archive" if reader.has_archives else "") + "。"
                 if not args.no_tools else "。"))
    if args.question is None:
        print("输入 /quit 退出，/clear 清空内存中的对话，/sources 查看上一轮的路线、记忆和核验。")
    session = Session(tools=not args.no_tools)
    profile = persona_profile(persona)
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
                run_turn(query, reader=reader, llm=llm, session=session, args=args,
                         persona=persona, profile=profile)
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
