-- Migration 002: Add status column to events table.
-- Supports active / archived lifecycle states for Event records.

ALTER TABLE events ADD COLUMN status TEXT NOT NULL DEFAULT 'active';

CREATE INDEX IF NOT EXISTS idx_events_status ON events(status);
