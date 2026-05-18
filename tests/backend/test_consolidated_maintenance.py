import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from core.tasks.synthesis import run_consolidated_maintenance
from core.domain.models import Event, Persona, Impression
from core.repository.memory import InMemoryEventRepository, InMemoryPersonaRepository, InMemoryImpressionRepository

class _MockResponse:
    def __init__(self, text: str):
        self.completion_text = text

class _MockProvider:
    def __init__(self, response: str):
        self._response = response
    async def text_chat(self, prompt: str = "", system_prompt: str = ""):
        return _MockResponse(self._response)

@pytest.mark.asyncio
async def test_run_consolidated_maintenance():
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    ir = InMemoryImpressionRepository()
    
    # Setup data
    await pr.upsert(Persona("u1", [], "Alice", {}, 0.5, 1000.0, 2000.0))
    await pr.upsert(Persona("u2", [], "Bob", {}, 0.5, 1000.0, 2000.0))
    
    await er.upsert(Event(event_id="e1", participants=["u1", "u2"], topic="topic1", end_time=1500.0))
    
    await ir.upsert(Impression("u1", "u2", "affinity", 0.6, 0.3, 0.0, 0.0, 0.0, "global", [], 1000.0))
    
    provider = _MockProvider('{"description": "new Alice", "big_five": {"O": 0.8}}')
    
    result = await run_consolidated_maintenance(pr, er, ir, lambda: provider)
    
    assert result["synthesized"] >= 1
    assert result["recalculated"] == 1
    
    # Check synthesis
    updated_alice = await pr.get("u1")
    assert updated_alice.persona_attrs["description"] == "new Alice"
    
    # Check recalculation
    updated_imp = await ir.get("u1", "u2", "global")
    assert "e1" in updated_imp.evidence_event_ids
    assert updated_imp.affect_intensity > 0
