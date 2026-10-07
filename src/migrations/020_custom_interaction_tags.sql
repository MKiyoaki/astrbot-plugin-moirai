-- Migration 020: Bot-persona-scoped custom interaction leaves.
--
-- Empty bot_persona_name is the isolated legacy scope. Only accepted names are
-- stored; generation attempts and judge scores stay in the event payload.
CREATE TABLE IF NOT EXISTS custom_interaction_tags (
    bot_persona_name TEXT NOT NULL DEFAULT '',
    tag_text TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (bot_persona_name, tag_text)
);
