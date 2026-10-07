"""Lightweight schema migration runner — no third-party dependencies.

Usage:
    await run_migrations(db)  # idempotent; safe to call on every startup
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import aiosqlite

_MIGRATIONS_DIR = Path(__file__).parent


async def run_migrations(db: aiosqlite.Connection) -> list[str]:
    """Apply all pending *.sql migrations in filename order.

    Returns the list of migration names that were newly applied.
    Idempotent: already-applied migrations are skipped.
    """
    # Bootstrap tracking table (may not exist yet on first run)
    await db.execute(
        "CREATE TABLE IF NOT EXISTS _migrations "
        "(name TEXT PRIMARY KEY, applied_at REAL NOT NULL)"
    )
    await db.commit()

    applied: list[str] = []
    sql_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))

    for sql_file in sql_files:
        name = sql_file.name
        async with db.execute(
            "SELECT 1 FROM _migrations WHERE name = ?", (name,)
        ) as cur:
            if await cur.fetchone() is not None:
                continue  # Already applied

        sql = sql_file.read_text(encoding="utf-8")
        # Execute each statement individually (executescript issues COMMIT first)
        for statement in _split_statements(sql):
            await db.execute(statement)

        await db.execute(
            "INSERT INTO _migrations(name, applied_at) VALUES (?, ?)",
            (name, time.time()),
        )
        await db.commit()
        applied.append(name)

    return applied


def _split_statements(sql: str) -> list[str]:
    """Split a SQL file into individual statements, skipping comments and blanks.

    Tracks BEGIN...END depth so trigger bodies are not split mid-statement.
    """
    statements: list[str] = []
    current: list[str] = []
    depth = 0  # nesting level for compound statements (CREATE TRIGGER ... BEGIN...END)

    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue

        # Count BEGIN/END keywords to track compound statement depth.
        # Use word-boundary matching to avoid false hits inside identifiers.
        for token in re.findall(r"\b(BEGIN|END)\b", stripped.upper()):
            if token == "BEGIN":
                depth += 1
            else:  # END
                depth -= 1

        current.append(line)
        if stripped.endswith(";") and depth == 0:
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []

    # Catch any trailing statement without a semicolon
    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)

    return statements
