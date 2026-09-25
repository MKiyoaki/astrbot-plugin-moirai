"""Evidence-scoped canon reply checks: deterministic cleanup first, model review only where plot content appears."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable

Complete = Callable[[list[dict], float], str]

PAST_MARKERS = ("那次", "那一次", "上次", "当时", "那时", "那天", "那场", "以前", "之前", "曾经", "还记得")
META_TERMS = ("原作", "剧情", "章节", "数据库", "知识库", "检索", "试跑", "语言模型", "人工智能", "明日方舟")
CLAIM_TYPES = frozenset(("plot", "profile", "shared", "opinion", "chat"))
FREE_TYPES = frozenset(("opinion", "chat"))
MEMORY_CHANNEL = {
    "experienced": "你亲历",
    "witnessed": "你在场看到",
    "told": "你听人说起",
    "recalled": "你回忆往事",
    "unstated": "你是否知道此事不明",
    "archive": "罗德岛档案记载，不是你亲历的事",
}
_END = re.compile(r"[。！？!?]+[”」』）)\]]*|\n+")
_CLOSERS = "”」』）)]…~～ \t\r\n"
_QUOTES = "”」』）)] \t\r\n"
_ASKING = ("什么", "怎么", "为什么", "谁", "哪", "几", "多少", "是不是", "要不要", "能不能", "会不会",
           "您呢", "你呢")
_NOT_ASKING_ME = ("什么", "怎么", "这么", "那么", "多么", "要么")
_LISTENER = ("您", "你", "博士")
_PUNCT = re.compile(r"[\s。！？!?，,、；;：:…—~～“”‘’「」『』（）()\"'.]")
_AI = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])")
_GAME = re.compile(
    r"[二三四五六2-6]星(?:干员|角色|先锋|近卫|重装|狙击|术师|医疗|辅助|特种|(?![一-鿿A-Za-z]))"
    r"|几星|星级|技能专精|专精[一二三1-3]|精英化|抽卡|卡池|第[一二三四五六七八九十百零〇0-9]+章"
)
_QUOTED = re.compile(r"[“\"「『]([^“”\"「」『』\n]{1,80})[”\"」』]")
MIN_QUOTE = 4
_EVIDENCE_ID = re.compile(r"[EAF]\d*")
_NOW = ("现在", "目前", "如今", "最近", "这几天")
_HEDGES = (
    "无法确认", "不确定", "不太确定", "不知道", "不能确认", "没有证据", "不清楚", "不太清楚",
    "记不清", "说不清", "说不准", "没有消息", "没有可靠的消息", "不了解",
)

REVIEW_SYSTEM = (
    "你是剧情事实核验器，逐句检查阿米娅的候选回复。可用的依据只有下面的[资料]、[人设档案]和[对话者本次说过的话]；"
    "模型自带的明日方舟知识、人格设定里的其他描述、候选回复本身都不是依据。"
    "[资料]是写给阿米娅本人看的记忆：其中的“你”，以及“当时的你”一段里的“我”，都指阿米娅；"
    "资料里的博士是否就是当前对话者，以[对话者]一段为准。"
    "编号以 A 开头的是罗德岛档案原文，可以作为 plot 和 profile 的依据，但阿米娅只能说成档案上的记载，说成亲身经历算 false。\n"
    "每句先定类型：plot＝关于原作人物、组织、地点、事件、经历或近况的具体说法；"
    "profile＝阿米娅自己的档案信息（生日、身高、种族、职位等）；"
    "shared＝关于当前对话者与阿米娅之间过去某件具体的事；"
    "opinion＝阿米娅对人物或组织的看法、评价和感受（如“她很坚定”“他是个很复杂的人”），不附带具体事件、动作、原话或数字；"
    "chat＝寒暄、关心、情绪、鼓励。\n"
    "表示不知道、没有消息、记不清、说不准的话本身不需要依据；同一句里其余的具体事实照常核对。\n"
    "判定：chat 和 opinion 一律 supported=true；一句评价只要夹带了具体事件、动作、原话或数字，就按 plot 核对。"
    "plot 只有[资料]明确支持才 true，并在 evidence 写资料编号（如 E1）；"
    "添加资料里没有的动作、神情、情绪、数字或原因，改变资料原意，把过去说成现在，把听说或不知情说成亲历，都算 false。"
    "profile 在[人设档案]或[资料]里阿米娅自己的档案中有记载才 true，依据来自[资料]时在 evidence 写编号。shared 在[资料]里有记载（当前对话者就是资料里的博士时）"
    "或[对话者本次说过的话]里提到过才 true，依据来自[资料]时在 evidence 写编号。\n"
    "只输出 JSON："
    '{"sentences":[{"i":1,"type":"plot|profile|shared|opinion|chat","supported":true,"evidence":["E1"],'
    '"problem":"不成立时写明缺了什么"}]}'
)
REVISE_NOTE = (
    "（校对意见，不是博士说的话）你刚才的回复逐句编号如下：\n{listing}\n"
    "以下句子需要处理：\n{notes}\n"
    "只改写或删掉这些句子，其他句子保持原样，只有删句后前后接不上时，才可以改动它们开头的连接词；"
    "不要新增句子，也不要重复其他句子已经说过的内容。"
    "改写时只能使用[你的记忆]里有的内容，改不好就直接删掉。用陈述句结束，不要向博士提问。只输出处理后的完整回复。"
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


def _is_question(piece: str) -> bool:
    """A question mark, or a question particle before a full stop; a trailing self-musing stays."""
    text = piece.strip()
    body = text.rstrip(_CLOSERS)
    if body.endswith(("？", "?")):
        return True
    if text.rstrip(_QUOTES).endswith("…") and not any(word in text for word in _LISTENER):
        return False
    core = body.rstrip("。.！!")
    if core.endswith("吗") or (core.endswith("么") and not core.endswith(_NOT_ASKING_ME)):
        return True
    return core.endswith("呢") and any(word in core for word in _ASKING)


def _norm(piece: str) -> str:
    return _PUNCT.sub("", piece)


def _is_meta(piece: str, terms: tuple[str, ...]) -> bool:
    return (any(term in piece for term in terms) or _AI.search(piece) is not None
            or _GAME.search(piece) is not None)


def _removals(pieces: list[str], terms: tuple[str, ...]) -> dict[int, str]:
    removed = {i: "meta" for i, piece in enumerate(pieces, 1) if _is_meta(piece, terms)}
    for i in range(len(pieces), 0, -1):
        if i in removed:
            continue
        if not _is_question(pieces[i - 1]):
            break
        removed[i] = "question"
    return removed


def tidy(text: str, extra_terms: Iterable[str] = ()) -> tuple[str, int, int]:
    """Drop out-of-character sentences, then every question at the end of the reply."""
    pieces = split_sentences(text.strip())
    removed = _removals(pieces, (*META_TERMS, *extra_terms))
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
    current: bool

    @property
    def canon(self) -> bool:
        return bool(self.entities) or self.past or self.current


def scan(sentence: str, find_entities: Callable[[str], list[str]]) -> Scan:
    entities = tuple(find_entities(sentence))
    third_party = bool(entities) or "她" in sentence or "他" in sentence
    current = (third_party and any(term in sentence for term in _NOW)
               and not any(term in sentence for term in _HEDGES))
    return Scan(entities, any(term in sentence for term in PAST_MARKERS), current)


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

    def __init__(self, doctor_label: str = "博士", doctor_present: bool = True) -> None:
        self.items: list[Memory] = []
        self.doctor_label = doctor_label
        self.doctor_present = doctor_present

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
            out.append(f"〔{item.eid}〕（{MEMORY_CHANNEL.get(item.channel, MEMORY_CHANNEL['unstated'])}）"
                       f"{item.summary.replace('{DOCTOR}', label)}")
            for speaker, body in item.lines:
                shown = label if self.doctor_present and speaker.startswith("博士") else speaker
                out.append(f"  「{shown}：{body}」")
            if item.note:
                out.append(f"  当时的你：{item.note.replace('{DOCTOR}', label)}")
        return "\n".join(out)

    def mentions(self, name: str) -> bool:
        return name in self.render()


@dataclass(frozen=True)
class Verdict:
    index: int
    kind: str
    supported: bool
    evidence: tuple[str, ...]
    problem: str


def parse_review(raw: str, count: int, evidence_ids: set[str]) -> list[Verdict] | None:
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
        index, kind, supported = row.get("i"), row.get("type"), row.get("supported")
        evidence = row.get("evidence") or []
        if (not isinstance(index, int) or not 1 <= index <= count or kind not in CLAIM_TYPES
                or not isinstance(supported, bool) or not isinstance(evidence, list)):
            return None
        cited = tuple(str(x) for x in evidence)
        ids = {c for c in cited if _EVIDENCE_ID.fullmatch(c)}
        problem = str(row.get("problem") or "")
        if kind in FREE_TYPES:
            supported = True
        elif kind == "plot" and supported and (not ids or not ids <= evidence_ids):
            supported, problem = False, problem or "没有引用有效的记忆编号"
        elif kind in ("shared", "profile") and supported and not ids <= evidence_ids:
            supported, problem = False, problem or "没有引用有效的记忆编号"
        verdicts[index] = Verdict(index, kind, supported, cited, problem)
    if len(verdicts) != count:
        return None
    return [verdicts[i] for i in range(1, count + 1)]


def review(complete: Complete, sentences: list[str], *, sources: str,
           evidence_ids: set[str]) -> list[Verdict] | None:
    payload = {"sentences": [{"i": i, "text": s.strip()} for i, s in enumerate(sentences, 1)]}
    raw = complete([
        {"role": "system", "content": REVIEW_SYSTEM + "\n\n" + sources},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ], 0.0)
    return parse_review(raw, len(sentences), evidence_ids)


def revise(complete: Complete, messages: list[dict], sentences: list[str],
           problems: dict[int, str], temperature: float) -> str:
    listing = "\n".join(f"{i}. {s.strip()}" for i, s in enumerate(sentences, 1))
    notes = "\n".join(f"第 {i} 句：{reason}" for i, reason in sorted(problems.items()))
    return complete([
        *messages,
        {"role": "assistant", "content": "".join(sentences).strip()},
        {"role": "user", "content": REVISE_NOTE.format(listing=listing, notes=notes)},
    ], temperature)


@dataclass
class CheckReport:
    questions_removed: int = 0
    meta_removed: int = 0
    refetched: tuple[str, ...] = ()
    reviewed: bool = False
    review_failed: bool = False
    sentences: tuple[str, ...] = ()
    problems: dict[int, str] = field(default_factory=dict)
    revised: bool = False
    rewrote: int = 0
    dropped: int = 0
    calls: int = 0


REWRITE_REASON = {
    "question": "这句是向对方的提问；请改成陈述句直接回答，不要提问",
    "meta": "这句出戏（提到游戏设定、原作之类）；请去掉，或改成角色自己会说的话",
}


def _tidy_into(report: CheckReport, text: str, extra_terms: tuple[str, ...]) -> str:
    cleaned, questions, meta = tidy(text, extra_terms)
    report.questions_removed += questions
    report.meta_removed += meta
    return cleaned


def check_reply(
    draft: str, *,
    complete: Complete,
    messages: Callable[[], list[dict]],
    pack: EvidencePack,
    find_entities: Callable[[str], list[str]],
    refetch: Callable[[list[str]], int],
    sources: Callable[[], str],
    extra_ids: set[str] | None = None,
    current_ok: bool,
    force_review: bool,
    temperature: float,
    extra_terms: tuple[str, ...] = (),
    fallback: str,
) -> tuple[str, CheckReport]:
    """Clean, review plot-bearing replies and revise only the flagged sentences; at most two calls.

    Deleting a question or an out-of-character sentence is free, but when that would remove most
    of the reply the sentences are rewritten once instead, so the answer itself is not lost.
    """
    report = CheckReport()
    pieces = split_sentences(draft.strip())
    removed = _removals(pieces, (*META_TERMS, *extra_terms))
    text = "".join(piece for i, piece in enumerate(pieces, 1) if i not in removed).strip()
    if removed and len(_norm(text)) * 2 < len(_norm(draft)):
        notes = {i: REWRITE_REASON[kind] for i, kind in removed.items()}
        text = _tidy_into(report, revise(complete, messages(), pieces, notes, temperature), extra_terms)
        report.calls += 1
        report.revised = True
        report.rewrote = len(removed)
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
    verdicts = review(complete, sentences, sources=source_text,
                      evidence_ids=pack.ids | (extra_ids or set()))
    report.calls += 1
    report.reviewed = True
    if verdicts is None:
        report.review_failed = True
        problems = {i: "核验没有给出有效结果，按无依据处理" for i, s in enumerate(scans, 1) if s.canon}
    else:
        problems = {v.index: v.problem or "没有依据" for v in verdicts if not v.supported}
    if not current_ok:
        for i, s in enumerate(scans, 1):
            if s.current:
                problems.setdefault(i, "没有可确认的近况，却说了别人现在的状态")
    for i, sentence in enumerate(sentences, 1):
        if unsupported_quote(sentence, haystack):
            problems.setdefault(i, "引号里的话在记忆里找不到原句；不是原话就不要加引号")
    report.sentences = tuple(sentences)
    report.problems = problems
    if not problems:
        return text, report
    kept = "".join(s for i, s in enumerate(sentences, 1) if i not in problems)
    if report.revised:
        return _tidy_into(report, kept, extra_terms) or fallback, report
    revised = _tidy_into(report, revise(complete, messages(), sentences, problems, temperature),
                         extra_terms)
    report.calls += 1
    report.revised = True
    rejected = {_norm(sentences[i - 1]) for i in problems}
    originals = {_norm(s) for s in sentences}
    rewrites = len(problems)
    seen: set[str] = set()
    final = []
    for piece in split_sentences(revised):
        key = _norm(piece)
        result = scan(piece, find_entities)
        fresh = key not in originals
        if (key in rejected or key in seen or (fresh and rewrites <= 0)
                or any(not pack.mentions(n) for n in result.entities)
                or (result.current and not current_ok) or unsupported_quote(piece, haystack)):
            report.dropped += 1
            continue
        rewrites -= fresh
        seen.add(key)
        final.append(piece)
    answer = _tidy_into(report, "".join(final), extra_terms)
    return answer or _tidy_into(report, kept, extra_terms) or fallback, report
