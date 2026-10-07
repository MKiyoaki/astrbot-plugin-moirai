"""Read-only canon database access with lexical, alias and scene indexes built once in memory."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from . import retrieval as retrieval_settings
from ..domain.character import profile_for
from .lexical import BigramIndex
from .packing import Hit
from .query import explicit_quote
from ..constant_utils import PREDICATES
from .retrieval import speaker_view
from ..domain.temporal import resolve
from ...utils.text_utils import is_cjk
from .mixins.archive import ArchiveMixin
from .mixins.lexical_search import LexicalSearchMixin
from .mixins.overview_search import OverviewMixin
from .mixins.time_index import TimeIndexMixin
from .reader_support import matches_alias


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


class CanonReader(TimeIndexMixin, ArchiveMixin, LexicalSearchMixin, OverviewMixin):
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
        self._index_anchors()
        rows = [row for row in rows if len(row["alias"]) > 1 or not is_cjk(row["alias"])
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
        self.story_events: set[str] = set()
        self.past_events: set[str] = set()
        for row in self.db.execute(
                "SELECT e.event_id,e.scene_key,e.topic,e.summary,e.participants,e.narrative_pos,e.involves_doctor,e.ord,"
                "e.in_world_time,s.chapter_no FROM events e JOIN views v ON v.event_id=e.event_id "
                "JOIN scenes s ON s.scene_key=e.scene_key WHERE v.character=?", (self.character,)):
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
            if row["chapter_no"] is not None and row["in_world_time"] != "past":
                self.story_events.add(event_id)
            if row["in_world_time"] == "past":
                self.past_events.add(event_id)
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


    def sequence(self, event_ids: list[str]) -> tuple[list[str], list[str]]:
        """Events whose order is certain as one chain, and the rest.

        Main-story events outside recollection keep the story's own order. Any other event joins the chain only
        where its directly dated interval clears both neighbours; an inherited date, or none, leaves it unordered.
        """
        ids = list(dict.fromkeys(event for event in event_ids if event in self.position))
        chain = sorted((event for event in ids if event in self.story_events),
                       key=lambda event: (self.position[event], self.event_order.get(event, 0)))
        rest = []
        for event in sorted((event for event in ids if event not in self.story_events),
                            key=lambda event: (self.spans.get(event, (float("inf"),))[0], self.position[event],
                                               self.event_order.get(event, 0))):
            slot = next((index for index in range(len(chain) + 1) if event in self.spans
                         and (index == 0 or self._before(chain[index - 1], event))
                         and (index == len(chain) or self._before(event, chain[index]))), None)
            if slot is None:
                rest.append(event)
            else:
                chain.insert(slot, event)
        return chain, rest

    def known_set(self) -> set[str]:
        """Events she knows, reports included: the set every injection path shares."""
        if getattr(self, "_known", None) is None:
            self._known = {row[0] for row in self.db.execute(
                f"SELECT event_id FROM {self.views} WHERE character=? AND channel!='unstated'", (self.character,))}
        return self._known

    def causal_links(self, event_ids: list[str]) -> set[tuple[str, str]]:
        """Cause and motivation edges the source states outright and cites; inferred edges license nothing."""
        ids = list(dict.fromkeys(event_ids))
        if len(ids) < 2:
            return set()
        marks = ",".join("?" for _ in ids)
        rows = self.db.execute(
            f"SELECT src,dst,evidence FROM edges WHERE explicit=1 AND type IN ('cause','motivation') "
            f"AND src IN ({marks}) AND dst IN ({marks})", (*ids, *ids)).fetchall()
        return {(row["src"], row["dst"]) for row in rows if json.loads(row["evidence"] or "[]")}

    def scene_run(self, anchor: str, *, before: int, after: int) -> list[str]:
        """The anchor's scene neighbours she knows, in scene order: the incident a recount retells."""
        known = self.known_set()
        scene = self.events_by_scene.get(self.event_scene.get(anchor, ""), [])
        ordered = sorted(scene, key=lambda event: self.event_order.get(event, 0))
        if anchor not in ordered:
            return [anchor]
        at = ordered.index(anchor)
        usable = lambda event: event not in self.past_events and event in known
        earlier = [event for event in reversed(ordered[:at]) if usable(event)][:before]
        later = [event for event in ordered[at + 1:] if usable(event)][:after]
        return [*reversed(earlier), anchor, *later]


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
            for start, end in matches_alias(text, alias):
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


    def source_keys(self, hit: Hit) -> list[str]:
        ordinals = [line[0] for line in hit.evidence]
        if not ordinals:
            return []
        marks = ",".join("?" for _ in ordinals)
        keys = dict(self.db.execute(
            f"SELECT ord,line_key FROM event_evidence WHERE event_id=? AND ord IN ({marks})",
            (hit.event_id, *ordinals)))
        return [keys[index] for index in ordinals if index in keys]


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
