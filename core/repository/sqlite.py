"""SQLite repository implementations using aiosqlite.

Each repository class takes an open aiosqlite.Connection. Connection setup
(WAL mode, PRAGMA tuning, extension loading) is handled by db_open() in this
module. Use db_open() as an async context manager in production code.

JSON serialization strategy
----------------------------
SQLite stores list/dict fields as JSON text. All serialisation is done at the
repository boundary; the domain model layer is never aware of it.

MessageRef special case: serialised as {"sender_uid":…, "timestamp":…, …}.
list[tuple[str,str]] (bound_identities): serialised as [[p, id], …].

sqlite-vec
----------
db_open() tries to load the sqlite-vec extension and create the events_vec
virtual table. If the extension is unavailable, vector operations silently
no-op — BM25 search still works.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import shutil
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from ..domain.models import Event, EventStatus, EventType, Impression, MessageRef, Persona
from .base import EventRepository, ImpressionRepository, PersonaRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------

_PRAGMAS = [
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
    "PRAGMA cache_size=-64000",  # 64 MB page cache
    "PRAGMA foreign_keys=ON",
]


def _get_db_lock(db: aiosqlite.Connection) -> asyncio.Lock:
    """Return the asyncio.Lock attached to this connection, creating it on first use.

    aiosqlite serializes execution on a single worker thread but transactions
    are connection-scoped state. Without this lock, two coroutines awaiting
    db.execute("BEGIN IMMEDIATE") on the same connection race each other and
    one of them hits "cannot start a transaction within a transaction".
    """
    lock = getattr(db, "_em_txn_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        db._em_txn_lock = lock
    return lock


@asynccontextmanager
async def _txn(db: aiosqlite.Connection, lock: asyncio.Lock) -> AsyncIterator[None]:
    """Serialized BEGIN IMMEDIATE … COMMIT block."""
    async with lock:
        await db.execute("BEGIN IMMEDIATE")
        try:
            yield
            await db.commit()
        except Exception:
            await db.rollback()
            raise


async def preview_bot_persona_merge(
    db: aiosqlite.Connection, src: str, target: str,
) -> dict[str, int]:
    """Return the row counts that would be moved/dropped by a src→target merge.

    impressions_dropped counts rows that share an (observer, subject, scope)
    tuple with an existing target row — those rows are deleted during merge
    because the (observer, subject, scope, ifnull(bot_persona_name, '')) unique
    index would otherwise be violated. "target wins" policy.
    """
    async with db.execute(
        "SELECT COUNT(*) FROM events WHERE bot_persona_name = ?", (src,)
    ) as cur:
        events_n = (await cur.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM impressions WHERE bot_persona_name = ?", (src,)
    ) as cur:
        imps_total = (await cur.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM impressions s WHERE s.bot_persona_name = ? "
        "AND EXISTS (SELECT 1 FROM impressions t "
        "WHERE t.observer_uid = s.observer_uid "
        "AND t.subject_uid = s.subject_uid "
        "AND t.scope = s.scope "
        "AND ifnull(t.bot_persona_name, '') = ifnull(?, ''))",
        (src, target),
    ) as cur:
        imps_conflicts = (await cur.fetchone())[0]
    async with db.execute(
        "SELECT COUNT(*) FROM personas WHERE bot_persona_name = ?", (src,)
    ) as cur:
        personas_n = (await cur.fetchone())[0]
    return {
        "events_moved": events_n,
        "impressions_moved": imps_total - imps_conflicts,
        "impressions_dropped": imps_conflicts,
        "personas_moved": personas_n,
    }


async def merge_bot_persona(
    db: aiosqlite.Connection, src: str, target: str,
) -> dict[str, int]:
    """Re-assign every row owned by bot persona `src` to `target` atomically.

    Returns the same shape as preview_bot_persona_merge(), measured after the
    transaction commits. "target wins" — src impressions that collide with an
    existing target row on (observer, subject, scope) are deleted.
    """
    counts = await preview_bot_persona_merge(db, src, target)
    lock = _get_db_lock(db)
    async with _txn(db, lock):
        # 1. Drop src impressions that conflict with target on (obs, subj, scope)
        await db.execute(
            "DELETE FROM impressions WHERE bot_persona_name = ? "
            "AND EXISTS (SELECT 1 FROM impressions t "
            "WHERE t.observer_uid = impressions.observer_uid "
            "AND t.subject_uid = impressions.subject_uid "
            "AND t.scope = impressions.scope "
            "AND ifnull(t.bot_persona_name, '') = ifnull(?, ''))",
            (src, target),
        )
        # 2. Re-key remaining src impressions to target
        await db.execute(
            "UPDATE impressions SET bot_persona_name = ? WHERE bot_persona_name = ?",
            (target, src),
        )
        # 3. Re-key events (event_id PK guarantees no conflicts)
        await db.execute(
            "UPDATE events SET bot_persona_name = ? WHERE bot_persona_name = ?",
            (target, src),
        )
        # 4. Re-key personas (uid PK; bot_persona_name here is just a tag)
        await db.execute(
            "UPDATE personas SET bot_persona_name = ? WHERE bot_persona_name = ?",
            (target, src),
        )
    return counts


async def _try_load_sqlite_vec(db: aiosqlite.Connection, dim: int = 512) -> bool:
    """Load the sqlite-vec extension and create virtual tables.

    Returns True on success, False if the extension is not installed.
    Safe to call on every startup — uses IF NOT EXISTS.
    """
    try:
        import sqlite_vec  # noqa: PLC0415

        await db.enable_load_extension(True)
        await db.load_extension(sqlite_vec.loadable_path())
        await db.enable_load_extension(False)  # re-disable for safety
        await db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS events_vec USING vec0(embedding float[{dim}])"
        )
        await db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS tags_vec USING vec0(embedding float[{dim}])"
        )
        await db.commit()
        return True
    except Exception as exc:
        logger.debug("[db_open] sqlite-vec not available: %s", exc)
        return False


@asynccontextmanager
async def db_open(
    path: Path | str, vec_dim: int = 512, migration_auto_backup: bool = True,
) -> AsyncIterator[aiosqlite.Connection]:
    """Open a tuned SQLite connection, run migrations, and load sqlite-vec.

    Usage::

        async with db_open(data_dir / "core.db") as db:
            repo = SQLiteEventRepository(db)
            ...

    vec_dim: embedding dimension for the events_vec virtual table.
    Must match the dimension of the Encoder used in production.
    migration_auto_backup: if True, copy the DB to <name>.db.bak before applying migrations.
    """
    from migrations.runner import run_migrations  # avoid circular import at module level

    db_path = Path(path)
    if migration_auto_backup and db_path.exists():
        try:
            shutil.copy(db_path, db_path.with_suffix(".db.bak"))
            logger.debug("[db_open] backed up %s → %s.bak", db_path.name, db_path.name)
        except Exception as exc:
            logger.warning("[db_open] auto-backup failed (continuing): %s", exc)

    async with aiosqlite.connect(str(path)) as db:
        db.row_factory = aiosqlite.Row
        for pragma in _PRAGMAS:
            await db.execute(pragma)
        await db.commit()
        await run_migrations(db)
        await _try_load_sqlite_vec(db, vec_dim)
        yield db


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _j(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_message_refs(raw: str) -> list[MessageRef]:
    return [MessageRef(**item) for item in json.loads(raw)]


def _dump_message_refs(refs: list[MessageRef]) -> str:
    return json.dumps(
        [
            {
                "sender_uid": r.sender_uid,
                "timestamp": r.timestamp,
                "content_hash": r.content_hash,
                "content_preview": r.content_preview,
            }
            for r in refs
        ],
        ensure_ascii=False,
    )


def _row_to_event(row: aiosqlite.Row) -> Event:
    keys = row.keys()
    status = row["status"] if "status" in keys else EventStatus.ACTIVE
    is_locked = bool(row["is_locked"]) if "is_locked" in keys else False
    summary = row["summary"] if "summary" in keys else ""
    bot_persona_name = row["bot_persona_name"] if "bot_persona_name" in keys else None
    event_type = row["event_type"] if "event_type" in keys else EventType.EPISODE
    return Event(
        event_id=row["event_id"],
        group_id=row["group_id"],
        start_time=row["start_time"],
        end_time=row["end_time"],
        participants=json.loads(row["participants"]),
        interaction_flow=_load_message_refs(row["interaction_flow"]),
        topic=row["topic"],
        summary=summary,
        chat_content_tags=json.loads(row["chat_content_tags"]),
        salience=row["salience"],
        confidence=row["confidence"],
        inherit_from=json.loads(row["inherit_from"]),
        last_accessed_at=row["last_accessed_at"],
        status=status,
        is_locked=is_locked,
        bot_persona_name=bot_persona_name,
        event_type=event_type,
    )


def _row_to_persona(row: aiosqlite.Row) -> Persona:
    raw_ids = json.loads(row["bound_identities"] or "[]")
    return Persona(
        uid=row["uid"],
        bound_identities=[(item[0], item[1]) for item in raw_ids],
        primary_name=row["primary_name"],
        persona_attrs=json.loads(row["persona_attrs"] or "{}"),
        confidence=row["confidence"],
        created_at=row["created_at"],
        last_active_at=row["last_active_at"],
        bot_persona_name=_safe_get(row, "bot_persona_name"),
    )


def _row_to_impression(row: aiosqlite.Row) -> Impression:
    return Impression(
        observer_uid=row["observer_uid"],
        subject_uid=row["subject_uid"],
        ipc_orientation=row["ipc_orientation"],
        benevolence=row["benevolence"],
        power=row["power"],
        affect_intensity=row["affect_intensity"],
        r_squared=row["r_squared"],
        confidence=row["confidence"],
        scope=row["scope"],
        evidence_event_ids=json.loads(row["evidence_event_ids"] or "[]"),
        last_reinforced_at=row["last_reinforced_at"],
        bot_persona_name=_safe_get(row, "bot_persona_name"),
    )


def _safe_get(row: aiosqlite.Row, key: str) -> Any:
    """Read a column that may be absent (e.g. older row factories or VIEW joins)."""
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def _persona_where(
    bot_persona_name: str | None, include_legacy: bool,
) -> tuple[str, list[Any]]:
    """Build the WHERE fragment that scopes a row set to one bot persona.

    None means "no filter — return everything". A non-None value yields rows
    matching that persona; when include_legacy is True, rows with NULL
    bot_persona_name are also surfaced so old data stays visible.
    """
    if bot_persona_name is None:
        return "", []
    if bot_persona_name == "":
        return "bot_persona_name IS NULL", []
    if include_legacy:
        return "(bot_persona_name = ? OR bot_persona_name IS NULL)", [bot_persona_name]
    return "bot_persona_name = ?", [bot_persona_name]


# ---------------------------------------------------------------------------
# PersonaRepository
# ---------------------------------------------------------------------------

class SQLitePersonaRepository(PersonaRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._lock = _get_db_lock(db)

    async def get(self, uid: str) -> Persona | None:
        # Fetch persona row + all bound identities in one query
        async with self._db.execute(
            "SELECT p.*, "
            "(SELECT json_group_array(json_array(ib.platform, ib.physical_id)) "
            " FROM identity_bindings ib WHERE ib.uid = p.uid) AS bound_identities "
            "FROM personas p WHERE p.uid = ?",
            (uid,),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_persona(row) if row else None

    async def get_by_identity(self, platform: str, physical_id: str) -> Persona | None:
        async with self._db.execute(
            "SELECT uid FROM identity_bindings WHERE platform = ? AND physical_id = ?",
            (platform, physical_id),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return await self.get(row["uid"])

    async def list_all(self) -> list[Persona]:
        async with self._db.execute(
            "SELECT p.*, "
            "(SELECT json_group_array(json_array(ib.platform, ib.physical_id)) "
            " FROM identity_bindings ib WHERE ib.uid = p.uid) AS bound_identities "
            "FROM personas p ORDER BY p.last_active_at DESC"
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_persona(r) for r in rows]

    async def upsert(self, persona: Persona) -> None:
        async with _txn(self._db, self._lock):
            await self._db.execute(
                "INSERT INTO personas(uid, primary_name, persona_attrs, confidence, "
                "created_at, last_active_at, bot_persona_name) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(uid) DO UPDATE SET "
                "primary_name=excluded.primary_name, "
                "persona_attrs=excluded.persona_attrs, "
                "confidence=excluded.confidence, "
                "last_active_at=excluded.last_active_at, "
                "bot_persona_name=excluded.bot_persona_name",
                (
                    persona.uid,
                    persona.primary_name,
                    _j(persona.persona_attrs),
                    persona.confidence,
                    persona.created_at,
                    persona.last_active_at,
                    persona.bot_persona_name,
                ),
            )
            # Replace all bindings for this uid atomically
            await self._db.execute(
                "DELETE FROM identity_bindings WHERE uid = ?", (persona.uid,)
            )
            for platform, physical_id in persona.bound_identities:
                await self._db.execute(
                    "INSERT OR REPLACE INTO identity_bindings(platform, physical_id, uid) "
                    "VALUES (?,?,?)",
                    (platform, physical_id, persona.uid),
                )

    async def delete(self, uid: str) -> bool:
        async with self._db.execute(
            "SELECT 1 FROM personas WHERE uid = ?", (uid,)
        ) as cur:
            if await cur.fetchone() is None:
                return False
        async with _txn(self._db, self._lock):
            await self._db.execute("DELETE FROM personas WHERE uid = ?", (uid,))
        return True

    async def bind_identity(self, uid: str, platform: str, physical_id: str) -> None:
        async with _txn(self._db, self._lock):
            await self._db.execute(
                "INSERT OR REPLACE INTO identity_bindings(platform, physical_id, uid) "
                "VALUES (?,?,?)",
                (platform, physical_id, uid),
            )


# ---------------------------------------------------------------------------
# EventRepository
# ---------------------------------------------------------------------------

_EVENT_COLS = (
    "event_id, group_id, start_time, end_time, participants, "
    "interaction_flow, topic, summary, chat_content_tags, salience, confidence, "
    "inherit_from, last_accessed_at, status, is_locked, bot_persona_name, event_type"
)

_EVENT_SELECT_COLS = (
    "e.event_id, e.group_id, e.start_time, e.end_time, e.participants, "
    "e.interaction_flow, e.topic, e.summary, e.chat_content_tags, e.salience, e.confidence, "
    "e.inherit_from, e.last_accessed_at, e.status, e.is_locked, e.event_type"
)

_EVENT_SELECT = f"SELECT {_EVENT_COLS} FROM events"


class SQLiteEventRepository(EventRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._lock = _get_db_lock(db)

    async def get(self, event_id: str) -> Event | None:
        async with self._db.execute(
            f"{_EVENT_SELECT} WHERE event_id = ?", (event_id,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_event(row) if row else None

    async def list_all(
        self, limit: int = 100,
        bot_persona_name: str | None = None, include_legacy: bool = True,
    ) -> list[Event]:
        where, params = _persona_where(bot_persona_name, include_legacy)
        sql = f"{_EVENT_SELECT}"
        if where:
            sql += " WHERE " + where
        sql += " ORDER BY start_time DESC LIMIT ?"
        async with self._db.execute(sql, tuple(params + [limit])) as cur:
            rows = await cur.fetchall()
        return [_row_to_event(r) for r in rows]

    async def list_by_group(
        self, group_id: str | None, limit: int = 100,
        exclude_type: str | None = None,
        bot_persona_name: str | None = None, include_legacy: bool = True,
    ) -> list[Event]:
        # IS ? correctly handles NULL comparison (group_id IS NULL)
        clauses = ["group_id IS ?"]
        params: list[Any] = [group_id]
        if exclude_type:
            clauses.append("event_type != ?")
            params.append(exclude_type)
        persona_where, persona_params = _persona_where(bot_persona_name, include_legacy)
        if persona_where:
            clauses.append(persona_where)
            params.extend(persona_params)
        sql = f"{_EVENT_SELECT} WHERE " + " AND ".join(clauses) + " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [_row_to_event(r) for r in rows]

    async def list_by_participant(self, uid: str, limit: int = 100) -> list[Event]:
        async with self._db.execute(
            f"{_EVENT_SELECT} e WHERE EXISTS ("
            "  SELECT 1 FROM json_each(e.participants) WHERE value = ?"
            ") ORDER BY e.start_time DESC LIMIT ?",
            (uid, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_event(r) for r in rows]

    async def list_group_ids(self) -> list[str | None]:
        async with self._db.execute("SELECT DISTINCT group_id FROM events") as cur:
            rows = await cur.fetchall()
        return [row[0] for row in rows]

    async def search_fts(
        self, query: str, limit: int = 20, active_only: bool = True,
        group_id: str | None = None, event_type: str | None = None,
    ) -> list[Event]:
        """BM25 full-text search over topic and chat_content_tags.

        group_id=None searches across all groups; pass a value to restrict to one scope.
        event_type filters by 'episode' or 'narrative' when specified.
        """
        try:
            status_clause = " AND e.status = 'active'" if active_only else ""
            type_clause = " AND e.event_type = ?" if event_type else ""
            params = [query, limit, group_id, group_id]
            if event_type:
                params.append(event_type)
            async with self._db.execute(
                f"{_EVENT_SELECT} e WHERE e.rowid IN ("
                "  SELECT rowid FROM events_fts WHERE events_fts MATCH ?"
                "  ORDER BY rank LIMIT ?"
                f"){status_clause}"
                " AND (? IS NULL OR e.group_id = ?)"
                f"{type_clause}"
                " ORDER BY e.salience DESC",
                params,
            ) as cur:
                rows = await cur.fetchall()
            return [_row_to_event(r) for r in rows]
        except Exception:
            return []

    async def search_vector(
        self, embedding: list[float], limit: int = 20, active_only: bool = True,
        group_id: str | None = None, event_type: str | None = None,
    ) -> list[Event]:
        """Cosine-approximate nearest-neighbour search via sqlite-vec vec0.

        group_id=None searches across all groups; pass a value to restrict to one scope.
        event_type filters by 'episode' or 'narrative' when specified.
        Returns [] if sqlite-vec is not loaded or the embedding is empty.
        """
        if not embedding:
            return []
        try:
            status_clause = " AND e.status = 'active'" if active_only else ""
            type_clause = " AND e.event_type = ?" if event_type else ""
            params = [json.dumps(embedding), limit, group_id, group_id]
            if event_type:
                params.append(event_type)
            async with self._db.execute(
                f"SELECT {_EVENT_SELECT_COLS} FROM "
                "(SELECT rowid, distance FROM events_vec WHERE embedding MATCH ? "
                " ORDER BY distance LIMIT ?) v "
                f"JOIN events e ON e.rowid = v.rowid{status_clause}"
                " AND (? IS NULL OR e.group_id = ?)"
                f"{type_clause}"
                " ORDER BY v.distance",
                params,
            ) as cur:
                rows = await cur.fetchall()
            return [_row_to_event(r) for r in rows]
        except Exception:
            return []

    async def upsert_vector(self, event_id: str, embedding: list[float]) -> None:
        """Store or replace the embedding for an event.

        No-op if events_vec doesn't exist (sqlite-vec not loaded).
        """
        if not embedding:
            return
        try:
            async with _txn(self._db, self._lock):
                await self._db.execute(
                    "INSERT OR REPLACE INTO events_vec(rowid, embedding) "
                    "SELECT rowid, ? FROM events WHERE event_id = ?",
                    (json.dumps(embedding), event_id),
                )
        except Exception:
            pass

    async def delete_vector(self, event_id: str) -> None:
        """Remove the vec0 embedding for an event (no-op if not present)."""
        try:
            async with _txn(self._db, self._lock):
                await self._db.execute(
                    "DELETE FROM events_vec WHERE rowid = "
                    "(SELECT rowid FROM events WHERE event_id = ?)",
                    (event_id,),
                )
        except Exception:
            pass

    async def get_children(self, parent_event_id: str) -> list[Event]:
        async with self._db.execute(
            f"{_EVENT_SELECT} e WHERE EXISTS ("
            "  SELECT 1 FROM json_each(e.inherit_from) WHERE value = ?"
            ")",
            (parent_event_id,),
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_event(r) for r in rows]

    async def upsert(self, event: Event) -> None:
        async with _txn(self._db, self._lock):
            await self._db.execute(
                "INSERT INTO events(event_id, group_id, start_time, end_time, participants, "
                "interaction_flow, topic, summary, chat_content_tags, salience, confidence, "
                "inherit_from, last_accessed_at, status, is_locked, bot_persona_name, event_type) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(event_id) DO UPDATE SET "
                "group_id=excluded.group_id, "
                "start_time=excluded.start_time, "
                "end_time=excluded.end_time, "
                "participants=excluded.participants, "
                "interaction_flow=excluded.interaction_flow, "
                "topic=excluded.topic, "
                "summary=excluded.summary, "
                "chat_content_tags=excluded.chat_content_tags, "
                "salience=excluded.salience, "
                "confidence=excluded.confidence, "
                "inherit_from=excluded.inherit_from, "
                "last_accessed_at=excluded.last_accessed_at, "
                "status=excluded.status, "
                "is_locked=excluded.is_locked, "
                "bot_persona_name=excluded.bot_persona_name, "
                "event_type=excluded.event_type",
                (
                    event.event_id,
                    event.group_id,
                    event.start_time,
                    event.end_time,
                    _j(event.participants),
                    _dump_message_refs(event.interaction_flow),
                    event.topic,
                    event.summary,
                    _j(event.chat_content_tags),
                    event.salience,
                    event.confidence,
                    _j(event.inherit_from),
                    event.last_accessed_at,
                    event.status,
                    int(event.is_locked),
                    event.bot_persona_name,
                    event.event_type,
                ),
            )

    async def delete(self, event_id: str) -> bool:
        async with _txn(self._db, self._lock):
            cursor = await self._db.execute(
                "DELETE FROM events WHERE event_id = ?", (event_id,)
            )
            rowcount = cursor.rowcount
        return rowcount > 0

    async def delete_with_vector(self, event_id: str) -> bool:
        """Delete both the events row and its vec0 entry in one transaction."""
        async with _txn(self._db, self._lock):
            try:
                await self._db.execute(
                    "DELETE FROM events_vec WHERE rowid = "
                    "(SELECT rowid FROM events WHERE event_id = ?)",
                    (event_id,),
                )
            except Exception:
                pass  # sqlite-vec not loaded
            cursor = await self._db.execute(
                "DELETE FROM events WHERE event_id = ?", (event_id,)
            )
            rowcount = cursor.rowcount
        return rowcount > 0

    async def count_by_status(self, status: str) -> int:
        async with self._db.execute(
            "SELECT COUNT(*) FROM events WHERE status = ?", (status,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    async def list_by_status(
        self, status: str, limit: int = 100,
        bot_persona_name: str | None = None, include_legacy: bool = True,
    ) -> list[Event]:
        clauses = ["status = ?"]
        params: list[Any] = [status]
        persona_where, persona_params = _persona_where(bot_persona_name, include_legacy)
        if persona_where:
            clauses.append(persona_where)
            params.extend(persona_params)
        sql = f"{_EVENT_SELECT} WHERE " + " AND ".join(clauses) + " ORDER BY start_time DESC LIMIT ?"
        params.append(limit)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [_row_to_event(r) for r in rows]

    async def set_status(self, event_id: str, status: str) -> bool:
        async with _txn(self._db, self._lock):
            cursor = await self._db.execute(
                "UPDATE events SET status = ? WHERE event_id = ?",
                (status, event_id),
            )
            rowcount = cursor.rowcount
        return rowcount > 0

    async def set_locked(self, event_id: str, is_locked: bool) -> bool:
        async with _txn(self._db, self._lock):
            cursor = await self._db.execute(
                "UPDATE events SET is_locked = ? WHERE event_id = ?",
                (int(is_locked), event_id),
            )
            rowcount = cursor.rowcount
        return rowcount > 0

    async def cleanup_low_salience_events(self, threshold: float) -> int:
        """Delete non-locked events with salience < threshold.

        Also deletes associated vector embeddings.
        """
        # Get event_ids to delete first to handle vector deletion
        async with self._db.execute(
            "SELECT event_id FROM events WHERE salience < ? AND is_locked = 0",
            (threshold,),
        ) as cur:
            ids = [row[0] for row in await cur.fetchall()]

        if not ids:
            return 0

        async with _txn(self._db, self._lock):
            # Delete from events_vec first if it exists
            try:
                for eid in ids:
                    await self._db.execute(
                        "DELETE FROM events_vec WHERE rowid = "
                        "(SELECT rowid FROM events WHERE event_id = ?)",
                        (eid,),
                    )
            except Exception:
                pass  # sqlite-vec not loaded

            placeholders = ",".join(["?"] * len(ids))
            cursor = await self._db.execute(
                f"DELETE FROM events WHERE event_id IN ({placeholders})",
                ids,
            )
            count = cursor.rowcount
        return count

    async def archive_low_salience_events(self, threshold: float) -> int:
        """Set status='archived' for non-locked active events below threshold."""
        async with _txn(self._db, self._lock):
            cursor = await self._db.execute(
                "UPDATE events SET status = 'archived' WHERE salience < ? AND is_locked = 0 AND status = 'active'",
                (threshold,),
            )
            count = cursor.rowcount
        return count

    async def delete_old_archived_events(self, cutoff_ts: float) -> int:
        """Permanently delete non-locked archived events older than cutoff_ts."""
        async with self._db.execute(
            "SELECT event_id FROM events WHERE status = 'archived' AND end_time < ? AND is_locked = 0",
            (cutoff_ts,),
        ) as cur:
            ids = [row[0] for row in await cur.fetchall()]

        if not ids:
            return 0

        async with _txn(self._db, self._lock):
            try:
                for eid in ids:
                    await self._db.execute(
                        "DELETE FROM events_vec WHERE rowid = "
                        "(SELECT rowid FROM events WHERE event_id = ?)",
                        (eid,),
                    )
            except Exception:
                pass

            placeholders = ",".join(["?"] * len(ids))
            cursor = await self._db.execute(
                f"DELETE FROM events WHERE event_id IN ({placeholders})",
                ids,
            )
            count = cursor.rowcount
        return count

    async def delete_by_group(self, group_id: str | None) -> int:
        """Delete all events (and their vectors) belonging to group_id."""
        async with self._db.execute(
            "SELECT event_id FROM events WHERE group_id IS ?", (group_id,)
        ) as cur:
            ids = [row[0] for row in await cur.fetchall()]
        if not ids:
            return 0
        async with _txn(self._db, self._lock):
            try:
                for eid in ids:
                    await self._db.execute(
                        "DELETE FROM events_vec WHERE rowid = "
                        "(SELECT rowid FROM events WHERE event_id = ?)",
                        (eid,),
                    )
            except Exception:
                pass
            placeholders = ",".join(["?"] * len(ids))
            cursor = await self._db.execute(
                f"DELETE FROM events WHERE event_id IN ({placeholders})", ids
            )
            count = cursor.rowcount
        return count

    async def delete_all(self) -> int:
        """Delete ALL events and their vectors."""
        async with self._db.execute("SELECT COUNT(*) FROM events") as cur:
            row = await cur.fetchone()
        count = row[0] if row else 0
        if count == 0:
            return 0
        async with _txn(self._db, self._lock):
            try:
                await self._db.execute("DELETE FROM events_vec")
            except Exception:
                pass
            await self._db.execute("DELETE FROM events")
        return count

    async def prune_group_history(self, group_id: str | None, max_messages: int, batch_size: int) -> int:
        """Prune oldest non-locked events in a group until total message count is <= max_messages."""
        # Get all events for the group with their message counts, oldest first
        async with self._db.execute(
            "SELECT event_id, json_array_length(interaction_flow) as msg_count "
            "FROM events WHERE group_id IS ? AND is_locked = 0 "
            "ORDER BY start_time ASC",
            (group_id,),
        ) as cur:
            rows = await cur.fetchall()
        
        if not rows:
            return 0
            
        total_messages = sum(r["msg_count"] for r in rows)
        if total_messages <= max_messages:
            return 0
            
        target_messages = max_messages - batch_size
        deleted_count = 0
        ids_to_delete = []
        
        current_messages = total_messages
        for r in rows:
            if current_messages <= target_messages:
                break
            ids_to_delete.append(r["event_id"])
            current_messages -= r["msg_count"]
            deleted_count += 1
            
        if not ids_to_delete:
            return 0
            
        # Delete the identified events
        async with _txn(self._db, self._lock):
            for eid in ids_to_delete:
                try:
                    await self._db.execute(
                        "DELETE FROM events_vec WHERE rowid = "
                        "(SELECT rowid FROM events WHERE event_id = ?)",
                        (eid,),
                    )
                except Exception:
                    pass
                await self._db.execute(
                    "DELETE FROM events WHERE event_id = ?", (eid,)
                )
        logger.info(
            "[SQLiteEventRepository] Pruned %d old events for group %s (%d messages removed)",
            deleted_count, group_id, total_messages - current_messages
        )
        return deleted_count

    async def get_rowid(self, event_id: str) -> int | None:
        async with self._db.execute(
            "SELECT rowid FROM events WHERE event_id = ?", (event_id,)
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def get_by_rowid(self, rowid: int) -> Event | None:
        async with self._db.execute(
            f"{_EVENT_SELECT} WHERE rowid = ?", (rowid,)
        ) as cur:
            row = await cur.fetchone()
        return _row_to_event(row) if row else None

    async def update_salience(self, event_id: str, new_salience: float) -> bool:
        async with _txn(self._db, self._lock):
            cursor = await self._db.execute(
                "UPDATE events SET salience = ? WHERE event_id = ?",
                (new_salience, event_id),
            )
            rowcount = cursor.rowcount
        return rowcount > 0

    async def update_last_accessed(self, event_id: str, timestamp: float) -> bool:
        async with _txn(self._db, self._lock):
            cursor = await self._db.execute(
                "UPDATE events SET last_accessed_at = ? WHERE event_id = ?",
                (timestamp, event_id),
            )
            rowcount = cursor.rowcount
        return rowcount > 0

    async def decay_all_salience(self, lambda_: float) -> int:
        """Multiply every event's salience by exp(-lambda_) in a single UPDATE."""
        factor = math.exp(-lambda_)
        async with _txn(self._db, self._lock):
            cursor = await self._db.execute(
                "UPDATE events SET salience = MAX(0.0, salience * ?)", (factor,)
            )
            count = cursor.rowcount
        return count

    async def count_messages_by_uid_bulk(self) -> dict[str, int]:
        """Single-pass aggregate: {uid: total_message_count} across ALL events."""
        async with self._db.execute(
            "SELECT json_extract(msg.value, '$.sender_uid'), COUNT(*) "
            "FROM events, json_each(events.interaction_flow) AS msg "
            "GROUP BY json_extract(msg.value, '$.sender_uid')"
        ) as cur:
            rows = await cur.fetchall()
        return {row[0]: row[1] for row in rows if row[0] is not None}

    async def count_edge_messages(self, uid1: str, uid2: str, scope: str) -> int:
        """Count messages from uid1 OR uid2 within a scope.

        scope='global' counts across all groups; other values filter by group_id.
        """
        if scope == "global":
            sql = (
                "SELECT COUNT(*) FROM events, json_each(events.interaction_flow) AS msg "
                "WHERE json_extract(msg.value, '$.sender_uid') IN (?, ?)"
            )
            params: tuple = (uid1, uid2)
        else:
            sql = (
                "SELECT COUNT(*) FROM events, json_each(events.interaction_flow) AS msg "
                "WHERE events.group_id = ? "
                "AND json_extract(msg.value, '$.sender_uid') IN (?, ?)"
            )
            params = (scope, uid1, uid2)
        async with self._db.execute(sql, params) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    # --- Tag Abstraction & Normalization ---

    async def list_frequent_tags(self, limit: int = 50) -> list[str]:
        async with self._db.execute(
            "SELECT value, COUNT(*) as freq "
            "FROM events, json_each(events.chat_content_tags) "
            "GROUP BY value "
            "ORDER BY freq DESC "
            "LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
        return [row[0] for row in rows]

    async def search_canonical_tag(
        self, embedding: list[float], limit: int = 5, threshold: float = 0.85
    ) -> list[tuple[str, float]]:
        if not embedding:
            return []
        try:
            # sqlite-vec distance for cosine is 1 - similarity.
            # similarity = 1 - distance.
            async with self._db.execute(
                "SELECT c.tag_text, (1.0 - v.distance) as similarity "
                "FROM tags_vec v "
                "JOIN canonical_tags c ON c.id = v.rowid "
                "WHERE embedding MATCH ? "
                "AND similarity >= ? "
                "ORDER BY distance "
                "LIMIT ?",
                (json.dumps(embedding), threshold, limit),
            ) as cur:
                rows = await cur.fetchall()
            return [(row[0], row[1]) for row in rows]
        except Exception as exc:
            logger.debug("[SQLiteEventRepository] search_canonical_tag failed: %s", exc)
            return []

    async def upsert_canonical_tag(self, tag_text: str, embedding: list[float]) -> None:
        import time
        async with _txn(self._db, self._lock):
            await self._db.execute(
                "INSERT INTO canonical_tags(tag_text, created_at) VALUES (?, ?) "
                "ON CONFLICT(tag_text) DO NOTHING",
                (tag_text, time.time()),
            )
            try:
                await self._db.execute(
                    "INSERT OR REPLACE INTO tags_vec(rowid, embedding) "
                    "SELECT id, ? FROM canonical_tags WHERE tag_text = ?",
                    (json.dumps(embedding), tag_text),
                )
            except Exception as exc:
                logger.debug("[SQLiteEventRepository] upsert_canonical_tag vector failed: %s", exc)


# ---------------------------------------------------------------------------
# ImpressionRepository
# ---------------------------------------------------------------------------

_IMPRESSION_SELECT = (
    "SELECT observer_uid, subject_uid, ipc_orientation, benevolence, power, "
    "affect_intensity, r_squared, confidence, scope, evidence_event_ids, "
    "last_reinforced_at, bot_persona_name FROM impressions"
)


class SQLiteImpressionRepository(ImpressionRepository):
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        self._lock = _get_db_lock(db)

    async def get(
        self, observer_uid: str, subject_uid: str, scope: str,
        bot_persona_name: str | None = None,
    ) -> Impression | None:
        async with self._db.execute(
            f"{_IMPRESSION_SELECT} WHERE observer_uid=? AND subject_uid=? AND scope=? "
            "AND ifnull(bot_persona_name, '') = ifnull(?, '')",
            (observer_uid, subject_uid, scope, bot_persona_name),
        ) as cur:
            row = await cur.fetchone()
        return _row_to_impression(row) if row else None

    async def list_by_observer(
        self, observer_uid: str, scope: str | None = None,
        bot_persona_name: str | None = None, include_legacy: bool = True,
    ) -> list[Impression]:
        where = ["observer_uid = ?"]
        params: list[Any] = [observer_uid]
        if scope is not None:
            where.append("scope = ?")
            params.append(scope)
        if bot_persona_name is not None:
            if bot_persona_name == "":
                where.append("bot_persona_name IS NULL")
            elif include_legacy:
                where.append("(bot_persona_name = ? OR bot_persona_name IS NULL)")
                params.append(bot_persona_name)
            else:
                where.append("bot_persona_name = ?")
                params.append(bot_persona_name)
        sql = f"{_IMPRESSION_SELECT} WHERE " + " AND ".join(where)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [_row_to_impression(r) for r in rows]

    async def list_by_subject(
        self, subject_uid: str, scope: str | None = None,
        bot_persona_name: str | None = None, include_legacy: bool = True,
    ) -> list[Impression]:
        where = ["subject_uid = ?"]
        params: list[Any] = [subject_uid]
        if scope is not None:
            where.append("scope = ?")
            params.append(scope)
        if bot_persona_name is not None:
            if bot_persona_name == "":
                where.append("bot_persona_name IS NULL")
            elif include_legacy:
                where.append("(bot_persona_name = ? OR bot_persona_name IS NULL)")
                params.append(bot_persona_name)
            else:
                where.append("bot_persona_name = ?")
                params.append(bot_persona_name)
        sql = f"{_IMPRESSION_SELECT} WHERE " + " AND ".join(where)
        async with self._db.execute(sql, tuple(params)) as cur:
            rows = await cur.fetchall()
        return [_row_to_impression(r) for r in rows]

    async def upsert(self, impression: Impression) -> None:
        async with _txn(self._db, self._lock):
            await self._db.execute(
                "INSERT INTO impressions(observer_uid, subject_uid, ipc_orientation, "
                "benevolence, power, affect_intensity, r_squared, confidence, scope, "
                "evidence_event_ids, last_reinforced_at, bot_persona_name) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(observer_uid, subject_uid, scope, ifnull(bot_persona_name, '')) DO UPDATE SET "
                "ipc_orientation=excluded.ipc_orientation, "
                "benevolence=excluded.benevolence, "
                "power=excluded.power, "
                "affect_intensity=excluded.affect_intensity, "
                "r_squared=excluded.r_squared, "
                "confidence=excluded.confidence, "
                "evidence_event_ids=excluded.evidence_event_ids, "
                "last_reinforced_at=excluded.last_reinforced_at",
                (
                    impression.observer_uid,
                    impression.subject_uid,
                    impression.ipc_orientation,
                    impression.benevolence,
                    impression.power,
                    impression.affect_intensity,
                    impression.r_squared,
                    impression.confidence,
                    impression.scope,
                    _j(impression.evidence_event_ids),
                    impression.last_reinforced_at,
                    impression.bot_persona_name,
                ),
            )

    async def delete(
        self, observer_uid: str, subject_uid: str, scope: str,
        bot_persona_name: str | None = None,
    ) -> bool:
        async with _txn(self._db, self._lock):
            if bot_persona_name is None:
                cursor = await self._db.execute(
                    "DELETE FROM impressions WHERE observer_uid=? AND subject_uid=? AND scope=?",
                    (observer_uid, subject_uid, scope),
                )
            elif bot_persona_name == "":
                cursor = await self._db.execute(
                    "DELETE FROM impressions "
                    "WHERE observer_uid=? AND subject_uid=? AND scope=? AND bot_persona_name IS NULL",
                    (observer_uid, subject_uid, scope),
                )
            else:
                cursor = await self._db.execute(
                    "DELETE FROM impressions "
                    "WHERE observer_uid=? AND subject_uid=? AND scope=? AND bot_persona_name=?",
                    (observer_uid, subject_uid, scope, bot_persona_name),
                )
            rowcount = cursor.rowcount
        return rowcount > 0

    async def delete_by_scope(
        self, scope: str, bot_persona_name: str | None = None,
    ) -> int:
        async with _txn(self._db, self._lock):
            if bot_persona_name is None:
                cursor = await self._db.execute(
                    "DELETE FROM impressions WHERE scope=?",
                    (scope,),
                )
            elif bot_persona_name == "":
                cursor = await self._db.execute(
                    "DELETE FROM impressions WHERE scope=? AND bot_persona_name IS NULL",
                    (scope,),
                )
            else:
                cursor = await self._db.execute(
                    "DELETE FROM impressions WHERE scope=? AND bot_persona_name=?",
                    (scope, bot_persona_name),
                )
            return cursor.rowcount
