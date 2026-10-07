"""SQLite storage for persona/person commitments and extraction-bound settlement."""
from __future__ import annotations

import json
import uuid

from .sqlite import _get_db_lock, _txn


# ---------------------------------------------------------------------------
# 承诺不进入事实摘要；同一原始回复的同一项只写一次；
# 同一人格对同一个人在同一范围内已有相同文字的未完成约定时不再重复写
# ---------------------------------------------------------------------------

class SQLiteCommitmentRepository:
    def __init__(self, db) -> None:
        self._db = db
        self._lock = _get_db_lock(db)

    async def add(self, *, persona: str, person_uid: str, session_id: str, group_id: str | None,
                  source_message_id: str, created_at: float, texts: list[str]) -> None:
        rows = [(str(uuid.uuid5(uuid.NAMESPACE_URL, f"moirai:{source_message_id}:{index}")),
                 persona, person_uid, session_id, group_id, text.strip(), source_message_id, created_at,
                 persona, person_uid, group_id, text.strip())
                for index, text in enumerate(texts) if text.strip()]
        if not rows:
            return
        async with _txn(self._db, self._lock):
            await self._db.executemany(
                "INSERT OR IGNORE INTO commitments(commitment_id, bot_persona_name, person_uid, "
                "session_id, group_id, text, source_message_id, created_at) SELECT ?,?,?,?,?,?,?,? "
                "WHERE NOT EXISTS (SELECT 1 FROM commitments WHERE bot_persona_name = ? "
                "AND person_uid = ? AND group_id IS ? AND text = ? AND status = 'open')", rows)

    async def list_open(self, persona: str, person_uids: list[str], group_id: str | None,
                        before: float | None = None) -> list[dict]:
        if not persona or not person_uids:
            return []
        async with self._db.execute(
            "SELECT * FROM commitments WHERE bot_persona_name = ? AND status = 'open' "
            "AND person_uid IN (SELECT value FROM json_each(?)) AND group_id IS ? "
            "AND (? IS NULL OR created_at <= ?) ORDER BY created_at, commitment_id",
            (persona, json.dumps(person_uids), group_id, before, before),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]

    async def close(self, resolutions: list[dict], *, allowed_ids: list[str], event_id: str, now: float) -> None:
        allowed = set(allowed_ids)
        rows = [(item["status"], now, event_id, item["id"])
                for item in resolutions if item["id"] in allowed and item["status"] in {"done", "dropped"}]
        if rows:
            async with _txn(self._db, self._lock):
                await self._db.executemany(
                    "UPDATE commitments SET status = ?, closed_at = ?, closing_event_id = ? "
                    "WHERE commitment_id = ? AND status = 'open'", rows)
