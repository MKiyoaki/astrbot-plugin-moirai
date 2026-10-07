"""Evidence rendering in story order and reply alignment: code only flags a claim, and one targeted repair fixes it.

The evidence is shown once, numbered in the order things happened and worded from the character's side, so a weak
model can retell it without reordering or changing viewpoint. The reply check never asks a model to judge: each
sentence is aligned to the memory it retells, closed-class words only nominate candidates (a connective, a denial, a
quantifier), and the evidence structure decides. Flagged sentences get one repair call; code never rewrites wording,
it only puts back the memory's own sentence where a repair still fails.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Iterable

from ..domain.character import DEFAULT_PROFILE, CharacterProfile
from ..read.lexical import terms
from ..constant_utils import (
    BACKWARD,
    CAUSAL,
    CIRCLED,
    CJK_DIGIT_VALUES,
    CLOSING_OFFER,
    CLOSING_OPEN,
    DENIAL,
    DIGITS,
    FORWARD,
    JUDGMENT,
    LISTENER,
    MEMORY_CHANNEL,
    META_TERMS,
    NOW_WORDS,
    NUMERALS,
    PAST_FRAME,
    QUANTITY,
    REPLY_GENERIC_CHARS,
    REPORTING,
    SENTENCE_ENDS,
    UNITS,
)
from ...utils.prompts.prompt_canon_utils import NOTES, REPAIR_NOTE
from ..settings import SETTINGS

Complete = Callable[[list[dict], float], str]

ALIGN_MIN = SETTINGS.gateway.align_min
_END = re.compile(r"[。！？!?；;]+[”」』）)\]]*|\n+")
_PUNCT = re.compile(r"[\s。！？!?，,、；;：:…—~～“”‘’「」『』（）()\"'.]")
_AI = re.compile(r"(?<![A-Za-z])AI(?![A-Za-z])")
_QUOTED = re.compile(r"[“\"「『]([^“”\"「」『』\n]{1,80})[”\"」』]")
MIN_QUOTE = SETTINGS.gateway.min_quote


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


def _norm(piece: str) -> str:
    return _PUNCT.sub("", piece)


def _is_meta(piece: str, terms_: tuple[str, ...], profile: CharacterProfile) -> bool:
    return (any(term in piece for term in (*terms_, profile.world)) or _AI.search(piece) is not None
            or _game(profile.game_pattern).search(piece) is not None)


@lru_cache(maxsize=8)
def _game(pattern: str) -> re.Pattern:
    return re.compile(pattern)


def unsupported_quote(sentence: str, haystack: str) -> bool:
    """Quoted wording must exist verbatim in the sources; a paraphrase may not wear quotation marks."""
    return any(len(body := _norm(m.group(1))) >= MIN_QUOTE and body not in haystack
               for m in _QUOTED.finditer(sentence))


def full_sentences(text: str) -> list[str]:
    """Sentences cut after each full stop, question or exclamation mark; a trailing fragment is kept last."""
    pieces, current = [], ""
    for char in text:
        current += char
        if char in SENTENCE_ENDS:
            if current.strip():
                pieces.append(current.strip())
            current = ""
    if current.strip():
        pieces.append(current.strip())
    return pieces


def numbers_with_units(sentence: str) -> list[tuple[str, str]]:
    """Each run of digits or Chinese numerals immediately followed by a measure word, as (numeral, unit)."""
    found, run, kind = [], "", ""
    for char in sentence:
        this = "d" if char in DIGITS or (char == "." and kind == "d" and run) else "c" if char in NUMERALS else ""
        if this and (not run or this == kind):
            run, kind = run + char, this
            continue
        if run and char in UNITS and not run.endswith("."):
            found.append((run, char))
        run, kind = (char, this) if this else ("", "")
    return found


def is_closing_offer(sentence: str) -> bool:
    head = sentence.lstrip("，,、 　\n")
    return head.startswith(CLOSING_OPEN) and any(word in head[:46] for word in CLOSING_OFFER)


def _arabic(numeral: str) -> str:
    if numeral.isdigit():
        return numeral
    total, section, digit = 0, 0, 0
    for char in numeral:
        if char in CJK_DIGIT_VALUES:
            digit = CJK_DIGIT_VALUES[char]
        elif char in "十百千":
            section += (digit or 1) * {"十": 10, "百": 100, "千": 1000}[char]
            digit = 0
        elif char == "万":
            total += (section + digit) * 10000
            section = digit = 0
    return str(total + section + digit)


@dataclass(frozen=True)
class Memory:
    eid: str
    event_id: str
    source: str
    channel: str
    summary: str
    lines: tuple[tuple[str, str], ...]
    note: str = ""


@dataclass(frozen=True)
class Beat:
    """One rendered memory: its label, its place in story order (None when unplaced) and its first-person text."""
    label: str
    item: Memory
    rank: int | None
    text: str


class EvidencePack:
    """One evidence set, rendered identically for the generator, the repair call and the alignment check."""

    def __init__(self, doctor_label: str | None = None, doctor_present: bool = True,
                 profile: CharacterProfile = DEFAULT_PROFILE) -> None:
        self.items: list[Memory] = []
        self.profile = profile
        self.doctor_label = profile.player if doctor_label is None else doctor_label
        self.doctor_present = doctor_present
        self.channels = {**MEMORY_CHANNEL, "archive": f"{profile.home}档案记载，不是你亲历的事",
                         "timeline": "时间轴，只列你知道的事"}
        self.when: Callable[[str], str] | None = None
        self.recent: Callable[[str], bool] | None = None
        self.sequence: Callable[[list[str]], tuple[list[str], list[str]]] | None = None
        self.links: Callable[[list[str]], set[tuple[str, str]]] | None = None

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

    def voice(self, text: str, aloud: bool = False) -> str:
        """Her own memories in her own words: her name becomes 我, the player placeholder the current label.

        A line said aloud to the Doctor addresses the Doctor as 您 rather than naming the Doctor in the third person.
        """
        label = LISTENER if aloud and self.doctor_present else self.doctor_label
        return text.replace(self.profile.player_placeholder, label).replace(self.profile.name, "我")

    def _speaker(self, speaker: str) -> str:
        if speaker == self.profile.name:
            return "我"
        return self.doctor_label if self.doctor_present and speaker.startswith(self.profile.player) else speaker

    def _block(self, label: str, item: Memory, unplaced: bool, place: str = "") -> str:
        if item.eid.startswith("A"):
            head = f"〔档案〕{self.voice(item.summary)}"
        elif item.eid.startswith("T"):
            head = f"〔时间轴〕{item.summary}"
        else:
            when = self.when(item.event_id) if self.when else ""
            tags = [part for part in (place, when, self.channels.get(item.channel, self.channels["unstated"]),
                                      "先后不明" if unplaced else "") if part]
            head = f"{label}（{'·'.join(tags)}）{self.voice(item.summary)}"
        out = [head, *(f"  「{self._speaker(speaker)}：{body}」" for speaker, body in item.lines)]
        if item.note:
            out.append(f"  当时的你：{self.voice(item.note)}")
        return "\n".join(out)

    def beats(self) -> list[Beat]:
        """Timeline first, then events in story order, then events the sequence cannot place, then archives."""
        events = [item for item in self.items if item.eid.startswith("E")]
        by_event = {item.event_id: item for item in events}
        if self.sequence and events:
            chain, rest = self.sequence(list(by_event))
            placed = set(chain) | set(rest)
            chain = [*chain, *(event for event in by_event if event not in placed)]
        else:
            chain, rest = list(by_event), []
        result = [Beat("时间轴", item, None, "") for item in self.items if item.eid.startswith("T")]
        for rank, event in enumerate(chain):
            label = CIRCLED[rank] if rank < len(CIRCLED) else f"({rank + 1})"
            result.append(Beat(label, by_event[event], rank, ""))
        result += [Beat("※", by_event[event], None, "") for event in rest]
        result += [Beat("档案", item, None, "") for item in self.items if item.eid.startswith("A")]
        return [Beat(beat.label, beat.item, beat.rank,
                     self._block(beat.label, beat.item, beat.label == "※")) for beat in result]

    def licensed(self) -> set[tuple[str, str]]:
        events = [item.event_id for item in self.items if item.eid.startswith("E")]
        return self.links(events) if self.links and len(events) > 1 else set()

    def render(self, items: Iterable[Memory] | None = None) -> str:
        chosen = None if items is None else {item.eid for item in items}
        beats = [beat for beat in self.beats() if chosen is None or beat.item.eid in chosen]
        out = [beat.text for beat in beats]
        if chosen is None:
            labels = {beat.item.event_id: beat.label for beat in beats if beat.rank is not None}
            pairs = sorted(f"{labels[a]}→{labels[b]}" for a, b in self.licensed() if a in labels and b in labels)
            if pairs:
                out.append("〔因果〕原文明说前一件促成了后一件：" + "、".join(pairs))
        return "\n".join(out)

    def labels(self) -> dict[str, str]:
        return {beat.item.eid: beat.label for beat in self.beats()}

    def render_new(self, shown: dict[str, str]) -> tuple[str, dict[str, str]]:
        """Only the memories a reader has not seen, for a conversation where the earlier render stays in view.

        A new event is labelled 新n and placed between the labels already shown; the causal line keeps only the
        pairs that involve a new event. Returns the text and the labels now shown.
        """
        beats = self.beats()
        seen = dict(shown)
        count = sum(1 for label in shown.values() if label.startswith("新"))
        placed = [beat for beat in beats if beat.rank is not None]
        out, fresh = [], set()
        for beat in beats:
            if beat.item.eid in shown:
                continue
            fresh.add(beat.item.eid)
            if not beat.item.eid.startswith("E"):
                seen[beat.item.eid] = beat.label
                out.append(beat.text)
                continue
            count += 1
            label = f"新{count}"
            seen[beat.item.eid] = label
            place = ""
            if beat.rank is not None:
                index = placed.index(beat)
                before = next((shown[b.item.eid] for b in reversed(placed[:index]) if b.item.eid in shown), "")
                after = next((shown[b.item.eid] for b in placed[index + 1:] if b.item.eid in shown), "")
                place = (f"排在{before}和{after}之间" if before and after else f"排在{before}之后" if before
                         else f"排在{after}之前" if after else "")
            out.append(self._block(label, beat.item, beat.label == "※", place))
        ranked = {beat.item.event_id: seen[beat.item.eid] for beat in placed}
        new_events = {beat.item.event_id for beat in placed if beat.item.eid in fresh}
        pairs = sorted(f"{ranked[a]}→{ranked[b]}" for a, b in self.licensed()
                       if a in ranked and b in ranked and (a in new_events or b in new_events))
        if pairs:
            out.append("〔因果〕原文明说前一件促成了后一件：" + "、".join(pairs))
        return "\n".join(out), seen

    def mentions(self, name: str) -> bool:
        return bool(_norm(name)) and _norm(name) in _norm(self.render())

    def fresh_ids(self) -> set[str]:
        return {item.eid for item in self.items if self.recent and self.recent(item.event_id)}


def beat_line(beat: Beat, pack: EvidencePack) -> str:
    """The memory's own last complete sentence, in the character's voice; a clipped fragment never stands in."""
    summary = pack.voice(beat.item.summary, aloud=True)
    if beat.item.eid.startswith("A"):
        return "档案上写着，" + summary.split("：", 1)[-1][:60].rstrip("，、；") + "。"
    body = summary.split("：", 1)[1] if "：" in summary[:24] else summary
    complete = [part for part in full_sentences(body) if part.endswith(tuple(SENTENCE_ENDS))]
    return complete[-1] if complete else ""


@dataclass(frozen=True)
class Flag:
    index: int
    kind: str
    detail: str = ""

    def note(self) -> str:
        return NOTES[self.kind].format(detail=self.detail)


def _grams(text: str) -> set[str]:
    return set(terms(text, REPLY_GENERIC_CHARS))


def align(sentence: str, beats: list[Beat]) -> tuple[Beat | None, float]:
    """The beat whose wording the sentence shares most, as a share of the sentence's own bigrams."""
    grams = _grams(sentence)
    if len(grams) < 2 or not beats:
        return None, 0.0
    best, score = None, 0.0
    for beat in beats:
        shared = len(grams & _grams(beat.text))
        value = shared / max(3, len(grams)) if shared >= 2 else 0.0
        if value > score:
            best, score = beat, value
    return (best, score) if score >= ALIGN_MIN else (None, score)


def speaks_of_now(sentence: str) -> bool:
    """A present-tense claim in her own voice: a now-word outside a 当时 frame and not after a reporting verb.

    Continuation words such as 还在 or 依然 mark aspect, not tense, and a now-word inside someone's reported words
    belongs to the time they said it.
    """
    if any(word in sentence for word in PAST_FRAME):
        return False
    for word in NOW_WORDS:
        at = sentence.find(word)
        if at >= 0 and not any(verb in sentence[:at] for verb in REPORTING):
            return True
    return False


def _opens_with(sentence: str, words: tuple[str, ...]) -> str:
    head = sentence.lstrip("，,、 　\n")
    return next((word for word in words if head.startswith(word)), "")


def inspect(sentences: list[str], *, pack: EvidencePack, find_entities: Callable[[str], list[str]],
            profile: CharacterProfile = DEFAULT_PROFILE, task: str = "fact", allowed: Iterable[str] = (),
            heard: str = "") -> tuple[list[Flag], list[Beat | None]]:
    """Flag what the evidence structure contradicts or lacks; the alignment is returned for the fallback."""
    beats = pack.beats()
    rendered = pack.render()
    haystack = _norm(rendered + heard)
    licensed = pack.licensed()
    allowed = set(allowed) | {profile.name, profile.player}
    fresh = pack.fresh_ids()
    archives = any(item.eid.startswith("A") for item in pack.items)
    flags: list[Flag] = []
    aligned: list[Beat | None] = []
    previous: Beat | None = None
    for index, raw in enumerate(sentences, 1):
        sentence = raw.strip()
        beat, _ = align(sentence, beats)
        aligned.append(beat)
        found = [name for name in find_entities(sentence) if name not in allowed]
        missing = [name for name in found if not pack.mentions(name)]
        if missing:
            flags.append(Flag(index, "entity", "、".join(missing)))
        if _is_meta(sentence, META_TERMS, profile):
            flags.append(Flag(index, "meta"))
        if unsupported_quote(sentence, haystack):
            flags.append(Flag(index, "quote"))
        denies = next((word for word in DENIAL if word in sentence), "")
        if beat is None:
            if denies and (task == "recount" or (task == "lookup" and archives)):
                flags.append(Flag(index, "denial"))
        else:
            source = _norm(beat.text)
            for numeral, unit in numbers_with_units(sentence):
                if numeral + unit not in source and _arabic(numeral) + unit not in source:
                    flags.append(Flag(index, "number", numeral + unit))
                    break
            over = next((word for word in QUANTITY if word in sentence and word not in beat.text), "")
            if over:
                flags.append(Flag(index, "quantity", over))
            if (speaks_of_now(sentence) and found and beat.item.eid.startswith("E")
                    and beat.item.eid not in fresh):
                flags.append(Flag(index, "stale"))
            if denies:
                flags.append(Flag(index, "denial"))
            if beat.rank is not None and previous is not None and previous.rank is not None:
                if ((_opens_with(sentence, FORWARD) and beat.rank < previous.rank)
                        or (_opens_with(sentence, BACKWARD) and beat.rank > previous.rank)):
                    flags.append(Flag(index, "order"))
                cause = _opens_with(sentence, CAUSAL)
                pair = (previous.item.event_id, beat.item.event_id)
                if (cause and beat is not previous and not any(word in sentence for word in JUDGMENT)
                        and pair not in licensed and pair[::-1] not in licensed):
                    flags.append(Flag(index, "causal", cause))
            previous = beat
        if index >= len(sentences) - 1 and is_closing_offer(sentence):
            flags.append(Flag(index, "closing"))
    return flags, aligned


@dataclass
class CheckReport:
    reviewed: bool = False
    sentences: tuple[str, ...] = ()
    problems: dict[int, str] = field(default_factory=dict)
    issues: dict[int, str] = field(default_factory=dict)
    refetched: tuple[str, ...] = ()
    revised: bool = False
    rechecked: bool = False
    replaced: int = 0
    dropped: int = 0
    calls: int = 0
    stages: list[dict] = field(default_factory=list)


def check_reply(
    draft: str, *,
    complete: Complete,
    messages: Callable[[], list[dict]],
    pack: EvidencePack,
    find_entities: Callable[[str], list[str]],
    refetch: Callable[[list[str]], int],
    temperature: float,
    fallback: str,
    profile: CharacterProfile = DEFAULT_PROFILE,
    task: str = "fact",
    allowed: Iterable[str] = (),
    heard: str = "",
) -> tuple[str, CheckReport]:
    """Align, flag, repair once, align again; a sentence that still fails takes its memory's own sentence.

    Only a sentence that aligns to no memory and still fails after the repair is left out, since nothing in the
    evidence can stand in for it.
    """
    report = CheckReport(reviewed=True)
    allowed = tuple(allowed)
    text = draft.strip()
    if not text:
        return fallback, report
    sentences = split_sentences(text)
    missing = list(dict.fromkeys(name for sentence in sentences for name in find_entities(sentence)
                                 if name not in allowed and not pack.mentions(name)))
    if missing and refetch(missing):
        report.refetched = tuple(missing)

    def run(pieces: list[str]) -> tuple[list[Flag], list[Beat | None]]:
        return inspect(pieces, pack=pack, find_entities=find_entities, profile=profile, task=task,
                       allowed=allowed, heard=heard)

    flags, _ = run(sentences)
    report.sentences = tuple(sentences)
    report.stages.append({"stage": "align", "sentences": [s.strip() for s in sentences],
                          "flags": [{"i": f.index, "kind": f.kind, "detail": f.detail} for f in flags]})
    if not flags:
        return text, report
    notes: dict[int, list[str]] = {}
    for flag in flags:
        notes.setdefault(flag.index, []).append(flag.note())
    report.problems = {index: "；".join(items) for index, items in notes.items()}
    report.issues = {flag.index: flag.kind for flag in flags}
    listing = "\n".join(f"{i}. {s.strip()}" for i, s in enumerate(sentences, 1))
    note = REPAIR_NOTE.format(player=profile.player, listing=listing,
                              notes="\n".join(f"第 {i} 句：{reason}" for i, reason in sorted(report.problems.items())))
    revised = complete([*messages(), {"role": "assistant", "content": text}, {"role": "user", "content": note}],
                       temperature).strip()
    report.calls += 1
    report.revised = True
    pieces = split_sentences(revised) if revised else sentences
    again, aligned = run(pieces)
    report.rechecked = True
    report.stages.append({"stage": "repair", "text": revised,
                          "flags": [{"i": f.index, "kind": f.kind, "detail": f.detail} for f in again]})
    failing = {flag.index for flag in again}
    kept: list[str] = []
    seen = {_norm(piece) for index, piece in enumerate(pieces, 1) if index not in failing}
    for index, piece in enumerate(pieces, 1):
        if index not in failing:
            kept.append(piece)
            continue
        beat = aligned[index - 1]
        line = beat_line(beat, pack) if beat else ""
        if line and _norm(line) not in seen:
            seen.add(_norm(line))
            kept.append(line)
            report.replaced += 1
        else:
            report.dropped += 1
    answer = "".join(kept).strip()
    if report.replaced or report.dropped:
        report.stages.append({"stage": "settle", "replaced": report.replaced, "dropped": report.dropped,
                              "text": answer})
    return answer or fallback, report
