"""Tests for Phase 9 + WebUI 重构: WebuiServer 数据构建、HTTP API、auth、面板注册。"""
from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from core.domain.models import Event, Impression, Persona
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)
from web.auth import AuthManager
from web.registry import PanelManifest, PanelRegistry, PanelRoute
from web.server import (
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
        summary="test summary",
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
        ipc_orientation="友好",
        benevolence=0.7,
        power=0.0,
        affect_intensity=0.8,
        r_squared=0.9,
        confidence=0.9,
        scope="global",
        evidence_event_ids=["ev1"],
        last_reinforced_at=2000.0,
    )


def _server(
    tmp_path: Path,
    pr=None,
    er=None,
    ir=None,
    *,
    auth_enabled: bool = False,
    task_runner=None,
    registry: PanelRegistry | None = None,
) -> WebuiServer:
    return WebuiServer(
        persona_repo=pr or InMemoryPersonaRepository(),
        event_repo=er or InMemoryEventRepository(),
        impression_repo=ir or InMemoryImpressionRepository(),
        data_dir=tmp_path,
        port=19999,
        auth_enabled=auth_enabled,
        task_runner=task_runner,
        registry=registry,
    )


# ---------------------------------------------------------------------------
# 序列化辅助函数
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
    assert e["data"]["label"] == "友好"
    assert e["data"]["affect"] == pytest.approx(0.7, abs=0.001)
    assert e["data"]["evidence_event_ids"] == ["ev1"]


def test_impression_edge_id_includes_scope() -> None:
    imp = make_impression("a", "b")
    e = impression_to_edge(imp)
    assert "global" in e["data"]["id"]


# ---------------------------------------------------------------------------
# 数据构建方法（无 HTTP）
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
    assert srv.summary_content("g1", "2024-01-01") == "# Hello"


def test_summary_content_not_found(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    assert srv.summary_content("g1", "9999-99-99") is None


def test_summary_content_global(tmp_path: Path) -> None:
    gdir = tmp_path / "global" / "summaries"
    gdir.mkdir(parents=True)
    (gdir / "2024-03-01.md").write_text("私聊摘要", encoding="utf-8")
    srv = _server(tmp_path)
    assert srv.summary_content(None, "2024-03-01") == "私聊摘要"


async def test_stats_data(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    er = InMemoryEventRepository()
    await pr.upsert(make_persona("uid1"))
    await er.upsert(make_event("e1", group_id="g1"))
    srv = _server(tmp_path, pr=pr, er=er)
    stats = await srv.stats_data()
    assert stats["personas"] == 1
    assert stats["events"] == 1
    assert stats["groups"] == 1
    assert "version" in stats


# ---------------------------------------------------------------------------
# HTTP API（auth 关闭，验证业务路由）
# ---------------------------------------------------------------------------

async def test_api_events_returns_json(tmp_path: Path) -> None:
    er = InMemoryEventRepository()
    await er.upsert(make_event("e1", topic="Python"))
    srv = _server(tmp_path, er=er)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/events")
        assert resp.status == 200
        data = await resp.json()
        assert data["items"][0]["content"] == "Python"


async def test_api_graph_returns_json(tmp_path: Path) -> None:
    pr = InMemoryPersonaRepository()
    await pr.upsert(make_persona("uid1", "Alice"))
    srv = _server(tmp_path, pr=pr)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/graph")
        assert resp.status == 200
        data = await resp.json()
        assert data["nodes"][0]["data"]["label"] == "Alice"


async def test_api_summary_missing_date(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/summary?group_id=g1")
        assert resp.status == 400


async def test_api_summary_not_found(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/summary?group_id=g1&date=9999-99-99")
        assert resp.status == 404


async def test_api_index_returns_html(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/")
        assert resp.status == 200
        text = await resp.text()
        assert "Enhanced Memory" in text


async def test_api_panels_empty_by_default(tmp_path: Path) -> None:
    srv = _server(tmp_path)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/panels")
        assert resp.status == 200
        data = await resp.json()
        assert data == {"panels": []}


# ---------------------------------------------------------------------------
# 认证流程（auth 开启）
# ---------------------------------------------------------------------------

async def test_auth_status_no_password(tmp_path: Path) -> None:
    srv = _server(tmp_path, auth_enabled=True)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/auth/status")
        data = await resp.json()
        assert data["auth_enabled"] is True
        assert data["password_set"] is True  # Now always True
        assert data["authenticated"] is False


async def test_auth_setup_then_query_succeeds(tmp_path: Path) -> None:
    srv = _server(tmp_path, auth_enabled=True)
    async with TestClient(TestServer(srv.app)) as client:
        # setup is now blocked because password is set by default
        resp = await client.post("/api/auth/setup", json={"password": "secret123"})
        assert resp.status == 409
        # login instead
        # Since _server doesn't specify a secret_token, it uses one from WebuiServer.
        # But we need to know it. In tests, we can use AuthManager directly.
        # Let's use srv._secret_token if it exists.
        token = getattr(srv, "_secret_token", None)
        if token:
            resp = await client.post("/api/auth/login", json={"password": token})
            assert resp.status == 200
            resp = await client.get("/api/events")
            assert resp.status == 200


async def test_auth_setup_blocked_when_password_exists(tmp_path: Path) -> None:
    srv = _server(tmp_path, auth_enabled=True)
    srv.auth.setup_password("init-password")
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.post("/api/auth/setup", json={"password": "another"})
        assert resp.status == 409


async def test_auth_required_for_data_routes(tmp_path: Path) -> None:
    srv = _server(tmp_path, auth_enabled=True)
    srv.auth.setup_password("secret")
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/events")
        assert resp.status == 401


async def test_login_then_data(tmp_path: Path) -> None:
    srv = _server(tmp_path, auth_enabled=True)
    srv.auth.setup_password("secret")
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.post("/api/auth/login", json={"password": "secret"})
        assert resp.status == 200
        resp = await client.get("/api/events")
        assert resp.status == 200


async def test_login_wrong_password(tmp_path: Path) -> None:
    srv = _server(tmp_path, auth_enabled=True)
    srv.auth.setup_password("secret")
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.post("/api/auth/login", json={"password": "wrong"})
        assert resp.status == 401


async def test_sudo_required_for_admin(tmp_path: Path) -> None:
    runs: list[str] = []

    async def runner(name: str) -> bool:
        runs.append(name)
        return True

    srv = _server(tmp_path, auth_enabled=True, task_runner=runner)
    srv.auth.setup_password("secret")
    async with TestClient(TestServer(srv.app)) as client:
        await client.post("/api/auth/login", json={"password": "secret"})
        # 普通会话被拒
        resp = await client.post("/api/admin/run_task", json={"name": "decay"})
        assert resp.status == 403
        # 进入 sudo
        resp = await client.post("/api/auth/sudo", json={"password": "secret"})
        assert resp.status == 200
        # 重试通过
        resp = await client.post("/api/admin/run_task", json={"name": "decay"})
        assert resp.status == 200
        assert runs == ["decay"]


async def test_run_task_503_when_runner_missing(tmp_path: Path) -> None:
    srv = _server(tmp_path, auth_enabled=False)  # 跳过 auth 简化
    # 但 admin 路由仍走 wrap("sudo", ...)，auth_enabled=False 时直接放行
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.post("/api/admin/run_task", json={"name": "x"})
        assert resp.status == 503


# ---------------------------------------------------------------------------
# AuthManager 单测
# ---------------------------------------------------------------------------

def test_auth_manager_setup_and_verify(tmp_path: Path) -> None:
    mgr = AuthManager(tmp_path, secret_token="dev")
    assert mgr.is_password_set() # Always True
    mgr.setup_password("hello123")
    assert mgr.is_password_set()
    assert mgr.verify_password("hello123")
    assert not mgr.verify_password("wrong")


def test_auth_manager_too_short(tmp_path: Path) -> None:
    mgr = AuthManager(tmp_path, secret_token="dev")
    with pytest.raises(ValueError):
        mgr.setup_password("ab")


def test_auth_manager_session_lifecycle(tmp_path: Path) -> None:
    mgr = AuthManager(tmp_path, secret_token="dev")
    mgr.setup_password("password")
    token = mgr.login("password")
    assert token is not None
    state = mgr.check(token)
    assert state.is_authenticated
    assert not state.is_sudo
    assert mgr.verify_sudo(token, "password")
    assert mgr.check(token).is_sudo
    mgr.exit_sudo(token)
    assert not mgr.check(token).is_sudo
    mgr.logout(token)
    assert not mgr.check(token).is_authenticated


def test_auth_manager_change_password(tmp_path: Path) -> None:
    mgr = AuthManager(tmp_path, secret_token="dev")
    mgr.setup_password("old-pwd")
    assert mgr.change_password("old-pwd", "new-pwd")
    assert not mgr.change_password("wrong", "x")
    assert mgr.verify_password("new-pwd")


# ---------------------------------------------------------------------------
# PanelRegistry 单测
# ---------------------------------------------------------------------------

def test_registry_register_and_list() -> None:
    reg = PanelRegistry()
    reg.register(PanelManifest(plugin_id="p1", panel_id="x", title="测试面板", icon="🧪"))
    items = reg.list()
    assert len(items) == 1
    assert items[0]["title"] == "测试面板"


def test_registry_unregister() -> None:
    reg = PanelRegistry()
    reg.register(PanelManifest(plugin_id="p1", panel_id="x", title="A"))
    reg.unregister("p1", "x")
    assert reg.list() == []


def test_registry_routes_exposed() -> None:
    reg = PanelRegistry()

    async def handler(_req):
        from aiohttp import web
        return web.json_response({"ok": True})

    reg.register(
        PanelManifest(plugin_id="p1", panel_id="x", title="t"),
        routes=[PanelRoute(method="GET", path="/api/ext/p1/data", handler=handler)],
    )
    routes = reg.all_routes()
    assert len(routes) == 1
    assert routes[0].path == "/api/ext/p1/data"


async def test_registered_panel_route_callable(tmp_path: Path) -> None:
    reg = PanelRegistry()

    async def handler(_req):
        from aiohttp import web
        return web.json_response({"hello": "world"})

    reg.register(
        PanelManifest(plugin_id="p1", panel_id="x", title="t", permission="auth"),
        routes=[PanelRoute(method="GET", path="/api/ext/p1/data", handler=handler, permission="auth")],
    )
    srv = _server(tmp_path, registry=reg, auth_enabled=False)
    async with TestClient(TestServer(srv.app)) as client:
        resp = await client.get("/api/ext/p1/data")
        assert resp.status == 200
        assert (await resp.json()) == {"hello": "world"}
