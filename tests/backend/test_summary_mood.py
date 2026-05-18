
import pytest
import json
from pathlib import Path
from core.domain.models import Event, Impression, MessageRef
from core.repository.memory import InMemoryEventRepository, InMemoryImpressionRepository
from core.tasks.summary import run_group_summary
from core.config import SummaryConfig

class MockResponse:
    def __init__(self, text):
        self.completion_text = text

class MockProvider:
    def __init__(self, mood_json):
        self.mood_json = mood_json
        self.calls = []
    async def text_chat(self, prompt, system_prompt):
        self.calls.append(prompt)
        # Check if it's the unified prompt
        if "summary" in system_prompt and "mood" in system_prompt:
            unified_data = {
                "summary": "这是统一总结的主要话题内容",
                "mood": json.loads(self.mood_json)
            }
            return MockResponse(json.dumps(unified_data))
        
        if "情感动态" in system_prompt or "情感动态" in prompt:
            return MockResponse(self.mood_json)
        return MockResponse("主要话题总结内容")

@pytest.mark.asyncio
async def test_mood_source_option_b_llm(tmp_path):
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    # Add an event
    await er.upsert(Event(
        event_id="e1", group_id="g1", participants=["u1", "u2"],
        topic="话题1", start_time=1000, end_time=2000,
        interaction_flow=[], chat_content_tags=[], salience=0.5, confidence=0.8
    ))
    
    mood_json = '{"orientation": "active", "benevolence": 0.5, "power": 0.5, "positions": {"u1": "dominant", "u2": "affinity"}}'
    provider = MockProvider(mood_json)
    
    cfg = SummaryConfig(mood_source="llm")
    await run_group_summary(er, tmp_path, lambda: provider, summary_config=cfg, impression_repo=ir)
    
    summary_file = list((tmp_path / "groups" / "g1" / "summaries").glob("*.md"))[0]
    content = summary_file.read_text(encoding="utf-8")
    
    assert "[情感动态]" in content
    assert "这是统一总结的主要话题内容" in content
    assert "群体情感动态整体偏向[活跃]" in content
    assert "u1处于群体中的掌控位置" in content
    # Note: LLM returns English keys which are translated to Chinese in the summary

@pytest.mark.asyncio
async def test_mood_source_option_a_db(tmp_path):
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    
    # Default bot_uid in _build_mood_section_db is "bot" if no persona_repo
    # Add impressions for u1 and u2
    await ir.upsert(Impression(
        observer_uid="bot", subject_uid="u1", 
        ipc_orientation="dominant", benevolence=0.2, power=0.8,
        affect_intensity=0.6, r_squared=0.8, confidence=0.9,
        scope="global",
        evidence_event_ids=[],
        last_reinforced_at=1000.0
    ))
    await ir.upsert(Impression(
        observer_uid="bot", subject_uid="u2", 
        ipc_orientation="affinity", benevolence=0.8, power=0.1,
        affect_intensity=0.5, r_squared=0.9, confidence=0.9,
        scope="global",
        evidence_event_ids=[],
        last_reinforced_at=1000.0
    ))
    
    await er.upsert(Event(
        event_id="e1", group_id="g1", participants=["u1", "u2"],
        topic="话题1", start_time=1000, end_time=2000,
        interaction_flow=[], chat_content_tags=[], salience=0.5, confidence=0.8
    ))
    
    provider = MockProvider("{}") # Should not be called for mood if Option A works
    
    cfg = SummaryConfig(mood_source="impression_db")
    await run_group_summary(er, tmp_path, lambda: provider, summary_config=cfg, impression_repo=ir)
    
    summary_file = list((tmp_path / "groups" / "g1" / "summaries").glob("*.md"))[0]
    content = summary_file.read_text(encoding="utf-8")
    
    assert "[情感动态]" in content
    # Average B: (0.2+0.8)/2 = 0.5, Average P: (0.8+0.1)/2 = 0.45
    assert "[平均亲和度：+0.50；平均支配度：+0.45]" in content
    assert "u1处于群体中的掌控位置" in content
    assert "u2处于群体中的亲和位置" in content

@pytest.mark.asyncio
async def test_mood_source_fallback_to_llm(tmp_path):
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository() # Empty DB
    
    await er.upsert(Event(
        event_id="e1", group_id="g1", participants=["u1", "u2"],
        topic="话题1", start_time=1000, end_time=2000,
        interaction_flow=[], chat_content_tags=[], salience=0.5, confidence=0.8
    ))
    
    mood_json = '{"orientation": "社交回退", "benevolence": 0.1, "power": 0.1, "positions": {}}'
    provider = MockProvider(mood_json)
    
    # Even if set to impression_db, it should fallback to LLM because DB is empty
    cfg = SummaryConfig(mood_source="impression_db")
    await run_group_summary(er, tmp_path, lambda: provider, summary_config=cfg, impression_repo=ir)
    
    summary_file = list((tmp_path / "groups" / "g1" / "summaries").glob("*.md"))[0]
    content = summary_file.read_text(encoding="utf-8")
    
    assert "群体情感动态整体偏向[社交回退]" in content
