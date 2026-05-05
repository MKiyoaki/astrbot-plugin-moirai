"""Hybrid BM25 + vector retrieval with RRF fusion.

Hot-path design: zero LLM calls. Encoding is done synchronously via a local
model (SentenceTransformerEncoder) or skipped entirely (NullEncoder).
"""
from __future__ import annotations

import asyncio

from ..domain.models import Event
from ..embedding.encoder import Encoder, NullEncoder
from ..repository.base import EventRepository
from .rrf import rrf_fuse, rrf_scores


class HybridRetriever:
    """Combines FTS5 BM25 and sqlite-vec vector search via RRF fusion.

    When no encoder is provided (or the encoder has dim=0), the retriever
    falls back to BM25-only results — vector search is silently skipped.
    """

    def __init__(
        self,
        event_repo: EventRepository,
        encoder: Encoder | None = None,
        bm25_limit: int = 20,
        vec_limit: int = 20,
        rrf_k: int = 60,
    ) -> None:
        self._event_repo = event_repo
        self._encoder: Encoder = encoder or NullEncoder()
        self._bm25_limit = bm25_limit
        self._vec_limit = vec_limit
        self._rrf_k = rrf_k

    async def search_raw(
        self, query: str, active_only: bool = True, group_id: str | None = None,
    ) -> tuple[list[Event], list[Event]]:
        """Return (bm25_results, vec_results) without fusion.

        group_id=None searches across all groups; pass a value to restrict to one scope.
        Encoding runs in a thread to avoid blocking the event loop.
        """
        bm25 = await self._event_repo.search_fts(
            query, limit=self._bm25_limit, active_only=active_only, group_id=group_id,
        )
        vec: list[Event] = []
        if self._encoder.dim > 0:
            embedding = await asyncio.to_thread(self._encoder.encode, query)
            vec = await self._event_repo.search_vector(
                embedding, limit=self._vec_limit, active_only=active_only, group_id=group_id,
            )
        return bm25, vec

    async def search(
        self, query: str, limit: int = 10, active_only: bool = True, group_id: str | None = None,
    ) -> list[Event]:
        """Return up to `limit` events most relevant to the query string."""
        bm25, vec = await self.search_raw(query, active_only=active_only, group_id=group_id)

        if not vec:
            return bm25[:limit]

        return rrf_fuse([bm25, vec], k=self._rrf_k, limit=limit)

    async def index_event(self, event: Event) -> None:
        """Compute and store the embedding for a single event (background use)."""
        if self._encoder.dim == 0:
            return
        text = event.topic
        if event.chat_content_tags:
            text += " " + " ".join(event.chat_content_tags)
        if not text.strip():
            return
        embedding = self._encoder.encode(text)
        await self._event_repo.upsert_vector(event.event_id, embedding)
