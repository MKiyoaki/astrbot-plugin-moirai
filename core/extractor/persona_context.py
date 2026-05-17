"""Bot persona context helpers for event extraction."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..repository.base import PersonaRepository


async def resolve_bot_persona_context(
    persona_repo: PersonaRepository | None,
    enabled: bool,
) -> tuple[str | None, str | None]:
    """Return (primary_name, prompt_description) for the internal bot persona."""
    if not enabled or persona_repo is None:
        return None, None

    personas = await persona_repo.list_all()
    bot = next(
        (
            p for p in personas
            if any(
                (bi[0] if isinstance(bi, tuple) else getattr(bi, "platform", None)) == "internal"
                for bi in (p.bound_identities or [])
            )
        ),
        None,
    )
    if bot is None:
        return None, None

    desc = ""
    if isinstance(bot.persona_attrs, dict):
        desc = str(bot.persona_attrs.get("description") or "").strip()
    name = (bot.primary_name or "").strip() or None
    return name, desc or name
