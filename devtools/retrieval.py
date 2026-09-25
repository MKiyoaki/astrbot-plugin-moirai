"""Development configuration and synchronous access to Moirai's shared retrieval providers."""
from __future__ import annotations

import asyncio
import os
import threading
from types import SimpleNamespace

from core.config import PluginConfig
from core.retrieval.providers import build_retrieval_providers


def development_config(config=None) -> PluginConfig:
    if config is None:
        try:
            import run_config as config
        except ImportError:
            config = SimpleNamespace()
    get = lambda name, default: getattr(config, name, default)
    base = get("KCL_API_URL", "https://ai.create.kcl.ac.uk/api/v1").rstrip("/")
    key = os.environ.get("MOIRAI_RETRIEVAL_API_KEY") or get("KCL_API_KEY", "")
    provider = get("RETRIEVAL_ENCODER_PROVIDER", "local")
    return PluginConfig({
        "embedding_enabled": get("RETRIEVAL_ENCODER_ENABLED", True),
        "embedding_provider": provider,
        "embedding_model": get("RETRIEVAL_ENCODER_MODEL", "arc:embedvl" if provider == "api"
                               else "BAAI/bge-small-zh-v1.5"),
        "embedding_api_url": get("RETRIEVAL_ENCODER_API_URL", "") or base + "/embeddings",
        "embedding_api_key": get("RETRIEVAL_ENCODER_API_KEY", "") or key,
        "embedding_dimensions": get("RETRIEVAL_ENCODER_DIMENSIONS", 0),
        "embedding_batch_size": get("RETRIEVAL_ENCODER_BATCH_SIZE", 50),
        "embedding_request_batch_size": get("RETRIEVAL_ENCODER_REQUEST_BATCH_SIZE", 16),
        "embedding_concurrency": get("RETRIEVAL_ENCODER_CONCURRENCY", 2),
        "embedding_batch_interval_ms": get("RETRIEVAL_ENCODER_BATCH_INTERVAL_MS", 50),
        "embedding_request_interval_ms": get("RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS", 0),
        "embedding_retry_max": get("RETRIEVAL_ENCODER_RETRY_MAX", 1),
        "embedding_retry_delay_ms": get("RETRIEVAL_ENCODER_RETRY_DELAY_MS", 1000),
        "embedding_timeout_seconds": get("RETRIEVAL_ENCODER_TIMEOUT", 60.0),
        "rerank_enabled": get("RETRIEVAL_RERANK_ENABLED", False),
        "rerank_model": get("RETRIEVAL_RERANK_MODEL", "arc:rerankvl"),
        "rerank_api_url": get("RETRIEVAL_RERANK_API_URL", "") or base + "/rerank",
        "rerank_api_key": get("RETRIEVAL_RERANK_API_KEY", "") or key,
        "rerank_max_candidates": get("RETRIEVAL_RERANK_MAX_CANDIDATES", 40),
        "rerank_timeout_seconds": get("RETRIEVAL_RERANK_TIMEOUT", 60.0),
        "rerank_retry_max": get("RETRIEVAL_RERANK_RETRY_MAX", 1),
    })


class ProviderBridge:
    """Keep one asynchronous provider lifecycle behind synchronous terminal tools."""

    def __init__(self, config, *, transport=None) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.closed = False

        async def create():
            providers = build_retrieval_providers(config, transport=transport)
            await providers.start()
            return providers

        try:
            self.providers = self.call(create())
        except BaseException:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join()
            self.loop.close()
            raise
        if self.providers.encoder.disabled_reason:
            self.close()
            raise ValueError(self.providers.encoder.disabled_reason)
        self.identity = self.providers.encoder.identity
        self.max_candidates = config.get_rerank_config().max_candidates

    def call(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result()

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self.call(self.providers.encoder.encode_batch(texts))

    def embed_query(self, query: str) -> list[float]:
        return self.call(self.providers.encoder.encode(query))

    def rerank(self, query: str, documents: list[str]) -> list[tuple[int, float]]:
        if self.providers.reranker is None:
            raise ValueError(self.providers.rerank_problem
                             or "Enable the shared RETRIEVAL_RERANK_ENABLED setting")
        return self.call(self.providers.reranker.rerank(query, documents))

    def metrics(self) -> dict:
        return self.providers.metrics()

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            try:
                self.call(self.providers.close())
            finally:
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.thread.join()
                self.loop.close()
