"""Bounded structural navigation to source events without asserting inferred relations."""

from __future__ import annotations

from collections import defaultdict
import json
import sqlite3


def expand_events(db: sqlite3.Connection, seeds: list[str], character: str,
                  *, max_hops: int = 2, limit: int = 48) -> dict[str, dict]:
    """Return navigation provenance; adjacency and extracted edges are never factual evidence."""
    if limit <= 0 or max_hops <= 0:
        return {}
    found = {}
    seeds = list(dict.fromkeys(seeds))[:4]
    frontier = [(event, [event]) for event in seeds]
    visited = set(seeds)
    for hop in range(1, min(2, max_hops) + 1):
        next_frontier = []
        for origin, path in frontier[:8]:
            row = db.execute(
                "SELECT e.scene_key,s.prev_scene_key,s.collection_id FROM events e "
                "JOIN scenes s USING(scene_key) WHERE e.event_id=?", (origin,)).fetchone()
            if row is None:
                continue
            scene, previous, collection = row
            linked = db.execute(
                "SELECT src,dst,type,explicit,evidence FROM edges WHERE src=? OR dst=? "
                "ORDER BY explicit DESC,confidence DESC,src,dst LIMIT 12", (origin, origin)).fetchall()
            candidates = []
            for src, dst, kind, explicit, evidence in linked:
                target = dst if src == origin else src
                try:
                    cited = json.loads(evidence)
                except (ValueError, TypeError):
                    cited = []
                candidates.append((target, kind, bool(explicit and cited)))
            neighbours = [scene]
            if previous:
                neighbours.append(previous)
            neighbours.extend(r[0] for r in db.execute(
                "SELECT scene_key FROM scenes WHERE prev_scene_key=? ORDER BY scene_key LIMIT 2", (scene,)))
            for neighbour in neighbours:
                events = db.execute(
                    "SELECT e.event_id FROM events e JOIN scenes s USING(scene_key) "
                    "WHERE e.scene_key=? AND s.collection_id IS ? ORDER BY e.ord LIMIT 24",
                    (neighbour, collection)).fetchall()
                for event, in events:
                    candidates.append((event, "same_scene" if neighbour == scene else "previous_scene" if neighbour == previous else "next_scene", False))
            for target, kind, explicit in candidates:
                if target in visited:
                    continue
                channel = db.execute("SELECT channel FROM views WHERE event_id=? AND character=?",
                                     (target, character)).fetchone()
                if channel is None:
                    continue
                visited.add(target)
                route = [*path, target]
                found[target] = {"seed": path[0], "path": route, "hop": hop,
                                 "via": kind, "explicit_with_citations": explicit}
                if kind != "same_scene":
                    next_frontier.append((target, route))
        grouped = defaultdict(list)
        for target, path in next_frontier:
            scene = db.execute("SELECT scene_key FROM events WHERE event_id=?", (target,)).fetchone()[0]
            grouped[scene].append((target, path))
        frontier = [values[0] for values in grouped.values()]
    buckets = defaultdict(list)
    for event, trace in found.items():
        buckets[(trace["seed"], trace["hop"], trace["via"])].append((event, trace))
    selected = {}
    while buckets and len(selected) < limit:
        for key in list(buckets):
            event, trace = buckets[key].pop(0)
            selected[event] = trace
            if not buckets[key]:
                del buckets[key]
            if len(selected) >= limit:
                break
    return selected


def resolve_name(query: str, aliases: list[tuple[str, str]], entity_types: dict[str, str]) -> tuple[str, dict]:
    """Correct a unique single substitution in a long name; never alter stored entity identity."""
    candidates = defaultdict(set)
    exact = [(query.find(alias), query.find(alias) + len(alias)) for alias, _ in aliases if alias in query]
    for alias, name in aliases:
        if entity_types.get(name) != "person" or not 4 <= len(alias) <= 12 or not alias.isalpha():
            continue
        for start in range(len(query) - len(alias) + 1):
            end = start + len(alias)
            if any(start < right and left < end for left, right in exact):
                continue
            fragment = query[start:end]
            if (fragment[0] == alias[0] and fragment[-1] == alias[-1]
                    and sum(a != b for a, b in zip(fragment, alias)) == 1):
                candidates[(start, end, fragment)].add(name)
    replacements = {}
    for (start, end, fragment), names in candidates.items():
        if len(names) == 1:
            replacements[(start, end)] = (fragment, next(iter(names)))
    if len(replacements) != 1:
        return query, {}
    (start, end), (fragment, name) = next(iter(replacements.items()))
    return query[:start] + name + query[end:], {fragment: name}
