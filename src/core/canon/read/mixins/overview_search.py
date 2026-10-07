"""概览检索：宽泛问题的事件挑选、概览证据和围绕种子事件的上下文扩展。"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from ...constant_utils import GENERIC_CHARS
from ..context import expand_events
from ..lexical import terms
from ..overview import OVERVIEW_MAX_CANDIDATES, OVERVIEW_MAX_EVENTS, OVERVIEW_MAX_SCENES, OverviewCandidate, STORY_MAX_EVENTS, is_overview, select_events, topic_terms
from ..packing import Hit


class OverviewMixin:
    """概览检索：宽泛问题的事件挑选、概览证据和围绕种子事件的上下文扩展。"""

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
