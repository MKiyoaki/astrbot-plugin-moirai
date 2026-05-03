"""DB → Markdown read-only projector.

Renders Jinja2 templates from current repository state and writes them to
the data_dir layout defined in CLAUDE.md:

    data_dir/
    ├── personas/<uid>/
    │   ├── PROFILE.md       (read-only projection)
    │   └── IMPRESSIONS.md   (user-editable; Phase 10 syncs back)
    └── global/
        └── BOT_PERSONA.md   (read-only projection)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..repository.base import EventRepository, ImpressionRepository, PersonaRepository

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _format_time(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _format_affect(value: float) -> str:
    if value >= 0.6:
        return f"正面（{value:+.2f}）"
    if value <= -0.6:
        return f"负面（{value:+.2f}）"
    return f"中性（{value:+.2f}）"


class MarkdownProjector:
    """Renders repo data into Markdown files under data_dir.

    The database is always the source of truth; these files are projections.
    IMPRESSIONS.md is the exception — users may edit it, and Phase 10 will
    sync those edits back to the database.
    """

    def __init__(
        self,
        data_dir: Path,
        persona_repo: PersonaRepository,
        event_repo: EventRepository,
        impression_repo: ImpressionRepository,
    ) -> None:
        self._data_dir = data_dir
        self._persona_repo = persona_repo
        self._event_repo = event_repo
        self._impression_repo = impression_repo
        self._env = self._build_env()

    def _build_env(self) -> Environment:
        env = Environment(
            loader=FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        env.filters["format_time"] = _format_time
        env.filters["format_affect"] = _format_affect
        return env

    def _render(self, template_name: str, **ctx: object) -> str:
        return self._env.get_template(template_name).render(**ctx)

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    async def render_persona(self, uid: str) -> bool:
        """Render PROFILE.md and IMPRESSIONS.md for one persona.

        Returns False if the persona does not exist in the repository.
        """
        persona = await self._persona_repo.get(uid)
        if persona is None:
            logger.warning("[Projector] persona %s not found", uid)
            return False

        events = await self._event_repo.list_by_participant(uid, limit=10)
        impressions = await self._impression_repo.list_by_subject(uid)

        persona_dir = self._data_dir / "personas" / uid
        self._write(
            persona_dir / "PROFILE.md",
            self._render("persona_profile.md.j2", persona=persona, events=events),
        )
        self._write(
            persona_dir / "IMPRESSIONS.md",
            self._render("persona_impressions.md.j2", persona=persona, impressions=impressions),
        )
        logger.debug("[Projector] rendered persona %s (%s)", uid, persona.primary_name)
        return True

    async def render_all_personas(self) -> int:
        """Render markdown for every persona. Returns count successfully rendered."""
        personas = await self._persona_repo.list_all()
        count = 0
        for persona in personas:
            if await self.render_persona(persona.uid):
                count += 1
        return count

    async def render_bot_persona(self, bot_uid: str) -> bool:
        """Render global/BOT_PERSONA.md for the bot's own persona.

        Returns False if the bot persona is not found.
        """
        persona = await self._persona_repo.get(bot_uid)
        if persona is None:
            logger.warning("[Projector] bot persona %s not found", bot_uid)
            return False

        self._write(
            self._data_dir / "global" / "BOT_PERSONA.md",
            self._render("bot_persona.md.j2", persona=persona),
        )
        logger.debug("[Projector] rendered BOT_PERSONA.md")
        return True
