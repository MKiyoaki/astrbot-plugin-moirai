-- canon.sqlite，schema_version 2。event_vec 和全文检索表由 store.py 按 encoder 维度与 FTS 模式创建。

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS scenes (
  scene_key TEXT PRIMARY KEY,
  scene_hash TEXT NOT NULL,
  narrative_pos INTEGER NOT NULL,
  anchor TEXT NOT NULL,
  category TEXT, tier TEXT NOT NULL,
  collection_id TEXT, collection_name TEXT,
  chapter_no INTEGER, story_code TEXT, story_name TEXT, avg_tag TEXT,
  release_date TEXT, official_summary TEXT, prev_scene_key TEXT
);
CREATE INDEX IF NOT EXISTS idx_scenes_pos ON scenes(narrative_pos);

CREATE TABLE IF NOT EXISTS lines (
  line_key TEXT PRIMARY KEY,
  scene_key TEXT NOT NULL REFERENCES scenes(scene_key) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  kind TEXT NOT NULL, speaker TEXT, speaker_id TEXT, portrait TEXT,
  text TEXT NOT NULL, has_nickname INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_lines_scene ON lines(scene_key, idx);

-- 抽取缓存：删除场景时不级联删除，场景改回原样时还能命中
CREATE TABLE IF NOT EXISTS extractions (
  scene_key TEXT NOT NULL, scene_hash TEXT NOT NULL, prompt_version TEXT NOT NULL,
  model TEXT NOT NULL, status TEXT NOT NULL CHECK (status IN ('ok','failed')),
  raw_json TEXT, error TEXT, attempts INTEGER NOT NULL,
  prompt_tokens INTEGER, completion_tokens INTEGER, created_at TEXT NOT NULL,
  PRIMARY KEY (scene_key, scene_hash, prompt_version)
);

-- rid 是显式整数主键：全文检索按 rowid 关联，文本主键表的 rowid 在 VACUUM 后可能改变
CREATE TABLE IF NOT EXISTS events (
  rid INTEGER PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE,
  scene_key TEXT NOT NULL REFERENCES scenes(scene_key) ON DELETE CASCADE,
  local_id TEXT NOT NULL, ord INTEGER NOT NULL,
  topic TEXT NOT NULL, summary TEXT NOT NULL,
  in_world_time TEXT NOT NULL, in_world_note TEXT,
  participants TEXT NOT NULL,
  involves_doctor INTEGER NOT NULL DEFAULT 0,
  narrative_pos INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_scene ON events(scene_key, ord);
CREATE INDEX IF NOT EXISTS idx_events_pos ON events(narrative_pos);

CREATE TABLE IF NOT EXISTS event_evidence (
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  line_key TEXT NOT NULL, ord INTEGER NOT NULL,
  PRIMARY KEY (event_id, line_key)
);

-- 事件里值得单独检索的细节（canon-extract-v3 起）：只作检索键，命中后注入的是所属事件；evidence 是 line_key 的 JSON 数组
CREATE TABLE IF NOT EXISTS event_beats (
  rid INTEGER PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  ord INTEGER NOT NULL, text TEXT NOT NULL,
  evidence TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_beats_event ON event_beats(event_id, ord);

CREATE TABLE IF NOT EXISTS entities (
  entity_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  type TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('seed','extracted'))
);
CREATE TABLE IF NOT EXISTS aliases (
  alias TEXT PRIMARY KEY,
  entity_id INTEGER NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS event_entities (
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  entity_id INTEGER NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
  PRIMARY KEY (event_id, entity_id)
);

CREATE TABLE IF NOT EXISTS views (
  character TEXT NOT NULL,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  channel TEXT NOT NULL CHECK (channel IN ('experienced','witnessed','told','recalled','unstated')),
  note TEXT,
  PRIMARY KEY (character, event_id)
);
CREATE TABLE IF NOT EXISTS view_evidence (
  character TEXT NOT NULL,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  line_key TEXT NOT NULL,
  PRIMARY KEY (character, event_id, line_key)
);

CREATE TABLE IF NOT EXISTS episodes (
  character TEXT NOT NULL,
  scene_key TEXT NOT NULL REFERENCES scenes(scene_key) ON DELETE CASCADE,
  text TEXT NOT NULL,
  PRIMARY KEY (character, scene_key)
);

-- 第二期才参与检索，第一期就写入
CREATE TABLE IF NOT EXISTS cognitions (
  character TEXT NOT NULL,
  scene_key TEXT NOT NULL REFERENCES scenes(scene_key) ON DELETE CASCADE,
  ord INTEGER NOT NULL, target TEXT NOT NULL, stance TEXT NOT NULL,
  evidence TEXT NOT NULL,
  PRIMARY KEY (character, scene_key, ord)
);
CREATE TABLE IF NOT EXISTS edges (
  src TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  dst TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  type TEXT NOT NULL CHECK (type IN ('cause','motivation','emotion_source','cognition_update')),
  explicit INTEGER NOT NULL, confidence REAL NOT NULL,
  evidence TEXT NOT NULL,
  PRIMARY KEY (src, dst, type)
);

CREATE TABLE IF NOT EXISTS event_vec_map (
  vec_rowid INTEGER PRIMARY KEY,
  event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id) ON DELETE CASCADE
);
