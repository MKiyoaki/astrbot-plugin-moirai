"""Persona-group overlay helpers.

Account binding is a non-destructive overlay: each platform account keeps its
own Persona/uid and raw data. These helpers expand a single uid into all uids
bound to the same group and aggregate their events, so personality synthesis
and recall can treat a bound group as one logical user without moving data.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..domain.models import Event
    from ..repository.base import (
        EventRepository,
        PersonaGroupRepository,
        PersonaRepository,
    )


async def expand_uids(
    persona_repo: PersonaRepository,
    group_repo: PersonaGroupRepository,
    uid: str,
) -> list[str]:
    """Return every uid bound to the same group as ``uid``.

    Returns ``[uid]`` when the persona is missing or not bound to any group.
    The result always contains ``uid`` itself.
    """
    persona = await persona_repo.get(uid)
    if persona is None or not persona.group_id:
        return [uid]
    members = await group_repo.list_member_uids(persona.group_id)
    if uid not in members:
        members.append(uid)
    return members


async def aggregate_events(
    event_repo: EventRepository,
    uids: list[str],
    limit: int,
) -> list[Event]:
    """Union the participant events of every uid, deduped and newest-first.

    Used to feed a bound group's combined history into persona synthesis.
    """
    by_id: dict[str, Event] = {}
    for uid in uids:
        for event in await event_repo.list_by_participant(uid, limit=limit):
            by_id.setdefault(event.event_id, event)
    merged = sorted(by_id.values(), key=lambda e: e.start_time, reverse=True)
    return merged[:limit]
