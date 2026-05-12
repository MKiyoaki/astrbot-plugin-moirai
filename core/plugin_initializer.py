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

try:
    from astrbot.api import logger as astrbot_logger
except:
    # Fallback if astrbot.api.logger is not available (e.g., during testing)
    astrbot_logger = logging.getLogger("astrbot_plugin_enhanced_memory")

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
from .managers.llm_manager import LLMTaskManager
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
from .utils.version import get_plugin_version
from .tasks.cleanup import run_memory_cleanup
from .tasks.scheduler import TaskScheduler
from .tasks.summary import run_group_summary
from .tasks.synthesis import run_impression_recalculation, run_persona_synthesis

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
        self.persona_repo = None
        self.resolver = None
        self.command_manager = None

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
            lang=cfg.language,
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

        self.llm_manager = LLMTaskManager(concurrency=cfg.llm_concurrency)

        self.context_manager = ContextManager(
            cfg.get_context_config(),
            evict_callback=None,  # set after extractor is built below
        )

        retrieval_cfg = cfg.get_retrieval_config()
        retriever = HybridRetriever(
            event_repo=event_repo,
            encoder=self.embedding_manager,  # Use manager as encoder
            bm25_limit=retrieval_cfg.bm25_limit,
            vec_limit=retrieval_cfg.vec_limit,
            rrf_k=retrieval_cfg.rrf_k,
            weighted_random=retrieval_cfg.weighted_random,
            sampling_temperature=retrieval_cfg.sampling_temperature,
        )

        self.memory = MemoryManager(
            event_repo=event_repo,
            retriever=retriever,
            encoder=self.embedding_manager,  # Use manager
            decay_config=cfg.get_decay_config(),
        )

        self.persona_repo = persona_repo
        self.recall = RecallManager(
            retriever=retriever,
            retrieval_config=cfg.get_retrieval_config(),
            injection_config=cfg.get_injection_config(),
            persona_repo=persona_repo,
            soul_config=cfg.get_soul_config(),
        )

        ipc_cfg = cfg.get_ipc_config()
        big_five_buffer: BigFiveBuffer | None = None
        orientation_analyzer: SocialOrientationAnalyzer | None = None
        if ipc_cfg.enabled and cfg.relation_enabled:
            big_five_buffer = BigFiveBuffer(
                x_messages=ipc_cfg.bigfive_x_messages,
                llm_timeout=ipc_cfg.bigfive_llm_timeout,
            )
            orientation_analyzer = SocialOrientationAnalyzer(
                impression_repo=impression_repo,
                event_repo=event_repo,
                cfg=cfg,
            )

        def provider_getter():
            if cfg.llm_provider:
                return self._context.get_using_provider(cfg.llm_provider)
            return self._context.get_using_provider()

        extractor = EventExtractor(
            event_repo=event_repo,
            provider_getter=provider_getter,
            encoder=self.embedding_manager,
            extractor_config=cfg.get_extractor_config(),
            big_five_buffer=big_five_buffer,
            orientation_analyzer=orientation_analyzer,
            ipc_enabled=ipc_cfg.enabled,
            persona_repo=persona_repo,
            llm_manager=self.llm_manager,
        )

        async def on_event_close(window: MessageWindow) -> None:
            asyncio.create_task(extractor(window))

        # Wire the same callback into ContextManager so LRU-evicted windows are
        # also extracted instead of silently dropped.
        self.context_manager._evict_callback = on_event_close

        resolver = IdentityResolver(persona_repo, default_confidence=cfg.persona_default_confidence)
        self.resolver = resolver
        detector = EventBoundaryDetector(cfg.get_boundary_config(), encoder=self.embedding_manager)
        self.router = MessageRouter(
            event_repo=event_repo,
            identity_resolver=resolver,
            detector=detector,
            context_manager=self.context_manager,
            encoder=self.embedding_manager,
            on_event_close=on_event_close,
        )

        synthesis_cfg = cfg.get_synthesis_config()
        summary_cfg = cfg.get_summary_config()

        self.scheduler = TaskScheduler()

        # Daily maintenance: decay → cleanup → projection (order matters).
        # Decay runs first so archived events are excluded from the projection render.
        cleanup_cfg = cfg.get_cleanup_config()
        async def _daily_maintenance() -> None:
            if cfg.decay_enabled and self.memory:
                await self.memory.apply_decay()
            if cleanup_cfg.enabled:
                await run_memory_cleanup(event_repo, cleanup_cfg)
            if cfg.markdown_projection_enabled:
                if self.projector:
                    await self.projector.render_all_personas()
                if self.syncer:
                    await self.syncer.register_all()

        self.scheduler.register(
            "daily_maintenance",
            interval=cfg.decay_interval_seconds,
            fn=_daily_maintenance,
        )
        self.scheduler.register(
            "context_cleanup",
            interval=60,
            fn=lambda: self.context_manager.cleanup_expired() if self.context_manager else None,
        )
        if cfg.persona_synthesis_enabled:
            self.scheduler.register(
                "persona_synthesis",
                interval=cfg.persona_synthesis_interval_seconds,
                fn=lambda: run_persona_synthesis(
                    persona_repo, event_repo, provider_getter,
                    synthesis_config=synthesis_cfg,
                    llm_manager=self.llm_manager,
                ),
            )
        if cfg.relation_enabled:
            self.scheduler.register(
                "impression_recalculation",
                interval=cfg.impression_aggregation_interval_seconds,
                fn=lambda: run_impression_recalculation(
                    persona_repo, event_repo, impression_repo,
                ),
            )
        if cfg.summary_enabled:
            self.scheduler.register(
                "group_summary",
                interval=cfg.summary_interval_seconds,
                fn=lambda: run_group_summary(
                    event_repo, data_dir, provider_getter,
                    summary_config=summary_cfg,
                    persona_repo=persona_repo,
                    impression_repo=impression_repo,
                    llm_manager=self.llm_manager,
                ),
            )
        await self.scheduler.start()

        from .tasks.reindex import run_reindex_all
        self.scheduler.register(
            "reindex_all",
            interval=0,  # Manual trigger only
            fn=lambda: run_reindex_all(event_repo, retriever),
        )

        from web.server import WebuiServer
        self.webui = WebuiServer(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=data_dir,
            port=cfg.webui_port,
            auth_enabled=cfg.webui_auth_enabled,
            task_runner=self.scheduler.run_now,
            plugin_version=get_plugin_version(),
            initial_config=cfg.as_dict(),
            provider_getter=provider_getter,
            all_providers_getter=self._context.get_all_providers,
            recall_manager=self.recall,
        )
        if cfg.webui_enabled:
            await self.webui.start()
        else:
            astrbot_logger.info("[%s] WebUI disabled by config", _PLUGIN_NAME)

        if cfg.markdown_projection_enabled:
            self.watcher = FileWatcher()
            self.syncer = ReverseSyncer(
                data_dir=data_dir,
                persona_repo=persona_repo,
                impression_repo=impression_repo,
                watcher=self.watcher,
            )
            await self.syncer.register_all()
            await self.watcher.start()
        else:
            astrbot_logger.info("[%s] Markdown projection disabled by config", _PLUGIN_NAME)
        if self.embedding_manager:
            await self.embedding_manager.start()

        from .managers.command_manager import CommandManager
        from .utils.i18n import LANG_ZH, LANG_EN, LANG_JA
        _lang_map = {"zh-CN": LANG_ZH, "en-US": LANG_EN, "ja-JP": LANG_JA}
        self.command_manager = CommandManager(
            scheduler=self.scheduler,
            recall=self.recall,
            context_manager=self.context_manager,
            webui=self.webui,
            persona_repo=persona_repo,
            event_repo=event_repo,
            data_dir=data_dir,
            initial_lang=_lang_map.get(cfg.language, LANG_ZH),
        )

        astrbot_logger.info("[%s] initialized — DB at %s",
                            _PLUGIN_NAME, db_path)

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



