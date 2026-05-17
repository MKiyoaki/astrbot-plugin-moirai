"""Tests for session window progress tracking in get_stats() and CommandManager.status()."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.api import get_stats
from core.boundary.window import MessageWindow
from core.domain.models import Event, Impression, Persona
from core.managers.command_manager import CommandManager
from core.managers.context_manager import ContextManager
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)
from core.tasks.scheduler import TaskScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_persona(uid: str, name: str = "Alice") -> Persona:
    return Persona(
        uid=uid,
        bound_identities=[("qq", "123")],
        primary_name=name,
        persona_attrs={},
        confidence=0.8,
        created_at=1000.0,
        last_active_at=2000.0,
    )


def make_impression(observer: str, subject: str) -> Impression:
    return Impression(
        observer_uid=observer,
        subject_uid=subject,
        scope="global",
        ipc_orientation="affinity",
        benevolence=0.5,
        power=0.0,
        affect_intensity=0.5,
        r_squared=0.8,
        confidence=0.7,
        evidence_event_ids=[],
        last_reinforced_at=1000.0,
    )


def _make_context_manager_with_windows(windows: list[MessageWindow]) -> MagicMock:
    cm = MagicMock()
    cm._windows = {w.session_id: w for w in windows}
    return cm


# ---------------------------------------------------------------------------
# Tests: get_stats() active_sessions
# ---------------------------------------------------------------------------

class TestGetStatsActiveSessions:
    @pytest.fixture
    def repos(self):
        return (
            InMemoryPersonaRepository(),
            InMemoryEventRepository(),
            InMemoryImpressionRepository(),
        )

    @pytest.mark.asyncio
    async def test_no_context_manager_returns_empty_list(self, repos, tmp_path):
        persona_repo, event_repo, impression_repo = repos
        result = await get_stats(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
            context_manager=None,
            summary_trigger_rounds=30,
        )
        assert result["active_sessions"] == []
        assert result["summary_trigger_rounds"] == 30

    @pytest.mark.asyncio
    async def test_sessions_populated_from_context_manager(self, repos, tmp_path):
        persona_repo, event_repo, impression_repo = repos

        win1 = MessageWindow(session_id="session:abc", group_id="g1")
        for i in range(10):
            win1.add_message(uid=f"u{i}", text=f"msg{i}", timestamp=float(1000 + i))

        win2 = MessageWindow(session_id="session:private", group_id=None)
        for i in range(4):
            win2.add_message(uid="u0", text=f"msg{i}", timestamp=float(2000 + i))

        cm = _make_context_manager_with_windows([win1, win2])

        result = await get_stats(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
            context_manager=cm,
            summary_trigger_rounds=30,
        )

        sessions = result["active_sessions"]
        assert len(sessions) == 2

        by_id = {s["session_id"]: s for s in sessions}

        s1 = by_id["session:abc"]
        assert s1["message_count"] == 10
        assert s1["current_rounds"] == 5   # 10 // 2
        assert s1["trigger_rounds"] == 30
        assert s1["group_id"] == "g1"
        assert s1["trigger_threshold_messages"] == 60

        s2 = by_id["session:private"]
        assert s2["message_count"] == 4
        assert s2["current_rounds"] == 2
        assert s2["group_id"] is None

    @pytest.mark.asyncio
    async def test_context_manager_exception_gives_empty_list(self, repos, tmp_path):
        """If the context_manager raises unexpectedly, we get an empty list, not a crash."""
        persona_repo, event_repo, impression_repo = repos

        bad_cm = MagicMock()
        # Make attribute access raise
        type(bad_cm)._windows = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))

        result = await get_stats(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
            context_manager=bad_cm,
            summary_trigger_rounds=30,
        )
        assert result["active_sessions"] == []

    @pytest.mark.asyncio
    async def test_trigger_rounds_respected(self, repos, tmp_path):
        persona_repo, event_repo, impression_repo = repos

        win = MessageWindow(session_id="s1", group_id=None)
        for i in range(20):
            win.add_message(uid="u", text="x", timestamp=float(i))

        cm = _make_context_manager_with_windows([win])
        result = await get_stats(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
            context_manager=cm,
            summary_trigger_rounds=15,
        )
        s = result["active_sessions"][0]
        assert s["trigger_rounds"] == 15
        assert s["trigger_threshold_messages"] == 30
        assert s["current_rounds"] == 10   # 20 // 2


# ---------------------------------------------------------------------------
# Tests: CommandManager.status()
# ---------------------------------------------------------------------------

class TestCommandManagerStatus:
    def _make_scheduler(self) -> TaskScheduler:
        sched = MagicMock(spec=TaskScheduler)
        sched.task_names = ["summary", "cleanup"]
        return sched

    def _make_recall(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_status_no_session_id_no_window_line(self):
        """When session_id=None, the window progress line is not included."""
        cm = ContextManager(config=MagicMock(max_sessions=10, vcm_enabled=False))
        manager = CommandManager(
            scheduler=self._make_scheduler(),
            recall=self._make_recall(),
            context_manager=cm,
            summary_trigger_rounds=30,
        )
        result = await manager.status(session_id=None)
        assert "轮" not in result or "window_none" not in result
        assert "cmd.status.window" not in result

    @pytest.mark.asyncio
    async def test_status_with_active_window_shows_progress(self):
        """When session has messages, the progress line is included."""
        from core.config import ContextConfig
        ctx_cfg = MagicMock(spec=ContextConfig)
        ctx_cfg.max_sessions = 10
        ctx_cfg.vcm_enabled = False

        cm = ContextManager(config=ctx_cfg)
        window = cm.get_window("sess:test", create=True, group_id="g1")
        for i in range(12):
            window.add_message(uid="u", text=f"msg{i}", timestamp=float(1000 + i))

        manager = CommandManager(
            scheduler=self._make_scheduler(),
            recall=self._make_recall(),
            context_manager=cm,
            summary_trigger_rounds=30,
        )
        result = await manager.status(session_id="sess:test")
        # 12 messages = 6 rounds
        assert "6" in result
        assert "30" in result

    @pytest.mark.asyncio
    async def test_status_with_no_window_shows_window_none(self):
        """When session_id is given but no window exists, show the 'none' message."""
        from core.config import ContextConfig
        ctx_cfg = MagicMock(spec=ContextConfig)
        ctx_cfg.max_sessions = 10
        ctx_cfg.vcm_enabled = False

        cm = ContextManager(config=ctx_cfg)
        manager = CommandManager(
            scheduler=self._make_scheduler(),
            recall=self._make_recall(),
            context_manager=cm,
            summary_trigger_rounds=30,
        )
        result = await manager.status(session_id="unknown:session")
        # The 'window_none' i18n string
        assert "暂无" in result

    @pytest.mark.asyncio
    async def test_status_includes_memory_stats(self):
        """Stats line with events/personas/impressions counts is present."""
        persona_repo = InMemoryPersonaRepository()
        event_repo = InMemoryEventRepository()
        impression_repo = InMemoryImpressionRepository()

        await persona_repo.upsert(make_persona("p1"))
        await persona_repo.upsert(make_persona("p2"))
        await impression_repo.upsert(make_impression("p1", "p2"))

        from core.config import ContextConfig
        ctx_cfg = MagicMock(spec=ContextConfig)
        ctx_cfg.max_sessions = 10
        ctx_cfg.vcm_enabled = False
        cm = ContextManager(config=ctx_cfg)

        manager = CommandManager(
            scheduler=self._make_scheduler(),
            recall=self._make_recall(),
            context_manager=cm,
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            summary_trigger_rounds=30,
        )
        result = await manager.status(session_id=None)
        # Should have persona count (2) and impression count (1)
        assert "2" in result
        assert "1" in result


# ---------------------------------------------------------------------------
# Tests: WebuiServer.stats_data() passes context_manager through
# ---------------------------------------------------------------------------

class TestWebuiServerActiveSessions:
    """Verify WebuiServer.stats_data() propagates context_manager to get_stats()."""

    @pytest.mark.asyncio
    async def test_webui_stats_data_no_context_manager_returns_empty(self, tmp_path):
        from web.server import WebuiServer

        persona_repo = InMemoryPersonaRepository()
        event_repo = InMemoryEventRepository()
        impression_repo = InMemoryImpressionRepository()

        server = WebuiServer(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
            context_manager=None,
            summary_trigger_rounds=30,
        )
        data = await server.stats_data()
        assert data["active_sessions"] == []
        assert data["summary_trigger_rounds"] == 30

    @pytest.mark.asyncio
    async def test_webui_stats_data_with_context_manager_returns_sessions(self, tmp_path):
        from web.server import WebuiServer

        persona_repo = InMemoryPersonaRepository()
        event_repo = InMemoryEventRepository()
        impression_repo = InMemoryImpressionRepository()

        win = MessageWindow(session_id="s:test", group_id="grp1")
        for i in range(6):
            win.add_message(uid="u1", text=f"msg{i}", timestamp=float(1000 + i))

        cm = _make_context_manager_with_windows([win])

        server = WebuiServer(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=tmp_path,
            context_manager=cm,
            summary_trigger_rounds=20,
        )
        data = await server.stats_data()
        sessions = data["active_sessions"]
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s:test"
        assert sessions[0]["current_rounds"] == 3   # 6 // 2
        assert sessions[0]["trigger_rounds"] == 20
        assert data["summary_trigger_rounds"] == 20
