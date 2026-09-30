"""Moirai's retrieval boundary: keyword and vector recall over events, independent of the event store.

Recall code talks to a RetrievalBackend instead of reaching into repository
search methods, so another index (or a Core-dispatched provider) can serve
recall later without touching ranking and injection. The event store stays the
source of truth; a backend only answers searches.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import Event
from ..repository.base import EventRepository
from .terms import TOKENIZER_ID


class RetrievalBackend(ABC):
    @property
    @abstractmethod
    def identity(self) -> dict:
        """What produced the keyword index, e.g. the tokenizer; recorded in traces and diagnostics."""

    @abstractmethod
    async def lexical(
        self, query: str, *, limit: int = 20, active_only: bool = True,
        group_id: str | None = None, scope_mode: str = "all",
        bot_persona_name: str | None = None,
    ) -> list[Event]:
        """Keyword matches, best first."""

    @abstractmethod
    async def vector(
        self, embedding: list[float], *, limit: int = 20, active_only: bool = True,
        group_id: str | None = None, scope_mode: str = "all",
        bot_persona_name: str | None = None,
    ) -> list[Event]:
        """Nearest events by embedding, closest first."""


class SQLiteRetrievalBackend(RetrievalBackend):
    """FTS5 over Moirai's CJK term columns plus sqlite-vec, inside the event database."""

    def __init__(self, event_repo: EventRepository) -> None:
        self._repo = event_repo

    @property
    def identity(self) -> dict:
        return {"backend": "sqlite", "tokenizer": TOKENIZER_ID}

    async def lexical(
        self, query: str, *, limit: int = 20, active_only: bool = True,
        group_id: str | None = None, scope_mode: str = "all",
        bot_persona_name: str | None = None,
    ) -> list[Event]:
        return await self._repo.search_fts(
            query, limit=limit, active_only=active_only, group_id=group_id,
            scope_mode=scope_mode, bot_persona_name=bot_persona_name,
        )

    async def vector(
        self, embedding: list[float], *, limit: int = 20, active_only: bool = True,
        group_id: str | None = None, scope_mode: str = "all",
        bot_persona_name: str | None = None,
    ) -> list[Event]:
        return await self._repo.search_vector(
            embedding, limit=limit, active_only=active_only, group_id=group_id,
            scope_mode=scope_mode, bot_persona_name=bot_persona_name,
        )
