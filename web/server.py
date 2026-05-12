from __future__ import annotations
import secrets
"""aiohttp WebUI Server — Three-axis Memory Panel + Unified Management + Third-party Panel Mount.

Route permission levels:
  - public: No login required (/login, /api/auth/setup, /api/auth/status)
  - auth: Session required (GET read-only interfaces)
  - sudo: Secondary password verification required (use configured password or auto-generated token) (POST write operations, sensitive configurations)

Data construction logic (events_data / graph_data / summaries_data) is kept purely asynchronous
and independent of the HTTP context for easier direct testing.
"""

import asyncio
import json
import logging
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web

from core.domain.models import Event, Impression, Persona, MessageRef
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)

from .auth import AuthManager, AuthState, PermLevel
from .registry import PanelRegistry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from core.repository.base import EventRepository, ImpressionRepository, PersonaRepository
    from core.managers.base import BaseRecallManager

    TaskRunner = Callable[[str], Awaitable[bool]]

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "frontend" / "output"
_DEFAULT_PORT = 2655
_SESSION_COOKIE = "em_session"


# Serialization helper functions (pure functions, independently testable)
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
        "topic": event.topic or "",
        "summary": event.summary or "",
        "start": _ts_to_iso(event.start_time),
        "end": _ts_to_iso(event.end_time),
        "start_ts": event.start_time,
        "end_ts": event.end_time,
        "group": event.group_id,
        "salience": round(event.salience, 3) if event.salience is not None else 0.5,
        "confidence": round(event.confidence, 3) if event.confidence is not None else 0.8,
        "tags": event.chat_content_tags if event.chat_content_tags is not None else [],
        "inherit_from": event.inherit_from if event.inherit_from is not None else [],
        "participants": event.participants if event.participants is not None else [],
        "status": event.status or "active",
        "is_locked": bool(event.is_locked),
        "bot_persona_name": event.bot_persona_name,
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
            "is_bot": any(p == "internal" for p, _ in persona.bound_identities),
        }
    }


def impression_to_edge(imp: Impression) -> dict[str, Any]:
    return {
        "data": {
            "id": f"{imp.observer_uid}--{imp.subject_uid}--{imp.scope}",
            "source": imp.observer_uid,
            "target": imp.subject_uid,
            "label": imp.ipc_orientation,
            "affect": round(imp.benevolence, 3),
            "intensity": round(imp.affect_intensity, 3),
            "power": round(imp.power, 3),
            "r_squared": round(imp.r_squared, 3),
            "confidence": round(imp.confidence, 3),
            "scope": imp.scope,
            "evidence_event_ids": imp.evidence_event_ids,
            "last_reinforced_at": _ts_to_iso(imp.last_reinforced_at),
        }
    }


# Demo data summaries (module-level constants, used by _handle_demo)

_DEMO_SUMMARY_1 = """\
# 群组 demo_group_001 活动摘要 — 2026-05-01 08:00 - 12:00

[主要话题]
Alice 和 Bob 进行了早安问候，随后 Alice 分享了几首独立音乐新歌，引发了群组关于音乐推荐的讨论，整体氛围轻松积极。

[事件列表]
[早安问候] - [demo_e01] | *在Bob发出了早，Alice。结束了话题后话题转向了 | [音乐推荐] - [demo_e02]

[情感动态]
群体情感动态整体偏向[亲和] | [亲和度：+0.62；支配度：-0.15] | [Alice处于群体中的亲和位置] | [Bob处于群体中的谦让位置]
"""

_DEMO_SUMMARY_2 = """\
# 群组 demo_group_001 活动摘要 — 2026-05-02 14:00 - 18:00

[主要话题]
Alice 与 Charlie 确定了周末游戏约定，Bob 与 Charlie 深入探讨了 Python asyncio 的并发优化策略，Bob 主导话语权，Charlie 积极参与技术交流。

[事件列表]
[游戏约定] - [demo_e03] | *在Charlie发出了好啊，我也有空结束了话题后话题转向了 | [技术交流] - [demo_e04]

[情感动态]
群体情感动态整体偏向[活跃] | [亲和度：+0.41；支配度：+0.38] | [Bob处于群体中的掌控位置] | [Alice, Charlie处于群体中的亲和位置]
"""


class WebuiServer:
    """Three-panel WebUI + Unified Management + Panel Registry.

    All write operations (password modification, task triggering, config updates) require sudo mode.
    """

    # Path to the plugin configuration schema (one level above web/)
    _CONF_SCHEMA_PATH = Path(__file__).parent.parent / "_conf_schema.json"

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
        initial_config: dict | None = None,
        provider_getter: Callable | None = None,
        all_providers_getter: Callable | None = None,
        recall_manager: BaseRecallManager | None = None,
    ) -> None:
        self._persona_repo = persona_repo
        self._event_repo = event_repo
        self._impression_repo = impression_repo
        self._recall_manager = recall_manager
        self._data_dir = data_dir
        self._port = port
        self._auth_enabled = auth_enabled

        # Determine secret token or configured password
        cfg_password = (initial_config or {}).get("webui_password", "").strip()
        if not cfg_password and auth_enabled:
            self._secret_token = secrets.token_urlsafe(16)
        else:
            self._secret_token = cfg_password or None

        self._auth = AuthManager(data_dir, secret_token=self._secret_token)
        self.registry = registry or PanelRegistry()
        self._task_runner = task_runner
        self._provider_getter = provider_getter
        self._all_providers_getter = all_providers_getter
        self._plugin_version = plugin_version

        # Plugin config: stored at data_dir/plugin_config.json, seeded from initial_config
        self._config_path = data_dir / "plugin_config.json"
        self._initial_config: dict = initial_config or {}

        # Feature flags derived from initial config (evaluated once at startup)
        self._relation_enabled: bool = bool(
            (initial_config or {}).get("relation_enabled", True)
        )

        # In-memory recycle bin (session-scoped)
        self._recycle_bin: list[dict] = []
        self._app = self._build_app()
        self._runner: web.AppRunner | None = None

    def _ensure_frontend_build(self) -> None:
        """Automated build logic: Triggers static build only in dev environment when the static folder is missing."""
        frontend_src = Path(__file__).parent / "frontend"

        # If the static folder exists and is not empty, proceed directly (user-side execution logic)
        if _STATIC_DIR.exists() and any(_STATIC_DIR.iterdir()):
            logger.info(
                "[WebUI] Static resources are ready, loading directly.")
            return

        # If frontend source code exists, it indicates a dev environment, execute the build process
        if (frontend_src / "package.json").exists():
            logger.info(
                "[WebUI] First run or missing static assets, automating frontend build, please wait...")
            try:
                # Use shell=True to inherit system NVM environment
                logger.info(
                    "[WebUI] Installing frontend dependencies (npm install)...")
                subprocess.run("npm install", cwd=frontend_src,
                               shell=True, check=True)

                logger.info(
                    "[WebUI] Executing static compilation (npm run build)...")
                subprocess.run("npm run build", cwd=frontend_src,
                               shell=True, check=True)

                logger.info(
                    "[WebUI] Frontend static compilation completed! Resources saved to: %s", _STATIC_DIR)
            except subprocess.CalledProcessError as e:
                logger.error(
                    "[WebUI] Automated build failed. Please check your Node.js environment or manually run build in the web/web directory. Error: %s", e)
        else:
            logger.warning(
                "[WebUI] Cannot start frontend: Static assets folder 'static' not found and source directory is missing.")

    # Application construction
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

        # Data queries
        app.router.add_get(
            "/api/events", self._wrap("auth", self._handle_events))
        app.router.add_get(
            "/api/graph", self._wrap("auth", self._handle_graph_guarded))
        app.router.add_get(
            "/api/summaries", self._wrap("auth", self._handle_summaries))
        app.router.add_get(
            "/api/summary", self._wrap("auth", self._handle_summary))
        app.router.add_get(
            "/api/stats", self._wrap("auth", self._handle_stats))
        app.router.add_get(
            "/api/soul/states", self._wrap("auth", self._handle_soul_states))

        # Admin operations (sudo)
        app.router.add_post("/api/admin/run_task",
                            self._wrap("sudo", self._handle_run_task))
        app.router.add_put(
            "/api/summary", self._wrap("auth", self._handle_update_summary))
        app.router.add_post(
            "/api/summary/regenerate", self._wrap("sudo", self._handle_regenerate_summary))
        app.router.add_post("/api/admin/demo",
                            self._wrap("sudo", self._handle_demo))

        # Memory recall testing
        app.router.add_get(
            "/api/recall", self._wrap("auth", self._handle_recall))

        # Event CRUD
        app.router.add_post(
            "/api/events", self._wrap("sudo", self._handle_create_event))
        app.router.add_put(
            "/api/events/{event_id}", self._wrap("sudo", self._handle_update_event))
        app.router.add_delete(
            "/api/events/{event_id}", self._wrap("sudo", self._handle_delete_event))
        app.router.add_delete(
            "/api/events", self._wrap("sudo", self._handle_clear_events))

        # Recycle bin
        app.router.add_get("/api/recycle_bin",
                           self._wrap("auth", self._handle_recycle_bin_list))
        app.router.add_post("/api/recycle_bin/restore",
                            self._wrap("sudo", self._handle_recycle_bin_restore))
        app.router.add_delete(
            "/api/recycle_bin", self._wrap("sudo", self._handle_recycle_bin_clear))

        # Persona CRUD
        app.router.add_post(
            "/api/personas", self._wrap("sudo", self._handle_create_persona))
        app.router.add_put(
            "/api/personas/{uid}", self._wrap("sudo", self._handle_update_persona))
        app.router.add_delete(
            "/api/personas/{uid}", self._wrap("sudo", self._handle_delete_persona))

        # Impression updates
        app.router.add_put(
            "/api/impressions/{observer}/{subject}/{scope}",
            self._wrap("sudo", self._handle_update_impression_guarded),
        )

        # Tags aggregation
        app.router.add_get(
            "/api/tags", self._wrap("auth", self._handle_tags))

        # Plugin config
        app.router.add_get(
            "/api/config", self._wrap("auth", self._handle_get_config))
        app.router.add_put(
            "/api/config", self._wrap("sudo", self._handle_update_config))
        app.router.add_get(
            "/api/config/schema", self._wrap("auth", self._handle_get_config_schema))
        app.router.add_get(
            "/api/config/providers", self._wrap("auth", self._handle_get_providers))

        # Third-party panel registration
        app.router.add_get(
            "/api/panels", self._wrap("auth", self._handle_panels_list))

        # Inject routes registered by third-party plugins
        for route in self.registry.all_routes():
            app.router.add_route(
                route.method,
                route.path,
                self._wrap(route.permission, lambda req,
                           h=route.handler: h(req)),
            )

        # Static files and SPA route fallback (must be placed last)
        app.router.add_get("/", self._handle_spa_fallback)
        app.router.add_get("/{tail:.*}", self._handle_spa_fallback)

        return app

    async def _handle_spa_fallback(self, request: web.Request) -> web.Response:
        """Handle Next.js static export SPA routing and fallback mechanism."""
        # Prevent accidental interception of API requests
        if request.path.startswith("/api/"):
            return web.Response(status=404, text="API Endpoint Not Found")

        path = request.match_info.get("tail", "").strip("/")
        if not path:
            path = "index.html"

        target_file = _STATIC_DIR / path

        # Security check: Prevent path traversal attacks
        try:
            target_file.resolve().relative_to(_STATIC_DIR.resolve())
        except ValueError:
            return web.Response(status=403, text="Forbidden")

        # 1. Serve static resources directly (CSS, JS, images)
        if target_file.is_file():
            return web.FileResponse(target_file)

        # 2. Next.js trailingSlash export: /events -> events/index.html
        dir_index = _STATIC_DIR / path / "index.html"
        if dir_index.is_file():
            return web.FileResponse(dir_index)

        # 3. Non-trailingSlash export fallback: /login -> /login.html
        html_file = _STATIC_DIR / f"{path}.html"
        if html_file.is_file():
            return web.FileResponse(html_file)

        # 4. Final fallback: hand over SPA routing to index.html
        index_file = _STATIC_DIR / "index.html"
        if index_file.is_file():
            return web.FileResponse(index_file)

        # Case where files are completely missing
        return web.Response(status=404, text="Frontend static files not found. Please ensure the frontend is built.")

    @property
    def app(self) -> web.Application:
        return self._app

    @property
    def auth(self) -> AuthManager:
        return self._auth

    async def start(self) -> None:
        # Ensure static resources are ready
        self._ensure_frontend_build()

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

    # Middleware (wraps handler to implement permission validation)

    def _wrap(self, level: PermLevel, handler: Callable) -> Callable:
        async def wrapped(request: web.Request) -> web.StreamResponse:
            try:
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
            except Exception as exc:
                logger.exception(
                    "[WebUI] Unhandled error in %s %s", request.method, request.path)
                return _json({"error": str(exc)}, status=500)
        return wrapped

    # Data construction (async, independently testable)

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
        return {"items": [event_to_dict(e) for e in events], "total": len(events)}

    async def graph_data(self) -> dict[str, Any]:
        personas = await self._persona_repo.list_all()
        uid_msg_counts = await self._event_repo.count_messages_by_uid_bulk()

        nodes = []
        for p in personas:
            node = persona_to_node(p)
            node["data"]["msg_count"] = uid_msg_counts.get(p.uid, 0)
            nodes.append(node)

        edges: list[dict[str, Any]] = []
        for persona in personas:
            imps = await self._impression_repo.list_by_observer(persona.uid)
            for imp in imps:
                edge = impression_to_edge(imp)
                edge["data"]["msg_count"] = await self._event_repo.count_edge_messages(
                    imp.observer_uid, imp.subject_uid, imp.scope
                )
                edges.append(edge)

        # Build group membership: group_id → [uid, ...]
        group_members: dict[str, list[str]] = {}
        group_ids = await self._event_repo.list_group_ids()
        for gid in group_ids:
            events = await self._event_repo.list_by_group(gid, limit=1000)
            uids: set[str] = set()
            for event in events:
                for uid in (event.participants or []):
                    uids.add(uid)
            if uids:
                group_members[gid] = sorted(uids)

        return {"nodes": nodes, "edges": edges, "group_members": group_members}

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
        from core.api import get_stats
        data = await get_stats(
            persona_repo=self._persona_repo,
            event_repo=self._event_repo,
            impression_repo=self._impression_repo,
            data_dir=self._data_dir,
            plugin_version=self._plugin_version,
        )
        data["soul_enabled"] = bool(self._initial_config.get("soul_enabled", True))
        return data

    # Route handlers: Static pages

    async def _handle_index(self, _: web.Request) -> web.Response:
        return web.json_response({
            "message": "WebUI backend is running"
        })

    # Route handlers: Authentication

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
        if not self._auth_enabled:
            return _json({"ok": True, "sudo_remaining_seconds": 3600})

        body = await request.json()
        token = request.cookies.get(_SESSION_COOKIE)

        # Prefer using state from middleware if available
        state = request.get("auth")
        if not state:
            state = self._auth.check(token)

        if not token or not state.is_authenticated:
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

    # Route handlers: Data queries

    async def _handle_events(self, request: web.Request) -> web.Response:
        group_id = request.rel_url.query.get("group_id") or None
        limit = int(request.rel_url.query.get("limit", "100"))
        return _json(await self.events_data(group_id, limit))

    def _relation_disabled_response(self) -> web.Response | None:
        """Return a disabled-feature response when relation_enabled=False, else None."""
        if not self._relation_enabled:
            return _json({"enabled": False, "nodes": [], "edges": []})
        return None

    async def _handle_graph_guarded(self, request: web.Request) -> web.Response:
        guard = self._relation_disabled_response()
        if guard is not None:
            return guard
        return await self._handle_graph(request)

    async def _handle_update_impression_guarded(self, request: web.Request) -> web.Response:
        guard = self._relation_disabled_response()
        if guard is not None:
            return guard
        return await self._handle_update_impression(request)

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

    async def _handle_soul_states(self, _: web.Request) -> web.Response:
        if self._recall_manager is None:
            return _json({"states": {}})
        states = getattr(self._recall_manager, "get_soul_states", lambda: {})()
        return _json({"states": states})

    # Route handlers: Admin operations (sudo)

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

    async def _handle_regenerate_summary(self, request: web.Request) -> web.Response:
        if self._provider_getter is None:
            return _json({"error": "provider_getter not wired"}, status=503)
        body = await request.json()
        group_id = body.get("group_id") or None
        date = body.get("date", "")
        if not date:
            return _json({"error": "date required"}, status=400)
        try:
            from core.tasks.summary import regenerate_single_summary
            content = await regenerate_single_summary(
                event_repo=self._event_repo,
                data_dir=self._data_dir,
                provider_getter=self._provider_getter,
                group_id=group_id,
                date=date,
                persona_repo=self._persona_repo,
                impression_repo=self._impression_repo,
            )
        except Exception as exc:
            logger.warning("[WebUI] regenerate_summary failed: %s", exc)
            return _json({"error": str(exc)}, status=500)
        if content is None:
            return _json({"error": "no events or no provider"}, status=503)
        return _json({"content": content})

    async def _handle_demo(self, _: web.Request) -> web.Response:
        now = time.time()
        DAY = 86_400

        personas = [
            Persona(
                uid="demo_uid_alice",
                bound_identities=[("qq", "demo_10001")],
                primary_name="Alice",
                persona_attrs={"description": "热情开朗，喜爱音乐与户外运动",
                               "content_tags": ["音乐", "徒步", "摄影"],
                               "big_five": {"E": 0.7, "A": 0.6, "O": 0.4, "C": 0.1, "N": -0.2}},
                confidence=0.92,
                created_at=now - 45 * DAY,
                last_active_at=now - DAY,
            ),
            Persona(
                uid="demo_uid_bob",
                bound_identities=[("qq", "demo_10002")],
                primary_name="Bob",
                persona_attrs={"description": "资深开发者，逻辑严密但乐于助人",
                               "content_tags": ["Python", "架构", "AI"],
                               "big_five": {"C": 0.7, "O": 0.5, "A": 0.4, "E": -0.1}},
                confidence=0.85,
                created_at=now - 40 * DAY,
                last_active_at=now - 2 * DAY,
            ),
            Persona(
                uid="demo_uid_charlie",
                bound_identities=[("telegram", "demo_tg_charlie")],
                primary_name="Charlie",
                persona_attrs={"description": "数据分析师，喜欢分享科技资讯",
                               "content_tags": ["科技", "阅读", "旅行"],
                               "big_five": {"O": 0.6, "C": 0.5, "E": 0.3}},
                confidence=0.78,
                created_at=now - 20 * DAY,
                last_active_at=now - 5 * DAY,
            ),
            Persona(
                uid="demo_uid_diana",
                bound_identities=[("internal", "diana_web")],
                primary_name="Diana",
                persona_attrs={"description": "文学爱好者，对话风格温婉",
                               "content_tags": ["文学", "诗歌", "艺术"],
                               "big_five": {"O": 0.7, "A": 0.7, "E": -0.4, "C": 0.3}},
                confidence=0.72,
                created_at=now - 10 * DAY,
                last_active_at=now - 12 * 3600,
            ),
            Persona(
                uid="demo_uid_bot",
                bound_identities=[("internal", "bot")],
                primary_name="BOT",
                persona_attrs={"description": "搭载增强记忆引擎的智能助手",
                               "content_tags": ["记忆管理", "日程分析"]},
                confidence=1.0,
                created_at=now - 90 * DAY,
                last_active_at=now,
            ),
        ]

        events = [
            Event(
                event_id="demo_evt_001", group_id="demo_group_001",
                start_time=now - 10 * DAY, end_time=now - 10 * DAY + 1200,
                participants=["demo_uid_alice",
                              "demo_uid_bob", "demo_uid_bot"],
                interaction_flow=[
                    MessageRef("demo_uid_alice", now -
                               10 * DAY, "h1", "大家早安！"),
                    MessageRef("demo_uid_bob", now - 10 *
                               DAY + 60, "h2", "早，Alice。"),
                ],
                topic="早安问候",
                summary="Alice 发起早安问候，Bob 礼貌回应，群组开启了一天的活跃氛围。",
                chat_content_tags=["社交", "日常"],
                salience=0.3, confidence=0.95, inherit_from=[],
                last_accessed_at=now - 5 * DAY,
            ),
            Event(
                event_id="demo_evt_002", group_id="demo_group_001",
                start_time=now - 8 * DAY, end_time=now - 8 * DAY + 3600,
                participants=["demo_uid_alice",
                              "demo_uid_bob", "demo_uid_bot"],
                interaction_flow=[],
                topic="音乐推荐：古典乐之美",
                summary="Alice 分享了几首德彪西的曲目，Bob 探讨了古典乐对专注力的提升作用。",
                chat_content_tags=["艺术", "分享"],
                salience=0.65, confidence=0.88, inherit_from=["demo_evt_001"],
                last_accessed_at=now - 2 * DAY,
            ),
            Event(
                event_id="demo_evt_003", group_id="demo_group_001",
                start_time=now - 6 * DAY, end_time=now - 6 * DAY + 5400,
                participants=["demo_uid_bob",
                              "demo_uid_charlie", "demo_uid_bot"],
                interaction_flow=[],
                topic="异步 IO 性能调优",
                summary="Bob 与 Charlie 深入讨论了 Python asyncio 的事件循环机制及在高并发场景下的优化策略。",
                chat_content_tags=["技术", "知识"],
                salience=0.82, confidence=0.94, inherit_from=[],
                last_accessed_at=now - 12 * 3600,
            ),
            Event(
                event_id="demo_evt_004", group_id="demo_group_002",
                start_time=now - 4 * DAY, end_time=now - 4 * DAY + 2400,
                participants=["demo_uid_alice",
                              "demo_uid_diana", "demo_uid_bot"],
                interaction_flow=[],
                topic="周末徒步计划",
                summary="Alice 邀请 Diana 周末去西山徒步，Diana 建议携带专业摄影器材记录秋景。",
                chat_content_tags=["运动", "日常"],
                salience=0.58, confidence=0.85, inherit_from=[],
                last_accessed_at=now - DAY,
            ),
            Event(
                event_id="demo_evt_005", group_id=None,
                start_time=now - 2 * DAY, end_time=now - 2 * DAY + 900,
                participants=["demo_uid_bob", "demo_uid_bot"],
                interaction_flow=[],
                topic="私聊：核心架构咨询",
                summary="Bob 私下向 BOT 询问了增强记忆引擎的向量检索原理，表现出对底层实现的浓厚兴趣。",
                chat_content_tags=["技术", "咨询"],
                salience=0.75, confidence=0.89, inherit_from=["demo_evt_003"],
                last_accessed_at=now - 3600,
            ),
            Event(
                event_id="demo_evt_006", group_id="demo_group_001",
                start_time=now - DAY, end_time=now - DAY + 4200,
                participants=["demo_uid_alice", "demo_uid_bob",
                              "demo_uid_charlie", "demo_uid_bot"],
                interaction_flow=[],
                topic="AI 伦理与长期记忆",
                summary="群组讨论了机器人拥有长期记忆后可能带来的隐私风险及相关的伦理边界问题。",
                chat_content_tags=["AI", "知识"],
                salience=0.91, confidence=0.92, inherit_from=[],
                last_accessed_at=now,
                is_locked=True,
            ),
            Event(
                event_id="demo_evt_007", group_id="demo_group_002",
                start_time=now - 18 * 3600, end_time=now - 17 * 3600,
                participants=["demo_uid_diana", "demo_uid_bot"],
                interaction_flow=[],
                topic="现代诗歌鉴赏",
                summary="Diana 朗读了一首关于时间的诗，BOT 从语义角度给出了深刻的解读与回应。",
                chat_content_tags=["艺术", "文学"],
                salience=0.42, confidence=0.81, inherit_from=[],
                last_accessed_at=now - 6 * 3600,
            ),
            Event(
                event_id="demo_evt_008", group_id="demo_group_001",
                start_time=now - 6 * 3600, end_time=now - 5 * 3600,
                participants=["demo_uid_alice",
                              "demo_uid_bob", "demo_uid_bot"],
                interaction_flow=[],
                topic="项目周报同步",
                summary="Alice 汇总了本周的讨论热点，Bob 确认了技术分享的排期，群组达成阶段性一致。",
                chat_content_tags=["工作", "同步"],
                salience=0.67, confidence=0.88, inherit_from=["demo_evt_006"],
                last_accessed_at=now,
            ),
        ]

        impressions = [
            Impression(
                observer_uid="demo_uid_bot", subject_uid="demo_uid_alice",
                ipc_orientation="友好", benevolence=0.85, power=0.1,
                affect_intensity=0.6, r_squared=0.88, confidence=0.92,
                scope="global",
                evidence_event_ids=[
                    "demo_evt_001", "demo_evt_002", "demo_evt_004", "demo_evt_006"],
                last_reinforced_at=now - 12 * 3600,
            ),
            Impression(
                observer_uid="demo_uid_bot", subject_uid="demo_uid_bob",
                ipc_orientation="支配友好", benevolence=0.3, power=0.45,
                affect_intensity=0.38, r_squared=0.75, confidence=0.89,
                scope="global",
                evidence_event_ids=["demo_evt_001", "demo_evt_003",
                                    "demo_evt_005", "demo_evt_006", "demo_evt_008"],
                last_reinforced_at=now - 3600,
            ),
            Impression(
                observer_uid="demo_uid_bot", subject_uid="demo_uid_charlie",
                ipc_orientation="友好", benevolence=0.4, power=-0.1,
                affect_intensity=0.25, r_squared=0.65, confidence=0.81,
                scope="demo_group_001",
                evidence_event_ids=["demo_evt_003", "demo_evt_006"],
                last_reinforced_at=now - DAY,
            ),
            Impression(
                observer_uid="demo_uid_bot", subject_uid="demo_uid_diana",
                ipc_orientation="友好", benevolence=0.65, power=-0.2,
                affect_intensity=0.42, r_squared=0.81, confidence=0.85,
                scope="demo_group_002",
                evidence_event_ids=["demo_evt_004", "demo_evt_007"],
                last_reinforced_at=now - 6 * 3600,
            ),
            Impression(
                observer_uid="demo_uid_alice", subject_uid="demo_uid_bot",
                ipc_orientation="友好", benevolence=0.9, power=0.0,
                affect_intensity=0.65, r_squared=0.92, confidence=0.85,
                scope="global",
                evidence_event_ids=["demo_evt_001", "demo_evt_002"],
                last_reinforced_at=now - DAY,
            ),
            Impression(
                observer_uid="demo_uid_bob", subject_uid="demo_uid_alice",
                ipc_orientation="友好", benevolence=0.55, power=0.1,
                affect_intensity=0.4, r_squared=0.78, confidence=0.75,
                scope="demo_group_001",
                evidence_event_ids=["demo_evt_002"],
                last_reinforced_at=now - 8 * DAY,
            ),
            Impression(
                observer_uid="demo_uid_diana", subject_uid="demo_uid_alice",
                ipc_orientation="友好", benevolence=0.75, power=0.0,
                affect_intensity=0.5, r_squared=0.85, confidence=0.82,
                scope="demo_group_002",
                evidence_event_ids=["demo_evt_004"],
                last_reinforced_at=now - 4 * DAY,
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

        return _json({"ok": True, "seeded": {"personas": len(personas), "events": len(events), "impressions": len(impressions)}})

    async def _handle_recall(self, request: web.Request) -> web.Response:
        q = request.rel_url.query.get("q", "").strip()
        limit = min(int(request.rel_url.query.get("limit", "5")), 50)
        session_id = request.rel_url.query.get("session_id", "").strip() or None

        if not q:
            return _json({"error": "q required"}, status=400)
        try:
            if self._recall_manager:
                # Use hybrid recall if available (RRF of FTS5 + Vector)
                results = await self._recall_manager.recall(q, group_id=session_id)
                # Apply limit if RecallManager doesn't handle it exactly as WebUI expects
                results = results[:limit]
                algorithm = "hybrid (rrf)"
            else:
                # Fallback to BM25-only if recall manager not provided
                results = await self._event_repo.search_fts(q, limit=limit)
                algorithm = "fts5"
        except Exception as exc:
            logger.exception("Recall failed")
            return _json({"error": str(exc)}, status=500)

        return _json({
            "items": [event_to_dict(e) for e in results],
            "algorithm": algorithm,
            "query": q,
            "count": len(results),
        })

    # Route handlers: Event CRUD

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
                summary=body.get("summary", ""),
                chat_content_tags=body.get("chat_content_tags", []),
                salience=float(body.get("salience", 0.5)),
                confidence=float(body.get("confidence", 0.8)),
                inherit_from=body.get("inherit_from", []),
                last_accessed_at=now,
                is_locked=bool(body.get("is_locked", False)),
                status=body.get("status", "active"),
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
                summary=body.get("summary", existing.summary),
                chat_content_tags=body.get(
                    "chat_content_tags", existing.chat_content_tags),
                salience=float(body.get("salience", existing.salience)),
                confidence=float(body.get("confidence", existing.confidence)),
                inherit_from=body.get("inherit_from", existing.inherit_from),
                last_accessed_at=now,
                is_locked=bool(body.get("is_locked", existing.is_locked)),
                status=body.get("status", existing.status),
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

    # Route handlers: Recycle bin

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
            event_args = {
                "event_id": item["id"],
                "group_id": item.get("group"),
                "start_time": item.get("start_ts", now),
                "end_time": item.get("end_ts", now),
                "participants": item.get("participants", []),
                "interaction_flow": [],
                "topic": item.get("topic", item.get("content", "")),
                "summary": item.get("summary", ""),
                "chat_content_tags": item.get("tags", []),
                "salience": item.get("salience", 0.5),
                "confidence": item.get("confidence", 0.8),
                "inherit_from": item.get("inherit_from", []),
                "last_accessed_at": now,
                "status": item.get("status", "active"),
                "is_locked": item.get("is_locked", False),
            }
            event = Event(**event_args)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return _json({"error": str(exc)}, status=400)

        try:
            await self._event_repo.upsert(event)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return _json({"error": f"Database error: {str(exc)}"}, status=500)

        self._recycle_bin = [
            x for x in self._recycle_bin if x["id"] != event_id]
        return _json({"ok": True, "event": event_to_dict(event)})

    async def _handle_recycle_bin_clear(self, _: web.Request) -> web.Response:
        count = len(self._recycle_bin)
        self._recycle_bin.clear()
        return _json({"ok": True, "cleared": count})

    # Route handlers: Persona CRUD

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
            "content_tags": body.get("content_tags", existing_attrs.get("content_tags", [])),
        }
        if "big_five" in existing_attrs:
            updated_attrs["big_five"] = existing_attrs["big_five"]
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

    # Route handlers: Impression updates

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
                ipc_orientation=body.get("relation_type",
                                         existing.ipc_orientation if existing else "友好"),
                benevolence=float(body.get("affect",
                                           existing.benevolence if existing else 0.0)),
                power=float(body.get("power",
                                     existing.power if existing else 0.0)),
                affect_intensity=float(body.get("intensity",
                                                existing.affect_intensity if existing else 0.5)),
                r_squared=float(body.get("r_squared",
                                         existing.r_squared if existing else 0.7)),
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

    # Route handlers: Tags aggregation

    async def _handle_tags(self, _: web.Request) -> web.Response:
        """Return all unique chat_content_tags across all events with usage counts."""
        counts: dict[str, int] = {}
        for gid in await self._event_repo.list_group_ids():
            for ev in await self._event_repo.list_by_group(gid, limit=10_000):
                for tag in (ev.chat_content_tags or []):
                    counts[tag] = counts.get(tag, 0) + 1
        tags = [{"name": k, "count": v}
                for k, v in sorted(counts.items(), key=lambda x: -x[1])]
        return _json({"tags": tags})

    # Route handlers: Plugin config

    def _load_conf_schema(self) -> dict:
        try:
            return json.loads(self._CONF_SCHEMA_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _read_config(self) -> dict:
        """Return merged config: schema defaults ← initial_config ← saved file."""
        schema = self._load_conf_schema()
        merged: dict = {k: v.get("default") for k, v in schema.items()}
        merged.update(self._initial_config)
        if self._config_path.exists():
            try:
                saved = json.loads(
                    self._config_path.read_text(encoding="utf-8"))
                merged.update(saved)
            except Exception:
                pass
        return merged

    async def _handle_get_config(self, _: web.Request) -> web.Response:
        schema = self._load_conf_schema()
        values = self._read_config()
        return _json({"schema": schema, "values": values})

    async def _handle_get_config_schema(self, _: web.Request) -> web.Response:
        return _json(self._load_conf_schema())

    async def _handle_update_config(self, request: web.Request) -> web.Response:
        body = await request.json()
        schema = self._load_conf_schema()
        # Validate keys against schema; coerce types
        coerced: dict = {}
        for key, val in body.items():
            if key not in schema:
                continue
            field_type = schema[key].get("type", "string")
            try:
                if field_type == "bool":
                    coerced[key] = bool(val)
                elif field_type == "int":
                    coerced[key] = int(val)
                elif field_type == "float":
                    coerced[key] = float(val)
                else:
                    coerced[key] = val
            except (TypeError, ValueError):
                coerced[key] = val
        # Merge with existing saved config
        existing: dict = {}
        if self._config_path.exists():
            try:
                existing = json.loads(
                    self._config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        existing.update(coerced)
        self._config_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return _json({"ok": True, "saved": list(coerced.keys())})


    async def _handle_get_providers(self, _: web.Request) -> web.Response:
        if self._all_providers_getter is None:
            return _json({"providers": []})
        try:
            # get_all_providers() might return a list or (success, list)
            data = self._all_providers_getter()
            providers = data
            if isinstance(data, (tuple, list)) and len(data) == 2 and isinstance(data[0], bool):
                providers = data[1]
            
            # We want to return a list of {id: str, name: str}
            res = []
            if isinstance(providers, (list, tuple)):
                for p in providers:
                    # Provider objects usually have id and name
                    p_id = getattr(p, "id", "")
                    p_name = getattr(p, "name", "")
                    if not p_id and hasattr(p, "__dict__"):
                         p_id = p.__dict__.get("id", str(p))
                    if not p_name and hasattr(p, "__dict__"):
                         p_name = p.__dict__.get("name", str(p))
                    
                    res.append({"id": str(p_id or p), "name": str(p_name or p)})
            return _json({"providers": res})
        except Exception as exc:
            logger.warning("[WebUI] get_providers failed: %s", exc)
            return _json({"error": str(exc)}, status=500)

    # Route handlers: Third-party panel registration

    async def _handle_panels_list(self, _: web.Request) -> web.Response:
        return _json({"panels": self.registry.list()})


"""Local WebUI debugging startup script.

- Uses in-memory repository, no database files required
- Authentication disabled (no password required)
- Auto-injects demo data (personas, events, impressions, summaries)
- Data directory is .dev_data/ under project root
- Default port 2654, does not conflict with production port 2653

Usage:
    python run_webui_dev.py
    python run_webui_dev.py --port 9000
"""

# Ensure project root is in sys.path
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_PORT = 2655
_DATA_DIR = _ROOT / ".dev_data"


def _parse_port() -> int:
    args = sys.argv[1:]
    if "--port" in args:
        idx = args.index("--port")
        try:
            return int(args[idx + 1])
        except (IndexError, ValueError):
            pass
    return _PORT


async def _seed(
    persona_repo: InMemoryPersonaRepository,
    event_repo: InMemoryEventRepository,
    impression_repo: InMemoryImpressionRepository,
    data_dir: Path,
) -> None:
    now = time.time()
    DAY = 86_400

    for p in [
        Persona(
            uid="demo_uid_alice",
            bound_identities=[("qq", "demo_10001")],
            primary_name="Alice",
            persona_attrs={"description": "热情开朗，喜爱音乐与游戏",
                           "content_tags": ["音乐", "游戏", "聊天"],
                           "big_five": {"E": 0.7, "A": 0.6, "O": 0.3}},
            confidence=0.88,
            created_at=now - 30 * DAY,
            last_active_at=now - DAY,
        ),
        Persona(
            uid="demo_uid_bob",
            bound_identities=[("qq", "demo_10002")],
            primary_name="Bob",
            persona_attrs={"description": "理性谨慎，热衷技术讨论",
                           "content_tags": ["技术", "编程"],
                           "big_five": {"C": 0.7, "O": 0.5, "N": 0.1}},
            confidence=0.82,
            created_at=now - 25 * DAY,
            last_active_at=now - 2 * DAY,
        ),
        Persona(
            uid="demo_uid_charlie",
            bound_identities=[("telegram", "demo_tg_charlie")],
            primary_name="Charlie",
            persona_attrs={"description": "神秘低调，偶尔参与讨论",
                           "content_tags": ["旅行", "摄影"],
                           "big_five": {"E": -0.5, "O": 0.4, "N": 0.3}},
            confidence=0.65,
            created_at=now - 15 * DAY,
            last_active_at=now - 5 * DAY,
        ),
        Persona(
            uid="demo_uid_bot",
            bound_identities=[("internal", "bot")],
            primary_name="BOT",
            persona_attrs={"description": "AI 助手",
                           "content_tags": []},
            confidence=1.0,
            created_at=now - 60 * DAY,
            last_active_at=now,
        ),
    ]:
        await persona_repo.upsert(p)

    for e in [
        Event(
            event_id="demo_evt_001", group_id="demo_group_001",
            start_time=now - 7 * DAY, end_time=now - 7 * DAY + 1800,
            participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_bot"],
            interaction_flow=[], topic="早安问候",
            summary="Alice 和 Bob 在群组中互相进行早安问候，AI 助手也参与了互动。",
            chat_content_tags=["日常", "问候"],
            salience=0.45, confidence=0.82, inherit_from=[],
            last_accessed_at=now - DAY,
        ),
        Event(
            event_id="demo_evt_002", group_id="demo_group_001",
            start_time=now - 6 * DAY, end_time=now - 6 * DAY + 3600,
            participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_bot"],
            interaction_flow=[], topic="音乐推荐",
            summary="Alice 向大家推荐了几首好听的音乐，引发了关于音乐文化的讨论。",
            chat_content_tags=["音乐", "推荐", "文化"],
            salience=0.72, confidence=0.88, inherit_from=["demo_evt_001"],
            last_accessed_at=now - 12 * 3600,
        ),
        Event(
            event_id="demo_evt_003", group_id="demo_group_001",
            start_time=now - 5 * DAY, end_time=now - 5 * DAY + 2700,
            participants=["demo_uid_alice",
                          "demo_uid_charlie", "demo_uid_bot"],
            interaction_flow=[], topic="游戏约定",
            summary="Alice 和 Charlie 约定在周末一起进行在线游戏，讨论了具体的时间和游戏类型。",
            chat_content_tags=["游戏", "约定", "娱乐"],
            salience=0.68, confidence=0.79, inherit_from=["demo_evt_002"],
            last_accessed_at=now - 8 * 3600,
        ),
        Event(
            event_id="demo_evt_004", group_id="demo_group_001",
            start_time=now - 3 * DAY, end_time=now - 3 * DAY + 4200,
            participants=["demo_uid_bob", "demo_uid_charlie", "demo_uid_bot"],
            interaction_flow=[], topic="技术交流",
            summary="Bob 和 Charlie 深入探讨了一些编程技术难题，AI 助手提供了相关的技术参考。",
            chat_content_tags=["技术", "编程", "讨论"],
            salience=0.85, confidence=0.91, inherit_from=["demo_evt_001"],
            last_accessed_at=now - 4 * 3600,
        ),
        Event(
            event_id="demo_evt_005", group_id=None,
            start_time=now - DAY, end_time=now - DAY + 900,
            participants=["demo_uid_alice", "demo_uid_bot"],
            interaction_flow=[], topic="私聊请教",
            summary="Alice 在私聊中向 AI 助手请教了一些生活中的小问题，得到了满意的答复。",
            chat_content_tags=["私聊", "帮助"],
            salience=0.55, confidence=0.77, inherit_from=[],
            last_accessed_at=now - 3600,
        ),
    ]:
        await event_repo.upsert(e)

    for imp in [
        Impression(
            observer_uid="demo_uid_bot", subject_uid="demo_uid_alice",
            ipc_orientation="友好", benevolence=0.7, power=0.0,
            affect_intensity=0.5, r_squared=0.8, confidence=0.85,
            scope="global",
            evidence_event_ids=["demo_evt_001",
                                "demo_evt_002", "demo_evt_005"],
            last_reinforced_at=now - DAY,
        ),
        Impression(
            observer_uid="demo_uid_bot", subject_uid="demo_uid_bob",
            ipc_orientation="支配友好", benevolence=0.2, power=0.3,
            affect_intensity=0.25, r_squared=0.7, confidence=0.78,
            scope="global",
            evidence_event_ids=["demo_evt_001", "demo_evt_004"],
            last_reinforced_at=now - 2 * DAY,
        ),
        Impression(
            observer_uid="demo_uid_alice", subject_uid="demo_uid_bot",
            ipc_orientation="友好", benevolence=0.8, power=0.0,
            affect_intensity=0.6, r_squared=0.9, confidence=0.80,
            scope="global",
            evidence_event_ids=["demo_evt_001", "demo_evt_002"],
            last_reinforced_at=now - DAY,
        ),
        Impression(
            observer_uid="demo_uid_bob", subject_uid="demo_uid_alice",
            ipc_orientation="友好", benevolence=0.5, power=0.0,
            affect_intensity=0.35, r_squared=0.75, confidence=0.72,
            scope="demo_group_001",
            evidence_event_ids=["demo_evt_002"],
            last_reinforced_at=now - 6 * DAY,
        ),
        Impression(
            observer_uid="demo_uid_charlie", subject_uid="demo_uid_bob",
            ipc_orientation="友好", benevolence=0.0, power=0.0,
            affect_intensity=0.1, r_squared=0.5, confidence=0.60,
            scope="demo_group_001",
            evidence_event_ids=["demo_evt_004"],
            last_reinforced_at=now - 3 * DAY,
        ),
    ]:
        await impression_repo.upsert(imp)

    for date, content in [
        ("2026-05-01", _DEMO_SUMMARY_1),
        ("2026-05-02", _DEMO_SUMMARY_2),
    ]:
        path = data_dir / "groups" / "demo_group_001" / \
            "summaries" / f"{date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


async def main() -> None:
    port = _parse_port()
    data_dir = _DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    persona_repo = InMemoryPersonaRepository()
    event_repo = InMemoryEventRepository()
    impression_repo = InMemoryImpressionRepository()

    await _seed(persona_repo, event_repo, impression_repo, data_dir)

    srv = WebuiServer(
        persona_repo=persona_repo,
        event_repo=event_repo,
        impression_repo=impression_repo,
        data_dir=data_dir,
        port=port,
        auth_enabled=False,      # No password required for local debugging
        plugin_version="dev",
    )
    await srv.start()

    print(f"\n  Enhanced Memory — Debugging interface started")
    print(f"  http://localhost:{port}")
    print(f"  Data directory: {data_dir}")
    print(f"  Authentication: Disabled (local debugging mode)")
    print(f"  Demo data: Injected (4 personas / 5 events / 5 impressions / 2 summaries)")
    print(f"\n  Press Ctrl+C to stop\n")

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()   # Wait indefinitely until Ctrl+C
    except asyncio.CancelledError:
        pass
    finally:
        await srv.stop()
        print("Stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
