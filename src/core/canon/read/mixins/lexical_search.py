"""词法检索：词项、原文行、实体与节拍的命中，合并成按场景限额的证据。"""
from __future__ import annotations

import json
import sqlite3

from collections import defaultdict
from itertools import zip_longest
from ...constant_utils import GENERIC_CHARS, LEXICAL_NOISE, QUERY_PAST
from ..lexical import terms
from ..packing import Hit, clip
from ..retrieval import fuse
from ..reader_support import ENTITY_LIMIT, LEXICAL_LIMIT, PER_SCENE, matches_alias


def _own_question(row: sqlite3.Row, name: str) -> bool:
    return row["speaker"] == name and row["text"].rstrip("…—.。 ").endswith(("？", "?"))


class LexicalSearchMixin:
    """词法检索：词项、原文行、实体与节拍的命中，合并成按场景限额的证据。"""

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
            for start, end in matches_alias(query, alias):
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
