"""One canon turn: its recall tools, the prompts built from its evidence, and the finishing reply check.

The terminal rebuilds its system prompt before every model request, so memories a tool adds appear once, in
the prompt. A host that keeps one system prompt for the whole tool loop, such as a Core generation, gets the
canon part of the system prompt once and the memory block in each tool result instead.
"""
from __future__ import annotations

from typing import Callable

from .assembly import EvidenceSettings
from .gateway import CheckReport, EvidencePack, Memory, check_reply
from ..constant_utils import ARCHIVE_DEFAULT, ARCHIVE_KIND, CIRCLED
from ..read.packing import clip, estimate_tokens, fill
from ..read.query import plan_turn, route, task_of
from ..read.reader import CanonReader
from .recall import VERIFY_EXTRA, CanonRecall, present_phrase
from ...hooks.recall_tools import RecallTool, register, registered
from ...utils.prompts.prompt_canon_utils import ARCHIVE_TOOL, PROBE_TOOL, recall_tool
from ...utils.prompts.prompt_canon_utils import (
    ADDED_NOTE,
    ARCHIVE_RULE,
    FALLBACK,
    MEMORY_NOTE,
    OUTLINE_NOTE,
    OUTPUT_RULES,
    RECALL_POLICY,
    SKELETONS,
    STYLE,
    TIME_RULE,
    WRAP_UP,
)
from ..settings import SETTINGS

MAX_TOOL_ROUNDS = SETTINGS.turn.max_tool_rounds
ARCHIVE_SECTIONS = SETTINGS.turn.archive_sections
ARCHIVE_CHARS = SETTINGS.turn.archive_chars


def outline_note(task: str) -> str:
    return OUTLINE_NOTE.format(blocks="\n".join(f"{name}：（{hint}）" for name, hint in SKELETONS[task]))


def between(text: str, start: str, end: str) -> str:
    head = text.find(start)
    if head < 0:
        return ""
    tail = text.find(end, head + len(start))
    return text[head + len(start): tail if tail >= 0 else len(text)].strip()


def spoken(draft: str) -> tuple[str, str]:
    """The reply the Doctor hears and the outline the model wrote for itself; a reply without tags is all speech."""
    outline, answer = between(draft, "<提纲>", "</提纲>"), between(draft, "<回答>", "</回答>")
    if not answer:
        close = draft.find("</提纲>")
        answer = draft[close + len("</提纲>"):].strip() if close >= 0 else draft.strip()
    return answer, outline


def empty_blocks(outline: str, task: str) -> list[tuple[str, str]]:
    """Blocks the model marked 无: the parts of the answer its memories lack, for one targeted recall each."""
    missing = []
    for name, hint in SKELETONS.get(task, ()):
        line = next((row.strip() for row in outline.splitlines() if row.strip().startswith(name)), "")
        rest = line[len(name):].strip("：: ")
        if rest.startswith("无") and not any(mark in rest for mark in CIRCLED):
            missing.append((name, hint))
    return missing


def knowledge(pack: EvidencePack, tools: bool, task: str = "fact", outline: bool = False) -> str:
    if pack.items:
        style = STYLE.get(task, STYLE["fact"]) + ("\n\n" + outline_note(task) if outline and task in SKELETONS else "")
        return "\n".join(("[你的记忆]", MEMORY_NOTE, pack.render(), "", style))
    return RECALL_POLICY if tools else "[你的记忆]\n本轮没有调出记忆。讲到原作里的具体事件时，说没印象就好。"


def build_block(doctor: bool, pack: EvidencePack, tools: bool, archives: bool = False,
                anchored: bool = False, task: str = "fact", outline: bool = False) -> str:
    """Everything canon adds after the persona: who is talking, the recall policy or memories, and the rules."""
    identity = "当前对话者是博士。" if doctor else "当前对话者的博士身份未确认，不要自行认定。"
    rules = OUTPUT_RULES + (TIME_RULE if anchored else "") + (ARCHIVE_RULE if tools and archives else "")
    return "\n\n".join((identity, knowledge(pack, tools, task, outline), rules))


def build_system(persona: str, doctor: bool, pack: EvidencePack, tools: bool, archives: bool = False,
                 anchored: bool = False, task: str = "fact", outline: bool = False) -> str:
    return "\n\n".join((persona, build_block(doctor, pack, tools, archives, anchored, task, outline)))


def supplement_recall(reader: CanonReader, recall: CanonRecall, query: str, doctor: bool) -> bool:
    """Safety net: when the model recalled nothing, a story question is still recalled once, as the local router reads it.

    An archive answers only an archive request; a story question the model sent to the archive is still recalled.
    """
    if any(entry["tool"] == "canon_recall" for entry in recall.log) or (recall.task == "lookup" and recall.pack.items):
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


def archive_names(reader: CanonReader, query: str) -> list[str]:
    """Names in the question that have an archive; a titled mention such as 某某医生 falls back to the name it holds.

    A name the entity table lacks is still found by the archive's own name.
    """
    names = []
    for name in reader.entities_in(query):
        candidates = (name, *sorted((other for other in reader.entity_type if 2 <= len(other) < len(name)
                                     and other in name), key=len, reverse=True))
        found = next((candidate for candidate in candidates if reader.archive_ids(candidate)), None)
        if found:
            names.append(found)
    if not names:
        titles = {row[0] for row in reader.db.execute("SELECT name FROM archives") if row[0]}
        names = sorted((title for title in titles if title in query), key=len, reverse=True)
    return list(dict.fromkeys(names))


def tier_label(log: list[dict]) -> str:
    recalls = [entry for entry in log if entry["tool"] == "canon_recall"]
    archives = [entry for entry in log if entry["tool"] == "operator_archive"]
    if not recalls:
        return "档位：查档案（" + "、".join(entry["name"] for entry in archives) + "）" if archives else "档位：不召回"
    tier = "深度探索" if any(entry["depth"] == "deep" for entry in recalls) else "轻量召回"
    paths = "、".join(f"{entry['path']}「{entry['subject'] or entry['query'][:12]}」" for entry in recalls)
    return f"档位：{tier}（{paths}）"


class CanonTurn:
    """One turn's recall state, tools and prompts; the terminal and the Core generation path share it."""

    def __init__(self, reader: CanonReader, settings: EvidenceSettings, *, query: str, persona: str,
                 history: list[dict], prompt: str | None = None, tools: bool = True,
                 archive_all: bool = False) -> None:
        self.reader, self.query, self.persona, self.history = reader, query, persona, history
        self.prompt = prompt or query
        self.doctor, self.archive_all, self.tools_enabled = settings.doctor, archive_all, tools
        self.recall = CanonRecall(reader, settings)
        self.evidence, self.pack = self.recall.evidence, self.recall.pack
        self.task = self.recall.task = task_of(query)
        self.tool_queries: list[str] = []
        self.archives = reader.has_archives
        self.anchored = bool(reader.placing)
        self.think = self.task in SKELETONS
        self.offer = False
        self.executed = 0
        self.shown: dict[str, str] = {}
        self.draft = self.outline = ""

    def start(self) -> None:
        """An archive request is read directly; tools are offered only while no memory is in hand."""
        direct = archive_names(self.reader, self.query) if self.task == "lookup" and self.archives else []
        for name in direct[:2]:
            self.archive({"name": name}, direct=True)
        self.offer = self.tools_enabled and not self.pack.items

    def probe(self, arguments: dict) -> str:
        wanted = str(arguments.get("query", "")).strip()[:120] or self.query
        self.tool_queries.append(f"探查「{wanted[:16]}」")
        return self.recall.probe(wanted)

    def remember(self, arguments: dict) -> str:
        wanted = str(arguments.get("query", "")).strip()
        result = self.recall.recall(wanted, str(arguments.get("path", "event")),
                                    str(arguments.get("subject", "")), str(arguments.get("depth", "light")))
        entry = self.recall.log[-1]
        self.tool_queries.append(f"回忆「{entry['subject'] or wanted[:16]}」{entry['path']}/{entry['depth']}")
        return result

    def _add_archive(self, key: str, source: str, body: str) -> Memory | None:
        pack = self.pack
        if key in pack or not body:
            return None
        body = body[:ARCHIVE_CHARS]
        minimum = min(40, len(body))
        low, high, best = minimum, len(body), 0
        while low <= high:
            size = (low + high) // 2
            summary = f"{source}：{clip(body, size)}"
            pack.add(key, source, "archive", summary, (), prefix="A")
            fits = estimate_tokens(pack.render()) <= self.evidence.budget
            pack.pop()
            if fits:
                best = size
                low = size + 1
            else:
                high = size - 1
        if not best:
            return None
        return pack.add(key, source, "archive", f"{source}：{clip(body, best)}", (), prefix="A")

    def archive(self, arguments: dict, direct: bool = False) -> str:
        reader, pack = self.reader, self.pack
        name = str(arguments.get("name", "")).strip()[:40]
        section = str(arguments.get("section", "")).strip()[:20]
        self.tool_queries.append(f"档案「{name or '空'}" + (f"·{section}" if section else "") + "」"
                                 + ("（直接查）" if direct else ""))
        self.recall.log.append({"tool": "operator_archive", "name": name, "section": section, "direct": direct})
        ids = reader.archive_ids(name)
        if not ids:
            return f"罗德岛档案里没有找到“{name}”。"
        added, notes = [], []
        for archive_id in ids[:2]:
            rows = reader.archive_sections(archive_id, every_form=self.archive_all)
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
                item = self._add_archive(key, f"{label} {row['name']}·{row['title']}", row["text"])
                if item:
                    added.append(item)
            notes.append(f"{rows[0]['name']}的{ARCHIVE_KIND.get(rows[0]['kind'], '档案')}可查的段："
                         f"{clip('、'.join(titles), 80)}")
        head = (f"查到 {len(added)} 段，已放进[你的记忆]。" if added
                else "本轮证据预算已满，或档案没有可加入的内容。")
        return head + "\n" + "\n".join(notes)

    def refetch(self, names: list[str]) -> int:
        reader, pack, evidence = self.reader, self.pack, self.evidence
        ceiling = evidence.budget + VERIFY_EXTRA
        known = reader.topic_mentions(pack.render())
        identity_hits = [reader.identity_hit(name, prior) for name in names for prior in known]
        linked = fill(pack, [hit for hit in identity_hits if hit], None, VERIFY_EXTRA, total_budget=ceiling)
        return len(linked) + len(evidence.fetch(" ".join(names), budget=VERIFY_EXTRA, ceiling=ceiling))

    @property
    def handlers(self) -> dict[str, Callable[[dict], str]]:
        return {tool.name: (lambda arguments, tool=tool: tool.handle(self, arguments)) for tool in registered()}

    def tools(self) -> list[dict]:
        return [tool.schema(self) for tool in registered() if tool.offered(self)]

    def system(self) -> str:
        return build_system(self.persona, self.doctor, self.pack, self.offer, self.archives, self.anchored,
                            self.task, self.think)

    def block(self) -> str:
        """The canon part of a host system prompt that stays fixed for the whole tool loop."""
        self.shown = self.pack.labels()
        return build_block(self.doctor, self.pack, self.offer, self.archives, self.anchored, self.task, self.think)

    def messages(self, outline: bool = False) -> list[dict]:
        return [{"role": "system", "content": build_system(self.persona, self.doctor, self.pack, False,
                                                          self.archives, self.anchored, self.task, outline)},
                *self.history, {"role": "user", "content": self.prompt}]

    def tool_text(self, name: str, arguments: dict) -> str:
        """A tool result for a host with a fixed system prompt: the memories travel with the result.

        The first result with memories carries the whole memory block; a later one carries only the memories not
        yet shown, placed among those already shown, since earlier results stay in the host's conversation.
        Executions are capped at the terminal's tool rounds; later calls get the wrap-up note.
        """
        handler = self.handlers.get(name)
        if handler is None:
            return f"没有名为 {name} 的工具。"
        if self.executed >= MAX_TOOL_ROUNDS:
            return WRAP_UP
        self.executed += 1
        before = len(self.pack.items)
        result = handler(arguments if isinstance(arguments, dict) else {})
        if len(self.pack.items) == before:
            return result
        if not self.shown:
            self.shown = self.pack.labels()
            return f"{result}\n\n{knowledge(self.pack, False, self.task, self.think)}"
        added, self.shown = self.pack.render_new(self.shown)
        return f"{result}\n\n{ADDED_NOTE}\n{added}"

    def settle(self, draft: str, complete: Callable[[list[dict], float], str], temperature: float, *,
               supplement: Callable = supplement_recall) -> tuple[str, int]:
        """The reply before its check: the safety-net recall, then one targeted recall per empty outline block."""
        calls = 0
        if self.offer and supplement(self.reader, self.recall, self.query, self.doctor):
            self.tool_queries.append("兜底补召回")
            draft, calls = complete(self.messages(self.think), temperature) or draft, calls + 1
        reply, outline = spoken(draft)
        gaps = empty_blocks(outline, self.task) if self.think and self.pack.items else []
        if gaps:
            before = len(self.pack.items)
            for _, hint in gaps[:2]:
                self.recall.recall(f"{self.query} {hint}", "event", "", "light")
            self.tool_queries.append("按提纲补查：" + "、".join(name for name, _ in gaps[:2]))
            if len(self.pack.items) > before:
                draft, calls = complete(self.messages(True), temperature) or draft, calls + 1
                reply, outline = spoken(draft)
        self.draft, self.outline = draft, outline
        return reply, calls

    def check(self, reply: str, complete: Callable[[list[dict], float], str], temperature: float, *,
              check: Callable = check_reply) -> tuple[str, CheckReport]:
        """Only a reply built on memories is checked against them; without memories it stands or falls back."""
        if not self.pack.items:
            return reply or FALLBACK, CheckReport()
        said = [message["content"] for message in self.history if message["role"] == "user"] + [self.query]
        heard = "\n".join(message["content"] for message in [*self.history, {"content": self.query}])
        return check(
            reply, complete=complete, messages=self.messages, pack=self.pack, find_entities=self.reader.entities_in,
            refetch=self.refetch, temperature=temperature, fallback=FALLBACK, profile=self.reader.profile,
            task=self.task, allowed=[name for text in said for name in self.reader.entities_in(text)], heard=heard)


register(RecallTool("canon_probe", lambda turn: PROBE_TOOL, CanonTurn.probe))
register(RecallTool("canon_recall", lambda turn: recall_tool(present_phrase(turn.reader)), CanonTurn.remember))
register(RecallTool("operator_archive", lambda turn: ARCHIVE_TOOL, CanonTurn.archive, offered=lambda turn: turn.archives))
