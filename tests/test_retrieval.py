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
        summary="test summary",
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

    async def encode(self, text: str) -> list[float]:  # noqa: ARG002
        return self._value

    async def encode_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._value for _ in texts]


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

    async def mock_vec(embedding, limit=20, active_only=True, group_id=None, event_type=None):
        return [e2, e1]

    repo.search_vector = mock_vec

    encoder = _FixedEncoder(dim=4, value=[1.0, 0.0, 0.0, 0.0])
    retriever = HybridRetriever(event_repo=repo, encoder=encoder)

    results = await retriever.search("python", limit=5)
    assert len(results) >= 1  # RRF should produce merged results


async def test_hybrid_retriever_falls_back_on_empty_vec_results() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(make_event("e1", topic="hello world"))

    async def mock_vec(embedding, limit=20, active_only=True, group_id=None, event_type=None):
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


# ---------------------------------------------------------------------------
# Weighted random retrieval
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weighted_random_off_returns_deterministic_top_k() -> None:
    """With weighted_random=False, results are always the top-k by RRF score."""
    repo = InMemoryEventRepository()
    for i in range(5):
        ev = make_event(f"e{i}", topic=f"topic {i}")
        await repo.upsert(ev)
    retriever = HybridRetriever(repo, encoder=NullEncoder(), weighted_random=False)
    r1 = await retriever.search("topic", limit=3)
    r2 = await retriever.search("topic", limit=3)
    assert [e.event_id for e in r1] == [e.event_id for e in r2]
    assert len(r1) == 3


@pytest.mark.asyncio
async def test_weighted_random_on_returns_correct_count() -> None:
    """With weighted_random=True, result count still respects limit."""
    repo = InMemoryEventRepository()
    for i in range(10):
        await repo.upsert(make_event(f"e{i}", topic=f"topic {i}"))
    retriever = HybridRetriever(repo, encoder=NullEncoder(), weighted_random=True, sampling_temperature=1.0)
    results = await retriever.search("topic", limit=5)
    assert len(results) == 5


@pytest.mark.asyncio
async def test_weighted_random_on_no_duplicates() -> None:
    """Sampling without replacement: no duplicate events in result."""
    repo = InMemoryEventRepository()
    for i in range(10):
        await repo.upsert(make_event(f"e{i}", topic=f"topic {i}"))
    retriever = HybridRetriever(repo, encoder=NullEncoder(), weighted_random=True, sampling_temperature=1.0)
    results = await retriever.search("topic", limit=8)
    ids = [e.event_id for e in results]
    assert len(ids) == len(set(ids))


@pytest.mark.asyncio
async def test_weighted_random_limit_larger_than_candidates() -> None:
    """If limit > candidate count, return all candidates without error."""
    repo = InMemoryEventRepository()
    for i in range(3):
        await repo.upsert(make_event(f"e{i}", topic="topic"))
    retriever = HybridRetriever(repo, encoder=NullEncoder(), weighted_random=True)
    results = await retriever.search("topic", limit=10)
    assert len(results) == 3


@pytest.mark.asyncio
async def test_weighted_random_high_temperature_produces_variety() -> None:
    """High temperature flattens distribution — over many runs all events should appear."""
    import random as _random
    _random.seed(42)
    repo = InMemoryEventRepository()
    for i in range(6):
        await repo.upsert(make_event(f"e{i}", topic="topic"))
    retriever = HybridRetriever(repo, encoder=NullEncoder(), weighted_random=True, sampling_temperature=10.0)
    seen: set[str] = set()
    for _ in range(50):
        results = await retriever.search("topic", limit=2)
        seen.update(e.event_id for e in results)
    # With high temperature and 50 runs sampling 2 from 6, expect all 6 seen
    assert len(seen) == 6


@pytest.mark.asyncio
async def test_weighted_random_low_temperature_favors_top() -> None:
    """Low temperature sharpens distribution — top event should dominate."""
    import random as _random
    _random.seed(0)
    repo = InMemoryEventRepository()
    # Insert events; BM25 ranks by term match — "aaa" appears more times → higher rank
    await repo.upsert(make_event("top", topic="aaa aaa aaa"))
    for i in range(5):
        await repo.upsert(make_event(f"other{i}", topic="aaa"))
    retriever = HybridRetriever(repo, encoder=NullEncoder(), weighted_random=True, sampling_temperature=0.05)
    top_count = 0
    for _ in range(30):
        results = await retriever.search("aaa", limit=1)
        if results and results[0].event_id == "top":
            top_count += 1
    # With very low temperature, top event should win the majority of runs
    assert top_count >= 20


# ---------------------------------------------------------------------------
# RecallManager: Neighbor Expansion (Primary Thread Filling)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recall_manager_neighbor_expansion_logic():
    from core.managers.recall_manager import RecallManager
    from core.config import RetrievalConfig, InjectionConfig
    
    repo = InMemoryEventRepository()
    retriever = HybridRetriever(repo, NullEncoder())
    rcfg = RetrievalConfig(final_limit=5)
    icfg = InjectionConfig()
    recall_manager = RecallManager(retriever, rcfg, icfg)
    
    # Chain: A -> B (Anchor) -> C
    await repo.upsert(make_event("A", topic="Context A", salience=0.3))
    await repo.upsert(make_event("B", topic="Target B", salience=0.9)) # B is top anchor
    await repo.upsert(make_event("C", topic="Topic C", salience=0.3))
    # Update B to inherit from A
    ev_b = await repo.get("B")
    ev_b.inherit_from = ["A"]
    await repo.upsert(ev_b)
    # Update C to inherit from B
    ev_c = await repo.get("C")
    ev_c.inherit_from = ["B"]
    await repo.upsert(ev_c)
    
    # Event D: unrelated anchor
    await repo.upsert(make_event("D", topic="Target D", salience=0.1))
    
    # Search for "Target" -> B and D are anchors. B is top.
    results = await recall_manager.recall("Target")
    
    # Order: B (Top Anchor) -> A (Parent) -> C (Child) -> D (Next Anchor)
    ids = [e.event_id for e in results]
    assert ids == ["B", "A", "C", "D"]


@pytest.mark.asyncio
async def test_recall_manager_expansion_deduplication():
    from core.managers.recall_manager import RecallManager
    from core.config import RetrievalConfig, InjectionConfig
    
    repo = InMemoryEventRepository()
    retriever = HybridRetriever(repo, NullEncoder())
    recall_manager = RecallManager(retriever, RetrievalConfig(final_limit=5), InjectionConfig())
    
    # A -> B. A is also an anchor.
    await repo.upsert(make_event("A", topic="Target A", salience=0.5))
    await repo.upsert(make_event("B", topic="Target B", salience=0.9)) # B is top anchor
    ev_b = await repo.get("B")
    ev_b.inherit_from = ["A"]
    await repo.upsert(ev_b)
    
    results = await recall_manager.recall("Target")
    
    # Result list should not contain duplicates
    ids = [e.event_id for e in results]
    assert len(ids) == len(set(ids))
    # Order: B (Anchor1) -> A (Neighbor of B) -> (Anchor A is skipped as duplicate)
    assert ids == ["B", "A"]
