-- Migration 017: Add participant_style column to events table
-- Per-speaker speaking-style / persona observations captured at extraction time:
--   {display_name: "一句话说话风格描述"}
-- Aggregated later by persona synthesis into persona_attrs.speaking_style.
ALTER TABLE events ADD COLUMN participant_style TEXT NOT NULL DEFAULT '{}';
