"""Optional shared model reranking of bounded, already scoped retrieval candidates."""
from __future__ import annotations

import asyncio

from ..embedding.remote import RemoteRetrievalClient, RemoteSettings


class ApiReranker:
    def __init__(self, config, embedding_config, *, transport=None) -> None:
        base = embedding_config.api_url.rstrip("/")
        if base.endswith("/embeddings"):
            base = base[:-len("/embeddings")]
        endpoint = config.api_url.rstrip("/") or base + "/rerank"
        base, _, suffix = endpoint.rpartition("/")
        self.max_candidates = config.max_candidates
        if self.max_candidates < 1:
            raise ValueError("Rerank candidate limit must be positive")
        self._client = RemoteRetrievalClient(RemoteSettings(
            base, config.api_key or embedding_config.api_key,
            rerank_model=config.model, rerank_path="/" + suffix,
            timeout=config.timeout_seconds, retries=config.retry_max,
        ), transport=transport)
        self.identity = {"model": config.model, "endpoint": endpoint}

    async def rerank(self, query: str, documents: list[str]) -> list[tuple[int, float]]:
        if len(documents) > self.max_candidates:
            raise ValueError("Rerank candidate budget exceeded")
        return await asyncio.to_thread(self._client.rerank, query, documents)

    def metrics(self) -> dict:
        return self._client.metrics()

    async def close(self) -> None:
        await asyncio.to_thread(self._client.close)
