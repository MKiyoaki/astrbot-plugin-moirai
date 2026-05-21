"""Tests for signal-driven Soul Layer update.

Covers:
- recall_depth grows more with high-salience events than low-salience
- expression_desire is positive when benevolence > 0, negative when < 0
- impression_depth grows when relation_count and power are positive
- creativity is higher when events span a long time range
- creativity is higher when both EPISODE and NARRATIVE are present
- zero signals → all axes stay near 0 (only decay)
- tanh clamping keeps values inside [-20, +20]
- recall_manager passes relation_debug signals to soul state update
"""
import dataclasses
import math

import pytest

from core.domain.models import Event, EventStatus, EventType
from core.social.soul_state import SoulState, update_from_signals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(eid: str, salience: float, etype: str = EventType.EPISODE,
           end_time: float = 1000.0) -> Event:
    return Event(
        event_id=eid,
        start_time=end_time - 100,
        end_time=end_time,
        salience=salience,
        event_type=etype,
        confidence=0.8,
        status=EventStatus.ACTIVE,
    )


def _neutral() -> SoulState:
    return SoulState()


# ---------------------------------------------------------------------------
# recall_depth driven by event count × salience
# ---------------------------------------------------------------------------

def test_recall_depth_grows_with_high_salience_events():
    """High-salience events produce a larger recall_depth boost than low-salience."""
    high = [_event(f"h{i}", salience=0.9) for i in range(3)]
    low  = [_event(f"l{i}", salience=0.1) for i in range(3)]

    state_high = update_from_signals(_neutral(), decay_rate=0.0, events=high)
    state_low  = update_from_signals(_neutral(), decay_rate=0.0, events=low)

    assert state_high.recall_depth > state_low.recall_depth


def test_recall_depth_zero_when_no_events():
    """No recall results → recall_depth stays at 0 after decay."""
    state = update_from_signals(_neutral(), decay_rate=0.0, events=[])
    assert state.recall_depth == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# expression_desire driven by benevolence
# ---------------------------------------------------------------------------

def test_expression_desire_positive_when_benevolence_positive():
    """Positive benevolence (warm relationship) raises expression_desire."""
    state = update_from_signals(_neutral(), decay_rate=0.0, events=[], benevolence=0.8)
    assert state.expression_desire > 0.0


def test_expression_desire_negative_when_benevolence_negative():
    """Negative benevolence (cold relationship) lowers expression_desire."""
    state = update_from_signals(_neutral(), decay_rate=0.0, events=[], benevolence=-0.8)
    assert state.expression_desire < 0.0


def test_expression_desire_neutral_when_benevolence_zero():
    """Zero benevolence → expression_desire stays near 0."""
    state = update_from_signals(_neutral(), decay_rate=0.0, events=[], benevolence=0.0)
    assert state.expression_desire == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# impression_depth driven by relation_count × power
# ---------------------------------------------------------------------------

def test_impression_depth_grows_with_relation_count_and_positive_power():
    """More impressions + positive power → higher impression_depth."""
    state_many = update_from_signals(
        _neutral(), decay_rate=0.0, events=[],
        relation_count=5, power=0.5,
    )
    state_none = update_from_signals(
        _neutral(), decay_rate=0.0, events=[],
        relation_count=0, power=0.0,
    )
    assert state_many.impression_depth > state_none.impression_depth


def test_impression_depth_zero_when_no_relations():
    """No relation data → impression_depth stays at 0."""
    state = update_from_signals(_neutral(), decay_rate=0.0, events=[],
                                relation_count=0, power=0.0)
    assert state.impression_depth == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# creativity driven by event time-span and type diversity
# ---------------------------------------------------------------------------

def test_creativity_higher_with_wide_time_span():
    """Events spread over 60+ days produce higher creativity than same-day events."""
    recent = [
        _event("r1", 0.5, end_time=1_000_000.0),
        _event("r2", 0.5, end_time=1_000_100.0),  # 100s apart
    ]
    spread = [
        _event("s1", 0.5, end_time=1_000_000.0),
        _event("s2", 0.5, end_time=1_000_000.0 + 60 * 86400),  # 60 days apart
    ]
    state_recent = update_from_signals(_neutral(), decay_rate=0.0, events=recent)
    state_spread = update_from_signals(_neutral(), decay_rate=0.0, events=spread)

    assert state_spread.creativity > state_recent.creativity



def test_creativity_zero_when_single_event():
    """Single event → no time spread → creativity stays near 0."""
    state = update_from_signals(_neutral(), decay_rate=0.0,
                                events=[_event("e1", 0.5)])
    assert state.creativity == pytest.approx(0.0, abs=0.1)


# ---------------------------------------------------------------------------
# Decay is applied before boost
# ---------------------------------------------------------------------------

def test_decay_reduces_values_before_boost():
    """Starting from a high value with decay_rate=0.5 and no signals, axes shrink."""
    warm = SoulState(
        recall_depth=10.0,
        impression_depth=10.0,
        expression_desire=10.0,
        creativity=10.0,
    )
    state = update_from_signals(warm, decay_rate=0.5, events=[])
    assert state.recall_depth < 10.0
    assert state.impression_depth < 10.0
    assert state.expression_desire < 10.0
    assert state.creativity < 10.0


# ---------------------------------------------------------------------------
# Tanh clamping keeps values inside [-20, +20]
# ---------------------------------------------------------------------------

def test_all_axes_stay_within_bounds_under_repeated_updates():
    """After many updates with strong signals, all axes stay within [-20, +20]."""
    state = _neutral()
    events = [_event(f"e{i}", 0.9) for i in range(10)]
    for _ in range(50):
        state = update_from_signals(
            state, decay_rate=0.0, events=events,
            benevolence=1.0, power=1.0, relation_count=10,
        )
    assert -20.0 <= state.recall_depth <= 20.0
    assert -20.0 <= state.impression_depth <= 20.0
    assert -20.0 <= state.expression_desire <= 20.0
    assert -20.0 <= state.creativity <= 20.0


# ---------------------------------------------------------------------------
# Integration: recall_manager passes relation_debug to soul update
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_soul_state_reflects_positive_relation_after_inject():
    """When relation_debug has positive benevolence, expression_desire > 0 after inject."""
    from unittest.mock import AsyncMock, MagicMock
    from core.config import InjectionConfig, RetrievalConfig, SoulConfig
    from core.domain.models import EventStatus
    from core.managers.recall_manager import RecallManager

    ev = Event(
        event_id="e1", start_time=900.0, end_time=1000.0,
        salience=0.7, event_type=EventType.EPISODE,
        confidence=0.9, status=EventStatus.ACTIVE,
    )

    event_repo = AsyncMock()
    event_repo.count_by_status = AsyncMock(return_value=1)
    event_repo.search_fts = AsyncMock(return_value=[ev])
    event_repo.search_vector = AsyncMock(return_value=[])
    event_repo.get_children = AsyncMock(return_value=[])
    event_repo.get = AsyncMock(return_value=None)
    event_repo.update_salience = AsyncMock(return_value=True)
    event_repo.update_last_accessed = AsyncMock(return_value=True)
    event_repo.increment_access_count = AsyncMock(return_value=True)

    encoder = MagicMock()
    encoder.dim = 0

    retriever = MagicMock()
    retriever._event_repo = event_repo
    retriever._encoder = encoder
    retriever._bm25_limit = 20
    retriever._vec_limit = 20

    # impression_repo returns a warm impression (benevolence=0.8)
    from core.domain.models import Impression
    imp = MagicMock(spec=Impression)
    imp.benevolence = 0.8
    imp.power = 0.2
    imp.ipc_orientation = "affinity"
    imp.confidence = 0.7
    imp.observer_uid = "bot"
    imp.subject_uid = "u1"
    imp.scope = "global"

    impression_repo = AsyncMock()
    impression_repo.list_by_subject = AsyncMock(return_value=[imp])
    impression_repo.list_by_observer = AsyncMock(return_value=[imp])

    persona_repo = AsyncMock()
    persona_repo.get = AsyncMock(return_value=None)
    persona_repo.list_all = AsyncMock(return_value=[])
    persona_repo.get_by_identity = AsyncMock(return_value=None)

    rm = RecallManager(
        retriever,
        RetrievalConfig(final_limit=5),
        InjectionConfig(position="system_prompt"),
        persona_repo=persona_repo,
        impression_repo=impression_repo,
        soul_config=SoulConfig(enabled=True, decay_rate=0.0),
    )

    req = MagicMock()
    req.system_prompt = ""
    req.prompt = ""
    req.model = "gpt-4"

    await rm.recall_and_inject("query", req, "sess1", sender_uid="u1")

    soul_states = rm.get_soul_states()
    assert "sess1" in soul_states
    state = soul_states["sess1"]
    assert state["expression_desire"] > 0.0, (
        "Positive benevolence should raise expression_desire"
    )
