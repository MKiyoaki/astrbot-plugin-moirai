"""Tests for Phase 9: WebuiServer data-builders and HTTP API."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from core.domain.models import Event, Impression, Persona
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)
from core.webui.server import (
    WebuiServer,
    event_to_dict,
    impression_to_edge,
    persona_to_node,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def make_persona(uid: str, name: str = "Alice") -> Persona:
    return Persona(
        uid=uid,
        bound_identities=[("qq", "123")],
        primary_name=name,
        persona_attrs={"affect_type": "中性"},
        confidence=0.8,
        created_at=1000.0,
        last_active_at=2000.0,
    )


def make_event(
    event_id: str,
    topic: str = "test",
    group_id: str | None = "g1",
    uid: str = "u1",
) -> Event:
    return Event(
        event_id=event_id,
        group_id=group_id,
        start_time=1_700_000_000.0,
        end_time=1_700_001_000.0,
        participants=[uid],
        interaction_flow=[],
        topic=topic,
        chat_content_tags=["tag1"],
        salience=0.6,
        confidence=0.8,
        inherit_from=[],
        last_accessed_at=1_700_001_000.0,
    )


def make_impression(observer: str, subject: str) -> Impression:
    return Impression(
        observer_uid=observer,
        subject_uid=subject,
        relation_type="friend",
        affect=0.7,
        intensity=0.8,
        confidence=0.9,
        scope="global",
        evidence_event_ids=["ev1"],
        last_reinforced_at=2000.0,
    )


def _server(tmp_path: Path, pr=None, er=None, ir=None) -> WebuiServer:
    return WebuiServer(
        persona_repo=pr or InMemoryPersonaRepository(),
        event_repo=er or InMemoryEventRepository(),
        impression_repo=ir or InMemoryImpressionRepository(),
        data_dir=tmp_path,
        port=_DEFAULT_PORT_UNUSED,
    )


_DEFAULT_PORT_UNUSED = 19999  # never actually bound in tests (TestServer manages port)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def test_event_to_dict_fields() -> None:
    ev = make_event("e1", topic="讨论Python")
    d = event_to_dict(ev)
    assert d["id"] == "e1"
    assert d["content"] == "讨论Python"
    assert "start" in d and "end" in d
    assert d["group"] == "g1"
    assert d["tags"] == ["tag1"]
    assert d["salience"] == pytest.approx(0.6, abs=0.001)


def test_event_to_dict_empty_topic_uses_id_prefix() -> None:
    ev = make_event("abcdefgh12", topic="")
    d = event_to_dict(ev)
    assert d["content"] == "abcdefgh"


def test_persona_to_node_structure() -> None:
    p = make_persona("uid1", "Bob")
    n = persona_to_node(p)
    assert n["data"]["id"] == "uid1"
    assert n["data"]["label"] == "Bob"
    assert "confidence" in n["data"]


def test_impression_to_edge_structure() -> None:
    imp = make_impression("uid1", "uid2")
    e = impression_to_edge(imp)
    assert e["data"]["source"] == "uid1"
    assert e["data"]["target"] == "uid2"
    assert e["data"]["label"] == "friend"
    assert e["data"]["affect"] == pytest.approx(0.7, abs=0.001)
    assert e["data"]["evidence_event_ids"] == ["ev1"]


def test_impression_edge_id_includes_scope() -> None:
    imp = make_impression("a", "b")
    e = impression_to_edge(imp)
    assert "global" in e["data"]["id"]


# ---------------------------------------------------------------------------
# Data-builder methods (no HTTP)
# ---------------------------------------------------------------------------

async def test_events_data_all_groups(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("e1", group_id="g1"))
    await er.upsert(make_event("e2", group_id="g2"))
    srv = _server(tmp_path, er=er)
    data = await srv.events_data(group_id=None, limit=100)
    assert len(data["items"]) == 2


async def test_events_data_filtered_by_group(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("e1", group_id="g1"))
    await er.upsert(make_event("e2", group_id="g2"))
    srv = _server(tmp_path, er=er)
    data = await srv.events_data(group_id="g1", limit=100)
    assert all(item["group"] == "g1" for item in data["items"])
    assert len(data["items"]) == 1


async def test_events_data_empty_repo(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    data = await srv.events_data(group_id=None, limit=10)
    assert data == {"items": []}


async def test_graph_data_nodes_and_edges(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    ir = InMemoryImpressionRepository()
    await pr.upsert(make_persona("uid1", "Alice"))
    await pr.upsert(make_persona("uid2", "Bob"))
    await ir.upsert(make_impression("uid1", "uid2"))
    srv = _server(tmp_path, pr=pr, ir=ir)
    data = await srv.graph_data()
    node_ids = {n["data"]["id"] for n in data["nodes"]}
    assert node_ids == {"uid1", "uid2"}
    assert len(data["edges"]) == 1
    assert data["edges"][0]["data"]["source"] == "uid1"


async def test_graph_data_empty(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    data = await srv.graph_data()
    assert data == {"nodes": [], "edges": []}


async def test_summaries_data_group_files(tmp_path: Path) -> None:
    gdir = tmp_path / "groups" / "g1" / "summaries"
    gdir.mkdir(parents=True)
    (gdir / "2024-01-01.md").write_text("# Summary", encoding="utf-8")
    srv = _server(tmp_path)
    data = await srv.summaries_data()
    assert len(data) == 1
    assert data[0]["group_id"] == "g1"
    assert data[0]["date"] == "2024-01-01"


async def test_summaries_data_global_files(tmp_path: Path) -> None:
    gdir = tmp_path / "global" / "summaries"
    gdir.mkdir(parents=True)
    (gdir / "2024-02-01.md").write_text("# Global", encoding="utf-8")
    srv = _server(tmp_path)
    data = await srv.summaries_data()
    assert any(s["group_id"] is None for s in data)


async def test_summaries_data_empty(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    assert await srv.summaries_data() == []


def test_summary_content_group(tmp_path: Path) -> None:
    gdir = tmp_path / "groups" / "g1" / "summaries"
    gdir.mkdir(parents=True)
    (gdir / "2024-01-01.md").write_text("# Hello", encoding="utf-8")
    srv = _server(tmp_path)
    content = srv.summary_content("g1", "2024-01-01")
    assert content == "# Hello"


def test_summary_content_not_found(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    assert srv.summary_content("g1", "9999-99-99") is None


def test_summary_content_global(tmp_path: Path) -> None:
    gdir = tmp_path / "global" / "summaries"
    gdir.mkdir(parents=True)
    (gdir / "2024-03-01.md").write_text("私聊摘要", encoding="utf-8")
    srv = _server(tmp_path)
    content = srv.summary_content(None, "2024-03-01")
    assert content == "私聊摘要"


# ---------------------------------------------------------------------------
# HTTP API via aiohttp TestClient
# ---------------------------------------------------------------------------

async def test_api_events_returns_json(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("e1", topic="Python"))
    srv = _server(tmp_path, er=er)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/events")
        assert resp.status == 200
        data = await resp.json()
        assert "items" in data
        assert data["items"][0]["content"] == "Python"


async def test_api_graph_returns_json(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid1", "Alice"))
    srv = _server(tmp_path, pr=pr)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/graph")
        assert resp.status == 200
        data = await resp.json()
        assert "nodes" in data and "edges" in data
        assert data["nodes"][0]["data"]["label"] == "Alice"


async def test_api_summaries_returns_list(tmp_path: Path) -> None:
    gdir = tmp_path / "groups" / "g1" / "summaries"
    gdir.mkdir(parents=True)
    (gdir / "2024-01-01.md").write_text("# S", encoding="utf-8")
    srv = _server(tmp_path)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/summaries")
        assert resp.status == 200
        data = await resp.json()
        assert isinstance(data, list)
        assert data[0]["date"] == "2024-01-01"


async def test_api_summary_content(tmp_path: Path) -> None:
    gdir = tmp_path / "groups" / "g1" / "summaries"
    gdir.mkdir(parents=True)
    (gdir / "2024-01-01.md").write_text("# 内容", encoding="utf-8")
    srv = _server(tmp_path)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/summary?group_id=g1&date=2024-01-01")
        assert resp.status == 200
        data = await resp.json()
        assert "# 内容" in data["content"]


async def test_api_summary_not_found(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/summary?group_id=g1&date=9999-99-99")
        assert resp.status == 404


async def test_api_summary_missing_date(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/summary?group_id=g1")
        assert resp.status == 400


async def test_api_index_returns_html(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/")
        assert resp.status == 200
        text = await resp.text()
        assert "Enhanced Memory" in text
        assert "vis-timeline" in text.lower() or "三轴" in text
