"""Realtime dev runner — parses mock_realtime.json through the full memory pipeline
and serves results via WebUI at port 2656.

Usage:
    python run_realtime_dev.py            # auto: resume if prior session found, else build
    python run_realtime_dev.py --resume   # force resume, skip the prompt
    python run_realtime_dev.py --fresh    # force a full rebuild, skip the prompt
    python run_realtime_dev.py --self-test # offline regressions, no runtime DB or models

Persistence:
    .dev_data/realtime_test.db and the group summaries it generates are no longer
    wiped on exit. If a previous session's DB is found on startup, you'll be asked
    whether to resume (skips re-ingesting mock_realtime.json and re-running the LLM
    extraction/synthesis/summary pipeline — no token cost) or rebuild fresh (old
    data is archived under .dev_data/archive/, same as before).
    Run reset_realtime_dev.py for a full, unconditional wipe back to a clean slate.

Controls:
    Press Ctrl+Q  — stop (Windows)
    Type 'q' + Enter — stop (fallback / non-Windows)
    Ctrl+C        — emergency stop

Configurations:
    Default:   EVENT_MODE="llm" to validate the LLM extractor path first.
    1. LMStudio: API_URL="http://localhost:1234/v1" (override via LMSTUDIO_API_URL
       in run_config.py, e.g. FreeToken's "http://localhost:1919/v1"),
       API_KEY="lm-studio", MODEL="any"
    2. DeepSeek:  API_URL="https://api.deepseek.com", API_KEY="your_key", MODEL="deepseek-chat"
"""

import asyncio
import json
import shutil
import sys
import re
import threading
import time
from datetime import datetime
from pathlib import Path

# ── Diagnostics: verbose pipeline logging ────────────────────────────────────
# Dev-only — lives in this gitignored/dev-tooling script, does not touch any
# core/*.py production code. Surfaces the logger.debug/info calls that already
# exist in the extraction/embedding/LLM pipeline so a stuck run can be pinned
# to an exact line instead of guessed at. Toggle off with --quiet.
if "--quiet" not in sys.argv:
    import logging as _logging
    _logging.basicConfig(
        level=_logging.WARNING,
        format="%(asctime)s.%(msecs)03d [%(levelname)s][%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    for _name in (
        "core.extractor.extractor",
        "core.extractor.partitioner",
        "core.managers.embedding_manager",
        "core.managers.llm_manager",
        "core.adapters.astrbot",
    ):
        _logging.getLogger(_name).setLevel(_logging.DEBUG)

# ── tqdm with graceful fallback ──────────────────────────────────────────────

try:
    from tqdm import tqdm as _tqdm
    _TQDM_OK = True
except ImportError:
    _TQDM_OK = False

    class _tqdm:  # type: ignore[no-redef]
        def __init__(self, iterable=None, total=None, desc="", unit="it", **kw):
            self._it = iterable
            self._n = 0
            self._total = total
            self._desc = desc
            self._unit = unit

        def __iter__(self):
            for item in (self._it or []):
                yield item
                self._n += 1
                self._print()
            print()

        def update(self, n: int = 1) -> None:
            self._n += n
            self._print()

        def close(self) -> None:
            print()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            self.close()

        def _print(self):
            total_str = f"/{self._total}" if self._total else ""
            print(
                f"\r  {self._desc}: {self._n}{total_str} {self._unit}", end="", flush=True)


# ── LLM Configuration ────────────────────────────────────────────────────────

# Load local config (run_config.py is gitignored); fall back to defaults.
try:
    import run_config as _rc  # type: ignore[import]
    _EVENT_MODE      = _rc.EVENT_MODE
    _MOOD_SOURCE     = _rc.MOOD_SOURCE
    _TIMEOUT         = _rc.TIMEOUT
    _MODEL_TYPE      = _rc.MODEL_TYPE
    _LMSTUDIO_MODEL  = _rc.LMSTUDIO_MODEL
    _LMSTUDIO_API_URL = getattr(_rc, "LMSTUDIO_API_URL", "http://localhost:1234/v1")
    _DEEPSEEK_MODEL  = _rc.DEEPSEEK_MODEL
    _DEEPSEEK_KEY    = _rc.DEEPSEEK_API_KEY
    _RETRIEVAL_ENCODER_ENABLED = getattr(_rc, "RETRIEVAL_ENCODER_ENABLED", True)
    _RETRIEVAL_ENCODER_MODEL = getattr(_rc, "RETRIEVAL_ENCODER_MODEL", "BAAI/bge-small-zh-v1.5")
    _RETRIEVAL_ENCODER_BATCH_INTERVAL_MS = getattr(_rc, "RETRIEVAL_ENCODER_BATCH_INTERVAL_MS", 50)
    _RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS = getattr(_rc, "RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS", 0)
    _LLM_CONCURRENCY = getattr(_rc, "LLM_CONCURRENCY", 2)
    _RECALL_BENCHMARK_ENABLED = getattr(_rc, "RECALL_BENCHMARK_ENABLED", True)
    print(f"[Config] Loaded run_config.py  (model_type={_MODEL_TYPE})")
except Exception as _cfg_err:
    print(f"[Config] WARNING: run_config.py not loaded ({_cfg_err!r}), using built-in defaults.")
    _EVENT_MODE      = "llm"
    _MOOD_SOURCE     = "llm"
    _TIMEOUT         = 330.0
    _MODEL_TYPE      = "lmstudio"
    _LMSTUDIO_MODEL  = "gemma-4-26b-a4b-it-ultra-uncensored-heretic"
    _LMSTUDIO_API_URL = "http://localhost:1234/v1"
    _DEEPSEEK_MODEL  = "deepseek-v4-flash"
    _DEEPSEEK_KEY    = "your_deepseek_api_key_here"
    _RETRIEVAL_ENCODER_ENABLED = True
    _RETRIEVAL_ENCODER_MODEL = "BAAI/bge-small-zh-v1.5"
    _RETRIEVAL_ENCODER_BATCH_INTERVAL_MS = 50
    _RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS = 0
    _LLM_CONCURRENCY = 2
    _RECALL_BENCHMARK_ENABLED = True


def _get_model_info(model_type: str):
    if model_type == "lmstudio":
        llm_api_url = _LMSTUDIO_API_URL
        llm_api_key = "lm-studio"
        llm_model = _LMSTUDIO_MODEL
    elif model_type == "deepseek":
        llm_api_url = "https://api.deepseek.com"
        llm_api_key = _DEEPSEEK_KEY
        llm_model = _DEEPSEEK_MODEL
    else:
        raise ValueError("Not supported model type! ")
    return llm_api_url, llm_api_key, llm_model

LLM_API_URL, LLM_API_KEY, LLM_MODEL = _get_model_info(_MODEL_TYPE)

# ── Paths ─────────────────────────────────────────────────────────────────────

_ROOT = Path(__file__).parent
MOCK_DATA_PATH = _ROOT / "tests" / "mock_data" / "mock_realtime.json"
MOCK_PERSONA_PATH = _ROOT / "tests" / "mock_data" / "mock_persona.md"
DEV_DATA = _ROOT / ".dev_data"
ARCHIVE_DIR = DEV_DATA / "archive"
REALTIME_DB = DEV_DATA / "realtime_test.db"
DATAFLOW_DB = DEV_DATA / "dataflow_test.db"
# Stash for this script's own group summaries between runs, so a resumed
# session gets its markdown output back without re-running Phase 4.
REALTIME_GROUPS_STASH = DEV_DATA / "realtime_groups"
REALTIME_SETTINGS = DEV_DATA / "realtime_settings.json"
PORT = 2656

# Tracks where the previous groups/ directory was archived so _cleanup()
# can restore it on Ctrl+Q exit.
_archived_groups: Path | None = None


# ── Resume prompt ────────────────────────────────────────────────────────────

def _resume_requested() -> bool:
    """Decide whether to resume a prior session instead of rebuilding.

    --fresh / --resume on argv skip the interactive prompt. Otherwise, if no
    prior realtime_test.db exists there's nothing to resume, so build fresh
    silently; if one does exist, ask (default: resume).
    """
    if "--resume" in sys.argv and not REALTIME_DB.exists():
        raise SystemExit("No prior realtime database exists; choose --fresh explicitly.")
    if "--fresh" in sys.argv:
        return False
    if "--resume" in sys.argv:
        return True
    if not REALTIME_DB.exists():
        return False
    ans = input(
        "\n[Dev] 检测到已有测试数据 (.dev_data/realtime_test.db)。"
        "是否恢复上次会话进度，跳过重新构建？(Y/n): "
    ).strip().lower()
    return ans not in ("n", "no")


def _load_eval_setting() -> bool:
    if not REALTIME_SETTINGS.exists():
        print("[Dev] 旧会话没有评价开关记录；保留历史事件，本次重新提取默认关闭评价。")
        return False
    try:
        settings = json.loads(REALTIME_SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("[Dev] 评价开关记录无法读取；本次重新提取默认关闭评价。")
        return False
    return isinstance(settings, dict) and settings.get("persona_influenced_summary") is True


def _save_eval_setting(enabled: bool) -> None:
    REALTIME_SETTINGS.write_text(
        json.dumps({"persona_influenced_summary": enabled}), encoding="utf-8",
    )


# ── Archive step ──────────────────────────────────────────────────────────────

def _archive_step(resume: bool) -> None:
    """Back up existing DB files and relocate the summary dir before injection.

    When resuming, realtime_test.db is left untouched (it will be opened
    directly) and any stashed realtime_groups/ from the previous session is
    moved back into groups/ so the WebUI serves last session's summaries.
    """
    global _archived_groups

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not resume and REALTIME_DB.exists():
        dest = ARCHIVE_DIR / f"realtime_test_stale_{ts}.db"
        try:
            shutil.move(str(REALTIME_DB), str(dest))
            print(f"[Archive] Moved stale realtime_test.db → {dest.name}")
        except PermissionError:
            # Windows: DB file is still locked by a previous process.
            # Delete it in place so a fresh DB can be created.
            try:
                REALTIME_DB.unlink()
                print(
                    "[Archive] realtime_test.db was locked; deleted in place (no archive).")
            except PermissionError:
                print("[Archive] WARNING: realtime_test.db is locked and cannot be deleted. "
                      "Close any process holding it and retry.")
    elif resume:
        print(f"[Archive] Resuming — keeping existing realtime_test.db in place.")

    if DATAFLOW_DB.exists():
        dest = ARCHIVE_DIR / f"dataflow_test_{ts}.db"
        shutil.copy2(str(DATAFLOW_DB), str(dest))
        print(f"[Archive] Backed up dataflow_test.db → {dest.name}")

    # Move (not delete) the existing groups/ dir so it can be restored on exit.
    groups_dir = DEV_DATA / "groups"
    if groups_dir.exists():
        dest = ARCHIVE_DIR / f"groups_{ts}"
        shutil.move(str(groups_dir), str(dest))
        _archived_groups = dest
        print(
            f"[Archive] Moved summary dir → archive/groups_{ts}/ (will restore on exit)")

    if resume and REALTIME_GROUPS_STASH.exists():
        shutil.move(str(REALTIME_GROUPS_STASH), str(groups_dir))
        print("[Archive] Restored previous session's group summaries → groups/")


# ── Mock_Data.md parser ───────────────────────────────────────────────────────

def _parse_mock_data(path: Path) -> list[dict]:
    """Load mock messages from the JSON file."""
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Provider bridge for slow local LLMs ──────────────────────────────────────

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class _RealtimeProviderBridge:
    """LLM provider bridge tuned for Gemma 26B on LMStudio.

    Two differences from the stock MockProviderBridge:
    - httpx timeout 300 s (Gemma 26B thinking can take 60-90 s per call)
    - strips <think>…</think> blocks before returning so the JSON parser
      never sees interleaved reasoning text
    """

    def __init__(self, api_url: str, api_key: str, model: str) -> None:
        self._url = api_url.rstrip("/") + "/chat/completions"
        self._key = api_key
        self._model = model

    async def text_chat(self, prompt: str, system_prompt: str = ""):
        import httpx
        from core.utils.llm import LLMResponse

        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        body: list[dict] = []
        if system_prompt:
            body.append({"role": "system", "content": system_prompt})
        body.append({"role": "user", "content": prompt})

        payload = {"model": self._model, "messages": body, "temperature": 0.1}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(self._url, headers=headers, json=payload)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]

        # Gemma 4 / Qwen3 thinking-mode models wrap reasoning in <think> tags;
        # strip them so the downstream JSON parser sees only the answer.
        text = _THINK_TAG_RE.sub("", text).strip()
        return LLMResponse(text)


# ── Cleanup ───────────────────────────────────────────────────────────────────

def _cleanup() -> None:
    global _archived_groups

    if REALTIME_DB.exists():
        print("[Cleanup] realtime_test.db preserved — run again to resume, "
              "or use reset_realtime_dev.py for a clean slate.")
    else:
        print("[Cleanup] realtime_test.db not present")

    # Stash this session's generated summary files (replacing any older
    # stash) so a future resume can put them back.
    realtime_groups = DEV_DATA / "groups"
    if realtime_groups.exists():
        if REALTIME_GROUPS_STASH.exists():
            shutil.rmtree(str(REALTIME_GROUPS_STASH))
        shutil.move(str(realtime_groups), str(REALTIME_GROUPS_STASH))
        print("[Cleanup] Stashed realtime summary files → .dev_data/realtime_groups/")

    # Restore the original summary dir that was moved at startup
    if _archived_groups is not None and _archived_groups.exists():
        shutil.move(str(_archived_groups), str(realtime_groups))
        print(
            f"[Cleanup] Restored original summary dir from {_archived_groups.name}")
        _archived_groups = None

    print("[Cleanup] Session ended cleanly.")


# ── Main async pipeline ───────────────────────────────────────────────────────

async def main() -> None:
    # Step 1: Resume decision + archive existing state
    print("=" * 70)
    print("  REALTIME DEV TEST  |  EVENT_MODE:", _EVENT_MODE.upper(), " |  LLM:", LLM_MODEL)
    print("=" * 70)
    resume = _resume_requested()
    print(f"  MODE: {'RESUME (skip rebuild)' if resume else 'FRESH BUILD'}")
    _archive_step(resume)

    # Step 2: Imports (lazy, inside main — same pattern as run_dataflow_dev.py)
    from core.utils.llm import SimpleLLMClient, MockProviderBridge  # noqa: F401 (SimpleLLMClient kept for reference)
    from core.repository.sqlite import (
        SQLiteEventRepository, SQLitePersonaRepository,
        SQLiteImpressionRepository, SQLitePersonaGroupRepository,
        SQLiteRawMessageRepository, db_open,
    )
    from core.managers.recall_manager import RecallManager
    from core.managers.context_manager import ContextManager
    from core.managers.account_link_manager import AccountLinkManager
    from core.managers.raw_message_writer import RawMessageWriter
    from core.utils.context_state_utils import VCMState
    from core.config import (
        MEMORY_INJECTION_FOOTER,
        MEMORY_INJECTION_HEADER,
        PluginConfig,
        ContextConfig,
        SynthesisConfig,
    )
    from core.adapters.astrbot import MessageRouter
    from core.adapters.identity import IdentityResolver
    from core.boundary.detector import EventBoundaryDetector
    from core.extractor.extractor import EventExtractor
    from core.social.big_five_scorer import BigFiveBuffer
    from core.social.orientation_analyzer import SocialOrientationAnalyzer
    from core.embedding.encoder import NullEncoder
    from core.utils.version import get_plugin_version
    from core.utils.perf import tracker
    from web.server import WebuiServer

    # Helper for RAG comparison
    class ProviderRequest:
        def __init__(self, prompt: str, system_prompt: str = ""):
            self.prompt = prompt
            self.system_prompt = system_prompt
            self.contexts: list = []

    def _clip(text: object, limit: int = 180) -> str:
        value = " ".join(str(text or "").split())
        return value if len(value) <= limit else value[: max(0, limit - 1)] + "…"

    def _extract_memory_block(req: ProviderRequest) -> str:
        text = "\n\n".join(
            part for part in [
                getattr(req, "system_prompt", ""),
                getattr(req, "prompt", ""),
            ] if part
        )
        start = text.find(MEMORY_INJECTION_HEADER)
        end = text.find(MEMORY_INJECTION_FOOTER)
        if start < 0 or end < 0 or end <= start:
            return ""
        end += len(MEMORY_INJECTION_FOOTER)
        return text[start:end]

    async def _print_event_quality_report(events, db) -> None:
        from collections import Counter

        if not events:
            print("\n[Quality] No events extracted.")
            return

        by_group = Counter(e.group_id or "__private__" for e in events)
        tag_counts = [len(e.chat_content_tags or []) for e in events]
        msg_counts = [len(e.interaction_flow or []) for e in events]
        avg_tags = sum(tag_counts) / len(tag_counts)
        avg_msgs = sum(msg_counts) / len(msg_counts)
        multi_topic = sum(1 for e in events if " | " in (e.summary or ""))
        low_conf = [e for e in events if float(e.confidence or 0.0) < 0.45]

        async with db.execute("SELECT COUNT(*) FROM raw_messages") as cur:
            raw_count = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM event_messages") as cur:
            linked_count = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT rm.message_id, rm.display_name, rm.text "
            "FROM raw_messages rm "
            "LEFT JOIN event_messages em ON em.message_id = rm.message_id "
            "WHERE em.message_id IS NULL "
            "ORDER BY rm.created_at LIMIT 5"
        ) as cur:
            unlinked_samples = await cur.fetchall()
        unlinked_count = max(0, raw_count - linked_count)

        print("\n" + "=" * 20 + " EVENT QUALITY " + "=" * 20)
        print(f"  Events by group       : {dict(by_group)}")
        print(f"  Avg source msgs/event : {avg_msgs:.2f}")
        print(f"  Avg tags/event        : {avg_tags:.2f}")
        print(f"  Multi-triple summaries: {multi_topic}/{len(events)}")
        print(f"  Low confidence events : {len(low_conf)}")
        print(f"  Raw messages persisted: {raw_count}")
        print(f"  Event-message links   : {linked_count}")
        print(f"  Unlinked raw messages : {unlinked_count}")
        if unlinked_samples:
            print("  Unlinked samples:")
            for row in unlinked_samples:
                print(f"    - {row[0]} {row[1]}: {_clip(row[2], 72)}")
        print("  Top events:")
        for ev in sorted(events, key=lambda e: float(e.salience or 0.0), reverse=True)[:5]:
            print(
                f"    - {ev.event_id[:8]} group={ev.group_id} "
                f"sal={float(ev.salience or 0.0):.2f} conf={float(ev.confidence or 0.0):.2f} "
                f"msgs={len(ev.interaction_flow or [])} tags={list(ev.chat_content_tags or [])[:4]} "
                f"topic={_clip(ev.topic, 48)}"
            )
        if low_conf:
            print("  Low confidence samples:")
            for ev in low_conf[:3]:
                print(f"    - {ev.event_id[:8]} conf={ev.confidence:.2f} topic={_clip(ev.topic, 64)}")
        print("=" * 55)

    async def _print_recall_diagnostics(query: str, group_id: str | None, retriever, recall, req: ProviderRequest) -> None:
        bm25, vec = await retriever.search_raw(query, group_id=group_id)
        recall_debug = recall.pop_recall_debug("test:114514") or {}
        injection_debug = recall.pop_injection_debug("test:114514") or {}
        injected_ids = recall.get_last_injected_ids("test:114514")
        memory_block = _extract_memory_block(req)

        print("\n" + "=" * 20 + " RECALL DIAGNOSTICS " + "=" * 20)
        print(f"  Query              : {query}")
        print(f"  Group              : {group_id}")
        print(f"  BM25 candidates    : {len(bm25)}")
        for ev in bm25[:5]:
            print(f"    [BM25] {ev.event_id[:8]} sal={ev.salience:.2f} topic={_clip(ev.topic, 58)}")
        print(f"  Vector candidates  : {len(vec)}")
        for ev in vec[:5]:
            print(f"    [VEC ] {ev.event_id[:8]} sal={ev.salience:.2f} topic={_clip(ev.topic, 58)}")
        print(f"  Injected event IDs : {[eid[:8] for eid in injected_ids]}")
        print(f"  Recall debug total : {recall_debug.get('total', 0)}")
        if injection_debug:
            memory = injection_debug.get("memory", {})
            print(
                f"  Injection position : {injection_debug.get('position')} "
                f"memory_count={memory.get('count', 0)} injected={injection_debug.get('injected')}"
            )
            for item in memory.get("events", [])[:5]:
                print(f"    [INJ ] {item.get('topic')} :: {_clip(item.get('summary'), 88)}")
        if memory_block:
            print("  Injected memory preview:")
            print("    " + _clip(memory_block, 1000))
        else:
            print("  Injected memory preview: <empty>")
        print("=" * 60)

    async def _print_perf_report() -> None:
        metrics = await tracker.get_metrics()
        print("\n" + "=" * 20 + " PERFORMANCE METRICS " + "=" * 20)
        for phase in sorted(metrics):
            data = metrics[phase]
            avg = data.get("avg", 0.0)
            last = data.get("last", 0.0)
            hits = ""
            if "avg_hits" in data or "last_hits" in data:
                hits = f" avg_hits={data.get('avg_hits', 0.0):.2f} last_hits={data.get('last_hits', 0)}"
            print(f"  {phase:<18} avg={avg:7.3f}s last={last:7.3f}s{hits}")
        print("=" * 58)

    async def _run_recall_benchmark() -> None:
        if not _RECALL_BENCHMARK_ENABLED:
            return
        queries = [
            ("no-evidence", "卿泽对原神的看法是什么？大家都说了些什么？", "114514"),
            ("gariton", "卿泽和Gariton发生了什么互动？", "114514"),
            ("arknights", "大家讨论明日方舟十四章和卫戍协议了吗？", "114514"),
            ("big-five", "谁请求了大五人格分析？", "114514"),
            ("fee", "导师和稿费的问题是什么？", "114514"),
            ("academic", "学术圈靠关系的吐槽是谁说的？", "1919810"),
        ]
        print("\n" + "=" * 20 + " RECALL BENCHMARK " + "=" * 20)
        for label, q, group in queries:
            t0 = time.perf_counter()
            hits = await recall.recall(q, group_id=group, limit=3)
            elapsed = time.perf_counter() - t0
            print(
                f"  [{label:<11}] group={group} hits={len(hits)} "
                f"time={elapsed:.3f}s query={q}"
            )
            for ev in hits[:3]:
                categories = getattr(ev, "chat_content_tags", []) or []
                from core.tags import derive_tag_categories
                tag_categories = derive_tag_categories(categories)
                print(
                    f"    - {ev.event_id[:8]} sal={float(ev.salience or 0.0):.2f} "
                    f"tags={list(ev.chat_content_tags or [])[:4]} "
                    f"cats={list(dict.fromkeys(tag_categories.values()))[:4]} "
                    f"topic={_clip(ev.topic, 56)}"
                )
        print("=" * 58)

    # Step 3: Parse Mock_Data.md (skipped when resuming — nothing to (re-)ingest)
    messages: list[dict] = []
    if not resume:
        print(f"\n[Parser] Reading {MOCK_DATA_PATH.name} ...")
        if not MOCK_DATA_PATH.exists():
            print(f"[Parser] ERROR: file not found at {MOCK_DATA_PATH}")
            return
        messages = _parse_mock_data(MOCK_DATA_PATH)
        groups = {m["group_id"] for m in messages}
        print(
            f"[Parser] {len(messages)} messages parsed across {len(groups)} groups: {sorted(groups)}")

    # Step 4: Config (mirrors run_dataflow_dev.py)
    def _build_config(mode: str) -> PluginConfig:
        raw: dict = {
            "retrieval_top_k": 3,
            "retrieval_token_budget": 1000,
            "boundary_max_messages": 200,
            "boundary_topic_drift_enabled": True, # Re-enabled now that it's optimized
            "boundary_topic_drift_interval": 5,
            "vcm_enabled": True,
            # Gemma 26B on LMStudio needs ~60-90 s per thinking call;
            # set asyncio timeout to 150 s so wait_for never fires first.
            "extractor_llm_timeout_seconds": _TIMEOUT,
            "llm_concurrency": _LLM_CONCURRENCY,
            "embedding_enabled": bool(_RETRIEVAL_ENCODER_ENABLED),
            "embedding_provider": "local",
            "embedding_model": _RETRIEVAL_ENCODER_MODEL,
            "embedding_batch_interval_ms": _RETRIEVAL_ENCODER_BATCH_INTERVAL_MS,
            "embedding_request_interval_ms": _RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS,
        }
        if mode == "encoder":
            raw.update({
                "extraction_strategy": "semantic",
                "semantic_clustering_eps": 0.45,
            })
        else:
            raw["extraction_strategy"] = "llm"
        return PluginConfig(raw, data_dir=DEV_DATA)

    cfg = _build_config(_EVENT_MODE)
    # Use _RealtimeProviderBridge instead of MockProviderBridge:
    # 180 s httpx timeout + <think> tag stripping for Gemma 26B.
    mock_provider = _RealtimeProviderBridge(
        LLM_API_URL, LLM_API_KEY, LLM_MODEL)

    # Step 5: Open fresh SQLite DB
    DEV_DATA.mkdir(parents=True, exist_ok=True)

    async with db_open(REALTIME_DB, migration_auto_backup=False) as db:
        event_repo = SQLiteEventRepository(db)
        persona_repo = SQLitePersonaRepository(db)
        impression_repo = SQLiteImpressionRepository(db)
        persona_group_repo = SQLitePersonaGroupRepository(db)
        raw_message_repo = SQLiteRawMessageRepository(db)
        raw_message_writer = RawMessageWriter(raw_message_repo)
        account_link_manager = AccountLinkManager(
            persona_repo=persona_repo,
            group_repo=persona_group_repo,
            event_repo=event_repo,
            provider_getter=lambda: mock_provider,
            synthesis_config=SynthesisConfig(llm_timeout=_TIMEOUT),
        )

        # Encoder. EVENT_MODE controls extraction strategy only; retrieval/indexing can
        # still use embeddings in LLM mode so Phase 5 validates semantic recall.
        if cfg.embedding_enabled:
            from core.embedding.encoder import SentenceTransformerEncoder
            from core.managers.embedding_manager import EmbeddingManager
            print(
                f"[Encoder] Loading {cfg.embedding_model} for retrieval/indexing "
                "(first run may download ~100 MB) ...")
            base_encoder = SentenceTransformerEncoder(
                model_name=cfg.embedding_model)
            encoder = EmbeddingManager(base_encoder, cfg.get_embedding_config())
            await encoder.start()
        else:
            print("[Encoder] Retrieval/indexing encoder disabled; vector recall will be unavailable.")
            encoder = NullEncoder()

        from core.retrieval.hybrid import HybridRetriever
        retriever = HybridRetriever(event_repo, encoder)
        recall = RecallManager(
            retriever, cfg.get_retrieval_config(), cfg.get_injection_config())
        context_manager = ContextManager(cfg.get_context_config())
        resolver = IdentityResolver(persona_repo)
        detector = EventBoundaryDetector(cfg.get_boundary_config())
        from core.managers.llm_manager import LLMTaskManager
        llm_manager = LLMTaskManager(concurrency=cfg.llm_concurrency)

        use_mock_persona = _load_eval_setting() if resume else False

        if not resume:
            # ── 模拟 Persona 选项 ──────────────────────────────────────────
            use_mock_persona = input(
                "\n[Dev] 是否启用模拟性格进行 [Eval] 测试？(y/N): "
            ).strip().lower() in ("y", "yes")

            if use_mock_persona:
                import time as _time
                from core.domain.models import Persona as _Persona
                _persona_text = MOCK_PERSONA_PATH.read_text(encoding="utf-8")
                _persona_name = "MockPersona"
                for _line in _persona_text.splitlines():
                    if _line.startswith("# Mock Persona:"):
                        _persona_name = _line.removeprefix(
                            "# Mock Persona:").strip()
                        break
                # Production stores a short synthesised blurb here, not the whole
                # profile. Mirror that: the extractor feeds `description` into the
                # [Eval] prompt, and an 8 KB file per call wrecks the prefix cache.
                _persona_desc = next(
                    (ln.strip() for ln in _persona_text.splitlines()
                     if ln.strip() and not ln.lstrip().startswith("#")),
                    _persona_name,
                )[:200]
                _mock_persona = _Persona(
                    uid="bot_internal_gariton",
                    bound_identities=[("internal", "gariton")],
                    primary_name=_persona_name,
                    persona_attrs={"description": _persona_desc},
                    confidence=0.9,
                    created_at=_time.time(),
                    last_active_at=_time.time(),
                )
                await persona_repo.upsert(_mock_persona)
                print("[Dev] persona 已植入。")

            _save_eval_setting(use_mock_persona)
            extractor_cfg = cfg.get_extractor_config()
            extractor_cfg.persona_influenced_summary = use_mock_persona

            extractor = EventExtractor(
                event_repo=event_repo,
                provider_getter=lambda: mock_provider,
                encoder=encoder,
                extractor_config=extractor_cfg,
                big_five_buffer=BigFiveBuffer(x_messages=10),
                orientation_analyzer=SocialOrientationAnalyzer(
                    impression_repo=impression_repo,
                    event_repo=event_repo,
                    cfg=cfg,
                ),
                ipc_enabled=True,
                persona_repo=persona_repo,
                llm_manager=llm_manager,
                raw_message_repo=raw_message_repo,
                raw_message_writer=raw_message_writer,
            )

            extraction_futures: list[asyncio.Task] = []

            async def on_event_close(window):
                task = asyncio.create_task(extractor(window))
                extraction_futures.append(task)

            router = MessageRouter(
                event_repo=event_repo,
                identity_resolver=resolver,
                detector=detector,
                context_manager=context_manager,
                encoder=encoder,
                on_event_close=on_event_close,
                raw_message_writer=raw_message_writer,
            )

            # ── Phase 1: Message ingestion ──────────────────────────────────────
            print(f"\n[Phase 1] Ingesting {len(messages)} messages ...")
            with _tqdm(total=len(messages), desc="  Ingesting", unit="msg") as bar:
                for msg in messages:
                    await router.process(
                        platform="discord",
                        physical_id=msg["user_id"],
                        display_name=msg["nickname"],
                        text=msg["content"],
                        raw_group_id=msg["group_id"],
                        now=msg["timestamp"],
                    )
                    bar.update(1)

            print("[Phase 1] Flushing router windows ...")
            await router.flush_all()
            await raw_message_writer.flush_once()
            print(
                f"[Phase 1] Done. {len(extraction_futures)} extraction task(s) queued.")

            # ── Phase 2: Wait for LLM extraction ───────────────────────────────
            if extraction_futures:
                print(
                    f"\n[Phase 2] Running {len(extraction_futures)} LLM extraction task(s) ...")
                with _tqdm(total=len(extraction_futures), desc="  Extracting", unit="task") as bar:
                    for fut in asyncio.as_completed(extraction_futures):
                        try:
                            await fut
                        except Exception as exc:
                            print(f"\n  [Warning] Extraction task raised: {exc}")
                        bar.update(1)
                print("[Phase 2] Annotating [Eval] asides (batched, after extraction) ...")
                await extractor.drain_evals()
            else:
                print("\n[Phase 2] No extraction tasks queued.")

            # ── Phase 3: Persona synthesis (writes big_five + big_five_evidence) ──
            print("\n[Phase 3] Running persona synthesis ...")
            from core.tasks.synthesis import run_persona_synthesis
            from core.config import SynthesisConfig
            synthesis_cfg = SynthesisConfig(llm_timeout=_TIMEOUT)
            n_synth = await run_persona_synthesis(
                persona_repo=persona_repo,
                event_repo=event_repo,
                provider_getter=lambda: mock_provider,
                synthesis_config=synthesis_cfg,
                llm_manager=llm_manager,
            )
            print(f"[Phase 3] Persona synthesis: {n_synth} persona(s) updated.")

            # ── Phase 4: Generate group summaries via LLM ──────────────────────
            print("\n[Phase 4] Generating group summaries via LLM ...")
            from core.tasks.summary import run_group_summary
            from core.config import SummaryConfig  # noqa: F811 (re-import for local use)
            # match Gemma 26B latency
            summary_cfg = SummaryConfig(
                llm_timeout=300.0, mood_source=_MOOD_SOURCE)
            n_written = await run_group_summary(
                event_repo=event_repo,
                data_dir=DEV_DATA,
                provider_getter=lambda: mock_provider,
                summary_config=summary_cfg,
                persona_repo=persona_repo,
                impression_repo=impression_repo,
                llm_manager=llm_manager,
            )
            print(f"[Phase 4] {n_written} summary file(s) written.")

            # ── Success summary ─────────────────────────────────────────────────
            events = await event_repo.list_all(limit=10_000)
            personas = await persona_repo.list_all()
            async with db.execute("SELECT COUNT(*) FROM impressions") as cur:
                row = await cur.fetchone()
            imp_count = row[0] if row else 0

            print("\n" + "=" * 70)
            print("  INJECTION COMPLETE")
            print(f"  Events      : {len(events)}")
            print(f"  Personas    : {len(personas)}")
            print(f"  Impressions : {imp_count}")
            print("=" * 70)
            await _print_event_quality_report(events, db)

            # ── Phase 5: RAG Validation & Prompt Injection ──────────────────────
            print("\n[Phase 5] Testing RAG Retrieval and Prompt Injection ...")
            query = "卿泽对原神的看法是什么？大家都说了些什么？"
            sid_rag = "test:114514"
            test_group_id = "114514"
            llm_client = SimpleLLMClient(LLM_API_URL, LLM_API_KEY, LLM_MODEL)

            req = ProviderRequest(
                prompt="You are now in a chatroom. The user asks: " + query,
                system_prompt=(
                    "You are a helpful assistant. For this dev validation, answer only from "
                    "explicitly provided memory evidence. If the memory block does not contain "
                    "the requested fact, say there is no evidence. Cite the recalled event topic "
                    "or say which evidence is missing."
                ),
            )

            print(f"  [LLM] Generating response WITHOUT memory for query: '{query}'")
            try:
                resp_no_mem = await llm_client.text_chat(req.prompt, req.system_prompt)
                no_mem_text = resp_no_mem.completion_text
            except Exception as e:
                print(f"  [Warning] LLM call failed ({e}). Using simulated response.")
                no_mem_text = "I don't know who Rain is."

            # Force RECALL state for testing
            context_manager._states[sid_rag] = VCMState.RECALL

            injected_count = await recall.recall_and_inject(
                query=query,
                req=req,
                session_id=sid_rag,
                group_id=test_group_id,
                store_debug=True,
                store_injection_debug=True,
            )
            print(f"  [Recall] Injected {injected_count} event(s).")
            await _print_recall_diagnostics(query, test_group_id, retriever, recall, req)

            print(f"  [LLM] Generating response WITH memory ...")
            try:
                resp_with_mem = await llm_client.text_chat(req.prompt, req.system_prompt)
                with_mem_text = resp_with_mem.completion_text
            except Exception as e:
                print(f"  [Warning] LLM call failed ({e}). Using simulated response.")
                with_mem_text = "Based on the chat history, Rain mentions playing Genshin Impact..."

            print("\n  " + "=" * 20 + " RAG COMPARISON " + "=" * 20)
            print(f"  QUERY: {query}")
            print("  " + "-" * 40)
            print(f"  BEFORE MEMORY:\n  {no_mem_text[:200]}...")
            print("  " + "-" * 40)
            print(f"  AFTER MEMORY (RAG):\n  {with_mem_text[:200]}...")
            print("  " + "=" * 52)
            await _run_recall_benchmark()

            # ── Phase 6: VCM State Stress Test ──────────────────────────────────
            print("\n[Phase 6] VCM State Stress Test (Focused -> Eviction -> Drift) ...")
            small_cfg = ContextConfig(vcm_enabled=True, window_size=5)
            stress_cm = ContextManager(small_cfg)
            stress_sid = "test:stress"

            print(f"  Initial State: {stress_cm.update_state(stress_sid).value}")
            # Fill to trigger EVICTION (80% of 5 = 4 messages)
            win = stress_cm.get_window(stress_sid, create=True)
            for i in range(4):
                win.add_message("u", f"stress {i}", time.time())
                state = stress_cm.update_state(stress_sid)
                print(f"  Msg {i+1}: State -> {state.value}")

            state = stress_cm.update_state(stress_sid, drift_detected=True)
            print(f"  Topic Drift Detected: State -> {state.value}")

            # ── Phase 7: Performance Metrics ────────────────────────────────────
            await _print_perf_report()
        else:
            # ── Resume: skip build entirely, just report what's already there ──
            events = await event_repo.list_all(limit=10_000)
            personas = await persona_repo.list_all()
            async with db.execute("SELECT COUNT(*) FROM impressions") as cur:
                row = await cur.fetchone()
            imp_count = row[0] if row else 0

            print("\n" + "=" * 70)
            print("  RESUMED FROM PREVIOUS SESSION  (no LLM calls made)")
            print(f"  Events      : {len(events)}")
            print(f"  Personas    : {len(personas)}")
            print(f"  Impressions : {imp_count}")
            print("=" * 70)
            await _print_event_quality_report(events, db)

        # ── Phase 8: Start WebUI ────────────────────────────────────────────
        from core.tasks.synthesis import run_persona_synthesis as _run_persona_synthesis, run_impression_recalculation
        from core.tasks.summary import run_group_summary as _run_group_summary

        async def _dev_task_runner(name: str) -> bool:
            if name == "persona_synthesis":
                n = await _run_persona_synthesis(
                    persona_repo, event_repo,
                    provider_getter=lambda: mock_provider,
                    llm_manager=llm_manager,
                )
                print(f"[Task] persona_synthesis: {n} updated")
                return True
            if name == "impression_recalculation":
                n = await run_impression_recalculation(
                    persona_repo, event_repo, impression_repo,
                )
                print(f"[Task] impression_recalculation: {n} updated")
                return True
            if name == "group_summary":
                n = await _run_group_summary(
                    event_repo=event_repo,
                    data_dir=DEV_DATA,
                    provider_getter=lambda: mock_provider,
                    persona_repo=persona_repo,
                    impression_repo=impression_repo,
                    llm_manager=llm_manager,
                )
                print(f"[Task] group_summary: {n} written")
                return True
            print(f"[Task] unknown task: {name}")
            return False

        session_config = {"persona_influenced_summary": use_mock_persona}
        srv = WebuiServer(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=DEV_DATA,
            port=PORT,
            auth_enabled=False,
            initial_config=session_config,
            plugin_version=get_plugin_version(),
            provider_getter=lambda: mock_provider,
            all_providers_getter=lambda: [type(
                "DevProviderInfo",
                (),
                {"id": _MODEL_TYPE, "name": f"{_MODEL_TYPE}:{LLM_MODEL}"},
            )()],

            recall_manager=recall,
            task_runner=_dev_task_runner,
            encoder=encoder,
            context_manager=context_manager,
            raw_message_repo=raw_message_repo,
            persona_group_repo=persona_group_repo,
            account_link_manager=account_link_manager,
        )
        await srv.start()
        print(f"\n  WebUI ready  →  http://localhost:{PORT}")
        print(f"  DB           →  {REALTIME_DB}")
        if not _TQDM_OK:
            print("  Tip: pip install tqdm  for nicer progress bars")
        print("\n  Press Ctrl+Q  (or type 'q' + Enter) to stop and clean up.\n")

        # ── Phase 4: Hotkey listener + keep-alive ──────────────────────────
        stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()

        def _hotkey_thread() -> None:
            try:
                import msvcrt  # Windows only
                while not stop_event.is_set():
                    if msvcrt.kbhit():
                        ch = msvcrt.getch()
                        if ch == b"\x11":  # Ctrl+Q = ASCII 17
                            print("\n[Input] Ctrl+Q detected — stopping ...")
                            loop.call_soon_threadsafe(stop_event.set)
                            return
                    time.sleep(0.05)
                return
            except ImportError:
                pass
            # Fallback: blocking readline (non-Windows / piped stdin)
            try:
                for line in sys.stdin:
                    if line.strip().lower() in ("q", "quit", "exit"):
                        print("[Input] Stop command received.")
                        loop.call_soon_threadsafe(stop_event.set)
                        return
                    if stop_event.is_set():
                        return
            except (EOFError, OSError):
                pass

        t = threading.Thread(target=_hotkey_thread, daemon=True)
        t.start()

        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            print("\n[Shutdown] Stopping WebUI server ...")
            _save_eval_setting(session_config["persona_influenced_summary"] is True)
            await srv.stop()
            await raw_message_writer.stop()
            if _EVENT_MODE == "encoder":
                await encoder.stop()
            _cleanup()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _root_str = str(Path(__file__).parent)
    if _root_str not in sys.path:
        sys.path.insert(0, _root_str)
    if "--self-test" in sys.argv:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(_ROOT / "tests"), pattern="test_event_summary.py")
        if not suite.countTestCases():
            raise SystemExit("No event-summary regression tests found.")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Interrupt] Ctrl+C received — forcing cleanup ...")
        _cleanup()
