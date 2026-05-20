#!/usr/bin/env python3
"""Read-only diagnostic for bot_persona_name bucketing.

Lists how events / impressions / personas are distributed across
``bot_persona_name`` buckets, and dumps every ``internal``-bound persona so
mis-filed data (e.g. an AstrBot persona "Gariton Ver 2" landing in a stray
account-name bucket like "GaritonBot") is easy to spot.

Usage:
    python tools/diagnose_persona_buckets.py [path/to/core.db]

The script never writes to the database. Once a stray bucket is identified,
consolidate it through the WebUI "Persona Ownership" panel (merge_bot_persona).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_DEFAULT_DB = Path("data/plugin_data/astrbot_plugin_enhanced_memory/db/core.db")


def _fmt_bucket(value: object) -> str:
    if value is None:
        return "<NULL / legacy>"
    text = str(value)
    return f'"{text}"' if text else '<empty string>'


def _group_count(conn: sqlite3.Connection, table: str) -> None:
    print(f"\n[{table}] bot_persona_name buckets:")
    try:
        rows = conn.execute(
            f"SELECT bot_persona_name, COUNT(*) FROM {table} GROUP BY bot_persona_name"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        print(f"  (skipped: {exc})")
        return
    if not rows:
        print("  (no rows)")
        return
    for bucket, count in sorted(rows, key=lambda r: -r[1]):
        print(f"  {count:>8}  {_fmt_bucket(bucket)}")
    if len(rows) > 1:
        print(f"  -> {len(rows)} distinct buckets. Multiple named buckets that "
              "should be the same persona indicate mis-filing.")


def _list_internal_personas(conn: sqlite3.Connection) -> None:
    print("\n[personas] internal-bound bot personas:")
    try:
        rows = conn.execute(
            "SELECT p.uid, p.primary_name, ib.physical_id, p.last_active_at "
            "FROM personas p JOIN identity_bindings ib ON ib.uid = p.uid "
            "WHERE ib.platform = 'internal' "
            "ORDER BY p.last_active_at DESC"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        print(f"  (skipped: {exc})")
        return
    if not rows:
        print("  (none)")
        return
    for uid, name, physical_id, last_active in rows:
        print(f"  primary_name={name!r:<28} physical_id={physical_id!r:<22} "
              f"uid={uid} last_active={last_active}")
    if len(rows) > 1:
        print(f"  -> {len(rows)} internal personas exist. The legacy "
              "_get_bot_persona() fallback picked one arbitrarily.")


def main(argv: list[str]) -> int:
    db_path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_DB
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        print("Pass the path explicitly: python tools/diagnose_persona_buckets.py <db>",
              file=sys.stderr)
        return 1

    print(f"=== Persona bucket diagnostic: {db_path} ===")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for table in ("events", "impressions", "personas"):
            _group_count(conn, table)
        _list_internal_personas(conn)
    finally:
        conn.close()
    print("\nDone. This script made no changes to the database.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
