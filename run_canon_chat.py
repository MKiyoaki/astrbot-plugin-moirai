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

from core.canon.gateway import CheckReport, EvidencePack, Memory, check_reply, tidy
from core.canon.lexical import terms
from core.canon.assembly import EvidenceSettings
from core.canon.packing import CHANNEL_LABEL, clip, estimate_tokens, fill
from core.canon.query import GENERIC_CHARS, plan_turn, route
from core.canon.reader import CanonReader
from core.canon.recall import PROBE_TOOL, TURN_BUDGET, VERIFY_EXTRA, CanonRecall, present_phrase, recall_tool

ROOT = Path(__file__).resolve().parent
NEXUS_DB = ROOT / ".dev_data/canon/v7/20/api/20260924-000545-kcl-arc_nexus/canon.sqlite"
TEMPORAL_DB = ROOT / ".dev_data/canon/v7/chat/nexus-v3.sqlite"
LATEST_DB = ROOT / ".dev_data/canon/v7/chat/nexus-20260924-045430.sqlite"
SAMPLE100_DB = ROOT / ".dev_data/canon/v7/chat/100-20260924-171238.sqlite"
FULL_DB = ROOT / ".dev_data/canon/v10/all/build/canon.sqlite"
V11_DB = ROOT / ".dev_data/canon/v11/chat/full-20260928.sqlite"
DEFAULT_DB = next((path for path in (V11_DB, FULL_DB, SAMPLE100_DB, LATEST_DB, TEMPORAL_DB, NEXUS_DB)
                   if path.is_file()), FULL_DB)
DEFAULT_PERSONA = ROOT / "devtools/canon/amiya_persona.txt"
DEFAULT_QUESTIONS = ROOT / ".dev_data/canon/eval/retrieval-200-v1.jsonl"
TRACE_DIR = ROOT / ".dev_data/canon/traces"
ISSUE_LABEL = {"contradicted": "矛盾", "uncovered": "缺依据"}
MAX_TOOL_ROUNDS = 2
FALLBACK = "嗯……这件事我记不太清了。"
WRAP_UP = "（回忆次数已用完，不要再调用工具；只根据上面回忆起的内容直接回答，没有的就说记不清。）"
RETRY_NOTE = "请直接用中文回答，不要输出任何工具调用。"
TOOL_MARKUP = re.compile(r"<[｜|]+\s*DSML|<tool_call>|<function_calls>|<[｜|]tool[▁_ ]calls?[▁_ ]begin")
MODEL_TYPE_ALIASES = {"oai": "openai"}
OUTPUT_RULES = (
    "[回复要求]\n"
    "· 先回应博士说的话；自然交流时可以顺势问一句，不要用反问代替回答。拿不准过去的事实时说清楚哪部分记不清。\n"
    "· 不要说出原作、剧情、章节、资料、编号、检索、数据库这类词。\n"
    "· 讲到过去的具体经历时，只说回忆起的内容，不添加其中没有的动作、神情、情绪、数字或原因；过去的事要说成过去。\n"
    "· 回答原因要说明有依据的动机或目的；材料只有经过时，不要把经过冒充原因。"
    "\n· 先想清楚对方这一轮真正想聊的事，再直接回答。记忆是依据，不是必须逐条复述的清单。"
    "通常先说重点，再选一两件必要的事说明；需要梳理一段经过时，用一段话讲清主要经过。不要展示回答提纲。"
    "\n· 延续本次交流，避免重复已经讲过的经历和同一句关心。不要凭几句话断定博士情绪反常，"
    "也不要编造博士平时的习惯。可以表达此刻的感受、立场和疑问，不必每轮都用问题收尾。"
    "\n· 对未来的判断只能基于你知道的事，并明确是判断；不知情的事件不能靠加上可能、记不清或不确定来透露。"
)
TIME_RULE = "\n· 说到事情发生的时间，照记忆括号里的说法，用某件大事期间、之前或之后来讲，不要说出年份、月份或日期。"
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
    return "\n".join(rows) or persona


RECALL_POLICY = (
    "[回忆方式]\n先判断这句话需不需要回忆原作：\n"
    "· 只有明显不涉及过去经历的话才不需要回忆：问候、闲聊、此刻的感受、对博士的回应，以及本次对话里说过的事。"
    "罗德岛上的日常近况（天气、饮食、作息）可以自然地聊。\n"
    "· 问到某个人说过什么、做过什么、多久、几个、为什么、在哪里这类可以核对的细节，即使问法像在聊眼前的事，也要回忆；"
    "拿不准是眼前的事还是过去的事时，先回忆，不要凭印象直接回答。\n"
    "· 需要原作里某件具体的事、某人某地的经历、你对某人的看法或某人最后的情况：调用 canon_recall，默认 depth=light，选最贴近的 path。\n"
    "· 需要梳理多段经过、前因后果：canon_recall 用 depth=deep。\n"
    "· 不确定该回忆哪个人物、地点或篇章时，先调用 canon_probe。\n"
    "别人现在的伤亡、下落、身份或阵营变化这类重大状态，只说你最后知道的情况。"
)
MEMORY_NOTE = (
    "以下是这一轮回忆起的片段。括号里是事情发生的时间，标着“最近”的才是接近现在的事。"
    "说到别人现在或最近的情况，只能依据标着“最近”的片段；更早的事要说成当时的事，"
    "例如“我最后知道……是在……的时候”。排列不代表事件先后；有〔先后〕一行时以它为准，否则以括号里的时间为准；"
    "两者都排不出、也没有原文依据时，不用随后连接两件事。两件事之间的因果没有原话依据时，说成你自己的判断，例如“在我看来……”。"
    "不要把概括写成原话引号。标为不知情的事不要说成亲历。编号只供你对照，不要说出来。"
)


def knowledge(pack: EvidencePack, tools: bool) -> str:
    if pack.items:
        return "\n".join(("[你的记忆]", MEMORY_NOTE,
                          "摘要中可能夹有博士未说出口的想法或感受；那不是你能直接回忆的见闻，只转述听见的台词和看见的行动。",
                          pack.render(), *filter(None, (pack.order_note(),))))
    return RECALL_POLICY if tools else "[你的记忆]\n本轮没有调出记忆。讲到原作里的具体事件时，说记不清就好。"


def build_system(persona: str, doctor: bool, pack: EvidencePack, tools: bool, archives: bool = False,
                 anchored: bool = False) -> str:
    identity = "当前对话者是博士。" if doctor else "当前对话者的博士身份未确认，不要自行认定。"
    rules = OUTPUT_RULES + (TIME_RULE if anchored else "") + (ARCHIVE_RULE if tools and archives else "")
    return "\n\n".join((persona, identity, knowledge(pack, tools), rules))


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
    order: str = ""


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
        wrap_up = bool(session.tools and tools and not offer)
        if wrap_up and messages[-1]["role"] == "tool" and WRAP_UP not in messages[-1]["content"]:
            messages[-1] = {**messages[-1], "content": f"{messages[-1]['content']}\n{WRAP_UP}"}
        try:
            if wrap_up:
                try:
                    message = llm.chat(messages, temperature, tools, tool_choice="none")
                except ToolsRejected:
                    message = llm.chat(messages, temperature, None)
            else:
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
        unusable = not message["content"] or (wrap_up and TOOL_MARKUP.search(message["content"]))
        if unusable and not retried_empty:
            retried_empty = True
            if wrap_up:
                messages = [*messages, {"role": "user", "content": RETRY_NOTE}]
            continue
        return message["content"], calls


def supplement_recall(reader: CanonReader, recall: CanonRecall, query: str, doctor: bool) -> bool:
    """Safety net: when the model recalled nothing, a story question is still recalled once, as the local router reads it."""
    if any(entry["tool"] == "canon_recall" for entry in recall.log):
        return False
    plan = route(reader, plan_turn(reader, query, None, None), query, doctor)
    if plan.lane not in ("canon", "status"):
        return False
    if plan.lane == "status" and plan.subjects:
        recall.recall(plan.search_query, "latest", plan.subjects[0], "light")
    else:
        path, depth = (("arc", "deep") if plan.overview else ("reason", "light") if plan.reason
                       else ("impression", "light") if plan.impression else ("event", "light"))
        recall.recall(plan.search_query, path, "", depth)
    recall.log[-1]["fallback"] = True
    return bool(recall.pack.items)


def tier_label(log: list[dict]) -> str:
    recalls = [entry for entry in log if entry["tool"] == "canon_recall"]
    if not recalls:
        return "档位：不召回"
    tier = "深度探索" if any(entry["depth"] == "deep" for entry in recalls) else "轻量召回"
    paths = "、".join(f"{entry['path']}「{entry['subject'] or entry['query'][:12]}」" for entry in recalls)
    return f"档位：{tier}（{paths}）"


def trace_line(session: Session, calls: int) -> str:
    report = session.report
    parts = [tier_label(session.recall_log)]
    if session.tool_queries:
        parts.append("调用工具：" + "、".join(session.tool_queries))
    if report.refetched:
        parts.append("按回复补查：" + "、".join(report.refetched))
    if report.reviewed:
        parts.append("核验：" + ("无效结果，按无依据处理" if report.review_failed
                                else issue_counts(report) if report.problems else "通过"))
    if report.looked_up:
        parts.append(f"按句补查 {report.looked_up} 句，{report.found} 句找到新记忆")
    if report.rewrote:
        parts.append(f"改写提问或出戏句 {report.rewrote} 句")
    if report.revised:
        parts.append("已修订")
    if report.second_pass:
        parts.append("复核未过的句子已二次修订")
    if report.rechecked:
        parts.append("已复核修订句")
    if report.dropped:
        parts.append(f"修订后又删去 {report.dropped} 句")
    if report.mended:
        parts.append(f"删句后补接 {report.mended} 处")
    if report.questions_removed:
        parts.append(f"删去结尾提问 {report.questions_removed} 句")
    if report.meta_removed:
        parts.append(f"删去出戏句 {report.meta_removed} 句")
    parts.append(f"模型调用 {calls} 次")
    if session.metrics:
        parts.append(f"证据 {session.metrics['evidence_tokens']}/{session.metrics['evidence_budget']} token（估算"
                     + ("，含核验补查" if session.metrics["evidence_tokens"] > session.metrics["evidence_budget"] else "")
                     + "）")
        parts.append(f"本轮 {session.metrics['seconds']:.1f}s")
        if session.metrics.get("prompt_tokens") is not None:
            parts.append(f"API 输入/输出 {session.metrics['prompt_tokens']}/{session.metrics['completion_tokens']}")
    return "[canon] " + "｜".join(parts)


def issue_counts(report: CheckReport) -> str:
    counts = [(label, sum(status == kind for status in report.issues.values())) for kind, label in ISSUE_LABEL.items()]
    other = len(report.problems) - sum(count for _, count in counts)
    return "、".join(f"{label} {count} 句" for label, count in (*counts, ("其他", other)) if count)


def problem_lines(report: CheckReport) -> list[str]:
    return [f"第 {index} 句「{report.sentences[index - 1].strip()}」："
            + (f"[{ISSUE_LABEL[report.issues[index]]}] " if index in report.issues else "") + reason
            for index, reason in sorted(report.problems.items())]


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
             args: argparse.Namespace, persona: str, profile: str) -> None:
    started = time.perf_counter()
    request_offset = len(getattr(llm, "request_metrics", []))
    session.active_history = conversation_history(session.history, query)
    recall = CanonRecall(reader, EvidenceSettings(
        doctor=args.doctor, top_k=args.top_k, evidence_lines=args.evidence_lines,
        token_budget=args.token_budget))
    evidence, pack = recall.evidence, recall.pack
    session.pack, session.report, session.recall_log = pack, None, recall.log
    session.tool_queries = []
    if args.dry_run or llm is None:
        print("  由模型决定是否回忆；范围探查结果：")
        print(recall.probe(query))
        return

    def probe(arguments: dict) -> str:
        wanted = str(arguments.get("query", "")).strip()[:120] or query
        session.tool_queries.append(f"探查「{wanted[:16]}」")
        return recall.probe(wanted)

    def remember(arguments: dict) -> str:
        wanted = str(arguments.get("query", "")).strip()
        result = recall.recall(wanted, str(arguments.get("path", "event")),
                               str(arguments.get("subject", "")), str(arguments.get("depth", "light")))
        entry = recall.log[-1]
        session.tool_queries.append(f"回忆「{entry['subject'] or wanted[:16]}」{entry['path']}/{entry['depth']}")
        return result

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
        system = build_system(persona, args.doctor, pack, False, anchored=bool(reader.placing))
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
        parts = [identity, "", "[资料]", pack.render() or "（本轮没有资料）", *filter(None, (pack.order_note(),))]
        parts += ["", "[人设档案]", profile or "（无）", "", "[对话者本次说过的话]",
                  *(f"· {text}" for text in said), "", "[本次对话记录]",
                  "以下只证明本次谁说过什么，不证明所说的世界事实为真。",
                  *(f"C{i} {'对话者' if m['role'] == 'user' else '阿米娅'}：{m['content']}"
                    for i, m in enumerate(dialogue, 1))]
        return "\n".join(parts)

    archives = reader.has_archives
    now = present_phrase(reader)
    tools = [PROBE_TOOL, recall_tool(now), *([ARCHIVE_TOOL] if archives else [])]
    handlers = {"canon_probe": probe, "canon_recall": remember, "operator_archive": archive}
    system = build_system(persona, args.doctor, pack, session.tools, archives, anchored=bool(reader.placing))
    draft, calls = generate(llm, session, system, query, tools if session.tools else [], handlers,
                            args.temperature)
    if session.tools and supplement_recall(reader, recall, query, args.doctor):
        session.tool_queries.append("兜底补召回")
        draft, calls = llm.complete(messages(), args.temperature) or draft, calls + 1
    session.draft = draft
    if reader.retrieval and any(entry["tool"] == "canon_recall" for entry in recall.log):
        trace = reader.retrieval.last_trace
        print(f"[retrieval] {reader.retrieval.mode}；{'降级' if trace.get('degraded') else '就绪'}；"
              f"{trace.get('seconds', 0):.3f}s")
    if pack.items:
        answer, report = check_reply(
            draft, complete=llm.complete, messages=messages, pack=pack,
            find_entities=reader.entities_in, refetch=refetch, sources=sources,
            force_review=True, temperature=args.temperature,
            allow_questions=False, fallback=FALLBACK,
            coherent_revision=True, retry_review=True,
            conversation_ids={f"C{i}" for i in range(1, len(session.active_history) + 2)},
            profile=reader.profile,
            long_answer=any(entry.get("depth") == "deep" for entry in recall.log),
            lookup=lambda sentence: evidence.fetch(sentence, budget=VERIFY_EXTRA,
                                                   ceiling=evidence.budget + VERIFY_EXTRA),
        )
    else:
        answer, questions, meta = tidy(draft, allow_questions=False, profile=reader.profile)
        answer, report = answer or FALLBACK, CheckReport(questions_removed=questions, meta_removed=meta)
    request_metrics = getattr(llm, "request_metrics", [])[request_offset:]
    usage = {key: sum(row[key] for row in request_metrics) if request_metrics and
             all(row[key] is not None for row in request_metrics) else None
             for key in ("prompt_tokens", "completion_tokens")}
    session.report = report
    session.order = pack.order_note()
    session.metrics = {"seconds": round(time.perf_counter() - started, 3),
                       "calls": calls + report.calls,
                       "history_tokens": sum(estimate_tokens(m["content"]) for m in session.active_history),
                       "evidence_tokens": estimate_tokens(pack.render()) if pack.items else 0,
                       "evidence_budget": args.token_budget,
                       "tier": tier_label(recall.log), "recalls": list(recall.log),
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
            "model": getattr(llm, "model", None), "query": query, "history": session.active_history,
            "tools": session.tool_queries, "recalls": recall.log,
            "evidence": [{"eid": item.eid, "event_id": item.event_id, "channel": item.channel,
                          "source": item.source, "when": reader.time_label(item.event_id),
                          "said": reader.time_phrase(item.event_id)}
                         for item in pack.items],
            "evidence_text": pack.render(), "order": session.order, "draft": draft, "check": report.stages,
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
