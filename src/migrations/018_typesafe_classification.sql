-- Migration 018: event interaction output and a per-tag topic category store.
--
-- interaction_classification is a versioned JSON object. Empty means the event
-- has not been classified. It is separate from event_type, which distinguishes
-- episode/narrative synthesis records, and from tag_categories, which powers
-- broad topic facets and recall.
ALTER TABLE events ADD COLUMN interaction_classification TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS tag_categories (
    tag_text TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    confidence REAL NOT NULL,
    updated_at REAL NOT NULL
);
