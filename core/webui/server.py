"""Lightweight aiohttp WebUI server — three-panel memory visualiser.

Panels:
  1. Event Flow      — vis-timeline, events as bars, inherit_from as edges
  2. Relation Graph  — Cytoscape.js, personas as nodes, impressions as edges
  3. Summarised Memory — marked.js, renders daily summary Markdown files

Data-building logic is extracted into async methods (*_data) so tests can
call them directly without needing a live HTTP server.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web

from ..domain.models import Event, Impression, Persona
from ..repository.base import EventRepository, ImpressionRepository, PersonaRepository

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"
_DEFAULT_PORT = 2653


def _ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _json(data: Any) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# Serialisation helpers (pure functions, tested directly)
# ---------------------------------------------------------------------------

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

class WebuiServer:
    """Serves the three-panel WebUI and JSON API on localhost:{port}."""

    def __init__(
        self,
        persona_repo: PersonaRepository,
        event_repo: EventRepository,
        impression_repo: ImpressionRepository,
        data_dir: Path,
        port: int = _DEFAULT_PORT,
    ) -> None:
        self._persona_repo = persona_repo
        self._event_repo = event_repo
        self._impression_repo = impression_repo
        self._data_dir = data_dir
        self._port = port
        self._app = self._build_app()
        self._runner: web.AppRunner | None = None

    def _build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/api/events", self._handle_events)
        app.router.add_get("/api/graph", self._handle_graph)
        app.router.add_get("/api/summaries", self._handle_summaries)
        app.router.add_get("/api/summary", self._handle_summary)
        return app

    @property
    def app(self) -> web.Application:
        return self._app

    async def start(self) -> None:
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "localhost", self._port)
        await site.start()
        logger.info("[WebUI] listening on http://localhost:%d", self._port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("[WebUI] stopped")

    # -------------------------------------------------------------------------
    # Data builders (async, no HTTP dependency — directly testable)
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Route handlers
    # -------------------------------------------------------------------------

    async def _handle_index(self, _: web.Request) -> web.Response:
        return web.Response(
            text=(_STATIC_DIR / "index.html").read_text(encoding="utf-8"),
            content_type="text/html",
        )

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
            raise web.HTTPBadRequest(reason="date parameter required")
        content = self.summary_content(group_id, date)
        if content is None:
            raise web.HTTPNotFound()
        return _json({"content": content})
