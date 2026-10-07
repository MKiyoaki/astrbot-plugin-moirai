-- Composite index to speed up search_fts and search_vector WHERE clauses
-- (status, event_type, group_id) covers the most common filter combination.
CREATE INDEX IF NOT EXISTS idx_events_status_type_group
    ON events (status, event_type, group_id);
