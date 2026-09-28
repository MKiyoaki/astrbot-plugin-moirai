"""Evidence-scoped canon reply checks: deterministic cleanup first, model review only where plot content appears."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from typing import Callable, Iterable

from .character import AMIYA, CharacterProfile

Complete = Callable[[list[dict], float], str]

PAST_MARKERS = ("平时你", "你平时", "刚才", "那次", "那一次", "上次", "当时", "那时", "那天", "那场", "以前", "之前", "曾经", "还记得")
META_TERMS = ("原作", "剧情", "章节", "数据库", "知识库", "检索", "试跑", "语言模型", "人工智能")
CLAIM_TYPES = frozenset(("plot", "profile", "shared", "opinion", "chat", "conversation", "inference"))
FREE_TYPES = frozenset(("opinion", "chat"))
CLAIM_KINDS = frozenset(("plot", "profile", "shared", "inference"))
STATUSES = frozenset(("supported", "contradicted", "uncovered"))
CLAIM_LOOKUPS = 3
MEMORY_CHANNEL = {
    "experienced": "你亲历",
    "witnessed": "你在场看到",
    "told": "你听人说起",
    "recalled": "你回忆往事",
    "reported": "你经汇报得知，只知道汇报的内容",
    "unstated": "你是否知道此事不明",
}
_END = re.compile(r"[。！？!?；;]+[”」』）)\]]*|\n+")
_CLOSERS = "”」』）)]…~～ \t\r\n"
_QUOTES = "”」』）)] \t\r\n"
_ASKING = ("什么", "怎么", "为什么", "谁", "哪", "几", "多少", "是不是", "要不要", "能不能", "会不会",
           "您呢", "你呢")
_NOT_ASKING_ME = ("什么", "怎么", "这么", "那么", "多么", "要么")
_LISTENER = ("您", "你")
_PUNCT = re.compile(r"[\s。！？!?，,、；;：:…—~～“”‘’「」『』（）()\"'.]")
_AI = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])")
_QUOTED = re.compile(r"[“\"「『]([^“”\"「」『』\n]{1,80})[”\"」』]")
MIN_QUOTE = 4
_EVIDENCE_ID = re.compile(r"[EAF]\d*")
STALE_NOTE = "把较早的事说成了现在的情况；改成最后知道的情况并带上当时的时间，例如“我最后知道……是在……的时候”，不要说成现在"
FAILED_NOTE = "核验没有给出有效结果，按无依据处理"
QUOTE_NOTE = "引号里的话在记忆里找不到原句；不是原话就不要加引号"
_LIST_ITEM = re.compile(r"第([一二三四五六七八九十])(个|点|条)(?=[是，,：:])")
_NUMERALS = "一二三四五六七八九十"
_DANGLING = ("其次", "再次", "另外", "此外", "同时", "因此", "所以", "于是", "随后", "之后", "接着",
             "然而", "但是", "不过", "而且")
_NOT_AFTER_DANGLING = ("的", "是", "说")

REVIEW_TEMPLATE = (
    "你是剧情事实核验器，逐句检查{name}的候选回复。可用的依据只有下面的[资料]、[人设档案]和[对话者本次说过的话]；"
    "模型自带的{world}知识、人格设定里的其他描述、候选回复本身都不是依据。"
    "[资料]的记忆标签和“当时的你”里的我指{name}；原文对话里的你取决于说话对象，原文旁白里的你通常指{player}，必须按上下文区分；"
    "资料里的{player}是否就是当前对话者，以[对话者]一段为准。"
    "编号以 A 开头的是{home}档案原文，可以作为 plot 和 profile 的依据，但{name}只能说成档案上的记载，说成亲身经历算 contradicted。\n"
    "每句先定类型：plot＝关于原作人物、组织、地点、事件、经历或近况的具体说法；"
    "profile＝{name}自己的档案信息（生日、身高、种族、职位等）；"
    "shared＝关于当前对话者与{name}之间过去某件具体的事；"
    "opinion＝{name}对人物或组织的看法、评价和感受（如“她很坚定”“他是个很复杂的人”），不附带具体事件、动作、原话或数字；"
    "chat＝寒暄、关心、情绪、鼓励。现在（今天、最近）{home}上的日常见闻和人物的日常状态（在忙、还好、老样子、刚看见谁在做什么）"
    "不属于原作，也是 chat，不需要资料依据；但不能与资料里的原作事实矛盾，不能宣布伤亡、下落、身份或阵营的变化，这些才是 plot。\n"
    "表示不知道、没有消息、记不清、说不准的话本身不需要依据；同一句里其余的具体事实照常核对。\n"
    "判定用 status 三选一：supported＝有依据；contradicted＝与[资料]里的内容冲突，evidence 写与之冲突的资料编号；"
    "uncovered＝[资料]里找不到依据，但也没有与之冲突的内容。"
    "chat 和 opinion 一律 supported；一句评价只要夹带了具体事件、动作、原话或数字，就按 plot 核对。"
    "plot 只有[资料]明确支持才 supported，并在 evidence 写资料编号（如 E1）；"
    "改变资料原意（例如资料说城门已经关上，回复说城门快要关上），把过去说成现在，把听说或不知情说成亲历，都算 contradicted；"
    "添加资料里没有的动作、神情、情绪、数字、地点、时间或原因，算 uncovered。"
    "profile 在[人设档案]或[资料]里{name}自己的档案中有记载才 supported，依据来自[资料]时在 evidence 写编号。"
    "shared 在[资料]里有记载（当前对话者就是资料里的{player}时）"
    "或[对话者本次说过的话]里提到过才 supported，依据来自[资料]时在 evidence 写编号。\n"
    "[本次对话记录]的 C 编号只证明谁在本次聊天说过什么，不证明那些世界事实为真。"
    "conversation＝回顾本次聊天或解释自己的上一句回答，引用对应 C 编号；即使提到剧情人物或地名，也不自动变成 plot。"
    "inference＝明确表示推测的判断，必须引用知情资料中的已知前提，不能把猜测当既定计划。"
    "不知情资料中的内容不能用可能、不确定是否、记不清是否包装后透露；应判 contradicted。"
    "标为亲历或在场目睹的事件，其原文明示的外部动作可用第一人称回顾，不要求原文再写我记得、我看到。"
    "这不授予其他角色的内心活动，也不改变具体动作的主体；听说不能改成亲历。"
    "一句话可以由多条资料共同支持，先检查相关资料的组合，不要求单条资料包含整句；仍不能凭相邻或排列顺序补造因果。"
    "正常概括和同义表达不要求逐字一致，但不能改变主体、知情渠道、时间或增加心理活动。"
    "记忆按相关度排列，不代表先后；检查句间后来、再后来、因此所断言的先后或因果，必须有原文依据，不能混合回忆和现实。"
    "对{player}平时习惯的断言是 shared，需要依据；普通寒暄与此刻的主观感受才是 chat。"
    "向对方询问感受或意图（例如你是在担心吗）是 chat，不是断言，不需要剧情证据；问题若预设具体经历，则核对该经历。"
    "每句另标 now：断言某个人物、组织或地点此刻（现在、最近、目前）的状态、下落、处境或关系时为 true；"
    "讲某个时候发生过的事、带时间的最后所知、表示不知道，以及{name}自己此刻的感受和日常，都是 false。"
    "now 只描述这句在说什么时候，不影响 status。\n"
    "只输出 JSON："
    '{{"sentences":[{{"i":1,"type":"plot|profile|shared|opinion|chat|conversation|inference","now":false,'
    '"status":"supported|contradicted|uncovered","evidence":["E1"],"problem":"不是 supported 时写明冲突在哪或缺了什么"}}]}}'
)
REVISE_NOTE = (
    "（校对意见，不是{player}说的话）你刚才的回复逐句编号如下：\n{listing}\n"
    "以下句子需要处理：\n{notes}\n"
    "只改写或删掉这些句子，其他句子保持原样，只有删句后前后接不上时，才可以改动它们开头的连接词；"
    "不要新增句子，也不要重复其他句子已经说过的内容。"
    "改写时只能使用[你的记忆]里有的内容，改不好就直接删掉。用陈述句结束，不要向{player}提问。只输出处理后的完整回复。"
)


def split_sentences(text: str) -> list[str]:
    pieces: list[str] = []
    start = 0
    for match in _END.finditer(text):
        piece = text[start:match.end()]
        start = match.end()
        if piece.strip():
            pieces.append(piece)
        elif pieces:
            pieces[-1] += piece
    tail = text[start:]
    if tail.strip():
        pieces.append(tail)
    elif pieces:
        pieces[-1] += tail
    return pieces


def _is_question(piece: str, player: str) -> bool:
    """A question mark, or a question particle before a full stop; a trailing self-musing stays."""
    text = piece.strip()
    body = text.rstrip(_CLOSERS)
    if body.endswith(("？", "?")):
        return True
    if text.rstrip(_QUOTES).endswith("…") and not any(word in text for word in (*_LISTENER, player)):
        return False
    core = body.rstrip("。.！!")
    if core.endswith("吗") or (core.endswith("么") and not core.endswith(_NOT_ASKING_ME)):
        return True
    return core.endswith("呢") and any(word in core for word in _ASKING)


def _norm(piece: str) -> str:
    return _PUNCT.sub("", piece)


def _is_meta(piece: str, terms: tuple[str, ...], profile: CharacterProfile) -> bool:
    return (any(term in piece for term in (*terms, profile.world)) or _AI.search(piece) is not None
            or _game(profile.game_pattern).search(piece) is not None)


@lru_cache(maxsize=8)
def _game(pattern: str) -> re.Pattern:
    return re.compile(pattern)


def _removals(pieces: list[str], terms: tuple[str, ...], *, allow_questions: bool = False,
              profile: CharacterProfile = AMIYA) -> dict[int, str]:
    removed = {i: "meta" for i, piece in enumerate(pieces, 1) if _is_meta(piece, terms, profile)}
    if allow_questions:
        return removed
    for i in range(len(pieces), 0, -1):
        if i in removed:
            continue
        if not _is_question(pieces[i - 1], profile.player):
            break
        removed[i] = "question"
    return removed


def tidy(text: str, extra_terms: Iterable[str] = (),
         *, allow_questions: bool = False, profile: CharacterProfile = AMIYA) -> tuple[str, int, int]:
    """Drop out-of-character sentences and optionally terminal questions."""
    pieces = split_sentences(text.strip())
    removed = _removals(pieces, (*META_TERMS, *extra_terms), allow_questions=allow_questions, profile=profile)
    kept = "".join(piece for i, piece in enumerate(pieces, 1) if i not in removed).strip()
    kinds = list(removed.values())
    return kept, kinds.count("question"), kinds.count("meta")


def unsupported_quote(sentence: str, haystack: str) -> bool:
    """Quoted wording must exist verbatim in the sources; a paraphrase may not wear quotation marks."""
    return any(len(body := _norm(m.group(1))) >= MIN_QUOTE and body not in haystack
               for m in _QUOTED.finditer(sentence))


@dataclass(frozen=True)
class Scan:
    entities: tuple[str, ...]
    past: bool

    @property
    def canon(self) -> bool:
        return bool(self.entities) or self.past


def scan(sentence: str, find_entities: Callable[[str], list[str]]) -> Scan:
    return Scan(tuple(find_entities(sentence)), any(term in sentence for term in PAST_MARKERS))


@dataclass(frozen=True)
class Memory:
    eid: str
    event_id: str
    source: str
    channel: str
    summary: str
    lines: tuple[tuple[str, str], ...]
    note: str = ""


class EvidencePack:
    """One evidence set, rendered identically for the generator, the tool result and the reviewer."""

    def __init__(self, doctor_label: str | None = None, doctor_present: bool = True,
                 profile: CharacterProfile = AMIYA) -> None:
        self.items: list[Memory] = []
        self.profile = profile
        self.doctor_label = profile.player if doctor_label is None else doctor_label
        self.doctor_present = doctor_present
        self.channels = {**MEMORY_CHANNEL, "archive": f"{profile.home}档案记载，不是你亲历的事",
                         "timeline": "时间轴，只列你知道的事"}
        self.when: Callable[[str], str] | None = None
        self.recent: Callable[[str], bool] | None = None

    def __contains__(self, event_id: str) -> bool:
        return any(item.event_id == event_id for item in self.items)

    @property
    def ids(self) -> set[str]:
        return {item.eid for item in self.items}

    def add(self, event_id: str, source: str, channel: str, summary: str,
            lines: tuple[tuple[str, str], ...], note: str = "", prefix: str = "E") -> Memory:
        number = sum(1 for item in self.items if item.eid.startswith(prefix)) + 1
        item = Memory(f"{prefix}{number}", event_id, source, channel, summary, lines, note)
        self.items.append(item)
        return item

    def pop(self) -> Memory:
        return self.items.pop()

    def render(self, items: Iterable[Memory] | None = None) -> str:
        label = self.doctor_label
        out = []
        for item in self.items if items is None else items:
            when = self.when(item.event_id) if self.when else ""
            out.append(f"〔{item.eid}〕（{when + '·' if when else ''}{self.channels.get(item.channel, self.channels['unstated'])}）"
                       f"{item.summary.replace(self.profile.player_placeholder, label)}")
            for speaker, body in item.lines:
                shown = label if self.doctor_present and speaker.startswith(self.profile.player) else speaker
                out.append(f"  「{shown}：{body}」")
            if item.note:
                out.append(f"  当时的你：{item.note.replace(self.profile.player_placeholder, label)}")
        return "\n".join(out)

    def mentions(self, name: str) -> bool:
        return bool(_norm(name)) and _norm(name) in _norm(self.render())

    def fresh_ids(self) -> set[str]:
        return {item.eid for item in self.items if self.recent and self.recent(item.event_id)}


@dataclass(frozen=True)
class Verdict:
    index: int
    kind: str
    status: str
    evidence: tuple[str, ...]
    problem: str
    now: bool = False

    @property
    def supported(self) -> bool:
        return self.status == "supported"


def parse_review(raw: str, count: int, evidence_ids: set[str],
                 conversation_ids: set[str] | None = None) -> list[Verdict] | None:
    """A conflict must name the evidence it conflicts with; otherwise it is only a gap in this turn's evidence.

    A row that still carries the older boolean `supported` is read as supported or uncovered.
    """
    body = re.sub(r"^\x60\x60\x60(?:json)?\s*|\s*\x60\x60\x60$", "", raw.strip(), flags=re.I)
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(body[start:end + 1])
    except ValueError:
        return None
    rows = obj.get("sentences") if isinstance(obj, dict) else None
    if not isinstance(rows, list):
        return None
    verdicts: dict[int, Verdict] = {}
    for row in rows:
        if not isinstance(row, dict):
            return None
        index, kind, status = row.get("i"), row.get("type"), row.get("status")
        if status is None and isinstance(row.get("supported"), bool):
            status = "supported" if row["supported"] else "uncovered"
        evidence = row.get("evidence") or []
        if (type(index) is not int or index in verdicts or not 1 <= index <= count or kind not in CLAIM_TYPES
                or status not in STATUSES or not isinstance(evidence, list)):
            return None
        cited = tuple(str(x) for x in evidence)
        ids = {c for c in cited if _EVIDENCE_ID.fullmatch(c)}
        problem = str(row.get("problem") or "")
        if kind in FREE_TYPES:
            status = "supported"
        elif status == "contradicted":
            if not ids & evidence_ids:
                status = "uncovered"
        elif kind == "conversation":
            if status == "supported" and (not cited or not set(cited) <= (conversation_ids or set())):
                status, problem = "uncovered", problem or "没有引用本次对话记录"
        elif kind in ("plot", "inference") and status == "supported" and (
                not ids or not ids <= evidence_ids or any(c.startswith("C") for c in cited)):
            status, problem = "uncovered", problem or "没有引用有效的记忆编号"
        elif kind in ("shared", "profile") and status == "supported" and not ids <= evidence_ids:
            status, problem = "uncovered", problem or "没有引用有效的记忆编号"
        verdicts[index] = Verdict(index, kind, status, cited, problem, row.get("now") is True)
    if len(verdicts) != count:
        return None
    return [verdicts[i] for i in range(1, count + 1)]


def review_system(profile: CharacterProfile) -> str:
    return REVIEW_TEMPLATE.format(name=profile.name, player=profile.player, world=profile.world, home=profile.home)


def review(complete: Complete, sentences: list[str], *, sources: str,
           evidence_ids: set[str], conversation_ids: set[str] | None = None,
           profile: CharacterProfile = AMIYA) -> list[Verdict] | None:
    payload = {"sentences": [{"i": i, "text": s.strip()} for i, s in enumerate(sentences, 1)]}
    raw = complete([
        {"role": "system", "content": review_system(profile) + "\n\n" + sources},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ], 0.0)
    return parse_review(raw, len(sentences), evidence_ids, conversation_ids)


def revise(complete: Complete, messages: list[dict], sentences: list[str],
           problems: dict[int, str], temperature: float, *, coherent: bool = False,
           allow_questions: bool = False, profile: CharacterProfile = AMIYA, long_answer: bool = False) -> str:
    listing = "\n".join(f"{i}. {s.strip()}" for i, s in enumerate(sentences, 1))
    notes = "\n".join(f"第 {i} 句：{reason}" for i, reason in sorted(problems.items()))
    note = REVISE_NOTE.format(listing=listing, notes=notes, player=profile.player)
    if coherent:
        note = (f"（校对意见，不是{profile.player}说的话）候选回复：\n{listing}\n问题：\n{notes}\n"
                f"围绕{profile.player}这一轮的问题，用已核实的内容重新组织一个连贯的回答。保留重要观点，"
                "不要逐项汇报材料，也不要因为删了事实就只剩空话。仅用已有记忆与本次对话记录；"
                "可以表达此刻感受，不能添加新经历。优先保留已经核实的核心冲突和直接回答；若只有人称或时态等局部错误，修正该处，不要舍弃同句里已有依据的冲突对象和行动。先回应核心要点，"
                + ("再用一段话讲清主要经过，" if long_answer else "再用一两件必要的事说明，通常两到四句，")
                + "不要逐项复述记忆。不知情的具体内容直接省去，不能改成不确定是否来透露。"
                + ("必要时可以自然追问，但先回答。" if allow_questions else "用陈述句结束。")
                + "只输出修订后的回复。")
    return complete([
        *messages,
        {"role": "assistant", "content": "".join(sentences).strip()},
        {"role": "user", "content": note},
    ], temperature)


@dataclass
class CheckReport:
    questions_removed: int = 0
    meta_removed: int = 0
    refetched: tuple[str, ...] = ()
    reviewed: bool = False
    rechecked: bool = False
    review_failed: bool = False
    sentences: tuple[str, ...] = ()
    problems: dict[int, str] = field(default_factory=dict)
    issues: dict[int, str] = field(default_factory=dict)
    revised: bool = False
    rewrote: int = 0
    dropped: int = 0
    calls: int = 0
    review_retries: int = 0
    looked_up: int = 0
    found: int = 0
    second_pass: bool = False
    mended: int = 0
    stages: list[dict] = field(default_factory=list)


REWRITE_REASON = {
    "question": "这句是向对方的提问；请改成陈述句直接回答，不要提问",
    "meta": "这句出戏（提到游戏设定、原作之类）；请去掉，或改成角色自己会说的话",
}


def repair_note(verdict: Verdict | None, reason: str, evidence_ids: set[str], found: bool = False) -> str:
    """A conflict is corrected from the evidence it names; a gap costs only the unsupported detail, never a hedge."""
    if verdict is None or verdict.supported:
        return reason
    if verdict.status == "contradicted":
        cited = "、".join(c for c in verdict.evidence if c in evidence_ids)
        return f"{reason}" + (f"（与{cited}冲突）" if cited else "") + "；按记忆里的说法改正"
    if found:
        return f"{reason}；[你的记忆]里补上了相关片段，能支持原意就按记忆保留，不能支持就只删去没有依据的那一处"
    return f"{reason}；只删去没有依据的那一处，同句其余有依据的内容保留，整句都没有依据才删掉这句"


def mend(sequence: list[tuple[str, bool]]) -> tuple[str, int]:
    """Join the kept sentences so a dropped one leaves no dangling list number or leading connective."""
    units = {match.group(2) for piece, dropped in sequence
             if dropped and (match := _LIST_ITEM.match(piece.lstrip()))}
    counters = dict.fromkeys(units, 0)
    out: list[str] = []
    changes = 0
    after_drop = False
    for piece, dropped in sequence:
        if dropped:
            after_drop = True
            continue
        body = piece.lstrip()
        lead = piece[:len(piece) - len(body)]
        match = _LIST_ITEM.match(body)
        if match and match.group(2) in counters:
            unit = match.group(2)
            counters[unit] += 1
            renumbered = f"第{_NUMERALS[counters[unit] - 1]}{unit}" + body[match.end():]
            changes += renumbered != body
            body = renumbered
        elif after_drop:
            word = next((word for word in _DANGLING if body.startswith(word)), "")
            rest = body[len(word):].lstrip("，,、 ")
            if word and rest and not rest.startswith(_NOT_AFTER_DANGLING):
                body = rest
                changes += 1
        out.append(lead + body)
        after_drop = False
    return "".join(out).strip(), changes


def _tidy_into(report: CheckReport, text: str, extra_terms: tuple[str, ...],
               *, allow_questions: bool = False, profile: CharacterProfile = AMIYA) -> str:
    cleaned, questions, meta = tidy(text, extra_terms, allow_questions=allow_questions, profile=profile)
    report.questions_removed += questions
    report.meta_removed += meta
    return cleaned


def _rows(verdicts: list[Verdict] | None) -> list[dict] | None:
    return None if verdicts is None else [{**asdict(v), "evidence": list(v.evidence)} for v in verdicts]


def check_reply(
    draft: str, *,
    complete: Complete,
    messages: Callable[[], list[dict]],
    pack: EvidencePack,
    find_entities: Callable[[str], list[str]],
    refetch: Callable[[list[str]], int],
    sources: Callable[[], str],
    extra_ids: set[str] | None = None,
    force_review: bool,
    temperature: float,
    extra_terms: tuple[str, ...] = (),
    allow_questions: bool = False,
    fallback: str,
    coherent_revision: bool = False,
    long_answer: bool = False,
    retry_review: bool = False,
    conversation_ids: set[str] | None = None,
    profile: CharacterProfile = AMIYA,
    lookup: Callable[[str], object] | None = None,
) -> tuple[str, CheckReport]:
    """Review plot claims, look up uncovered ones, revise by the kind of problem and recheck what changed.

    A plot claim about how things are now stands only on evidence dated in the current stretch of the story;
    the review decides whether a sentence speaks of the present, and the evidence dates decide whether it may.
    A revised sentence that still fails gets one targeted second revision before it may be dropped, and a
    dropped sentence never leaves a dangling list number or connective behind.
    """
    report = CheckReport()

    def log(stage: str, **data) -> None:
        report.stages.append({"stage": stage, **data})

    def tidied(value: str) -> str:
        return _tidy_into(report, value, extra_terms, allow_questions=allow_questions, profile=profile)

    def mended(sequence: list[tuple[str, bool]]) -> str:
        value, changes = mend(sequence)
        report.mended += changes
        return value

    def evidence_ids() -> set[str]:
        return pack.ids | (extra_ids or set())

    def stale(verdict: Verdict | None) -> bool:
        return (verdict is not None and verdict.now and verdict.kind == "plot"
                and not set(verdict.evidence) & pack.fresh_ids())

    pieces = split_sentences(draft.strip())
    removed = _removals(pieces, (*META_TERMS, *extra_terms), allow_questions=allow_questions, profile=profile)
    text = "".join(piece for i, piece in enumerate(pieces, 1) if i not in removed).strip()
    if removed and len(_norm(text)) * 2 < len(_norm(draft)):
        notes = {i: REWRITE_REASON[kind] for i, kind in removed.items()}
        text = tidied(revise(complete, messages(), pieces, notes, temperature, profile=profile))
        report.calls += 1
        report.revised = True
        report.rewrote = len(removed)
        log("rewrite", notes=notes, text=text)
    else:
        kinds = list(removed.values())
        report.questions_removed += kinds.count("question")
        report.meta_removed += kinds.count("meta")
    if not text:
        return fallback, report
    sentences = split_sentences(text)
    scans = [scan(s, find_entities) for s in sentences]
    if not force_review and not any(s.canon for s in scans):
        return text, report
    missing = list(dict.fromkeys(n for s in scans for n in s.entities if not pack.mentions(n)))
    if missing and refetch(missing):
        report.refetched = tuple(missing)
    source_text = sources()
    haystack = _norm(source_text)

    def checked_review(pieces: list[str]) -> list[Verdict] | None:
        result = review(complete, pieces, sources=source_text,
                        evidence_ids=evidence_ids(), conversation_ids=conversation_ids, profile=profile)
        report.calls += 1
        if result is None and retry_review and report.review_retries == 0:
            report.review_retries += 1
            result = review(complete, pieces, sources=source_text,
                            evidence_ids=evidence_ids(), conversation_ids=conversation_ids, profile=profile)
            report.calls += 1
        return result

    def settle(originals: list[str], problems: dict[int, str], revised: str, *, every_fresh: bool,
               reopened: set[int] = frozenset()) -> str:
        again = {_norm(originals[i - 1]) for i in reopened}
        rejected = {_norm(originals[i - 1]) for i in problems if i not in reopened}
        known = {_norm(s) for s in originals}
        rewrites = len(problems)
        seen: set[str] = set()
        sequence: list[tuple[str, bool]] = []
        for piece in split_sentences(revised)[:max(4, len(originals) + 2) if every_fresh else None]:
            key = _norm(piece)
            fresh = key not in known
            if (key in rejected or key in seen or (fresh and rewrites <= 0 and not every_fresh)
                    or any(not pack.mentions(n) for n in scan(piece, find_entities).entities)
                    or unsupported_quote(piece, haystack)):
                report.dropped += 1
                sequence.append((piece, True))
                continue
            rewrites -= fresh
            seen.add(key)
            sequence.append((piece, False))
        pending = [position for position, (piece, dropped) in enumerate(sequence)
                   if not dropped and ((key := _norm(piece)) in again
                                       or key not in known and (every_fresh or scan(piece, find_entities).canon))]
        if pending:
            checked = checked_review([sequence[position][0] for position in pending])
            report.rechecked = True
            log("recheck_changed", sentences=[sequence[position][0].strip() for position in pending],
                verdicts=_rows(checked))
            for rank, position in enumerate(pending):
                verdict = checked[rank] if checked else None
                if verdict is None or not verdict.supported or stale(verdict):
                    sequence[position] = (sequence[position][0], True)
                    report.dropped += 1
        return tidied(mended(sequence))

    verdicts = checked_review(sentences)
    report.reviewed = True
    log("review", sentences=[s.strip() for s in sentences], verdicts=_rows(verdicts))
    issues: dict[int, Verdict] = {}
    if verdicts is None:
        report.review_failed = True
        problems = {i: FAILED_NOTE for i, s in enumerate(scans, 1) if s.canon}
    else:
        problems = {v.index: v.problem or "没有依据" for v in verdicts if not v.supported}
        issues = {v.index: v for v in verdicts if not v.supported}
    for verdict in verdicts or ():
        if stale(verdict):
            problems.setdefault(verdict.index, STALE_NOTE)
    for i, sentence in enumerate(sentences, 1):
        if unsupported_quote(sentence, haystack):
            problems.setdefault(i, QUOTE_NOTE)
    report.sentences = tuple(sentences)
    report.problems = problems
    report.issues = {i: v.status for i, v in issues.items()}
    if not problems:
        return text, report
    kept = [(s, i in problems) for i, s in enumerate(sentences, 1)]

    def cut() -> str:
        return tidied(mended(kept)) or fallback

    if report.revised:
        return cut(), report
    found: set[int] = set()
    claims = [v.index for v in issues.values() if v.status == "uncovered" and v.kind in CLAIM_KINDS]
    if lookup is not None and claims:
        rows = []
        for i in claims[:CLAIM_LOOKUPS]:
            before = pack.ids
            lookup(sentences[i - 1].strip())
            added = sorted(pack.ids - before)
            if added:
                found.add(i)
            rows.append({"i": i, "added": added})
        report.looked_up, report.found = len(rows), len(found)
        log("lookup", claims=rows)
        if found:
            source_text = sources()
            haystack = _norm(source_text)
    notes = {i: repair_note(issues.get(i), reason, evidence_ids(), i in found) for i, reason in problems.items()}
    revised = tidied(revise(complete, messages(), sentences, notes, temperature,
                            coherent=coherent_revision, allow_questions=allow_questions, profile=profile,
                            long_answer=long_answer))
    report.calls += 1
    report.revised = True
    log("revise", coherent=coherent_revision, notes=notes, text=revised)
    if not coherent_revision:
        return settle(sentences, notes, revised, every_fresh=False, reopened=found) or cut(), report
    sequence: list[tuple[str, bool]] = []
    seen: set[str] = set()
    for piece in split_sentences(revised)[:max(4, len(sentences) + 2)]:
        key = _norm(piece)
        sequence.append((piece, key in seen))
        report.dropped += key in seen
        seen.add(key)
    pieces = [piece for piece, dropped in sequence if not dropped]
    if not pieces:
        return cut(), report
    checked = checked_review(pieces)
    report.rechecked = True
    log("recheck", sentences=[piece.strip() for piece in pieces], verdicts=_rows(checked))
    if checked is None:
        report.dropped += len(pieces)
        return cut(), report
    failing: dict[int, str] = {}
    for index, (piece, verdict) in enumerate(zip(pieces, checked), 1):
        if not verdict.supported:
            failing[index] = repair_note(verdict, verdict.problem or "没有依据", evidence_ids())
        elif stale(verdict):
            failing[index] = STALE_NOTE
        elif unsupported_quote(piece, haystack):
            failing[index] = QUOTE_NOTE
    if not failing:
        return tidied(mended(sequence)) or cut(), report
    second = tidied(revise(complete, messages(), pieces, failing, temperature,
                           allow_questions=allow_questions, profile=profile))
    report.calls += 1
    report.second_pass = True
    log("second_revise", notes=failing, text=second)
    passed = [(piece, index in failing) for index, piece in enumerate(pieces, 1)]
    return (settle(pieces, failing, second, every_fresh=True) or tidied(mended(passed)) or cut()), report
