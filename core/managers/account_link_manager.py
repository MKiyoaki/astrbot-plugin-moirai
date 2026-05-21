"""Account binding service: link multiple per-platform Personas into one group.

Binding is a non-destructive overlay (see ``core/social/persona_group.py``):
no per-account data is moved, so unbinding is fully reversible. Every bind /
unbind / dissolve schedules a forced re-synthesis so the merged personality
reflects the new membership immediately.

Shared by the WebUI routes and the ``/mrm bind`` chat commands.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from typing import TYPE_CHECKING

from ..domain.models import PersonaGroup
from ..tasks.synthesis import run_persona_synthesis_for_uid, synthesize_persona_group

if TYPE_CHECKING:
    from ..config import SynthesisConfig
    from ..managers.llm_manager import LLMTaskManager
    from ..repository.base import (
        EventRepository,
        PersonaGroupRepository,
        PersonaRepository,
    )

logger = logging.getLogger(__name__)

_PAIRING_CODE_TTL_SECONDS = 300.0
_PAIRING_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class AccountLinkError(ValueError):
    """Raised for user-facing binding errors (bad input, conflicting state)."""


def _is_bot_persona(persona) -> bool:
    if getattr(persona, "bot_persona_name", None):
        return True
    return any(p == "internal" for p, _ in (persona.bound_identities or []))


class AccountLinkManager:
    def __init__(
        self,
        *,
        persona_repo: PersonaRepository,
        group_repo: PersonaGroupRepository,
        event_repo: EventRepository,
        provider_getter,
        synthesis_config: SynthesisConfig,
        llm_manager: LLMTaskManager | None = None,
    ) -> None:
        self._persona_repo = persona_repo
        self._group_repo = group_repo
        self._event_repo = event_repo
        self._provider_getter = provider_getter
        self._synthesis_config = synthesis_config
        self._llm_manager = llm_manager
        # pairing code → (uid, expires_at)
        self._pairing_codes: dict[str, tuple[str, float]] = {}

    # ------------------------------------------------------------------
    # Re-synthesis scheduling
    # ------------------------------------------------------------------

    def _schedule_group_synthesis(self, group_id: str) -> None:
        async def _run() -> None:
            try:
                await synthesize_persona_group(
                    self._persona_repo,
                    self._group_repo,
                    self._event_repo,
                    self._provider_getter,
                    group_id,
                    synthesis_config=self._synthesis_config,
                    llm_manager=self._llm_manager,
                )
            except Exception as exc:
                logger.warning("[AccountLink] group synthesis failed for %s: %s", group_id, exc)

        asyncio.create_task(_run())

    def _schedule_solo_synthesis(self, uids: list[str]) -> None:
        async def _run() -> None:
            for uid in uids:
                try:
                    await run_persona_synthesis_for_uid(
                        self._persona_repo,
                        self._event_repo,
                        self._provider_getter,
                        uid,
                        synthesis_config=self._synthesis_config,
                        llm_manager=self._llm_manager,
                        group_repo=self._group_repo,
                        force=True,
                    )
                except Exception as exc:
                    logger.warning("[AccountLink] solo synthesis failed for %s: %s", uid, exc)

        asyncio.create_task(_run())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _pick_primary_uid(self, uids: list[str]) -> str:
        counts = await self._event_repo.count_messages_by_uid_bulk()
        return max(uids, key=lambda u: int(counts.get(u, 0) or 0))

    async def _require_human_persona(self, uid: str):
        persona = await self._persona_repo.get(uid)
        if persona is None:
            raise AccountLinkError(f"未找到用户 {uid}")
        if _is_bot_persona(persona):
            raise AccountLinkError("不能绑定 Bot 人格账号")
        return persona

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    async def bind_accounts(
        self, uids: list[str], display_name: str | None = None
    ) -> PersonaGroup:
        """Bind two or more account uids under one group.

        Handles new-group creation and extending an existing group. Rejects
        binding accounts that already belong to two different groups.
        """
        unique = list(dict.fromkeys(u for u in uids if u))
        if len(unique) < 2:
            raise AccountLinkError("至少需要两个账号才能绑定")

        personas = [await self._require_human_persona(u) for u in unique]
        existing = {p.group_id for p in personas if p.group_id}
        if len(existing) >= 2:
            raise AccountLinkError("选中的账号已分属不同分组，请先解绑后再绑定")

        now = time.time()
        if existing:
            group_id = next(iter(existing))
            group = await self._group_repo.get_group(group_id)
            if group is None:
                raise AccountLinkError("目标分组不存在")
        else:
            group_id = str(uuid.uuid4())
            group = None

        for uid in unique:
            await self._group_repo.set_member_group(uid, group_id)

        members = await self._group_repo.list_member_uids(group_id)
        primary_uid = await self._pick_primary_uid(members)
        final_name = (
            (display_name or "").strip()
            or (group.display_name if group else "")
            or personas[0].primary_name
            or "绑定用户"
        )
        await self._group_repo.upsert_group(
            PersonaGroup(
                group_id=group_id,
                display_name=final_name,
                primary_uid=primary_uid,
                created_at=group.created_at if group else now,
                updated_at=now,
            )
        )
        self._schedule_group_synthesis(group_id)
        result = await self._group_repo.get_group(group_id)
        assert result is not None
        return result

    async def add_to_group(self, group_id: str, uid: str) -> PersonaGroup:
        """Add a single account to an existing group."""
        group = await self._group_repo.get_group(group_id)
        if group is None:
            raise AccountLinkError("分组不存在")
        persona = await self._require_human_persona(uid)
        if persona.group_id == group_id:
            return group
        if persona.group_id:
            raise AccountLinkError("该账号已绑定其它分组，请先解绑")

        await self._group_repo.set_member_group(uid, group_id)
        members = await self._group_repo.list_member_uids(group_id)
        primary_uid = await self._pick_primary_uid(members)
        await self._group_repo.upsert_group(
            PersonaGroup(
                group_id=group_id,
                display_name=group.display_name,
                primary_uid=primary_uid,
                created_at=group.created_at,
                updated_at=time.time(),
            )
        )
        self._schedule_group_synthesis(group_id)
        result = await self._group_repo.get_group(group_id)
        assert result is not None
        return result

    async def unbind(self, uid: str) -> None:
        """Remove one account from its group; dissolves the group if <2 remain."""
        persona = await self._persona_repo.get(uid)
        if persona is None:
            raise AccountLinkError(f"未找到用户 {uid}")
        if not persona.group_id:
            raise AccountLinkError("该账号未绑定任何分组")

        group_id = persona.group_id
        await self._group_repo.set_member_group(uid, None)
        remaining = await self._group_repo.list_member_uids(group_id)

        if len(remaining) <= 1:
            await self._group_repo.delete_group(group_id)
            self._schedule_solo_synthesis(remaining + [uid])
            return

        group = await self._group_repo.get_group(group_id)
        if group is not None:
            primary = group.primary_uid
            if primary == uid:
                primary = await self._pick_primary_uid(remaining)
            await self._group_repo.upsert_group(
                PersonaGroup(
                    group_id=group_id,
                    display_name=group.display_name,
                    primary_uid=primary,
                    created_at=group.created_at,
                    updated_at=time.time(),
                )
            )
        self._schedule_group_synthesis(group_id)
        self._schedule_solo_synthesis([uid])

    async def dissolve(self, group_id: str) -> None:
        """Disband a group entirely; every former member reverts to solo."""
        members = await self._group_repo.list_member_uids(group_id)
        if not await self._group_repo.delete_group(group_id):
            raise AccountLinkError("分组不存在")
        if members:
            self._schedule_solo_synthesis(members)

    async def rename(self, group_id: str, display_name: str) -> PersonaGroup:
        group = await self._group_repo.get_group(group_id)
        if group is None:
            raise AccountLinkError("分组不存在")
        name = (display_name or "").strip()
        if not name:
            raise AccountLinkError("分组名称不能为空")
        await self._group_repo.upsert_group(
            PersonaGroup(
                group_id=group_id,
                display_name=name,
                primary_uid=group.primary_uid,
                created_at=group.created_at,
                updated_at=time.time(),
            )
        )
        result = await self._group_repo.get_group(group_id)
        assert result is not None
        return result

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    async def list_groups(self) -> list[dict]:
        """Return all groups with their members for the WebUI."""
        groups = await self._group_repo.list_groups()
        out: list[dict] = []
        for group in groups:
            member_uids = await self._group_repo.list_member_uids(group.group_id)
            members = []
            for uid in member_uids:
                persona = await self._persona_repo.get(uid)
                if persona is None:
                    continue
                members.append({
                    "uid": uid,
                    "primary_name": persona.primary_name,
                    "bound_identities": [
                        {"platform": p, "physical_id": pid}
                        for p, pid in persona.bound_identities
                    ],
                })
            out.append({
                "group_id": group.group_id,
                "display_name": group.display_name,
                "primary_uid": group.primary_uid,
                "created_at": group.created_at,
                "updated_at": group.updated_at,
                "members": members,
            })
        return out

    async def list_human_personas(self) -> list[dict]:
        """Return non-bot personas as binding candidates."""
        personas = await self._persona_repo.list_all()
        counts = await self._event_repo.count_messages_by_uid_bulk()
        out: list[dict] = []
        for persona in personas:
            if _is_bot_persona(persona):
                continue
            out.append({
                "uid": persona.uid,
                "primary_name": persona.primary_name,
                "group_id": persona.group_id,
                "msg_count": int(counts.get(persona.uid, 0) or 0),
                "bound_identities": [
                    {"platform": p, "physical_id": pid}
                    for p, pid in persona.bound_identities
                ],
            })
        return out

    # ------------------------------------------------------------------
    # Chat pairing codes
    # ------------------------------------------------------------------

    def _purge_expired_codes(self) -> None:
        now = time.time()
        expired = [c for c, (_, exp) in self._pairing_codes.items() if exp < now]
        for code in expired:
            self._pairing_codes.pop(code, None)

    def generate_pairing_code(self, uid: str) -> str:
        """Issue a short-lived pairing code for ``uid`` (the issuing account)."""
        self._purge_expired_codes()
        # Drop any prior code from the same uid so only the latest is valid.
        for code, (owner, _) in list(self._pairing_codes.items()):
            if owner == uid:
                self._pairing_codes.pop(code, None)
        code = "".join(secrets.choice(_PAIRING_CODE_ALPHABET) for _ in range(6))
        self._pairing_codes[code] = (uid, time.time() + _PAIRING_CODE_TTL_SECONDS)
        return code

    async def redeem_pairing_code(self, code: str, current_uid: str) -> PersonaGroup:
        """Consume a pairing code and bind the issuer to ``current_uid``."""
        self._purge_expired_codes()
        entry = self._pairing_codes.get(code.strip().upper())
        if entry is None:
            raise AccountLinkError("配对码无效或已过期")
        issuer_uid, _ = entry
        if issuer_uid == current_uid:
            raise AccountLinkError("不能与自己绑定")
        self._pairing_codes.pop(code.strip().upper(), None)
        return await self.bind_accounts([issuer_uid, current_uid])
