-- canon.sqlite，schema_version 4。event_vec 和全文检索表由 store.py 按 encoder 维度与 FTS 模式创建。

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

CREATE TABLE IF NOT EXISTS timeline_points (
  point_id TEXT PRIMARY KEY,
  timeline_id TEXT NOT NULL,
  scene_key TEXT NOT NULL REFERENCES scenes(scene_key) ON DELETE CASCADE,
  line_key TEXT REFERENCES lines(line_key) ON DELETE SET NULL,
  label TEXT NOT NULL,
  precision TEXT NOT NULL CHECK (precision IN ('scene','line','explicit_date'))
);
CREATE INDEX IF NOT EXISTS idx_timeline_points_scene ON timeline_points(scene_key);

CREATE TABLE IF NOT EXISTS timeline_before (
  earlier TEXT NOT NULL REFERENCES timeline_points(point_id) ON DELETE CASCADE,
  later TEXT NOT NULL REFERENCES timeline_points(point_id) ON DELETE CASCADE,
  evidence_event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  evidence_line_key TEXT NOT NULL REFERENCES lines(line_key) ON DELETE CASCADE,
  PRIMARY KEY (earlier, later),
  CHECK (earlier != later)
);

CREATE TABLE IF NOT EXISTS facts (
  fact_id TEXT PRIMARY KEY,
  subject TEXT NOT NULL,
  predicate TEXT NOT NULL CHECK (predicate IN ('location','custody','affiliation','life_status')),
  object TEXT NOT NULL,
  polarity INTEGER NOT NULL CHECK (polarity IN (0,1)),
  point_id TEXT NOT NULL REFERENCES timeline_points(point_id) ON DELETE CASCADE,
  end_point_id TEXT REFERENCES timeline_points(point_id) ON DELETE SET NULL,
  persistence TEXT NOT NULL CHECK (persistence IN ('point','until_changed','explicit_interval')),
  source_type TEXT NOT NULL CHECK (source_type IN ('explicit','derived','suggested')),
  review_status TEXT NOT NULL CHECK (review_status IN ('candidate','reviewed','rejected')),
  CHECK (persistence != 'explicit_interval' OR end_point_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject, predicate);

CREATE TABLE IF NOT EXISTS fact_evidence (
  fact_id TEXT NOT NULL REFERENCES facts(fact_id) ON DELETE CASCADE,
  event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  line_key TEXT NOT NULL REFERENCES lines(line_key) ON DELETE CASCADE,
  relation TEXT NOT NULL CHECK (relation IN ('supports','refutes','changes')),
  PRIMARY KEY (fact_id, event_id, line_key, relation)
);

CREATE TABLE IF NOT EXISTS fact_transitions (
  earlier_fact_id TEXT NOT NULL REFERENCES facts(fact_id) ON DELETE CASCADE,
  later_fact_id TEXT NOT NULL REFERENCES facts(fact_id) ON DELETE CASCADE,
  relation TEXT NOT NULL CHECK (relation IN ('supersedes','contradicts','corroborates')),
  evidence_event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
  evidence_line_key TEXT NOT NULL REFERENCES lines(line_key) ON DELETE CASCADE,
  PRIMARY KEY (earlier_fact_id, later_fact_id, relation),
  CHECK (earlier_fact_id != later_fact_id)
);

CREATE TABLE IF NOT EXISTS fact_coverage (
  timeline_id TEXT PRIMARY KEY,
  scene_scope TEXT NOT NULL CHECK (scene_scope IN ('sparse','continuous')),
  fact_scope TEXT NOT NULL CHECK (fact_scope IN ('none','partial','reviewed')),
  current_anchor_id TEXT REFERENCES timeline_points(point_id) ON DELETE SET NULL,
  note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS fact_extractions (
  scene_key TEXT NOT NULL,
  scene_hash TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  model TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok','failed')),
  raw_json TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (scene_key,scene_hash,prompt_version,model)
);

CREATE TABLE IF NOT EXISTS archives (
  archive_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('operator','npc','enemy')),
  name TEXT NOT NULL,
  appellation TEXT NOT NULL DEFAULT '',
  subject_ids TEXT NOT NULL,
  archive_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_archives_name ON archives(name);

CREATE TABLE IF NOT EXISTS archive_sections (
  archive_id TEXT NOT NULL REFERENCES archives(archive_id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  version INTEGER NOT NULL,
  title TEXT NOT NULL,
  text TEXT NOT NULL,
  unlock_type TEXT NOT NULL,
  unlock_param TEXT NOT NULL,
  forms TEXT NOT NULL,
  hidden INTEGER NOT NULL CHECK (hidden IN (0,1)),
  PRIMARY KEY (archive_id, seq, version)
);

CREATE TABLE IF NOT EXISTS entity_archives (
  entity_id INTEGER NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
  archive_id TEXT NOT NULL,
  PRIMARY KEY (entity_id, archive_id)
);
