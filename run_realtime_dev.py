"""Realtime dev runner — parses Mock_Data.md through the full memory pipeline
and serves results via WebUI at port 2656.

Usage:
    python run_realtime_dev.py

Controls:
    Press Ctrl+Q  — stop and clean up (Windows)
    Type 'q' + Enter — stop and clean up (fallback / non-Windows)
    Ctrl+C        — emergency stop (also triggers cleanup)

Configurations:
    1. LMStudio: API_URL="http://localhost:1234/v1", API_KEY="lm-studio", MODEL="any"
    2. DeepSeek:  API_URL="https://api.deepseek.com", API_KEY="your_key", MODEL="deepseek-chat"
"""

import asyncio
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

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
            print(f"\r  {self._desc}: {self._n}{total_str} {self._unit}", end="", flush=True)


# ── LLM Configuration ────────────────────────────────────────────────────────

try:
    from key import KEY  # type: ignore[import]
except ImportError:
    KEY = "your_api_key_here"

# 1. LMStudio (Local) — Heretic Gemma
LLM_API_URL = "http://localhost:1234/v1"
LLM_API_KEY = "lm-studio"
LLM_MODEL   = "gemma-4-26b-a4b-it-ultra-uncensored-heretic"

# 2. DeepSeek (Cloud) — uncomment to use
# LLM_API_URL = "https://api.deepseek.com"
# LLM_API_KEY = KEY
# LLM_MODEL   = "deepseek-v4-flash"

MODE = "encoder"   # "encoder" | "llm"

# ── Paths ─────────────────────────────────────────────────────────────────────

_ROOT              = Path(__file__).parent
MOCK_DATA_PATH     = _ROOT / "tests" / "mock_data" / "Mock_Realtime_Data.md"
MOCK_PERSONA_PATH  = _ROOT / "tests" / "mock_data" / "mock_persona.md"
DEV_DATA           = _ROOT / ".dev_data"
ARCHIVE_DIR        = DEV_DATA / "archive"
REALTIME_DB        = DEV_DATA / "realtime_test.db"
DATAFLOW_DB        = DEV_DATA / "dataflow_test.db"
PORT               = 2656

# Tracks where the previous groups/ directory was archived so _cleanup()
# can restore it on Ctrl+Q exit.
_archived_groups: Path | None = None


# ── Archive step ──────────────────────────────────────────────────────────────

def _archive_step() -> None:
    """Back up existing DB files and relocate the summary dir before injection."""
    global _archived_groups

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    if REALTIME_DB.exists():
        dest = ARCHIVE_DIR / f"realtime_test_stale_{ts}.db"
        try:
            shutil.move(str(REALTIME_DB), str(dest))
            print(f"[Archive] Moved stale realtime_test.db → {dest.name}")
        except PermissionError:
            # Windows: DB file is still locked by a previous process.
            # Delete it in place so a fresh DB can be created.
            try:
                REALTIME_DB.unlink()
                print("[Archive] realtime_test.db was locked; deleted in place (no archive).")
            except PermissionError:
                print("[Archive] WARNING: realtime_test.db is locked and cannot be deleted. "
                      "Close any process holding it and retry.")

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
        print(f"[Archive] Moved summary dir → archive/groups_{ts}/ (will restore on exit)")


# ── Mock_Data.md parser ───────────────────────────────────────────────────────

_GROUP_HDR = re.compile(r'^## Group ID: (\S+)', re.MULTILINE)
_MSG_HDR   = re.compile(
    r'^\*\*(.+?) \((\d+)\)\*\* \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) ?\]:$'
)


def _parse_mock_data(path: Path) -> list[dict]:
    """Parse Mock_Data.md into a flat list of message dicts.

    Each dict: group_id, display_name, user_id, timestamp (POSIX float), text.
    Blocks that contain no message header (preamble, metadata) are skipped.
    """
    raw = path.read_text(encoding="utf-8")
    blocks = re.split(r'\n\n---\n\n', raw)

    messages: list[dict] = []
    current_group: str | None = None

    for block in blocks:
        lines = block.strip().splitlines()

        for line in lines:
            gm = _GROUP_HDR.match(line)
            if gm:
                current_group = gm.group(1)

        for i, line in enumerate(lines):
            mm = _MSG_HDR.match(line)
            if mm:
                display_name = mm.group(1)
                user_id      = mm.group(2)
                ts_str       = mm.group(3)
                body         = "\n".join(lines[i + 1:]).strip()
                try:
                    dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M")
                    timestamp = dt.timestamp()
                except ValueError:
                    timestamp = time.time()
                if body:
                    messages.append({
                        "group_id":     current_group,
                        "display_name": display_name,
                        "user_id":      user_id,
                        "timestamp":    timestamp,
                        "text":         body,
                    })
                break

    return messages


# ── Provider bridge for slow local LLMs ──────────────────────────────────────

_THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class _RealtimeProviderBridge:
    """LLM provider bridge tuned for Gemma 26B on LMStudio.

    Two differences from the stock MockProviderBridge:
    - httpx timeout 180 s (Gemma 26B thinking can take 60-90 s per call)
    - strips <think>…</think> blocks before returning so the JSON parser
      never sees interleaved reasoning text
    """

    def __init__(self, api_url: str, api_key: str, model: str) -> None:
        self._url   = api_url.rstrip("/") + "/chat/completions"
        self._key   = api_key
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

        async with httpx.AsyncClient(timeout=330.0) as client:
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
        REALTIME_DB.unlink()
        print("[Cleanup] Deleted realtime_test.db")
    else:
        print("[Cleanup] realtime_test.db already removed")

    # Remove realtime-generated summary files
    realtime_groups = DEV_DATA / "groups"
    if realtime_groups.exists():
        shutil.rmtree(str(realtime_groups))
        print("[Cleanup] Removed realtime summary files")

    # Restore the original summary dir that was moved at startup
    if _archived_groups is not None and _archived_groups.exists():
        shutil.move(str(_archived_groups), str(realtime_groups))
        print(f"[Cleanup] Restored original summary dir from {_archived_groups.name}")
        _archived_groups = None

    print("[Cleanup] Session ended cleanly.")


# ── Main async pipeline ───────────────────────────────────────────────────────

async def main() -> None:
    # Step 1: Archive existing state
    print("=" * 70)
    print("  REALTIME DEV TEST  |  MODE:", MODE.upper(), " |  LLM:", LLM_MODEL)
    print("=" * 70)
    _archive_step()

    # Step 2: Imports (lazy, inside main — same pattern as run_dataflow_dev.py)
    from core.utils.llm import SimpleLLMClient, MockProviderBridge  # noqa: F401 (SimpleLLMClient kept for reference)
    from core.repository.sqlite import (
        SQLiteEventRepository, SQLitePersonaRepository,
        SQLiteImpressionRepository, db_open,
    )
    from core.managers.recall_manager import RecallManager
    from core.managers.context_manager import ContextManager
    from core.adapters.astrbot import MessageRouter
    from core.adapters.identity import IdentityResolver
    from core.boundary.detector import EventBoundaryDetector
    from core.extractor.extractor import EventExtractor
    from core.embedding.encoder import NullEncoder
    from core.config import PluginConfig
    from web.server import WebuiServer

    # Step 3: Parse Mock_Data.md
    print(f"\n[Parser] Reading {MOCK_DATA_PATH.name} ...")
    if not MOCK_DATA_PATH.exists():
        print(f"[Parser] ERROR: file not found at {MOCK_DATA_PATH}")
        return
    messages = _parse_mock_data(MOCK_DATA_PATH)
    groups = {m["group_id"] for m in messages}
    print(f"[Parser] {len(messages)} messages parsed across {len(groups)} groups: {sorted(groups)}")

    # Step 4: Config (mirrors run_dataflow_dev.py)
    def _build_config(mode: str) -> PluginConfig:
        raw: dict = {
            "retrieval_top_k": 3,
            "retrieval_token_budget": 1000,
            "boundary_max_messages": 200,
            "vcm_enabled": True,
            # Gemma 26B on LMStudio needs ~60-90 s per thinking call;
            # set asyncio timeout to 150 s so wait_for never fires first.
            "extractor_llm_timeout_seconds": 300.0,
        }
        if mode == "encoder":
            raw.update({
                "extraction_strategy": "semantic",
                "semantic_clustering_eps": 0.45,
                "embedding_provider": "local",
                "embedding_model": "BAAI/bge-small-zh-v1.5",
            })
        else:
            raw["extraction_strategy"] = "llm"
        return PluginConfig(raw)

    cfg           = _build_config(MODE)
    # Use _RealtimeProviderBridge instead of MockProviderBridge:
    # 180 s httpx timeout + <think> tag stripping for Gemma 26B.
    mock_provider = _RealtimeProviderBridge(LLM_API_URL, LLM_API_KEY, LLM_MODEL)

    # Step 5: Open fresh SQLite DB
    DEV_DATA.mkdir(parents=True, exist_ok=True)

    async with db_open(REALTIME_DB, migration_auto_backup=False) as db:
        event_repo      = SQLiteEventRepository(db)
        persona_repo    = SQLitePersonaRepository(db)
        impression_repo = SQLiteImpressionRepository(db)

        # Encoder
        if MODE == "encoder":
            from core.embedding.encoder import SentenceTransformerEncoder
            print(f"[Encoder] Loading {cfg.embedding_model} (first run may download ~100 MB) ...")
            encoder = SentenceTransformerEncoder(model_name=cfg.embedding_model)
        else:
            encoder = NullEncoder()

        from core.retrieval.hybrid import HybridRetriever
        retriever       = HybridRetriever(event_repo, encoder)
        recall          = RecallManager(retriever, cfg.get_retrieval_config(), cfg.get_injection_config())
        context_manager = ContextManager(cfg.get_context_config())
        resolver        = IdentityResolver(persona_repo)
        detector        = EventBoundaryDetector(cfg.get_boundary_config())

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
                    _persona_name = _line.removeprefix("# Mock Persona:").strip()
                    break
            _mock_persona = _Persona(
                uid="bot_internal_gariton",
                bound_identities=[("internal", "gariton")],
                primary_name=_persona_name,
                persona_attrs={"description": _persona_text},
                confidence=0.9,
                created_at=_time.time(),
                last_active_at=_time.time(),
            )
            await persona_repo.upsert(_mock_persona)
            print("[Dev] persona 已植入。")

        extractor_cfg = cfg.get_extractor_config()
        if use_mock_persona:
            extractor_cfg.persona_influenced_summary = True

        extractor       = EventExtractor(
            event_repo=event_repo,
            provider_getter=lambda: mock_provider,
            encoder=encoder,
            extractor_config=extractor_cfg,
            ipc_enabled=False,
            persona_repo=persona_repo,
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
            on_event_close=on_event_close,
        )

        # ── Phase 1: Message ingestion ──────────────────────────────────────
        print(f"\n[Phase 1] Ingesting {len(messages)} messages ...")
        with _tqdm(total=len(messages), desc="  Ingesting", unit="msg") as bar:
            for msg in messages:
                await router.process(
                    platform="discord",
                    physical_id=msg["user_id"],
                    display_name=msg["display_name"],
                    text=msg["text"],
                    raw_group_id=msg["group_id"],
                    now=msg["timestamp"],
                )
                bar.update(1)

        print("[Phase 1] Flushing router windows ...")
        await router.flush_all()
        print(f"[Phase 1] Done. {len(extraction_futures)} extraction task(s) queued.")

        # ── Phase 2: Wait for LLM extraction ───────────────────────────────
        if extraction_futures:
            print(f"\n[Phase 2] Running {len(extraction_futures)} LLM extraction task(s) ...")
            with _tqdm(total=len(extraction_futures), desc="  Extracting", unit="task") as bar:
                for fut in asyncio.as_completed(extraction_futures):
                    try:
                        await fut
                    except Exception as exc:
                        print(f"\n  [Warning] Extraction task raised: {exc}")
                    bar.update(1)
        else:
            print("\n[Phase 2] No extraction tasks queued.")

        # ── Phase 3: Generate group summaries via LLM ──────────────────────
        print("\n[Phase 3] Generating group summaries via LLM ...")
        from core.tasks.summary import run_group_summary
        from core.config import SummaryConfig
        summary_cfg = SummaryConfig(llm_timeout=300.0)  # match Gemma 26B latency
        n_written = await run_group_summary(
            event_repo=event_repo,
            data_dir=DEV_DATA,
            provider_getter=lambda: mock_provider,
            summary_config=summary_cfg,
            persona_repo=persona_repo,
            impression_repo=impression_repo,
        )
        print(f"[Phase 3] {n_written} summary file(s) written.")

        # ── Success summary ─────────────────────────────────────────────────
        events   = await event_repo.list_all(limit=10_000)
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

        # ── Phase 3: Start WebUI ────────────────────────────────────────────
        srv = WebuiServer(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=DEV_DATA,
            port=PORT,
            auth_enabled=False,
            plugin_version="realtime-dev",
        )
        await srv.start()
        print(f"\n  WebUI ready  →  http://localhost:{PORT}")
        print(f"  DB           →  {REALTIME_DB}")
        if not _TQDM_OK:
            print("  Tip: pip install tqdm  for nicer progress bars")
        print("\n  Press Ctrl+Q  (or type 'q' + Enter) to stop and clean up.\n")

        # ── Phase 4: Hotkey listener + keep-alive ──────────────────────────
        stop_event = asyncio.Event()
        loop       = asyncio.get_event_loop()

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
            await srv.stop()
            _cleanup()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    _root_str = str(Path(__file__).parent)
    if _root_str not in sys.path:
        sys.path.insert(0, _root_str)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Interrupt] Ctrl+C received — forcing cleanup ...")
        _cleanup()
