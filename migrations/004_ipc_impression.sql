-- Migration 004: IPC social orientation fields for impressions
--
-- Replaces the 5-label relation_type system with the 8-label Interpersonal
-- Circumplex (IPC) model and adds a second coordinate axis (power).
--
-- Field mapping from old → new:
--   relation_type  → ipc_orientation  (string label, 8 IPC categories)
--   affect         → benevolence      (Affiliation axis, [-1, 1], semantics unchanged)
--   intensity      → affect_intensity (IPC magnitude √(B²+P²)/√2, [0, 1])
--
-- New fields initialised to 0 (neutral); values are populated by the next
-- run of the impression aggregation task or SocialOrientationAnalyzer.
--
-- Historical relation_type value guidance (for manual correction if needed):
--   friend     → 友好   rival    → 敌意   stranger → 友好 (low confidence)
--   family     → 服从友好          colleague → 主导友好
ALTER TABLE impressions RENAME COLUMN relation_type TO ipc_orientation;
ALTER TABLE impressions RENAME COLUMN affect TO benevolence;
ALTER TABLE impressions RENAME COLUMN intensity TO affect_intensity;
ALTER TABLE impressions ADD COLUMN power REAL NOT NULL DEFAULT 0.0;
ALTER TABLE impressions ADD COLUMN r_squared REAL NOT NULL DEFAULT 0.0;
