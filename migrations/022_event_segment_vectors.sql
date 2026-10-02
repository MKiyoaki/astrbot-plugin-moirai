-- Migration 022: one embedding per summary segment, for picking what to inject.
--
-- Recall still ranks whole events; within the recalled events, injection picks
-- the summary segments closest to the message. ordinal is the segment's
-- position in split_subtopics(summary); text_hash and identity let a reader
-- discard a vector whose segment text or encoder has changed since, so edits,
-- re-extraction and a model switch never need to touch this table.
CREATE TABLE IF NOT EXISTS event_segment_vectors (
    event_id  TEXT    NOT NULL,
    ordinal   INTEGER NOT NULL,
    text_hash TEXT    NOT NULL,
    identity  TEXT    NOT NULL,
    vector    BLOB    NOT NULL,
    PRIMARY KEY (event_id, ordinal)
);

CREATE TRIGGER IF NOT EXISTS event_segment_vectors_ad AFTER DELETE ON events BEGIN
    DELETE FROM event_segment_vectors WHERE event_id = old.event_id;
END;
