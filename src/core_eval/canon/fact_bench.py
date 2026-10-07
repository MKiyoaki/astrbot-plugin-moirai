"""时间事实候选的基准步骤：全范围抽取、写审阅页、在一次基准运行里统计候选。"""
from __future__ import annotations

import json
from pathlib import Path

from core.canon.storage.store import CanonStore
from core.utils.prompts.prompt_canon_utils import PROMPT_VERSION

from .review_page import review_page


async def run_fact_pipeline(store, keys: list[str], call, model: str, out: Path,
                            *, concurrency: int = 2) -> dict:
    """Extract all eligible scenes and write resumable review artifacts."""
    import sqlite3
    import time
    from core.canon.builder.fact_extract import suggest_all
    from core.canon.builder.fact_review import build_review_bundle

    if any(path.exists() for path in (out, out.with_suffix(".review.json"), out.with_suffix(".report.json"))):
        raise ValueError(f"事实输出文件已存在，拒绝覆盖：{out}")
    eligible, skipped = [], {}
    for scene_key in keys:
        async with store.db.execute(
            "SELECT x.status FROM scenes s LEFT JOIN extractions x ON "
            "x.scene_key=s.scene_key AND x.scene_hash=s.scene_hash AND x.prompt_version=? "
            "WHERE s.scene_key=?", (PROMPT_VERSION, scene_key),
        ) as cur:
            row = await cur.fetchone()
        if row and row["status"] == "ok":
            eligible.append(scene_key)
        else:
            skipped[scene_key] = "缺少当前版本的成功事件抽取"
    done = [0]
    def progress(key, status, detail):
        done[0] += 1
        print(f"  [facts {done[0]}/{len(eligible)}] {status:6} {key}：{detail}", flush=True)
    calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    async def measured_call(prompt, system_prompt):
        nonlocal calls, prompt_tokens, completion_tokens
        calls += 1
        response = await call(prompt, system_prompt)
        usage = getattr(response, "usage", None)
        if isinstance(usage, dict):
            prompt_tokens += usage.get("prompt_tokens") or 0
            completion_tokens += usage.get("completion_tokens") or 0
        return response
    started = time.monotonic()
    report = await suggest_all(store, eligible, measured_call, model,
                               concurrency=concurrency, progress=progress)
    report["selected"] = len(keys)
    report["skipped"] = skipped
    report["model_calls"] = calls
    report["prompt_tokens"] = prompt_tokens
    report["completion_tokens"] = completion_tokens
    report["wall_seconds"] = round(time.monotonic() - started, 2)
    results = report.pop("results")
    report["scenes_with_candidates"] = sum(bool(result["facts"]) for result in results)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for result in results:
            fh.write(json.dumps(result, ensure_ascii=False) + "\n")
    db = sqlite3.connect(store.path)
    db.row_factory = sqlite3.Row
    try:
        bundle = build_review_bundle(db, results)
    finally:
        db.close()
    report["review_groups"] = len(bundle["review_groups"])
    out.with_suffix(".review.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_suffix(".report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


async def write_fact_review_page(store, keys: list[str], report: dict, out: Path,
                                 review_out: Path) -> None:
    """Render the event and fact-candidate review page from one completed fact pass."""
    candidates = {item["scene_key"]: item["facts"] for item in
                  (json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line)}
    dumps = []
    for key in keys:
        scene = await store.scene_dump(key)
        if scene is None:
            continue
        if key in candidates:
            scene["fact_candidates"] = candidates[key]
        scene["fact_error"] = report["errors"].get(key) or report["skipped"].get(key)
        dumps.append(scene)
    review_out.write_text(review_page(dumps), encoding="utf-8")


async def run_fact_benchmark(run_dir: Path, keys: list[str], call, model: str,
                             *, concurrency: int = 2, out: Path | None = None) -> dict:
    """Run the candidate stage and add its result to the benchmark report."""
    from core_eval.canon.bench import write_fact_summary
    out = out or run_dir / "facts-candidates.jsonl"
    store = CanonStore(run_dir / "canon.sqlite")
    await store.open()
    try:
        report = await run_fact_pipeline(store, keys, call, model, out, concurrency=concurrency)
        await write_fact_review_page(store, keys, report, out, run_dir / "review.html")
    finally:
        await store.close()
    write_fact_summary(run_dir, report, out)
    return report
