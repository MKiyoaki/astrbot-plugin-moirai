import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from core.managers.recall_manager import RecallManager, _event_contains_term, _explicit_query_terms
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
async def test_recall_blocks_vector_only_without_explicit_evidence() -> None:
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

    assert events == []


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
