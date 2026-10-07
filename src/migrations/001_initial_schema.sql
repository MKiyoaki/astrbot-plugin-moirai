-- Migration 001: Initial schema
-- Creates all core tables, FTS5 virtual table, sync triggers, and indexes.
-- sqlite-vec vec0 table is added in Migration 005 (Phase 5).

-- -----------------------------------------------------------------------
-- Personas & identity bindings
-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS personas (
    uid TEXT PRIMARY KEY,
    primary_name TEXT NOT NULL,
    persona_attrs TEXT NOT NULL DEFAULT '{}',
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at REAL NOT NULL,
    last_active_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS identity_bindings (
    platform TEXT NOT NULL,
    physical_id TEXT NOT NULL,
    uid TEXT NOT NULL REFERENCES personas(uid) ON DELETE CASCADE,
    PRIMARY KEY (platform, physical_id)
);

CREATE INDEX IF NOT EXISTS idx_identity_uid ON identity_bindings(uid);

-- -----------------------------------------------------------------------
-- Events
-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    group_id TEXT,                          -- NULL = private chat
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    participants TEXT NOT NULL DEFAULT '[]',      -- JSON array of uids
    interaction_flow TEXT NOT NULL DEFAULT '[]',  -- JSON array of MessageRef dicts
    topic TEXT NOT NULL DEFAULT '',
    chat_content_tags TEXT NOT NULL DEFAULT '[]', -- JSON array of strings
    salience REAL NOT NULL DEFAULT 0.5,
    confidence REAL NOT NULL DEFAULT 0.5,
    inherit_from TEXT NOT NULL DEFAULT '[]',      -- JSON array of event_ids
    last_accessed_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_group_start ON events(group_id, start_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_salience ON events(salience DESC);

-- -----------------------------------------------------------------------
-- Events FTS5 (BM25 keyword search)
-- External-content table: stores only the index, reads from events for snippets.
-- -----------------------------------------------------------------------

CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
    topic,
    chat_content_tags,
    content='events',
    content_rowid='rowid',
    tokenize='unicode61'
);

-- Keep FTS5 index in sync with events table via triggers.

CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, topic, chat_content_tags)
    VALUES (new.rowid, new.topic, new.chat_content_tags);
END;

CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, topic, chat_content_tags)
    VALUES ('delete', old.rowid, old.topic, old.chat_content_tags);
END;

CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, topic, chat_content_tags)
    VALUES ('delete', old.rowid, old.topic, old.chat_content_tags);
    INSERT INTO events_fts(rowid, topic, chat_content_tags)
    VALUES (new.rowid, new.topic, new.chat_content_tags);
END;

-- -----------------------------------------------------------------------
-- Impressions (directed social graph)
-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS impressions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observer_uid TEXT NOT NULL,
    subject_uid TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    affect REAL NOT NULL,            -- [-1, 1]
    intensity REAL NOT NULL,         -- [0, 1]
    confidence REAL NOT NULL DEFAULT 0.5,
    scope TEXT NOT NULL DEFAULT 'global',
    evidence_event_ids TEXT NOT NULL DEFAULT '[]',  -- JSON array
    last_reinforced_at REAL NOT NULL,
    UNIQUE(observer_uid, subject_uid, scope)
);

CREATE INDEX IF NOT EXISTS idx_impressions_observer ON impressions(observer_uid, scope);
CREATE INDEX IF NOT EXISTS idx_impressions_subject ON impressions(subject_uid, scope);

-- -----------------------------------------------------------------------
-- Migration tracking (managed by migrations/runner.py)
-- -----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS _migrations (
    name TEXT PRIMARY KEY,
    applied_at REAL NOT NULL
);
