"""aiohttp WebUI Server with Unified Port Proxy for Next.js.

Routing permission levels:
  - public: No login required
  - auth: Session required
  - sudo: Secondary password verification required
"""
from __future__ import annotations

import json
import logging
import time
import uuid
import subprocess
import aiohttp
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web

from core.domain.models import Event, Impression, Persona
from core.repository.base import EventRepository, ImpressionRepository, PersonaRepository

from .auth import AuthManager, AuthState, PermLevel
from .registry import PanelRegistry

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_DEFAULT_PORT = 2653
_SESSION_COOKIE = "em_session"


# Serialization helper functions
def _ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _json(data: Any, *, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        content_type="application/json",
        status=status,
    )


def event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "id": event.event_id,
        "content": event.topic or event.event_id[:8],
        "topic": event.topic,
        "start": _ts_to_iso(event.start_time),
        "end": _ts_to_iso(event.end_time),
        "start_ts": event.start_time,
        "end_ts": event.end_time,
        "group": event.group_id,
        "salience": round(event.salience, 3),
        "confidence": round(event.confidence, 3),
        "tags": event.chat_content_tags,
        "inherit_from": event.inherit_from,
        "participants": event.participants,
    }


def persona_to_node(persona: Persona) -> dict[str, Any]:
    return {
        "data": {
            "id": persona.uid,
            "label": persona.primary_name,
            "confidence": round(persona.confidence, 3),
            "attrs": persona.persona_attrs,
            "bound_identities": [
                {"platform": p, "physical_id": pid}
                for p, pid in persona.bound_identities
            ],
            "created_at": _ts_to_iso(persona.created_at),
            "last_active_at": _ts_to_iso(persona.last_active_at),
        }
    }


def impression_to_edge(imp: Impression) -> dict[str, Any]:
    return {
        "data": {
            "id": f"{imp.observer_uid}--{imp.subject_uid}--{imp.scope}",
            "source": imp.observer_uid,
            "target": imp.subject_uid,
            "label": imp.relation_type,
            "affect": round(imp.affect, 3),
            "intensity": round(imp.intensity, 3),
            "confidence": round(imp.confidence, 3),
            "scope": imp.scope,
            "evidence_event_ids": imp.evidence_event_ids,
            "last_reinforced_at": _ts_to_iso(imp.last_reinforced_at),
        }
    }


# ---------------------------------------------------------------------------
# Demo Data Summaries
# ---------------------------------------------------------------------------

_DEMO_SUMMARY_1 = """\
# 群组 demo_group_001 · 2026-05-01

## 主要话题
- Alice 和 Bob 进行了愉快的早安问候，话题延伸至音乐推荐
- Alice 分享了几首新歌，引发了关于独立音乐的讨论

## 情感动态
- 群体氛围积极，用户间互动友好
- Alice 表现出较高的参与热情（重要度 72%）

## 关键事件
1. **早安问候**（重要度 45%）— 日常对话开启当日交流
2. **音乐推荐**（重要度 72%）— 话题丰富，连接昨日对话

## 行动项
- [ ] 跟进 Alice 推荐的音乐播放列表
"""

_DEMO_SUMMARY_2 = """\
# 群组 demo_group_001 · 2026-05-02

## 主要话题
- Alice 和 Charlie 讨论了周末游戏约定
- Bob 和 Charlie 进行了深入的技术交流

## 情感动态
- Charlie 参与度增加，但整体互动相对保守
- Bob 的技术讨论获得较高参与度（重要度 85%）

## 关键事件
1. **游戏约定**（重要度 68%）— Alice 与 Charlie 确定周末安排
2. **技术交流**（重要度 85%）— Bob 主导的编程讨论，内容丰富

## 关系变化
- Bob ↔ Charlie：从陌生人升级为技术话题上的讨论伙伴
- Alice → Charlie：建立了轻松的游戏同好关系
"""

# ---------------------------------------------------------------------------
# WebuiServer
# ---------------------------------------------------------------------------

TaskRunner = Callable[[str], Awaitable[bool]]


class WebuiServer:
    """Three-panel WebUI with Unified Management and Proxy Router."""

    def __init__(
        self,
        persona_repo: PersonaRepository,
        event_repo: EventRepository,
        impression_repo: ImpressionRepository,
        data_dir: Path,
        port: int = _DEFAULT_PORT,
        auth_enabled: bool = True,
        registry: PanelRegistry | None = None,
        task_runner: TaskRunner | None = None,
        plugin_version: str = "0.1.0",
    ) -> None:
        self._persona_repo = persona_repo
        self._event_repo = event_repo
        self._impression_repo = impression_repo
        self._data_dir = data_dir
        self._port = port
        self._auth_enabled = auth_enabled
        self._auth = AuthManager(data_dir)
        self.registry = registry or PanelRegistry()
        self._task_runner = task_runner
        self._plugin_version = plugin_version
        self._recycle_bin: list[dict] = []
        self._app = self._build_app()
        self._runner: web.AppRunner | None = None
        self._frontend_process: subprocess.Popen | None = None

    def _build_app(self) -> web.Application:
        app = web.Application()

        # Authentication
        app.router.add_get("/api/auth/status",
                           self._wrap("public", self._handle_auth_status))
        app.router.add_post("/api/auth/setup",
                            self._wrap("public", self._handle_auth_setup))
        app.router.add_post("/api/auth/login",
                            self._wrap("public", self._handle_auth_login))
        app.router.add_post("/api/auth/logout",
                            self._wrap("auth", self._handle_auth_logout))
        app.router.add_post(
            "/api/auth/sudo", self._wrap("auth", self._handle_auth_sudo))
        app.router.add_post("/api/auth/sudo/exit",
                            self._wrap("auth", self._handle_auth_sudo_exit))
        app.router.add_post(
            "/api/auth/password",
            self._wrap("sudo", self._handle_change_password),
        )

        # Data Query
        app.router.add_get(
            "/api/events", self._wrap("auth", self._handle_events))
        app.router.add_get(
            "/api/graph", self._wrap("auth", self._handle_graph))
        app.router.add_get(
            "/api/summaries", self._wrap("auth", self._handle_summaries))
        app.router.add_get(
            "/api/summary", self._wrap("auth", self._handle_summary))
        app.router.add_get(
            "/api/stats", self._wrap("auth", self._handle_stats))

        # Admin Operations
        app.router.add_post("/api/admin/run_task",
                            self._wrap("sudo", self._handle_run_task))
        app.router.add_put(
            "/api/summary", self._wrap("auth", self._handle_update_summary))
        app.router.add_post("/api/admin/demo",
                            self._wrap("sudo", self._handle_demo))

        # Recall Tests
        app.router.add_get(
            "/api/recall", self._wrap("auth", self._handle_recall))

        # Events CRUD
        app.router.add_post(
            "/api/events", self._wrap("sudo", self._handle_create_event))
        app.router.add_put(
            "/api/events/{event_id}", self._wrap("sudo", self._handle_update_event))
        app.router.add_delete(
            "/api/events/{event_id}", self._wrap("sudo", self._handle_delete_event))
        app.router.add_delete(
            "/api/events", self._wrap("sudo", self._handle_clear_events))

        # Recycle Bin
        app.router.add_get("/api/recycle_bin",
                           self._wrap("auth", self._handle_recycle_bin_list))
        app.router.add_post("/api/recycle_bin/restore",
                            self._wrap("sudo", self._handle_recycle_bin_restore))
        app.router.add_delete(
            "/api/recycle_bin", self._wrap("sudo", self._handle_recycle_bin_clear))

        # Personas CRUD
        app.router.add_post(
            "/api/personas", self._wrap("sudo", self._handle_create_persona))
        app.router.add_put(
            "/api/personas/{uid}", self._wrap("sudo", self._handle_update_persona))
        app.router.add_delete(
            "/api/personas/{uid}", self._wrap("sudo", self._handle_delete_persona))

        # Impressions
        app.router.add_put(
            "/api/impressions/{observer}/{subject}/{scope}",
            self._wrap("sudo", self._handle_update_impression),
        )

        # Third-party Panels
        app.router.add_get(
            "/api/panels", self._wrap("auth", self._handle_panels_list))

        # Inject third-party routes
        for route in self.registry.all_routes():
            app.router.add_route(
                route.method,
                route.path,
                self._wrap(route.permission, lambda req,
                           h=route.handler: h(req)),
            )

        # Proxy Next.js Frontend Catch-all Route
        app.router.add_route("*", "/{tail:.*}", self._handle_proxy)

        return app

    async def _handle_proxy(self, request: web.Request) -> web.StreamResponse:
        """Proxy non-API traffic to the Next.js development server running on port 3000."""
        target_url = f"http://127.0.0.1:3000{request.path_qs}"

        async with aiohttp.ClientSession() as session:
            try:
                try:
                    req_data = await request.read()
                except ConnectionResetError:
                    return web.Response(status=499)

                async with session.request(
                    method=request.method,
                    url=target_url,
                    headers=request.headers,
                    data=req_data
                ) as response:

                    # 强行剥离会引起浏览器解析错误的 Header
                    proxy_headers = {}
                    for k, v in response.headers.items():
                        if k.lower() not in ('transfer-encoding', 'content-encoding', 'content-length'):
                            proxy_headers[k] = v

                    proxy_response = web.StreamResponse(
                        status=response.status,
                        headers=proxy_headers
                    )
                    await proxy_response.prepare(request)

                    try:
                        async for chunk in response.content.iter_chunked(4096):
                            await proxy_response.write(chunk)
                    except (ConnectionResetError, aiohttp.client_exceptions.ClientConnectionResetError):
                        pass

                    return proxy_response

            except aiohttp.ClientConnectorError:
                return web.Response(
                    text="Next.js frontend is starting or unavailable.",
                    status=502
                )

    @property
    def app(self) -> web.Application:
        return self._app

    @property
    def auth(self) -> AuthManager:
        return self._auth

    async def start(self) -> None:
        # Start frontend subprocess targeting the nested 'web/web' directory
        frontend_dir = Path(__file__).parent / "web"
        if frontend_dir.exists() and (frontend_dir / "package.json").exists():
            logger.info("[WebUI] Starting Next.js frontend on port 3000")
            self._frontend_process = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=frontend_dir
            )
        else:
            logger.warning(
                "[WebUI] Frontend directory not found at %s", frontend_dir)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("[WebUI] listening on http://localhost:%d", self._port)

    async def stop(self) -> None:
        if self._frontend_process is not None:
            logger.info("[WebUI] Stopping Next.js frontend process")
            self._frontend_process.terminate()
            self._frontend_process.wait()

        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("[WebUI] stopped")

    # ------------------------------------------------------------------
    # Middleware
    # ------------------------------------------------------------------

    def _wrap(self, level: PermLevel, handler: Callable) -> Callable:
        async def wrapped(request: web.Request) -> web.StreamResponse:
            if not self._auth_enabled or level == "public":
                return await handler(request)
            token = request.cookies.get(_SESSION_COOKIE)
            state = self._auth.check(token)
            if not state.is_authenticated:
                return _json({"error": "unauthorized"}, status=401)
            if level == "sudo" and not state.is_sudo:
                return _json({"error": "sudo required"}, status=403)
            request["auth"] = state
            return await handler(request)
        return wrapped

    # ------------------------------------------------------------------
    # Data Construction
    # ------------------------------------------------------------------

    async def events_data(self, group_id: str | None, limit: int) -> dict[str, Any]:
        if group_id is not None:
            events = await self._event_repo.list_by_group(group_id, limit=limit)
        else:
            group_ids = await self._event_repo.list_group_ids()
            if not group_ids:
                return {"items": []}
            per_group = max(1, limit // len(group_ids))
            events: list[Event] = []
            for gid in group_ids:
                events.extend(await self._event_repo.list_by_group(gid, limit=per_group))
            events = events[:limit]
        return {"items": [event_to_dict(e) for e in events]}

    async def graph_data(self) -> dict[str, Any]:
        personas = await self._persona_repo.list_all()
        nodes = [persona_to_node(p) for p in personas]
        edges: list[dict[str, Any]] = []
        for persona in personas:
            imps = await self._impression_repo.list_by_observer(persona.uid)
            edges.extend(impression_to_edge(imp) for imp in imps)
        return {"nodes": nodes, "edges": edges}

    async def summaries_data(self) -> list[dict[str, str | None]]:
        result: list[dict[str, str | None]] = []
        groups_dir = self._data_dir / "groups"
        if groups_dir.exists():
            for gid_dir in sorted(groups_dir.iterdir()):
                if not gid_dir.is_dir():
                    continue
                sub = gid_dir / "summaries"
                for f in sorted(sub.glob("*.md"), reverse=True) if sub.exists() else []:
                    result.append({"group_id": gid_dir.name,
                                  "date": f.stem, "label": gid_dir.name})
        global_dir = self._data_dir / "global" / "summaries"
        if global_dir.exists():
            for f in sorted(global_dir.glob("*.md"), reverse=True):
                result.append(
                    {"group_id": None, "date": f.stem, "label": "私聊"})
        return result

    def summary_content(self, group_id: str | None, date: str) -> str | None:
        if not date:
            return None
        if group_id:
            path = self._data_dir / "groups" / \
                group_id / "summaries" / f"{date}.md"
        else:
            path = self._data_dir / "global" / "summaries" / f"{date}.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    async def stats_data(self) -> dict[str, Any]:
        personas = await self._persona_repo.list_all()
        group_ids = await self._event_repo.list_group_ids()
        event_count = 0
        for gid in group_ids:
            evs = await self._event_repo.list_by_group(gid, limit=10_000)
            event_count += len(evs)
        impression_count = 0
        for p in personas:
            imps = await self._impression_repo.list_by_observer(p.uid)
            impression_count += len(imps)
        return {
            "personas": len(personas),
            "events": event_count,
            "impressions": impression_count,
            "groups": len(group_ids),
            "version": self._plugin_version,
        }

    # ------------------------------------------------------------------
    # Route Handlers: Static
    # ------------------------------------------------------------------

    async def _handle_index(self, _: web.Request) -> web.Response:
        return web.json_response({
            "message": "WebUI backend is running"
        })

    # ------------------------------------------------------------------
    # Route Handlers: Auth
    # ------------------------------------------------------------------

    async def _handle_auth_status(self, request: web.Request) -> web.Response:
        token = request.cookies.get(_SESSION_COOKIE)
        state = self._auth.check(
            token) if self._auth_enabled else AuthState(True, True)
        return _json({
            "auth_enabled": self._auth_enabled,
            "password_set": self._auth.is_password_set(),
            "authenticated": state.is_authenticated,
            "sudo": state.is_sudo,
            "sudo_remaining_seconds": state.sudo_remaining_seconds,
        })

    async def _handle_auth_setup(self, request: web.Request) -> web.Response:
        if self._auth.is_password_set():
            return _json({"error": "password already set"}, status=409)
        body = await request.json()
        password = body.get("password", "")
        try:
            self._auth.setup_password(password)
        except ValueError as e:
            return _json({"error": str(e)}, status=400)
        token = self._auth.login(password)
        resp = _json({"ok": True})
        if token:
            resp.set_cookie(_SESSION_COOKIE, token,
                            httponly=True, samesite="Lax", path="/")
        return resp

    async def _handle_auth_login(self, request: web.Request) -> web.Response:
        body = await request.json()
        token = self._auth.login(body.get("password", ""))
        if token is None:
            return _json({"error": "invalid password"}, status=401)
        resp = _json({"ok": True})
        resp.set_cookie(_SESSION_COOKIE, token, httponly=True,
                        samesite="Lax", path="/")
        return resp

    async def _handle_auth_logout(self, request: web.Request) -> web.Response:
        self._auth.logout(request.cookies.get(_SESSION_COOKIE))
        resp = _json({"ok": True})
        resp.del_cookie(_SESSION_COOKIE, path="/")
        return resp

    async def _handle_auth_sudo(self, request: web.Request) -> web.Response:
        body = await request.json()
        token = request.cookies.get(_SESSION_COOKIE)
        if not token or not self._auth.check(token).is_authenticated:
            return _json({"error": "session expired, please login again"}, status=401)
        if not self._auth.verify_password(body.get("password", "")):
            return _json({"error": "invalid password"}, status=401)
        if not self._auth.verify_sudo(token, body.get("password", "")):
            return _json({"error": "sudo activation failed"}, status=500)
        state = self._auth.check(token)
        return _json({"ok": True, "sudo_remaining_seconds": state.sudo_remaining_seconds})

    async def _handle_auth_sudo_exit(self, request: web.Request) -> web.Response:
        self._auth.exit_sudo(request.cookies.get(_SESSION_COOKIE))
        return _json({"ok": True})

    async def _handle_change_password(self, request: web.Request) -> web.Response:
        body = await request.json()
        ok = self._auth.change_password(
            body.get("old_password", ""), body.get("new_password", ""))
        if not ok:
            return _json({"error": "old password incorrect or weak new password"}, status=400)
        return _json({"ok": True})

    # ------------------------------------------------------------------
    # Route Handlers: Query
    # ------------------------------------------------------------------

    async def _handle_events(self, request: web.Request) -> web.Response:
        group_id = request.rel_url.query.get("group_id") or None
        limit = int(request.rel_url.query.get("limit", "100"))
        return _json(await self.events_data(group_id, limit))

    async def _handle_graph(self, _: web.Request) -> web.Response:
        return _json(await self.graph_data())

    async def _handle_summaries(self, _: web.Request) -> web.Response:
        return _json(await self.summaries_data())

    async def _handle_summary(self, request: web.Request) -> web.Response:
        group_id = request.rel_url.query.get("group_id") or None
        date = request.rel_url.query.get("date", "")
        if not date:
            return _json({"error": "date required"}, status=400)
        content = self.summary_content(group_id, date)
        if content is None:
            return _json({"error": "not found"}, status=404)
        return _json({"content": content})

    async def _handle_stats(self, _: web.Request) -> web.Response:
        return _json(await self.stats_data())

    # ------------------------------------------------------------------
    # Route Handlers: Admin (sudo)
    # ------------------------------------------------------------------

    async def _handle_run_task(self, request: web.Request) -> web.Response:
        if self._task_runner is None:
            return _json({"error": "task runner not wired"}, status=503)
        body = await request.json()
        name = body.get("name", "")
        if not name:
            return _json({"error": "task name required"}, status=400)
        try:
            ok = await self._task_runner(name)
        except Exception as exc:
            return _json({"error": str(exc)}, status=500)
        return _json({"ok": ok})

    async def _handle_update_summary(self, request: web.Request) -> web.Response:
        body = await request.json()
        group_id = body.get("group_id") or None
        date = body.get("date", "")
        content = body.get("content", "")
        if not date:
            return _json({"error": "date required"}, status=400)
        if group_id:
            path = self._data_dir / "groups" / \
                group_id / "summaries" / f"{date}.md"
        else:
            path = self._data_dir / "global" / "summaries" / f"{date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return _json({"ok": True})

    async def _handle_demo(self, _: web.Request) -> web.Response:
        now = time.time()
        DAY = 86_400

        personas = [
            Persona(
                uid="demo_uid_alice",
                bound_identities=[("qq", "demo_10001")],
                primary_name="Alice",
                persona_attrs={"description": "热情开朗，喜爱音乐与游戏",
                               "affect_type": "积极", "content_tags": ["音乐", "游戏", "聊天"]},
                confidence=0.88,
                created_at=now - 30 * DAY,
                last_active_at=now - DAY,
            ),
            Persona(
                uid="demo_uid_bob",
                bound_identities=[("qq", "demo_10002")],
                primary_name="Bob",
                persona_attrs={"description": "理性谨慎，热衷技术讨论",
                               "affect_type": "中性", "content_tags": ["技术", "编程"]},
                confidence=0.82,
                created_at=now - 25 * DAY,
                last_active_at=now - 2 * DAY,
            ),
            Persona(
                uid="demo_uid_charlie",
                bound_identities=[("telegram", "demo_tg_charlie")],
                primary_name="Charlie",
                persona_attrs={"description": "神秘低调，偶尔参与讨论",
                               "affect_type": "消极", "content_tags": ["旅行", "摄影"]},
                confidence=0.65,
                created_at=now - 15 * DAY,
                last_active_at=now - 5 * DAY,
            ),
            Persona(
                uid="demo_uid_bot",
                bound_identities=[("internal", "bot")],
                primary_name="BOT",
                persona_attrs={"description": "AI 助手",
                               "affect_type": "中性", "content_tags": []},
                confidence=1.0,
                created_at=now - 60 * DAY,
                last_active_at=now,
            ),
        ]

        events = [
            Event(
                event_id="demo_evt_001",
                group_id="demo_group_001",
                start_time=now - 7 * DAY,
                end_time=now - 7 * DAY + 1800,
                participants=["demo_uid_alice",
                              "demo_uid_bob", "demo_uid_bot"],
                interaction_flow=[],
                topic="早安问候",
                chat_content_tags=["日常", "问候"],
                salience=0.45,
                confidence=0.82,
                inherit_from=[],
                last_accessed_at=now - DAY,
            ),
            Event(
                event_id="demo_evt_002",
                group_id="demo_group_001",
                start_time=now - 6 * DAY,
                end_time=now - 6 * DAY + 3600,
                participants=["demo_uid_alice",
                              "demo_uid_bob", "demo_uid_bot"],
                interaction_flow=[],
                topic="音乐推荐",
                chat_content_tags=["音乐", "推荐", "文化"],
                salience=0.72,
                confidence=0.88,
                inherit_from=["demo_evt_001"],
                last_accessed_at=now - 12 * 3600,
            ),
            Event(
                event_id="demo_evt_003",
                group_id="demo_group_001",
                start_time=now - 5 * DAY,
                end_time=now - 5 * DAY + 2700,
                participants=["demo_uid_alice",
                              "demo_uid_charlie", "demo_uid_bot"],
                interaction_flow=[],
                topic="游戏约定",
                chat_content_tags=["游戏", "约定", "娱乐"],
                salience=0.68,
                confidence=0.79,
                inherit_from=["demo_evt_002"],
                last_accessed_at=now - 8 * 3600,
            ),
            Event(
                event_id="demo_evt_004",
                group_id="demo_group_001",
                start_time=now - 3 * DAY,
                end_time=now - 3 * DAY + 4200,
                participants=["demo_uid_bob",
                              "demo_uid_charlie", "demo_uid_bot"],
                interaction_flow=[],
                topic="技术交流",
                chat_content_tags=["技术", "编程", "讨论"],
                salience=0.85,
                confidence=0.91,
                inherit_from=["demo_evt_001"],
                last_accessed_at=now - 4 * 3600,
            ),
            Event(
                event_id="demo_evt_005",
                group_id=None,
                start_time=now - DAY,
                end_time=now - DAY + 900,
                participants=["demo_uid_alice", "demo_uid_bot"],
                interaction_flow=[],
                topic="私聊请教",
                chat_content_tags=["私聊", "帮助"],
                salience=0.55,
                confidence=0.77,
                inherit_from=[],
                last_accessed_at=now - 3600,
            ),
        ]

        impressions = [
            Impression(
                observer_uid="demo_uid_bot", subject_uid="demo_uid_alice",
                relation_type="friend", affect=0.7, intensity=0.6, confidence=0.85,
                scope="global",
                evidence_event_ids=["demo_evt_001",
                                    "demo_evt_002", "demo_evt_005"],
                last_reinforced_at=now - DAY,
            ),
            Impression(
                observer_uid="demo_uid_bot", subject_uid="demo_uid_bob",
                relation_type="colleague", affect=0.2, intensity=0.4, confidence=0.78,
                scope="global",
                evidence_event_ids=["demo_evt_001", "demo_evt_004"],
                last_reinforced_at=now - 2 * DAY,
            ),
            Impression(
                observer_uid="demo_uid_alice", subject_uid="demo_uid_bot",
                relation_type="friend", affect=0.8, intensity=0.7, confidence=0.80,
                scope="global",
                evidence_event_ids=["demo_evt_001", "demo_evt_002"],
                last_reinforced_at=now - DAY,
            ),
            Impression(
                observer_uid="demo_uid_bob", subject_uid="demo_uid_alice",
                relation_type="friend", affect=0.5, intensity=0.5, confidence=0.72,
                scope="demo_group_001",
                evidence_event_ids=["demo_evt_002"],
                last_reinforced_at=now - 6 * DAY,
            ),
            Impression(
                observer_uid="demo_uid_charlie", subject_uid="demo_uid_bob",
                relation_type="stranger", affect=-0.2, intensity=0.3, confidence=0.60,
                scope="demo_group_001",
                evidence_event_ids=["demo_evt_004"],
                last_reinforced_at=now - 3 * DAY,
            ),
        ]

        for p in personas:
            await self._persona_repo.upsert(p)
        for e in events:
            await self._event_repo.upsert(e)
        for imp in impressions:
            await self._impression_repo.upsert(imp)

        for date, content in [("2026-05-01", _DEMO_SUMMARY_1), ("2026-05-02", _DEMO_SUMMARY_2)]:
            path = self._data_dir / "groups" / \
                "demo_group_001" / "summaries" / f"{date}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        return _json({"ok": True, "seeded": {
            "personas": len(personas),
            "events": len(events),
            "impressions": len(impressions),
            "summaries": 2,
        }})

    # ------------------------------------------------------------------
    # Route Handlers: Recall
    # ------------------------------------------------------------------

    async def _handle_recall(self, request: web.Request) -> web.Response:
        q = request.rel_url.query.get("q", "").strip()
        limit = min(int(request.rel_url.query.get("limit", "5")), 50)
        if not q:
            return _json({"error": "q required"}, status=400)
        try:
            fts_results = await self._event_repo.search_fts(q, limit=limit)
        except Exception as exc:
            return _json({"error": str(exc)}, status=500)
        return _json({
            "items": [event_to_dict(e) for e in fts_results],
            "algorithm": "fts5",
            "query": q,
            "count": len(fts_results),
        })

    # ------------------------------------------------------------------
    # Route Handlers: Events CRUD
    # ------------------------------------------------------------------

    async def _handle_create_event(self, request: web.Request) -> web.Response:
        body = await request.json()
        now = time.time()
        try:
            event = Event(
                event_id=body.get("event_id") or str(uuid.uuid4()),
                group_id=body.get("group_id") or None,
                start_time=float(body.get("start_time", now)),
                end_time=float(body.get("end_time", now)),
                participants=body.get("participants", []),
                interaction_flow=[],
                topic=body.get("topic", ""),
                chat_content_tags=body.get("chat_content_tags", []),
                salience=float(body.get("salience", 0.5)),
                confidence=float(body.get("confidence", 0.8)),
                inherit_from=body.get("inherit_from", []),
                last_accessed_at=now,
            )
        except (ValueError, TypeError) as exc:
            return _json({"error": str(exc)}, status=400)
        await self._event_repo.upsert(event)
        return _json({"ok": True, "event": event_to_dict(event)}, status=201)

    async def _handle_update_event(self, request: web.Request) -> web.Response:
        event_id = request.match_info["event_id"]
        existing = await self._event_repo.get(event_id)
        if existing is None:
            return _json({"error": "not found"}, status=404)
        body = await request.json()
        now = time.time()
        try:
            updated = Event(
                event_id=existing.event_id,
                group_id=body.get("group_id", existing.group_id),
                start_time=float(body.get("start_time", existing.start_time)),
                end_time=float(body.get("end_time", existing.end_time)),
                participants=body.get("participants", existing.participants),
                interaction_flow=existing.interaction_flow,
                topic=body.get("topic", existing.topic),
                chat_content_tags=body.get(
                    "chat_content_tags", existing.chat_content_tags),
                salience=float(body.get("salience", existing.salience)),
                confidence=float(body.get("confidence", existing.confidence)),
                inherit_from=body.get("inherit_from", existing.inherit_from),
                last_accessed_at=now,
            )
        except (ValueError, TypeError) as exc:
            return _json({"error": str(exc)}, status=400)
        await self._event_repo.upsert(updated)
        return _json({"ok": True, "event": event_to_dict(updated)})

    async def _handle_delete_event(self, request: web.Request) -> web.Response:
        event_id = request.match_info["event_id"]
        existing = await self._event_repo.get(event_id)
        if existing is None:
            return _json({"error": "not found"}, status=404)
        self._recycle_bin.append({
            **event_to_dict(existing),
            "deleted_at": _ts_to_iso(time.time()),
        })
        await self._event_repo.delete(event_id)
        return _json({"ok": True})

    async def _handle_clear_events(self, _: web.Request) -> web.Response:
        group_ids = await self._event_repo.list_group_ids()
        deleted = 0
        for gid in group_ids:
            events = await self._event_repo.list_by_group(gid, limit=10_000)
            for ev in events:
                self._recycle_bin.append({
                    **event_to_dict(ev),
                    "deleted_at": _ts_to_iso(time.time()),
                })
                await self._event_repo.delete(ev.event_id)
                deleted += 1
        return _json({"ok": True, "deleted": deleted})

    # ------------------------------------------------------------------
    # Route Handlers: Recycle Bin
    # ------------------------------------------------------------------

    async def _handle_recycle_bin_list(self, _: web.Request) -> web.Response:
        return _json({"items": list(reversed(self._recycle_bin))})

    async def _handle_recycle_bin_restore(self, request: web.Request) -> web.Response:
        body = await request.json()
        event_id = body.get("event_id", "")
        if not event_id:
            return _json({"error": "event_id required"}, status=400)
        item = next(
            (x for x in self._recycle_bin if x["id"] == event_id), None)
        if item is None:
            return _json({"error": "not found in recycle bin"}, status=404)
        now = time.time()
        try:
            event = Event(
                event_id=item["id"],
                group_id=item.get("group"),
                start_time=item.get("start_ts", now),
                end_time=item.get("end_ts", now),
                participants=item.get("participants", []),
                interaction_flow=[],
                topic=item.get("topic", item.get("content", "")),
                chat_content_tags=item.get("tags", []),
                salience=item.get("salience", 0.5),
                confidence=item.get("confidence", 0.8),
                inherit_from=item.get("inherit_from", []),
                last_accessed_at=now,
            )
        except (ValueError, TypeError) as exc:
            return _json({"error": str(exc)}, status=400)
        await self._event_repo.upsert(event)
        self._recycle_bin = [
            x for x in self._recycle_bin if x["id"] != event_id]
        return _json({"ok": True, "event": event_to_dict(event)})

    async def _handle_recycle_bin_clear(self, _: web.Request) -> web.Response:
        count = len(self._recycle_bin)
        self._recycle_bin.clear()
        return _json({"ok": True, "cleared": count})

    # ------------------------------------------------------------------
    # Route Handlers: Personas CRUD
    # ------------------------------------------------------------------

    async def _handle_create_persona(self, request: web.Request) -> web.Response:
        body = await request.json()
        now = time.time()
        raw_bindings = body.get("bound_identities", [])
        bindings: list[tuple[str, str]] = [
            (b["platform"], b["physical_id"])
            for b in raw_bindings
            if isinstance(b, dict) and "platform" in b and "physical_id" in b
        ]
        try:
            persona = Persona(
                uid=body.get("uid") or str(uuid.uuid4()),
                bound_identities=bindings,
                primary_name=body.get("primary_name", ""),
                persona_attrs={
                    "description": body.get("description", ""),
                    "affect_type": body.get("affect_type", ""),
                    "content_tags": body.get("content_tags", []),
                },
                confidence=float(body.get("confidence", 0.8)),
                created_at=now,
                last_active_at=now,
            )
        except (ValueError, TypeError) as exc:
            return _json({"error": str(exc)}, status=400)
        await self._persona_repo.upsert(persona)
        return _json({"ok": True, "persona": persona_to_node(persona)}, status=201)

    async def _handle_update_persona(self, request: web.Request) -> web.Response:
        uid = request.match_info["uid"]
        existing = await self._persona_repo.get(uid)
        if existing is None:
            return _json({"error": "not found"}, status=404)
        body = await request.json()
        raw_bindings = body.get("bound_identities")
        if raw_bindings is not None:
            bindings: list[tuple[str, str]] = [
                (b["platform"], b["physical_id"])
                for b in raw_bindings
                if isinstance(b, dict) and "platform" in b and "physical_id" in b
            ]
        else:
            bindings = existing.bound_identities
        existing_attrs = existing.persona_attrs or {}
        updated_attrs = {
            "description": body.get("description", existing_attrs.get("description", "")),
            "affect_type": body.get("affect_type", existing_attrs.get("affect_type", "")),
            "content_tags": body.get("content_tags", existing_attrs.get("content_tags", [])),
        }
        try:
            updated = Persona(
                uid=existing.uid,
                bound_identities=bindings,
                primary_name=body.get("primary_name", existing.primary_name),
                persona_attrs=updated_attrs,
                confidence=float(body.get("confidence", existing.confidence)),
                created_at=existing.created_at,
                last_active_at=time.time(),
            )
        except (ValueError, TypeError) as exc:
            return _json({"error": str(exc)}, status=400)
        await self._persona_repo.upsert(updated)
        return _json({"ok": True, "persona": persona_to_node(updated)})

    async def _handle_delete_persona(self, request: web.Request) -> web.Response:
        uid = request.match_info["uid"]
        ok = await self._persona_repo.delete(uid)
        if not ok:
            return _json({"error": "not found"}, status=404)
        return _json({"ok": True})

    # ------------------------------------------------------------------
    # Route Handlers: Impressions
    # ------------------------------------------------------------------

    async def _handle_update_impression(self, request: web.Request) -> web.Response:
        observer = request.match_info["observer"]
        subject = request.match_info["subject"]
        scope = request.match_info["scope"]
        existing = await self._impression_repo.get(observer, subject, scope)
        body = await request.json()
        now = time.time()
        try:
            impression = Impression(
                observer_uid=observer,
                subject_uid=subject,
                relation_type=body.get("relation_type",
                                       existing.relation_type if existing else "stranger"),
                affect=float(body.get("affect",
                                      existing.affect if existing else 0.0)),
                intensity=float(body.get("intensity",
                                         existing.intensity if existing else 0.5)),
                confidence=float(body.get("confidence",
                                          existing.confidence if existing else 0.7)),
                scope=scope,
                evidence_event_ids=body.get("evidence_event_ids",
                                            existing.evidence_event_ids if existing else []),
                last_reinforced_at=now,
            )
        except (ValueError, TypeError) as exc:
            return _json({"error": str(exc)}, status=400)
        await self._impression_repo.upsert(impression)
        return _json({"ok": True, "impression": impression_to_edge(impression)["data"]})

    # ------------------------------------------------------------------
    # Route Handlers: Panels
    # ------------------------------------------------------------------

    async def _handle_panels_list(self, _: web.Request) -> web.Response:
        return _json({"panels": self.registry.list()})
