"""canon.sqlite 的读写：建表、FTS 模式、向量表、按场景整体替换、抽取缓存。

一个场景的场景行、台词行和全部抽取结果在同一个事务里写入，所以中途中断不会留下半个场景；
场景的 scene_hash 只在这个事务里更新，导入器据此判断哪些场景还没做完。
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "2"
_SCHEMA = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
_PRAGMAS = ("PRAGMA foreign_keys=ON", "PRAGMA journal_mode=WAL", "PRAGMA busy_timeout=5000",
            "PRAGMA synchronous=NORMAL")
_TRIGRAM = """
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
  topic, summary, content='events', content_rowid='rid', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS events_fts_ai AFTER INSERT ON events BEGIN
  INSERT INTO events_fts(rowid, topic, summary) VALUES (new.rid, new.topic, new.summary);
END;
CREATE TRIGGER IF NOT EXISTS events_fts_ad AFTER DELETE ON events BEGIN
  INSERT INTO events_fts(events_fts, rowid, topic, summary) VALUES ('delete', old.rid, old.topic, old.summary);
END;
CREATE TRIGGER IF NOT EXISTS events_fts_au AFTER UPDATE ON events BEGIN
  INSERT INTO events_fts(events_fts, rowid, topic, summary) VALUES ('delete', old.rid, old.topic, old.summary);
  INSERT INTO events_fts(rowid, topic, summary) VALUES (new.rid, new.topic, new.summary);
END;
CREATE VIRTUAL TABLE IF NOT EXISTS beats_fts USING fts5(
  text, content='event_beats', content_rowid='rid', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS beats_fts_ai AFTER INSERT ON event_beats BEGIN
  INSERT INTO beats_fts(rowid, text) VALUES (new.rid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS beats_fts_ad AFTER DELETE ON event_beats BEGIN
  INSERT INTO beats_fts(beats_fts, rowid, text) VALUES ('delete', old.rid, old.text);
END;
CREATE TRIGGER IF NOT EXISTS beats_fts_au AFTER UPDATE ON event_beats BEGIN
  INSERT INTO beats_fts(beats_fts, rowid, text) VALUES ('delete', old.rid, old.text);
  INSERT INTO beats_fts(rowid, text) VALUES (new.rid, new.text);
END;
"""
_BIGRAM = "CREATE VIRTUAL TABLE IF NOT EXISTS events_fts_bigram USING fts5(event_id UNINDEXED, grams, tokenize='unicode61')"
_CJK_RUN = re.compile(r"[一-鿿]+")


def bigrams(text: str) -> list[str]:
    """把每段连续汉字切成 2 字片段（降级全文检索用），保持首次出现的顺序去重。"""
    out: dict[str, None] = {}
    for run in _CJK_RUN.findall(text or ""):
        for i in range(max(1, len(run) - 1)):
            out.setdefault(run[i:i + 2], None)
    return list(out)


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _serialized(fn):
    """同一连接上的事务不能交错：所有写操作排队执行。"""
    async def wrapper(self, *args, **kwargs):
        async with self._lock:
            return await fn(self, *args, **kwargs)
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    return wrapper


class CanonStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.db: aiosqlite.Connection | None = None
        self.fts_mode = ""
        self.vec_enabled = False
        self.vec_dim = 0
        self._vec_table = False
        self._lock = asyncio.Lock()

    # ── 打开与关闭 ────────────────────────────────────────────────────────────

    async def open(self, *, vec_dim: int = 0, encoder_id: str = "") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(str(self.path), isolation_level=None)
        self.db.row_factory = aiosqlite.Row
        for pragma in _PRAGMAS:
            await self.db.execute(pragma)
        await self.db.executescript(_SCHEMA)
        await self._init_fts()
        await self._init_vec(vec_dim, encoder_id)
        await self.set_meta(schema_version=SCHEMA_VERSION, fts_mode=self.fts_mode, vec_dim=str(self.vec_dim))

    async def close(self) -> None:
        if self.db is not None:
            await self.db.close()
            self.db = None

    async def _init_fts(self) -> None:
        mode = (await self.get_meta()).get("fts_mode")
        if mode != "bigram":
            try:
                await self.db.executescript(_TRIGRAM)
                self.fts_mode = "trigram"
                return
            except Exception as exc:
                if mode == "trigram":
                    raise
                logger.warning("[canon] FTS5 trigram unavailable, using bigram fallback: %s", exc)
        await self.db.execute(_BIGRAM)
        self.fts_mode = "bigram"

    async def _init_vec(self, dim: int, encoder_id: str) -> None:
        try:
            import sqlite_vec  # noqa: PLC0415

            await self.db.enable_load_extension(True)
            await self.db.load_extension(sqlite_vec.loadable_path())
            await self.db.enable_load_extension(False)
        except Exception as exc:
            logger.warning("[canon] sqlite-vec unavailable, vector recall disabled: %s", exc)
            self.vec_enabled, self.vec_dim = False, 0
            return
        meta = await self.get_meta()
        old_dim, old_id = int(meta.get("vec_dim") or 0), meta.get("encoder_id", "")
        if dim <= 0:
            async with self.db.execute("SELECT 1 FROM sqlite_master WHERE name='event_vec'") as cur:
                self._vec_table = await cur.fetchone() is not None
            self.vec_enabled, self.vec_dim = False, 0
            return
        if old_dim != dim or old_id != encoder_id:
            # encoder 变了：清空向量，之后由导入器用本地 encoder 重新编码，不需要调用大模型
            await self.db.execute("DROP TABLE IF EXISTS event_vec")
            await self.db.execute("DELETE FROM event_vec_map")
        await self.db.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS event_vec USING vec0(embedding float[{dim}])")
        await self.set_meta(encoder_id=encoder_id)
        self.vec_enabled, self.vec_dim, self._vec_table = True, dim, True

    # ── meta ─────────────────────────────────────────────────────────────────

    async def get_meta(self) -> dict[str, str]:
        async with self.db.execute("SELECT key, value FROM meta") as cur:
            return {r["key"]: r["value"] for r in await cur.fetchall()}

    async def set_meta(self, **values) -> None:
        await self.db.executemany("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                                  [(k, str(v)) for k, v in values.items()])

    # ── 场景 ─────────────────────────────────────────────────────────────────

    async def scene_hashes(self) -> dict[str, str]:
        async with self.db.execute("SELECT scene_key, scene_hash FROM scenes") as cur:
            return {r["scene_key"]: r["scene_hash"] for r in await cur.fetchall()}

    async def ok_extraction_keys(self, prompt_version: str) -> set[tuple[str, str]]:
        async with self.db.execute(
                "SELECT scene_key, scene_hash FROM extractions WHERE status='ok' AND prompt_version=?",
                (prompt_version,)) as cur:
            return {(r["scene_key"], r["scene_hash"]) for r in await cur.fetchall()}

    async def _delete_scene_rows(self, scene_key: str) -> None:
        async with self.db.execute("SELECT event_id FROM events WHERE scene_key=?", (scene_key,)) as cur:
            event_ids = [r["event_id"] for r in await cur.fetchall()]
        if event_ids:
            marks = ",".join("?" * len(event_ids))
            if self._vec_table:
                await self.db.execute(
                    f"DELETE FROM event_vec WHERE rowid IN (SELECT vec_rowid FROM event_vec_map WHERE event_id IN ({marks}))",
                    event_ids)
            if self.fts_mode == "bigram":
                await self.db.execute(f"DELETE FROM events_fts_bigram WHERE event_id IN ({marks})", event_ids)
        await self.db.execute("DELETE FROM scenes WHERE scene_key=?", (scene_key,))

    @_serialized
    async def delete_scene(self, scene_key: str) -> None:
        await self.db.execute("BEGIN")
        try:
            await self._delete_scene_rows(scene_key)
            await self.db.execute("COMMIT")
        except Exception:
            await self.db.execute("ROLLBACK")
            raise

    @_serialized
    async def apply_scene(self, scene: dict, result: dict | None, character: dict) -> int:
        """在一个事务里用新内容替换整个场景，返回写入的事件数。result 为 None 表示抽取失败，只写场景和台词。"""
        key = scene["scene_key"]
        line_keys = [line["k"] for line in scene["lines"]]

        def lk(ref: str) -> str:
            return line_keys[int(ref[1:]) - 1]

        await self.db.execute("BEGIN")
        try:
            await self._delete_scene_rows(key)
            await self.db.execute(
                "INSERT INTO scenes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (key, scene["scene_hash"], scene["narrative_pos"], scene["anchor"], scene.get("category"),
                 scene["tier"], scene.get("collection_id"), scene.get("collection_name"), scene.get("chapter_no"),
                 scene.get("story_code"), scene.get("story_name"), scene.get("avg_tag"), scene.get("release_date"),
                 scene.get("official_summary"), scene.get("prev_scene_key")))
            await self.db.executemany(
                "INSERT INTO lines VALUES (?,?,?,?,?,?,?,?,?)",
                [(line["k"], key, i, line["kind"], line.get("spk"), line.get("sid"), line.get("por"),
                  line["text"], int(line.get("nick") or 0)) for i, line in enumerate(scene["lines"], 1)])
            count = 0
            if result is not None:
                count = await self._write_result(scene, result, character, lk)
            await self.db.execute("COMMIT")
            return count
        except Exception:
            await self.db.execute("ROLLBACK")
            raise

    async def _write_result(self, scene: dict, result: dict, character: dict, lk) -> int:
        key, char_id = scene["scene_key"], character["character"]
        event_id = {ev["id"]: f"{key}@{ev['id']}" for ev in result["events"]}
        for ord_, ev in enumerate(result["events"]):
            eid = event_id[ev["id"]]
            parts = [p.strip() for p in ev["participants"]]
            await self.db.execute(
                "INSERT INTO events(event_id, scene_key, local_id, ord, topic, summary, in_world_time, "
                "in_world_note, participants, involves_doctor, narrative_pos) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (eid, key, ev["id"], ord_, ev["topic"].strip(), ev["summary"].strip(), ev["in_world_time"],
                 (ev.get("in_world_note") or "").strip() or None, json.dumps(parts, ensure_ascii=False),
                 int("@doctor" in parts), scene["narrative_pos"]))
            refs = list(dict.fromkeys(lk(r) for r in ev["evidence"]))
            await self.db.executemany("INSERT INTO event_evidence VALUES (?,?,?)",
                                      [(eid, ref, i) for i, ref in enumerate(refs)])
            beats = ev.get("beats") or []
            await self.db.executemany(
                "INSERT INTO event_beats(event_id, ord, text, evidence) VALUES (?,?,?,?)",
                [(eid, j, beat["text"].strip(),
                  json.dumps(list(dict.fromkeys(lk(r) for r in beat["evidence"])), ensure_ascii=False))
                 for j, beat in enumerate(beats)])
            for ent in ev.get("entities") or []:
                entity = await self._entity_for(ent["name"].strip(), ent["type"])
                await self.db.execute("INSERT OR IGNORE INTO event_entities VALUES (?,?)", (eid, entity))
            if self.fts_mode == "bigram":
                await self.db.execute("INSERT INTO events_fts_bigram(event_id, grams) VALUES (?,?)",
                                      (eid, " ".join(bigrams(" ".join([ev["topic"], ev["summary"],
                                                                        *(b["text"] for b in beats)])))))
        for view in result["views"]:
            eid = event_id[view["event"]]
            await self.db.execute("INSERT INTO views VALUES (?,?,?,?)",
                                  (char_id, eid, view["channel"], (view.get("note") or "").strip() or None))
            await self.db.executemany("INSERT OR IGNORE INTO view_evidence VALUES (?,?,?)",
                                      [(char_id, eid, lk(r)) for r in view.get("evidence") or []])
        if result.get("episode"):
            await self.db.execute("INSERT INTO episodes VALUES (?,?,?)",
                                  (char_id, key, result["episode"]["text"].strip()))
        for ord_, cog in enumerate(result["cognitions"]):
            await self.db.execute("INSERT INTO cognitions VALUES (?,?,?,?,?,?)",
                                  (char_id, key, ord_, cog["target"].strip(), cog["stance"].strip(),
                                   json.dumps([lk(r) for r in cog["evidence"]], ensure_ascii=False)))
        for edge in result["edges"]:
            await self.db.execute(
                "INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?)",
                (event_id[edge["from"]], event_id[edge["to"]], edge["type"], int(edge["explicit"]),
                 float(edge["confidence"]),
                 json.dumps([lk(r) for r in edge.get("evidence") or []], ensure_ascii=False)))
        return len(result["events"])

    # ── 实体 ─────────────────────────────────────────────────────────────────

    async def _entity_for(self, name: str, type_: str) -> int:
        """名字已经是某个实体的别名就复用那个实体，否则新增一个 extracted 实体。"""
        async with self.db.execute("SELECT entity_id FROM aliases WHERE alias=?", (name,)) as cur:
            row = await cur.fetchone()
        if row:
            return row["entity_id"]
        async with self.db.execute("SELECT entity_id FROM entities WHERE name=?", (name,)) as cur:
            row = await cur.fetchone()
        if row:
            return row["entity_id"]
        cur = await self.db.execute("INSERT INTO entities(name, type, source) VALUES (?,?, 'extracted')",
                                    (name, type_))
        await self.db.execute("INSERT OR IGNORE INTO aliases VALUES (?,?)", (name, cur.lastrowid))
        return cur.lastrowid

    @_serialized
    async def seed_entities(self, seeds: list[dict]) -> int:
        """第一次导入时写入实体种子；已经写过就跳过。返回写入的实体数。"""
        async with self.db.execute("SELECT COUNT(*) FROM entities WHERE source='seed'") as cur:
            if (await cur.fetchone())[0]:
                return 0
        await self.db.execute("BEGIN")
        try:
            for seed in seeds:
                await self.db.execute("INSERT OR IGNORE INTO entities(name, type, source) VALUES (?,?, 'seed')",
                                      (seed["name"], seed.get("type", "person")))
                async with self.db.execute("SELECT entity_id FROM entities WHERE name=?", (seed["name"],)) as cur:
                    entity = (await cur.fetchone())[0]
                await self.db.executemany("INSERT OR IGNORE INTO aliases VALUES (?,?)",
                                          [(a, entity) for a in dict.fromkeys([seed["name"], *seed.get("aliases", [])])])
            await self.db.execute("COMMIT")
        except Exception:
            await self.db.execute("ROLLBACK")
            raise
        return len(seeds)

    # ── 抽取缓存 ─────────────────────────────────────────────────────────────

    async def cached_extraction(self, scene_key: str, scene_hash: str, prompt_version: str) -> dict | None:
        async with self.db.execute(
                "SELECT raw_json FROM extractions WHERE scene_key=? AND scene_hash=? AND prompt_version=? "
                "AND status='ok'", (scene_key, scene_hash, prompt_version)) as cur:
            row = await cur.fetchone()
        return json.loads(row["raw_json"]) if row else None

    @_serialized
    async def put_extraction(self, scene_key: str, scene_hash: str, prompt_version: str, model: str, outcome) -> None:
        await self.db.execute(
            "INSERT OR REPLACE INTO extractions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (scene_key, scene_hash, prompt_version, model, outcome.status,
             json.dumps(outcome.result, ensure_ascii=False) if outcome.result is not None else None,
             outcome.error, outcome.attempts, outcome.prompt_tokens, outcome.completion_tokens, now_iso()))

    # ── 向量 ─────────────────────────────────────────────────────────────────

    async def events_without_vectors(self) -> list[tuple[str, str]]:
        """返回还没有向量的事件：(event_id, 编码文本)。{DOCTOR} 换成"博士"。"""
        async with self.db.execute(
                "SELECT e.event_id, e.topic, e.summary FROM events e "
                "LEFT JOIN event_vec_map m ON m.event_id = e.event_id WHERE m.event_id IS NULL "
                "ORDER BY e.narrative_pos, e.ord") as cur:
            rows = await cur.fetchall()
        return [(r["event_id"], f"{r['topic']}：{r['summary']}".replace("{DOCTOR}", "博士")) for r in rows]

    @_serialized
    async def put_vectors(self, items: list[tuple[str, list[float]]]) -> None:
        if not self.vec_enabled:
            return
        await self.db.execute("BEGIN")
        try:
            for event_id, vec in items:
                cur = await self.db.execute("INSERT INTO event_vec(embedding) VALUES (?)", (json.dumps(vec),))
                await self.db.execute("INSERT INTO event_vec_map VALUES (?,?)", (cur.lastrowid, event_id))
            await self.db.execute("COMMIT")
        except Exception:
            await self.db.execute("ROLLBACK")
            raise

    # ── 查询：状态与审阅 ─────────────────────────────────────────────────────

    async def counts(self, prompt_version: str) -> dict[str, int]:
        out = {}
        for name, sql in (
                ("scenes", "SELECT COUNT(*) FROM scenes"),
                ("events", "SELECT COUNT(*) FROM events"),
                ("beats", "SELECT COUNT(*) FROM event_beats"),
                ("entities", "SELECT COUNT(*) FROM entities"),
                ("vectors", "SELECT COUNT(*) FROM event_vec_map"),
                ("failed_scenes", "SELECT COUNT(*) FROM scenes s WHERE NOT EXISTS (SELECT 1 FROM extractions x "
                                  "WHERE x.scene_key=s.scene_key AND x.scene_hash=s.scene_hash "
                                  "AND x.prompt_version=? AND x.status='ok')")):
            params = (prompt_version,) if "?" in sql else ()
            async with self.db.execute(sql, params) as cur:
                out[name] = (await cur.fetchone())[0]
        return out

    async def scene_dump(self, scene_key: str) -> dict | None:
        async def rows(sql, *params):
            async with self.db.execute(sql, params) as cur:
                return [dict(r) for r in await cur.fetchall()]

        scene = await rows("SELECT * FROM scenes WHERE scene_key=?", scene_key)
        if not scene:
            return None
        out = scene[0]
        out["lines"] = await rows("SELECT * FROM lines WHERE scene_key=? ORDER BY idx", scene_key)
        out["events"] = await rows("SELECT * FROM events WHERE scene_key=? ORDER BY ord", scene_key)
        for ev in out["events"]:
            ev["evidence"] = [r["line_key"] for r in await rows(
                "SELECT line_key FROM event_evidence WHERE event_id=? ORDER BY ord", ev["event_id"])]
            ev["beats"] = [{"text": r["text"], "evidence": json.loads(r["evidence"])} for r in await rows(
                "SELECT text, evidence FROM event_beats WHERE event_id=? ORDER BY ord", ev["event_id"])]
            ev["views"] = await rows("SELECT character, channel, note FROM views WHERE event_id=?", ev["event_id"])
            for view in ev["views"]:
                view["evidence"] = [r["line_key"] for r in await rows(
                    "SELECT line_key FROM view_evidence WHERE event_id=? AND character=?",
                    ev["event_id"], view["character"])]
            ev["entities"] = await rows(
                "SELECT n.name, n.type FROM event_entities x JOIN entities n USING(entity_id) WHERE x.event_id=?",
                ev["event_id"])
        out["episodes"] = await rows("SELECT character, text FROM episodes WHERE scene_key=?", scene_key)
        out["cognitions"] = await rows("SELECT * FROM cognitions WHERE scene_key=? ORDER BY ord", scene_key)
        out["edges"] = await rows(
            "SELECT e.* FROM edges e JOIN events v ON v.event_id = e.src WHERE v.scene_key=?", scene_key)
        out["extraction"] = (await rows(
            "SELECT status, error, attempts, model, prompt_version, prompt_tokens, completion_tokens, created_at "
            "FROM extractions WHERE scene_key=? AND scene_hash=? ORDER BY created_at DESC LIMIT 1",
            scene_key, out["scene_hash"]) or [None])[0]
        return out
