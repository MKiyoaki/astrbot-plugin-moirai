-- Migration 010: bot_persona_name scope columns for cross-persona isolation
--
-- Adds bot_persona_name to personas (simple ADD COLUMN) and impressions
-- (table rebuild required because the UNIQUE constraint needs the new column).
--
-- All existing rows are seeded with bot_persona_name = NULL, which the
-- application layer treats as the "legacy / default persona" scope so old
-- data remains visible under any persona view when persona_isolation_legacy_visible
-- is enabled (default).

-- ---------------------------------------------------------------------------
-- Personas
-- ---------------------------------------------------------------------------

ALTER TABLE personas ADD COLUMN bot_persona_name TEXT DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_personas_bot_persona ON personas(bot_persona_name);

-- ---------------------------------------------------------------------------
-- Events: column already present from migration 006; just add the lookup index.
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_events_bot_persona ON events(bot_persona_name);

-- ---------------------------------------------------------------------------
-- Impressions: rebuild table so the unique key includes bot_persona_name.
--
-- SQLite treats NULL ≠ NULL in inline UNIQUE constraints, so two legacy rows
-- with NULL persona would *not* collide. We use a CREATE UNIQUE INDEX with
-- ifnull(...) to coalesce NULLs to '' for de-duplication purposes, preserving
-- the dataclass-level "NULL means legacy persona" convention.
-- ---------------------------------------------------------------------------

ALTER TABLE impressions RENAME TO impressions_old;

CREATE TABLE impressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observer_uid TEXT NOT NULL,
    subject_uid TEXT NOT NULL,
    ipc_orientation TEXT NOT NULL,
    benevolence REAL NOT NULL,
    affect_intensity REAL NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    scope TEXT NOT NULL DEFAULT 'global',
    evidence_event_ids TEXT NOT NULL DEFAULT '[]',
    last_reinforced_at REAL NOT NULL,
    power REAL NOT NULL DEFAULT 0.0,
    r_squared REAL NOT NULL DEFAULT 0.0,
    bot_persona_name TEXT DEFAULT NULL
);

INSERT INTO impressions (
    id, observer_uid, subject_uid, ipc_orientation, benevolence, affect_intensity,
    confidence, scope, evidence_event_ids, last_reinforced_at, power, r_squared,
    bot_persona_name
)
SELECT
    id, observer_uid, subject_uid, ipc_orientation, benevolence, affect_intensity,
    confidence, scope, evidence_event_ids, last_reinforced_at, power, r_squared,
    NULL
FROM impressions_old;

DROP TABLE impressions_old;

CREATE UNIQUE INDEX uniq_impressions_persona_scope
    ON impressions(observer_uid, subject_uid, scope, ifnull(bot_persona_name, ''));

CREATE INDEX IF NOT EXISTS idx_impressions_observer ON impressions(observer_uid, scope);
CREATE INDEX IF NOT EXISTS idx_impressions_subject ON impressions(subject_uid, scope);
CREATE INDEX IF NOT EXISTS idx_impressions_bot_persona ON impressions(bot_persona_name);
