-- Migration 016: document frequency for canonical tags.
--
-- Tag normalization used to promote every first-seen tag straight into the
-- matchable vocabulary, so one-off labels became permanent anchors and the
-- vocabulary only ever grew. df turns canonical_tags into a two-tier store:
-- freshly seen tags are candidates, and only tags that recur often enough
-- become anchors other tags may collapse onto.

ALTER TABLE canonical_tags ADD COLUMN df INTEGER NOT NULL DEFAULT 0;

-- Existing rows predate the gate; seed them at 1 so they are treated as
-- candidates rather than silently grandfathered in as anchors.
UPDATE canonical_tags SET df = 1 WHERE df = 0;

CREATE INDEX IF NOT EXISTS idx_canonical_tags_df ON canonical_tags(df DESC);
