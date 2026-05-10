-- Migration 007: Canonical tags for normalization
-- Stores unique macro tags and their vectors for "Silent Alignment".

CREATE TABLE IF NOT EXISTS canonical_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_text TEXT UNIQUE NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_canonical_tags_text ON canonical_tags(tag_text);
