"""Abstract repository interfaces.

Production code uses the SQLite implementation; tests use the in-memory
implementation. Both satisfy the same interface, enabling interface-swap tests.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import Event, Impression, Persona


class PersonaRepository(ABC):
    @abstractmethod
    async def get(self, uid: str) -> Persona | None: ...

    @abstractmethod
    async def get_by_identity(self, platform: str, physical_id: str) -> Persona | None: ...

    @abstractmethod
    async def list_all(self) -> list[Persona]: ...

    @abstractmethod
    async def upsert(self, persona: Persona) -> None: ...

    @abstractmethod
    async def delete(self, uid: str) -> bool: ...

    @abstractmethod
    async def bind_identity(self, uid: str, platform: str, physical_id: str) -> None:
        """Add a new (platform, physical_id) binding to an existing Persona."""
        ...


class EventRepository(ABC):
    @abstractmethod
    async def get(self, event_id: str) -> Event | None: ...

    @abstractmethod
    async def list_by_group(self, group_id: str | None, limit: int = 100) -> list[Event]:
        """Return events for a group, sorted by start_time DESC.
        group_id=None returns private-chat events.
        """
        ...

    @abstractmethod
    async def list_by_participant(self, uid: str, limit: int = 100) -> list[Event]:
        """Return events where uid is in participants, sorted by start_time DESC."""
        ...

    @abstractmethod
    async def list_group_ids(self) -> list[str | None]:
        """Return the distinct group_id values present in the events table.
        None represents private-chat events.
        """
        ...

    @abstractmethod
    async def search_fts(self, query: str, limit: int = 20) -> list[Event]:
        """Keyword search over topic and chat_content_tags."""
        ...

    @abstractmethod
    async def search_vector(self, embedding: list[float], limit: int = 20) -> list[Event]:
        """Semantic search via embedding similarity.
        Stub returns []; real implementation uses sqlite-vec vec0 (Phase 5).
        """
        ...

    @abstractmethod
    async def get_children(self, parent_event_id: str) -> list[Event]:
        """Return events whose inherit_from contains parent_event_id."""
        ...

    @abstractmethod
    async def upsert(self, event: Event) -> None: ...

    @abstractmethod
    async def delete(self, event_id: str) -> bool:
        """Return False if event_id not found."""
        ...

    @abstractmethod
    async def update_salience(self, event_id: str, new_salience: float) -> bool:
        """Return False if event_id not found."""
        ...

    @abstractmethod
    async def update_last_accessed(self, event_id: str, timestamp: float) -> bool:
        """Return False if event_id not found."""
        ...

    @abstractmethod
    async def decay_all_salience(self, lambda_: float) -> int:
        """Multiply every event's salience by exp(-lambda_). Return count updated.
        Intended to be called once per day by the periodic task scheduler.
        """
        ...

    async def upsert_vector(self, event_id: str, embedding: list[float]) -> None:
        """Store the vector embedding for an event.

        Default is a no-op — overridden by SQLiteEventRepository when
        sqlite-vec is loaded. In-memory repo ignores vectors.
        """


class ImpressionRepository(ABC):
    @abstractmethod
    async def get(
        self, observer_uid: str, subject_uid: str, scope: str
    ) -> Impression | None: ...

    @abstractmethod
    async def list_by_observer(
        self, observer_uid: str, scope: str | None = None
    ) -> list[Impression]:
        """If scope is None, return impressions across all scopes."""
        ...

    @abstractmethod
    async def list_by_subject(
        self, subject_uid: str, scope: str | None = None
    ) -> list[Impression]: ...

    @abstractmethod
    async def upsert(self, impression: Impression) -> None:
        """Insert or replace based on (observer_uid, subject_uid, scope) key."""
        ...

    @abstractmethod
    async def delete(self, observer_uid: str, subject_uid: str, scope: str) -> bool:
        """Return False if not found."""
        ...
