"""Identity resolution: (platform, physical_id) → stable internal uid.

A new Persona is created on first encounter. Subsequent calls with the same
(platform, physical_id) pair return the existing uid without writing to the DB.
"""
from __future__ import annotations

import dataclasses
import re
import time
import uuid

from ..domain.models import Persona
from ..repository.base import PersonaRepository

# Matches pure numeric strings (e.g. QQ IDs like "1257116920")
_NUMERIC_ID_RE = re.compile(r'^\d+$')


class IdentityResolver:
    def __init__(self, persona_repo: PersonaRepository, default_confidence: float = 0.5) -> None:
        self._repo = persona_repo
        self._default_confidence = default_confidence
        # (platform, physical_id) → uid; avoids one DB round-trip per message
        self._cache: dict[tuple[str, str], str] = {}

    async def get_or_create_uid(
        self, platform: str, physical_id: str, display_name: str
    ) -> str:
        """Return stable uid for (platform, physical_id), creating a Persona if new."""
        key = (platform, physical_id)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        persona = await self._repo.get_by_identity(platform, physical_id)
        if persona is not None:
            self._cache[key] = persona.uid
            # If the stored name is a raw numeric ID and a real display_name is now available, update it.
            if (
                display_name
                and display_name != persona.primary_name
                and _NUMERIC_ID_RE.match(persona.primary_name)
                and not _NUMERIC_ID_RE.match(display_name)
            ):
                await self._repo.upsert(dataclasses.replace(persona, primary_name=display_name))
            return persona.uid

        now = time.time()
        uid = str(uuid.uuid4())
        await self._repo.upsert(
            Persona(
                uid=uid,
                bound_identities=[(platform, physical_id)],
                primary_name=display_name or "User",
                persona_attrs={},
                confidence=self._default_confidence,
                created_at=now,
                last_active_at=now,
            )
        )
        self._cache[key] = uid
        return uid

    async def touch_last_active(self, uid: str) -> None:
        """Update last_active_at for an existing Persona."""
        persona = await self._repo.get(uid)
        if persona is None:
            return
        await self._repo.upsert(
            dataclasses.replace(persona, last_active_at=time.time())
        )
