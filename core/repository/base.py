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
    async def list_all(self, limit: int = 100) -> list[Event]:
        """Return all events, sorted by start_time DESC."""
        ...

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
    async def search_fts(
        self, query: str, limit: int = 20, active_only: bool = True,
        group_id: str | None = None,
    ) -> list[Event]:
        """Keyword search over topic and chat_content_tags.

        group_id=None searches across all groups; pass a value to restrict to one scope.
        """
        ...

    @abstractmethod
    async def search_vector(
        self, embedding: list[float], limit: int = 20, active_only: bool = True,
        group_id: str | None = None,
    ) -> list[Event]:
        """Semantic search via embedding similarity.

        group_id=None searches across all groups; pass a value to restrict to one scope.
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

    @abstractmethod
    async def count_by_status(self, status: str) -> int:
        """Return the number of events with the given status without loading rows."""
        ...

    @abstractmethod
    async def list_by_status(
        self, status: str, limit: int = 100
    ) -> list[Event]:
        """Return events filtered by status ('active' or 'archived'), newest first."""
        ...

    @abstractmethod
    async def set_status(self, event_id: str, status: str) -> bool:
        """Update the lifecycle status of one event. Returns False if not found."""
        ...

    @abstractmethod
    async def set_locked(self, event_id: str, is_locked: bool) -> bool:
        """Protect an event from auto-cleanup. Returns False if not found."""
        ...

    @abstractmethod
    async def cleanup_low_salience_events(self, threshold: float) -> int:
        """Delete non-locked events with salience < threshold. Returns count deleted."""
        ...

    @abstractmethod
    async def archive_low_salience_events(self, threshold: float) -> int:
        """Set status=archived for non-locked active events with salience < threshold. Returns count archived."""
        ...

    @abstractmethod
    async def delete_old_archived_events(self, cutoff_ts: float) -> int:
        """Permanently delete non-locked archived events with end_time < cutoff_ts. Returns count deleted."""
        ...

    @abstractmethod
    async def get_rowid(self, event_id: str) -> int | None:
        """Return the SQLite integer rowid for an event (used for FTS5/vec joins)."""
        ...

    @abstractmethod
    async def get_by_rowid(self, rowid: int) -> Event | None:
        """Look up an event by its integer rowid (the integer primary key)."""
        ...

    async def upsert_vector(self, event_id: str, embedding: list[float]) -> None:
        """Store the vector embedding for an event.

        Default is a no-op — overridden by SQLiteEventRepository when
        sqlite-vec is loaded. In-memory repo ignores vectors.
        """

    async def delete_vector(self, event_id: str) -> None:
        """Remove the vector embedding for an event.

        Default is a no-op — overridden by SQLiteEventRepository.
        """

    async def delete_with_vector(self, event_id: str) -> bool:
        """Delete an event and its vector embedding atomically.

        Default implementation calls delete_vector then delete sequentially.
        SQLiteEventRepository overrides this with a single transaction.
        Returns False if event_id was not found.
        """
        await self.delete_vector(event_id)
        return await self.delete(event_id)

    @abstractmethod
    async def count_messages_by_uid_bulk(self) -> dict[str, int]:
        """Return {uid: total_message_count} for every sender across ALL events."""
        ...

    @abstractmethod
    async def count_edge_messages(self, uid1: str, uid2: str, scope: str) -> int:
        """Count messages sent by uid1 OR uid2 within a scope.

        scope='global' counts across all groups; any other value filters by group_id.
        """
        ...

    # --- Tag Abstraction & Normalization ---

    @abstractmethod
    async def list_frequent_tags(self, limit: int = 50) -> list[str]:
        """Return the most frequently used tags from the events table."""
        ...

    @abstractmethod
    async def search_canonical_tag(
        self, embedding: list[float], limit: int = 5, threshold: float = 0.85
    ) -> list[tuple[str, float]]:
        """Find existing canonical tags similar to the given embedding.
        Returns a list of (tag_text, similarity_score).
        """
        ...

    @abstractmethod
    async def upsert_canonical_tag(self, tag_text: str, embedding: list[float]) -> None:
        """Store a new canonical tag and its embedding."""
        ...


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
