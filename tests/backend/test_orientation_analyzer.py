import pytest
import time
from unittest.mock import AsyncMock, MagicMock
from core.social.orientation_analyzer import SocialOrientationAnalyzer
from core.domain.models import Impression, BigFiveVector, Event
from core.boundary.window import MessageWindow, RawMessage

@pytest.fixture
def analyzer():
    ir = AsyncMock()
    er = AsyncMock()
    cfg = MagicMock()
    cfg.impression_trigger_debounce_hours = 1.0
    cfg.impression_event_trigger_threshold = 5
    cfg.impression_update_alpha = 0.4
    return SocialOrientationAnalyzer(ir, er, cfg), ir, er, cfg

@pytest.mark.asyncio
async def test_analyze_scientific_path(analyzer):
    soa, ir, er, cfg = analyzer
    
    # Setup window
    window = MessageWindow("s1", "g1")
    window.add_message("u1", "msg1", 1000.0)
    window.add_message("u2", "msg2", 1005.0)
    
    # Setup Big Five
    bf_buffer = MagicMock()
    bf_buffer.get_cached.side_effect = lambda uid: (
        BigFiveVector(0.5, 0.0, 0.5, 0.5, 0.0) if uid == "u1" else BigFiveVector(0.0, 0.0, 0.0, 0.0, 0.0)
    )
    
    ir.get.return_value = None
    
    updated = await soa.analyze(window, bf_buffer, event_id="e1")
    
    # u1 observed u2 (scientific path)
    # u2 observed u1 (heuristic path - skip if no shared events)
    assert updated >= 1
    ir.upsert.assert_called()
    call_args = ir.upsert.call_args[0][0]
    assert call_args.observer_uid == "u1"
    assert call_args.subject_uid == "u2"
    assert "e1" in call_args.evidence_event_ids

@pytest.mark.asyncio
async def test_analyze_heuristic_path(analyzer):
    soa, ir, er, cfg = analyzer
    
    window = MessageWindow("s1", "global")
    window.add_message("u1", "m1", 1000.0)
    window.add_message("u2", "m2", 1005.0)
    
    bf_buffer = MagicMock()
    bf_buffer.get_cached.return_value = BigFiveVector(0.0, 0.0, 0.0, 0.0, 0.0)
    
    ir.get.return_value = None
    
    # Mock shared events
    er.list_by_participant.side_effect = lambda uid, limit: [
        Event(event_id=f"e{i}", group_id=None) for i in range(10)
    ]
    
    updated = await soa.analyze(window, bf_buffer, scope="global")
    
    assert updated == 2 # u1->u2 and u2->u1
    ir.upsert.assert_called()

@pytest.mark.asyncio
async def test_analyze_debounce(analyzer):
    soa, ir, er, cfg = analyzer
    
    window = MessageWindow("s1", "g1")
    window.add_message("u1", "m1", 1000.0)
    window.add_message("u2", "m2", 1005.0)
    
    bf_buffer = MagicMock()
    bf_buffer.get_cached.return_value = BigFiveVector(0.0, 0.0, 0.0, 0.0, 0.0)
    
    # Existing impression is recent
    ir.get.return_value = Impression("u1", "u2", "affinity", 0.0, 0.0, 0.0, 0.0, 0.0, "global", [], time.time())
    
    updated = await soa.analyze(window, bf_buffer)
    assert updated == 0

@pytest.mark.asyncio
async def test_upsert_ema(analyzer):
    soa, ir, er, cfg = analyzer
    
    existing = Impression("u1", "u2", "affinity", 0.2, 0.1, 0.0, 0.0, 0.0, "g1", ["old_e"], 1000.0)
    ir.get.return_value = existing
    
    window = MessageWindow("s1", "g1")
    
    # Call internal _upsert_impression
    await soa._upsert_impression("u1", "u2", "affinity", 0.8, 0.5, 0.9, 0.7, "g1", window, event_id="new_e")
    
    ir.upsert.assert_called_once()
    imp = ir.upsert.call_args[0][0]
    # alpha=0.4. 0.4 * 0.8 + 0.6 * 0.2 = 0.32 + 0.12 = 0.44
    assert pytest.approx(imp.benevolence) == 0.44
    assert "old_e" in imp.evidence_event_ids
    assert "new_e" in imp.evidence_event_ids
