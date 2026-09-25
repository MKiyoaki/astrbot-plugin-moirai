"""Read-only, in-memory terminal chat over a local canon database."""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import math
import os
import re
import sqlite3
from contextlib import ExitStack
from collections import defaultdict
from dataclasses import dataclass, field, replace
from itertools import zip_longest
from pathlib import Path

import httpx

from core.canon.gateway import PAST_MARKERS, CheckReport, EvidencePack, Memory, check_reply
from core.canon.lexical import BigramIndex, terms
from core.canon import retrieval as retrieval_settings
from core.canon.retrieval import fuse, speaker_view
from core.canon.temporal import PREDICATES, resolve

ROOT = Path(__file__).resolve().parent
NEXUS_DB = ROOT / ".dev_data/canon/v7/20/api/20260924-000545-kcl-arc_nexus/canon.sqlite"
TEMPORAL_DB = ROOT / ".dev_data/canon/v7/chat/nexus-v3.sqlite"
LATEST_DB = ROOT / ".dev_data/canon/v7/chat/nexus-20260924-045430.sqlite"
SAMPLE100_DB = ROOT / ".dev_data/canon/v7/chat/100-20260924-171238.sqlite"
FULL_DB = ROOT / ".dev_data/canon/v10/all/build/canon.sqlite"
DEFAULT_DB = next((path for path in (FULL_DB, SAMPLE100_DB, LATEST_DB, TEMPORAL_DB, NEXUS_DB)
                   if path.is_file()), FULL_DB)
DEFAULT_PERSONA = ROOT / "devtools/canon/amiya_persona.txt"
DEFAULT_QUESTIONS = ROOT / ".dev_data/canon/eval/retrieval-200-v1.jsonl"
CHANNEL_LABEL = {
    "experienced": "亲历",
    "witnessed": "在场目睹",
    "told": "听人讲述",
    "recalled": "回忆",
    "unstated": "文本未表明是否知情",
}
SELF_NAMES = frozenset(("阿米娅", "博士"))
SELF_CONTEXT = SELF_NAMES | {"罗德岛"}
GENERIC_CHARS = frozenset(
    "还记得是什么怎么样了吗呢吧啊呀的地得在有没这那你我他她它们个些时候事情知道觉得想要会能可以说过去上次当时一下"
)
QUERY_PAST = ("那次", "那一次", "上次", "当时", "那时", "那天", "那场", "还记得")
LEXICAL_NOISE = ("还记得", "那一次", "那时候", "那次", "那天", "那时", "那场", "当时", "上次", "后来",
                 "为什么", "是什么", "是谁", "什么", "怎么", "知道", "是不是")
LEXICAL_LIMIT = 50
ENTITY_LIMIT = 60
PER_SCENE = 3
SINGLE_LEFT = frozenset("和跟与被让叫问找给对向同帮见把替等陪救及或是说像连带请看喊")
SINGLE_RIGHT = frozenset("第被和跟与的是在说也都就还又为把让给对向从同去来呢吗吧啊呀了着过当之他她那这会能要有没不怎以讲问叫救帮打做看找见一")
SINGLE_BLOCK = frozenset((
    "陈述", "陈旧", "陈列", "陈设", "陈年", "陈词", "陈腐", "辉煌", "今年", "去年", "明年", "那年", "当年",
    "新年", "多年", "几年", "每年", "年轻", "年纪", "年代", "年龄", "命令", "口令", "其余", "多余", "天空",
    "空中", "红色", "黑色", "黑暗", "希望", "失望", "山上", "雪山",
))
REFERENCES = ("她", "他", "那件事")
STATUS_TERMS = (
    "今天", "今晚", "现在", "目前", "最近", "近况", "还在", "还好吗",
    "在岛上", "在舰上", "如今", "怎么样了", "在哪",
)
LANE_LABEL = {"chat": "闲聊", "canon": "剧情", "status": "近况"}
MAX_SUBJECTS = 3
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
OUTPUT_RULES = (
    "[回复要求]\n"
    "· 用陈述句结束回复。不要向博士提问或反问，不要请博士补充、确认或回忆任何事；拿不准时直接说自己记不清或不知道。\n"
    "· 不要说出原作、剧情、章节、资料、编号、检索、数据库这类词。\n"
    "· 讲到过去的具体经历时，只说[你的记忆]里有的内容，不添加其中没有的动作、神情、情绪、数字或原因；过去的事要说成过去。"
)
TOOL_RULE = "\n· 需要具体的过去事件、人物或地点，而[你的记忆]里没有时，先调用 canon_recall。"
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
_CJK = re.compile(r"[一-鿿]+")
_LATIN = re.compile(r"^[A-Za-z0-9'.-]+$")


@dataclass(frozen=True)
class Hit:
    event_id: str
    scene_key: str
    anchor: str
    topic: str
    summary: str
    channel: str
    score: float
    position: int
    evidence: tuple[tuple[int, str, str], ...]


def _matches_alias(query: str, alias: str) -> list[tuple[int, int]]:
    if _LATIN.fullmatch(alias):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])"
        return [(m.start(), m.end()) for m in re.finditer(pattern, query)]
    if len(alias) == 1 and _CJK.fullmatch(alias):
        return [(i, i + 1) for i, char in enumerate(query) if char == alias and _single_ok(query, i)]
    found = []
    start = 0
    while (pos := query.find(alias, start)) >= 0:
        found.append((pos, pos + len(alias)))
        start = pos + len(alias)
    return found


def _single_ok(text: str, i: int) -> bool:
    """A one-character name counts only between non-letters or name-friendly particles, never inside a word."""
    left = text[i - 1] if i > 0 else ""
    right = text[i + 1] if i + 1 < len(text) else ""
    if (left and left + text[i] in SINGLE_BLOCK) or (right and text[i] + right in SINGLE_BLOCK):
        return False
    return ((not left or not _CJK.fullmatch(left) or left in SINGLE_LEFT)
            and (not right or not _CJK.fullmatch(right) or right in SINGLE_RIGHT))


def _estimate_tokens(text: str) -> int:
    cjk = sum(1 for char in text if _CJK.fullmatch(char))
    return cjk + math.ceil((len(text) - cjk) / 4)


def _clip(text: str, limit: int) -> str:
    return text[:limit] + ("……" if len(text) > limit else "")


def _amiya_question(row: sqlite3.Row) -> bool:
    return row["speaker"] == "阿米娅" and row["text"].rstrip("…—.。 ").endswith(("？", "?"))


class CanonReader:
    """Read canon without opening the write-oriented CanonStore."""

    def __init__(self, path: Path, *, character: str = "amiya", retrieval=None) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"找不到 canon 数据库：{path}")
        uri = path.resolve().as_uri() + "?mode=ro"
        self.db = sqlite3.connect(uri, uri=True)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA query_only=ON")
        self.character = character
        self.retrieval = retrieval
        self.last_channels: dict[str, dict[str, int]] = {}
        self.meta = dict(self.db.execute("SELECT key,value FROM meta"))
        self.scene_count = self.db.execute("SELECT count(*) FROM scenes").fetchone()[0]
        self.event_count = self.db.execute("SELECT count(*) FROM events").fetchone()[0]
        self.has_temporal = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='facts'"
        ).fetchone() is not None
        rows = self.db.execute(
            "SELECT a.alias,a.entity_id,e.name,e.type FROM aliases a "
            "JOIN entities e ON e.entity_id=a.entity_id"
        ).fetchall()
        self._index_events({row["alias"]: row["entity_id"] for row in rows})
        rows = [row for row in rows if len(row["alias"]) > 1 or not _CJK.fullmatch(row["alias"])
                or self.entity_events.get(row["entity_id"])]
        self.aliases = sorted([(row["alias"], row["entity_id"]) for row in rows],
                              key=lambda item: -len(item[0]))
        self.alias_names = sorted([(row["alias"], row["name"]) for row in rows],
                                  key=lambda item: -len(item[0]))
        self.entity_type = {row["name"]: row["type"] for row in rows}
        self.has_archives = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='archives'"
        ).fetchone() is not None and self.db.execute("SELECT 1 FROM archives LIMIT 1").fetchone() is not None
        self.titles = tuple(sorted({
            title for row in self.db.execute("SELECT anchor FROM scenes")
            for title in re.findall(r"「([^」]+)」", row["anchor"] or "")
        }))

    def _index_events(self, alias_ids: dict[str, int]) -> None:
        """Lexical documents and entity links, including extracted participants the entity table misses."""
        self.beats: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
        for row in self.db.execute("SELECT event_id,text,evidence FROM event_beats ORDER BY event_id,ord"):
            self.beats[row["event_id"]].append((row["text"], json.loads(row["evidence"])))
        self.entity_events: dict[int, set[str]] = defaultdict(set)
        for row in self.db.execute(
                "SELECT ee.event_id,ee.entity_id FROM event_entities ee "
                "JOIN views v ON v.event_id=ee.event_id WHERE v.character=?", (self.character,)):
            self.entity_events[row["entity_id"]].add(row["event_id"])
        documents, self.position, self.doctor_events = {}, {}, set()
        for row in self.db.execute(
                "SELECT e.event_id,e.topic,e.summary,e.participants,e.narrative_pos,e.involves_doctor "
                "FROM events e JOIN views v ON v.event_id=e.event_id WHERE v.character=?", (self.character,)):
            event_id, participants = row["event_id"], json.loads(row["participants"])
            for name in participants:
                if name in alias_ids:
                    self.entity_events[alias_ids[name]].add(event_id)
            documents[event_id] = "\n".join((
                row["topic"], row["summary"], "、".join(participants),
                *(text for text, _ in self.beats.get(event_id, ())),
            )).replace("{DOCTOR}", "博士").replace("@doctor", "博士")
            self.position[event_id] = row["narrative_pos"]
            if row["involves_doctor"]:
                self.doctor_events.add(event_id)
        self.lexical = BigramIndex(documents)
        self.event_lines: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in self.db.execute(
                "SELECT ee.event_id,l.line_key,l.speaker,l.text FROM event_evidence ee "
                "JOIN lines l ON l.line_key=ee.line_key ORDER BY ee.event_id,ee.ord"):
            if row["event_id"] in self.position and row["text"].strip():
                self.event_lines[row["event_id"]].append(
                    (row["line_key"], f"{row['speaker'] or '旁白'}：{row['text']}"))
        self.line_lexical = BigramIndex({event_id: "\n".join(text for _, text in lines)
                                         for event_id, lines in self.event_lines.items()})

    def close(self) -> None:
        self.db.close()

    def persons_in(self, query: str) -> list[str]:
        return [name for name in self.entities_in(query) if self.entity_type.get(name) == "person"]

    def _spans(self, text: str) -> list[tuple[int, int, str]]:
        occupied: list[tuple[int, int, str]] = []
        for alias, name in self.alias_names:
            for start, end in _matches_alias(text, alias):
                if any(start < right and left < end for left, right, _ in occupied):
                    continue
                occupied.append((start, end, name))
        return sorted(occupied)

    def entities_in(self, text: str) -> list[str]:
        names = [name for _, _, name in self._spans(text) if name not in SELF_CONTEXT]
        return list(dict.fromkeys(names))

    def archive_ids(self, name: str) -> list[str]:
        """Entity links first (through aliases), then the archive's own name; operators before enemies."""
        name = name.strip()
        if not self.has_archives or not name:
            return []
        row = self.db.execute(
            "SELECT e.name FROM aliases a JOIN entities e ON e.entity_id=a.entity_id WHERE a.alias=?", (name,)
        ).fetchone()
        names = [row["name"]] if row else ([n for _, _, n in self._spans(name)] or [name])
        found: list[str] = []
        for entity in dict.fromkeys(names):
            found += [r["archive_id"] for r in self.db.execute(
                "SELECT ea.archive_id FROM entity_archives ea JOIN entities e ON e.entity_id=ea.entity_id "
                "JOIN archives a ON a.archive_id=ea.archive_id WHERE e.name=? "
                "ORDER BY a.kind='enemy', a.archive_id", (entity,))]
            found += [r["archive_id"] for r in self.db.execute(
                "SELECT archive_id FROM archives WHERE name=? OR appellation=? COLLATE NOCASE "
                "ORDER BY kind='enemy', archive_id", (entity, entity))]
        return list(dict.fromkeys(found))

    def archive_sections(self, archive_id: str, *, every_form: bool) -> list[sqlite3.Row]:
        """By default only the archive's own form: no PATCH unlocks, other forms or hidden sections."""
        rows = self.db.execute(
            "SELECT s.*, a.name, a.kind FROM archive_sections s JOIN archives a ON a.archive_id=s.archive_id "
            "WHERE s.archive_id=? ORDER BY s.seq, s.version", (archive_id,)
        ).fetchall()
        if every_form:
            return rows
        return [row for row in rows if not row["hidden"] and row["unlock_type"] != "PATCH"
                and (not json.loads(row["forms"]) or archive_id in json.loads(row["forms"]))]

    def semantic(self, query: str, doctor: bool) -> str:
        return speaker_view(query) if doctor and retrieval_settings.SPEAKER_VIEW else query

    def without_self(self, text: str) -> str:
        """Her own and the Doctor's names match nearly every event, so they never steer retrieval."""
        for start, end, name in reversed(self._spans(text)):
            if name in SELF_NAMES:
                text = text[:start] + " " + text[end:]
        return text

    def fact_context(self, subject: str, *, as_of: str | None = None) -> tuple[str, bool]:
        if not self.has_temporal:
            return "", False
        decisions = [resolve(self.db, subject, predicate, as_of=as_of)
                     for predicate in PREDICATES]
        valid = [d for d in decisions if d.status == "as_of_valid"]
        lines = ["〔F〕[已审阅的时间事实] 以下是截至指定时间点的状态，不代表现实中的今天。"]
        for decision in valid:
            for fact in decision.facts:
                lines.append(
                    f"· {fact['subject']} {fact['predicate']} "
                    f"{'非' if not fact['polarity'] else ''}{fact['object']}；"
                    f"时间点 {fact['point_label']}；状态 {decision.status}"
                )
                for ev in fact["evidence"][:3]:
                    channel = ev["channel"] or "unstated"
                    lines.append(
                        f"  证据 {ev['line_key']}（阿米娅渠道 {channel}）：{ev['text'][:100]}"
                    )
                for change in fact["transitions"]:
                    lines.append(
                        f"  状态变更 {change['earlier_fact_id']} → {fact['fact_id']}；"
                        f"证据 {change['evidence_event_id']} {change['evidence_line_key']}"
                    )
        return ("\n".join(lines) if valid else ""), bool(valid)

    def _lexical(self, query: str) -> tuple[dict[str, int], dict[str, float], list[str]]:
        for noise in LEXICAL_NOISE:
            query = query.replace(noise, " ")
        query_terms = terms(query, GENERIC_CHARS)
        scores = self.lexical.scores(query_terms)
        ordered = sorted(scores, key=lambda eid: (-scores[eid], self.position[eid]))[:LEXICAL_LIMIT]
        return {eid: rank for rank, eid in enumerate(ordered, 1)}, scores, query_terms

    def _lines(self, query_terms: list[str]) -> dict[str, int]:
        """Raw dialogue keeps names, epithets and quotes that summaries leave out."""
        scores = self.line_lexical.scores(query_terms)
        ordered = sorted(scores, key=lambda eid: (-scores[eid], self.position[eid]))[:LEXICAL_LIMIT]
        return {eid: rank for rank, eid in enumerate(ordered, 1)}

    def _line_keys(self, event_id: str, query_terms: list[str]) -> list[str]:
        weighted = [(self.line_lexical.weight(text, query_terms), key) for key, text in self.event_lines.get(event_id, ())]
        best = max((weight for weight, _ in weighted), default=0.0)
        ranked = sorted((item for item in weighted if best and item[0] >= max(1.0, 0.6 * best)), key=lambda item: -item[0])
        return [key for _, key in ranked[:2]]

    def _entities(self, query: str, doctor: bool, lexical: dict[str, float]) -> dict[str, int]:
        """Events linked to the named entities, most entities first, then by lexical relevance."""
        occupied: list[tuple[int, int]] = []
        entity_ids: set[int] = set()
        for alias, entity_id in self.aliases:
            for start, end in _matches_alias(query, alias):
                if any(start < right and left < end for left, right in occupied):
                    continue
                occupied.append((start, end))
                entity_ids.add(entity_id)
        hits: dict[str, int] = defaultdict(int)
        for entity_id in entity_ids:
            for event_id in self.entity_events.get(entity_id, ()):
                hits[event_id] += 1
        order = lambda eid: (-hits[eid], -lexical.get(eid, 0.0), self.position[eid])
        event_ids = sorted(hits, key=order)[:ENTITY_LIMIT]
        if doctor and "我" in query and any(term in query for term in QUERY_PAST):
            extra = sorted(self.doctor_events - set(event_ids),
                           key=lambda eid: (-lexical.get(eid, 0.0), self.position[eid]))[:30]
            event_ids += extra
        return {event_id: rank for rank, event_id in enumerate(event_ids, 1)}

    def _beat_keys(self, event_id: str, query_terms: list[str]) -> list[str]:
        weighted = [(self.lexical.weight(text, query_terms), keys) for text, keys in self.beats.get(event_id, ())]
        best = max((weight for weight, _ in weighted), default=0.0)
        return [key for weight, keys in weighted if best and weight >= max(1.0, 0.6 * best) for key in keys]

    def _evidence(self, event_id: str, preferred: list[str],
                  limit: int) -> tuple[tuple[int, str, str], ...]:
        rows = self.db.execute(
            "SELECT l.line_key,l.speaker,l.text,ee.ord FROM event_evidence ee "
            "JOIN lines l ON l.line_key=ee.line_key WHERE ee.event_id=? ORDER BY ee.ord",
            (event_id,),
        ).fetchall()
        by_key = {row["line_key"]: row for row in rows}
        beats = [json.loads(row["evidence"]) for row in self.db.execute(
            "SELECT evidence FROM event_beats WHERE event_id=? ORDER BY ord", (event_id,))]
        spread = [key for depth in zip_longest(*beats) for key in depth if key]
        ordered = [key for key in dict.fromkeys([*preferred, *spread]) if key in by_key]
        rest = sorted(
            (row for row in rows if row["line_key"] not in ordered),
            key=lambda row: (_amiya_question(row), row["speaker"] != "阿米娅", row["ord"]),
        )
        ordered.extend(row["line_key"] for row in rest)
        return tuple(
            (by_key[key]["ord"], by_key[key]["speaker"] or "旁白", _clip(by_key[key]["text"], 160))
            for key in ordered[:limit]
        )

    def search(self, query: str, *, top_k: int, evidence_lines: int,
               doctor: bool, focus_person: str | None = None) -> tuple[list[Hit], str | None]:
        semantic_query = self.semantic(query, doctor)
        query = self.without_self(query)
        fts, lexical_scores, query_terms = self._lexical(query)
        entities = self._entities(query, doctor, lexical_scores)
        lines = self._lines(query_terms)
        self.last_channels = {"fts": fts, "entities": entities, "lines": lines}
        remote_scores = self.retrieval.rank(semantic_query, fts, entities, lines) if self.retrieval else None
        candidate_ids = (list(remote_scores) if remote_scores is not None
                         else list(dict.fromkeys([*fts, *lines, *entities])))
        if not candidate_ids:
            return [], None
        marks = ",".join("?" for _ in candidate_ids)
        rows = self.db.execute(
            "SELECT e.event_id,e.scene_key,e.topic,e.summary,e.narrative_pos,"
            "s.anchor,s.tier,v.channel FROM events e "
            "JOIN scenes s ON s.scene_key=e.scene_key "
            "JOIN views v ON v.event_id=e.event_id "
            f"WHERE e.event_id IN ({marks}) AND v.character=?",
            (*candidate_ids, self.character),
        ).fetchall()
        raw_rrf = fuse({"lexical": fts, "lines": lines, "entities": entities})
        maximum = max(raw_rrf.values(), default=0.0) or 1.0
        scored = []
        focus_id = None
        if focus_person:
            found = self.db.execute(
                "SELECT entity_id FROM entities WHERE name=?", (focus_person,)
            ).fetchone()
            focus_id = found["entity_id"] if found else None
        for row in rows:
            if (focus_person and focus_person not in (row["topic"] + row["summary"])
                    and row["event_id"] not in self.entity_events.get(focus_id, ())):
                continue
            event_id = row["event_id"]
            if remote_scores is not None:
                score = remote_scores[event_id]
            else:
                score = raw_rrf.get(event_id, 0.0) / maximum
            scored.append((score, row))
        scored.sort(key=lambda item: (-item[0], -item[1]["narrative_pos"], item[1]["event_id"]))
        selected = []
        per_scene: dict[str, int] = defaultdict(int)
        for score, row in scored:
            if per_scene[row["scene_key"]] >= PER_SCENE:
                continue
            per_scene[row["scene_key"]] += 1
            selected.append(Hit(
                event_id=row["event_id"], scene_key=row["scene_key"], anchor=row["anchor"],
                topic=row["topic"], summary=row["summary"], channel=row["channel"],
                score=score, position=row["narrative_pos"],
                evidence=self._evidence(row["event_id"],
                                        [*self._line_keys(row["event_id"], query_terms),
                                         *self._beat_keys(row["event_id"], query_terms)],
                                        evidence_lines),
            ))
            if len(selected) >= top_k:
                break
        episode = None
        if selected:
            row = self.db.execute(
                "SELECT text FROM episodes WHERE scene_key=? AND character=?",
                (selected[0].scene_key, self.character),
            ).fetchone()
            episode = row["text"] if row else None
        return selected, episode


def fill(pack: EvidencePack, hits: list[Hit], episode: str | None, budget: int,
         *, total_budget: int | None = None) -> list[Memory]:
    """Add hits within both this fetch's share and the turn's cumulative evidence budget."""
    cap = budget if total_budget is None else total_budget
    added: list[Memory] = []
    for index, hit in enumerate(hits):
        if hit.event_id in pack:
            continue
        lines = list(hit.evidence)
        note = episode if index == 0 and episode else ""
        while True:
            item = pack.add(hit.event_id, hit.anchor, hit.channel, hit.summary,
                            tuple((speaker, text) for _, speaker, text in sorted(lines)), note)
            if (_estimate_tokens(pack.render([*added, item])) <= budget
                    and _estimate_tokens(pack.render()) <= cap):
                added.append(item)
                break
            pack.pop()
            if note:
                note = ""
            elif lines:
                lines.pop()
            else:
                return added
    return added


def asks_status(query: str) -> bool:
    return any(term in query for term in STATUS_TERMS)


ROUTE_IDF_MASS = 2.7


def distinctive_mass(reader: CanonReader, query: str) -> float:
    """The query's corpus-rare vocabulary mass, scaled by this corpus's rarest term.

    Small talk reaches canon-level dense similarity by matching everyday words the
    corpus also uses; a story question carries terms that are rare within the
    corpus. The ratio stays on one scale across corpus sizes, where the raw
    similarity threshold does not.
    """
    idf = reader.lexical.idf
    if not idf:
        return 0.0
    total = sum(idf[term] for term in dict.fromkeys(terms(query, GENERIC_CHARS)) if term in idf)
    return total / max(idf.values())


@dataclass(frozen=True)
class TurnPlan:
    lane: str
    subjects: tuple[str, ...]
    focus: str | None
    search_query: str
    by_retrieval: bool = False


def plan_turn(reader: CanonReader, query: str, focus: str | None, as_of: str | None) -> TurnPlan:
    """Decide what the turn touches; the reply itself is never chosen here."""
    explicit = reader.persons_in(query)[:MAX_SUBJECTS]
    focus = explicit[0] if explicit else focus
    names = reader.entities_in(query)
    past = any(term in query for term in QUERY_PAST)
    pointer = any(term in query for term in REFERENCES)
    carry = bool(focus) and not names and (pointer or (past and "我" not in query and "你" not in query))
    subjects = tuple(explicit) or ((focus,) if carry else ())
    if subjects and (asks_status(query) or as_of):
        lane = "status"
    elif names or subjects or past:
        lane = "canon"
    else:
        lane = "chat"
    search_query = " ".join([query, *(name for name in subjects if name not in query)])
    return TurnPlan(lane, subjects, focus, search_query)


def route(reader: CanonReader, plan: TurnPlan, query: str, doctor: bool) -> TurnPlan:
    """A story question without names or time words still reaches canon when retrieval is confident."""
    if plan.lane != "chat" or reader.retrieval is None:
        return plan
    probe = reader.semantic(reader.without_self(query), doctor)
    if reader.retrieval.confident(probe) and distinctive_mass(reader, probe) >= ROUTE_IDF_MASS:
        return replace(plan, lane="canon", by_retrieval=True)
    return plan


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
    if pack.items:
        lines.append("以下是和这句话有关的零散记忆，都是过去的事，不代表现在。编号只供你对照，不要说出来。")
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
    return "\n\n".join((persona, identity, rules,
                        knowledge(plan, pack, fact_block, fact_valid, tools)))


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
        response = self.client.post(
            f"{self.url}/chat/completions",
            headers={"Authorization": f"Bearer {self.key}"},
            json=body,
        )
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
    plan: TurnPlan | None = None
    pack: EvidencePack | None = None
    fact_block: str = ""
    tool_queries: list[str] = field(default_factory=list)
    report: CheckReport | None = None


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
    messages = [{"role": "system", "content": system}, *session.history,
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
    return f"路线：{LANE_LABEL[plan.lane]}" + (f"（{who}）" if who else "")


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
    if report.dropped:
        parts.append(f"修订后又删去 {report.dropped} 句")
    if report.questions_removed:
        parts.append(f"删去结尾提问 {report.questions_removed} 句")
    if report.meta_removed:
        parts.append(f"删去出戏句 {report.meta_removed} 句")
    parts.append(f"模型调用 {calls} 次")
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
    plan = route(reader, plan_turn(reader, query, session.focus, args.as_of), query, args.doctor)
    session.focus = plan.focus
    pack = EvidencePack("对方（博士）" if args.doctor else "博士", args.doctor)
    session.plan, session.pack, session.report = plan, pack, None
    session.tool_queries = []

    def fetch(text: str, focus_person: str | None = None,
              budget: int = args.token_budget) -> list[Memory]:
        hits, episode = reader.search(text, top_k=args.top_k, evidence_lines=args.evidence_lines,
                                      doctor=args.doctor, focus_person=focus_person)
        return fill(pack, hits, episode, budget, total_budget=args.token_budget)

    if plan.lane != "chat":
        share = args.token_budget // max(1, len(plan.subjects))
        for subject in plan.subjects if len(plan.subjects) > 1 else (None,):
            fetch(plan.search_query, subject, share)
    if reader.retrieval:
        trace = reader.retrieval.last_trace
        print(f"[retrieval] {reader.retrieval.mode}；"
              f"{'降级' if trace.get('degraded') else '就绪'}；"
              f"{trace.get('seconds', 0):.3f}s")
        if trace.get("degraded"):
            print(f"[retrieval] {trace.get('embedding_error') or trace.get('rerank_error')}")
    fact_block, fact_valid = "", False
    if plan.lane == "status":
        contexts = [reader.fact_context(subject, as_of=args.as_of) for subject in plan.subjects]
        fact_block = "\n".join(block for block, _ in contexts if block)
        fact_valid = all(valid for _, valid in contexts)
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
        added = fetch(wanted)
        if added:
            return pack.render(added)
        return "没有想起新的相关的事；只根据上面已有的记忆回答，没有的就说记不清。"

    def add_archive(key: str, source: str, body: str) -> Memory | None:
        if key in pack or not body:
            return None
        body = body[:ARCHIVE_CHARS]
        minimum = min(40, len(body))
        low, high, best = minimum, len(body), 0
        while low <= high:
            size = (low + high) // 2
            summary = f"{source}：{_clip(body, size)}"
            item = pack.add(key, source, "archive", summary, (), prefix="A")
            fits = _estimate_tokens(pack.render()) <= args.token_budget
            pack.pop()
            if fits:
                best = size
                low = size + 1
            else:
                high = size - 1
        if not best:
            return None
        return pack.add(key, source, "archive", f"{source}：{_clip(body, best)}", (), prefix="A")

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
                         f"{_clip('、'.join(titles), 80)}")
        body = pack.render(added) if added else "本轮证据预算已满，或档案没有可加入的内容。"
        return body + "\n" + "\n".join(notes)

    def messages() -> list[dict]:
        system = build_system(persona, args.doctor, plan, pack, fact_block, fact_valid, False)
        return [{"role": "system", "content": system}, *session.history,
                {"role": "user", "content": query}]

    def refetch(names: list[str]) -> int:
        return len(fetch(" ".join(names)))

    def sources() -> str:
        said = [m["content"] for m in session.history if m["role"] == "user"][-4:] + [query]
        identity = ("[对话者]\n当前对话者是博士；[资料]里的“对方（博士）”就是当前对话者。" if args.doctor else
                    "[对话者]\n当前对话者不是博士；[资料]里的“博士”是另一个人，与博士有关的经历不算和当前对话者的共同经历。")
        parts = [identity, "", "[资料]", pack.render() or "（本轮没有资料）"]
        if fact_valid:
            parts.append(fact_block)
        parts += ["", "[人设档案]", profile or "（无）", "", "[对话者本次说过的话]",
                  *(f"· {text}" for text in said)]
        return "\n".join(parts)

    archives = reader.has_archives
    tools = [RECALL_TOOL, ARCHIVE_TOOL] if archives else [RECALL_TOOL]
    handlers = {"canon_recall": recall, "operator_archive": archive}
    system = build_system(persona, args.doctor, plan, pack, fact_block, fact_valid, session.tools, archives)
    draft, calls = generate(llm, session, system, query, tools, handlers, args.temperature)
    answer, report = check_reply(
        draft, complete=llm.complete, messages=messages, pack=pack,
        find_entities=reader.entities_in, refetch=refetch, sources=sources,
        extra_ids={"F"} if fact_valid else None, current_ok=fact_valid,
        force_review=bool(pack.items), temperature=args.temperature,
        extra_terms=reader.titles, fallback=FALLBACK,
    )
    session.report = report
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
    parser.add_argument("--token-budget", type=int, default=900, help="每次取证注入的 token 上限")
    parser.add_argument("--evidence-lines", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--no-tools", action="store_true", help="不向模型提供 canon_recall 和档案查询工具")
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
        print("[canon] 闲聊只生成一次；回复涉及剧情时加一次核验，有无依据的句子再加一次修订"
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
