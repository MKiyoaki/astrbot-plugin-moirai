"""Resumable, evidence-bound fact candidate extraction for the whole canon library."""
from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict

from .store import now_iso
from .temporal import FACT_PROMPT_VERSION, PREDICATES

MAX_PROMPT_CHARS = 6500
MAX_ATTEMPTS = 4
POLARITY_TEXT = {"1": 1, "0": 0, "-1": 0, "true": 1, "false": 0, "yes": 1, "no": 0,
                 "positive": 1, "negative": 0, "肯定": 1, "否定": 0, "是": 1, "否": 0}
SYSTEM_PROMPT = (
    "从给定剧情事件与证据行中提出可核验的状态事实候选。只写明确发生或明确说出的"
    "地点、拘押、组织归属、存活状态。场景可能包含回忆；不要推测世界时间、当前状态、"
    "跨场景先后或有效期终点。每条只陈述一个主体、一个谓词和一个客体。"
    "证据必须是所给事件下的原样行 ID；片段不完整时不猜测。只输出 JSON，格式为 "
    '{"facts":[{"subject":"人物名","predicate":"location|custody|affiliation|life_status",'
    '"object":"值","polarity":1,"event_id":"原样事件ID","line_key":"原样证据行ID"}]}。'
    "没有可靠状态事实时返回空数组。"
)


def normalize_polarity(value: object) -> int | None:
    """The prompt only shows polarity 1; models write negation as false, -1 or "0", so every form maps to 1 or 0."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)) and value in (1, 0, -1):
        return 1 if value == 1 else 0
    if isinstance(value, str):
        return POLARITY_TEXT.get(value.strip().lower())
    return None


def validate_candidates(obj: object, allowed: dict[str, set[str]]) -> list[dict]:
    if not isinstance(obj, dict) or not isinstance(obj.get("facts"), list):
        raise ValueError("事实候选 JSON 缺少 facts 数组")
    output = []
    for item in obj["facts"]:
        if not isinstance(item, dict):
            raise ValueError("事实候选必须是对象")
        if item.get("predicate") not in PREDICATES:
            raise ValueError("事实候选的谓词不合法")
        event_id, line_key = item.get("event_id"), item.get("line_key")
        if event_id not in allowed or line_key not in allowed[event_id]:
            raise ValueError("事实候选引用了本块外或不在事件证据里的行")
        for key in ("subject", "object"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"事实候选缺少 {key}")
        polarity = normalize_polarity(item.get("polarity"))
        if polarity is None:
            raise ValueError(f"事实候选极性不合法：{item.get('polarity')!r}")
        output.append({
            "subject": item["subject"].strip(), "predicate": item["predicate"],
            "object": item["object"].strip(), "polarity": polarity,
            "event_id": event_id, "line_key": line_key,
            "review_status": "candidate", "prompt_version": FACT_PROMPT_VERSION,
        })
    return output


def plan_chunks(anchor: str, rows: list[dict], limit: int = MAX_PROMPT_CHARS) -> list[dict]:
    """Split at evidence lines, repeating event context and preserving real line IDs."""
    if limit < 500:
        raise ValueError("分块字符上限过小")
    chunks = []
    current = []
    allowed: dict[str, set[str]] = defaultdict(set)
    current_event = None
    prefix = f"[场景] {anchor}\n"
    size = len(prefix)

    def flush():
        nonlocal current, allowed, current_event, size
        if current:
            prompt = prefix + "\n".join(current)
            chunks.append({"prompt": prompt, "allowed": dict(allowed),
                           "signature": hashlib.sha256(prompt.encode("utf-8")).hexdigest()})
        current, allowed, current_event, size = [], defaultdict(set), None, len(prefix)

    for row in rows:
        event_id = row["event_id"]
        head = (f"事件 {event_id}（{row['in_world_time']}）：{row['topic']}；{row['summary']}")
        line_key = row["line_key"]
        source = row["text"]
        while source:
            header = head if current_event != event_id else ""
            overhead = len(header) + len(line_key) + 8
            space = limit - size - overhead
            if space < 100 and current:
                flush()
                continue
            if space < 1:
                raise ValueError(f"事件标题超过分块上限：{event_id}")
            part, source = source[:space], source[space:]
            if header:
                current.append(header)
                size += len(header) + 1
                current_event = event_id
            current.append(f"  {line_key}：{part}" + (" [续]" if source else ""))
            size += len(line_key) + len(part) + 6
            allowed[event_id].add(line_key)
            if source:
                flush()
    flush()
    return chunks


def _parse(raw, allowed):
    raw = getattr(raw, "completion_text", raw)
    if not isinstance(raw, str):
        raise ValueError("模型没有返回文本")
    body = raw.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return validate_candidates(json.loads(body), allowed)


async def _save(store, scene_key, scene_hash, model, status, state, error=None):
    async with store._lock:
        await store.db.execute(
            "INSERT OR REPLACE INTO fact_extractions VALUES (?,?,?,?,?,?,?,?)",
            (scene_key, scene_hash, FACT_PROMPT_VERSION, model, status,
             json.dumps(state, ensure_ascii=False), error, now_iso()),
        )


async def suggest_scene(store, scene_key: str, call, model: str, *, max_attempts: int = MAX_ATTEMPTS) -> dict:
    db = store.db
    async with db.execute("SELECT scene_hash,anchor FROM scenes WHERE scene_key=?", (scene_key,)) as cur:
        scene = await cur.fetchone()
    if scene is None:
        raise ValueError(f"场景不在数据库里：{scene_key}")
    async with db.execute(
        "SELECT status,raw_json FROM fact_extractions WHERE scene_key=? AND scene_hash=? "
        "AND prompt_version=? AND model=?",
        (scene_key, scene["scene_hash"], FACT_PROMPT_VERSION, model),
    ) as cur:
        cached = await cur.fetchone()
    if cached and cached["status"] == "ok":
        return json.loads(cached["raw_json"])
    async with db.execute(
        "SELECT e.event_id,e.topic,e.summary,e.in_world_time,l.line_key,l.text FROM events e "
        "JOIN event_evidence x ON x.event_id=e.event_id "
        "JOIN lines l ON l.line_key=x.line_key WHERE e.scene_key=? "
        "ORDER BY e.ord,x.ord", (scene_key,),
    ) as cur:
        rows = [dict(row) for row in await cur.fetchall()]
    if not rows:
        result = {"scene_key": scene_key, "scene_hash": scene["scene_hash"],
                  "prompt_version": FACT_PROMPT_VERSION, "chunks": 0, "facts": []}
        await _save(store, scene_key, scene["scene_hash"], model, "ok", result)
        return result
    chunks = plan_chunks(scene["anchor"], rows)
    signatures = [chunk["signature"] for chunk in chunks]
    saved = json.loads(cached["raw_json"]) if cached and cached["raw_json"] else {}
    completed = saved.get("completed", {}) if saved.get("signatures") == signatures else {}
    state = {"scene_key": scene_key, "scene_hash": scene["scene_hash"],
             "prompt_version": FACT_PROMPT_VERSION, "signatures": signatures, "completed": completed}
    for index, chunk in enumerate(chunks):
        key = str(index)
        if key in completed:
            continue
        error = None
        for attempt in range(max_attempts):
            try:
                raw = await call(chunk["prompt"], SYSTEM_PROMPT)
                completed[key] = _parse(raw, chunk["allowed"])
                await _save(store, scene_key, scene["scene_hash"], model, "failed", state, "incomplete")
                break
            except Exception as exc:
                error = f"块 {index + 1}/{len(chunks)}，尝试 {attempt + 1}/{max_attempts}：{type(exc).__name__}: {exc}"
        else:
            await _save(store, scene_key, scene["scene_hash"], model, "failed", state, error[:500])
            raise ValueError(f"{scene_key} {error}")
    facts = list(dict.fromkeys(
        (f["subject"], f["predicate"], f["object"], f["polarity"], f["event_id"], f["line_key"])
        for index in range(len(chunks)) for f in completed[str(index)]
    ))
    result = {"scene_key": scene_key, "scene_hash": scene["scene_hash"],
              "prompt_version": FACT_PROMPT_VERSION, "chunks": len(chunks), "facts": [
                  {"subject": sub, "predicate": pred, "object": obj, "polarity": pol,
                   "event_id": event, "line_key": line, "review_status": "candidate",
                   "prompt_version": FACT_PROMPT_VERSION}
                  for sub, pred, obj, pol, event, line in facts]}
    await _save(store, scene_key, scene["scene_hash"], model, "ok", result)
    return result


async def suggest_all(store, keys: list[str], call, model: str, *, concurrency: int = 2, progress=None) -> dict:
    """Process every selected scene, retaining chunk progress and reporting failures."""
    sem = asyncio.Semaphore(max(1, concurrency))
    results = {}
    errors = {}
    async def process(key):
        try:
            async with sem:
                results[key] = await suggest_scene(store, key, call, model)
            if progress:
                progress(key, "ok", len(results[key]["facts"]))
        except Exception as exc:
            errors[key] = f"{type(exc).__name__}: {exc}"
            if progress:
                progress(key, "failed", errors[key])
    await asyncio.gather(*(process(key) for key in keys))
    return {"selected": len(keys), "complete": len(results), "failed": len(errors),
            "candidates": sum(len(r["facts"]) for r in results.values()),
            "chunks": sum(r["chunks"] for r in results.values()),
            "results": [results[key] for key in keys if key in results], "errors": errors}
