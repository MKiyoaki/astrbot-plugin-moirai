import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from core.managers.recall_manager import RecallManager, _event_contains_term, _event_term_score, _explicit_query_terms
from core.domain.models import Event, EventType, Persona, Impression, RawStoredMessage
from core.config import RetrievalConfig, InjectionConfig, SoulConfig
from core.repository.memory import InMemoryRawMessageRepository

def _make_retriever(events=None):
    """Build a MagicMock retriever whose _event_repo and _encoder are properly wired."""
    event_repo = AsyncMock()
    event_repo.count_by_status = AsyncMock(return_value=1)
    event_repo.get_children = AsyncMock(return_value=[])
    event_repo.get = AsyncMock(return_value=None)
    event_repo.search_fts = AsyncMock(return_value=events or [])
    event_repo.search_vector = AsyncMock(return_value=[])

    encoder = MagicMock()
    encoder.dim = 0  # NullEncoder: skip vector search

    retriever = MagicMock()
    retriever._event_repo = event_repo
    retriever._encoder = encoder
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    return retriever, event_repo


def _make_vector_retriever(vector_events=None, bm25_events=None):
    event_repo = AsyncMock()
    event_repo.count_by_status = AsyncMock(return_value=1)
    event_repo.get_children = AsyncMock(return_value=[])
    event_repo.get = AsyncMock(return_value=None)
    event_repo.search_fts = AsyncMock(return_value=bm25_events or [])
    event_repo.search_vector = AsyncMock(return_value=vector_events or [])

    encoder = MagicMock()
    encoder.dim = 2
    encoder.encode = AsyncMock(return_value=[1.0, 0.0])

    retriever = MagicMock()
    retriever._event_repo = event_repo
    retriever._encoder = encoder
    retriever._bm25_limit = 20
    retriever._vec_limit = 20
    return retriever, event_repo


@pytest.fixture
def recall_manager():
    retriever, _ = _make_retriever()
    retrieval_cfg = RetrievalConfig(final_limit=10)
    injection_cfg = InjectionConfig(position="system_prompt")
    persona_repo = AsyncMock()
    impression_repo = AsyncMock()
    soul_cfg = SoulConfig(enabled=True)
    return RecallManager(retriever, retrieval_cfg, injection_cfg, persona_repo, impression_repo, soul_cfg), retriever, persona_repo, impression_repo


@pytest.mark.asyncio
async def test_recall_returns_episodes(recall_manager):
    rm, retriever, pr, ir = recall_manager
    episode_ev = Event(event_id="e1", event_type=EventType.EPISODE, end_time=1000.0)
    retriever._event_repo.search_fts = AsyncMock(return_value=[episode_ev])

    events = await rm.recall("some query")
    assert any(e.event_id == "e1" for e in events)


@pytest.mark.asyncio
async def test_recall_vector_only_low_evidence_passes_through() -> None:
    # Low-evidence events are no longer hard-blocked; they pass through with
    # evidence_score≈0 so _score demotes them. The LLM self-assesses relevance.
    unrelated = Event(
        event_id="e1",
        topic="卿泽对gariton的撒娇与学术互动",
        summary="卿泽与gariton讨论互动",
        chat_content_tags=["情感", "技术"],
        end_time=1000.0,
    )
    retriever, _ = _make_vector_retriever(vector_events=[unrelated])
    rm = RecallManager(
        retriever,
        RetrievalConfig(final_limit=5, vector_fallback_enabled=True),
        InjectionConfig(),
    )

    events = await rm.recall("卿泽对原神的看法是什么？大家都说了些什么？")

    # Unrelated event passes through (evidence_score=0 but not hard-blocked).
    assert len(events) == 1
    assert events[0].event_id == "e1"


@pytest.mark.asyncio
async def test_recall_allows_vector_only_with_explicit_evidence() -> None:
    related = Event(
        event_id="e1",
        topic="卿泽对原神剧情的评价",
        summary="卿泽评价原神剧情和玩法",
        chat_content_tags=["游戏讨论", "原神"],
        end_time=1000.0,
    )
    retriever, _ = _make_vector_retriever(vector_events=[related])
    rm = RecallManager(
        retriever,
        RetrievalConfig(final_limit=5, vector_fallback_enabled=True),
        InjectionConfig(),
    )

    events = await rm.recall("卿泽对原神的看法是什么？大家都说了些什么？")

    assert [event.event_id for event in events] == ["e1"]


@pytest.mark.asyncio
async def test_recall_ignores_question_words_for_evidence_filter() -> None:
    related = Event(
        event_id="e1",
        topic="请求大五人格分析并扩展范围",
        summary="用户请求大五人格分析，并要求学术化说明",
        chat_content_tags=["大五人格", "性格分析", "学术化要求"],
        end_time=1000.0,
    )
    retriever, _ = _make_vector_retriever(vector_events=[related])
    rm = RecallManager(
        retriever,
        RetrievalConfig(final_limit=5, vector_fallback_enabled=True),
        InjectionConfig(),
    )

    events = await rm.recall("谁请求了大五人格分析？")

    assert [event.event_id for event in events] == ["e1"]


@pytest.mark.asyncio
async def test_recall_allows_named_entity_when_person_name_is_absent_from_event_text() -> None:
    related = Event(
        event_id="e1",
        topic="用户向Gariton示好与游戏话题互动",
        summary="用户向Gariton示好，并夹杂游戏话题",
        chat_content_tags=["示好告白", "游戏话题"],
        end_time=1000.0,
    )
    retriever, _ = _make_vector_retriever(vector_events=[related])
    rm = RecallManager(
        retriever,
        RetrievalConfig(final_limit=5, vector_fallback_enabled=True),
        InjectionConfig(),
    )
    assert "Gariton" in _explicit_query_terms("卿泽和Gariton发生了什么互动？")
    assert _event_contains_term(related, "Gariton")

    events = await rm.recall("卿泽和Gariton发生了什么互动？")

    assert [event.event_id for event in events] == ["e1"]


@pytest.mark.asyncio
async def test_recall_and_inject_system_prompt(recall_manager):
    rm, retriever, pr, ir = recall_manager
    rm._rcfg.final_limit = 5

    e1 = Event(event_id="e1", topic="test", end_time=1000.0)
    retriever._event_repo.search_fts = AsyncMock(return_value=[e1])
    retriever._event_repo.count_by_status = AsyncMock(return_value=1)

    req = MagicMock()
    req.system_prompt = "Existing prompt"
    req.prompt = ""
    req.model = "gpt-4"

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
    retriever._event_repo.search_fts = AsyncMock(return_value=[e1])
    retriever._event_repo.count_by_status = AsyncMock(return_value=1)

    req = MagicMock()
    req.contexts = []
    req.system_prompt = ""
    req.prompt = ""
    req.model = "gpt-4"

    count = await rm.recall_and_inject("query", req, "s1")
    assert count == 1
    assert len(req.contexts) == 2  # assistant + tool result

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
    retriever._event_repo.search_fts = AsyncMock(return_value=[])
    retriever._event_repo.count_by_status = AsyncMock(return_value=0)

    await rm.recall_and_inject("hi", req, "s1")
    state1 = rm._soul_states["s1"]

    await rm.recall_and_inject("hi", req, "s1")
    state2 = rm._soul_states["s1"]
    assert state2 is not state1


@pytest.mark.asyncio
async def test_recall_and_inject_hydrates_raw_message_details() -> None:
    retriever, event_repo = _make_retriever()
    raw_repo = InMemoryRawMessageRepository()
    event = Event(event_id="e1", topic="raw topic", summary="summary", end_time=1000.0)
    event_repo.search_fts = AsyncMock(return_value=[event])
    event_repo.count_by_status = AsyncMock(return_value=1)
    await raw_repo.upsert_many([
        RawStoredMessage(
            message_id="m1",
            session_id="s1",
            group_id="g1",
            platform="test",
            physical_id="u1",
            sender_uid="u1",
            display_name="Alice",
            role="user",
            text="hydrated raw detail",
            content_hash="h1",
            created_at=1000.0,
            ingested_at=1000.1,
        )
    ])
    await raw_repo.link_event_messages("e1", ["m1"])
    rm = RecallManager(
        retriever,
        RetrievalConfig(final_limit=5),
        InjectionConfig(position="system_prompt", token_budget=500),
        raw_message_repo=raw_repo,
    )
    req = MagicMock()
    req.system_prompt = ""
    req.prompt = ""
    req.model = "gpt-4"

    count = await rm.recall_and_inject("query", req, "s1")

    assert count == 1
    assert "hydrated raw detail" in req.system_prompt


# ── _event_term_score field-weight tests ──────────────────────────────────────

def test_event_term_score_topic_highest():
    ev = Event(event_id="e1", topic="稿费纠纷", summary="", end_time=1000.0)
    assert _event_term_score(ev, "稿费") == 1.0


def test_event_term_score_tag_second():
    ev = Event(event_id="e1", topic="日常讨论", summary="", chat_content_tags=["稿费问题"], end_time=1000.0)
    assert _event_term_score(ev, "稿费") == 0.9


def test_event_term_score_summary_lowest():
    ev = Event(event_id="e1", topic="普通事件", summary="顺带提了一句稿费的事", end_time=1000.0)
    assert _event_term_score(ev, "稿费") == 0.4


def test_event_term_score_absent():
    ev = Event(event_id="e1", topic="游戏讨论", summary="明日方舟攻略", end_time=1000.0)
    assert _event_term_score(ev, "稿费") == 0.0


def test_event_contains_term_backward_compat():
    ev = Event(event_id="e1", topic="稿费纠纷", summary="", end_time=1000.0)
    assert _event_contains_term(ev, "稿费") is True
    ev2 = Event(event_id="e2", topic="游戏讨论", summary="", end_time=1000.0)
    assert _event_contains_term(ev2, "稿费") is False


def test_event_term_score_topic_beats_summary():
    ev = Event(event_id="e1", topic="稿费主题事件", summary="同时也提到了稿费", end_time=1000.0)
    assert _event_term_score(ev, "稿费") == 1.0


# ── evidence coverage filter integration tests ────────────────────────────────

@pytest.mark.asyncio
async def test_recall_focused_event_passes_coverage_threshold() -> None:
    """Event with term in topic/tag should pass the coverage threshold."""
    focused = Event(
        event_id="e_focused",
        topic="导师拒绝给稿费的纠纷",
        summary="讨论了导师不给稿费的问题",
        chat_content_tags=["稿费", "导师关系"],
        end_time=1000.0,
    )
    retriever, _ = _make_vector_retriever(vector_events=[focused])
    rm = RecallManager(
        retriever,
        RetrievalConfig(final_limit=5, vector_fallback_enabled=True),
        InjectionConfig(),
    )
    events = await rm.recall("导师和稿费的问题是什么？")
    assert any(e.event_id == "e_focused" for e in events)


@pytest.mark.asyncio
async def test_recall_broad_event_alone_passes_through() -> None:
    """When only a broad event exists, it passes through with low evidence_score.
    Mixed-candidate ranking (focused > broad) is tested separately."""
    broad = Event(
        event_id="e_broad",
        topic="研究生日常吐槽",
        summary="提到了导师的一些事情",
        chat_content_tags=["日常", "吐槽"],
        end_time=1000.0,
    )
    retriever, _ = _make_vector_retriever(vector_events=[broad])
    rm = RecallManager(
        retriever,
        RetrievalConfig(final_limit=5, vector_fallback_enabled=True),
        InjectionConfig(),
    )
    # "导师和稿费" → evidence_terms = ["导师", "稿费"]
    # broad: "导师" in summary → 0.4; "稿费" absent → 0.0; coverage = 0.2 < 0.35
    # No evidence_candidates → candidates kept as-is, LLM handles relevance.
    events = await rm.recall("导师和稿费的问题是什么？")
    assert len(events) == 1
    assert events[0].event_id == "e_broad"


@pytest.mark.asyncio
async def test_recall_low_evidence_passes_through_llm_handles_relevance() -> None:
    """Vector-only results with no matching evidence terms pass through (not hard-blocked).
    The LLM is expected to self-assess and discard irrelevant injected context."""
    unrelated = Event(
        event_id="e_unrelated",
        topic="卿泽对gariton的撒娇与学术互动",
        summary="卿泽与gariton讨论互动",
        chat_content_tags=["情感", "技术"],
        end_time=1000.0,
    )
    retriever, _ = _make_vector_retriever(vector_events=[unrelated])
    rm = RecallManager(
        retriever,
        RetrievalConfig(final_limit=5, vector_fallback_enabled=True),
        InjectionConfig(),
    )
    events = await rm.recall("卿泽对原神的看法是什么？大家都说了些什么？")
    assert len(events) == 1
    assert events[0].event_id == "e_unrelated"


@pytest.mark.asyncio
async def test_recall_focused_ranks_above_broad_in_mixed_candidates() -> None:
    """When both events pass threshold, focused event should rank first."""
    focused = Event(
        event_id="e_focused",
        topic="导师拒绝给稿费的纠纷",
        summary="稿费问题详细经过",
        chat_content_tags=["稿费"],
        salience=0.5,
        end_time=1000.0,
    )
    broad = Event(
        event_id="e_broad",
        topic="稿费随口一提",
        summary="大家讨论了很多，导师和稿费都提到了",
        chat_content_tags=["日常"],
        salience=0.9,
        end_time=900.0,
    )
    retriever, _ = _make_vector_retriever(vector_events=[focused, broad])
    rm = RecallManager(
        retriever,
        RetrievalConfig(final_limit=5, vector_fallback_enabled=True),
        InjectionConfig(),
    )
    events = await rm.recall("导师和稿费的问题是什么？")
    assert events[0].event_id == "e_focused"


@pytest.mark.asyncio
async def test_bump_salience_on_use_calls_bump_event_usage():
    # Setup mock event repo and recall manager
    retriever, event_repo = _make_retriever()
    rm = RecallManager(
        retriever,
        RetrievalConfig(),
        InjectionConfig(),
    )
    
    # Mock event object
    mock_event = Event(
        event_id="e1",
        salience=0.5,
        chat_content_tags=["python", "coding"],
        end_time=1000.0,
    )
    
    # Wire the event repo mock
    event_repo.get = AsyncMock(return_value=mock_event)
    event_repo.bump_event_usage = AsyncMock(return_value=True)
    
    # Run bump_salience_on_use
    await rm.bump_salience_on_use(
        event_ids=["e1"],
        response_text="Let's write some python code",
        boost=0.1
    )
    
    # Assert get was called
    event_repo.get.assert_called_once_with("e1")
    
    # Assert bump_event_usage was called with expected arguments
    event_repo.bump_event_usage.assert_called_once()
    args, kwargs = event_repo.bump_event_usage.call_args
    # args: (event_id, new_salience, timestamp)
    assert args[0] == "e1"
    assert abs(args[1] - 0.6) < 1e-5  # 0.5 + 0.1 = 0.6
    assert isinstance(args[2], float)

