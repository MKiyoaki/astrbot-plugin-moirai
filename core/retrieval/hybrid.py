"""Hybrid BM25 + vector retrieval with RRF fusion.

Hot-path design: zero LLM calls. Encoding is done synchronously via a local
model (SentenceTransformerEncoder) or skipped entirely (NullEncoder).
"""
from __future__ import annotations

from ..domain.models import Event
from ..embedding.encoder import Encoder, NullEncoder
from ..repository.base import EventRepository
from .rrf import rrf_fuse


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

    async def search(self, query: str, limit: int = 10) -> list[Event]:
        """Return up to `limit` events most relevant to the query string."""
        bm25 = await self._event_repo.search_fts(query, limit=self._bm25_limit)

        vec: list[Event] = []
        if self._encoder.dim > 0:
            embedding = self._encoder.encode(query)
            vec = await self._event_repo.search_vector(embedding, limit=self._vec_limit)

        if not vec:
            return bm25[:limit]

        return rrf_fuse([bm25, vec], k=self._rrf_k, limit=limit)

    async def index_event(self, event: Event) -> None:
        """Compute and store the embedding for a single event (background use).

        Called after LLM extraction so the vector reflects the extracted topic
        and tags rather than the raw message text.
        """
        if self._encoder.dim == 0:
            return
        text = event.topic
        if event.chat_content_tags:
            text += " " + " ".join(event.chat_content_tags)
        if not text.strip():
            return
        embedding = self._encoder.encode(text)
        await self._event_repo.upsert_vector(event.event_id, embedding)
