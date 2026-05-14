-- Migration 009: Add event_type column for narrative/episode distinction
-- ---------------------------------------------------------------------------

-- 1. Add event_type column with default 'episode' for all existing rows
ALTER TABLE events ADD COLUMN event_type TEXT NOT NULL DEFAULT 'episode';

-- 2. Index for fast type-filtered queries
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
