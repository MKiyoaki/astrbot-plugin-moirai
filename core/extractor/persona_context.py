"""Bot persona context helpers for event extraction."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..repository.base import PersonaRepository

logger = logging.getLogger(__name__)


def _is_internal_bound(persona) -> bool:
    return any(
        (bi[0] if isinstance(bi, tuple) else getattr(bi, "platform", None)) == "internal"
        for bi in (persona.bound_identities or [])
    )


async def resolve_bot_persona_context(
    persona_repo: PersonaRepository | None,
    enabled: bool,
) -> tuple[str | None, str | None]:
    """Return (primary_name, prompt_description) for the internal bot persona.

    This is a *prompt-description* helper only — it must not be used as the
    source of an Event's ``bot_persona_name`` bucket key. When several internal
    bot personas exist the choice is made deterministically (most recently
    active) instead of picking an arbitrary first match, and the ambiguity is
    logged so stray personas can be merged.
    """
    if not enabled or persona_repo is None:
        return None, None

    personas = await persona_repo.list_all()
    internal = [p for p in personas if _is_internal_bound(p)]
    if not internal:
        return None, None

    if len(internal) > 1:
        # Deterministic: most recently active wins. Arbitrary ordering here is
        # exactly what caused personas to be filed under the wrong bucket.
        internal.sort(
            key=lambda p: (getattr(p, "last_active_at", 0.0) or 0.0,
                           (p.primary_name or "")),
            reverse=True,
        )
        logger.warning(
            "[persona_context] %d internal bot personas found (%s); using "
            "most-recently-active %r. Consider merging via WebUI Persona Ownership.",
            len(internal),
            ", ".join(repr(p.primary_name) for p in internal),
            internal[0].primary_name,
        )

    bot = internal[0]
    desc = ""
    if isinstance(bot.persona_attrs, dict):
        desc = str(bot.persona_attrs.get("description") or "").strip()
    name = (bot.primary_name or "").strip() or None
    return name, desc or name
