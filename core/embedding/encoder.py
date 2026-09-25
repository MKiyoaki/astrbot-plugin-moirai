"""Embedding encoder interface and implementations.

NullEncoder: always returns [], disabling vector search — used when no model
is configured or when sentence-transformers is not installed.

SentenceTransformerEncoder: wraps a local embedding model (default:
BAAI/bge-small-zh-v1.5, 512-dim). CPU inference, ~100 MB download.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol, runtime_checkable, List

from ..utils.cache import _LRUCache

_ENCODE_CACHE_SIZE = 128
# BGE-small saturates at ~512 tokens; ~200 CJK chars cover that budget.
# Truncating before the cache lookup collapses near-identical long queries.
_ENCODE_MAX_CHARS = 200
_WHITESPACE_RE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Collapse whitespace, strip edges, truncate to cache-key length."""
    return _WHITESPACE_RE.sub(" ", text).strip()[:_ENCODE_MAX_CHARS]


@runtime_checkable
class Encoder(Protocol):
    @property
    def dim(self) -> int:
        """Embedding dimension. 0 means the encoder is inactive."""
        ...

    async def encode(self, text: str) -> List[float]:
        """Return a normalised float vector for the given text."""
        ...

    async def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """Return a list of normalised float vectors for the given texts."""
        ...


class NullEncoder:
    """No-op encoder — returns empty list to disable all vector search."""

    @property
    def dim(self) -> int:
        return 0

    async def encode(self, text: str) -> List[float]:  # noqa: ARG002
        return []

    async def encode_batch(self, texts: List[str]) -> List[List[float]]:
        return [[] for _ in texts]


try:
    from sentence_transformers import SentenceTransformer
    _ST_AVAILABLE = True
except ImportError:
    _ST_AVAILABLE = False


class SentenceTransformerEncoder:
    """Local embedding via sentence-transformers.

    The model is loaded lazily on first encode() call to avoid slowing down
    plugin startup. A dedicated single-thread executor keeps the model weights
    resident in the thread's CPU cache between calls.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        self._model_name = model_name
        self._model = None
        self._dim: int | None = None
        self._cache = _LRUCache(maxsize=_ENCODE_CACHE_SIZE)
        # Single worker keeps model weights hot in CPU cache; prevents contention
        # with unrelated thread-pool work in the default executor.
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="em_encoder")

    def _load(self) -> None:
        if self._model is not None:
            return
        if not _ST_AVAILABLE:
            raise ImportError(
                "本地向量模型需要 sentence-transformers。请运行 `pip install sentence-transformers` "
                "或在 WebUI 设置中切换为 API 模式 (OpenAI 兼容接口)。"
            )
        self._model = SentenceTransformer(self._model_name)
        self._dim = self._model.get_embedding_dimension()

    @property
    def dim(self) -> int:
        self._load()
        return self._dim or 0

    async def encode(self, text: str) -> List[float]:
        import asyncio
        self._load()
        key = _normalise(text)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: self._model.encode(key, normalize_embeddings=True, show_progress_bar=False).tolist()
        )
        self._cache.put(key, result)
        return result

    async def encode_batch(self, texts: List[str]) -> List[List[float]]:
        import asyncio
        if not texts:
            return []
        self._load()
        keys = [_normalise(t) for t in texts]
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: self._model.encode(keys, normalize_embeddings=True, show_progress_bar=False).tolist()
        )


class ApiEncoder:
    """Shared remote encoder with measured dimensions and complete input preservation."""

    def __init__(self, model_name: str, api_url: str, api_key: str, dim: int = 0,
                 timeout: float = 60.0, *, transport=None) -> None:
        from .remote import RemoteRetrievalClient, RemoteSettings
        base = api_url.rstrip("/")
        if base.endswith("/embeddings"):
            base = base[:-len("/embeddings")]
        self._model_name = model_name
        self._dim = dim
        self._client = RemoteRetrievalClient(RemoteSettings(
            base, api_key, embedding_model=model_name, timeout=timeout, retries=0,
        ), transport=transport)
        self._cache = _LRUCache(maxsize=_ENCODE_CACHE_SIZE)

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def identity(self) -> dict:
        return self._client.settings.identity

    @property
    def active(self) -> bool:
        return True

    async def encode(self, text: str) -> List[float]:
        cached = self._cache.get(text)
        if cached is not None:
            return list(cached)
        return (await self.encode_batch([text]))[0]

    async def encode_batch(self, texts: List[str]) -> List[List[float]]:
        import asyncio
        from .remote import RetrievalError
        if not texts:
            return []
        vectors = await asyncio.to_thread(self._client.embed, texts)
        dimension = len(vectors[0])
        if self._dim and self._dim != dimension:
            raise RetrievalError("Embedding dimension changed or differs from configured dimensions")
        self._dim = dimension
        for text, vector in zip(texts, vectors):
            self._cache.put(text, vector)
        return vectors

    def metrics(self) -> dict:
        return self._client.metrics()

    async def close(self) -> None:
        import asyncio
        await asyncio.to_thread(self._client.close)
