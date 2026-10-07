"""档案查询：按名字找档案条目，读取它的分段。"""
from __future__ import annotations

import json
import sqlite3



class ArchiveMixin:
    """档案查询：按名字找档案条目，读取它的分段。"""

    def archive_ids(self, name: str) -> list[str]:
        """Entity links first (through aliases), then the archive's own name; operators before enemies."""
        name = name.strip()
        if not self.has_archives or not name:
            return []
        row = self.db.execute(
            "SELECT e.name FROM aliases a JOIN entities e ON e.entity_id=a.entity_id WHERE a.alias=?", (name,)
        ).fetchone()
        names = [row["name"]] if row else ([n for _, _, n in self._spans(name)] or [name])
        found: list[str] = []
        for entity in dict.fromkeys(names):
            found += [r["archive_id"] for r in self.db.execute(
                "SELECT ea.archive_id FROM entity_archives ea JOIN entities e ON e.entity_id=ea.entity_id "
                "JOIN archives a ON a.archive_id=ea.archive_id WHERE e.name=? "
                "ORDER BY a.kind='enemy', a.archive_id", (entity,))]
            found += [r["archive_id"] for r in self.db.execute(
                "SELECT archive_id FROM archives WHERE name=? OR appellation=? COLLATE NOCASE "
                "ORDER BY kind='enemy', archive_id", (entity, entity))]
        return list(dict.fromkeys(found))

    def archive_sections(self, archive_id: str, *, every_form: bool) -> list[sqlite3.Row]:
        """By default only the archive's own form: no PATCH unlocks, other forms or hidden sections."""
        rows = self.db.execute(
            "SELECT s.*, a.name, a.kind FROM archive_sections s JOIN archives a ON a.archive_id=s.archive_id "
            "WHERE s.archive_id=? ORDER BY s.seq, s.version", (archive_id,)
        ).fetchall()
        if every_form:
            return rows
        return [row for row in rows if not row["hidden"] and row["unlock_type"] != "PATCH"
                and (not json.loads(row["forms"]) or archive_id in json.loads(row["forms"]))]
