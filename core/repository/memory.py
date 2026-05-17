"""In-memory repository implementations — for testing only.

All read methods return deep copies so callers cannot accidentally mutate
the store. All write methods store deep copies for the same reason.
"""

from __future__ import annotations

import math
from copy import deepcopy

from ..domain.models import Event, Impression, Persona

from .base import EventRepository, ImpressionRepository, PersonaRepository


class InMemoryPersonaRepository(PersonaRepository):
    def __init__(self) -> None:
        self._store: dict[str, Persona] = {}
        # (platform, physical_id) → uid
        self._bindings: dict[tuple[str, str], str] = {}

    async def get(self, uid: str) -> Persona | None:
        persona = self._store.get(uid)
        return deepcopy(persona) if persona is not None else None

    async def get_by_identity(self, platform: str, physical_id: str) -> Persona | None:
        uid = self._bindings.get((platform, physical_id))
        if uid is None:
            return None
        return await self.get(uid)

    async def list_all(self) -> list[Persona]:
        return [deepcopy(p) for p in self._store.values()]

    async def upsert(self, persona: Persona) -> None:
        # Remove stale bindings that belonged to the previous version of this uid
        old = self._store.get(persona.uid)
        if old is not None:
            for identity in old.bound_identities:
                self._bindings.pop(identity, None)

        copy = deepcopy(persona)
        self._store[copy.uid] = copy
        for identity in copy.bound_identities:
            self._bindings[identity] = copy.uid

    async def delete(self, uid: str) -> bool:
        persona = self._store.pop(uid, None)
        if persona is None:
            return False
        for identity in persona.bound_identities:
            self._bindings.pop(identity, None)
        return True

    async def bind_identity(self, uid: str, platform: str, physical_id: str) -> None:
        self._bindings[(platform, physical_id)] = uid
        if uid in self._store:
            persona = self._store[uid]
            identity = (platform, physical_id)
            if identity not in persona.bound_identities:
                persona.bound_identities.append(identity)


class InMemoryEventRepository(EventRepository):
    def __init__(self) -> None:
        self._store: dict[str, Event] = {}

    async def get(self, event_id: str) -> Event | None:
        event = self._store.get(event_id)
        return deepcopy(event) if event is not None else None

    async def list_all(
        self, limit: int = 100,
        bot_persona_name: str | None = None, include_legacy: bool = True,
    ) -> list[Event]:
        events = [
            deepcopy(e) for e in self._store.values()
            if _event_persona_matches(e, bot_persona_name, include_legacy)
        ]
        events.sort(key=lambda e: e.start_time, reverse=True)
        return events[:limit]

    async def list_by_group(
        self, group_id: str | None, limit: int = 100, exclude_type: str | None = None,
        bot_persona_name: str | None = None, include_legacy: bool = True,
    ) -> list[Event]:
        events = [
            deepcopy(e) for e in self._store.values()
            if e.group_id == group_id
            and (exclude_type is None or e.event_type != exclude_type)
            and _event_persona_matches(e, bot_persona_name, include_legacy)
        ]
        events.sort(key=lambda e: e.start_time, reverse=True)
        return events[:limit]

    async def list_by_participant(self, uid: str, limit: int = 100) -> list[Event]:
        events = [
            deepcopy(e) for e in self._store.values() if uid in e.participants
        ]
        events.sort(key=lambda e: e.start_time, reverse=True)
        return events[:limit]

    async def list_group_ids(self) -> list[str | None]:
        return list({e.group_id for e in self._store.values()})

    async def search_fts(
        self, query: str, limit: int = 20, active_only: bool = True,
        group_id: str | None = None, event_type: str | None = None,
    ) -> list[Event]:
        """Naive term-in-string match over topic + tags. FTS5 replaces this in production."""
        terms = query.lower().split()
        results: list[Event] = []
        for event in self._store.values():
            if active_only and event.status != "active":
                continue
            if group_id is not None and event.group_id != group_id:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            haystack = (event.topic + " " + " ".join(event.chat_content_tags)).lower()
            if any(term in haystack for term in terms):
                results.append(deepcopy(event))
        results.sort(key=lambda e: e.salience, reverse=True)
        return results[:limit]

    async def search_vector(
        self, embedding: list[float], limit: int = 20, active_only: bool = True,
        group_id: str | None = None, event_type: str | None = None,
    ) -> list[Event]:
        """Stub — no vector index in memory. Production uses sqlite-vec."""
        return []

    async def get_children(self, parent_event_id: str) -> list[Event]:
        return [
            deepcopy(e)
            for e in self._store.values()
            if parent_event_id in e.inherit_from
        ]

    async def upsert(self, event: Event) -> None:
        self._store[event.event_id] = deepcopy(event)

    async def delete(self, event_id: str) -> bool:
        if event_id not in self._store:
            return False
        del self._store[event_id]
        return True

    async def update_salience(self, event_id: str, new_salience: float) -> bool:
        if event_id not in self._store:
            return False
        self._store[event_id].salience = new_salience
        return True

    async def update_last_accessed(self, event_id: str, timestamp: float) -> bool:
        if event_id not in self._store:
            return False
        self._store[event_id].last_accessed_at = timestamp
        return True

    async def decay_all_salience(self, lambda_: float) -> int:
        """Multiply every event's salience by exp(-lambda_).
        Intended to be called once per day; lambda_=0.01 ≈ half-life 69 days.
        """
        factor = math.exp(-lambda_)
        for event in self._store.values():
            event.salience = max(0.0, event.salience * factor)
        return len(self._store)

    async def count_by_status(self, status: str) -> int:
        return sum(1 for e in self._store.values() if e.status == status)

    async def list_by_status(
        self, status: str, limit: int = 100,
        bot_persona_name: str | None = None, include_legacy: bool = True,
    ) -> list[Event]:
        events = [
            deepcopy(e) for e in self._store.values()
            if e.status == status
            and _event_persona_matches(e, bot_persona_name, include_legacy)
        ]
        events.sort(key=lambda e: e.start_time, reverse=True)
        return events[:limit]

    async def set_status(self, event_id: str, status: str) -> bool:
        if event_id not in self._store:
            return False
        self._store[event_id].status = status
        return True

    async def set_locked(self, event_id: str, is_locked: bool) -> bool:
        if event_id not in self._store:
            return False
        self._store[event_id].is_locked = is_locked
        return True

    async def cleanup_low_salience_events(self, threshold: float) -> int:
        to_delete = [
            eid for eid, ev in self._store.items()
            if ev.salience < threshold and not ev.is_locked
        ]
        for eid in to_delete:
            del self._store[eid]
        return len(to_delete)

    async def archive_low_salience_events(self, threshold: float) -> int:
        import dataclasses
        from ..domain.models import EventStatus
        count = 0
        for eid, ev in list(self._store.items()):
            if ev.salience < threshold and not ev.is_locked and ev.status == EventStatus.ACTIVE:
                self._store[eid] = dataclasses.replace(ev, status=EventStatus.ARCHIVED)
                count += 1
        return count

    async def delete_old_archived_events(self, cutoff_ts: float) -> int:
        from ..domain.models import EventStatus
        to_delete = [
            eid for eid, ev in self._store.items()
            if ev.status == EventStatus.ARCHIVED and ev.end_time < cutoff_ts and not ev.is_locked
        ]
        for eid in to_delete:
            del self._store[eid]
        return len(to_delete)

    async def delete_by_group(self, group_id: str | None) -> int:
        to_delete = [eid for eid, ev in self._store.items() if ev.group_id == group_id]
        for eid in to_delete:
            del self._store[eid]
        return len(to_delete)

    async def delete_all(self) -> int:
        count = len(self._store)
        self._store.clear()
        return count

    async def prune_group_history(self, group_id: str | None, max_messages: int, batch_size: int) -> int:
        """Prune oldest non-locked events in a group until total message count is <= max_messages."""
        group_events = [
            e for e in self._store.values()
            if e.group_id == group_id and not e.is_locked
        ]
        group_events.sort(key=lambda e: e.start_time)
        
        total_messages = sum(len(e.interaction_flow) for e in group_events)
        if total_messages <= max_messages:
            return 0
            
        target_messages = max_messages - batch_size
        deleted_count = 0
        current_messages = total_messages
        
        for event in group_events:
            if current_messages <= target_messages:
                break
            del self._store[event.event_id]
            current_messages -= len(event.interaction_flow)
            deleted_count += 1
            
        return deleted_count

    async def get_rowid(self, event_id: str) -> int | None:
        # In-memory has no rowid concept; return position index as a surrogate
        for i, key in enumerate(self._store):
            if key == event_id:
                return i
        return None

    async def get_by_rowid(self, rowid: int) -> Event | None:
        keys = list(self._store)
        if rowid < 0 or rowid >= len(keys):
            return None
        return deepcopy(self._store[keys[rowid]])

    async def count_messages_by_uid_bulk(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for event in self._store.values():
            for msg in event.interaction_flow:
                counts[msg.sender_uid] = counts.get(msg.sender_uid, 0) + 1
        return counts

    async def count_edge_messages(self, uid1: str, uid2: str, scope: str) -> int:
        count = 0
        for event in self._store.values():
            if scope != "global" and event.group_id != scope:
                continue
            for msg in event.interaction_flow:
                if msg.sender_uid in (uid1, uid2):
                    count += 1
        return count

    # --- Tag Abstraction & Normalization ---

    async def list_frequent_tags(self, limit: int = 50) -> list[str]:
        counts: dict[str, int] = {}
        for event in self._store.values():
            for tag in event.chat_content_tags:
                counts[tag] = counts.get(tag, 0) + 1
        sorted_tags = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        return [t[0] for t in sorted_tags[:limit]]

    async def search_canonical_tag(
        self, embedding: list[float], limit: int = 5, threshold: float = 0.85
    ) -> list[tuple[str, float]]:
        # Stub: memory repo has no vector store for tags
        return []

    async def upsert_canonical_tag(self, tag_text: str, embedding: list[float]) -> None:
        # Stub: memory repo just accepts it
        pass


class InMemoryImpressionRepository(ImpressionRepository):
    def __init__(self) -> None:
        # Unique key: (observer_uid, subject_uid, scope, bot_persona_name_or_empty).
        # bot_persona_name is normalized to '' when None so dict equality matches
        # the SQLite ifnull(bot_persona_name, '') unique index semantics.
        self._store: dict[tuple[str, str, str, str], Impression] = {}

    def _key(
        self, observer_uid: str, subject_uid: str, scope: str,
        bot_persona_name: str | None = None,
    ) -> tuple[str, str, str, str]:
        return (observer_uid, subject_uid, scope, bot_persona_name or "")

    async def get(
        self, observer_uid: str, subject_uid: str, scope: str,
        bot_persona_name: str | None = None,
    ) -> Impression | None:
        imp = self._store.get(self._key(observer_uid, subject_uid, scope, bot_persona_name))
        return deepcopy(imp) if imp is not None else None

    async def list_by_observer(
        self, observer_uid: str, scope: str | None = None,
        bot_persona_name: str | None = None, include_legacy: bool = True,
    ) -> list[Impression]:
        return [
            deepcopy(imp)
            for (obs, _subj, sc, _bp), imp in self._store.items()
            if obs == observer_uid
            and (scope is None or sc == scope)
            and _persona_matches(imp.bot_persona_name, bot_persona_name, include_legacy)
        ]

    async def list_by_subject(
        self, subject_uid: str, scope: str | None = None,
        bot_persona_name: str | None = None, include_legacy: bool = True,
    ) -> list[Impression]:
        return [
            deepcopy(imp)
            for (_obs, subj, sc, _bp), imp in self._store.items()
            if subj == subject_uid
            and (scope is None or sc == scope)
            and _persona_matches(imp.bot_persona_name, bot_persona_name, include_legacy)
        ]

    async def upsert(self, impression: Impression) -> None:
        key = self._key(
            impression.observer_uid, impression.subject_uid,
            impression.scope, impression.bot_persona_name,
        )
        self._store[key] = deepcopy(impression)

    async def delete(
        self, observer_uid: str, subject_uid: str, scope: str,
        bot_persona_name: str | None = None,
    ) -> bool:
        keys = [
            k for k in self._store
            if k[0] == observer_uid
            and k[1] == subject_uid
            and k[2] == scope
            and (
                bot_persona_name is None
                or k[3] == bot_persona_name
                or (bot_persona_name == "" and k[3] == "")
            )
        ]
        if not keys:
            return False
        for k in keys:
            del self._store[k]
        return True

    async def delete_by_scope(
        self, scope: str, bot_persona_name: str | None = None,
    ) -> int:
        keys = [
            k for k in self._store
            if k[2] == scope
            and (
                bot_persona_name is None
                or k[3] == bot_persona_name
                or (bot_persona_name == "" and k[3] == "")
            )
        ]
        for k in keys:
            del self._store[k]
        return len(keys)


def _persona_matches(row_persona: str | None, filter_persona: str | None, include_legacy: bool) -> bool:
    if filter_persona is None:
        return True
    if filter_persona == "":
        return row_persona is None
    if row_persona == filter_persona:
        return True
    return include_legacy and row_persona is None


def _event_persona_matches(event: Event, filter_persona: str | None, include_legacy: bool) -> bool:
    return _persona_matches(event.bot_persona_name, filter_persona, include_legacy)
