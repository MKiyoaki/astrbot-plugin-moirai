"""Per-segment summary embeddings: write them next to the event vector, read them back for injection.

A stored vector counts only while its segment text hash and encoder identity still match, so
summary edits, re-extraction and a model switch simply make it stale. Injection reads stored
vectors only; missing vectors use the lexical pick while the manager queues a backfill.
"""
from __future__ import annotations

import hashlib
import json
import logging

from ..extractor.summary import split_subtopics

logger = logging.getLogger(__name__)


def segments_of(summary: str) -> list[str]:
    return split_subtopics(summary or "")


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def identity_key(encoder) -> str:
    identity = getattr(encoder, "identity", None)
    if isinstance(identity, dict) and identity:
        return json.dumps(identity, sort_keys=True, ensure_ascii=False)
    name = getattr(encoder, "_model_name", "") or type(encoder).__name__
    return f"{type(encoder).__name__}:{name}:{getattr(encoder, 'dim', 0)}"


def _active(encoder) -> bool:
    try:
        return encoder is not None and encoder.dim > 0 and getattr(encoder, "active", True)
    except Exception:
        return False


async def index_segments(repo, encoder, events) -> None:
    """Embed every summary segment of the given events in one batch and store them."""
    if not _active(encoder):
        return
    work = [(event, segments_of(event.summary)) for event in events]
    texts = [s for _, segs in work for s in segs]
    if not texts:
        return
    identity = identity_key(encoder)
    vectors = await encoder.encode_batch(texts)
    if identity_key(encoder) != identity:
        return
    if len(vectors) != len(texts) or any(not vector for vector in vectors):
        raise ValueError("segment encoder returned incomplete vectors")
    cursor = 0
    for event, segs in work:
        items = [(i, text_hash(s), vectors[cursor + i]) for i, s in enumerate(segs)]
        cursor += len(segs)
        if items:
            await repo.upsert_segment_vectors(event.event_id, identity, items)


async def segment_vectors(repo, encoder, events, *, missing: list | None = None) -> dict[str, list[list[float]]] | None:
    """Read stored vectors only; report incomplete events without invoking the encoder."""
    if not _active(encoder) or not events:
        return None
    identity = identity_key(encoder)
    try:
        stored = await repo.get_segment_vectors([e.event_id for e in events], identity)

        def complete(event) -> list[list[float]] | None:
            have = stored.get(event.event_id, {})
            out = []
            for i, seg in enumerate(segments_of(event.summary)):
                entry = have.get(i)
                if entry is None or entry[0] != text_hash(seg):
                    return None
                out.append(entry[1])
            return out

        incomplete = [e for e in events if complete(e) is None]
        if incomplete:
            if missing is not None:
                missing.extend(incomplete)
            return None
        result = {}
        for event in events:
            vectors = complete(event)
            if vectors is None:
                return None
            result[event.event_id] = vectors
        return result
    except Exception as exc:
        logger.warning("[segments] segment vectors unavailable: %s", exc)
        return None
