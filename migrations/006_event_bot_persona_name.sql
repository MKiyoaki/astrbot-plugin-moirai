-- Migration 006: Add bot_persona_name column to events table
ALTER TABLE events ADD COLUMN bot_persona_name TEXT DEFAULT NULL;
