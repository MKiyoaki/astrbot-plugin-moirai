-- Migration 013: Persist recent raw messages as a short-lived evidence layer.

CREATE TABLE IF NOT EXISTS raw_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    session_id TEXT NOT NULL,
    group_id TEXT,
    platform TEXT NOT NULL,
    physical_id TEXT NOT NULL,
    sender_uid TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user',
    text TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    message_chain_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    bot_persona_name TEXT,
    created_at REAL NOT NULL,
    ingested_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS event_messages (
    event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    message_id TEXT NOT NULL REFERENCES raw_messages(message_id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    PRIMARY KEY (event_id, ordinal),
    UNIQUE (event_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_messages_session_time
    ON raw_messages(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_raw_messages_group_time
    ON raw_messages(group_id, created_at);
CREATE INDEX IF NOT EXISTS idx_raw_messages_sender_time
    ON raw_messages(sender_uid, created_at);
CREATE INDEX IF NOT EXISTS idx_raw_messages_persona_time
    ON raw_messages(bot_persona_name, created_at);
CREATE INDEX IF NOT EXISTS idx_raw_messages_created_at
    ON raw_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_event_messages_message
    ON event_messages(message_id);

CREATE VIRTUAL TABLE IF NOT EXISTS raw_messages_fts USING fts5(
    text,
    display_name,
    content='raw_messages',
    content_rowid='id',
    tokenize='unicode61'
);

CREATE TRIGGER IF NOT EXISTS raw_messages_ai AFTER INSERT ON raw_messages BEGIN
    INSERT INTO raw_messages_fts(rowid, text, display_name)
    VALUES (new.id, new.text, new.display_name);
END;

CREATE TRIGGER IF NOT EXISTS raw_messages_ad AFTER DELETE ON raw_messages BEGIN
    INSERT INTO raw_messages_fts(raw_messages_fts, rowid, text, display_name)
    VALUES ('delete', old.id, old.text, old.display_name);
END;

CREATE TRIGGER IF NOT EXISTS raw_messages_au AFTER UPDATE ON raw_messages BEGIN
    INSERT INTO raw_messages_fts(raw_messages_fts, rowid, text, display_name)
    VALUES ('delete', old.id, old.text, old.display_name);
    INSERT INTO raw_messages_fts(rowid, text, display_name)
    VALUES (new.id, new.text, new.display_name);
END;
