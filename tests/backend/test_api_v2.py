import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
from core.api import (
    event_to_dict, 
    persona_to_dict, 
    impression_to_dict, 
    get_stats, 
    list_events,
    get_graph
)
from core.domain.models import Event, Persona, Impression, EventStatus

@pytest.fixture
def mock_repos():
    persona_repo = AsyncMock()
    event_repo = AsyncMock()
    impression_repo = AsyncMock()
    return persona_repo, event_repo, impression_repo

def test_serializers():
    # Test event_to_dict
    event = Event(
        event_id="test_e",
        start_time=1700000000.0,
        end_time=1700001000.0,
        group_id="g1",
        participants=["u1"],
        topic="test topic",
        summary="test summary",
        salience=0.8,
        confidence=0.9,
        chat_content_tags=["tag1"],
        status=EventStatus.ACTIVE
    )
    d = event_to_dict(event)
    assert d["id"] == "test_e"
    assert d["salience"] == 0.8
    assert "start" in d
    
    # Test persona_to_dict
    persona = Persona(
        uid="u1",
        primary_name="Alice",
        confidence=0.7,
        created_at=1700000000.0,
        last_active_at=1700000000.0,
        bound_identities=[("qq", "123")],
        persona_attrs={}
    )
    d = persona_to_dict(persona)
    assert d["uid"] == "u1"
    assert d["primary_name"] == "Alice"
    assert d["is_bot"] is False
    
    # Test impression_to_dict
    imp = Impression(
        observer_uid="u1",
        subject_uid="u2",
        scope="g1",
        ipc_orientation="亲和",
        benevolence=0.5,
        power=0.0,
        affect_intensity=0.8,
        r_squared=0.9,
        confidence=0.9,
        evidence_event_ids=["e1"],
        last_reinforced_at=1700000000.0
    )
    d = impression_to_dict(imp)
    assert d["observer_uid"] == "u1"
    assert d["subject_uid"] == "u2"
    assert d["id"] == "u1--u2--g1"

@pytest.mark.asyncio
async def test_get_stats_comprehensive(mock_repos, tmp_path):
    pr, er, ir = mock_repos
    
    # Setup mocks
    pr.list_all.return_value = [Persona(
        uid="u1", 
        primary_name="U1", 
        bound_identities=[], 
        persona_attrs={}, 
        confidence=1.0, 
        created_at=0.0, 
        last_active_at=0.0
    )]
    er.list_group_ids.return_value = ["g1"]
    er.count_by_status.side_effect = lambda s: 10 if s == EventStatus.ACTIVE else 5
    er.list_by_status.return_value = [Event(event_id="e1", is_locked=True)]
    er.list_by_group.return_value = [Event(event_id="e1", is_locked=True)]
    ir.list_by_observer.return_value = [Impression(
        observer_uid="u1", 
        subject_uid="u2", 
        ipc_orientation="亲和",
        benevolence=0.0,
        power=0.0,
        affect_intensity=0.0,
        r_squared=0.0,
        confidence=0.0,
        scope="g1",
        evidence_event_ids=[],
        last_reinforced_at=0.0
    )]
    
    # Mock data_dir for summaries
    summary_dir = tmp_path / "g1" / "summaries"
    summary_dir.mkdir(parents=True)
    (summary_dir / "2023-11-15.md").write_text("test summary content")
    
    # Mock llm_manager
    mock_llm = MagicMock()
    mock_llm.get_stats.return_value = {"total_tokens": 100}
    
    # Mock context_manager
    mock_cm = MagicMock()
    mock_window = MagicMock()
    mock_window.session_id = "s1"
    mock_window.group_id = "g1"
    mock_window.message_count = 10
    mock_cm._windows = {"s1": mock_window}
    
    stats = await get_stats(
        pr, er, ir, 
        data_dir=tmp_path, 
        llm_manager=mock_llm,
        context_manager=mock_cm,
        plugin_version="1.0.0"
    )
    
    assert stats["personas"] == 1
    assert stats["events"] == 10
    assert stats["archived_events"] == 5
    assert stats["locked_count"] == 1
    assert stats["summaries"] == 1
    assert stats["version"] == "1.0.0"
    assert stats["llm_stats"] == {"total_tokens": 100}
    assert len(stats["active_sessions"]) == 1
    assert stats["active_sessions"][0]["session_id"] == "s1"

@pytest.mark.asyncio
async def test_list_events(mock_repos):
    pr, er, ir = mock_repos
    event = Event(event_id="e1", status=EventStatus.ACTIVE)
    
    # Case 1: group_id provided
    er.list_by_group.return_value = [event]
    res = await list_events(er, group_id="g1")
    assert len(res["items"]) == 1
    er.list_by_group.assert_called_with("g1", limit=100)
    
    # Case 2: no group_id
    er.list_group_ids.return_value = ["g1", "g2"]
    er.list_by_group.return_value = [event]
    res = await list_events(er, group_id=None, limit=10)
    assert len(res["items"]) == 2 # 1 from g1, 1 from g2
    
@pytest.mark.asyncio
async def test_get_graph(mock_repos):
    pr, er, ir = mock_repos
    pr.list_all.return_value = [Persona(
        uid="u1", 
        primary_name="U1", 
        bound_identities=[], 
        persona_attrs={}, 
        confidence=1.0, 
        created_at=0.0, 
        last_active_at=0.0
    )]
    ir.list_by_observer.return_value = [Impression(
        observer_uid="u1", 
        subject_uid="u2", 
        scope="g1",
        ipc_orientation="亲和",
        benevolence=0.0,
        power=0.0,
        affect_intensity=0.0,
        r_squared=0.0,
        confidence=0.0,
        evidence_event_ids=[],
        last_reinforced_at=0.0
    )]
    
    res = await get_graph(pr, ir)
    assert len(res["nodes"]) == 1
    assert len(res["edges"]) == 1
    assert res["nodes"][0]["uid"] == "u1"
    assert res["edges"][0]["observer_uid"] == "u1"
