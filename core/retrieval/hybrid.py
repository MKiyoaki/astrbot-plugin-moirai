"""Hybrid BM25 + vector retrieval with RRF fusion.

Hot-path design: zero LLM calls. Encoding is done synchronously via a local
model (SentenceTransformerEncoder) or skipped entirely (NullEncoder).
"""
from __future__ import annotations

import asyncio
import random
import math

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
        weighted_random: bool = False,
        sampling_temperature: float = 1.0,
    ) -> None:
        self._event_repo = event_repo
        self._encoder: Encoder = encoder or NullEncoder()
        self._bm25_limit = bm25_limit
        self._vec_limit = vec_limit
        self._rrf_k = rrf_k
        self._weighted_random = weighted_random
        self._sampling_temperature = sampling_temperature

    async def search_raw(
        self, query: str, active_only: bool = True, group_id: str | None = None,
        event_type: str | None = None,
    ) -> tuple[list[Event], list[Event]]:
        """Return (bm25_results, vec_results) without fusion.

        group_id=None searches across all groups; pass a value to restrict to one scope.
        event_type restricts to 'episode' or 'narrative' when specified.
        Encoding runs in a thread to avoid blocking the event loop.
        """
        bm25 = await self._event_repo.search_fts(
            query, limit=self._bm25_limit, active_only=active_only,
            group_id=group_id, event_type=event_type,
        )
        vec: list[Event] = []
        if self._encoder.dim > 0:
            embedding = await self._encoder.encode(query)
            vec = await self._event_repo.search_vector(
                embedding, limit=self._vec_limit, active_only=active_only,
                group_id=group_id, event_type=event_type,
            )
        return bm25, vec

    async def search(
        self, query: str, limit: int = 10, active_only: bool = True, group_id: str | None = None,
    ) -> list[Event]:
        """Return up to `limit` events most relevant to the query string."""
        from ..utils.perf import performance_timer
        async with performance_timer("retrieval"):
            bm25, vec = await self.search_raw(query, active_only=active_only, group_id=group_id)

            if not vec:
                candidates = bm25
            else:
                # Get all candidates with their RRF scores
                scores_dict = rrf_scores([bm25, vec], k=self._rrf_k)
                # Map back to event objects
                event_map = {e.event_id: e for e in (bm25 + vec)}
                candidates = [event_map[eid] for eid in sorted(scores_dict, key=lambda x: -scores_dict[x])]

            if not candidates:
                return []

            if not self._weighted_random or len(candidates) <= 1:
                return candidates[:limit]

            # Weighted Random Retrieval (Softmax Sampling)
            # 1. Re-calculate scores for all candidates (if not already done via rrf_scores)
            if not vec:
                # BM25-only: use 1/(rank) as proxy for score
                scores = [1.0 / (i + 1) for i in range(len(candidates))]
            else:
                scores = [scores_dict[e.event_id] for e in candidates]

            # 2. Apply Softmax with Temperature
            # Softmax(x_i) = exp(x_i / T) / sum(exp(x_j / T))
            # To avoid overflow, subtract max score
            max_s = max(scores)
            exp_scores = [math.exp((s - max_s) / self._sampling_temperature) for s in scores]
            total = sum(exp_scores)
            probs = [s / total for s in exp_scores]

            # 3. Sample without replacement
            # Use random.choices to sample indices
            try:
                sampled_indices = []
                remaining_indices = list(range(len(candidates)))
                remaining_probs = list(probs)
                
                count = min(limit, len(candidates))
                for _ in range(count):
                    idx_in_remaining = random.choices(range(len(remaining_indices)), weights=remaining_probs, k=1)[0]
                    sampled_indices.append(remaining_indices.pop(idx_in_remaining))
                    # Remove and re-normalize remaining probs
                    remaining_probs.pop(idx_in_remaining)
                    p_sum = sum(remaining_probs)
                    if p_sum > 0:
                        remaining_probs = [p / p_sum for p in remaining_probs]
                    else:
                        break
                        
                return [candidates[i] for i in sampled_indices]
            except Exception as exc:
                import logging
                logging.getLogger(__name__).error("[HybridRetriever] sampling failed: %s", exc)
                return candidates[:limit]

    async def index_event(self, event: Event) -> None:
        """Compute and store the embedding for a single event (background use)."""
        if self._encoder.dim == 0:
            return
        text = event.topic
        if event.summary:
            text += " " + event.summary
        if event.chat_content_tags:
            text += " " + " ".join(event.chat_content_tags)
        if not text.strip():
            return
        embedding = await self._encoder.encode(text)
        await self._event_repo.upsert_vector(event.event_id, embedding)
