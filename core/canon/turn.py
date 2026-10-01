"""One canon turn: its recall tools, the prompts built from its evidence, and the finishing reply check.

The terminal rebuilds its system prompt before every model request, so memories a tool adds appear once, in
the prompt. A host that keeps one system prompt for the whole tool loop, such as a Core generation, gets the
canon part of the system prompt once and the memory block in each tool result instead.
"""
from __future__ import annotations

from typing import Callable

from .assembly import EvidenceSettings
from .gateway import CIRCLED, CheckReport, EvidencePack, Memory, check_reply
from .packing import clip, estimate_tokens, fill
from .query import plan_turn, route, task_of
from .reader import CanonReader
from .recall import PROBE_TOOL, VERIFY_EXTRA, CanonRecall, present_phrase, recall_tool

MAX_TOOL_ROUNDS = 2
FALLBACK = "嗯……这件事我记不太清了。"
WRAP_UP = "（回忆次数已用完，不要再调用工具；只根据[你的记忆]直接回答。）"
ADDED_NOTE = ("[你的记忆·接着想起的]\n这是这一轮又想起的事，接在前面的[你的记忆]后面看，前面的不再重复。"
              "新想起的事标作“新1”“新2”，按发生先后编号，括号里写着它排在前面哪件事的前后。编号和括号只供你对照，不要说出来。")
OUTPUT_RULES = (
    "[回复要求]\n"
    "· 先回应博士说的话；自然交流时可以顺势问一句，不要用反问代替回答。\n"
    "· 不要说出原作、剧情、章节、资料、编号、检索、数据库这类词。\n"
    "· 讲过去的事只用[你的记忆]里有的内容，不添加其中没有的动作、神情、情绪、数字或原因；过去的事说成过去。\n"
    "· 记忆里有的直接说，不要在开头或结尾声明记不清、需要时间或给不了全部；问到的事记忆里确实没有，只在那一处说一句没印象。"
    "说完就停，不要用“如果您还想……我可以……”收尾。\n"
    "· 延续本次交流，避免重复已经讲过的经历和同一句关心。不要凭几句话断定博士情绪反常，也不要编造博士平时的习惯。\n"
    "· 对未来的判断只能基于你知道的事，并明确是判断；不知情的事件不能靠加上可能、记不清或不确定来透露。"
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
    "以下是你这一轮想起的事，编号就是发生的先后；标着“先后不明”的不要和别的事排先后。"
    "括号里是时间和你怎么知道的；标着“最近”的才是接近现在的事，更早的事说成当时的事。"
    "摘要里博士没说出口的想法不是你能知道的。编号和括号只供你对照，不要说出来。"
)
STYLE = {
    "recount": ("[讲法]\n这一轮是在讲一段经过，不受三句的限制，用一段话讲清楚，约 150–300 字：先一句点出是哪件事，"
                "再按编号顺序讲起因、经过和结果，一个编号最多一两句，不重要的可以跳过。编号之间用“后来”“接着”“到……的时候”连接；"
                "只有〔因果〕一行列出的两件事之间才能说“所以”“因此”，其他地方要说原因就说成“在我看来”。"
                "最后可以用一句说说你现在的感受。"),
    "fact": ("[讲法]\n先直接回答：问了几项就答几项，每一项都说到；再用一两句交代当时的情况。说两件事的先后，以编号为准。"),
    "reason": ("[讲法]\n这一轮在问原因：先直接说原因，也就是记忆里明说的动机、目的或当时说出口的理由，问了几项就答几项；"
               "再用一两句交代当时的情况。记忆里只有经过、没有明说原因时，不要把经过当成原因，说成你自己的判断，例如“在我看来……”。"),
    "lookup": ("[讲法]\n这一轮是在转述档案：说成“档案上写着……”，把博士要的内容说清楚，不受三句的限制；"
               "档案里没写的，就说档案里没写。"),
}


SKELETONS = {
    "recount": (("起因", "为什么、在哪里、有谁"), ("经过", "按先后的关键时刻"), ("结果", "最后怎样收场"), ("感受", "你此刻怎么看")),
}
OUTLINE_NOTE = (
    "[先想后说]\n先以你自己的身份想一想博士想知道什么，然后分两步写。\n"
    "第一步，在<提纲>和</提纲>之间，按下面几块逐行写：每行写块名，后面只写能用上的记忆编号（例如②④），"
    "再用不超过八个字提示用它讲什么；这块在记忆里找不到，就只写块名和“无”。不要写整句概括。"
    "记忆编号就是发生先后，起因通常在编号靠前的几条，结果通常在编号最靠后的几条。\n{blocks}\n"
    "第二步，在<回答>和</回答>之间对博士说话：按提纲的块顺序，把每块所引记忆里的具体人、动作、原话要点讲出来，"
    "写“无”的块跳过；不要提到块名、提纲和编号。"
)


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
        return {"canon_probe": self.probe, "canon_recall": self.remember, "operator_archive": self.archive}

    def tools(self) -> list[dict]:
        return [PROBE_TOOL, recall_tool(present_phrase(self.reader)), *([ARCHIVE_TOOL] if self.archives else [])]

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
