-- Migration 015: Cross-platform account binding (persona groups).
-- A persona_group links multiple per-platform Personas under one display name
-- so that personality synthesis aggregates their data. Membership is stored on
-- personas.group_id; no per-account data is moved, so unbinding is lossless.

CREATE TABLE IF NOT EXISTS persona_groups (
    group_id     TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    primary_uid  TEXT NOT NULL,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL
);

ALTER TABLE personas ADD COLUMN group_id TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_personas_group ON personas(group_id);
