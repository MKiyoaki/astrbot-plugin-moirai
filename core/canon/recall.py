"""Model-directed canon recall: a cheap scope probe and path-chosen recall under one turn budget.

The model decides whether a turn needs recall at all, how deep to go and which path fits; this module
only retrieves deterministically. Every recall in a turn draws on one evidence budget, which never widens
on its own, so the budget is a real upper bound on the source text the model reads.
"""
from __future__ import annotations

import re
from collections import Counter

from .assembly import EvidenceAssembler, EvidenceSettings
from .gateway import EvidencePack, Memory
from .packing import (estimate_tokens, fill, fill_overview, fill_story_adaptive, overview_tool_result,
                      rank_reason_hits)
from .query import TurnPlan
from .reader import CanonReader, fact_search

PATHS = ("event", "reason", "impression", "arc", "latest", "timeline", "recent")
TURN_BUDGET = 2000
VERIFY_EXTRA = 400
DEEP_NOTE = "（这是一段需要梳理的经过：这一轮不受三句的限制，用一段话讲清主要经过，约 150–300 字，不逐条复述。）"
CAUSAL_NOTE = ("（这是一段前因后果：这一轮不受三句的限制，用一段话按先后讲清，约 150–300 字：先说起点，"
               "再说两三个关键转折，最后说结果；只挑必要的事，不逐条复述。两件事之间的因果没有原话依据时，说成你自己的判断。）")
DEPTHS = ("light", "deep")
PROBE_NAMES = 3
PROBE_COLLECTIONS = 3
AXIS_ROWS = 8
AXIS_TOPICS = 2
AXIS_NEIGHBOURS = 2
RECENT_ROWS = 6
RECENT_EVENTS = 3
AXIS_MARK = {"reported": "（汇报）", "told": "（听说）"}

PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "canon_probe",
        "description": "只在不确定该回忆哪个人物、地点、组织或篇章时调用。返回问题里点到的范围、你知情的事件数和主要出现的篇章，"
                       "不含原文，消耗很少。范围明确时直接调用 canon_recall。",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "结合上下文改写后的完整问题"}},
            "required": ["query"],
        },
    },
}
def now_phrase(label: str) -> str:
    """A day-precise "now" read as early, middle or late in its month."""
    match = re.fullmatch(r"(.+?年\d+月)(\d+)日", label or "")
    if not match:
        return label or ""
    day = int(match.group(2))
    return match.group(1) + ("上旬" if day <= 10 else "中旬" if day <= 20 else "下旬")


def recall_tool(now: str = "") -> dict:
    """The recall tool; when the canon carries a calendar, it states the present so time words have an anchor."""
    description = ("回忆原作里你知道的事。闲聊、日常、此刻的感受和回应不需要调用。"
                   "path：event＝某次具体经过或细节；reason＝某件事的原因或动机；impression＝你对某人某组织的看法；"
                   "arc＝某个人物、地点、组织或篇章的一段经历；latest＝某人你最后知道的情况。")
    if now:
        description += ("timeline＝把某件事放到时间轴上，看它在什么时候、前后接着哪些经历；"
                        f"recent＝到现在为止最近的几段经历，不针对某个人。现在大约是{now}。")
    description += "depth：light＝一两件事就能答（默认，消耗少）；deep＝需要梳理多次事件、前因后果时才用。"
    return {
        "type": "function",
        "function": {
            "name": "canon_recall",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "凝练后可以独立理解的回忆内容，写清人物、地点和要找的事"},
                    "path": {"type": "string", "enum": list(PATHS if now else PATHS[:5])},
                    "subject": {"type": "string", "description": "主要人物、地点或组织的名字，只写一个名字，不要写篇章名或几个词；不确定就留空"},
                    "depth": {"type": "string", "enum": list(DEPTHS)},
                },
                "required": ["query", "path"],
            },
        },
    }


class CanonRecall:
    """One turn's recall state: the shared evidence pack, its budget and a log of what the model asked for."""

    def __init__(self, reader: CanonReader, settings: EvidenceSettings) -> None:
        self.reader, self.settings = reader, settings
        self.evidence = EvidenceAssembler(reader, TurnPlan("canon", (), None, ""), settings)
        self.log: list[dict] = []
        self._entity_ids: dict[str, int] | None = None
        self._known: set[str] | None = None
        self._axis: list[dict] | None = None

    @property
    def pack(self) -> EvidencePack:
        return self.evidence.pack

    def used(self) -> int:
        return estimate_tokens(self.pack.render()) if self.pack.items else 0

    def remaining(self) -> int:
        return max(0, self.settings.token_budget - self.used())

    def known_events(self) -> set[str]:
        if self._known is None:
            self._known = {row[0] for row in self.reader.db.execute(
                f"SELECT event_id FROM {self.reader.views} WHERE character=? AND channel!='unstated'",
                (self.reader.character,))}
        return self._known

    def entity_ids(self) -> dict[str, int]:
        if self._entity_ids is None:
            by_alias = dict(self.reader.aliases)
            self._entity_ids = {name: by_alias[alias] for alias, name in self.reader.alias_names
                                if alias in by_alias}
        return self._entity_ids

    def probe(self, query: str) -> str:
        reader, known = self.reader, self.known_events()
        lines = []
        for name in reader.entities_in(query)[:PROBE_NAMES]:
            name, events = max(((candidate, reader.entity_events.get(self.entity_ids().get(candidate, -1), set()))
                                for candidate in self._variants(name)),
                               key=lambda item: sum(event in known for event in item[1]))
            mine = [event for event in events if event in known]
            places = Counter(reader.scene_meta[reader.event_scene[event]].get("collection_name") or "其他"
                             for event in mine if event in reader.event_scene)
            where = "、".join(f"{title}（{count}）" for title, count in places.most_common(PROBE_COLLECTIONS))
            kind = {"person": "人物", "place": "地点", "faction": "组织"}.get(reader.entity_type.get(name, ""), "名称")
            lines.append(f"{kind} {name}：你知情的事件 {len(mine)}/{len(events)}" + (f"，主要在 {where}" if where else ""))
        titles = [title for title in reader.titles if title in query]
        lines += [f"篇章 「{title}」" for title in titles[:PROBE_COLLECTIONS]]
        self.log.append({"tool": "canon_probe", "query": query[:120], "matches": len(lines)})
        if not lines:
            return "没有点到明确的人物、地点、组织或篇章；需要具体事实时用 event 按原话回忆，闲聊不必回忆。"
        return "[范围]\n" + "\n".join(lines)

    def _variants(self, name: str) -> list[str]:
        """A mention such as 某某医生 may be its own entity; the shorter contained name often holds the events."""
        return [name, *(other for other in self.entity_ids() if 2 <= len(other) < len(name) and other in name)]

    def recall(self, query: str, path: str = "event", subject: str = "", depth: str = "light") -> str:
        query, subject = query.strip()[:120], subject.strip()[:20]
        path = path if path in PATHS else "event"
        deep = depth == "deep"
        room = self.remaining()
        entry = {"tool": "canon_recall", "query": query, "path": path, "subject": subject,
                 "depth": "deep" if deep else "light", "tokens_before": self.used()}
        self.log.append(entry)
        if not query and not subject:
            return "没有指定要回忆的内容。"
        if room <= 0:
            return "这一轮能想起的内容已经到上限；只根据上面已有的记忆回答，没有的就说记不清。"
        if deep or path == "reason":
            self.pack.ordered = True
        share = room
        cap = self.used() + share
        added, body = self._fetch(query or subject, path, subject, deep, share, cap)
        entry.update(added=len(added), tokens_after=self.used())
        if not added:
            if self.pack.items:
                return "没有想起新的相关的事；只根据上面已有的记忆回答，没有的就说记不清。"
            return ("没有想起相关的事。可以换一个更具体的人物、地点或组织的名字，或者不填 subject 再回忆一次；"
                    "仍然想不起来就说记不清。")
        note = CAUSAL_NOTE if deep and path == "reason" else DEEP_NOTE if deep else ""
        return "\n".join(part for part in (note, body, self.pack.order_note()) if part)

    def _focus(self, subject: str) -> str | None:
        """Only a known entity name narrows a search; any other text is left to the query itself."""
        return subject if subject in self.reader.entity_type else None

    def _fetch(self, text: str, path: str, subject: str, deep: bool, share: int,
               cap: int) -> tuple[list[Memory], str]:
        reader, settings, pack = self.reader, self.settings, self.pack
        focus = self._focus(subject)
        if path in ("arc", "impression"):
            hits, trace = reader.overview_search(
                text, doctor=settings.doctor, evidence_lines=min(4 if path == "arc" else 2, settings.evidence_lines),
                personal=path == "impression", story=path == "arc" and deep)
            if path == "arc" and deep and not pack.items:
                added, _ = fill_story_adaptive(pack, hits, cap, widen=False)
            else:
                added = fill_overview(pack, hits, cap)
            return added, overview_tool_result(pack, added, trace, cap) if added else ""
        if path == "latest" and (hits := self._latest_of(subject)):
            added = fill(pack, hits, None, share, total_budget=cap)
            return added, pack.render(added)
        if path == "latest":
            hits, _ = reader.search(subject if focus else text, top_k=24, evidence_lines=settings.evidence_lines,
                                    doctor=settings.doctor, focus_person=focus, known_only=True)
            hits = sorted(hits, key=lambda hit: (reader.times.get(hit.event_id, (float("-inf"),))[0], hit.position),
                          reverse=True)[:settings.top_k]
            added = fill(pack, hits, None, share, total_budget=cap)
            return added, pack.render(added)
        if path in ("timeline", "recent") and reader.now:
            return self._timeline(text, subject, share, cap, recent=path == "recent")
        reason = path == "reason"
        hits, episode = fact_search(reader, text, top_k=max(settings.top_k, 12) if reason else settings.top_k,
                                    evidence_lines=settings.evidence_lines, doctor=settings.doctor,
                                    focus_person=focus)
        if reason:
            hits, episode = rank_reason_hits(hits, (subject,) if subject else ())[:settings.top_k], None
        if deep and hits:
            seen = {hit.event_id for hit in hits}
            context = [hit for hit in reader.expand_context(hits[:2], text, limit=3) if hit.event_id not in seen]
            hits = [*hits[:2], *context, *hits[2:]]
        added = fill(pack, hits, episode, share, total_budget=cap)
        return added, pack.render(added)

    def _latest_of(self, subject: str) -> list:
        """A named subject's newest known, dated events up to now, taken from its entity links."""
        reader, settings = self.reader, self.settings
        names = reader.entities_in(subject) if subject and reader.now else []
        if not names:
            return []
        ids, known, now = self.entity_ids(), self.known_events(), reader.now[0]
        name = max(self._variants(names[0]),
                   key=lambda candidate: len(reader.entity_events.get(ids.get(candidate, -1), set()) & known))
        events = [event for event in reader.entity_events.get(ids.get(name, -1), ())
                  if event in known and event in reader.times and reader.times[event][0] <= now]
        events.sort(key=lambda event: (reader.times[event][0], reader.position.get(event, 0)), reverse=True)
        return [hit for hit in (reader.hit(event, settings.evidence_lines, prefer=name)
                                for event in events[:settings.top_k]) if hit]

    def axis(self) -> list[dict]:
        """Her known, dated events up to now, grouped by story and month and ordered by world time."""
        if self._axis is None:
            reader = self.reader
            now = reader.now[0] if reader.now else float("inf")
            groups: dict[tuple[str, int], dict] = {}
            for row in reader.db.execute(
                    "SELECT e.event_id,e.topic,e.narrative_pos,s.collection_name,v.channel FROM events e "
                    f"JOIN scenes s ON s.scene_key=e.scene_key JOIN {reader.views} v ON v.event_id=e.event_id "
                    "WHERE v.character=? AND v.channel!='unstated'", (reader.character,)):
                key, label = reader.times.get(row["event_id"], (None, ""))
                if key is None or key > now:
                    continue
                group = groups.setdefault((row["collection_name"] or "", int(key // 100)), {
                    "story": row["collection_name"] or "", "labels": Counter(), "events": []})
                group["labels"][re.sub(r"\d+日$", "", label)] += 1
                group["events"].append((key, row["narrative_pos"], row["event_id"], row["topic"], row["channel"]))
            for group in groups.values():
                group["events"].sort()
                group["label"] = max(group["labels"], key=lambda label: (group["labels"][label], label.endswith("月")))
                middle = group["events"][len(group["events"]) // 2]
                group["order"] = (middle[0], min(event[1] for event in group["events"]))
            self._axis = sorted(groups.values(), key=lambda group: group["order"])
        return self._axis

    def _row(self, group: dict, anchors: set[str] = frozenset()) -> str:
        rank = {"experienced": 0, "witnessed": 1, "recalled": 2, "told": 3, "reported": 4}
        chosen = sorted(group["events"], key=lambda event: (event[2] not in anchors, rank.get(event[4], 5), event[:2]))
        topics = "；".join(f"{topic}{AXIS_MARK.get(channel, '')}"
                          for _, _, _, topic, channel in sorted(chosen[:AXIS_TOPICS]))
        mark = "→ " if anchors & {event[2] for event in group["events"]} else "· "
        return f"{mark}{group['label']} " + (f"{group['story']}：" if group["story"] else "") + topics

    def _timeline(self, text: str, subject: str, share: int, cap: int, *, recent: bool) -> tuple[list[Memory], str]:
        reader, settings, pack, axis = self.reader, self.settings, self.pack, self.axis()
        if recent:
            chosen = axis[-RECENT_ROWS:]
            anchors: set[str] = set()
            latest = sorted((event for group in chosen[-2:] for event in group["events"]), reverse=True)
            hits = [hit for hit in (reader.hit(event[2], settings.evidence_lines)
                                    for event in latest[:RECENT_EVENTS]) if hit]
        else:
            focus = self._focus(subject)
            found, _ = reader.search(subject if focus else text, top_k=3, evidence_lines=settings.evidence_lines,
                                     doctor=settings.doctor, focus_person=focus, known_only=True)
            hits = [hit for hit in found if hit.event_id in reader.times and reader.times[hit.event_id][0] <= reader.now[0]]
            anchors = {hit.event_id for hit in hits[:2]}
            where = [index for index, group in enumerate(axis)
                     if anchors & {event[2] for event in group["events"]}]
            if not where:
                return [], ""
            window = sorted({near for index in where for near in range(index - AXIS_NEIGHBOURS, index + AXIS_NEIGHBOURS + 1)
                             if 0 <= near < len(axis)})
            chosen = [axis[index] for index in window]
            while len(chosen) > AXIS_ROWS:
                chosen.pop(0 if not anchors & {event[2] for event in chosen[0]["events"]} else -1)
            hits = hits[:2]
        rows = [self._row(group, anchors) for group in chosen]
        head = f"现在大约是{now_phrase(reader.now[1])}。按时间先后，只列你知道的事："
        axis_item = None
        while rows:
            axis_item = pack.add(f"timeline:{len(pack.items)}", "时间轴", "timeline", "\n".join([head, *rows]), (),
                                 prefix="T")
            if estimate_tokens(pack.render()) <= cap:
                break
            pack.pop()
            axis_item = None
            rows.pop(0 if recent or not rows[0].startswith("→") else -1)
        if axis_item is None:
            return [], ""
        room = cap - estimate_tokens(pack.render())
        added = fill(pack, hits, None, room, total_budget=cap) if room > 0 else []
        return [axis_item, *added], pack.render([axis_item, *added])
