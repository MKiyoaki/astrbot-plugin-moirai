"""Identity resolution: (platform, physical_id) → stable internal uid.

A new Persona is created on first encounter. Subsequent calls with the same
(platform, physical_id) pair return the existing uid without writing to the DB.
"""
from __future__ import annotations

import dataclasses
import time
import uuid

from ..domain.models import Persona
from ..repository.base import PersonaRepository


class IdentityResolver:
    def __init__(self, persona_repo: PersonaRepository) -> None:
        self._repo = persona_repo
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
            return persona.uid

        now = time.time()
        uid = str(uuid.uuid4())
        await self._repo.upsert(
            Persona(
                uid=uid,
                bound_identities=[(platform, physical_id)],
                primary_name=display_name or "User",
                persona_attrs={},
                confidence=0.5,
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
