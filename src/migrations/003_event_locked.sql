-- Add is_locked column to events table
ALTER TABLE events ADD COLUMN is_locked INTEGER DEFAULT 0;
