-- Migration 008: Fix FTS indexing to include summary column
-- ---------------------------------------------------------------------------

-- 1. Drop existing FTS table and recreate with summary column
DROP TABLE IF EXISTS events_fts;

CREATE VIRTUAL TABLE events_fts USING fts5(
    topic,
    chat_content_tags,
    summary,
    content='events',
    content_rowid='rowid',
    tokenize='unicode61'
);

-- 2. Populate FTS table with existing data
INSERT INTO events_fts(rowid, topic, chat_content_tags, summary)
SELECT rowid, topic, chat_content_tags, summary FROM events;

-- 3. Drop existing triggers
DROP TRIGGER IF EXISTS events_ai;
DROP TRIGGER IF EXISTS events_ad;
DROP TRIGGER IF EXISTS events_au;

-- 4. Create updated triggers including summary column
CREATE TRIGGER events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, topic, chat_content_tags, summary)
    VALUES (new.rowid, new.topic, new.chat_content_tags, new.summary);
END;

CREATE TRIGGER events_ad AFTER DELETE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, topic, chat_content_tags, summary)
    VALUES ('delete', old.rowid, old.topic, old.chat_content_tags, old.summary);
END;

CREATE TRIGGER events_au AFTER UPDATE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, topic, chat_content_tags, summary)
    VALUES ('delete', old.rowid, old.topic, old.chat_content_tags, old.summary);
    INSERT INTO events_fts(rowid, topic, chat_content_tags, summary)
    VALUES (new.rowid, new.topic, new.chat_content_tags, new.summary);
END;
