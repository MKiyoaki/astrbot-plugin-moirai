"""Tests for recall pipeline optimisations.

Covers:
- Pre-flight active-event count check (skip encode when DB is empty)
- BM25 runs in parallel with encoding (BM25 calls happen before encode awaits)
- Parallel parent expansion in recall_expand
- Persona/relation pre-fetched in parallel with recall
- Timer: response timer removed from event_handler; recall_inject covers full inject phase
- Timer: retrieval timer removed from hybrid.search()
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from core.config import InjectionConfig, RetrievalConfig, SoulConfig
from core.domain.models import Event, EventStatus, EventType, Persona
from core.managers.recall_manager import RecallManager


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _event(eid: str, etype: str = EventType.EPISODE, inherit_from=None) -> Event:
    return Event(
        event_id=eid,
        group_id=None,
        start_time=1000.0,
        end_time=2000.0,
        participants=["u1"],
        interaction_flow=[],
        topic=f"topic-{eid}",
        summary="",
        chat_content_tags=[],
        salience=0.8,
        confidence=0.9,
        inherit_from=inherit_from or [],
        last_accessed_at=None,
        status=EventStatus.ACTIVE,
        is_locked=False,
        bot_persona_name=None,
        event_type=etype,
    )


def _make_retriever(active_count: int = 1, fts_events=None, vec_events=None):
    """Return a fully wired MagicMock retriever."""
    fts_events = fts_events or []
    vec_events = vec_events or []

    event_repo = AsyncMock()
    event_repo.count_by_status = AsyncMock(return_value=active_count)
    event_repo.search_fts = AsyncMock(return_value=fts_events)
    event_repo.search_vector = AsyncMock(return_value=vec_events)
    event_repo.get_children = AsyncMock(return_value=[])
    event_repo.get = AsyncMock(return_value=None)

    encoder = MagicMock()
    encoder.dim = 0  # NullEncoder by default

    retriever = MagicMock()
    retriever._event_repo = event_repo
    retriever._encoder = encoder
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    return retriever, event_repo, encoder


def _make_rm(retriever, *, position="system_prompt", final_limit=5,
             persona_repo=None, impression_repo=None):
    cfg = RetrievalConfig(final_limit=final_limit)
    icfg = InjectionConfig(position=position)
    return RecallManager(
        retriever, cfg, icfg,
        persona_repo=persona_repo or AsyncMock(),
        impression_repo=impression_repo or AsyncMock(),
    )


# ---------------------------------------------------------------------------
# Pre-flight active-event count check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_preflight_skips_encode_when_db_empty():
    """With 0 active events and an active encoder, encode must NOT be called."""
    retriever, event_repo, encoder = _make_retriever(active_count=0)
    encoder.dim = 4
    encoder.encode = AsyncMock(return_value=[0.1, 0.2, 0.3, 0.4])

    rm = _make_rm(retriever)
    events = await rm.recall("any query")

    assert events == []
    encoder.encode.assert_not_called()
    event_repo.search_fts.assert_not_called()
    event_repo.search_vector.assert_not_called()


@pytest.mark.asyncio
async def test_preflight_skips_encode_null_encoder_regardless():
    """NullEncoder (dim=0): encode never called even if events exist."""
    retriever, event_repo, encoder = _make_retriever(active_count=3)
    encoder.dim = 0

    rm = _make_rm(retriever)
    await rm.recall("any query")

    # encode should never be called on NullEncoder path
    assert not hasattr(encoder, "encode") or not getattr(encoder.encode, "called", False)


@pytest.mark.asyncio
async def test_preflight_proceeds_when_db_has_events():
    """With events present, BM25 search must be called."""
    ev = _event("e1")
    retriever, event_repo, encoder = _make_retriever(active_count=1, fts_events=[ev])
    encoder.dim = 0  # NullEncoder

    rm = _make_rm(retriever)
    events = await rm.recall("test query")

    event_repo.search_fts.assert_called()
    assert any(e.event_id == "e1" for e in events)


# ---------------------------------------------------------------------------
# BM25 runs in parallel with encoding
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bm25_called_before_encode_completes():
    """BM25 search tasks are started before the encode coroutine finishes.

    We verify this by making encode yield control (asyncio.sleep) and confirming
    BM25 was still called during that window.
    """
    bm25_called_times: list[float] = []
    encode_resolved_time: list[float] = []

    ev = _event("e1")
    retriever, event_repo, encoder = _make_retriever(active_count=1, fts_events=[ev])
    encoder.dim = 4

    async def slow_encode(text):
        await asyncio.sleep(0.02)  # 20 ms delay
        encode_resolved_time.append(asyncio.get_event_loop().time())
        return [0.1, 0.2, 0.3, 0.4]

    async def fts_with_timestamp(*args, **kwargs):
        bm25_called_times.append(asyncio.get_event_loop().time())
        return [ev]

    encoder.encode = slow_encode
    event_repo.search_fts = fts_with_timestamp
    event_repo.search_vector = AsyncMock(return_value=[])

    rm = _make_rm(retriever)
    await rm.recall("test")

    assert bm25_called_times, "BM25 was never called"
    assert encode_resolved_time, "encode never completed"
    # BM25 must have been dispatched BEFORE encode resolved
    assert min(bm25_called_times) < encode_resolved_time[0], (
        "BM25 should start before encode finishes"
    )


# ---------------------------------------------------------------------------
# Parallel parent expansion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recall_expand_fetches_parents_in_parallel():
    """Multiple inherit_from parents are fetched concurrently, not sequentially."""
    call_order: list[str] = []

    parent_a = _event("pa")
    parent_b = _event("pb")
    child = _event("c1", inherit_from=["pa", "pb"])

    retriever, event_repo, encoder = _make_retriever(active_count=1, fts_events=[child])
    encoder.dim = 0

    async def get_event(event_id):
        call_order.append(f"get:{event_id}:start")
        await asyncio.sleep(0.005)
        call_order.append(f"get:{event_id}:end")
        return parent_a if event_id == "pa" else parent_b

    event_repo.get = get_event
    event_repo.get_children = AsyncMock(return_value=[])

    rm = _make_rm(retriever)
    events = await rm.recall("test")

    # Both parents should be in results
    ids = {e.event_id for e in events}
    assert "pa" in ids and "pb" in ids

    # With parallel fetch: both "start" markers appear before any "end" marker
    starts = [i for i, e in enumerate(call_order) if ":start" in e]
    ends = [i for i, e in enumerate(call_order) if ":end" in e]
    assert starts, "no get calls recorded"
    # The second start should occur before the first end (overlap = parallel)
    if len(starts) >= 2:
        assert starts[1] < ends[0], "parents were fetched sequentially, not in parallel"


# ---------------------------------------------------------------------------
# Persona / relation pre-fetched in parallel with recall
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persona_fetched_during_recall_not_after():
    """persona_repo.get is invoked while recall is still running (during encode wait)."""
    fetch_times: dict[str, float] = {}

    ev = _event("e1")
    retriever, event_repo, encoder = _make_retriever(active_count=1, fts_events=[ev])
    encoder.dim = 4

    async def slow_encode(text):
        await asyncio.sleep(0.03)
        fetch_times["encode_done"] = asyncio.get_event_loop().time()
        return [0.1, 0.2, 0.3, 0.4]

    encoder.encode = slow_encode
    event_repo.search_vector = AsyncMock(return_value=[])

    persona_repo = AsyncMock()

    async def get_persona(uid):
        fetch_times["persona_fetched"] = asyncio.get_event_loop().time()
        return Persona(uid, [], "Alice", {"big_five": {"O": 0.5}}, 0.9, 0.0, 0.0)

    persona_repo.get = get_persona

    impression_repo = AsyncMock()
    impression_repo.list_by_subject = AsyncMock(return_value=[])
    impression_repo.list_by_observer = AsyncMock(return_value=[])

    rm = _make_rm(retriever, persona_repo=persona_repo, impression_repo=impression_repo)

    req = MagicMock()
    req.system_prompt = ""
    req.prompt = ""
    req.model = "gpt-4"

    await rm.recall_and_inject("query", req, "s1", sender_uid="u1")

    assert "persona_fetched" in fetch_times, "persona was never fetched"
    assert "encode_done" in fetch_times
    # persona fetch must complete BEFORE or DURING encode (not strictly after)
    assert fetch_times["persona_fetched"] <= fetch_times["encode_done"] + 0.005, (
        "persona was fetched after encode completed — not pre-fetched in parallel"
    )


@pytest.mark.asyncio
async def test_relation_segment_fetched_during_recall():
    """impression_repo list calls happen while recall is running."""
    impression_fetched_at: list[float] = []

    ev = _event("e1")
    retriever, event_repo, encoder = _make_retriever(active_count=1, fts_events=[ev])
    encoder.dim = 4

    async def slow_encode(text):
        await asyncio.sleep(0.03)
        return [0.1, 0.2, 0.3, 0.4]

    encoder.encode = slow_encode
    event_repo.search_vector = AsyncMock(return_value=[])

    impression_repo = AsyncMock()

    async def list_by_subject(*args, **kwargs):
        impression_fetched_at.append(asyncio.get_event_loop().time())
        return []

    impression_repo.list_by_subject = list_by_subject
    impression_repo.list_by_observer = AsyncMock(return_value=[])

    rm = _make_rm(retriever, impression_repo=impression_repo)
    req = MagicMock()
    req.system_prompt = ""
    req.prompt = ""
    req.model = "gpt-4"

    t_start = asyncio.get_event_loop().time()
    await rm.recall_and_inject("query", req, "s1", sender_uid="u1")
    t_encode_end = t_start + 0.03

    assert impression_fetched_at, "impression repo was never queried"
    # Should have been called before or very shortly after encode finishes
    assert impression_fetched_at[0] < t_encode_end + 0.01


# ---------------------------------------------------------------------------
# Timer: response timer removed from event_handler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_response_timer_not_recorded_by_event_handler():
    """handle_llm_request must NOT record a 'response' phase in the perf tracker."""
    import sys
    import types

    # Stub out astrbot modules so event_handler can be imported without the real package
    for mod_name in ["astrbot", "astrbot.api"]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)
    astrbot_api = sys.modules["astrbot.api"]
    if not hasattr(astrbot_api, "logger"):
        import logging
        astrbot_api.logger = logging.getLogger("astrbot_stub")

    from core.utils.perf import tracker

    # Reset tracker history for this phase
    async with tracker._lock:
        tracker._history.pop("response", None)
        tracker._last_durations.pop("response", None)

    from core.event_handler import EventHandler

    init = MagicMock()
    init.recall = None  # recall=None → early return
    handler = EventHandler(init)

    event = MagicMock()
    event.message_str = "hello"
    event.unified_msg_origin = "test-session"
    req = MagicMock()
    req.prompt = ""

    await handler.handle_llm_request(event, req)

    metrics = await tracker.get_metrics()
    assert "response" not in metrics, (
        "'response' timer should be removed from event_handler"
    )


# ---------------------------------------------------------------------------
# Timer: retrieval timer removed from hybrid.search()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retrieval_timer_not_recorded_by_hybrid_search():
    """hybrid.search() must NOT record a 'retrieval' phase after the timer was removed."""
    from core.utils.perf import tracker
    from core.retrieval.hybrid import HybridRetriever

    async with tracker._lock:
        tracker._history.pop("retrieval", None)
        tracker._last_durations.pop("retrieval", None)

    event_repo = AsyncMock()
    event_repo.search_fts = AsyncMock(return_value=[])
    event_repo.search_vector = AsyncMock(return_value=[])

    encoder = MagicMock()
    encoder.dim = 0

    retriever = HybridRetriever(event_repo, encoder=encoder)
    await retriever.search("test query")

    metrics = await tracker.get_metrics()
    assert "retrieval" not in metrics, (
        "'retrieval' timer should be removed from hybrid.search()"
    )


# ---------------------------------------------------------------------------
# Timer: recall_inject covers full injection phase
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recall_inject_timer_covers_injection():
    """recall_inject must be recorded and represent meaningful work time."""
    from core.utils.perf import tracker

    async with tracker._lock:
        tracker._history.pop("recall_inject", None)
        tracker._last_durations.pop("recall_inject", None)

    ev = _event("e1")
    retriever, event_repo, encoder = _make_retriever(active_count=1, fts_events=[ev])
    impression_repo = AsyncMock()
    impression_repo.list_by_subject = AsyncMock(return_value=[])
    impression_repo.list_by_observer = AsyncMock(return_value=[])

    rm = _make_rm(retriever, impression_repo=impression_repo)
    req = MagicMock()
    req.system_prompt = ""
    req.prompt = ""
    req.model = "gpt-4"

    await rm.recall_and_inject("query", req, "s1", sender_uid="u1")

    metrics = await tracker.get_metrics()
    assert "recall_inject" in metrics, "recall_inject timer was not recorded"
    assert metrics["recall_inject"]["last"] >= 0
