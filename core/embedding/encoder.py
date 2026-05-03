"""Embedding encoder interface and implementations.

NullEncoder: always returns [], disabling vector search — used when no model
is configured or when sentence-transformers is not installed.

SentenceTransformerEncoder: wraps a local embedding model (default:
BAAI/bge-small-zh-v1.5, 512-dim). CPU inference, ~100 MB download.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Encoder(Protocol):
    @property
    def dim(self) -> int:
        """Embedding dimension. 0 means the encoder is inactive."""
        ...

    def encode(self, text: str) -> list[float]:
        """Return a normalised float vector for the given text."""
        ...


class NullEncoder:
    """No-op encoder — returns empty list to disable all vector search."""

    @property
    def dim(self) -> int:
        return 0

    def encode(self, text: str) -> list[float]:  # noqa: ARG002
        return []


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

        self._model = SentenceTransformer(self._model_name)
        self._dim = self._model.get_sentence_embedding_dimension()

    @property
    def dim(self) -> int:
        self._load()
        return self._dim or 0

    def encode(self, text: str) -> list[float]:
        self._load()
        return self._model.encode(text, normalize_embeddings=True).tolist()
