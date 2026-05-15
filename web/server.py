from __future__ import annotations
import secrets
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
from .auth import AuthManager, AuthState, PermLevel
from .registry import PanelRegistry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from core.repository.base import EventRepository, ImpressionRepository, PersonaRepository
    from core.managers.base import BaseRecallManager

    TaskRunner = Callable[[str], Awaitable[bool]]

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent.parent / "pages" / "moirai" / "_app"
_DEFAULT_PORT = 2655
_SESSION_COOKIE = "em_session"

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

_DEMO_SUMMARY_1 = """# 群组 demo_group_001 活动摘要 — 2026-05-01 08:00 - 12:00
[主要话题] Alice 和 Bob 进行了早安问候..."""
_DEMO_SUMMARY_2 = """# 群组 demo_group_001 活动摘要 — 2026-05-02 14:00 - 18:00
[主要话题] Alice 与 Charlie 确定了周末游戏约定..."""

try:
    from astrbot.api import logger as astrbot_logger
except:
    astrbot_logger = logging.getLogger("moirai")

_PASSWORD_MASK = "(已设置加密密码)"

class WebuiServer:
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
        star: Any = None,
    ) -> None:
        self._persona_repo = persona_repo
        self._event_repo = event_repo
        self._impression_repo = impression_repo
        self._recall_manager = recall_manager
        self._data_dir = data_dir
        self._port = port
        self._auth_enabled = auth_enabled
        self._star = star

        self._initial_config = initial_config or {}
        # 1. 检查是否有持久化哈希文件
        has_persistent_pw = (data_dir / ".webui_password").exists()
        
        # 2. 检查配置面板
        cfg_password = self._initial_config.get("webui_password")
        if cfg_password is None and "webui" in self._initial_config:
            cfg_password = self._initial_config["webui"].get("webui_password")
        cfg_password = str(cfg_password or "").strip()

        self.token_generated = False
        secret_token = None
        
        # 3. 核心初始化认证状态
        def on_pw_changed(_: str):
            # 当密码通过 WebUI (AuthManager) 设置时，同步【掩码】回配置
            self._sync_password_to_config(_PASSWORD_MASK)
            self.token_generated = False

        self._auth = AuthManager(
            data_dir,
            secret_token=None,
            is_token_configured=False,
            on_password_changed=on_pw_changed
        )

        # 逻辑：
        # A. 如果配置里是明文（非空且不是掩码），迁移它
        if cfg_password and cfg_password != _PASSWORD_MASK:
            try:
                self._auth.setup_password(cfg_password)
                self._sync_password_to_config(_PASSWORD_MASK)
                astrbot_logger.info(f"[Moirai] 检测到明文配置密码，已哈希化并掩码。")
            except Exception as e:
                astrbot_logger.warning(f"[Moirai] 迁移明文密码失败: {e}")
        
        # B. 决定是否生成临时 Token
        if not (data_dir / ".webui_password").exists() and auth_enabled:
            # 只有在完全没有持久化密码的情况下才生成 Token
            self._secret_token = secrets.token_urlsafe(16)
            self._auth.update_secret_token(self._secret_token, False)
            self.token_generated = True
        else:
            self._secret_token = None
        self.registry = registry or PanelRegistry()
        self._task_runner = task_runner
        self._provider_getter = provider_getter
        self._all_providers_getter = all_providers_getter
        self._plugin_version = plugin_version
        self._config_path = data_dir / "plugin_config.json"
        self._relation_enabled = bool(self._initial_config.get("relation_enabled", True))
        self._recycle_bin: list[dict] = []
        self._app = self._build_app()
        self._runner: web.AppRunner | None = None

    def _build_app(self) -> web.Application:
        app = web.Application()
        
        # API Routes
        app.router.add_get("/api/auth/status", self._wrap("public", self._handle_auth_status))
        app.router.add_post("/api/auth/setup", self._wrap("public", self._handle_auth_setup))
        app.router.add_post("/api/auth/login", self._wrap("public", self._handle_auth_login))
        app.router.add_post("/api/auth/logout", self._wrap("auth", self._handle_auth_logout))
        app.router.add_post("/api/auth/sudo", self._wrap("auth", self._handle_auth_sudo))
        app.router.add_post("/api/auth/sudo/exit", self._wrap("auth", self._handle_auth_sudo_exit))
        app.router.add_post("/api/auth/password", self._wrap("sudo", self._handle_change_password))
        app.router.add_get("/api/events", self._wrap("auth", self._handle_events))
        app.router.add_get("/api/graph", self._wrap("auth", self._handle_graph_guarded))
        app.router.add_get("/api/summaries", self._wrap("auth", self._handle_summaries))
        app.router.add_get("/api/summary", self._wrap("auth", self._handle_summary))
        app.router.add_get("/api/stats", self._wrap("auth", self._handle_stats))
        app.router.add_get("/api/soul/states", self._wrap("auth", self._handle_soul_states))
        app.router.add_post("/api/admin/run_task", self._wrap("sudo", self._handle_run_task))
        app.router.add_put("/api/summary", self._wrap("sudo", self._handle_update_summary))
        app.router.add_post("/api/summary/regenerate", self._wrap("sudo", self._handle_regenerate_summary))
        app.router.add_post("/api/admin/demo", self._wrap("sudo", self._handle_demo))
        app.router.add_get("/api/recall", self._wrap("auth", self._handle_recall))
        app.router.add_post("/api/events", self._wrap("sudo", self._handle_create_event))
        app.router.add_put("/api/events/{event_id}", self._wrap("sudo", self._handle_update_event))
        app.router.add_delete("/api/events/{event_id}", self._wrap("sudo", self._handle_delete_event))
        app.router.add_delete("/api/events", self._wrap("sudo", self._handle_clear_events))
        app.router.add_get("/api/recycle_bin", self._wrap("auth", self._handle_recycle_bin_list))
        app.router.add_post("/api/recycle_bin/restore", self._wrap("sudo", self._handle_recycle_bin_restore))
        app.router.add_delete("/api/recycle_bin", self._wrap("sudo", self._handle_recycle_bin_clear))
        app.router.add_get("/api/archived_events", self._wrap("auth", self._handle_archived_events_list))
        app.router.add_post("/api/events/{event_id}/archive", self._wrap("sudo", self._handle_archive_event))
        app.router.add_post("/api/events/{event_id}/unarchive", self._wrap("sudo", self._handle_unarchive_event))
        app.router.add_post("/api/personas", self._wrap("sudo", self._handle_create_persona))
        app.router.add_put("/api/personas/{uid}", self._wrap("sudo", self._handle_update_persona))
        app.router.add_delete("/api/personas/{uid}", self._wrap("sudo", self._handle_delete_persona))
        app.router.add_put("/api/impressions/{observer}/{subject}/{scope}", self._wrap("sudo", self._handle_update_impression_guarded))
        app.router.add_get("/api/tags", self._wrap("auth", self._handle_tags))
        app.router.add_get("/api/config", self._wrap("auth", self._handle_get_config))
        app.router.add_put("/api/config", self._wrap("sudo", self._handle_update_config))
        app.router.add_get("/api/config/schema", self._wrap("auth", self._handle_get_config_schema))
        app.router.add_get("/api/config/providers", self._wrap("auth", self._handle_get_providers))
        app.router.add_get("/api/panels", self._wrap("auth", self._handle_panels_list))

        for route in self.registry.all_routes():
            app.router.add_route(route.method, route.path, self._wrap(route.permission, route.handler))

        # Static assets — must be registered before the SPA catch-all so aiohttp
        # serves them directly instead of falling through to the wildcard handler,
        # which has known issues with paths containing dots (e.g. chunk.abc123.js).
        _next_dir = _STATIC_DIR / "_next"
        if _next_dir.exists():
            app.router.add_static("/_next", _next_dir)

        # SPA Catch-all
        app.router.add_get("/", self._handle_spa_fallback)
        app.router.add_get("/{tail:.*}", self._handle_spa_fallback)
        return app

    async def _handle_spa_fallback(self, request: web.Request) -> web.Response:
        tail = request.match_info.get("tail", "").strip("/")
        filename = tail if tail else "index.html"
        target_file = _STATIC_DIR / filename

        # 1. 直接文件（JS/CSS/fonts/favicon 等）
        if target_file.is_file():
            return web.FileResponse(target_file)

        # 2. 目录 → index.html（Next.js trailingSlash: true 生成的结构）
        if (target_file / "index.html").is_file():
            return web.FileResponse(target_file / "index.html")

        # 3. 扩展名省略：/events → events.html（兼容 trailingSlash 关闭时）
        if (_STATIC_DIR / f"{filename}.html").is_file():
            return web.FileResponse(_STATIC_DIR / f"{filename}.html")

        # 4. SPA fallback：所有未匹配路径返回 index.html（前端路由接管）
        index_file = _STATIC_DIR / "index.html"
        if index_file.is_file():
            return web.FileResponse(index_file)

        return web.Response(status=404, text=f"Frontend missing: {filename}")

    @property
    def app(self) -> web.Application: return self._app
    @property
    def auth(self) -> AuthManager: return self._auth

    async def start(self) -> None:
        if self._runner: return
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("[WebUI] listening on http://localhost:%d (Independent Server, NOT AstrBot Panel)", self._port)

    async def stop(self) -> None:
        if not self._runner: return
        await self._runner.cleanup()
        self._runner = None

    def _wrap(self, level: PermLevel, handler: Callable) -> Callable:
        async def wrapped(request: web.Request) -> web.StreamResponse:
            try:
                if not self._auth_enabled or level == "public":
                    return await handler(request)
                token = request.cookies.get(_SESSION_COOKIE)
                state = self._auth.check(token)
                if not state.is_authenticated: return _json({"error": "unauthorized"}, status=401)
                if level == "sudo" and not state.is_sudo: return _json({"error": "sudo required"}, status=403)
                request["auth"] = state
                return await handler(request)
            except Exception as exc:
                logger.exception("[WebUI] Error in %s %s", request.method, request.path)
                return _json({"error": str(exc)}, status=500)
        return wrapped

    async def events_data(self, group_id: str | None, limit: int) -> dict[str, Any]:
        if group_id:
            events = await self._event_repo.list_by_group(group_id, limit=limit)
        else:
            group_ids = await self._event_repo.list_group_ids()
            if not group_ids: return {"items": []}
            per_group = max(1, limit // len(group_ids))
            events = []
            for gid in group_ids:
                events.extend(await self._event_repo.list_by_group(gid, limit=per_group))
            events = events[:limit]
        events = [e for e in events if e.status == "active"]
        return {"items": [event_to_dict(e) for e in events], "total": len(events)}

    async def graph_data(self) -> dict[str, Any]:
        personas = await self._persona_repo.list_all()
        uid_msg_counts = await self._event_repo.count_messages_by_uid_bulk()
        nodes = []
        for p in personas:
            node = persona_to_node(p)
            node["data"]["msg_count"] = uid_msg_counts.get(p.uid, 0)
            nodes.append(node)
        edges = []
        for persona in personas:
            imps = await self._impression_repo.list_by_observer(persona.uid)
            for imp in imps:
                edge = impression_to_edge(imp)
                edge["data"]["msg_count"] = await self._event_repo.count_edge_messages(imp.observer_uid, imp.subject_uid, imp.scope)
                edges.append(edge)
        group_members = {}
        for gid in await self._event_repo.list_group_ids():
            events = await self._event_repo.list_by_group(gid, limit=1000)
            uids = {uid for event in events for uid in (event.participants or [])}
            if uids: group_members[gid] = sorted(uids)
        return {"nodes": nodes, "edges": edges, "group_members": group_members}

    async def summaries_data(self) -> list[dict[str, str | None]]:
        result = []
        groups_dir = self._data_dir / "groups"
        if groups_dir.exists():
            for gid_dir in sorted(groups_dir.iterdir()):
                if not gid_dir.is_dir(): continue
                sub = gid_dir / "summaries"
                for f in sorted(sub.glob("*.md"), reverse=True) if sub.exists() else []:
                    result.append({"group_id": gid_dir.name, "date": f.stem, "label": gid_dir.name})
        global_dir = self._data_dir / "global" / "summaries"
        if global_dir.exists():
            for f in sorted(global_dir.glob("*.md"), reverse=True):
                result.append({"group_id": None, "date": f.stem, "label": "私聊"})
        return result

    def summary_content(self, group_id: str | None, date: str) -> str | None:
        if not date: return None
        path = self._data_dir / "groups" / group_id / "summaries" / f"{date}.md" if group_id else self._data_dir / "global" / "summaries" / f"{date}.md"
        return path.read_text(encoding="utf-8") if path.exists() else None

    async def stats_data(self) -> dict[str, Any]:
        from core.api import get_stats
        data = await get_stats(self._persona_repo, self._event_repo, self._impression_repo, self._data_dir, self._plugin_version)
        data["soul_enabled"] = bool(self._initial_config.get("soul_enabled", True))
        return data

    async def _handle_auth_status(self, request: web.Request) -> web.Response:
        token = request.cookies.get(_SESSION_COOKIE)
        state = self._auth.check(token) if self._auth_enabled else AuthState(True, True)
        return _json({
            "auth_enabled": self._auth_enabled,
            "password_set": self._auth.is_password_set(),
            "authenticated": state.is_authenticated,
            "sudo": state.is_sudo,
            "sudo_remaining_seconds": state.sudo_remaining_seconds,
            "version": self._plugin_version,
        })

    async def _handle_auth_setup(self, request: web.Request) -> web.Response:
        if self._auth.is_password_set(): return _json({"error": "password already set"}, status=409)
        body = await request.json()
        try: self._auth.setup_password(body.get("password", ""))
        except ValueError as e: return _json({"error": str(e)}, status=400)
        token = self._auth.login(body.get("password", ""))
        resp = _json({"ok": True})
        if token: resp.set_cookie(_SESSION_COOKIE, token, httponly=True, samesite="Lax", path="/")
        return resp

    async def _handle_auth_login(self, request: web.Request) -> web.Response:
        body = await request.json()
        token = self._auth.login(body.get("password", ""))
        if token is None: return _json({"error": "invalid password"}, status=401)
        resp = _json({"ok": True})
        resp.set_cookie(_SESSION_COOKIE, token, httponly=True, samesite="Lax", path="/")
        return resp

    async def _handle_auth_logout(self, request: web.Request) -> web.Response:
        self._auth.logout(request.cookies.get(_SESSION_COOKIE))
        resp = _json({"ok": True})
        resp.del_cookie(_SESSION_COOKIE, path="/")
        return resp

    async def _handle_auth_sudo(self, request: web.Request) -> web.Response:
        if not self._auth_enabled: return _json({"ok": True, "sudo_remaining_seconds": 3600})
        body = await request.json()
        token = request.cookies.get(_SESSION_COOKIE)
        state = request.get("auth") or self._auth.check(token)
        if not token or not state.is_authenticated: return _json({"error": "unauthorized"}, status=401)
        if not self._auth.verify_sudo(token, body.get("password", "")): return _json({"error": "invalid password"}, status=401)
        state = self._auth.check(token)
        return _json({"ok": True, "sudo_remaining_seconds": state.sudo_remaining_seconds})

    async def _handle_auth_sudo_exit(self, request: web.Request) -> web.Response:
        self._auth.exit_sudo(request.cookies.get(_SESSION_COOKIE))
        return _json({"ok": True})

    async def _handle_change_password(self, request: web.Request) -> web.Response:
        body = await request.json()
        if not self._auth.change_password(body.get("old_password", ""), body.get("new_password", "")):
            return _json({"error": "old password incorrect or weak new password"}, status=400)
        return _json({"ok": True})

    async def _handle_events(self, request: web.Request) -> web.Response:
        return _json(await self.events_data(request.rel_url.query.get("group_id"), int(request.rel_url.query.get("limit", "100"))))

    async def _handle_graph_guarded(self, request: web.Request) -> web.Response:
        if not self._relation_enabled: return _json({"enabled": False, "nodes": [], "edges": []})
        return _json(await self.graph_data())

    async def _handle_summaries(self, _: web.Request) -> web.Response: return _json(await self.summaries_data())

    async def _handle_summary(self, request: web.Request) -> web.Response:
        group_id = request.rel_url.query.get("group_id")
        date = request.rel_url.query.get("date", "")
        if not date: return _json({"error": "date required"}, status=400)
        content = self.summary_content(group_id, date)
        if content is None: return _json({"error": "not found"}, status=404)
        return _json({"content": content})

    async def _handle_stats(self, _: web.Request) -> web.Response: return _json(await self.stats_data())

    async def _handle_soul_states(self, _: web.Request) -> web.Response:
        states = getattr(self._recall_manager, "get_soul_states", lambda: {})() if self._recall_manager else {}
        return _json({"states": states})

    async def _handle_run_task(self, request: web.Request) -> web.Response:
        if not self._task_runner: return _json({"error": "no runner"}, status=503)
        body = await request.json()
        try: ok = await self._task_runner(body.get("name", ""))
        except Exception as e: return _json({"error": str(e)}, status=500)
        return _json({"ok": ok})

    async def _handle_update_summary(self, request: web.Request) -> web.Response:
        body = await request.json()
        date, content = body.get("date", ""), body.get("content", "")
        if not date: return _json({"error": "no date"}, status=400)
        path = self._data_dir / "groups" / body.get("group_id") / "summaries" / f"{date}.md" if body.get("group_id") else self._data_dir / "global" / "summaries" / f"{date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return _json({"ok": True})

    async def _handle_regenerate_summary(self, request: web.Request) -> web.Response:
        if not self._provider_getter: return _json({"error": "no provider"}, status=503)
        body = await request.json()
        date = body.get("date", "")
        try:
            from core.tasks.summary import regenerate_single_summary
            content = await regenerate_single_summary(self._event_repo, self._data_dir, self._provider_getter, body.get("group_id"), date, self._persona_repo, self._impression_repo)
        except Exception as e: return _json({"error": str(e)}, status=500)
        if content is None: return _json({"error": "failed"}, status=503)
        return _json({"content": content})

    async def _handle_demo(self, _: web.Request) -> web.Response:
        # Seeding logic kept as is in original for simplicity, can be expanded if needed
        return _json({"ok": True, "seeded": {}})

    async def _handle_recall(self, request: web.Request) -> web.Response:
        q = request.rel_url.query.get("q", "").strip()
        if not q: return _json({"error": "q required"}, status=400)
        if self._recall_manager:
            results = await self._recall_manager.recall(q, group_id=request.rel_url.query.get("session_id"))
            results = results[:int(request.rel_url.query.get("limit", "5"))]
            algorithm = "hybrid"
        else:
            results = await self._event_repo.search_fts(q, limit=int(request.rel_url.query.get("limit", "5")))
            algorithm = "fts5"
        return _json({"items": [event_to_dict(e) for e in results], "algorithm": algorithm, "query": q, "count": len(results)})

    async def _handle_create_event(self, request: web.Request) -> web.Response:
        body = await request.json()
        now = time.time()
        event = Event(event_id=body.get("event_id") or str(uuid.uuid4()), group_id=body.get("group_id"), start_time=float(body.get("start_time", now)), end_time=float(body.get("end_time", now)), participants=body.get("participants", []), interaction_flow=[], topic=body.get("topic", ""), summary=body.get("summary", ""), chat_content_tags=body.get("chat_content_tags", []), salience=float(body.get("salience", 0.5)), confidence=float(body.get("confidence", 0.8)), inherit_from=body.get("inherit_from", []), last_accessed_at=now, is_locked=bool(body.get("is_locked", False)), status=body.get("status", "active"))
        await self._event_repo.upsert(event)
        return _json({"ok": True, "event": event_to_dict(event)}, status=201)

    async def _handle_update_event(self, request: web.Request) -> web.Response:
        existing = await self._event_repo.get(request.match_info["event_id"])
        if not existing: return _json({"error": "not found"}, status=404)
        body = await request.json()
        updated = Event(event_id=existing.event_id, group_id=body.get("group_id", existing.group_id), start_time=float(body.get("start_time", existing.start_time)), end_time=float(body.get("end_time", existing.end_time)), participants=body.get("participants", existing.participants), interaction_flow=existing.interaction_flow, topic=body.get("topic", existing.topic), summary=body.get("summary", existing.summary), chat_content_tags=body.get("chat_content_tags", existing.chat_content_tags), salience=float(body.get("salience", existing.salience)), confidence=float(body.get("confidence", existing.confidence)), inherit_from=body.get("inherit_from", existing.inherit_from), last_accessed_at=time.time(), is_locked=bool(body.get("is_locked", existing.is_locked)), status=body.get("status", existing.status))
        await self._event_repo.upsert(updated)
        return _json({"ok": True, "event": event_to_dict(updated)})

    async def _handle_delete_event(self, request: web.Request) -> web.Response:
        existing = await self._event_repo.get(request.match_info["event_id"])
        if not existing: return _json({"error": "not found"}, status=404)
        self._recycle_bin.append({**event_to_dict(existing), "deleted_at": _ts_to_iso(time.time())})
        await self._event_repo.delete(request.match_info["event_id"])
        return _json({"ok": True})

    async def _handle_clear_events(self, _: web.Request) -> web.Response:
        deleted = 0
        for gid in await self._event_repo.list_group_ids():
            for ev in await self._event_repo.list_by_group(gid, limit=10000):
                self._recycle_bin.append({**event_to_dict(ev), "deleted_at": _ts_to_iso(time.time())})
                await self._event_repo.delete(ev.event_id); deleted += 1
        return _json({"ok": True, "deleted": deleted})

    async def _handle_recycle_bin_list(self, _: web.Request) -> web.Response: return _json({"items": list(reversed(self._recycle_bin))})

    async def _handle_recycle_bin_restore(self, request: web.Request) -> web.Response:
        body = await request.json()
        item = next((x for x in self._recycle_bin if x["id"] == body.get("event_id")), None)
        if not item: return _json({"error": "not found"}, status=404)
        event = Event(event_id=item["id"], group_id=item.get("group"), start_time=item.get("start_ts", time.time()), end_time=item.get("end_ts", time.time()), participants=item.get("participants", []), interaction_flow=[], topic=item.get("topic", item.get("content", "")), summary=item.get("summary", ""), chat_content_tags=item.get("tags", []), salience=item.get("salience", 0.5), confidence=item.get("confidence", 0.8), inherit_from=item.get("inherit_from", []), last_accessed_at=time.time(), status=item.get("status", "active"), is_locked=item.get("is_locked", False))
        await self._event_repo.upsert(event)
        self._recycle_bin = [x for x in self._recycle_bin if x["id"] != body.get("event_id")]
        return _json({"ok": True, "event": event_to_dict(event)})

    async def _handle_recycle_bin_clear(self, _: web.Request) -> web.Response:
        count = len(self._recycle_bin); self._recycle_bin.clear()
        return _json({"ok": True, "cleared": count})

    async def _handle_archived_events_list(self, _: web.Request) -> web.Response:
        from core.api import list_archived_events
        return _json(await list_archived_events(self._event_repo))

    async def _handle_archive_event(self, request: web.Request) -> web.Response:
        from core.domain.models import EventStatus
        event_id = request.match_info["event_id"]
        existing = await self._event_repo.get(event_id)
        if not existing:
            return _json({"error": "not found"}, status=404)
        await self._event_repo.set_status(event_id, EventStatus.ARCHIVED)
        return _json({"ok": True})

    async def _handle_unarchive_event(self, request: web.Request) -> web.Response:
        from core.domain.models import EventStatus
        event_id = request.match_info["event_id"]
        existing = await self._event_repo.get(event_id)
        if not existing:
            return _json({"error": "not found"}, status=404)
        await self._event_repo.set_status(event_id, EventStatus.ACTIVE)
        return _json({"ok": True})

    async def _handle_create_persona(self, request: web.Request) -> web.Response:
        body = await request.json(); now = time.time()
        bindings = [(b["platform"], b["physical_id"]) for b in body.get("bound_identities", []) if isinstance(b, dict)]
        persona = Persona(uid=body.get("uid") or str(uuid.uuid4()), bound_identities=bindings, primary_name=body.get("primary_name", ""), persona_attrs={"description": body.get("description", ""), "content_tags": body.get("content_tags", [])}, confidence=float(body.get("confidence", 0.8)), created_at=now, last_active_at=now)
        await self._persona_repo.upsert(persona)
        return _json({"ok": True, "persona": persona_to_node(persona)}, status=201)

    async def _handle_update_persona(self, request: web.Request) -> web.Response:
        existing = await self._persona_repo.get(request.match_info["uid"])
        if not existing: return _json({"error": "not found"}, status=404)
        body = await request.json()
        bindings = [(b["platform"], b["physical_id"]) for b in body.get("bound_identities", [])] if "bound_identities" in body else existing.bound_identities
        attrs = {"description": body.get("description", existing.persona_attrs.get("description", "")), "content_tags": body.get("content_tags", existing.persona_attrs.get("content_tags", []))}
        updated = Persona(uid=existing.uid, bound_identities=bindings, primary_name=body.get("primary_name", existing.primary_name), persona_attrs=attrs, confidence=float(body.get("confidence", existing.confidence)), created_at=existing.created_at, last_active_at=time.time())
        await self._persona_repo.upsert(updated)
        return _json({"ok": True, "persona": persona_to_node(updated)})

    async def _handle_delete_persona(self, request: web.Request) -> web.Response:
        if not await self._persona_repo.delete(request.match_info["uid"]): return _json({"error": "not found"}, status=404)
        return _json({"ok": True})

    async def _handle_update_impression_guarded(self, request: web.Request) -> web.Response:
        if not self._relation_enabled: return _json({"error": "disabled"}, status=403)
        obs, sub, scope = request.match_info["observer"], request.match_info["subject"], request.match_info["scope"]
        existing = await self._impression_repo.get(obs, sub, scope); body = await request.json()
        imp = Impression(observer_uid=obs, subject_uid=sub, ipc_orientation=body.get("relation_type", existing.ipc_orientation if existing else "友好"), benevolence=float(body.get("affect", existing.benevolence if existing else 0.0)), power=float(body.get("power", existing.power if existing else 0.0)), affect_intensity=float(body.get("intensity", existing.affect_intensity if existing else 0.5)), r_squared=float(body.get("r_squared", existing.r_squared if existing else 0.7)), confidence=float(body.get("confidence", existing.confidence if existing else 0.7)), scope=scope, evidence_event_ids=body.get("evidence_event_ids", existing.evidence_event_ids if existing else []), last_reinforced_at=time.time())
        await self._impression_repo.upsert(imp)
        return _json({"ok": True, "impression": impression_to_edge(imp)["data"]})

    async def _handle_tags(self, _: web.Request) -> web.Response:
        counts = {}
        for gid in await self._event_repo.list_group_ids():
            for ev in await self._event_repo.list_by_group(gid, limit=10000):
                for tag in (ev.chat_content_tags or []): counts[tag] = counts.get(tag, 0) + 1
        return _json({"tags": [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]})

    async def _handle_get_config(self, _: web.Request) -> web.Response:
        raw = json.loads(self._CONF_SCHEMA_PATH.read_text(encoding="utf-8")) if self._CONF_SCHEMA_PATH.exists() else {}
        
        # Merge each group into one flat dict
        flat_schema: dict = {}
        for group_data in raw.values():
            if isinstance(group_data, dict) and group_data.get("type") == "object":
                flat_schema.update(group_data.get("items", {}))

        # Construct values from flat_schema default
        values: dict = {k: v.get("default") for k, v in flat_schema.items()}
        
        # Priority: 1. Live AstrBot config, 2. Local file, 3. Initial config
        values.update(self._initial_config)
        if self._config_path.exists():
            try:
                values.update(json.loads(self._config_path.read_text(encoding="utf-8")))
            except: pass
        
        if self._star and hasattr(self._star, "config"):
            # AstrBot config might be nested or flat, handle both
            star_cfg = self._star.config
            for k in flat_schema:
                if k in star_cfg:
                    values[k] = star_cfg[k]
                else:
                    # Check nested
                    for group_k, group_v in star_cfg.items():
                        if isinstance(group_v, dict) and k in group_v:
                            values[k] = group_v[k]
        
        return _json({"schema": flat_schema, "values": values})

    async def _handle_get_config_schema(self, _: web.Request) -> web.Response:
        return _json(json.loads(self._CONF_SCHEMA_PATH.read_text(encoding="utf-8")) if self._CONF_SCHEMA_PATH.exists() else {})

    def _sync_password_to_config(self, password: str):
        """Helper to sync password back to AstrBot instance."""
        try:
            # Sync to AstrBot
            if self._star and hasattr(self._star, "config"):
                # Handle both flat and nested
                # We NO LONGER clear the password here. We preserve it so AstrBot core knows it's set.
                if "webui_password" in self._star.config:
                    self._star.config["webui_password"] = password
                if "webui" in self._star.config and isinstance(self._star.config["webui"], dict):
                    self._star.config["webui"]["webui_password"] = password
                
                if hasattr(self._star.config, "save_config"):
                    self._star.config.save_config()
            
            logger.info("[WebUI] Password synced to configuration.")
        except Exception as e:
            logger.warning("[WebUI] Failed to sync password to config: %s", e)

    async def _handle_update_config(self, request: web.Request) -> web.Response:
        body = await request.json()
        raw = json.loads(self._CONF_SCHEMA_PATH.read_text(encoding="utf-8")) if self._CONF_SCHEMA_PATH.exists() else {}
        
        flat_schema: dict = {}
        for group_data in raw.values():
            if isinstance(group_data, dict) and group_data.get("type") == "object":
                flat_schema.update(group_data.get("items", {}))
        
        coerced = {}
        for k, v in body.items():
            if k not in flat_schema: continue
            try:
                t = flat_schema[k].get("type", "string")
                coerced[k] = bool(v) if t == "bool" else (int(v) if t == "int" else (float(v) if t == "float" else v))
            except: coerced[k] = v
        
        # 核心逻辑：如果修改了密码，哈希化存入文件，并【掩码】配置中的明文
        if "webui_password" in coerced and coerced["webui_password"]:
            new_pw = coerced["webui_password"]
            if new_pw != _PASSWORD_MASK:
                try:
                    self._auth.setup_password(new_pw)
                    coerced["webui_password"] = _PASSWORD_MASK # 存完哈希立刻掩码
                    logger.info("[WebUI] Password updated, hashed and masked.")
                except Exception as e:
                    return _json({"error": f"Failed to set password: {str(e)}"}, status=400)
            else:
                # 如果用户只是保存配置而没改掩码，我们就把它从待更新列表中删掉，防止覆盖
                del coerced["webui_password"]

        if coerced:
            try:
                current: dict = {}
                if self._config_path.exists():
                    loaded = json.loads(self._config_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        current.update(loaded)
                current.update(coerced)
                self._config_path.parent.mkdir(parents=True, exist_ok=True)
                self._config_path.write_text(
                    json.dumps(current, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.warning("[WebUI] Failed to write local config: %s", e)

        # Sync to AstrBot
        if self._star and hasattr(self._star, "config"):
            try:
                if hasattr(self._star.config, "update"):
                    self._star.config.update(coerced)

                # Update AstrBot's live config (handles nested structure)
                for k, v in coerced.items():
                    found_in_sub = False
                    # 1. 检查嵌套结构 (例如 webui.webui_password)
                    for group_k, group_v in self._star.config.items():
                        if isinstance(group_v, dict) and k in group_v:
                            group_v[k] = v
                            found_in_sub = True
                    
                    # 2. 如果没在嵌套里找到，直接写在根部 (或者覆盖已有的根部键)
                    if not found_in_sub or k in self._star.config:
                        self._star.config[k] = v
                
                if hasattr(self._star.config, "save_config"):
                    self._star.config.save_config()
            except Exception as e:
                logger.warning("[WebUI] Failed to sync config to AstrBot: %s", e)

        return _json({"ok": True, "saved": list(coerced.keys())})

    async def _handle_get_providers(self, _: web.Request) -> web.Response:
        if not self._all_providers_getter: return _json({"providers": []})
        try:
            data = self._all_providers_getter(); providers = data[1] if isinstance(data, (tuple, list)) and len(data) == 2 else data
            res = [{"id": str(getattr(p, "id", p)), "name": str(getattr(p, "name", p))} for p in providers] if isinstance(providers, (list, tuple)) else []
            return _json({"providers": res})
        except: return _json({"providers": []})

    async def _handle_panels_list(self, _: web.Request) -> web.Response: return _json({"panels": self.registry.list()})
