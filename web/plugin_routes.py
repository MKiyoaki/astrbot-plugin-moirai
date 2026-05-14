"""AstrBot Plugin Pages route handlers for Moirai WebUI.

Registers all API routes via `context.register_web_api()` so that AstrBot
manages the HTTP server and authentication.  The standalone `WebuiServer`
(web/server.py) is kept as a local-debug entry point only.

Route mapping:  /{PLUGIN_NAME}/{path}  →  /api/plug/{PLUGIN_NAME}/{path}
"""
from __future__ import annotations

import json
import logging
import time
import uuid
import inspect
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from quart import Response, request as quart_request

from core.domain.models import Event, Impression, Persona, MessageRef
from .registry import PanelRegistry
from .server import _PASSWORD_MASK

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from core.repository.base import EventRepository, ImpressionRepository, PersonaRepository
    from core.managers.base import BaseRecallManager

    TaskRunner = Callable[[str], Awaitable[bool]]

logger = logging.getLogger(__name__)

_PLUGIN_NAME = "moirai"
_CONF_SCHEMA_PATH = Path(__file__).parent.parent / "_conf_schema.json"


def _ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _json(data: Any, *, status: int = 200) -> Response:
    return Response(
        json.dumps(data, ensure_ascii=False),
        content_type="application/json",
        status=status,
    )


def _query(request: Any, key: str, default: str = "") -> str:
    rel_url = getattr(request, "rel_url", None)
    if rel_url is not None:
        return rel_url.query.get(key, default)
    args = getattr(request, "args", None)
    if args is not None:
        return args.get(key, default)
    return default


def _match(request: Any, key: str) -> str:
    match_info = getattr(request, "match_info", None)
    if match_info is not None:
        return match_info[key]
    view_args = getattr(request, "view_args", None) or {}
    return view_args[key]


async def _request_json(request: Any) -> dict:
    json_attr = getattr(request, "json", None)
    if callable(json_attr):
        return await json_attr()
    if json_attr is not None:
        if inspect.isawaitable(json_attr):
            return await json_attr
        return json_attr
    return await request.get_json()


def _event_to_dict(event: Event) -> dict[str, Any]:
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


def _persona_to_node(persona: Persona) -> dict[str, Any]:
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


def _impression_to_edge(imp: Impression) -> dict[str, Any]:
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


class PluginRoutes:
    """Holds all WebUI route handlers and registers them with AstrBot.

    Unlike WebuiServer, this class has no auth layer — authentication is
    delegated to AstrBot.  The recycle bin remains in-memory session state.
    """

    def __init__(
        self,
        persona_repo: PersonaRepository,
        event_repo: EventRepository,
        impression_repo: ImpressionRepository,
        data_dir: Path,
        task_runner: TaskRunner | None = None,
        plugin_version: str = "0.1.0",
        initial_config: dict | None = None,
        provider_getter: Callable | None = None,
        all_providers_getter: Callable | None = None,
        recall_manager: BaseRecallManager | None = None,
        registry: PanelRegistry | None = None,
        star: Any = None,
    ) -> None:
        self._persona_repo = persona_repo
        self._event_repo = event_repo
        self._impression_repo = impression_repo
        self._data_dir = data_dir
        self._task_runner = task_runner
        self._plugin_version = plugin_version
        self._initial_config: dict = initial_config or {}
        self._provider_getter = provider_getter
        self._all_providers_getter = all_providers_getter
        self._recall_manager = recall_manager
        self.registry = registry or PanelRegistry()
        self._star = star

        self._relation_enabled: bool = bool(self._initial_config.get("relation_enabled", True))
        self._config_path = data_dir / "plugin_config.json"
        self._recycle_bin: list[dict] = []

    # ------------------------------------------------------------------
    # Route registration
    # ------------------------------------------------------------------

    def register(self, context: Any) -> None:
        """Register all routes via context.register_web_api()."""
        p = _PLUGIN_NAME

        def adapt(handler: Any) -> Any:
            async def wrapped(request: Any = None) -> Response:
                return await handler(request or quart_request)
            return wrapped

        routes: list[tuple[str, Any, list[str], str]] = [
            # Stats / soul
            (f"/api/stats",                    self._handle_stats,                   ["GET"],         "Plugin stats"),
            (f"/api/soul/states",              self._handle_soul_states,             ["GET"],         "Soul/recall states"),
            # Events
            (f"/api/events",                   self._handle_events,                  ["GET"],         "List events"),
            (f"/api/events",                   self._handle_create_event,            ["POST"],        "Create event"),
            (f"/api/events/{{event_id}}",      self._handle_update_event,            ["PUT"],         "Update event"),
            (f"/api/events/{{event_id}}/update", self._handle_update_event,          ["POST"],        "Update event"),
            (f"/api/events/{{event_id}}",      self._handle_delete_event,            ["DELETE"],      "Delete event"),
            (f"/api/events/{{event_id}}/delete", self._handle_delete_event,          ["POST"],        "Delete event"),
            (f"/api/events",                   self._handle_clear_events,            ["DELETE"],      "Clear all events"),
            (f"/api/events/delete",            self._handle_clear_events,            ["POST"],        "Clear all events"),
            # Graph
            (f"/api/graph",                    self._handle_graph_guarded,           ["GET"],         "Relation graph"),
            # Summaries
            (f"/api/summaries",                self._handle_summaries,               ["GET"],         "List summaries"),
            (f"/api/summary",                  self._handle_summary,                 ["GET"],         "Get summary content"),
            (f"/api/summary",                  self._handle_update_summary,          ["PUT"],         "Update summary"),
            (f"/api/summary/update",           self._handle_update_summary,          ["POST"],        "Update summary"),
            (f"/api/summary/regenerate",       self._handle_regenerate_summary,      ["POST"],        "Regenerate summary"),
            # Recall
            (f"/api/recall",                   self._handle_recall,                  ["GET"],         "Memory recall"),
            # Tags
            (f"/api/tags",                     self._handle_tags,                    ["GET"],         "List tags"),
            # Personas
            (f"/api/personas",                 self._handle_create_persona,          ["POST"],        "Create persona"),
            (f"/api/personas/{{uid}}",         self._handle_update_persona,          ["PUT"],         "Update persona"),
            (f"/api/personas/{{uid}}/update",  self._handle_update_persona,          ["POST"],        "Update persona"),
            (f"/api/personas/{{uid}}",         self._handle_delete_persona,          ["DELETE"],      "Delete persona"),
            (f"/api/personas/{{uid}}/delete",  self._handle_delete_persona,          ["POST"],        "Delete persona"),
            # Impressions
            (
                f"/api/impressions/{{observer}}/{{subject}}/{{scope}}",
                self._handle_update_impression_guarded,
                ["PUT"],
                "Update impression",
            ),
            (
                f"/api/impressions/{{observer}}/{{subject}}/{{scope}}/update",
                self._handle_update_impression_guarded,
                ["POST"],
                "Update impression",
            ),
            # Recycle bin
            (f"/api/recycle_bin",              self._handle_recycle_bin_list,        ["GET"],         "Recycle bin list"),
            (f"/api/recycle_bin/restore",      self._handle_recycle_bin_restore,     ["POST"],        "Restore from recycle bin"),
            (f"/api/recycle_bin",              self._handle_recycle_bin_clear,       ["DELETE"],      "Clear recycle bin"),
            (f"/api/recycle_bin/delete",       self._handle_recycle_bin_clear,       ["POST"],        "Clear recycle bin"),
            # Config
            (f"/api/config",                   self._handle_get_config,              ["GET"],         "Get config"),
            (f"/api/config",                   self._handle_update_config,           ["PUT"],         "Update config"),
            (f"/api/config/update",            self._handle_update_config,           ["POST"],        "Update config"),
            (f"/api/config/schema",            self._handle_get_config_schema,       ["GET"],         "Config schema"),
            (f"/api/config/providers",         self._handle_get_providers,           ["GET"],         "Available providers"),
            # Admin
            (f"/api/admin/run_task",           self._handle_run_task,                ["POST"],        "Run scheduled task"),
            (f"/api/admin/demo",               self._handle_demo,                    ["POST"],        "Seed demo data"),
            # Panels (PanelRegistry)
            (f"/api/panels",                   self._handle_panels_list,             ["GET"],         "Third-party panel list"),
        ]

        for route_path, handler, methods, description in routes:
            try:
                context.register_web_api(route_path, adapt(handler), methods, description)
            except Exception:
                logger.exception("[PluginRoutes] Failed to register route %s %s", methods, route_path)

        # Register routes from third-party plugins via PanelRegistry
        for route in self.registry.all_routes():
            try:
                context.register_web_api(route.path, route.handler, [route.method], f"ext:{route.path}")
            except Exception:
                logger.exception("[PluginRoutes] Failed to register ext route %s %s", route.method, route.path)

        logger.info("[PluginRoutes] Registered %d routes under /api/plug/%s/", len(routes), p)

    # ------------------------------------------------------------------
    # Data construction helpers (async, independently testable)
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
        return {"items": [_event_to_dict(e) for e in events], "total": len(events)}

    async def graph_data(self) -> dict[str, Any]:
        personas = await self._persona_repo.list_all()
        uid_msg_counts = await self._event_repo.count_messages_by_uid_bulk()

        nodes = []
        for p in personas:
            node = _persona_to_node(p)
            node["data"]["msg_count"] = uid_msg_counts.get(p.uid, 0)
            nodes.append(node)

        edges: list[dict[str, Any]] = []
        for persona in personas:
            imps = await self._impression_repo.list_by_observer(persona.uid)
            for imp in imps:
                edge = _impression_to_edge(imp)
                edge["data"]["msg_count"] = await self._event_repo.count_edge_messages(
                    imp.observer_uid, imp.subject_uid, imp.scope
                )
                edges.append(edge)

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

    # ------------------------------------------------------------------
    # Handlers: stats / soul
    # ------------------------------------------------------------------

    async def _handle_stats(self, request: web.Request) -> web.Response:
        return _json(await self.stats_data())

    async def _handle_soul_states(self, request: web.Request) -> web.Response:
        if self._recall_manager is None:
            return _json({"states": {}})
        states = getattr(self._recall_manager, "get_soul_states", lambda: {})()
        return _json({"states": states})

    # ------------------------------------------------------------------
    # Handlers: events
    # ------------------------------------------------------------------

    async def _handle_events(self, request: web.Request) -> web.Response:
        group_id = _query(request, "group_id") or None
        limit = int(_query(request, "limit", "100"))
        return _json(await self.events_data(group_id, limit))

    async def _handle_create_event(self, request: web.Request) -> web.Response:
        body = await _request_json(request)
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
        return _json({"ok": True, "event": _event_to_dict(event)}, status=201)

    async def _handle_update_event(self, request: web.Request) -> web.Response:
        event_id = _match(request, "event_id")
        existing = await self._event_repo.get(event_id)
        if existing is None:
            return _json({"error": "not found"}, status=404)
        body = await _request_json(request)
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
                chat_content_tags=body.get("chat_content_tags", existing.chat_content_tags),
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
        return _json({"ok": True, "event": _event_to_dict(updated)})

    async def _handle_delete_event(self, request: web.Request) -> web.Response:
        event_id = _match(request, "event_id")
        existing = await self._event_repo.get(event_id)
        if existing is None:
            return _json({"error": "not found"}, status=404)
        self._recycle_bin.append({
            **_event_to_dict(existing),
            "deleted_at": _ts_to_iso(time.time()),
        })
        await self._event_repo.delete(event_id)
        return _json({"ok": True})

    async def _handle_clear_events(self, request: web.Request) -> web.Response:
        group_ids = await self._event_repo.list_group_ids()
        deleted = 0
        for gid in group_ids:
            events = await self._event_repo.list_by_group(gid, limit=10_000)
            for ev in events:
                self._recycle_bin.append({
                    **_event_to_dict(ev),
                    "deleted_at": _ts_to_iso(time.time()),
                })
                await self._event_repo.delete(ev.event_id)
                deleted += 1
        return _json({"ok": True, "deleted": deleted})

    # ------------------------------------------------------------------
    # Handlers: graph / impressions
    # ------------------------------------------------------------------

    def _relation_disabled_response(self) -> web.Response | None:
        if not self._relation_enabled:
            return _json({"enabled": False, "nodes": [], "edges": []})
        return None

    async def _handle_graph_guarded(self, request: web.Request) -> web.Response:
        guard = self._relation_disabled_response()
        if guard is not None:
            return guard
        return _json(await self.graph_data())

    async def _handle_update_impression_guarded(self, request: web.Request) -> web.Response:
        guard = self._relation_disabled_response()
        if guard is not None:
            return guard
        return await self._handle_update_impression(request)

    async def _handle_update_impression(self, request: web.Request) -> web.Response:
        observer = _match(request, "observer")
        subject = _match(request, "subject")
        scope = _match(request, "scope")
        existing = await self._impression_repo.get(observer, subject, scope)
        body = await _request_json(request)
        now = time.time()
        try:
            impression = Impression(
                observer_uid=observer,
                subject_uid=subject,
                ipc_orientation=body.get("relation_type", existing.ipc_orientation if existing else "友好"),
                benevolence=float(body.get("affect", existing.benevolence if existing else 0.0)),
                power=float(body.get("power", existing.power if existing else 0.0)),
                affect_intensity=float(body.get("intensity", existing.affect_intensity if existing else 0.5)),
                r_squared=float(body.get("r_squared", existing.r_squared if existing else 0.7)),
                confidence=float(body.get("confidence", existing.confidence if existing else 0.7)),
                scope=scope,
                evidence_event_ids=body.get("evidence_event_ids", existing.evidence_event_ids if existing else []),
                last_reinforced_at=now,
            )
        except (ValueError, TypeError) as exc:
            return _json({"error": str(exc)}, status=400)
        await self._impression_repo.upsert(impression)
        return _json({"ok": True, "impression": _impression_to_edge(impression)["data"]})

    # ------------------------------------------------------------------
    # Handlers: summaries
    # ------------------------------------------------------------------

    async def _handle_summaries(self, request: web.Request) -> web.Response:
        return _json(await self.summaries_data())

    async def _handle_summary(self, request: web.Request) -> web.Response:
        group_id = _query(request, "group_id") or None
        date = _query(request, "date", "")
        if not date:
            return _json({"error": "date required"}, status=400)
        content = self.summary_content(group_id, date)
        if content is None:
            return _json({"error": "not found"}, status=404)
        return _json({"content": content})

    async def _handle_update_summary(self, request: web.Request) -> web.Response:
        body = await _request_json(request)
        group_id = body.get("group_id") or None
        date = body.get("date", "")
        content = body.get("content", "")
        if not date:
            return _json({"error": "date required"}, status=400)
        if group_id:
            path = self._data_dir / "groups" / group_id / "summaries" / f"{date}.md"
        else:
            path = self._data_dir / "global" / "summaries" / f"{date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return _json({"ok": True})

    async def _handle_regenerate_summary(self, request: web.Request) -> web.Response:
        if self._provider_getter is None:
            return _json({"error": "provider_getter not wired"}, status=503)
        body = await _request_json(request)
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
            logger.warning("[PluginRoutes] regenerate_summary failed: %s", exc)
            return _json({"error": str(exc)}, status=500)
        if content is None:
            return _json({"error": "no events or no provider"}, status=503)
        return _json({"content": content})

    # ------------------------------------------------------------------
    # Handlers: recall / tags
    # ------------------------------------------------------------------

    async def _handle_recall(self, request: web.Request) -> web.Response:
        q = _query(request, "q", "").strip()
        limit = min(int(_query(request, "limit", "5")), 50)
        session_id = _query(request, "session_id", "").strip() or None
        if not q:
            return _json({"error": "q required"}, status=400)
        try:
            if self._recall_manager:
                results = await self._recall_manager.recall(q, group_id=session_id)
                results = results[:limit]
                algorithm = "hybrid (rrf)"
            else:
                results = await self._event_repo.search_fts(q, limit=limit)
                algorithm = "fts5"
        except Exception as exc:
            logger.exception("Recall failed")
            return _json({"error": str(exc)}, status=500)
        return _json({
            "items": [_event_to_dict(e) for e in results],
            "algorithm": algorithm,
            "query": q,
            "count": len(results),
        })

    async def _handle_tags(self, request: web.Request) -> web.Response:
        counts: dict[str, int] = {}
        for gid in await self._event_repo.list_group_ids():
            for ev in await self._event_repo.list_by_group(gid, limit=10_000):
                for tag in (ev.chat_content_tags or []):
                    counts[tag] = counts.get(tag, 0) + 1
        tags = [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
        return _json({"tags": tags})

    # ------------------------------------------------------------------
    # Handlers: personas
    # ------------------------------------------------------------------

    async def _handle_create_persona(self, request: web.Request) -> web.Response:
        body = await _request_json(request)
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
        return _json({"ok": True, "persona": _persona_to_node(persona)}, status=201)

    async def _handle_update_persona(self, request: web.Request) -> web.Response:
        uid = _match(request, "uid")
        existing = await self._persona_repo.get(uid)
        if existing is None:
            return _json({"error": "not found"}, status=404)
        body = await _request_json(request)
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
        return _json({"ok": True, "persona": _persona_to_node(updated)})

    async def _handle_delete_persona(self, request: web.Request) -> web.Response:
        uid = _match(request, "uid")
        ok = await self._persona_repo.delete(uid)
        if not ok:
            return _json({"error": "not found"}, status=404)
        return _json({"ok": True})

    # ------------------------------------------------------------------
    # Handlers: recycle bin
    # ------------------------------------------------------------------

    async def _handle_recycle_bin_list(self, request: web.Request) -> web.Response:
        return _json({"items": list(reversed(self._recycle_bin))})

    async def _handle_recycle_bin_restore(self, request: web.Request) -> web.Response:
        body = await _request_json(request)
        event_id = body.get("event_id", "")
        if not event_id:
            return _json({"error": "event_id required"}, status=400)
        item = next((x for x in self._recycle_bin if x["id"] == event_id), None)
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
                summary=item.get("summary", ""),
                chat_content_tags=item.get("tags", []),
                salience=item.get("salience", 0.5),
                confidence=item.get("confidence", 0.8),
                inherit_from=item.get("inherit_from", []),
                last_accessed_at=now,
                status=item.get("status", "active"),
                is_locked=item.get("is_locked", False),
            )
        except Exception as exc:
            return _json({"error": str(exc)}, status=400)
        try:
            await self._event_repo.upsert(event)
        except Exception as exc:
            return _json({"error": f"Database error: {str(exc)}"}, status=500)
        self._recycle_bin = [x for x in self._recycle_bin if x["id"] != event_id]
        return _json({"ok": True, "event": _event_to_dict(event)})

    async def _handle_recycle_bin_clear(self, request: web.Request) -> web.Response:
        count = len(self._recycle_bin)
        self._recycle_bin.clear()
        return _json({"ok": True, "cleared": count})

    # ------------------------------------------------------------------
    # Handlers: config
    # ------------------------------------------------------------------

    def _load_conf_schema(self) -> dict:
        try:
            return json.loads(_CONF_SCHEMA_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _read_config(self) -> dict:
        raw = self._load_conf_schema()
        # 展平：把每个 group 的 items 合并到一个 flat dict
        flat_schema: dict = {}
        for group_data in raw.values():
            if isinstance(group_data, dict) and group_data.get("type") == "object":
                flat_schema.update(group_data.get("items", {}))

        merged: dict = {k: v.get("default") for k, v in flat_schema.items()}
        merged.update(self._initial_config)
        if self._config_path.exists():
            try:
                saved = json.loads(self._config_path.read_text(encoding="utf-8"))
                merged.update(saved)
            except Exception:
                pass
        return merged

    async def _handle_get_config(self, request: web.Request) -> web.Response:
        raw = self._load_conf_schema()
        # 展平
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
                saved = json.loads(self._config_path.read_text(encoding="utf-8"))
                values.update(saved)
            except: pass

        if self._star and hasattr(self._star, "config"):
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

    async def _handle_get_config_schema(self, request: web.Request) -> web.Response:
        raw = self._load_conf_schema()
        flat_schema: dict = {}
        for group_data in raw.values():
            if isinstance(group_data, dict) and group_data.get("type") == "object":
                flat_schema.update(group_data.get("items", {}))
        return _json(flat_schema)

    def _sync_password_to_file(self, password: str):
        """Helper to sync password back to .webui_password file (hashed)."""
        if not password: return
        try:
            # We don't have AuthManager here, but we can do a simple hash
            # or just rely on the next restart to pick it up.
            # Actually, it's better to use the same logic as AuthManager.
            from .auth import _hash_password
            pw_file = self._data_dir / ".webui_password"
            pw_file.write_text(_hash_password(password), encoding="utf-8")
            try: pw_file.chmod(0o600)
            except: pass
        except Exception as e:
            logger.warning("[PluginRoutes] Failed to sync password to file: %s", e)

    async def _handle_update_config(self, request: web.Request) -> web.Response:
        body = await _request_json(request)
        raw = self._load_conf_schema()
        # 构建 flat schema 用于类型校验
        flat_schema: dict = {}
        for group_data in raw.values():
            if isinstance(group_data, dict) and group_data.get("type") == "object":
                flat_schema.update(group_data.get("items", {}))

        coerced: dict = {}
        for key, val in body.items():
            if key not in flat_schema:
                continue
            field_type = flat_schema[key].get("type", "string")
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
        
        # 核心逻辑：如果修改了密码，哈希化存入文件，并【掩码】配置中的明文
        if "webui_password" in coerced and coerced["webui_password"]:
            new_pw = coerced["webui_password"]
            if new_pw != _PASSWORD_MASK:
                try:
                    from .auth import _hash_password
                    pw_file = self._data_dir / ".webui_password"
                    pw_file.write_text(_hash_password(new_pw), encoding="utf-8")
                    try: pw_file.chmod(0o600)
                    except: pass
                    coerced["webui_password"] = _PASSWORD_MASK # 存完哈希立刻掩码
                    logger.info("[PluginRoutes] Password updated, hashed and masked.")
                except Exception as e:
                    return _json({"error": f"Failed to set password: {str(e)}"}, status=400)
            else:
                # 如果用户只是保存配置而没改掩码，我们就把它从待更新列表中删掉
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
                logger.warning("[PluginRoutes] Failed to write local config: %s", e)

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
                logger.warning("[PluginRoutes] Failed to sync config to AstrBot: %s", e)

        return _json({"ok": True, "saved": list(coerced.keys())})

    async def _handle_get_providers(self, request: web.Request) -> web.Response:
        if self._all_providers_getter is None:
            return _json({"providers": []})
        try:
            data = self._all_providers_getter()
            providers = data
            if isinstance(data, (tuple, list)) and len(data) == 2 and isinstance(data[0], bool):
                providers = data[1]
            res = []
            if isinstance(providers, (list, tuple)):
                for p in providers:
                    p_id = getattr(p, "id", "")
                    p_name = getattr(p, "name", "")
                    if not p_id and hasattr(p, "__dict__"):
                        p_id = p.__dict__.get("id", str(p))
                    if not p_name and hasattr(p, "__dict__"):
                        p_name = p.__dict__.get("name", str(p))
                    res.append({"id": str(p_id or p), "name": str(p_name or p)})
            return _json({"providers": res})
        except Exception as exc:
            logger.warning("[PluginRoutes] get_providers failed: %s", exc)
            return _json({"error": str(exc)}, status=500)

    # ------------------------------------------------------------------
    # Handlers: admin
    # ------------------------------------------------------------------

    async def _handle_run_task(self, request: web.Request) -> web.Response:
        if self._task_runner is None:
            return _json({"error": "task runner not wired"}, status=503)
        body = await _request_json(request)
        name = body.get("name", "")
        if not name:
            return _json({"error": "task name required"}, status=400)
        try:
            ok = await self._task_runner(name)
        except Exception as exc:
            return _json({"error": str(exc)}, status=500)
        return _json({"ok": ok})

    async def _handle_demo(self, request: web.Request) -> web.Response:
        now = time.time()
        DAY = 86_400

        personas = [
            Persona(
                uid="demo_uid_alice", bound_identities=[("qq", "demo_10001")],
                primary_name="Alice",
                persona_attrs={"description": "热情开朗，喜爱音乐与户外运动",
                               "content_tags": ["音乐", "徒步", "摄影"],
                               "big_five": {"E": 0.7, "A": 0.6, "O": 0.4, "C": 0.1, "N": -0.2}},
                confidence=0.92, created_at=now - 45 * DAY, last_active_at=now - DAY,
            ),
            Persona(
                uid="demo_uid_bob", bound_identities=[("qq", "demo_10002")],
                primary_name="Bob",
                persona_attrs={"description": "资深开发者，逻辑严密但乐于助人",
                               "content_tags": ["Python", "架构", "AI"],
                               "big_five": {"C": 0.7, "O": 0.5, "A": 0.4, "E": -0.1}},
                confidence=0.85, created_at=now - 40 * DAY, last_active_at=now - 2 * DAY,
            ),
            Persona(
                uid="demo_uid_charlie", bound_identities=[("telegram", "demo_tg_charlie")],
                primary_name="Charlie",
                persona_attrs={"description": "数据分析师，喜欢分享科技资讯",
                               "content_tags": ["科技", "阅读", "旅行"],
                               "big_five": {"O": 0.6, "C": 0.5, "E": 0.3}},
                confidence=0.78, created_at=now - 20 * DAY, last_active_at=now - 5 * DAY,
            ),
            Persona(
                uid="demo_uid_diana", bound_identities=[("internal", "diana_web")],
                primary_name="Diana",
                persona_attrs={"description": "文学爱好者，对话风格温婉",
                               "content_tags": ["文学", "诗歌", "艺术"],
                               "big_five": {"O": 0.7, "A": 0.7, "E": -0.4, "C": 0.3}},
                confidence=0.72, created_at=now - 10 * DAY, last_active_at=now - 12 * 3600,
            ),
            Persona(
                uid="demo_uid_bot", bound_identities=[("internal", "bot")],
                primary_name="BOT",
                persona_attrs={"description": "搭载增强记忆引擎的智能助手",
                               "content_tags": ["记忆管理", "日程分析"]},
                confidence=1.0, created_at=now - 90 * DAY, last_active_at=now,
            ),
        ]
        events = [
            Event(
                event_id="demo_evt_001", group_id="demo_group_001",
                start_time=now - 10 * DAY, end_time=now - 10 * DAY + 1200,
                participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_bot"],
                interaction_flow=[
                    MessageRef("demo_uid_alice", now - 10 * DAY, "h1", "大家早安！"),
                    MessageRef("demo_uid_bob", now - 10 * DAY + 60, "h2", "早，Alice。"),
                ],
                topic="早安问候", summary="Alice 发起早安问候，Bob 礼貌回应，群组开启了一天的活跃氛围。",
                chat_content_tags=["社交", "日常"], salience=0.3, confidence=0.95,
                inherit_from=[], last_accessed_at=now - 5 * DAY,
            ),
            Event(
                event_id="demo_evt_002", group_id="demo_group_001",
                start_time=now - 8 * DAY, end_time=now - 8 * DAY + 3600,
                participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_bot"],
                interaction_flow=[],
                topic="音乐推荐：古典乐之美",
                summary="Alice 分享了几首德彪西的曲目，Bob 探讨了古典乐对专注力的提升作用。",
                chat_content_tags=["艺术", "分享"], salience=0.65, confidence=0.88,
                inherit_from=["demo_evt_001"], last_accessed_at=now - 2 * DAY,
            ),
            Event(
                event_id="demo_evt_003", group_id="demo_group_001",
                start_time=now - 6 * DAY, end_time=now - 6 * DAY + 5400,
                participants=["demo_uid_bob", "demo_uid_charlie", "demo_uid_bot"],
                interaction_flow=[],
                topic="异步 IO 性能调优",
                summary="Bob 与 Charlie 深入讨论了 Python asyncio 的事件循环机制及在高并发场景下的优化策略。",
                chat_content_tags=["技术", "知识"], salience=0.82, confidence=0.94,
                inherit_from=[], last_accessed_at=now - 12 * 3600,
            ),
            Event(
                event_id="demo_evt_004", group_id="demo_group_002",
                start_time=now - 4 * DAY, end_time=now - 4 * DAY + 2400,
                participants=["demo_uid_alice", "demo_uid_diana", "demo_uid_bot"],
                interaction_flow=[],
                topic="周末徒步计划",
                summary="Alice 邀请 Diana 周末去西山徒步，Diana 建议携带专业摄影器材记录秋景。",
                chat_content_tags=["运动", "日常"], salience=0.58, confidence=0.85,
                inherit_from=[], last_accessed_at=now - DAY,
            ),
            Event(
                event_id="demo_evt_005", group_id=None,
                start_time=now - 2 * DAY, end_time=now - 2 * DAY + 900,
                participants=["demo_uid_bob", "demo_uid_bot"],
                interaction_flow=[],
                topic="私聊：核心架构咨询",
                summary="Bob 私下向 BOT 询问了增强记忆引擎的向量检索原理，表现出对底层实现的浓厚兴趣。",
                chat_content_tags=["技术", "咨询"], salience=0.75, confidence=0.89,
                inherit_from=["demo_evt_003"], last_accessed_at=now - 3600,
            ),
            Event(
                event_id="demo_evt_006", group_id="demo_group_001",
                start_time=now - DAY, end_time=now - DAY + 4200,
                participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_charlie", "demo_uid_bot"],
                interaction_flow=[],
                topic="AI 伦理与长期记忆",
                summary="群组讨论了机器人拥有长期记忆后可能带来的隐私风险及相关的伦理边界问题。",
                chat_content_tags=["AI", "知识"], salience=0.91, confidence=0.92,
                inherit_from=[], last_accessed_at=now, is_locked=True,
            ),
            Event(
                event_id="demo_evt_007", group_id="demo_group_002",
                start_time=now - 18 * 3600, end_time=now - 17 * 3600,
                participants=["demo_uid_diana", "demo_uid_bot"],
                interaction_flow=[],
                topic="现代诗歌鉴赏",
                summary="Diana 朗读了一首关于时间的诗，BOT 从语义角度给出了深刻的解读与回应。",
                chat_content_tags=["艺术", "文学"], salience=0.42, confidence=0.81,
                inherit_from=[], last_accessed_at=now - 6 * 3600,
            ),
            Event(
                event_id="demo_evt_008", group_id="demo_group_001",
                start_time=now - 6 * 3600, end_time=now - 5 * 3600,
                participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_bot"],
                interaction_flow=[],
                topic="项目周报同步",
                summary="Alice 汇总了本周的讨论热点，Bob 确认了技术分享的排期，群组达成阶段性一致。",
                chat_content_tags=["工作", "同步"], salience=0.67, confidence=0.88,
                inherit_from=["demo_evt_006"], last_accessed_at=now,
            ),
        ]
        impressions = [
            Impression(
                observer_uid="demo_uid_bot", subject_uid="demo_uid_alice",
                ipc_orientation="友好", benevolence=0.85, power=0.1,
                affect_intensity=0.6, r_squared=0.88, confidence=0.92, scope="global",
                evidence_event_ids=["demo_evt_001", "demo_evt_002", "demo_evt_004", "demo_evt_006"],
                last_reinforced_at=now - 12 * 3600,
            ),
            Impression(
                observer_uid="demo_uid_bot", subject_uid="demo_uid_bob",
                ipc_orientation="支配友好", benevolence=0.3, power=0.45,
                affect_intensity=0.38, r_squared=0.75, confidence=0.89, scope="global",
                evidence_event_ids=["demo_evt_001", "demo_evt_003", "demo_evt_005", "demo_evt_006", "demo_evt_008"],
                last_reinforced_at=now - 3600,
            ),
            Impression(
                observer_uid="demo_uid_bot", subject_uid="demo_uid_charlie",
                ipc_orientation="友好", benevolence=0.4, power=-0.1,
                affect_intensity=0.25, r_squared=0.65, confidence=0.81, scope="demo_group_001",
                evidence_event_ids=["demo_evt_003", "demo_evt_006"],
                last_reinforced_at=now - DAY,
            ),
            Impression(
                observer_uid="demo_uid_bot", subject_uid="demo_uid_diana",
                ipc_orientation="友好", benevolence=0.65, power=-0.2,
                affect_intensity=0.42, r_squared=0.81, confidence=0.85, scope="demo_group_002",
                evidence_event_ids=["demo_evt_004", "demo_evt_007"],
                last_reinforced_at=now - 6 * 3600,
            ),
            Impression(
                observer_uid="demo_uid_alice", subject_uid="demo_uid_bot",
                ipc_orientation="友好", benevolence=0.9, power=0.0,
                affect_intensity=0.65, r_squared=0.92, confidence=0.85, scope="global",
                evidence_event_ids=["demo_evt_001", "demo_evt_002"],
                last_reinforced_at=now - DAY,
            ),
            Impression(
                observer_uid="demo_uid_bob", subject_uid="demo_uid_alice",
                ipc_orientation="友好", benevolence=0.55, power=0.1,
                affect_intensity=0.4, r_squared=0.78, confidence=0.75, scope="demo_group_001",
                evidence_event_ids=["demo_evt_002"],
                last_reinforced_at=now - 8 * DAY,
            ),
            Impression(
                observer_uid="demo_uid_diana", subject_uid="demo_uid_alice",
                ipc_orientation="友好", benevolence=0.75, power=0.0,
                affect_intensity=0.5, r_squared=0.85, confidence=0.82, scope="demo_group_002",
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

        _DEMO_SUMMARY_1 = "# 群组 demo_group_001 活动摘要 — 2026-05-01\n\n[主要话题]\nAlice 和 Bob 进行了早安问候，随后 Alice 分享了几首独立音乐新歌。\n"
        _DEMO_SUMMARY_2 = "# 群组 demo_group_001 活动摘要 — 2026-05-02\n\n[主要话题]\nAlice 与 Charlie 确定了周末游戏约定，Bob 与 Charlie 深入探讨了 Python asyncio 的并发优化策略。\n"
        for date, content in [("2026-05-01", _DEMO_SUMMARY_1), ("2026-05-02", _DEMO_SUMMARY_2)]:
            path = self._data_dir / "groups" / "demo_group_001" / "summaries" / f"{date}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        return _json({"ok": True, "seeded": {"personas": len(personas), "events": len(events), "impressions": len(impressions)}})

    # ------------------------------------------------------------------
    # Handlers: panels
    # ------------------------------------------------------------------

    async def _handle_panels_list(self, request: web.Request) -> web.Response:
        return _json({"panels": self.registry.list()})
