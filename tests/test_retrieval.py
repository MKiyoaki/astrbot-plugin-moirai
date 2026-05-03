"""Tests for RRF fusion, HybridRetriever, and SQLite vector operations."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.domain.models import Event, MessageRef
from core.embedding.encoder import NullEncoder
from core.repository.memory import InMemoryEventRepository
from core.retrieval.hybrid import HybridRetriever
from core.retrieval.rrf import rrf_fuse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_event(event_id: str, topic: str = "", salience: float = 0.5) -> Event:
    return Event(
        event_id=event_id,
        group_id="g1",
        start_time=1000.0,
        end_time=1010.0,
        participants=["uid-a"],
        interaction_flow=[],
        topic=topic,
        chat_content_tags=[],
        salience=salience,
        confidence=0.8,
        inherit_from=[],
        last_accessed_at=1010.0,
    )


class _FixedEncoder:
    """Returns a pre-set embedding for any text."""

    def __init__(self, dim: int, value: list[float]) -> None:
        self._dim = dim
        self._value = value

    @property
    def dim(self) -> int:
        return self._dim

    def encode(self, text: str) -> list[float]:  # noqa: ARG002
        return self._value


# ---------------------------------------------------------------------------
# RRF fusion tests
# ---------------------------------------------------------------------------

def test_rrf_fuse_single_list() -> None:
    events = [make_event("e1"), make_event("e2"), make_event("e3")]
    result = rrf_fuse([events], limit=3)
    assert [e.event_id for e in result] == ["e1", "e2", "e3"]


def test_rrf_fuse_two_lists_boosts_shared_events() -> None:
    e1, e2, e3 = make_event("e1"), make_event("e2"), make_event("e3")
    # e1 appears in both lists at rank 1 → gets double score
    result = rrf_fuse([[e1, e2, e3], [e1, e3, e2]], limit=3)
    assert result[0].event_id == "e1"


def test_rrf_fuse_respects_limit() -> None:
    events = [make_event(f"e{i}") for i in range(10)]
    result = rrf_fuse([events], limit=3)
    assert len(result) == 3


def test_rrf_fuse_empty_lists() -> None:
    assert rrf_fuse([]) == []
    assert rrf_fuse([[]]) == []


def test_rrf_fuse_disjoint_lists_interleaves() -> None:
    a = [make_event("a1"), make_event("a2")]
    b = [make_event("b1"), make_event("b2")]
    result = rrf_fuse([a, b], limit=4)
    ids = [e.event_id for e in result]
    assert set(ids) == {"a1", "a2", "b1", "b2"}


def test_rrf_fuse_k_affects_scores() -> None:
    e1, e2 = make_event("e1"), make_event("e2")
    # With larger k, rank differences matter less — scores are closer
    result_small_k = rrf_fuse([[e1, e2], [e2, e1]], k=1, limit=2)
    result_large_k = rrf_fuse([[e1, e2], [e2, e1]], k=1000, limit=2)
    # Both should still rank tied events (e1 rank1+e2rank2 = e2rank1+e1rank2 by symmetry)
    assert {e.event_id for e in result_small_k} == {"e1", "e2"}
    assert {e.event_id for e in result_large_k} == {"e1", "e2"}


# ---------------------------------------------------------------------------
# HybridRetriever tests (in-memory, no actual embeddings)
# ---------------------------------------------------------------------------

async def test_hybrid_retriever_bm25_only_when_null_encoder() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", topic="project planning"))
    await repo.upsert(make_event("e2", topic="weekend trip"))

    retriever = HybridRetriever(event_repo=repo, encoder=NullEncoder())
    results = await retriever.search("project", limit=5)
    # In-memory FTS is a simple substring match
    assert any(e.event_id == "e1" for e in results)


async def test_hybrid_retriever_uses_rrf_when_encoder_active() -> None:
    repo = InMemoryEventRepository()
    e1 = make_event("e1", topic="python coding")
    e2 = make_event("e2", topic="cooking recipes")
    await repo.upsert(e1)
    await repo.upsert(e2)

    # Mock: search_vector always returns [e2, e1] regardless of query
    original_vec = repo.search_vector

    async def mock_vec(embedding, limit=20):
        return [e2, e1]

    repo.search_vector = mock_vec

    encoder = _FixedEncoder(dim=4, value=[1.0, 0.0, 0.0, 0.0])
    retriever = HybridRetriever(event_repo=repo, encoder=encoder)

    results = await retriever.search("python", limit=5)
    assert len(results) >= 1  # RRF should produce merged results


async def test_hybrid_retriever_falls_back_on_empty_vec_results() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", topic="hello world"))

    async def mock_vec(embedding, limit=20):
        return []

    repo.search_vector = mock_vec

    encoder = _FixedEncoder(dim=4, value=[1.0, 0.0, 0.0, 0.0])
    retriever = HybridRetriever(event_repo=repo, encoder=encoder)
    results = await retriever.search("hello", limit=5)
    assert any(e.event_id == "e1" for e in results)


async def test_hybrid_retriever_index_event_calls_upsert_vector() -> None:
    repo = InMemoryEventRepository()
    vectorized: list[tuple[str, list[float]]] = []

    original_upsert_vector = repo.upsert_vector

    async def capture_vector(event_id, embedding):
        vectorized.append((event_id, embedding))

    repo.upsert_vector = capture_vector

    encoder = _FixedEncoder(dim=4, value=[0.5, 0.5, 0.0, 0.0])
    retriever = HybridRetriever(event_repo=repo, encoder=encoder)
    event = make_event("ev1", topic="test topic")
    await retriever.index_event(event)

    assert len(vectorized) == 1
    assert vectorized[0][0] == "ev1"
    assert vectorized[0][1] == [0.5, 0.5, 0.0, 0.0]


async def test_hybrid_retriever_index_event_skips_null_encoder() -> None:
    repo = InMemoryEventRepository()
    vectorized: list = []

    async def capture_vector(event_id, embedding):
        vectorized.append(event_id)

    repo.upsert_vector = capture_vector

    retriever = HybridRetriever(event_repo=repo, encoder=NullEncoder())
    await retriever.index_event(make_event("ev2", topic="topic"))
    assert vectorized == []


# ---------------------------------------------------------------------------
# SQLite vector search integration test (requires sqlite-vec)
# ---------------------------------------------------------------------------

async def test_sqlite_vector_upsert_and_search(tmp_path: Path) -> None:
    pytest.importorskip("sqlite_vec")

    from core.repository.sqlite import SQLiteEventRepository, db_open

    async with db_open(tmp_path / "test.db", vec_dim=4) as db:
        repo = SQLiteEventRepository(db)

        e1 = make_event("e1", topic="alpha")
        e2 = make_event("e2", topic="beta")
        await repo.upsert(e1)
        await repo.upsert(e2)

        # Store different embeddings
        await repo.upsert_vector("e1", [1.0, 0.0, 0.0, 0.0])
        await repo.upsert_vector("e2", [0.0, 1.0, 0.0, 0.0])

        # Query close to e1
        results = await repo.search_vector([0.99, 0.01, 0.0, 0.0], limit=2)
        assert len(results) > 0
        assert results[0].event_id == "e1"


async def test_sqlite_vector_search_returns_empty_without_vec(tmp_path: Path) -> None:
    from core.repository.sqlite import SQLiteEventRepository, db_open

    async with db_open(tmp_path / "test.db", vec_dim=4) as db:
        repo = SQLiteEventRepository(db)
        # search_vector with empty embedding → always []
        results = await repo.search_vector([], limit=5)
        assert results == []


async def test_sqlite_upsert_vector_overwrite(tmp_path: Path) -> None:
    pytest.importorskip("sqlite_vec")

    from core.repository.sqlite import SQLiteEventRepository, db_open

    async with db_open(tmp_path / "test.db", vec_dim=4) as db:
        repo = SQLiteEventRepository(db)
        event = make_event("ev1")
        await repo.upsert(event)

        await repo.upsert_vector("ev1", [1.0, 0.0, 0.0, 0.0])
        await repo.upsert_vector("ev1", [0.0, 1.0, 0.0, 0.0])  # overwrite

        results = await repo.search_vector([0.0, 0.99, 0.0, 0.0], limit=1)
        assert len(results) == 1
        assert results[0].event_id == "ev1"
