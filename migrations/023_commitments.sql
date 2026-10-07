-- 每轮回复里的「记下」独立保存，不随一次便签或原始消息清理消失。
CREATE TABLE IF NOT EXISTS commitments (
    commitment_id TEXT PRIMARY KEY,
    bot_persona_name TEXT NOT NULL,
    person_uid TEXT NOT NULL,
    session_id TEXT NOT NULL,
    group_id TEXT,
    text TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'dropped')),
    closed_at REAL,
    closing_event_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_commitments_person_status
    ON commitments(bot_persona_name, person_uid, status);
