-- Migration 005: Add summary column to events table
-- ---------------------------------------------------------------------------

ALTER TABLE events ADD COLUMN summary TEXT NOT NULL DEFAULT '';
