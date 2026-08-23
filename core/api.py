"""Pure business-logic functions for the memory plugin.

These functions are framework-agnostic: no aiohttp, no HTTP concepts.
web/server.py delegates to these and wraps results in HTTP responses.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

from .domain.models import Event, EventStatus, Impression, INTERNAL_PLATFORM, Persona
from .tags import derive_tag_categories
from .utils.version import get_plugin_version

if TYPE_CHECKING:
    from .managers.memory_manager import MemoryManager
    from .managers.recall_manager import RecallManager
    from .repository.base import EventRepository, ImpressionRepository, PersonaRepository
    from .managers.llm_manager import LLMTaskManager


# ---------------------------------------------------------------------------
# Serialisation helpers (pure functions)
# ---------------------------------------------------------------------------

def _ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def event_to_dict(event: Event) -> dict[str, Any]:
    participants = event.participants or []
    return {
        "id": event.event_id,
        "content": event.topic or event.event_id[:8],
        "topic": event.topic,
        "summary": event.summary,
        "start": _ts(event.start_time),
        "end": _ts(event.end_time),
        "start_ts": event.start_time,
        "end_ts": event.end_time,
        "group": event.group_id,
        "salience": round(event.salience, 3),
        "confidence": round(event.confidence, 3),
        "tags": event.chat_content_tags,
        "tag_categories": derive_tag_categories(event.chat_content_tags),
        "inherit_from": event.inherit_from,
        "participants": participants,
        "participant_names": {uid: uid for uid in participants},
        "status": event.status,
        "is_locked": event.is_locked,
    }


def persona_to_dict(persona: Persona) -> dict[str, Any]:
    return {
        "uid": persona.uid,
        "primary_name": persona.primary_name,
        "confidence": round(persona.confidence, 3),
        "attrs": persona.persona_attrs,
        "bound_identities": [
            {"platform": p, "physical_id": pid}
            for p, pid in persona.bound_identities
        ],
        "created_at": _ts(persona.created_at),
        "last_active_at": _ts(persona.last_active_at),
        "is_bot": any(p == INTERNAL_PLATFORM for p, _ in persona.bound_identities),
    }


def impression_to_dict(imp: Impression) -> dict[str, Any]:
    return {
        "id": f"{imp.observer_uid}--{imp.subject_uid}--{imp.scope}",
        "observer_uid": imp.observer_uid,
        "subject_uid": imp.subject_uid,
        "ipc_orientation": imp.ipc_orientation,
        "benevolence": round(imp.benevolence, 3),
        "power": round(imp.power, 3),
        "affect_intensity": round(imp.affect_intensity, 3),
        "r_squared": round(imp.r_squared, 3),
        "confidence": round(imp.confidence, 3),
        "scope": imp.scope,
        "evidence_event_ids": imp.evidence_event_ids,
        "last_reinforced_at": _ts(imp.last_reinforced_at),
    }


# ---------------------------------------------------------------------------
# Business-logic functions
# ---------------------------------------------------------------------------

async def get_stats(
    persona_repo: PersonaRepository,
    event_repo: EventRepository,
    impression_repo: ImpressionRepository,
    data_dir: Path | None = None,
    plugin_version: str | None = None,
    llm_manager: LLMTaskManager | None = None,
    context_manager: object | None = None,
    summary_trigger_rounds: int = 30,
    show_llm_call_details: bool = False,
) -> dict[str, Any]:

    if plugin_version is None:
        plugin_version = get_plugin_version()
    from .utils.perf import tracker
    perf_metrics = await tracker.get_metrics()
    
    from .domain.models import EventStatus
    from .repository.base import EventStatusStats
    persona_count, group_count, status_stats, impression_count = await asyncio.gather(
        persona_repo.count(),
        event_repo.count_groups(),
        event_repo.aggregate_by_status(),
        # Orphaned rows (observer persona deleted) stay excluded, matching
        # both the previous count and what the relation graph renders.
        impression_repo.count_all(known_observers_only=True),
    )
    active = status_stats.get(EventStatus.ACTIVE, EventStatusStats())
    archived = status_stats.get(EventStatus.ARCHIVED, EventStatusStats())
    active_count, archived_count = active.total, archived.total
    locked_count = active.locked

    # Count summary files and calculate simple metrics
    summary_count = 0
    total_summary_chars = 0
    summary_days = set()
    if data_dir:
        try:
            from .tasks.summary_paths import iter_summary_paths
            summary_files = list(iter_summary_paths(data_dir))
            summary_count = len(summary_files)
            for f in summary_files:
                summary_days.add(f.stem) # YYYY-MM-DD
                total_summary_chars += f.stat().st_size 
        except Exception:
            pass
    
    avg_summary_chars = (total_summary_chars / summary_count) if summary_count > 0 else 0

    # Format detailed perf stats for frontend
    perf_stats = {}
    for phase, m in perf_metrics.items():
        perf_stats[phase] = {
            "avg_ms": round(m.get("avg", 0.0) * 1000, 2),
            "last_ms": round(m.get("last", 0.0) * 1000, 2),
            "avg_hits": round(m.get("avg_hits", 0.0), 2),
            "last_hits": int(m.get("last_hits", 0)),
        }
    
    # LLM Token stats
    llm_stats = llm_manager.get_stats(show_details=show_llm_call_details) if llm_manager else {}
    
    # Backward compatibility for existing flat fields (in seconds)
    legacy_perf = {
        f"avg_{phase}_time": round(m.get("avg", 0.0), 3)
        for phase, m in perf_metrics.items()
    }
    perf_stats.update(legacy_perf)

    # Active session window progress
    active_sessions: list[dict[str, Any]] = []
    if context_manager is not None:
        try:
            windows = list(getattr(context_manager, "_windows", {}).values())
            trigger_threshold = summary_trigger_rounds * 2
            for w in windows:
                current_rounds = w.message_count // 2
                active_sessions.append({
                    "session_id": w.session_id,
                    "group_id": w.group_id,
                    "message_count": w.message_count,
                    "current_rounds": current_rounds,
                    "trigger_rounds": summary_trigger_rounds,
                    "trigger_threshold_messages": trigger_threshold,
                })
        except Exception as e:
            logger.warning("[get_stats] failed to read active_sessions from context_manager: %s", e, exc_info=True)

    return {
        "personas": persona_count,
        "events": active_count,
        "archived_events": archived_count,
        "locked_count": locked_count,
        "impressions": impression_count,
        "summaries": summary_count,
        "summary_days": len(summary_days),
        "avg_summary_chars": round(avg_summary_chars, 1),
        "groups": group_count,
        "version": plugin_version,
        "perf": perf_stats,
        "llm_stats": llm_stats,
        "active_sessions": active_sessions,
        "summary_trigger_rounds": summary_trigger_rounds,
    }


async def list_events(
    event_repo: EventRepository,
    group_id: str | None,
    limit: int = 100,
) -> dict[str, Any]:
    if group_id is not None:
        events = await event_repo.list_by_group(group_id, limit=limit)
    else:
        group_ids = await event_repo.list_group_ids()
        if not group_ids:
            return {"items": []}
        per_group = max(1, limit // len(group_ids))
        events: list[Event] = []
        for gid in group_ids:
            events.extend(await event_repo.list_by_group(gid, limit=per_group))
        events = events[:limit]
    events = [e for e in events if e.status == EventStatus.ACTIVE]
    return {"items": [event_to_dict(e) for e in events]}


async def list_archived_events(
    event_repo: EventRepository,
    limit: int = 1000,
) -> dict[str, Any]:
    from .domain.models import EventStatus
    events = await event_repo.list_by_status(EventStatus.ARCHIVED, limit=limit)
    return {"items": [event_to_dict(e) for e in events]}


async def get_event(
    event_repo: EventRepository, event_id: str
) -> dict[str, Any] | None:
    event = await event_repo.get(event_id)
    return event_to_dict(event) if event else None


async def update_event(
    memory: MemoryManager, event_id: str, patch: dict[str, Any]
) -> dict[str, Any] | None:
    event = await memory.get_event(event_id)
    if event is None:
        return None
    changes: dict[str, Any] = {}
    if "topic" in patch:
        changes["topic"] = str(patch["topic"])
    if "summary" in patch:
        changes["summary"] = str(patch["summary"])
    if "salience" in patch:
        changes["salience"] = float(patch["salience"])
    if "tags" in patch and isinstance(patch["tags"], list):
        changes["chat_content_tags"] = [str(t) for t in patch["tags"]]
    if "inherit_from" in patch and isinstance(patch["inherit_from"], list):
        changes["inherit_from"] = [str(i) for i in patch["inherit_from"]]
    if "participants" in patch and isinstance(patch["participants"], list):
        changes["participants"] = [str(p) for p in patch["participants"]]
    if "status" in patch and patch["status"] in (EventStatus.ACTIVE, EventStatus.ARCHIVED):
        changes["status"] = patch["status"]
    if "is_locked" in patch:
        changes["is_locked"] = bool(patch["is_locked"])
    updated = dataclasses.replace(event, **changes)
    await memory.update_event(updated)
    return event_to_dict(updated)


async def delete_event(
    memory: MemoryManager, event_id: str
) -> bool:
    return await memory.delete_event(event_id)


async def list_personas(persona_repo: PersonaRepository) -> list[dict[str, Any]]:
    personas = await persona_repo.list_all()
    return [persona_to_dict(p) for p in personas]


async def get_graph(
    persona_repo: PersonaRepository,
    impression_repo: ImpressionRepository,
) -> dict[str, Any]:
    """Return personas (nodes) + impressions (edges) in a flat serializable format."""
    personas = await persona_repo.list_all()
    nodes = [persona_to_dict(p) for p in personas]
    # One query for every impression, then walked in persona order so the edge
    # sequence matches what the per-persona loop produced.
    impressions = await impression_repo.list_all()
    by_observer: dict[str, list[Impression]] = {}
    for imp in impressions:
        by_observer.setdefault(imp.observer_uid, []).append(imp)
    edges: list[dict[str, Any]] = [
        impression_to_dict(imp)
        for persona in personas
        for imp in by_observer.get(persona.uid, ())
    ]
    return {"nodes": nodes, "edges": edges}


async def update_impression(
    impression_repo: ImpressionRepository,
    observer: str, subject: str, scope: str,
    patch: dict[str, Any],
) -> dict[str, Any] | None:
    existing = await impression_repo.get(observer, subject, scope)
    if existing is None:
        return None
    changes: dict[str, Any] = {}
    if "benevolence" in patch:
        changes["benevolence"] = max(-1.0, min(1.0, float(patch["benevolence"])))
    if "affect_intensity" in patch:
        changes["affect_intensity"] = max(0.0, min(1.0, float(patch["affect_intensity"])))
    if "confidence" in patch:
        changes["confidence"] = max(0.0, min(1.0, float(patch["confidence"])))
    if "evidence_event_ids" in patch and isinstance(patch["evidence_event_ids"], list):
        changes["evidence_event_ids"] = [str(e) for e in patch["evidence_event_ids"]]
    changes["last_reinforced_at"] = time.time()
    updated = dataclasses.replace(existing, **changes)
    await impression_repo.upsert(updated)
    return impression_to_dict(updated)


async def recall_preview(
    recall_manager: RecallManager,
    query: str,
    group_id: str | None = None,
) -> list[dict[str, Any]]:
    scope_mode = "group" if group_id is not None else "all"
    events = await recall_manager.recall(query, group_id=group_id, scope_mode=scope_mode)
    return [event_to_dict(e) for e in events]
