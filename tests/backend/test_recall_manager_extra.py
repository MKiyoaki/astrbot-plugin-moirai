import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from core.managers.recall_manager import RecallManager, _classify_granularity
from core.domain.models import Event, EventType, Persona, Impression
from core.config import RetrievalConfig, InjectionConfig, SoulConfig

@pytest.fixture
def recall_manager():
    retriever = AsyncMock()
    retrieval_cfg = RetrievalConfig(final_limit=10)
    injection_cfg = InjectionConfig(position="system_prompt")
    persona_repo = AsyncMock()
    impression_repo = AsyncMock()
    soul_cfg = SoulConfig(enabled=True)
    return RecallManager(retriever, retrieval_cfg, injection_cfg, persona_repo, impression_repo, soul_cfg), retriever, persona_repo, impression_repo

def test_classify_granularity():
    assert _classify_granularity("总结一下最近发生了什么") == "macro"
    assert _classify_granularity("他具体怎么说的") == "micro"
    assert _classify_granularity("你好") == "both"

@pytest.mark.asyncio
async def test_recall_macro_granularity(recall_manager):
    rm, retriever, pr, ir = recall_manager
    
    # Mock retriever results
    narrative_ev = Event(event_id="n1", event_type=EventType.NARRATIVE, end_time=1000.0)
    episode_ev = Event(event_id="e1", event_type=EventType.EPISODE, end_time=1000.0)
    
    retriever.search_raw.side_effect = lambda q, **kwargs: (
        ([narrative_ev], [narrative_ev]) if kwargs.get("event_type") == EventType.NARRATIVE
        else ([episode_ev], [episode_ev])
    )
    
    events = await rm.recall("最近总结")
    assert any(e.event_id == "n1" for e in events)
    assert any(e.event_id == "e1" for e in events)

@pytest.mark.asyncio
async def test_recall_and_inject_system_prompt(recall_manager):
    rm, retriever, pr, ir = recall_manager
    rm._rcfg.final_limit = 5
    
    # Mock events
    e1 = Event(event_id="e1", topic="test", end_time=1000.0)
    retriever.search_raw.return_value = ([e1], [e1])
    
    req = MagicMock()
    req.system_prompt = "Existing prompt"
    req.prompt = ""
    req.model = "gpt-4"
    
    # Mock persona and impressions
    pr.get.return_value = Persona("u1", [], "Alice", {"big_five": {"O": 0.5}}, 0.5, 0.0, 0.0)
    ir.list_by_subject.return_value = []
    ir.list_by_observer.return_value = []
    
    count = await rm.recall_and_inject("query", req, "s1", sender_uid="u1")
    
    assert count == 1
    assert "相关历史记忆" in req.system_prompt
    assert "Alice" in req.system_prompt

@pytest.mark.asyncio
async def test_recall_and_inject_fake_tool_call(recall_manager):
    rm, retriever, pr, ir = recall_manager
    rm._icfg.position = "fake_tool_call"
    
    e1 = Event(event_id="e1", topic="test", end_time=1000.0)
    retriever.search_raw.return_value = ([e1], [e1])
    
    req = MagicMock()
    req.contexts = []
    req.system_prompt = ""
    req.prompt = ""
    req.model = "gpt-4" # supports tool calls
    
    count = await rm.recall_and_inject("query", req, "s1")
    assert count == 1
    assert len(req.contexts) == 2 # assistant + tool result

@pytest.mark.asyncio
async def test_clear_previous_injection(recall_manager):
    rm, retriever, pr, ir = recall_manager
    
    req = MagicMock()
    from core.config import MEMORY_INJECTION_HEADER, MEMORY_INJECTION_FOOTER
    injected_text = f"{MEMORY_INJECTION_HEADER}\nsome content\n{MEMORY_INJECTION_FOOTER}"
    req.system_prompt = f"Original {injected_text}"
    req.prompt = ""
    req.contexts = [{"role": "user", "content": f"Hi {injected_text}"}]
    
    removed = rm.clear_previous_injection(req)
    assert removed >= 2
    assert injected_text not in req.system_prompt
    assert injected_text not in req.contexts[0]["content"]

@pytest.mark.asyncio
async def test_soul_state_update(recall_manager):
    rm, retriever, pr, ir = recall_manager
    req = MagicMock()
    req.system_prompt = ""
    req.prompt = ""
    retriever.search_raw.return_value = ([], []) # no events
    
    # First call - init soul state
    await rm.recall_and_inject("hi", req, "s1")
    state1 = rm._soul_states["s1"]
    
    # Second call - state should change (decay)
    await rm.recall_and_inject("hi", req, "s1")
    state2 = rm._soul_states["s1"]
    assert state2 is not state1
