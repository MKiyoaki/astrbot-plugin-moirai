"""Resumable derived vector indexes over read-only canon event snapshots."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path

from ..embedding.remote import RetrievalError, normalized_vector

TEXT_RECIPE = "canon-event-topic-summary-participants-beats-v1"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Document:
    event_id: str
    text: str

    @property
    def content_hash(self) -> str:
        return digest(self.text)


def read_documents(source: Path, character: str = "amiya") -> list[Document]:
    db = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        beats: dict[str, list[str]] = {}
        for event_id, text in db.execute("SELECT event_id,text FROM event_beats ORDER BY event_id,ord"):
            beats.setdefault(event_id, []).append(text)
        rows = db.execute(
            "SELECT e.event_id,e.topic,e.summary,e.participants FROM events e "
            "JOIN views v ON v.event_id=e.event_id WHERE v.character=? ORDER BY e.event_id",
            (character,),
        ).fetchall()
        return [Document(eid, "\n".join((topic, summary, "参与者：" + "、".join(json.loads(parts)),
                                        *beats.get(eid, []))).replace("{DOCTOR}", "博士")
                         .replace("@doctor", "博士")) for eid, topic, summary, parts in rows]
    finally:
        db.close()


def corpus_fingerprint(documents: list[Document]) -> str:
    return digest(json.dumps([(d.event_id, d.content_hash) for d in documents], ensure_ascii=False))


def index_identity(settings, character: str) -> dict:
    return {**settings.identity, "recipe": TEXT_RECIPE, "character": character, "schema": 1}


def _load_vec(db: sqlite3.Connection) -> None:
    try:
        import sqlite_vec
        db.enable_load_extension(True)
        db.load_extension(sqlite_vec.loadable_path())
    except (ImportError, sqlite3.Error):
        raise RetrievalError("sqlite-vec is unavailable; use the existing Moirai environment") from None
    finally:
        db.enable_load_extension(False)


def _blob(vector: list[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


class VectorIndex:
    def __init__(self, path: Path, identity: dict, *, writable: bool = False) -> None:
        self.path, self.identity, self.writable = path, identity, writable
        if writable:
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path.resolve().as_uri() + ("?mode=rwc" if writable else "?mode=ro"),
                                  uri=True, timeout=10)
        try:
            _load_vec(self.db)
            if writable:
                self.db.executescript(
                    "CREATE TABLE IF NOT EXISTS index_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);"
                    "CREATE TABLE IF NOT EXISTS embedding_cache("
                    "content_hash TEXT PRIMARY KEY,vector BLOB NOT NULL);"
                    "CREATE TABLE IF NOT EXISTS documents("
                    "rid INTEGER PRIMARY KEY,event_id TEXT UNIQUE NOT NULL,content_hash TEXT NOT NULL);"
                )
            else:
                self.db.execute("PRAGMA query_only=ON")
            self.meta = dict(self.db.execute("SELECT key,value FROM index_meta"))
            encoded = json.dumps(identity, sort_keys=True)
            if self.meta.get("identity", encoded) != encoded:
                raise RetrievalError("Index model or text recipe differs; use another --index path")
            if "identity" not in self.meta:
                if not writable:
                    raise RetrievalError("Index has no model identity")
                self._set(identity=encoded)
            self.dimension = int(self.meta.get("dimension", 0))
        except BaseException:
            self.db.close()
            raise

    def close(self) -> None:
        self.db.close()

    def _set(self, **values) -> None:
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO index_meta VALUES (?,?)",
                                [(k, str(v)) for k, v in values.items()])
        self.meta.update({k: str(v) for k, v in values.items()})

    def missing(self, documents: list[Document]) -> list[Document]:
        cached = {row[0] for row in self.db.execute("SELECT content_hash FROM embedding_cache")}
        unique = {d.content_hash: d for d in documents if d.content_hash not in cached}
        return list(unique.values())

    def validate(self, documents: list[Document]) -> None:
        if (self.meta.get("status") != "ready"
                or self.meta.get("corpus") != corpus_fingerprint(documents)):
            raise RetrievalError("Vector index is incomplete or stale; run retrieval build for this canon DB")
        count = self.db.execute("SELECT count(*) FROM documents").fetchone()[0]
        if self.dimension <= 0 or count != len(documents):
            raise RetrievalError("Vector index coverage is incomplete")

    def _save(self, documents: list[Document], vectors: list[list[float]]) -> None:
        if len(documents) != len(vectors):
            raise RetrievalError("Embedding batch count mismatch")
        dimension = self.dimension or len(vectors[0])
        rows = [(d.content_hash, _blob(normalized_vector(v, dimension)))
                for d, v in zip(documents, vectors)]
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO embedding_cache VALUES (?,?)", rows)
            self.db.execute("INSERT OR REPLACE INTO index_meta VALUES ('dimension',?)", (str(dimension),))
        self.dimension = dimension
        self.meta["dimension"] = str(dimension)

    def build(self, documents: list[Document], client, *, batch_size: int = 16,
              concurrency: int = 2, progress=None) -> dict:
        if not self.writable or not documents:
            raise ValueError("A writable index and nonempty corpus are required")
        if not 1 <= batch_size <= 128 or not 1 <= concurrency <= 8:
            raise ValueError("batch-size must be 1..128; concurrency must be 1..8")
        started = time.perf_counter()
        missing = self.missing(documents)
        self._set(status="building")
        batches = iter([missing[i:i + batch_size] for i in range(0, len(missing), batch_size)])
        completed = 0
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            pending = {}

            def submit() -> None:
                batch = next(batches, None)
                if batch:
                    pending[pool.submit(client.embed, [d.text for d in batch])] = batch

            for _ in range(concurrency):
                submit()
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                failure = None
                for future in done:
                    batch = pending.pop(future)
                    try:
                        self._save(batch, future.result())
                        completed += len(batch)
                        if progress:
                            progress(completed, len(missing))
                    except Exception as exc:
                        failure = exc
                if failure:
                    for future, batch in pending.items():
                        try:
                            self._save(batch, future.result())
                        except Exception:
                            pass
                    raise failure
                for _ in done:
                    submit()
        self.db.execute("BEGIN")
        try:
            self.db.execute("DELETE FROM documents")
            self.db.execute("DROP TABLE IF EXISTS event_vectors")
            self.db.execute(f"CREATE VIRTUAL TABLE event_vectors USING vec0("
                            f"embedding float[{self.dimension}] distance_metric=cosine)")
            for rid, document in enumerate(documents, 1):
                vector = self.db.execute("SELECT vector FROM embedding_cache WHERE content_hash=?",
                                         (document.content_hash,)).fetchone()[0]
                self.db.execute("INSERT INTO documents VALUES (?,?,?)",
                                (rid, document.event_id, document.content_hash))
                self.db.execute("INSERT INTO event_vectors(rowid,embedding) VALUES (?,?)", (rid, vector))
            self.db.executemany("INSERT OR REPLACE INTO index_meta VALUES (?,?)",
                                [("status", "ready"), ("corpus", corpus_fingerprint(documents)),
                                 ("count", str(len(documents)))])
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        self.meta = dict(self.db.execute("SELECT key,value FROM index_meta"))
        missing_hashes = {m.content_hash for m in missing}
        return {"events": len(documents), "embedded_documents": len(missing),
                "reused_events": sum(d.content_hash not in missing_hashes for d in documents),
                "dimension": self.dimension, "corpus": self.meta["corpus"],
                "seconds": time.perf_counter() - started}

    def search(self, vector: list[float], limit: int) -> list[tuple[str, float]]:
        if limit < 1:
            raise ValueError("Vector candidate limit must be positive")
        normalized = normalized_vector(vector, self.dimension)
        rows = self.db.execute(
            "SELECT d.event_id,v.distance FROM event_vectors v JOIN documents d ON d.rid=v.rowid "
            "WHERE v.embedding MATCH ? AND k=? ORDER BY v.distance,d.event_id",
            (_blob(normalized), limit),
        ).fetchall()
        return [(event_id, 1.0 - distance) for event_id, distance in rows]
