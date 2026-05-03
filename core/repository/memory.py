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

    async def list_by_group(self, group_id: str | None, limit: int = 100) -> list[Event]:
        events = [
            deepcopy(e) for e in self._store.values() if e.group_id == group_id
        ]
        events.sort(key=lambda e: e.start_time, reverse=True)
        return events[:limit]

    async def list_by_participant(self, uid: str, limit: int = 100) -> list[Event]:
        events = [
            deepcopy(e) for e in self._store.values() if uid in e.participants
        ]
        events.sort(key=lambda e: e.start_time, reverse=True)
        return events[:limit]

    async def search_fts(self, query: str, limit: int = 20) -> list[Event]:
        """Naive term-in-string match over topic + tags. FTS5 replaces this in Phase 2."""
        terms = query.lower().split()
        results: list[Event] = []
        for event in self._store.values():
            haystack = (event.topic + " " + " ".join(event.chat_content_tags)).lower()
            if any(term in haystack for term in terms):
                results.append(deepcopy(event))
        results.sort(key=lambda e: e.salience, reverse=True)
        return results[:limit]

    async def search_vector(self, embedding: list[float], limit: int = 20) -> list[Event]:
        """Stub — no vector index in memory. Phase 5 adds sqlite-vec."""
        return []

    async def get_children(self, parent_event_id: str) -> list[Event]:
        return [
            deepcopy(e)
            for e in self._store.values()
            if parent_event_id in e.inherit_from
        ]

    async def upsert(self, event: Event) -> None:
        self._store[event.event_id] = deepcopy(event)

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


class InMemoryImpressionRepository(ImpressionRepository):
    def __init__(self) -> None:
        # Unique key: (observer_uid, subject_uid, scope)
        self._store: dict[tuple[str, str, str], Impression] = {}

    def _key(self, observer_uid: str, subject_uid: str, scope: str) -> tuple[str, str, str]:
        return (observer_uid, subject_uid, scope)

    async def get(
        self, observer_uid: str, subject_uid: str, scope: str
    ) -> Impression | None:
        imp = self._store.get(self._key(observer_uid, subject_uid, scope))
        return deepcopy(imp) if imp is not None else None

    async def list_by_observer(
        self, observer_uid: str, scope: str | None = None
    ) -> list[Impression]:
        return [
            deepcopy(imp)
            for (obs, _subj, sc), imp in self._store.items()
            if obs == observer_uid and (scope is None or sc == scope)
        ]

    async def list_by_subject(
        self, subject_uid: str, scope: str | None = None
    ) -> list[Impression]:
        return [
            deepcopy(imp)
            for (_obs, subj, sc), imp in self._store.items()
            if subj == subject_uid and (scope is None or sc == scope)
        ]

    async def upsert(self, impression: Impression) -> None:
        key = self._key(impression.observer_uid, impression.subject_uid, impression.scope)
        self._store[key] = deepcopy(impression)

    async def delete(self, observer_uid: str, subject_uid: str, scope: str) -> bool:
        key = self._key(observer_uid, subject_uid, scope)
        if key not in self._store:
            return False
        del self._store[key]
        return True
