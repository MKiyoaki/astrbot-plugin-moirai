-- Migration 024: 事件记下抽取它的会话窗口（私聊为那段对话，群聊为该群的会话），用于按来源删除记忆。旧事件为空。
ALTER TABLE events ADD COLUMN source_session_id TEXT DEFAULT NULL;
CREATE INDEX IF NOT EXISTS idx_events_source_session ON events(source_session_id);
