"""Read-only canon database access with lexical, alias and scene indexes built once in memory."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import replace
from itertools import zip_longest
from pathlib import Path

from . import retrieval as retrieval_settings
from .character import profile_for
from .context import expand_events
from .lexical import BigramIndex, terms
from .overview import (OVERVIEW_MAX_CANDIDATES, OVERVIEW_MAX_EVENTS, OVERVIEW_MAX_SCENES, STORY_MAX_EVENTS,
                       OverviewCandidate, is_overview, select_events, topic_terms)
from .packing import Hit, clip
from .query import GENERIC_CHARS, QUERY_PAST, explicit_quote
from .retrieval import fuse, speaker_view
from .temporal import PREDICATES, resolve


LEXICAL_NOISE = ("还记得", "那一次", "那时候", "那次", "那天", "那时", "那场", "当时", "上次", "后来",
                 "为什么", "是什么", "是谁", "什么", "怎么", "知道", "是不是")
LEXICAL_LIMIT = 50
ENTITY_LIMIT = 60
PER_SCENE = 3
SINGLE_LEFT = frozenset("和跟与被让叫问找给对向同帮见把替等陪救及或是说像连带请看喊")
SINGLE_RIGHT = frozenset("第被和跟与的是在说也都就还又为把让给对向从同去来呢吗吧啊呀了着过当之他她那这会能要有没不怎以讲问叫救帮打做看找见一")
_CJK = re.compile(r"[一-鿿]+")
_LATIN = re.compile(r"^[A-Za-z0-9'.-]+$")
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
    return ((not left or not _CJK.fullmatch(left) or left in SINGLE_LEFT)
            and (not right or not _CJK.fullmatch(right) or right in SINGLE_RIGHT))



def _own_question(row: sqlite3.Row, name: str) -> bool:
    return row["speaker"] == name and row["text"].rstrip("…—.。 ").endswith(("？", "?"))


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


RECENT_MONTHS = 1


def _month(key: float) -> int:
    return int(key // 10000) * 12 + int(key // 100 % 100)


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
        self.profile = profile_for(character)
        self.retrieval = retrieval
        self.reported = self._reported() if self.profile.report_knowledge else None
        self.views = "views" if self.reported is None else (
            "(SELECT character,event_id,CASE WHEN channel='unstated' AND event_id IN "
            f"(SELECT event_id FROM view_access a WHERE a.character=views.character AND ({self.profile.report_sql()})) "
            "THEN 'reported' ELSE channel END AS channel FROM views)")
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
        self._index_times()
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

    def _reported(self) -> dict[str, tuple[str, frozenset[str]]] | None:
        """Unstated events that reached her through a report; she knows only the reported content and lines."""
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='view_access'").fetchone() is None:
            return None
        reported: dict[str, tuple[str, frozenset[str]]] = {}
        for row in self.db.execute(
                "SELECT a.event_id,a.content,a.evidence FROM view_access a JOIN views v "
                "ON v.event_id=a.event_id AND v.character=a.character "
                f"WHERE a.character=? AND v.channel='unstated' AND ({self.profile.report_sql()}) ORDER BY a.event_id,a.ord",
                (self.character,)):
            content, keys = reported.get(row["event_id"], ("", frozenset()))
            reported[row["event_id"]] = ("；".join(filter(None, (content, row["content"]))),
                                         keys | frozenset(json.loads(row["evidence"])))
        return reported

    def _summary(self, event_id: str, summary: str) -> str:
        return self.reported[event_id][0] if self.reported and event_id in self.reported else summary

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
            )).replace(self.profile.player_placeholder, self.profile.player).replace(self.profile.player_token, self.profile.player)
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

    def _index_times(self) -> None:
        """World-calendar labels per event; "now" is the latest main-story time she knows."""
        self.times: dict[str, tuple[float, str]] = {}
        self.recounted: set[str] = set()
        self.now: tuple[float, str] | None = None
        self.now_precision = ""
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_times'").fetchone() is None:
            return
        self.times = {row["event_id"]: (row["sort_key"], row["label"])
                      for row in self.db.execute("SELECT event_id,sort_key,label FROM event_times")}
        if not self.times:
            return
        self.recounted = {row["event_id"] for row in self.db.execute(
            "SELECT event_id FROM events WHERE in_world_time='past'")} - self.times.keys()
        row = self.db.execute(
            "SELECT t.sort_key,t.label,t.precision FROM event_times t JOIN events e ON e.event_id=t.event_id "
            f"JOIN scenes s ON s.scene_key=e.scene_key JOIN {self.views} v ON v.event_id=t.event_id "
            "WHERE v.character=? AND v.channel!='unstated' AND s.chapter_no IS NOT NULL "
            "ORDER BY t.sort_key DESC LIMIT 1", (self.character,)).fetchone()
        self.now = (row["sort_key"], row["label"]) if row else None
        self.now_precision = row["precision"] if row else ""

    def is_recent(self, event_id: str) -> bool:
        """Dated in the current stretch, the only evidence that may speak for the present.

        The stretch is the month of "now" and the month before; a season-precise "now" reaches two months back,
        and a year-precise one covers its year.
        """
        if not self.now or event_id not in self.times:
            return False
        key, now = self.times[event_id][0], self.now[0]
        if self.now_precision in ("year", "span", "era"):
            return int(key // 10000) == int(now // 10000)
        reach = 2 if self.now_precision == "season" else RECENT_MONTHS
        return key <= now and _month(key) >= _month(now) - reach

    def time_label(self, event_id: str) -> str:
        if event_id in self.times:
            return self.times[event_id][1]
        return "往事" if event_id in self.recounted else ""

    def hit(self, event_id: str, evidence_lines: int, prefer: str = "") -> Hit | None:
        row = self.db.execute(
            "SELECT e.scene_key,e.topic,e.summary,e.narrative_pos,s.anchor,v.channel "
            "FROM events e JOIN scenes s ON s.scene_key=e.scene_key "
            f"JOIN {self.views} v ON v.event_id=e.event_id WHERE e.event_id=? AND v.character=?",
            (event_id, self.character)).fetchone()
        if row is None:
            return None
        preferred = [key for key, text in self.event_lines[event_id] if prefer and prefer in text]
        return Hit(event_id, row["scene_key"], row["anchor"], row["topic"], self._summary(event_id, row["summary"]),
                   row["channel"], 1.0, row["narrative_pos"], self._evidence(event_id, preferred, evidence_lines))

    def close(self) -> None:
        self.db.close()

    def persons_in(self, query: str) -> list[str]:
        return [name for name in self.entities_in(query) if self.entity_type.get(name) == "person"]

    def topic_mentions(self, query: str) -> list[str]:
        return list(dict.fromkeys(name for _, _, name in self._spans(query) if name not in self.profile.self_names))

    def _spans(self, text: str) -> list[tuple[int, int, str]]:
        occupied: list[tuple[int, int, str]] = []
        for alias, name in self.alias_names:
            for start, end in _matches_alias(text, alias):
                if any(start < right and left < end for left, right, _ in occupied):
                    continue
                occupied.append((start, end, name))
        return sorted(occupied)

    def entities_in(self, text: str) -> list[str]:
        names = [name for _, _, name in self._spans(text) if name not in self.profile.self_names | {self.profile.home}]
        return list(dict.fromkeys(names))

    def identity_hit(self, first: str, second: str) -> Hit | None:
        event_id = self.identity_events.get(frozenset((first, second)))
        if event_id is None:
            return None
        row = self.db.execute(
            "SELECT e.scene_key,e.topic,e.summary,e.narrative_pos,s.anchor,v.channel "
            "FROM events e JOIN scenes s ON s.scene_key=e.scene_key "
            f"JOIN {self.views} v ON v.event_id=e.event_id WHERE e.event_id=? AND v.character=?",
            (event_id, self.character),
        ).fetchone()
        if row is None:
            return None
        preferred = [key for key, text in self.event_lines[event_id]
                     if text.startswith(first + "：") or text.startswith(second + "：")
                     or first in text or second in text]
        return Hit(event_id, row["scene_key"], row["anchor"], row["topic"], self._summary(event_id, row["summary"]),
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
        return speaker_view(query, self.profile) if doctor and retrieval_settings.SPEAKER_VIEW else query

    def without_self(self, text: str) -> str:
        """Her own and the Doctor's names match nearly every event, so they never steer retrieval."""
        for start, end, name in reversed(self._spans(text)):
            if name in self.profile.self_names:
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
                        f"  证据 {ev['line_key']}（{self.profile.name}渠道 {channel}）：{ev['text'][:100]}"
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
        if self.reported and event_id in self.reported:
            rows = [row for row in rows if row["line_key"] in self.reported[event_id][1]]
        by_key = {row["line_key"]: row for row in rows}
        beats = [json.loads(row["evidence"]) for row in self.db.execute(
            "SELECT evidence FROM event_beats WHERE event_id=? ORDER BY ord", (event_id,))]
        spread = [key for depth in zip_longest(*beats) for key in depth if key]
        ordered = [key for key in dict.fromkeys([*preferred, *spread]) if key in by_key]
        rest = sorted(
            (row for row in rows if row["line_key"] not in ordered),
            key=lambda row: (_own_question(row, self.profile.name), row["speaker"] != self.profile.name, row["ord"]),
        )
        ordered.extend(row["line_key"] for row in rest)
        return tuple(
            (by_key[key]["ord"], by_key[key]["speaker"] or "旁白", clip(by_key[key]["text"], 160))
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
            f"JOIN {self.views} v ON v.event_id=e.event_id "
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
                topic=row["topic"], summary=self._summary(row["event_id"], row["summary"]), channel=row["channel"],
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
            f"JOIN {self.views} v ON v.event_id=e.event_id "
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
                    self._summary(row["event_id"], row["summary"]), row["channel"], 1.0, row["narrative_pos"],
                    self._evidence(row["event_id"], matching[row["event_id"]], evidence_lines))
                for row in rows[:3]]

    def overview_search(self, query: str, *, doctor: bool, evidence_lines: int = 1,
                        personal: bool = False, contextual: bool = False,
                        story: bool | None = None) -> tuple[list[Hit], dict]:
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
            f"JOIN {self.views} v ON v.event_id=e.event_id "
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
                phase, self._summary(row["event_id"], self.event_documents[row["event_id"]])[:300]))
            by_id[row["event_id"]] = row
        story = (not personal and not contextual and is_overview(query)) if story is None else story
        limit = STORY_MAX_EVENTS if story else OVERVIEW_MAX_EVENTS
        selected = select_events(candidates, limit=limit, pinned_collection=pinned)
        hits = []
        source_lines = {}
        for event_id in selected:
            row = by_id[event_id]
            evidence = self.overview_evidence(event_id, [], evidence_lines)
            hits.append(Hit(event_id, row["scene_key"], row["anchor"], row["topic"],
                            self._summary(event_id, row["summary"]), row["channel"], relevance(event_id),
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
            f"FROM events e JOIN scenes s USING(scene_key) JOIN {self.views} v USING(event_id) "
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
            ranked.append(Hit(event, row["scene_key"], row["anchor"], row["topic"], self._summary(event, row["summary"]),
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


def fact_search(reader: CanonReader, query: str, *, top_k: int, evidence_lines: int,
                doctor: bool, focus_person: str | None = None) -> tuple[list[Hit], str | None]:
    """Reserve evidence for each explicit part of a Doctor relationship question."""
    relation = doctor and any(term in query for term in ("关系", "联系"))
    player = reader.profile.player
    self_related = any(term in query for term in (
        "我和", "和我", "我与", "与我", "我跟", "跟我",
        f"{player}和", f"和{player}", f"{player}与", f"与{player}", f"{player}跟", f"跟{player}"))
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
    relation_query = f"{names[0]}和{player}之间的联系"
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
