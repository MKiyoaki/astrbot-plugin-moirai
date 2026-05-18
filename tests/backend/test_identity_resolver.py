"""Tests for IdentityResolver: uid stability and in-memory cache."""
from __future__ import annotations

import pytest
from core.adapters.identity import IdentityResolver
from core.repository.memory import InMemoryPersonaRepository


class _CountingPersonaRepo(InMemoryPersonaRepository):
    """Wraps InMemoryPersonaRepository and counts get_by_identity calls."""

    def __init__(self) -> None:
        super().__init__()
        self.get_by_identity_calls: int = 0

    async def get_by_identity(self, platform: str, physical_id: str):
        self.get_by_identity_calls += 1
        return await super().get_by_identity(platform, physical_id)


async def test_same_user_returns_same_uid() -> None:
    repo = _CountingPersonaRepo()
    resolver = IdentityResolver(repo)
    uid1 = await resolver.get_or_create_uid("qq", "u1", "Alice")
    uid2 = await resolver.get_or_create_uid("qq", "u1", "Alice")
    assert uid1 == uid2


async def test_different_platform_gives_different_uid() -> None:
    repo = _CountingPersonaRepo()
    resolver = IdentityResolver(repo)
    uid_qq = await resolver.get_or_create_uid("qq", "u1", "Alice")
    uid_tg = await resolver.get_or_create_uid("telegram", "u1", "Alice")
    assert uid_qq != uid_tg


# ---------------------------------------------------------------------------
# P1-1: In-memory cache should eliminate redundant DB lookups for known users
# ---------------------------------------------------------------------------

async def test_known_user_skips_db_after_first_call() -> None:
    """After the first lookup, subsequent calls for the same identity
    must NOT hit get_by_identity again (cache hit)."""
    repo = _CountingPersonaRepo()
    resolver = IdentityResolver(repo)

    await resolver.get_or_create_uid("qq", "u1", "Alice")  # first — DB hit
    calls_after_first = repo.get_by_identity_calls

    await resolver.get_or_create_uid("qq", "u1", "Alice")  # second — cache
    await resolver.get_or_create_uid("qq", "u1", "Alice")  # third — cache

    # No additional DB calls after the first lookup
    assert repo.get_by_identity_calls == calls_after_first


async def test_new_user_always_hits_db() -> None:
    """Unknown identities must always go to the DB."""
    repo = _CountingPersonaRepo()
    resolver = IdentityResolver(repo)

    await resolver.get_or_create_uid("qq", "u1", "Alice")
    await resolver.get_or_create_uid("qq", "u2", "Bob")

    # Two distinct users → at least 2 DB calls
    assert repo.get_by_identity_calls >= 2


async def test_cache_isolated_per_resolver_instance() -> None:
    """Different resolver instances do not share cache."""
    repo = _CountingPersonaRepo()
    r1 = IdentityResolver(repo)
    r2 = IdentityResolver(repo)

    await r1.get_or_create_uid("qq", "u1", "Alice")
    calls_after_r1 = repo.get_by_identity_calls

    # r2 has its own empty cache → must hit DB
    await r2.get_or_create_uid("qq", "u1", "Alice")
    assert repo.get_by_identity_calls > calls_after_r1
