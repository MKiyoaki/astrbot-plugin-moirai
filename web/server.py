"""aiohttp WebUI 服务器 — 三轴记忆面板 + 统一管理 + 第三方面板挂载点。

路由权限分级：
  - public：无需登录（/login、/api/auth/setup、/api/auth/status）
  - auth：需要会话（GET 类只读接口）
  - sudo：需要二级密码验证（POST 写操作、敏感配置）

数据构建逻辑（events_data / graph_data / summaries_data）保持纯异步，
不依赖 HTTP 上下文，方便测试直接调用。
"""
from __future__ import annotations

import json
import logging
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


# ---------------------------------------------------------------------------
# 序列化辅助函数（纯函数，可单独测试）
# ---------------------------------------------------------------------------

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
        "start": _ts_to_iso(event.start_time),
        "end": _ts_to_iso(event.end_time),
        "group": event.group_id,
        "salience": round(event.salience, 3),
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
        }
    }


# ---------------------------------------------------------------------------
# WebuiServer
# ---------------------------------------------------------------------------

# 任务执行器协议：传入任务名，返回是否成功（实际由 main.py 注入 TaskScheduler.run_now）
TaskRunner = Callable[[str], Awaitable[bool]]


class WebuiServer:
    """三面板 WebUI + 统一管理 + 面板注册中心。

    所有写操作（密码修改、任务触发、配置更新）都需要 sudo 模式。
    """

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
        self._app = self._build_app()
        self._runner: web.AppRunner | None = None

    # ------------------------------------------------------------------
    # 应用构建
    # ------------------------------------------------------------------

    def _build_app(self) -> web.Application:
        app = web.Application()
        # 静态/HTML
        app.router.add_get("/", self._handle_index)
        app.router.add_static("/static", _STATIC_DIR)
        # 认证
        app.router.add_get("/api/auth/status", self._wrap("public", self._handle_auth_status))
        app.router.add_post("/api/auth/setup", self._wrap("public", self._handle_auth_setup))
        app.router.add_post("/api/auth/login", self._wrap("public", self._handle_auth_login))
        app.router.add_post("/api/auth/logout", self._wrap("auth", self._handle_auth_logout))
        app.router.add_post("/api/auth/sudo", self._wrap("auth", self._handle_auth_sudo))
        app.router.add_post("/api/auth/sudo/exit", self._wrap("auth", self._handle_auth_sudo_exit))
        app.router.add_post(
            "/api/auth/password",
            self._wrap("sudo", self._handle_change_password),
        )
        # 数据查询
        app.router.add_get("/api/events", self._wrap("auth", self._handle_events))
        app.router.add_get("/api/graph", self._wrap("auth", self._handle_graph))
        app.router.add_get("/api/summaries", self._wrap("auth", self._handle_summaries))
        app.router.add_get("/api/summary", self._wrap("auth", self._handle_summary))
        app.router.add_get("/api/stats", self._wrap("auth", self._handle_stats))
        # 管理操作（sudo）
        app.router.add_post("/api/admin/run_task", self._wrap("sudo", self._handle_run_task))
        # 第三方面板注册
        app.router.add_get("/api/panels", self._wrap("auth", self._handle_panels_list))
        # 注入第三方插件已注册的路由
        for route in self.registry.all_routes():
            app.router.add_route(
                route.method,
                route.path,
                self._wrap(route.permission, lambda req, h=route.handler: h(req)),
            )
        return app

    @property
    def app(self) -> web.Application:
        return self._app

    @property
    def auth(self) -> AuthManager:
        return self._auth

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("[WebUI] listening on http://localhost:%d", self._port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("[WebUI] stopped")

    # ------------------------------------------------------------------
    # 中间件（包装 handler 实现权限校验）
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
    # 数据构建（async，可独立测试）
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
                    result.append({"group_id": gid_dir.name, "date": f.stem, "label": gid_dir.name})
        global_dir = self._data_dir / "global" / "summaries"
        if global_dir.exists():
            for f in sorted(global_dir.glob("*.md"), reverse=True):
                result.append({"group_id": None, "date": f.stem, "label": "私聊"})
        return result

    def summary_content(self, group_id: str | None, date: str) -> str | None:
        if not date:
            return None
        if group_id:
            path = self._data_dir / "groups" / group_id / "summaries" / f"{date}.md"
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
    # 路由处理器：静态页
    # ------------------------------------------------------------------

    async def _handle_index(self, _: web.Request) -> web.Response:
        return web.Response(
            text=(_STATIC_DIR / "index.html").read_text(encoding="utf-8"),
            content_type="text/html",
        )

    # ------------------------------------------------------------------
    # 路由处理器：认证
    # ------------------------------------------------------------------

    async def _handle_auth_status(self, request: web.Request) -> web.Response:
        token = request.cookies.get(_SESSION_COOKIE)
        state = self._auth.check(token) if self._auth_enabled else AuthState(True, True)
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
            resp.set_cookie(_SESSION_COOKIE, token, httponly=True, samesite="Strict", path="/")
        return resp

    async def _handle_auth_login(self, request: web.Request) -> web.Response:
        body = await request.json()
        token = self._auth.login(body.get("password", ""))
        if token is None:
            return _json({"error": "invalid password"}, status=401)
        resp = _json({"ok": True})
        resp.set_cookie(_SESSION_COOKIE, token, httponly=True, samesite="Strict", path="/")
        return resp

    async def _handle_auth_logout(self, request: web.Request) -> web.Response:
        self._auth.logout(request.cookies.get(_SESSION_COOKIE))
        resp = _json({"ok": True})
        resp.del_cookie(_SESSION_COOKIE, path="/")
        return resp

    async def _handle_auth_sudo(self, request: web.Request) -> web.Response:
        body = await request.json()
        token = request.cookies.get(_SESSION_COOKIE)
        if not self._auth.verify_sudo(token, body.get("password", "")):
            return _json({"error": "invalid password"}, status=401)
        state = self._auth.check(token)
        return _json({"ok": True, "sudo_remaining_seconds": state.sudo_remaining_seconds})

    async def _handle_auth_sudo_exit(self, request: web.Request) -> web.Response:
        self._auth.exit_sudo(request.cookies.get(_SESSION_COOKIE))
        return _json({"ok": True})

    async def _handle_change_password(self, request: web.Request) -> web.Response:
        body = await request.json()
        ok = self._auth.change_password(body.get("old_password", ""), body.get("new_password", ""))
        if not ok:
            return _json({"error": "old password incorrect or weak new password"}, status=400)
        return _json({"ok": True})

    # ------------------------------------------------------------------
    # 路由处理器：数据查询
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
    # 路由处理器：管理操作（sudo）
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

    # ------------------------------------------------------------------
    # 路由处理器：面板注册
    # ------------------------------------------------------------------

    async def _handle_panels_list(self, _: web.Request) -> web.Response:
        return _json({"panels": self.registry.list()})
