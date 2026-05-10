"""PluginInitializer: component wiring and lifecycle management.

Constructs all subsystems in dependency order and tears them down in reverse.
main.py instantiates this class and delegates to it; all business logic stays
out of the Star shell.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING

from astrbot.api import logger as astrbot_logger

from .adapters.astrbot import MessageRouter
from .adapters.identity import IdentityResolver
from .boundary.detector import EventBoundaryDetector
from .config import PluginConfig
from .domain.models import Event
from .embedding.encoder import NullEncoder, SentenceTransformerEncoder, ApiEncoder, Encoder
from .extractor.extractor import EventExtractor
from .managers import MemoryManager, RecallManager
from .managers.context_manager import ContextManager
from .managers.embedding_manager import EmbeddingManager
from .projector.projector import MarkdownProjector
from .repository.sqlite import (
    SQLiteEventRepository,
    SQLiteImpressionRepository,
    SQLitePersonaRepository,
    db_open,
)
from .retrieval.hybrid import HybridRetriever
from .social.big_five_scorer import BigFiveBuffer
from .social.orientation_analyzer import SocialOrientationAnalyzer
from .sync.syncer import ReverseSyncer
from .sync.watcher import FileWatcher
from .tasks.cleanup import run_memory_cleanup
from .tasks.scheduler import TaskScheduler
from .tasks.summary import run_group_summary
from .tasks.synthesis import run_impression_aggregation, run_persona_synthesis

if TYPE_CHECKING:
    from astrbot.api.star import Context
    from .boundary.window import MessageWindow

_VEC_DIM = 512
_PLUGIN_NAME = "EnhancedMemory"

logger = logging.getLogger(__name__)


class PluginInitializer:
    """Wires all subsystems together and owns their lifecycle."""

    def __init__(self, context: Context, cfg: PluginConfig, data_dir: Path) -> None:
        self._context = context
        self._cfg = cfg
        self._data_dir = data_dir

        self._exit_stack: AsyncExitStack | None = None

        # Subsystem attributes — set during initialize()
        self.context_manager: ContextManager | None = None
        self.embedding_manager: EmbeddingManager | None = None
        self.memory: MemoryManager | None = None
        self.recall: RecallManager | None = None
        self.router: MessageRouter | None = None
        self.projector: MarkdownProjector | None = None
        self.scheduler: TaskScheduler | None = None
        self.webui = None
        self.watcher: FileWatcher | None = None
        self.syncer: ReverseSyncer | None = None

    async def initialize(self) -> None:
        cfg = self._cfg
        data_dir = self._data_dir
        # ... (rest of initialize remains same)
        # Actually I need to make sure I add start/stop to the end of initialize and start of terminate
        
    # Wait, the tool only shows parts of the file. I need to find where initialize/terminate methods end.

        db_path = data_dir / "db" / "core.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._exit_stack = AsyncExitStack()
        db = await self._exit_stack.enter_async_context(
            db_open(db_path, vec_dim=_VEC_DIM,
                    migration_auto_backup=cfg.migration_auto_backup)
        )

        persona_repo = SQLitePersonaRepository(db)
        event_repo = SQLiteEventRepository(db)
        impression_repo = SQLiteImpressionRepository(db)

        self.projector = MarkdownProjector(
            data_dir=data_dir,
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
        )

        # Encoder: try local/API model, fall back to null (BM25-only) on any error
        embed_cfg = cfg.get_embedding_config()
        if cfg.embedding_enabled:
            try:
                if embed_cfg.provider == "api":
                    encoder: Encoder = ApiEncoder(
                        model_name=embed_cfg.model,
                        api_url=embed_cfg.api_url,
                        api_key=embed_cfg.api_key
                    )
                else:
                    encoder = SentenceTransformerEncoder(embed_cfg.model)
                    _ = encoder.dim  # trigger lazy load early
            except Exception as exc:
                astrbot_logger.warning(
                    "[%s] embedding provider (%s) unavailable: %s. Falling back to NullEncoder.",
                    _PLUGIN_NAME, embed_cfg.provider, exc,
                )
                encoder = NullEncoder()
        else:
            encoder = NullEncoder()

        self.embedding_manager = EmbeddingManager(encoder, embed_cfg)
        
        self.context_manager = ContextManager(cfg.get_context_config())

        retriever = HybridRetriever(
            event_repo=event_repo,
            encoder=self.embedding_manager,  # Use manager as encoder
            bm25_limit=cfg.get_retrieval_config().bm25_limit,
            vec_limit=cfg.get_retrieval_config().vec_limit,
            rrf_k=cfg.get_retrieval_config().rrf_k,
        )

        self.memory = MemoryManager(
            event_repo=event_repo,
            retriever=retriever,
            encoder=self.embedding_manager,  # Use manager
            decay_config=cfg.get_decay_config(),
        )

        self.recall = RecallManager(
            retriever=retriever,
            retrieval_config=cfg.get_retrieval_config(),
            injection_config=cfg.get_injection_config(),
        )

        ipc_cfg = cfg.get_ipc_config()
        big_five_buffer: BigFiveBuffer | None = None
        orientation_analyzer: SocialOrientationAnalyzer | None = None
        if ipc_cfg.enabled and cfg.relation_enabled:
            big_five_buffer = BigFiveBuffer(
                x_messages=ipc_cfg.bigfive_x_messages,
                llm_timeout=ipc_cfg.bigfive_llm_timeout,
            )
            orientation_analyzer = SocialOrientationAnalyzer(impression_repo)

        extractor = EventExtractor(
            event_repo=event_repo,
            provider_getter=lambda: self._context.get_using_provider(),
            encoder=self.embedding_manager,
            extractor_config=cfg.get_extractor_config(),
            big_five_buffer=big_five_buffer,
            orientation_analyzer=orientation_analyzer,
            ipc_enabled=ipc_cfg.enabled,
            impression_repo=impression_repo,
            plugin_config=cfg,
            persona_repo=persona_repo,
        )

        async def on_event_close(window: MessageWindow) -> None:
            asyncio.create_task(extractor(window))

        resolver = IdentityResolver(persona_repo)
        detector = EventBoundaryDetector(cfg.get_boundary_config())
        self.router = MessageRouter(
            event_repo=event_repo,
            identity_resolver=resolver,
            detector=detector,
            context_manager=self.context_manager,
            on_event_close=on_event_close,
        )

        def provider_getter():
            return self._context.get_using_provider()

        synthesis_cfg = cfg.get_synthesis_config()
        summary_cfg = cfg.get_summary_config()

        self.scheduler = TaskScheduler()
        self.scheduler.register(
            "salience_decay",
            interval=cfg.decay_interval_seconds,
            fn=lambda: self.memory.apply_decay() if self.memory else None,
        )
        self.scheduler.register(
            "context_cleanup",
            interval=60,
            fn=lambda: self.context_manager.cleanup_expired() if self.context_manager else None,
        )
        self.scheduler.register(
            "memory_cleanup",
            interval=cfg.get_cleanup_config().interval_days * 86400,
            fn=lambda: run_memory_cleanup(event_repo, cfg.get_cleanup_config()),
        )

        async def _projection_and_register() -> None:
            if self.projector:
                await self.projector.render_all_personas()
            if self.syncer:
                await self.syncer.register_all()

        self.scheduler.register(
            "projection",
            interval=cfg.summary_interval_seconds,
            fn=_projection_and_register,
        )
        self.scheduler.register(
            "persona_synthesis",
            interval=cfg.persona_synthesis_interval_seconds,
            fn=lambda: run_persona_synthesis(
                persona_repo, event_repo, provider_getter,
                synthesis_config=synthesis_cfg,
            ),
        )
        self.scheduler.register(
            "impression_aggregation",
            interval=cfg.impression_aggregation_interval_seconds,
            fn=lambda: run_impression_aggregation(
                persona_repo, event_repo, impression_repo, provider_getter,
                synthesis_config=synthesis_cfg,
                persona_isolation_enabled=cfg.persona_isolation_enabled,
            ),
        )
        self.scheduler.register(
            "group_summary",
            interval=cfg.summary_interval_seconds,
            fn=lambda: run_group_summary(
                event_repo, data_dir, provider_getter,
                summary_config=summary_cfg,
            ),
        )
        await self.scheduler.start()

        from web.server import WebuiServer
        self.webui = WebuiServer(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=data_dir,
            port=cfg.webui_port,
            auth_enabled=cfg.webui_auth_enabled,
            task_runner=self.scheduler.run_now,
            plugin_version=_get_plugin_version(),
            initial_config=cfg.as_dict(),
        )
        if cfg.webui_enabled:
            await self.webui.start()
        else:
            astrbot_logger.info("[%s] WebUI disabled by config", _PLUGIN_NAME)

        self.watcher = FileWatcher()
        self.syncer = ReverseSyncer(
            data_dir=data_dir,
            persona_repo=persona_repo,
            impression_repo=impression_repo,
            watcher=self.watcher,
        )
        await self.syncer.register_all()
        await self.watcher.start()
        if self.embedding_manager:
            await self.embedding_manager.start()

        astrbot_logger.info("[%s] initialized — DB at %s", _PLUGIN_NAME, db_path)

    async def teardown(self) -> None:
        if self.watcher is not None:
            await self.watcher.stop()
        if self.webui is not None:
            await self.webui.stop()
        if self.scheduler is not None:
            await self.scheduler.stop()
        if self.embedding_manager is not None:
            await self.embedding_manager.stop()
        if self.router is not None:
            await self.router.flush_all()
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        astrbot_logger.info("[%s] terminated", _PLUGIN_NAME)


def _get_plugin_version() -> str:
    try:
        from importlib.metadata import version
        return version("astrbot-plugin-enhanced-memory")
    except Exception:
        return "0.6.0"


async def _maybe_trigger_impression(
    event: Event,
    impression_repo,
    event_repo,
    cfg: PluginConfig,
) -> None:
    """Rule-based impression update triggered on event close.

    Iterates all (observer, subject) pairs among event participants.
    Skips a pair if:
    - debounce window not elapsed since last_reinforced_at
    - shared event count in this scope < threshold

    On trigger: maps heuristic signals to IPC coordinates (no LLM, no ML).
    colleague (≥10 shared events) → 支配友好 (B=0.4, P=0.2)
    stranger  (<10 shared events) → 友好      (B=0.2, P=0.0)
    """
    import math
    from .domain.models import Impression

    uids = event.participants
    if len(uids) < 2:
        return

    scope = event.group_id or "global"
    threshold = cfg.impression_event_trigger_threshold
    debounce_sec = cfg.impression_trigger_debounce_hours * 3600
    now = time.time()

    for i, observer in enumerate(uids):
        for subject in uids[i + 1:]:
            for obs, subj in [(observer, subject), (subject, observer)]:
                try:
                    existing = await impression_repo.get(obs, subj, scope)

                    # Debounce
                    if existing and (now - existing.last_reinforced_at) < debounce_sec:
                        continue

                    # Count shared events in this scope
                    obs_events = await event_repo.list_by_participant(obs, limit=200)
                    subj_ids = {
                        e.event_id
                        for e in await event_repo.list_by_participant(subj, limit=200)
                    }
                    shared = [
                        e for e in obs_events
                        if e.event_id in subj_ids
                        and (e.group_id or "global") == scope
                    ]

                    if len(shared) < threshold:
                        continue

                    # Rule-based IPC heuristics
                    count = len(shared)
                    avg_salience = sum(e.salience for e in shared) / count
                    # colleague → 支配友好 (B=0.4, P=0.2); stranger → 友好 (B=0.2, P=0.0)
                    if count >= 10:
                        ipc_orientation = "支配友好"
                        benevolence = min(1.0, 0.3 + avg_salience * 0.4)
                        power = 0.2
                    else:
                        ipc_orientation = "友好"
                        benevolence = min(1.0, 0.1 + avg_salience * 0.3)
                        power = 0.0
                    affect_intensity = min(1.0, math.sqrt(benevolence ** 2 + power ** 2) / math.sqrt(2))
                    r_squared = 0.3  # low confidence — rule-based signal only

                    if existing:
                        alpha = cfg.impression_update_alpha
                        new_imp = dataclasses.replace(
                            existing,
                            ipc_orientation=ipc_orientation,
                            benevolence=round(existing.benevolence * (1 - alpha) + benevolence * alpha, 3),
                            power=round(existing.power * (1 - alpha) + power * alpha, 3),
                            affect_intensity=round(existing.affect_intensity * (1 - alpha) + affect_intensity * alpha, 3),
                            r_squared=round(existing.r_squared * (1 - alpha) + r_squared * alpha, 3),
                            last_reinforced_at=now,
                        )
                    else:
                        new_imp = Impression(
                            observer_uid=obs,
                            subject_uid=subj,
                            ipc_orientation=ipc_orientation,
                            benevolence=benevolence,
                            power=power,
                            affect_intensity=affect_intensity,
                            r_squared=r_squared,
                            confidence=0.3,
                            scope=scope,
                            evidence_event_ids=[e.event_id for e in shared[-5:]],
                            last_reinforced_at=now,
                        )

                    await impression_repo.upsert(new_imp)
                    logger.debug(
                        "[ImpressionTrigger] %s→%s scope=%s updated (count=%d, ipc=%s)",
                        obs[:8], subj[:8], scope, count, ipc_orientation,
                    )
                except Exception as exc:
                    logger.warning(
                        "[ImpressionTrigger] failed for %s→%s: %s", obs[:8], subj[:8], exc
                    )
