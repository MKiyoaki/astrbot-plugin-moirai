import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from core.social.big_five_scorer import LLMBigFiveScorer, BigFiveBuffer, BigFiveVector

class _MockResponse:
    def __init__(self, text: str):
        self.completion_text = text

@pytest.mark.asyncio
async def test_llm_big_five_scorer_success():
    scorer = LLMBigFiveScorer()
    provider = AsyncMock()
    provider.text_chat.return_value = _MockResponse('{"O": 0.5, "C": 0.1, "E": -0.2, "A": 0.8, "N": 0.0}')
    
    vec = await scorer.score("hello", lambda: provider)
    
    assert vec.openness == 0.5
    assert vec.agreeableness == 0.8
    assert vec.extraversion == -0.2

@pytest.mark.asyncio
async def test_llm_big_five_scorer_parse_error():
    scorer = LLMBigFiveScorer()
    provider = AsyncMock()
    provider.text_chat.return_value = _MockResponse('invalid json')
    
    vec = await scorer.score("hello", lambda: provider)
    
    assert vec.openness == 0.0
    assert vec.conscientiousness == 0.0

@pytest.mark.asyncio
async def test_big_five_buffer_accumulation():
    scorer = AsyncMock()
    buffer = BigFiveBuffer(x_messages=3, scorer=scorer)
    
    buffer.add_message("u1", "m1")
    buffer.add_message("u1", "m2")
    assert buffer.count("u1") == 2
    assert buffer.maybe_score("u1", lambda: None) is None
    
    buffer.add_message("u1", "m3")
    assert buffer.count("u1") == 3
    
    task = buffer.maybe_score("u1", lambda: None)
    assert task is not None
    await task
    
    assert buffer.count("u1") == 0
    scorer.score.assert_called_once()
    assert "m1\nm2\nm3" in scorer.score.call_args[0][0]

@pytest.mark.asyncio
async def test_big_five_buffer_cache():
    scorer = AsyncMock()
    scorer.score.return_value = BigFiveVector(0.1, 0.2, 0.3, 0.4, 0.5)
    buffer = BigFiveBuffer(x_messages=1, scorer=scorer)
    
    buffer.add_message("u1", "hello")
    await buffer.maybe_score("u1", lambda: None)
    
    vec = buffer.get_cached("u1")
    assert vec.openness == 0.1
    assert vec.neuroticism == 0.5

@pytest.mark.asyncio
async def test_big_five_buffer_evict():
    buffer = BigFiveBuffer(x_messages=1)
    buffer.add_message("u1", "hello")
    buffer.evict("u1")
    assert buffer.count("u1") == 0
