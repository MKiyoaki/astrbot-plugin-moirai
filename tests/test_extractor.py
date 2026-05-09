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
        summary="测试摘要",
        chat_content_tags=[],
        salience=0.5,
        confidence=0.5,
        inherit_from=[],
        last_accessed_at=1100.0,
    )


# ---------------------------------------------------------------------------
# parse_llm_output tests
# ---------------------------------------------------------------------------

def test_parse_clean_json_array() -> None:
    raw = '[{"start_idx": 0, "end_idx": 1, "topic": "项目讨论", "summary": "这是一个摘要", "chat_content_tags": ["工作", "计划"], "salience": 0.7, "confidence": 0.9, "inherit": false}]'
    result = parse_llm_output(raw, max_idx=1)
    assert result is not None
    assert len(result) == 1
    assert result[0]["topic"] == "项目讨论"
    assert result[0]["summary"] == "这是一个摘要"
    assert result[0]["chat_content_tags"] == ["工作", "计划"]
    assert result[0]["salience"] == pytest.approx(0.7)
    assert result[0]["confidence"] == pytest.approx(0.9)


def test_parse_multi_event_array() -> None:
    raw = ('['
           '{"start_idx": 0, "end_idx": 1, "topic": "t1", "summary": "s1", "chat_content_tags": [], "salience": 0.5, "confidence": 0.5},'
           '{"start_idx": 2, "end_idx": 3, "topic": "t2", "summary": "s2", "chat_content_tags": [], "salience": 0.5, "confidence": 0.5}'
           ']')
    result = parse_llm_output(raw, max_idx=3)
    assert result is not None
    assert len(result) == 2
    assert result[0]["topic"] == "t1"
    assert result[0]["summary"] == "s1"
    assert result[1]["topic"] == "t2"
    assert result[1]["summary"] == "s2"


def test_parse_strips_markdown_fence() -> None:
    raw = '```json\n[{"start_idx": 0, "end_idx": 0, "topic": "test", "summary": "summ", "chat_content_tags": ["a"], "salience": 0.5, "confidence": 0.8}]\n```'
    result = parse_llm_output(raw, max_idx=0)
    assert result is not None
    assert result[0]["topic"] == "test"
    assert result[0]["summary"] == "summ"


def test_parse_extracts_json_from_surrounding_text() -> None:
    raw = 'Here is the result: [{"start_idx": 0, "end_idx": 0, "topic": "chat", "summary": "s", "chat_content_tags": ["x"], "salience": 0.4, "confidence": 0.6}] done.'
    result = parse_llm_output(raw, max_idx=0)
    assert result is not None
    assert result[0]["topic"] == "chat"
    assert result[0]["summary"] == "s"


def test_parse_invalid_range_skipped() -> None:
    raw = '[{"start_idx": 0, "end_idx": 10, "topic": "bad", "summary": "s", "chat_content_tags": [], "salience": 0.5, "confidence": 0.5}]'
    # max_idx is 5, so end_idx 10 is invalid
    assert parse_llm_output(raw, max_idx=5) is None


def test_parse_missing_required_key_skipped() -> None:
    raw = '[{"topic": "chat", "summary": "s", "salience": 0.5, "start_idx": 0, "end_idx": 0}]'  # missing chat_content_tags & confidence
    assert parse_llm_output(raw, max_idx=0) is None


def test_parse_invalid_json_returns_none() -> None:
    assert parse_llm_output("not json at all", max_idx=10) is None
    assert parse_llm_output("", max_idx=10) is None


# ---------------------------------------------------------------------------
# fallback_extraction tests
# ---------------------------------------------------------------------------

def test_fallback_returns_list() -> None:
    w = make_window([("u1", "Alice", "msg")])
    result = fallback_extraction(w)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["topic"] == "msg"
    assert "summary" in result[0]


def test_fallback_salience_scales_with_message_count() -> None:
    w_small = make_window([("u1", "A", "hi")] * 3)
    w_large = make_window([("u1", "A", "hi")] * 30)
    assert fallback_extraction(w_small)[0]["salience"] < fallback_extraction(w_large)[0]["salience"]


def test_fallback_salience_capped_at_0_7() -> None:
    w = make_window([("u1", "A", "word1 word2")] * 100)
    result = fallback_extraction(w)
    assert result[0]["salience"] <= 0.7


def test_fallback_confidence_is_low() -> None:
    w = make_window([("u1", "A", "test")])
    result = fallback_extraction(w)
    assert result[0]["confidence"] <= 0.3


def test_fallback_empty_window() -> None:
    w = MessageWindow(session_id="s", group_id=None, start_time=1000.0, last_message_time=1000.0)
    # Note: make_window and window.py handle start_time/last_message_time.
    # Empty window message_count is 0.
    result = fallback_extraction(w)
    assert result[0]["topic"] == "（无内容）"


# ---------------------------------------------------------------------------
# build_user_prompt tests
# ---------------------------------------------------------------------------

def test_build_user_prompt_includes_indices() -> None:
    w = make_window([("u1", "Alice", "hello"), ("u2", "Bob", "hi")])
    prompt = build_user_prompt(w)
    assert "[0] Alice: hello" in prompt
    assert "[1] Bob: hi" in prompt


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


async def test_extractor_creates_events_from_llm(tmp_path) -> None:
    event_repo = InMemoryEventRepository()
    
    json_resp = '[{"start_idx": 0, "end_idx": 1, "topic": "话题1", "summary": "摘要1", "chat_content_tags": ["A"], "salience": 0.8, "confidence": 0.9}]'
    provider = _MockProvider(json_resp)

    extractor = EventExtractor(event_repo=event_repo, provider_getter=lambda: provider)
    w = make_window([("u1", "Alice", "消息1"), ("u2", "Bob", "消息2")])
    await extractor(w)

    events = await event_repo.list_by_group("g1")
    assert len(events) == 1
    assert events[0].topic == "话题1"
    assert events[0].summary == "摘要1"
    assert events[0].salience == pytest.approx(0.8)


async def test_extractor_multi_event_partitioning() -> None:
    event_repo = InMemoryEventRepository()
    json_resp = ('['
                 '{"start_idx": 0, "end_idx": 0, "topic": "t1", "summary": "s1", "chat_content_tags": [], "salience": 0.5, "confidence": 0.5},'
                 '{"start_idx": 1, "end_idx": 1, "topic": "t2", "summary": "s2", "chat_content_tags": [], "salience": 0.5, "confidence": 0.5}'
                 ']')
    provider = _MockProvider(json_resp)
    extractor = EventExtractor(event_repo=event_repo, provider_getter=lambda: provider)
    w = make_window([("u1", "A", "m1"), ("u2", "B", "m2")])
    await extractor(w)

    events = await event_repo.list_by_group("g1")
    assert len(events) == 2
    # list_by_group returns newest first (t=1010 then t=1000)
    events.sort(key=lambda e: e.start_time)
    assert events[0].topic == "t1"
    assert events[0].summary == "s1"
    assert events[1].topic == "t2"
    assert events[1].summary == "s2"
    assert len(events[0].interaction_flow) == 1
    assert len(events[1].interaction_flow) == 1
