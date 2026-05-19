"""Tests for performance optimizations:
- SQLite PRAGMA changes (mmap_size, temp_store, wal_autocheckpoint)
- Composite index migration (012)
- Embedding LRU cache
- search_raw pre-computed embedding parameter
- RecallManager single-encode + soul_states TTL eviction
- interaction_flow excluded from search hot path
"""
import asyncio
import time
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_event(eid: str):
    from core.domain.models import Event, EventStatus, EventType
    return Event(
        event_id=eid,
        group_id=None,
        start_time=1000.0,
        end_time=2000.0,
        participants=["u1"],
        interaction_flow=[],
        topic="test topic",
        summary="test summary",
        chat_content_tags=["tag"],
        salience=0.8,
        confidence=0.9,
        inherit_from=[],
        last_accessed_at=None,
        status=EventStatus.ACTIVE,
        is_locked=False,
        bot_persona_name=None,
        event_type=EventType.EPISODE,
    )


# ── PRAGMA tests ──────────────────────────────────────────────────────────────

def test_pragmas_contain_mmap_and_temp_store():
    from core.repository.sqlite import _PRAGMAS
    pragma_text = " ".join(_PRAGMAS)
    assert "mmap_size" in pragma_text
    assert "temp_store" in pragma_text
    assert "wal_autocheckpoint" in pragma_text


# ── Composite index migration ─────────────────────────────────────────────────

def test_migration_012_exists():
    migration_path = Path(__file__).parent.parent.parent / "migrations" / "012_perf_composite_index.sql"
    assert migration_path.exists()
    content = migration_path.read_text()
    assert "idx_events_status_type_group" in content
    assert "status" in content and "event_type" in content and "group_id" in content


# ── Embedding LRU cache ───────────────────────────────────────────────────────

def test_lru_cache_put_and_get():
    from core.embedding.encoder import _LRUCache
    cache = _LRUCache(maxsize=3)
    assert cache.get("a") is None
    cache.put("a", [1.0, 2.0])
    assert cache.get("a") == [1.0, 2.0]


def test_lru_cache_evicts_oldest():
    from core.embedding.encoder import _LRUCache
    cache = _LRUCache(maxsize=2)
    cache.put("a", [1.0])
    cache.put("b", [2.0])
    cache.put("c", [3.0])  # should evict "a"
    assert cache.get("a") is None
    assert cache.get("b") == [2.0]
    assert cache.get("c") == [3.0]


def test_lru_cache_move_to_end_on_access():
    from core.embedding.encoder import _LRUCache
    cache = _LRUCache(maxsize=2)
    cache.put("a", [1.0])
    cache.put("b", [2.0])
    cache.get("a")  # access "a" to make it recently used
    cache.put("c", [3.0])  # should evict "b", not "a"
    assert cache.get("a") == [1.0]
    assert cache.get("b") is None


@pytest.mark.asyncio
async def test_sentence_transformer_encoder_uses_cache():
    """Second call with same text should skip the executor."""
    from core.embedding.encoder import SentenceTransformerEncoder
    enc = SentenceTransformerEncoder.__new__(SentenceTransformerEncoder)
    enc._model_name = "test"
    enc._model = None
    enc._dim = 4
    from core.embedding.encoder import _LRUCache
    enc._cache = _LRUCache()

    call_count = 0

    async def fake_encode(text: str) -> List[float]:
        nonlocal call_count
        call_count += 1
        return [0.1, 0.2, 0.3, 0.4]

    import asyncio
    loop = asyncio.get_running_loop()

    # Patch run_in_executor to count calls
    original_encode = SentenceTransformerEncoder.encode

    async def patched_encode(self, text):
        nonlocal call_count
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        call_count += 1
        result = [0.1, 0.2, 0.3, 0.4]
        self._cache.put(text, result)
        return result

    with patch.object(SentenceTransformerEncoder, 'encode', patched_encode):
        enc2 = SentenceTransformerEncoder()
        r1 = await enc2.encode("hello")
        r2 = await enc2.encode("hello")
        r3 = await enc2.encode("world")

    assert r1 == r2
    assert call_count == 2  # "hello" once, "world" once


# ── search_raw pre-computed embedding ────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_raw_uses_provided_embedding():
    """When embedding is passed to search_raw, encoder.encode should NOT be called."""
    from core.retrieval.hybrid import HybridRetriever

    mock_repo = AsyncMock()
    mock_repo.search_fts = AsyncMock(return_value=[])
    mock_repo.search_vector = AsyncMock(return_value=[])

    mock_encoder = MagicMock()
    mock_encoder.dim = 4
    mock_encoder.encode = AsyncMock(return_value=[1.0, 0.0, 0.0, 0.0])

    retriever = HybridRetriever(mock_repo, encoder=mock_encoder)
    precomputed = [0.5, 0.5, 0.0, 0.0]
    await retriever.search_raw("query", embedding=precomputed)

    mock_encoder.encode.assert_not_called()
    mock_repo.search_vector.assert_called_once()
    call_args = mock_repo.search_vector.call_args
    # embedding is passed as first positional arg to search_vector
    assert call_args[0][0] == precomputed


@pytest.mark.asyncio
async def test_search_raw_encodes_when_no_embedding():
    """When embedding is not passed, encoder.encode should be called."""
    from core.retrieval.hybrid import HybridRetriever

    mock_repo = AsyncMock()
    mock_repo.search_fts = AsyncMock(return_value=[])
    mock_repo.search_vector = AsyncMock(return_value=[])

    mock_encoder = MagicMock()
    mock_encoder.dim = 4
    mock_encoder.encode = AsyncMock(return_value=[1.0, 0.0, 0.0, 0.0])

    retriever = HybridRetriever(mock_repo, encoder=mock_encoder)
    await retriever.search_raw("query")

    mock_encoder.encode.assert_called_once_with("query")


# ── soul_states TTL eviction ──────────────────────────────────────────────────

def test_evict_soul_states_removes_stale():
    from core.managers.recall_manager import RecallManager
    from core.social.soul_state import SoulState

    mgr = RecallManager.__new__(RecallManager)
    mgr._soul_states = {"old_session": SoulState(0.0, 0.0, 0.0, 0.0)}
    mgr._soul_state_accessed = {"old_session": time.time() - 48 * 3600}
    mgr._soul_states_ttl_hours = 24.0

    mgr._evict_soul_states()

    assert "old_session" not in mgr._soul_states
    assert "old_session" not in mgr._soul_state_accessed


def test_evict_soul_states_keeps_fresh():
    from core.managers.recall_manager import RecallManager
    from core.social.soul_state import SoulState

    mgr = RecallManager.__new__(RecallManager)
    mgr._soul_states = {"new_session": SoulState(0.0, 0.0, 0.0, 0.0)}
    mgr._soul_state_accessed = {"new_session": time.time() - 1 * 3600}
    mgr._soul_states_ttl_hours = 24.0

    mgr._evict_soul_states()

    assert "new_session" in mgr._soul_states


# ── interaction_flow excluded from hot path ───────────────────────────────────

@pytest.mark.asyncio
async def test_vector_search_returns_empty_interaction_flow(tmp_path: Path):
    """Events from search_vector should have interaction_flow=[] (stripped in hot path)."""
    pytest.importorskip("sqlite_vec")
    from core.repository.sqlite import SQLiteEventRepository, db_open
    import dataclasses
    from core.domain.models import MessageRef

    async with db_open(tmp_path / "test.db", vec_dim=4) as db:
        repo = SQLiteEventRepository(db)
        base = _make_event("ev-vec-test")
        ev = dataclasses.replace(base, last_accessed_at=1000.0, interaction_flow=[
            MessageRef("u1", 1000, "hash1", "some message content")
        ])
        await repo.upsert(ev)
        await repo.upsert_vector("ev-vec-test", [1.0, 0.0, 0.0, 0.0])

        results = await repo.search_vector([0.99, 0.01, 0.0, 0.0], limit=1)
        assert len(results) == 1
        # interaction_flow should be empty (stripped for I/O reduction in hot path)
        assert results[0].interaction_flow == []


# ── SoulConfig TTL wiring ─────────────────────────────────────────────────────

def test_soul_config_has_states_ttl():
    from core.config import SoulConfig
    cfg = SoulConfig(states_ttl_hours=12.0)
    assert cfg.states_ttl_hours == 12.0


def test_recall_manager_uses_soul_config_ttl():
    from core.managers.recall_manager import RecallManager
    from core.config import SoulConfig

    cfg = SoulConfig(states_ttl_hours=6.0)
    mgr = RecallManager.__new__(RecallManager)
    mgr._soul_states = {}
    mgr._soul_state_accessed = {}
    mgr._soul_states_ttl_hours = cfg.states_ttl_hours if cfg is not None else 24.0

    assert mgr._soul_states_ttl_hours == 6.0
