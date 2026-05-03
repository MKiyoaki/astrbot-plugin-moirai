"""Tests for the LLM event extractor — parser, fallback, and full pipeline."""
from __future__ import annotations

import dataclasses

import pytest

from core.boundary.window import MessageWindow
from core.domain.models import Event, MessageRef
from core.extractor.extractor import EventExtractor
from core.extractor.parser import fallback_extraction, parse_llm_output
from core.extractor.prompts import build_user_prompt
from core.repository.memory import InMemoryEventRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_window(msgs: list[tuple[str, str, str]]) -> MessageWindow:
    """(uid, display_name, text) triples → MessageWindow starting at t=1000."""
    w = MessageWindow(session_id="s", group_id="g1", start_time=1000.0, last_message_time=1000.0)
    for i, (uid, name, text) in enumerate(msgs):
        w.add_message(uid, text, 1000.0 + i * 10, name)
    return w


def make_event(event_id: str = "ev1") -> Event:
    return Event(
        event_id=event_id,
        group_id="g1",
        start_time=1000.0,
        end_time=1100.0,
        participants=["uid-a"],
        interaction_flow=[],
        topic="",
        chat_content_tags=[],
        salience=0.5,
        confidence=0.5,
        inherit_from=[],
        last_accessed_at=1100.0,
    )


# ---------------------------------------------------------------------------
# parse_llm_output tests
# ---------------------------------------------------------------------------

def test_parse_clean_json() -> None:
    raw = '{"topic": "项目讨论", "chat_content_tags": ["工作", "计划"], "salience": 0.7, "confidence": 0.9}'
    result = parse_llm_output(raw)
    assert result is not None
    assert result["topic"] == "项目讨论"
    assert result["chat_content_tags"] == ["工作", "计划"]
    assert result["salience"] == pytest.approx(0.7)
    assert result["confidence"] == pytest.approx(0.9)


def test_parse_strips_markdown_fence() -> None:
    raw = '```json\n{"topic": "test", "chat_content_tags": ["a"], "salience": 0.5, "confidence": 0.8}\n```'
    result = parse_llm_output(raw)
    assert result is not None
    assert result["topic"] == "test"


def test_parse_extracts_json_from_surrounding_text() -> None:
    raw = 'Here is the result: {"topic": "chat", "chat_content_tags": ["x"], "salience": 0.4, "confidence": 0.6} done.'
    result = parse_llm_output(raw)
    assert result is not None
    assert result["topic"] == "chat"


def test_parse_missing_required_key_returns_none() -> None:
    raw = '{"topic": "chat", "salience": 0.5}'  # missing chat_content_tags & confidence
    assert parse_llm_output(raw) is None


def test_parse_invalid_json_returns_none() -> None:
    assert parse_llm_output("not json at all") is None
    assert parse_llm_output("") is None
    assert parse_llm_output("{broken json}") is None


def test_parse_clamps_salience_and_confidence() -> None:
    raw = '{"topic": "t", "chat_content_tags": [], "salience": 2.5, "confidence": -0.1}'
    result = parse_llm_output(raw)
    assert result is not None
    assert result["salience"] == pytest.approx(1.0)
    assert result["confidence"] == pytest.approx(0.0)


def test_parse_topic_truncated_to_60_chars() -> None:
    long_topic = "A" * 80
    raw = f'{{"topic": "{long_topic}", "chat_content_tags": [], "salience": 0.5, "confidence": 0.5}}'
    result = parse_llm_output(raw)
    assert result is not None
    assert len(result["topic"]) == 60


def test_parse_tags_truncated_to_5() -> None:
    tags = ["t1", "t2", "t3", "t4", "t5", "t6", "t7"]
    import json
    raw = json.dumps({"topic": "t", "chat_content_tags": tags, "salience": 0.5, "confidence": 0.5})
    result = parse_llm_output(raw)
    assert result is not None
    assert len(result["chat_content_tags"]) == 5


# ---------------------------------------------------------------------------
# fallback_extraction tests
# ---------------------------------------------------------------------------

def test_fallback_uses_first_message_as_topic() -> None:
    w = make_window([("u1", "Alice", "今天天气真好"), ("u1", "Alice", "不错")])
    result = fallback_extraction(w)
    assert result["topic"] == "今天天气真好"


def test_fallback_salience_scales_with_message_count() -> None:
    w_small = make_window([("u1", "A", "hi")] * 3)
    w_large = make_window([("u1", "A", "hi")] * 30)
    assert fallback_extraction(w_small)["salience"] < fallback_extraction(w_large)["salience"]


def test_fallback_salience_capped_at_0_7() -> None:
    w = make_window([("u1", "A", "word1 word2")] * 100)
    result = fallback_extraction(w)
    assert result["salience"] <= 0.7


def test_fallback_confidence_is_low() -> None:
    w = make_window([("u1", "A", "test")])
    result = fallback_extraction(w)
    assert result["confidence"] <= 0.3


def test_fallback_empty_window() -> None:
    w = MessageWindow(session_id="s", group_id=None, start_time=1000.0, last_message_time=1000.0)
    result = fallback_extraction(w)
    assert result["topic"] == "（无内容）"
    assert result["chat_content_tags"] == []


# ---------------------------------------------------------------------------
# build_user_prompt tests
# ---------------------------------------------------------------------------

def test_build_user_prompt_includes_names() -> None:
    w = make_window([("u1", "Alice", "hello"), ("u2", "Bob", "hi")])
    prompt = build_user_prompt(w)
    assert "Alice" in prompt
    assert "Bob" in prompt
    assert "hello" in prompt


def test_build_user_prompt_uses_fallback_label_when_no_name() -> None:
    w = make_window([("u1", "", "hi")])
    prompt = build_user_prompt(w)
    assert "用户1" in prompt


def test_build_user_prompt_respects_max_messages() -> None:
    msgs = [("u1", "A", f"msg{i}") for i in range(30)]
    w = make_window(msgs)
    prompt = build_user_prompt(w, max_messages=5)
    # Only last 5 messages should appear
    assert "msg29" in prompt
    assert "msg0" not in prompt


# ---------------------------------------------------------------------------
# EventExtractor integration tests (mock provider)
# ---------------------------------------------------------------------------

class _MockProvider:
    """Synchronous mock returning a fixed JSON string."""

    def __init__(self, response_text: str) -> None:
        self._text = response_text

    async def text_chat(self, prompt=None, system_prompt=None, **_kwargs):
        class _Resp:
            completion_text: str

        r = _Resp()
        r.completion_text = self._text
        return r


async def test_extractor_fills_event_fields_from_llm(tmp_path) -> None:
    event_repo = InMemoryEventRepository()
    event = make_event("ev1")
    await event_repo.upsert(event)

    json_resp = '{"topic": "LLM话题", "chat_content_tags": ["标签A", "标签B"], "salience": 0.8, "confidence": 0.9}'
    provider = _MockProvider(json_resp)

    extractor = EventExtractor(event_repo=event_repo, provider_getter=lambda: provider)
    w = make_window([("u1", "Alice", "消息1"), ("u2", "Bob", "消息2")])
    await extractor(event, w)

    updated = await event_repo.get("ev1")
    assert updated is not None
    assert updated.topic == "LLM话题"
    assert updated.chat_content_tags == ["标签A", "标签B"]
    assert updated.salience == pytest.approx(0.8)
    assert updated.confidence == pytest.approx(0.9)


async def test_extractor_falls_back_when_no_provider() -> None:
    event_repo = InMemoryEventRepository()
    event = make_event("ev2")
    await event_repo.upsert(event)

    extractor = EventExtractor(event_repo=event_repo, provider_getter=lambda: None)
    w = make_window([("u1", "Alice", "fallback text")])
    await extractor(event, w)

    updated = await event_repo.get("ev2")
    assert updated is not None
    assert updated.topic == "fallback text"
    assert updated.confidence == pytest.approx(0.2)


async def test_extractor_falls_back_on_invalid_llm_output() -> None:
    event_repo = InMemoryEventRepository()
    event = make_event("ev3")
    await event_repo.upsert(event)

    provider = _MockProvider("this is not valid json")
    extractor = EventExtractor(event_repo=event_repo, provider_getter=lambda: provider)
    w = make_window([("u1", "Alice", "第一条消息")])
    await extractor(event, w)

    updated = await event_repo.get("ev3")
    assert updated is not None
    assert updated.confidence == pytest.approx(0.2)  # fallback indicator


async def test_extractor_falls_back_on_timeout() -> None:
    import asyncio as _asyncio

    event_repo = InMemoryEventRepository()
    event = make_event("ev4")
    await event_repo.upsert(event)

    class _SlowProvider:
        async def text_chat(self, **_):
            await _asyncio.sleep(100)

    extractor = EventExtractor(
        event_repo=event_repo,
        provider_getter=lambda: _SlowProvider(),
        llm_timeout=0.05,
    )
    w = make_window([("u1", "Alice", "slow")])
    await extractor(event, w)

    updated = await event_repo.get("ev4")
    assert updated is not None
    assert updated.confidence == pytest.approx(0.2)


async def test_extractor_preserves_other_event_fields() -> None:
    event_repo = InMemoryEventRepository()
    original = dataclasses.replace(make_event("ev5"), participants=["uid-x", "uid-y"])
    await event_repo.upsert(original)

    json_resp = '{"topic": "T", "chat_content_tags": [], "salience": 0.6, "confidence": 0.7}'
    extractor = EventExtractor(
        event_repo=event_repo,
        provider_getter=lambda: _MockProvider(json_resp),
    )
    w = make_window([("u1", "Alice", "hi")])
    await extractor(original, w)

    updated = await event_repo.get("ev5")
    assert updated is not None
    assert updated.participants == ["uid-x", "uid-y"]  # unchanged
    assert updated.group_id == "g1"  # unchanged
