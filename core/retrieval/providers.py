"""Shared embedding and reranker construction for Moirai runtime and experiments.

Invalid settings disable only the affected capability, so a misconfigured optional
provider never stops the plugin; development tools check the recorded reasons.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ..embedding.encoder import ApiEncoder, NullEncoder, SentenceTransformerEncoder
from ..managers.embedding_manager import EmbeddingManager
from .reranker import ApiReranker


logger = logging.getLogger(__name__)


@dataclass
class RetrievalProviders:
    encoder: EmbeddingManager
    reranker: ApiReranker | None
    rerank_problem: str | None = None

    async def start(self) -> None:
        await self.encoder.start()

    async def close(self) -> None:
        try:
            await self.encoder.stop()
        finally:
            if self.reranker:
                await self.reranker.close()

    def metrics(self) -> dict:
        return {"embedding": self.encoder.metrics(),
                "rerank": self.reranker.metrics() if self.reranker else {}}


def build_retrieval_providers(config, *, transport=None) -> RetrievalProviders:
    embedding = config.get_embedding_config()
    rerank = config.get_rerank_config()
    problem = None
    try:
        if not config.embedding_enabled:
            encoder = NullEncoder()
        elif embedding.provider == "api":
            encoder = ApiEncoder(embedding.model, embedding.api_url, embedding.api_key,
                                 dim=embedding.dimensions, timeout=embedding.timeout_seconds,
                                 transport=transport)
        elif embedding.provider == "local":
            encoder = SentenceTransformerEncoder(embedding.model)
        else:
            raise ValueError(f"unsupported embedding provider {embedding.provider!r}")
    except ValueError as exc:
        encoder, problem = NullEncoder(), f"invalid embedding settings: {exc}"
    manager = EmbeddingManager(encoder, embedding)
    if problem:
        manager.disable(problem)
    reranker, rerank_problem = None, None
    if rerank.enabled:
        try:
            reranker = ApiReranker(rerank, embedding, transport=transport)
        except ValueError as exc:
            rerank_problem = f"invalid rerank settings: {exc}"
            logger.error("[Retrieval] model rerank disabled: %s", rerank_problem)
    return RetrievalProviders(manager, reranker, rerank_problem)


def embedding_identity(config) -> dict:
    embedding = config.get_embedding_config()
    if embedding.provider == "api":
        base = embedding.api_url.rstrip("/")
        if base.endswith("/embeddings"):
            base = base[:-len("/embeddings")]
        return {"endpoint": base, "model": embedding.model, "query_instruction": ""}
    return {"provider": embedding.provider, "model": embedding.model}
