-- Migration 014: Add access_count to events
-- Tracks how many times each event has been injected into an LLM request.
ALTER TABLE events ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0;
