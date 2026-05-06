"""Embedding encoder interface and implementations.

NullEncoder: always returns [], disabling vector search — used when no model
is configured or when sentence-transformers is not installed.

SentenceTransformerEncoder: wraps a local embedding model (default:
BAAI/bge-small-zh-v1.5, 512-dim). CPU inference, ~100 MB download.
"""
from typing import Protocol, runtime_checkable, List


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


class SentenceTransformerEncoder:
    """Local embedding via sentence-transformers.

    The model is loaded lazily on first encode() call to avoid slowing down
    plugin startup.
    """

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        self._model_name = model_name
        self._model = None
        self._dim: int | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        import asyncio

        self._model = SentenceTransformer(self._model_name)
        self._dim = self._model.get_sentence_embedding_dimension()

    @property
    def dim(self) -> int:
        self._load()
        return self._dim or 0

    async def encode(self, text: str) -> List[float]:
        import asyncio
        self._load()
        # Run in thread pool as it's CPU intensive
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, 
            lambda: self._model.encode(text, normalize_embeddings=True).tolist()
        )

    async def encode_batch(self, texts: List[str]) -> List[List[float]]:
        import asyncio
        if not texts:
            return []
        self._load()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._model.encode(texts, normalize_embeddings=True).tolist()
        )


class ApiEncoder:
    """Remote embedding via OpenAI-compatible API."""

    def __init__(self, model_name: str, api_url: str, api_key: str, dim: int = 512) -> None:
        self._model_name = model_name
        self._api_url = api_url
        self._api_key = api_key
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def encode(self, text: str) -> List[float]:
        results = await self.encode_batch([text])
        return results[0] if results else []

    async def encode_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        
        import aiohttp
        headers = {"Authorization": f"Bearer {self._api_key}"}
        payload = {
            "model": self._model_name,
            "input": texts
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self._api_url, json=payload, headers=headers) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise RuntimeError(f"API request failed ({resp.status}): {error_text}")
                    
                    data = await resp.json()
                    # OpenAI format: data[i].embedding
                    embeddings = [item["embedding"] for item in data["data"]]
                    return embeddings
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("[ApiEncoder] failed: %s", exc)
            raise
