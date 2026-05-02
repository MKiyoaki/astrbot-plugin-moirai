"""Unit tests for the domain model layer.

No I/O, no external dependencies. Tests run in < 1 second.
"""

import pytest

from core.domain.models import Event, Impression, MessageRef, Persona

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = 1_000_000.0


def make_persona(**overrides) -> Persona:
    defaults: dict = dict(
        uid="uid-alice",
        bound_identities=[("qq", "12345")],
        primary_name="Alice",
        persona_attrs={"affect_type": "warm", "content_tags": ["tech"]},
        confidence=0.8,
        created_at=NOW,
        last_active_at=NOW,
    )
    defaults.update(overrides)
    return Persona(**defaults)


def make_event(**overrides) -> Event:
    defaults: dict = dict(
        event_id="evt-001",
        group_id="grp-1",
        start_time=NOW,
        end_time=NOW + 600,
        participants=["uid-alice", "uid-bot"],
        interaction_flow=[],
        topic="项目讨论",
        chat_content_tags=["工作", "产品"],
        salience=0.7,
        confidence=0.9,
        inherit_from=[],
        last_accessed_at=NOW,
    )
    defaults.update(overrides)
    return Event(**defaults)


def make_impression(**overrides) -> Impression:
    defaults: dict = dict(
        observer_uid="uid-bot",
        subject_uid="uid-alice",
        relation_type="friend",
        affect=0.6,
        intensity=0.8,
        confidence=0.75,
        scope="global",
        evidence_event_ids=["evt-001"],
        last_reinforced_at=NOW,
    )
    defaults.update(overrides)
    return Impression(**defaults)


# ---------------------------------------------------------------------------
# MessageRef
# ---------------------------------------------------------------------------


def test_message_ref_is_frozen() -> None:
    ref = MessageRef(
        sender_uid="uid-alice",
        timestamp=NOW,
        content_hash="abc123",
        content_preview="Hello",
    )
    with pytest.raises((AttributeError, TypeError)):
        ref.sender_uid = "other"  # type: ignore[misc]


def test_message_ref_equality() -> None:
    r1 = MessageRef("uid-a", NOW, "hash", "preview")
    r2 = MessageRef("uid-a", NOW, "hash", "preview")
    assert r1 == r2


# ---------------------------------------------------------------------------
# Persona
# ---------------------------------------------------------------------------


def test_persona_valid() -> None:
    p = make_persona()
    assert p.uid == "uid-alice"
    assert p.primary_name == "Alice"
    assert p.confidence == 0.8


def test_persona_confidence_zero_and_one_are_valid() -> None:
    make_persona(confidence=0.0)
    make_persona(confidence=1.0)


@pytest.mark.parametrize("bad_conf", [-0.01, 1.01, 2.0, -1.0])
def test_persona_confidence_out_of_range(bad_conf: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        make_persona(confidence=bad_conf)


def test_persona_multiple_bound_identities() -> None:
    p = make_persona(
        bound_identities=[("qq", "111"), ("telegram", "222"), ("wechat", "333")]
    )
    assert len(p.bound_identities) == 3


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


def test_event_valid() -> None:
    e = make_event()
    assert e.event_id == "evt-001"
    assert e.salience == 0.7
    assert e.group_id == "grp-1"


def test_event_private_chat_has_none_group_id() -> None:
    e = make_event(group_id=None)
    assert e.group_id is None


def test_event_salience_boundary_values() -> None:
    make_event(salience=0.0)
    make_event(salience=1.0)


@pytest.mark.parametrize("bad_sal", [-0.01, 1.01])
def test_event_salience_out_of_range(bad_sal: float) -> None:
    with pytest.raises(ValueError, match="salience"):
        make_event(salience=bad_sal)


@pytest.mark.parametrize("bad_conf", [-0.01, 1.01])
def test_event_confidence_out_of_range(bad_conf: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        make_event(confidence=bad_conf)


def test_event_start_after_end_raises() -> None:
    with pytest.raises(ValueError, match="start_time"):
        make_event(start_time=NOW + 100, end_time=NOW)


def test_event_start_equals_end_is_valid() -> None:
    make_event(start_time=NOW, end_time=NOW)


def test_event_inherit_from_multiple_parents() -> None:
    e = make_event(inherit_from=["evt-parent-a", "evt-parent-b"])
    assert len(e.inherit_from) == 2


def test_event_with_interaction_flow() -> None:
    refs = [
        MessageRef("uid-alice", NOW, "h1", "hi"),
        MessageRef("uid-bot", NOW + 1, "h2", "hello"),
    ]
    e = make_event(interaction_flow=refs)
    assert len(e.interaction_flow) == 2
    assert e.interaction_flow[0].sender_uid == "uid-alice"


# ---------------------------------------------------------------------------
# Impression
# ---------------------------------------------------------------------------


def test_impression_valid() -> None:
    imp = make_impression()
    assert imp.observer_uid == "uid-bot"
    assert imp.subject_uid == "uid-alice"
    assert imp.affect == 0.6


def test_impression_directional_asymmetry() -> None:
    fwd = make_impression(observer_uid="A", subject_uid="B")
    rev = make_impression(observer_uid="B", subject_uid="A")
    assert fwd.observer_uid != rev.observer_uid


def test_impression_affect_extremes_valid() -> None:
    make_impression(affect=-1.0)
    make_impression(affect=1.0)
    make_impression(affect=0.0)


@pytest.mark.parametrize("bad_affect", [-1.01, 1.01, 2.0])
def test_impression_affect_out_of_range(bad_affect: float) -> None:
    with pytest.raises(ValueError, match="affect"):
        make_impression(affect=bad_affect)


@pytest.mark.parametrize("bad_intensity", [-0.01, 1.01])
def test_impression_intensity_out_of_range(bad_intensity: float) -> None:
    with pytest.raises(ValueError, match="intensity"):
        make_impression(intensity=bad_intensity)


@pytest.mark.parametrize("bad_conf", [-0.01, 1.01])
def test_impression_confidence_out_of_range(bad_conf: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        make_impression(confidence=bad_conf)


def test_impression_group_scope() -> None:
    imp = make_impression(scope="grp-42")
    assert imp.scope == "grp-42"


def test_impression_evidence_event_ids() -> None:
    imp = make_impression(evidence_event_ids=["e1", "e2", "e3"])
    assert len(imp.evidence_event_ids) == 3
