"""Tests for Phase 7: MarkdownProjector."""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from core.domain.models import Event, Impression, Persona
from core.projector.projector import MarkdownProjector
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_persona(uid: str, name: str = "Alice") -> Persona:
    return Persona(
        uid=uid,
        bound_identities=[("qq", "12345")],
        primary_name=name,
        persona_attrs={"big_five": {"O": 0.6, "E": 0.4}, "description": "test user"},
        confidence=0.9,
        created_at=1000.0,
        last_active_at=2000.0,
    )


def make_event(event_id: str, topic: str = "test topic", uid: str = "u1") -> Event:
    return Event(
        event_id=event_id,
        group_id="g1",
        start_time=1000.0,
        end_time=1010.0,
        participants=[uid],
        interaction_flow=[],
        topic=topic,
        summary="test summary",
        chat_content_tags=["tag1", "tag2"],
        salience=0.5,
        confidence=0.8,
        inherit_from=[],
        last_accessed_at=1010.0,
    )


def make_impression(observer: str, subject: str, orientation: str = "affinity") -> Impression:
    return Impression(
        observer_uid=observer,
        subject_uid=subject,
        ipc_orientation=orientation,
        benevolence=0.8,
        power=0.0,
        affect_intensity=0.7,
        r_squared=0.6,
        confidence=0.85,
        scope="global",
        evidence_event_ids=["ev1", "ev2"],
        last_reinforced_at=2000.0,
    )


def _projector(tmp_path: Path, persona_repo=None, event_repo=None, impression_repo=None):
    return MarkdownProjector(
        tmp_path,
        persona_repo or InMemoryPersonaRepository(),
        event_repo or InMemoryEventRepository(),
        impression_repo or InMemoryImpressionRepository(),
    )


# ---------------------------------------------------------------------------
# render_persona — file creation
# ---------------------------------------------------------------------------

async def test_render_persona_creates_both_files(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid1"))
    p = _projector(tmp_path, persona_repo=pr)
    result = await p.render_persona("uid1")
    assert result is True
    assert (tmp_path / "personas" / "uid1" / "PROFILE.md").exists()
    assert (tmp_path / "personas" / "uid1" / "IMPRESSIONS.md").exists()


async def test_render_persona_not_found_returns_false(tmp_path: Path) -> None:
    p = _projector(tmp_path)
    assert await p.render_persona("nonexistent") is False


async def test_render_persona_creates_nested_directory(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("deep-uid"))
    p = _projector(tmp_path, persona_repo=pr)
    await p.render_persona("deep-uid")
    assert (tmp_path / "personas" / "deep-uid").is_dir()


# ---------------------------------------------------------------------------
# PROFILE.md content
# ---------------------------------------------------------------------------

async def test_profile_contains_name(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid1", "Charlie"))
    p = _projector(tmp_path, persona_repo=pr)
    await p.render_persona("uid1")
    content = (tmp_path / "personas" / "uid1" / "PROFILE.md").read_text(encoding="utf-8")
    assert "Charlie" in content


async def test_profile_contains_uid(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid-abc123"))
    p = _projector(tmp_path, persona_repo=pr)
    await p.render_persona("uid-abc123")
    content = (tmp_path / "personas" / "uid-abc123" / "PROFILE.md").read_text(encoding="utf-8")
    assert "uid-abc123" in content


async def test_profile_contains_event_topic(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("uid1"))
    await er.upsert(make_event("ev1", "机器学习研究", "uid1"))
    p = _projector(tmp_path, persona_repo=pr, event_repo=er)
    await p.render_persona("uid1")
    content = (tmp_path / "personas" / "uid1" / "PROFILE.md").read_text(encoding="utf-8")
    assert "机器学习研究" in content


async def test_profile_contains_persona_attrs(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid1"))
    p = _projector(tmp_path, persona_repo=pr)
    await p.render_persona("uid1")
    content = (tmp_path / "personas" / "uid1" / "PROFILE.md").read_text(encoding="utf-8")
    assert "big_five" in content
    assert "description" in content


async def test_profile_no_events_shows_placeholder(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid1"))
    p = _projector(tmp_path, persona_repo=pr)
    await p.render_persona("uid1")
    content = (tmp_path / "personas" / "uid1" / "PROFILE.md").read_text(encoding="utf-8")
    assert "暂无事件记录" in content


async def test_profile_event_tags_included(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("uid1"))
    await er.upsert(make_event("ev1", "话题", "uid1"))
    p = _projector(tmp_path, persona_repo=pr, event_repo=er)
    await p.render_persona("uid1")
    content = (tmp_path / "personas" / "uid1" / "PROFILE.md").read_text(encoding="utf-8")
    assert "tag1" in content


# ---------------------------------------------------------------------------
# IMPRESSIONS.md content
# ---------------------------------------------------------------------------

async def test_impressions_contains_ipc_orientation(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    ir = InMemoryImpressionRepository()
    await pr.upsert(make_persona("uid1"))
    await ir.upsert(make_impression("bot", "uid1", orientation="dominant"))
    p = _projector(tmp_path, persona_repo=pr, impression_repo=ir)
    await p.render_persona("uid1")
    content = (tmp_path / "personas" / "uid1" / "IMPRESSIONS.md").read_text(encoding="utf-8")
    assert "掌控" in content


async def test_impressions_no_impressions_shows_placeholder(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid1"))
    p = _projector(tmp_path, persona_repo=pr)
    await p.render_persona("uid1")
    content = (tmp_path / "personas" / "uid1" / "IMPRESSIONS.md").read_text(encoding="utf-8")
    assert "暂无印象记录" in content


async def test_impressions_contains_evidence_events(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    ir = InMemoryImpressionRepository()
    await pr.upsert(make_persona("uid1"))
    await ir.upsert(make_impression("bot", "uid1"))
    p = _projector(tmp_path, persona_repo=pr, impression_repo=ir)
    await p.render_persona("uid1")
    content = (tmp_path / "personas" / "uid1" / "IMPRESSIONS.md").read_text(encoding="utf-8")
    assert "ev1" in content


# ---------------------------------------------------------------------------
# render_all_personas
# ---------------------------------------------------------------------------

async def test_render_all_personas_returns_count(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid1", "Alice"))
    await pr.upsert(make_persona("uid2", "Bob"))
    p = _projector(tmp_path, persona_repo=pr)
    count = await p.render_all_personas()
    assert count == 2


async def test_render_all_personas_creates_all_directories(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid1", "Alice"))
    await pr.upsert(make_persona("uid2", "Bob"))
    p = _projector(tmp_path, persona_repo=pr)
    await p.render_all_personas()
    assert (tmp_path / "personas" / "uid1" / "PROFILE.md").exists()
    assert (tmp_path / "personas" / "uid2" / "PROFILE.md").exists()


async def test_render_all_personas_empty_repo_returns_zero(tmp_path: Path) -> None:
    p = _projector(tmp_path)
    assert await p.render_all_personas() == 0


# ---------------------------------------------------------------------------
# render_bot_persona
# ---------------------------------------------------------------------------

async def test_render_bot_persona_creates_file(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("bot-uid", "ChatBot"))
    p = _projector(tmp_path, persona_repo=pr)
    result = await p.render_bot_persona("bot-uid")
    assert result is True
    assert (tmp_path / "global" / "BOT_PERSONA.md").exists()


async def test_render_bot_persona_not_found_returns_false(tmp_path: Path) -> None:
    p = _projector(tmp_path)
    assert await p.render_bot_persona("missing-bot") is False


async def test_render_bot_persona_contains_name(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("bot-uid", "MyBot"))
    p = _projector(tmp_path, persona_repo=pr)
    await p.render_bot_persona("bot-uid")
    content = (tmp_path / "global" / "BOT_PERSONA.md").read_text(encoding="utf-8")
    assert "MyBot" in content


async def test_render_bot_persona_contains_uid(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("bot-xyz"))
    p = _projector(tmp_path, persona_repo=pr)
    await p.render_bot_persona("bot-xyz")
    content = (tmp_path / "global" / "BOT_PERSONA.md").read_text(encoding="utf-8")
    assert "bot-xyz" in content


# ---------------------------------------------------------------------------
# Overwrite behaviour
# ---------------------------------------------------------------------------

async def test_render_overwrites_existing_file(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid1", "Alice"))
    p = _projector(tmp_path, persona_repo=pr)
    await p.render_persona("uid1")

    updated = dataclasses.replace(
        await pr.get("uid1"),  # type: ignore[arg-type]
        primary_name="AliceRenamed",
    )
    await pr.upsert(updated)
    await p.render_persona("uid1")

    content = (tmp_path / "personas" / "uid1" / "PROFILE.md").read_text(encoding="utf-8")
    assert "AliceRenamed" in content
