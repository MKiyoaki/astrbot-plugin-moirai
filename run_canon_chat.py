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
import time
from contextlib import ExitStack
from collections import defaultdict
from dataclasses import dataclass, field, replace
from itertools import zip_longest
from pathlib import Path

import httpx

from core.canon.gateway import PAST_MARKERS, CheckReport, EvidencePack, Memory, check_reply
from core.canon.context import expand_events, resolve_name
from core.canon.lexical import BigramIndex, terms
from core.canon.overview import (OVERVIEW_MAX_CANDIDATES, OVERVIEW_MAX_SCENES, OVERVIEW_MAX_EVENTS,
                                 STORY_MAX_EVENTS, OverviewCandidate, is_overview, select_events, topic_terms)
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
DEFAULT_PERSONA = ROOT / "devtools/canon/amiya_persona_concise.txt"
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
PERSON_REFERENCES = ("她", "他", "那个人")
OTHER_REFERENCES = ("它", "那里", "那座城", "那个地方")
EVENT_REFERENCES = ("那件事", "那次", "那一回")
REASON_MARKERS = ("为什么", "为何", "原因", "缘由", "动机", "目的")
IMPRESSION_MARKERS = ("印象", "看法", "怎么看", "感觉如何")
RATIONALE_CUES = ("动机", "来意", "理想", "原因", "因为", "为了", "目的是", "旨在", "阻止", "避免", "减少牺牲", "而战")
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


_PRIVATE_DOCTOR = re.compile(
    r"(?:\{DOCTOR\}|博士)[^，。！？]{0,12}(?:感到|感觉|觉得|意识到|直觉|心里|不由自主|无法准确判断)"
)


def visible_summary(summary: str) -> str:
    """Leave unspoken Doctor thoughts out of Amiya's injected memory summaries."""
    return "".join(part for part in re.split(r"(?<=[。！？])", summary)
                   if not _PRIVATE_DOCTOR.search(part)).strip()


def explicit_quote(query: str) -> str | None:
    """Extract a literal claim only when the question supplies concrete wording."""
    quoted = (re.findall(r'[“「『"]([^”」』"]{4,24})[”」』"]', query)
              if any(word in query for word in ('是不是', '有没有', '是否', '说过', '叫过', '原话', '称呼')) else [])
    marker = re.search(
        r'(?:管.{1,12}?叫|(?:是不是|是否|有没有)叫|被叫做|叫做|叫作|称作|称为|称呼|喊作|说成)'
        r'([一-鿿A-Za-z0-9·]{4,20})[吗呢吧了]?[？?。]*$', query)
    endings = [phrase.strip() for phrase in quoted]
    if marker:
        endings.append(marker.group(1).lstrip('是为作').rstrip('吗呢吧了'))
    for phrase in endings:
        if 4 <= len(phrase) <= 24 and not any(word in phrase for word in (
                '什么', '哪个', '哪句', '谁', '多少', '如何', '那天', '什么时候')):
            return phrase
    return None


def _amiya_question(row: sqlite3.Row) -> bool:
    return row["speaker"] == "阿米娅" and row["text"].rstrip("…—.。 ").endswith(("？", "?"))


def _identity_pairs(summary: str, names: set[str], lines: list[tuple[str, str]]) -> set[frozenset[str]]:
    pairs = set()
    for match in re.finditer(r"([一-鿿A-Za-z0-9·]{2,14})[（(]([一-鿿A-Za-z0-9·]{2,14})[）)]", summary):
        first, second = match.groups()
        if first == second or first not in names or second not in names:
            continue
        if (any(text.startswith(first + "：") for _, text in lines)
                and any(second in text for _, text in lines)) or (
                any(text.startswith(second + "：") for _, text in lines)
                and any(first in text for _, text in lines)):
            pairs.add(frozenset((first, second)))
    return pairs


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
        self.last_expansion_trace: dict = {}
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
        self._index_scenes()
        rows = [row for row in rows if len(row["alias"]) > 1 or not _CJK.fullmatch(row["alias"])
                or self.entity_events.get(row["entity_id"])]
        self.aliases = sorted([(row["alias"], row["entity_id"]) for row in rows],
                              key=lambda item: -len(item[0]))
        self.alias_names = sorted([(row["alias"], row["name"]) for row in rows],
                                  key=lambda item: -len(item[0]))
        self.entity_type = {row["name"]: row["type"] for row in rows}
        self.identity_events: dict[frozenset[str], str] = {}
        person_names = {name for name, kind in self.entity_type.items() if kind == "person"}
        for row in self.db.execute("SELECT event_id,summary FROM events"):
            for pair in _identity_pairs(row["summary"], person_names,
                                        self.event_lines.get(row["event_id"], [])):
                self.identity_events.setdefault(pair, row["event_id"])
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
        self.events_by_scene: dict[str, list[str]] = defaultdict(list)
        self.event_scene: dict[str, str] = {}
        self.event_order: dict[str, int] = {}
        for row in self.db.execute(
                "SELECT e.event_id,e.scene_key,e.topic,e.summary,e.participants,e.narrative_pos,e.involves_doctor,e.ord "
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
            self.event_order[event_id] = row["ord"]
            self.events_by_scene[row["scene_key"]].append(event_id)
            self.event_scene[event_id] = row["scene_key"]
            if row["involves_doctor"]:
                self.doctor_events.add(event_id)
        self.event_documents = documents
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

    def _index_scenes(self) -> None:
        self.scene_meta = {}
        collections: dict[str, list[tuple[int, str]]] = defaultdict(list)
        documents = {}
        for row in self.db.execute(
                "SELECT s.scene_key,s.narrative_pos,s.anchor,s.collection_id,s.collection_name,"
                "s.story_name,s.official_summary,p.text episode FROM scenes s "
                "LEFT JOIN episodes p ON p.scene_key=s.scene_key AND p.character=?",
                (self.character,)):
            scene = dict(row)
            self.scene_meta[row["scene_key"]] = scene
            collections[row["collection_id"] or row["scene_key"]].append(
                (row["narrative_pos"], row["scene_key"]))
            documents[row["scene_key"]] = "\n".join(
                str(row[key] or "") for key in
                ("anchor", "collection_name", "story_name", "official_summary", "episode"))
        self.scene_lexical = BigramIndex(documents)
        self.collection_scenes = {
            key: [scene for _, scene in sorted(values)] for key, values in collections.items()
        }

    def close(self) -> None:
        self.db.close()

    def persons_in(self, query: str) -> list[str]:
        return [name for name in self.entities_in(query) if self.entity_type.get(name) == "person"]

    def topic_mentions(self, query: str) -> list[str]:
        return list(dict.fromkeys(name for _, _, name in self._spans(query) if name not in SELF_NAMES))

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

    def identity_hit(self, first: str, second: str) -> Hit | None:
        event_id = self.identity_events.get(frozenset((first, second)))
        if event_id is None:
            return None
        row = self.db.execute(
            "SELECT e.scene_key,e.topic,e.summary,e.narrative_pos,s.anchor,v.channel "
            "FROM events e JOIN scenes s ON s.scene_key=e.scene_key "
            "JOIN views v ON v.event_id=e.event_id WHERE e.event_id=? AND v.character=?",
            (event_id, self.character),
        ).fetchone()
        if row is None:
            return None
        preferred = [key for key, text in self.event_lines[event_id]
                     if text.startswith(first + "：") or text.startswith(second + "：")
                     or first in text or second in text]
        return Hit(event_id, row["scene_key"], row["anchor"], row["topic"], row["summary"],
                   row["channel"], 1.0, row["narrative_pos"], self._evidence(event_id, preferred, 3))


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
               doctor: bool, focus_person: str | None = None,
               known_only: bool = False) -> tuple[list[Hit], str | None]:
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
            if known_only and row["channel"] == "unstated":
                continue
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

    def exact_quote_hits(self, query: str, phrase: str, evidence_lines: int) -> list[Hit]:
        """Find known events with the user's exact quoted wording in a source line."""
        matching = {event_id: [key for key, text in lines if phrase in text.partition("：")[2]]
                    for event_id, lines in self.event_lines.items()}
        matching = {event_id: keys for event_id, keys in matching.items() if keys}
        if not matching or len(matching) > 16:
            return []
        marks = ",".join("?" for _ in matching)
        rows = self.db.execute(
            "SELECT e.event_id,e.scene_key,e.topic,e.summary,e.narrative_pos,"
            "s.anchor,v.channel FROM events e JOIN scenes s ON s.scene_key=e.scene_key "
            "JOIN views v ON v.event_id=e.event_id "
            f"WHERE e.event_id IN ({marks}) AND v.character=? AND v.channel!='unstated'",
            (*matching, self.character),
        ).fetchall()
        first_person = next(iter(self.persons_in(query)), None)
        lexical = self._lexical(query)[1]
        rows = sorted(rows, key=lambda row: (
            -int(bool(first_person) and any(
                text.startswith(first_person + "：") and phrase in text
                for _, text in self.event_lines[row["event_id"]])),
            -lexical.get(row["event_id"], 0.0), -row["narrative_pos"], row["event_id"]))
        return [Hit(row["event_id"], row["scene_key"], row["anchor"], row["topic"],
                    row["summary"], row["channel"], 1.0, row["narrative_pos"],
                    self._evidence(row["event_id"], matching[row["event_id"]], evidence_lines))
                for row in rows[:3]]

    def overview_search(self, query: str, *, doctor: bool, evidence_lines: int = 1,
                        personal: bool = False, contextual: bool = False) -> tuple[list[Hit], dict]:
        """Build one dense-backed pool, then select distinct story moments locally."""
        base, _ = self.search(query, top_k=40, evidence_lines=0, doctor=doctor)
        if contextual and base:
            scope = self.scene_meta[base[0].scene_key]["collection_id"]
            scoped = [hit for hit in base if self.scene_meta[hit.scene_key]["collection_id"] == scope]
            primary = [replace(hit, evidence=self.overview_evidence(hit.event_id,
                       self._line_keys(hit.event_id, topic_terms(query, GENERIC_CHARS)), evidence_lines))
                       for hit in scoped[:4]]
            context = self.expand_context(primary[:1], query)
            seen = set()
            hits = []
            for hit in [*primary[:1], *context]:
                if hit.event_id not in seen:
                    seen.add(hit.event_id)
                    hits.append(hit)
            trace = {"scope": None, "candidates": len(base), "selected": [h.event_id for h in hits],
                     "expansion": self.last_expansion_trace, "source_lines": {
                         h.event_id: self.source_keys(h) for h in hits}}
            self.last_overview_trace = trace
            return hits, trace
        original = {hit.event_id: rank for rank, hit in enumerate(base)}
        query_terms = topic_terms(query, GENERIC_CHARS)
        event_scores = self.lexical.scores(query_terms)
        scene_scores = self.scene_lexical.scores(query_terms)
        named = [(len(info["collection_name"]), info["collection_id"], info["collection_name"])
                 for info in self.scene_meta.values()
                 if info["collection_id"] and info["collection_name"]
                 and len(info["collection_name"]) >= 2 and info["collection_name"] in query]
        pinned = max(named)[1] if named else None
        collection_scores: dict[str, list[float]] = defaultdict(list)
        for event_id, score in event_scores.items():
            scene = self.event_scene.get(event_id)
            if scene:
                collection = self.scene_meta[scene]["collection_id"] or scene
                collection_scores[collection].append(score)
        collection_rank = sorted(
            ((sum(sorted(values, reverse=True)[:8]), key)
             for key, values in collection_scores.items()), reverse=True)
        primary = pinned or (collection_rank[0][1] if collection_rank else None)
        pool = set(original)
        pool.update(sorted(event_scores, key=lambda eid: -event_scores[eid])[:100])
        for scene in sorted(scene_scores, key=lambda key: -scene_scores[key])[:OVERVIEW_MAX_SCENES]:
            pool.update(self.events_by_scene.get(scene, ()))
        if pinned:
            for scene in self.collection_scenes.get(pinned, ()):
                pool.update(self.events_by_scene.get(scene, ()))
        event_max = max(event_scores.values(), default=1.0) or 1.0
        scene_max = max(scene_scores.values(), default=1.0) or 1.0

        def relevance(event_id: str) -> float:
            scene = self.event_scene[event_id]
            score = 0.35 / (1 + original[event_id] / 8) if event_id in original else 0.0
            score += 0.45 * event_scores.get(event_id, 0.0) / event_max
            score += 0.35 * scene_scores.get(scene, 0.0) / scene_max
            collection = self.scene_meta.get(scene, {}).get("collection_id")
            if collection == primary:
                score += 0.52
            if pinned and collection == pinned:
                score += 0.25
            return score

        ranked = sorted((eid for eid in pool if eid in self.event_documents),
                        key=lambda eid: (-relevance(eid), eid))[:OVERVIEW_MAX_CANDIDATES]
        if not ranked:
            return [], {"scope": None, "candidates": 0, "selected": []}
        marks = ",".join("?" for _ in ranked)
        rows = self.db.execute(
            "SELECT e.event_id,e.scene_key,e.topic,e.summary,e.narrative_pos,"
            "s.anchor,s.collection_id,s.collection_name,v.channel FROM events e "
            "JOIN scenes s ON s.scene_key=e.scene_key "
            "JOIN views v ON v.event_id=e.event_id "
            f"WHERE e.event_id IN ({marks}) AND v.character=?",
            (*ranked, self.character),
        ).fetchall()
        candidates = []
        by_id = {}
        for row in rows:
            if (row["channel"] == "unstated" or personal and
                    row["channel"] not in ("experienced", "witnessed", "told", "recalled")):
                continue
            scene = row["scene_key"]
            collection = row["collection_id"] or scene
            scene_order = self.collection_scenes.get(collection, [scene])
            phase = min(2, 3 * scene_order.index(scene) // max(1, len(scene_order)))
            candidates.append(OverviewCandidate(
                row["event_id"], scene, collection, relevance(row["event_id"]),
                phase, self.event_documents[row["event_id"]][:300]))
            by_id[row["event_id"]] = row
        story = not personal and not contextual and is_overview(query)
        limit = STORY_MAX_EVENTS if story else OVERVIEW_MAX_EVENTS
        selected = select_events(candidates, limit=limit, pinned_collection=pinned)
        hits = []
        source_lines = {}
        for event_id in selected:
            row = by_id[event_id]
            evidence = self.overview_evidence(event_id, [], evidence_lines)
            hits.append(Hit(event_id, row["scene_key"], row["anchor"], row["topic"],
                            row["summary"], row["channel"], relevance(event_id),
                            row["narrative_pos"], evidence))
            ords = [line[0] for line in evidence]
            if ords:
                marks = ",".join("?" for _ in ords)
                line_keys = {line["ord"]: line["line_key"] for line in self.db.execute(
                    "SELECT ord,line_key FROM event_evidence WHERE event_id=? "
                    f"AND ord IN ({marks})", (event_id, *ords))}
                source_lines[event_id] = [line_keys[ord_] for ord_ in ords]
        scope = next((info["collection_name"] for info in self.scene_meta.values()
                      if info["collection_id"] == primary and info["collection_name"]), None)
        trace = {"scope": scope, "scope_id": primary, "candidates": len(candidates),
                 "selected": selected, "source_lines": source_lines,
                 "remote_queries": 1 if self.retrieval else 0,
                 "collection_candidates": collection_rank[:5]}
        context = self.expand_context(hits[:4], query) if not personal else []
        known = {hit.event_id for hit in hits}
        extra = [hit for hit in context if hit.event_id not in known]
        if extra:
            hits = [*hits[:6], *extra[:2], *hits[6:]][:limit]
        trace["expansion"] = self.last_expansion_trace
        trace["selected"] = [hit.event_id for hit in hits]
        for hit in hits:
            source_lines[hit.event_id] = self.source_keys(hit)
        self.last_overview_trace = trace
        return hits, trace

    def overview_evidence(self, event_id: str, preferred: list[str], limit: int):
        candidates = self._evidence(event_id, preferred, max(limit, 8))
        substantial = [line for line in candidates if len(line[2].strip()) >= 10]
        return tuple((substantial or list(candidates))[:limit])

    def source_keys(self, hit: Hit) -> list[str]:
        ordinals = [line[0] for line in hit.evidence]
        if not ordinals:
            return []
        marks = ",".join("?" for _ in ordinals)
        keys = dict(self.db.execute(
            f"SELECT ord,line_key FROM event_evidence WHERE event_id=? AND ord IN ({marks})",
            (hit.event_id, *ordinals)))
        return [keys[index] for index in ordinals if index in keys]

    def expand_context(self, seeds: list[Hit], query: str, *, limit: int = 6) -> list[Hit]:
        paths = expand_events(self.db, [hit.event_id for hit in seeds], self.character)
        self.last_expansion_trace = {"candidates": len(paths), "selected": {}}
        if not paths:
            return []
        query_terms = topic_terms(query, GENERIC_CHARS)
        lexical = self.lexical.scores(query_terms)
        peak = max(lexical.values(), default=1.0) or 1.0
        seed_rank = {hit.event_id: rank for rank, hit in enumerate(seeds)}
        context_terms = terms(" ".join(hit.topic + " " + hit.summary for hit in seeds), GENERIC_CHARS)
        affinity = self.lexical.scores(context_terms)
        affinity_peak = max((affinity.get(event, 0.0) for event in paths), default=1.0) or 1.0
        marks = ",".join("?" for _ in paths)
        rows = self.db.execute(
            "SELECT e.event_id,e.scene_key,e.topic,e.summary,e.narrative_pos,s.anchor,v.channel "
            "FROM events e JOIN scenes s USING(scene_key) JOIN views v USING(event_id) "
            f"WHERE e.event_id IN ({marks}) AND v.character=?", (*paths, self.character)).fetchall()
        ranked = []
        for row in rows:
            if row["channel"] == "unstated":
                continue
            event = row["event_id"]
            path = paths[event]
            strength = (0.30 if path["explicit_with_citations"] else
                        0.22 if path["via"] == "previous_scene" else
                        0.18 if path["via"] not in ("same_scene", "next_scene") else 0.04)
            score = (0.35 / (1 + seed_rank.get(path["seed"], 4)) + strength
                     + 0.10 * lexical.get(event, 0.0) / peak
                     + 0.35 * affinity.get(event, 0.0) / affinity_peak - 0.05 * (path["hop"] - 1))
            ranked.append(Hit(event, row["scene_key"], row["anchor"], row["topic"], row["summary"],
                              row["channel"], score, row["narrative_pos"],
                              self.overview_evidence(event, self._line_keys(event, query_terms), 2)))
        chosen = []
        scenes = defaultdict(int)
        for hit in sorted(ranked, key=lambda h: (-h.score, h.event_id)):
            if scenes[hit.scene_key] >= 3:
                continue
            chosen.append(hit)
            scenes[hit.scene_key] += 1
            self.last_expansion_trace["selected"][hit.event_id] = paths[hit.event_id]
            if len(chosen) >= limit:
                break
        return chosen


def fill(pack: EvidencePack, hits: list[Hit], episode: str | None, budget: int,
         *, total_budget: int | None = None, summary_limit: int | None = None) -> list[Memory]:
    """Add hits within both this fetch's share and the turn's cumulative evidence budget."""
    cap = budget if total_budget is None else total_budget
    added: list[Memory] = []
    for index, hit in enumerate(hits):
        if hit.channel == "unstated" or hit.event_id in pack:
            continue
        lines = list(hit.evidence)
        note = episode if index == 0 and episode else ""
        summary = visible_summary(hit.summary)
        if summary_limit is not None:
            summary = _clip(summary, summary_limit)
        while True:
            item = pack.add(hit.event_id, hit.anchor, hit.channel, summary,
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
                break
    return added


def fill_fact_adaptive(pack: EvidencePack, hits: list[Hit], episode: str | None,
                       budget: int) -> tuple[list[Memory], int]:
    """Widen a crowded initial fact pack while retaining selected source lines."""
    if pack.items or not 900 <= budget < 1200:
        return fill(pack, hits, episode, budget, total_budget=budget), budget
    added = fill(pack, hits, episode, budget, total_budget=budget)
    available = {hit.event_id for hit in hits if hit.channel != "unstated"}
    if len(added) >= len(available):
        return added, budget
    original = pack.items[:]
    pack.items.clear()
    expanded = min(1200, budget + 300)
    compact = fill(pack, hits, None, expanded, total_budget=expanded, summary_limit=220)
    if len(compact) <= len(added):
        pack.items[:] = original
        return added, budget
    return compact, expanded


def rank_reason_hits(hits: list[Hit], topics: tuple[str, ...]) -> list[Hit]:
    """Prefer firsthand statements of purpose while retaining retrieval relevance."""
    def score(hit: Hit) -> float:
        body = hit.topic + " " + hit.summary
        cues = sum(cue in body for cue in RATIONALE_CUES)
        named = sum(name in body for name in topics)
        firsthand = hit.channel in ("experienced", "witnessed", "told", "recalled")
        return 2.0 * min(cues, 4) + 1.5 * min(named, 2) + (1.0 if firsthand else 0.0) + hit.score

    return sorted(hits, key=score, reverse=True)


def fact_search(reader: CanonReader, query: str, *, top_k: int, evidence_lines: int,
                doctor: bool, focus_person: str | None = None) -> tuple[list[Hit], str | None]:
    """Reserve evidence for each explicit part of a Doctor relationship question."""
    relation = doctor and any(term in query for term in ("关系", "联系"))
    self_related = any(term in query for term in (
        "我和", "和我", "我与", "与我", "我跟", "跟我",
        "博士和", "和博士", "博士与", "与博士", "博士跟", "跟博士"))
    names = reader.persons_in(query) if relation and self_related else []
    composite = len(names) == 1
    hits, episode = reader.search(query, top_k=max(top_k, 24) if composite else top_k,
                                  evidence_lines=evidence_lines, doctor=doctor,
                                  focus_person=focus_person, known_only=True)
    phrase = explicit_quote(query)
    quoted = reader.exact_quote_hits(query, phrase, evidence_lines) if phrase and not focus_person else []
    if quoted:
        hits = list(dict((hit.event_id, hit) for hit in [*quoted, *hits]).values())[:top_k]
        episode = None
    if not composite:
        return hits, episode
    relation_query = f"{names[0]}和博士之间的联系"
    related, _ = reader.search(relation_query, top_k=24, evidence_lines=evidence_lines,
                               doctor=doctor, focus_person=focus_person, known_only=True)
    if not related:
        return hits[:top_k], episode
    asks_events = any(term in query for term in ("发生", "经历", "做了", "做过", "遇到"))
    context = reader.expand_context(related[:1], relation_query, limit=1)
    ordered = [*(hits[:1] if asks_events else ()), related[0], *context, *hits, *related]
    chosen = []
    seen = set()
    for hit in ordered:
        if hit.event_id in seen:
            continue
        chosen.append(hit)
        seen.add(hit.event_id)
        if len(chosen) >= max(2, min(3, top_k)):
            break
    return chosen, None


def fill_overview(pack: EvidencePack, hits: list[Hit], budget: int) -> list[Memory]:
    """Fit short event summaries and original lines inside the shared turn budget."""
    added: list[Memory] = []
    for hit in hits:
        if hit.channel == "unstated" or hit.event_id in pack:
            continue
        for summary_limit, line_limit, line_count in ((65, 85, 2), (50, 65, 2),
                                                       (55, 85, 1), (40, 55, 1)):
            summary = _clip(hit.topic + "：" + visible_summary(hit.summary), summary_limit)
            lines = tuple((speaker, _clip(text, line_limit))
                          for _, speaker, text in hit.evidence[:line_count])
            item = pack.add(hit.event_id, hit.anchor, hit.channel, summary, lines)
            if _estimate_tokens(pack.render()) <= budget:
                added.append(item)
                break
            pack.pop()
    return added


def fill_overview_adaptive(pack: EvidencePack, hits: list[Hit], budget: int) -> tuple[list[Memory], int]:
    """Expand a crowded broad evidence pack only when selected known events do not fit."""
    pending = sum(hit.channel != "unstated" and hit.event_id not in pack for hit in hits)
    added = fill_overview(pack, hits, budget)
    if 900 <= budget < 1200 and len(added) < pending:
        budget = min(1200, budget + 300)
        added.extend(fill_overview(pack, hits, budget))
    return added, budget


def _story_source(anchor: str) -> str:
    title = re.search(r"「([^」]+)」", anchor)
    parts = anchor.split(" · ")
    place = " · ".join(parts[-2:]) if len(parts) > 1 else anchor
    return _clip((title.group(1) + " / " if title else "") + place, 36)


def fill_story_adaptive(pack: EvidencePack, hits: list[Hit], budget: int) -> tuple[list[Memory], int]:
    """Fit a source-ordered story outline before spending remaining room on original lines."""
    if pack.items:
        return fill_overview_adaptive(pack, hits, budget)
    cap = min(2400, budget + 1500) if 900 <= budget < 2400 else budget
    outline_cap = min(cap, 1600)
    known = [hit for hit in hits if hit.channel != "unstated"]
    collections = {hit.event_id: hit.anchor.split(" · ")[0] for hit in known}
    order = {collection: rank for rank, collection in enumerate(dict.fromkeys(collections.values()))}
    ordered = sorted(known, key=lambda hit: (order[collections[hit.event_id]], hit.position, hit.event_id))
    for hit in ordered:
        if hit.event_id in pack:
            continue
        summary = _story_source(hit.anchor) + "｜" + _clip(
            hit.topic + "：" + visible_summary(hit.summary), 40)
        pack.add(hit.event_id, hit.anchor, hit.channel, summary, ())
        if _estimate_tokens(pack.render()) > outline_cap:
            pack.pop()
    by_id = {hit.event_id: hit for hit in known}
    priorities = sorted(range(len(pack.items)),
                        key=lambda index: (-by_id[pack.items[index].event_id].score, index))
    blocked: set[str] = set()
    for line_number in (1, 2, 3, 4):
        for index in priorities:
            item = pack.items[index]
            hit = by_id[item.event_id]
            if (item.event_id in blocked or len(hit.evidence) < line_number
                    or len(item.lines) != line_number - 1):
                continue
            _, speaker, body = hit.evidence[line_number - 1]
            trial = replace(item, lines=(*item.lines, (speaker, _clip(body, 95))))
            pack.items[index] = trial
            if _estimate_tokens(pack.render()) > cap:
                pack.items[index] = item
                blocked.add(item.event_id)
    effective = cap if _estimate_tokens(pack.render()) > budget else budget
    return pack.items[:], effective


def overview_tool_result(pack: EvidencePack, added: list[Memory], trace: dict,
                         budget: int) -> str:
    """Return bounded, source-linked tool evidence without claiming complete coverage."""
    while added:
        entries = []
        for item in added:
            keys = trace.get("source_lines", {}).get(item.event_id, ())
            entries.append({
                "ref": item.eid, "event_id": item.event_id,
                "channel": CHANNEL_LABEL.get(item.channel, item.channel),
                "summary": item.summary,
                "lines": [{"line_key": key, "speaker": speaker, "text": body}
                          for key, (speaker, body) in zip(keys, item.lines)],
            })
        result = json.dumps({
            "scope": trace.get("scope"), "coverage": "代表性片段，不能据此断言完整或跨篇章时序",
            "evidence": entries,
        }, ensure_ascii=False, separators=(",", ":"))
        if _estimate_tokens(result) <= budget:
            return result
        if pack.items[-1] is not added[-1]:
            raise RuntimeError("Overview evidence pack changed while rendering a tool result")
        pack.pop()
        added.pop()
    return "没有想起新的相关经历；现有证据可能只覆盖部分情节。"


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
    overview: bool = False
    reason: bool = False
    impression: bool = False
    topics: tuple[str, ...] = ()
    intent: str = "fact"
    corrections: tuple[tuple[str, str], ...] = ()


def plan_turn(reader: CanonReader, query: str, focus: str | None, as_of: str | None,
              context: tuple[str, ...] = ()) -> TurnPlan:
    """Resolve a short follow-up against named topics before choosing evidence."""
    query, corrections = resolve_name(query, getattr(reader, "alias_names", []), reader.entity_type)
    explicit = reader.topic_mentions(query)
    conversational = any(term in query for term in ("刚才我们", "刚才我说", "我刚才说", "你刚才", "刚才你", "为什么这么觉得", "为啥这么觉得", "我一开始", "我最早", "我最开始"))
    prediction = any(term in query for term in ("接下来", "以后会", "将会", "下一步", "未来会"))
    reason = any(marker in query for marker in REASON_MARKERS)
    impression = any(marker in query for marker in (*IMPRESSION_MARKERS, "感受", "最难的", "你觉得"))
    person_pointer = any(marker in query for marker in PERSON_REFERENCES)
    other_pointer = any(marker in query for marker in OTHER_REFERENCES)
    event_pointer = any(marker in query for marker in EVENT_REFERENCES)
    focus_type = reader.entity_type.get(focus) if focus else None
    points_to_focus = (focus and (event_pointer or (person_pointer and focus_type == "person")
                                  or (other_pointer and focus_type != "person")))
    resolved = focus if points_to_focus and focus not in explicit else None
    mentioned = list(dict.fromkeys([*explicit, *([resolved] if resolved else [])]))
    explicit_person = any(reader.entity_type.get(name) == "person" for name in explicit)
    reason_context = ([name for name in context if name not in mentioned][:2]
                      if reason and len(query) <= 30 and not explicit_person else [])
    subjects = tuple(name for name in mentioned if reader.entity_type.get(name) == "person")[:MAX_SUBJECTS]
    past = any(term in query for term in QUERY_PAST)
    overview = (is_overview(query) or (impression and bool(mentioned)) or
                (bool(mentioned) and bool(re.search(r"(?:发生(?:了)?什么(?:事情|事)?|最后怎么样)[了吗呢？?。]*$", query)))) and not any(
        term in query for term in ("那次", "那天", "当时"))
    if conversational:
        lane = "chat"
        overview = False
    elif subjects and (asks_status(query) or as_of) and not prediction:
        lane = "status"
        overview = False
    elif mentioned or past or overview or reason_context:
        lane = "canon"
    else:
        lane = "chat"
    named_people = [name for name in explicit if reader.entity_type.get(name) == "person"]
    next_focus = resolved or (focus if reason_context else None) or (named_people[0] if len(named_people) == 1 else
                              explicit[0] if len(explicit) == 1 else None)
    topics = tuple(dict.fromkeys([*mentioned, *reason_context]))
    additions = [name for name in [resolved, *reason_context] if name and name not in query]
    search_query = " ".join([query, *additions, *(["原因 目的 动机"] if reason and lane == "canon" else [])])
    intent = ("conversation" if conversational else "prediction" if prediction else
              "impression" if impression else "overview" if overview else "reason" if reason else
              "chat" if lane == "chat" else "fact")
    return TurnPlan(lane, subjects, next_focus, search_query,
                    overview=overview, reason=reason, impression=impression, topics=topics,
                    intent=intent, corrections=tuple(corrections.items()))


def needs_motive_rerank(reader: CanonReader, plan: TurnPlan) -> bool:
    """Use purpose ranking only when a question names both sides of a broad relationship."""
    return (plan.reason and not plan.subjects and len(plan.topics) >= 2
            and any(reader.entity_type.get(name) in ("place", "faction", "organization")
                    for name in plan.topics))


def route(reader: CanonReader, plan: TurnPlan, query: str, doctor: bool) -> TurnPlan:
    """A story question without names or time words still reaches canon when retrieval is confident."""
    if plan.lane != "chat" or plan.intent == "conversation" or reader.retrieval is None:
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
        cost = sum(_estimate_tokens(m["content"]) for m in pairs[0])
        if cost <= budget // 4:
            chosen[0] = pairs[0]
            used = cost
    for index in range(len(pairs) - 1, max(-1, len(pairs) - 9), -1):
        if index in chosen:
            continue
        cost = sum(_estimate_tokens(m["content"]) for m in pairs[index])
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
        cost = sum(_estimate_tokens(m["content"]) for m in pairs[index])
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
    reader.last_expansion_trace = {}
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
    pack = EvidencePack("对方（博士）" if args.doctor else "博士", args.doctor)
    turn_budget = args.token_budget
    session.plan, session.pack, session.report = plan, pack, None
    session.tool_queries = []

    def fetch(text: str, focus_person: str | None = None,
              budget: int | None = None, prefer_reason: bool = False,
              adaptive: bool = False) -> list[Memory]:
        nonlocal turn_budget
        hits, episode = fact_search(reader, text,
                                    top_k=max(args.top_k, 12) if prefer_reason else args.top_k,
                                    evidence_lines=args.evidence_lines,
                                    doctor=args.doctor, focus_person=focus_person)
        if prefer_reason:
            hits = rank_reason_hits(hits, plan.topics)[:args.top_k]
            episode = None
        if plan.intent == "reason" and not prefer_reason:
            context = reader.expand_context(hits[:2], text, limit=2)
            known = {hit.event_id for hit in hits}
            hits = [*hits[:2], *(hit for hit in context if hit.event_id not in known), *hits[2:]]
            episode = None
        if adaptive:
            added, turn_budget = fill_fact_adaptive(pack, hits, episode, turn_budget)
            return added
        return fill(pack, hits, episode, turn_budget if budget is None else budget,
                    total_budget=turn_budget)

    def fetch_overview(text: str, budget: int | None = None) -> tuple[list[Memory], dict]:
        nonlocal turn_budget
        hits, trace = reader.overview_search(text, doctor=args.doctor,
                                             evidence_lines=min(4 if is_overview(text) and not plan.impression
                                                                else 2, args.evidence_lines),
                                             personal=plan.impression,
                                             contextual=not plan.impression and not is_overview(text))
        packer = (fill_story_adaptive if not plan.impression and is_overview(text)
                  else fill_overview_adaptive)
        added, turn_budget = packer(pack, hits, turn_budget if budget is None else budget)
        return added, trace

    if plan.overview:
        fetch_overview(plan.search_query)
    elif plan.lane != "chat":
        subjects = plan.subjects if plan.lane == "status" and len(plan.subjects) > 1 else (None,)
        share = turn_budget // len(subjects)
        for subject in subjects:
            fetch(plan.search_query, subject, share,
                  prefer_reason=needs_motive_rerank(reader, plan),
                  adaptive=len(subjects) == 1 and reader.retrieval is not None)
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

    def overview(arguments: dict) -> str:
        wanted = str(arguments.get("query", "")).strip()[:100]
        session.tool_queries.append(f"综述「{wanted or '空'}」")
        if not wanted:
            return "没有指定要综述的经历。"
        added, trace = fetch_overview(wanted)
        return overview_tool_result(pack, added, trace, turn_budget)

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
            fits = _estimate_tokens(pack.render()) <= turn_budget
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
        return [{"role": "system", "content": system}, *session.active_history,
                {"role": "user", "content": query}]

    def refetch(names: list[str]) -> int:
        known = reader.topic_mentions(pack.render())
        identity_hits = [reader.identity_hit(name, prior) for name in names for prior in known]
        linked = fill(pack, [hit for hit in identity_hits if hit], None,
                      turn_budget, total_budget=turn_budget)
        return len(linked) + len(fetch(" ".join(names)))

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
    tool_offer = session.tools and _estimate_tokens(pack.render()) + 80 < turn_budget
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
                       "history_tokens": sum(_estimate_tokens(m["content"]) for m in session.active_history),
                       "evidence_tokens": _estimate_tokens(pack.render()),
                       "evidence_budget": turn_budget,
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
