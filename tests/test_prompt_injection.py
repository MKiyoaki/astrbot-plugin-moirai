"""Tests for Phase 6: event formatter and prompt injection logic."""
from __future__ import annotations

import dataclasses
import time

import pytest

from core.domain.models import Event
from core.retrieval.formatter import format_events_for_prompt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_event(
    event_id: str,
    topic: str = "test topic",
    salience: float = 0.5,
    tags: list[str] | None = None,
    end_time: float = 1010.0,
) -> Event:
    return Event(
        event_id=event_id,
        group_id="g1",
        start_time=1000.0,
        end_time=end_time,
        participants=["uid-a"],
        interaction_flow=[],
        topic=topic,
        chat_content_tags=tags or [],
        salience=salience,
        confidence=0.8,
        inherit_from=[],
        last_accessed_at=1010.0,
    )


# ---------------------------------------------------------------------------
# format_events_for_prompt
# ---------------------------------------------------------------------------

def test_format_empty_returns_empty() -> None:
    assert format_events_for_prompt([]) == ""


def test_format_single_event_contains_topic() -> None:
    event = make_event("e1", topic="项目计划讨论")
    result = format_events_for_prompt([event], now=2000.0)
    assert "项目计划讨论" in result
    assert "相关历史记忆" in result


def test_format_includes_tags() -> None:
    event = make_event("e1", topic="周末旅行", tags=["旅游", "计划"])
    result = format_events_for_prompt([event], now=2000.0)
    assert "旅游" in result
    assert "计划" in result


def test_format_no_tags_no_parentheses() -> None:
    event = make_event("e1", topic="无标签事件", tags=[])
    result = format_events_for_prompt([event], now=2000.0)
    assert "（" not in result


def test_format_sorts_by_salience_descending() -> None:
    low = make_event("low", topic="低重要性事件", salience=0.1)
    high = make_event("high", topic="高重要性事件", salience=0.9)
    result = format_events_for_prompt([low, high], now=2000.0)
    assert result.index("高重要性事件") < result.index("低重要性事件")


def test_format_respects_token_budget() -> None:
    # Each event has a 100-char topic; tight budget should exclude some
    events = [make_event(f"e{i}", topic="x" * 100, salience=float(i) / 10) for i in range(10)]
    result = format_events_for_prompt(events, token_budget=80, now=2000.0)
    # With budget=80 tokens ≈ 160 chars, only the header might fit or one entry
    assert len(result) < sum(len(e.topic) for e in events)


def test_format_returns_empty_when_all_exceed_budget() -> None:
    # Header alone uses ~9 tokens; budget of 5 should return empty after no lines fit
    event = make_event("e1", topic="x" * 200)
    result = format_events_for_prompt([event], token_budget=5, now=2000.0)
    # Either empty (nothing fits) or just the header — either way, very short
    assert len(result) < 20


def test_format_time_label_minutes() -> None:
    now = time.time()
    event = dataclasses.replace(make_event("e1", topic="刚刚发生"), end_time=now - 300)
    result = format_events_for_prompt([event], now=now)
    assert "分钟前" in result


def test_format_time_label_hours() -> None:
    now = time.time()
    event = dataclasses.replace(make_event("e1", topic="几小时前"), end_time=now - 7200)
    result = format_events_for_prompt([event], now=now)
    assert "小时前" in result


def test_format_time_label_days() -> None:
    now = time.time()
    event = dataclasses.replace(make_event("e1", topic="几天前"), end_time=now - 172800)
    result = format_events_for_prompt([event], now=now)
    assert "天前" in result


def test_format_multiple_events_all_present_within_budget() -> None:
    events = [
        make_event("e1", topic="话题一", salience=0.9),
        make_event("e2", topic="话题二", salience=0.8),
        make_event("e3", topic="话题三", salience=0.7),
    ]
    result = format_events_for_prompt(events, token_budget=800, now=2000.0)
    assert "话题一" in result
    assert "话题二" in result
    assert "话题三" in result


def test_format_header_present() -> None:
    event = make_event("e1", topic="测试事件")
    result = format_events_for_prompt([event], now=2000.0)
    assert result.startswith("## 相关历史记忆\n")


# ---------------------------------------------------------------------------
# on_llm_request hook logic (tested via mock objects)
# ---------------------------------------------------------------------------

class _MockRequest:
    """Minimal stand-in for ProviderRequest."""

    def __init__(self, prompt: str = "hello", system_prompt: str = "") -> None:
        self.prompt = prompt
        self.system_prompt = system_prompt


async def _run_hook(retriever, req: _MockRequest) -> None:
    """Reproduce the hook logic from main.py for isolated testing."""
    if retriever is None or not req.prompt:
        return
    try:
        results = await retriever.search(req.prompt, limit=10)
        if not results:
            return
        injected = format_events_for_prompt(results)
        if injected:
            sep = "\n\n" if req.system_prompt else ""
            req.system_prompt = req.system_prompt + sep + injected
    except Exception:
        pass


class _MockRetriever:
    def __init__(self, results: list[Event]) -> None:
        self._results = results

    async def search(self, query: str, limit: int = 10) -> list[Event]:
        return self._results[:limit]


async def test_hook_injects_into_empty_system_prompt() -> None:
    event = make_event("e1", topic="python 编程", salience=0.8)
    retriever = _MockRetriever([event])
    req = _MockRequest(prompt="python", system_prompt="")
    await _run_hook(retriever, req)
    assert "python 编程" in req.system_prompt
    assert req.system_prompt.startswith("## 相关历史记忆")


async def test_hook_appends_to_existing_system_prompt() -> None:
    event = make_event("e1", topic="测试话题", salience=0.8)
    retriever = _MockRetriever([event])
    req = _MockRequest(prompt="测试", system_prompt="你是一个助手。")
    await _run_hook(retriever, req)
    assert req.system_prompt.startswith("你是一个助手。")
    assert "测试话题" in req.system_prompt
    assert "\n\n" in req.system_prompt  # separator added


async def test_hook_no_results_leaves_system_prompt_unchanged() -> None:
    retriever = _MockRetriever([])
    req = _MockRequest(prompt="something", system_prompt="original")
    await _run_hook(retriever, req)
    assert req.system_prompt == "original"


async def test_hook_skips_when_retriever_none() -> None:
    req = _MockRequest(prompt="hello", system_prompt="original")
    await _run_hook(None, req)
    assert req.system_prompt == "original"


async def test_hook_skips_when_prompt_empty() -> None:
    retriever = _MockRetriever([make_event("e1", topic="something")])
    req = _MockRequest(prompt="", system_prompt="original")
    await _run_hook(retriever, req)
    assert req.system_prompt == "original"


async def test_hook_swallows_retriever_exception() -> None:
    class _BrokenRetriever:
        async def search(self, query, limit=10):
            raise RuntimeError("DB error")

    req = _MockRequest(prompt="hello", system_prompt="original")
    await _run_hook(_BrokenRetriever(), req)
    assert req.system_prompt == "original"
