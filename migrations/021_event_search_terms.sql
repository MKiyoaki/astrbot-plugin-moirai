-- Migration 021: Chinese-capable keyword search columns.
--
-- unicode61 treats a whole run of Chinese characters as one token, so keyword
-- recall matched almost nothing on Chinese text. search_words (CJK pairs and
-- Latin words) and search_chars (single CJK characters) hold space-separated
-- terms computed by core/retrieval/terms.py. NULL means not computed yet;
-- db_open fills those rows after migrations. A later SQL migration that edits
-- event text must set both columns back to NULL.
ALTER TABLE events ADD COLUMN search_words TEXT;
ALTER TABLE events ADD COLUMN search_chars TEXT;

CREATE TABLE IF NOT EXISTS search_index_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

DROP TRIGGER IF EXISTS events_ai;
DROP TRIGGER IF EXISTS events_ad;
DROP TRIGGER IF EXISTS events_au;
DROP TABLE IF EXISTS events_fts;

CREATE VIRTUAL TABLE events_fts USING fts5(
    topic,
    chat_content_tags,
    summary,
    search_words,
    search_chars,
    content='events',
    content_rowid='rowid',
    tokenize='unicode61'
);

CREATE TRIGGER events_ai AFTER INSERT ON events BEGIN
    INSERT INTO events_fts(rowid, topic, chat_content_tags, summary, search_words, search_chars)
    VALUES (new.rowid, new.topic, new.chat_content_tags, new.summary, new.search_words, new.search_chars);
END;

CREATE TRIGGER events_ad AFTER DELETE ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, topic, chat_content_tags, summary, search_words, search_chars)
    VALUES ('delete', old.rowid, old.topic, old.chat_content_tags, old.summary, old.search_words, old.search_chars);
END;

-- Only text columns feed the index; salience and access-count updates no longer rewrite it.
CREATE TRIGGER events_au AFTER UPDATE OF topic, chat_content_tags, summary, search_words, search_chars ON events BEGIN
    INSERT INTO events_fts(events_fts, rowid, topic, chat_content_tags, summary, search_words, search_chars)
    VALUES ('delete', old.rowid, old.topic, old.chat_content_tags, old.summary, old.search_words, old.search_chars);
    INSERT INTO events_fts(rowid, topic, chat_content_tags, summary, search_words, search_chars)
    VALUES (new.rowid, new.topic, new.chat_content_tags, new.summary, new.search_words, new.search_chars);
END;

INSERT INTO events_fts(events_fts) VALUES ('rebuild');
