"""PluginInitializer: component wiring and lifecycle management.

Constructs all subsystems in dependency order and tears them down in reverse.
main.py instantiates this class and delegates to it; all business logic stays
out of the Star shell.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING

from astrbot.api import logger as astrbot_logger

from .adapters.astrbot import MessageRouter
from .adapters.identity import IdentityResolver
from .boundary.detector import EventBoundaryDetector
from .config import PluginConfig
from .domain.models import Event
from .embedding.encoder import NullEncoder, SentenceTransformerEncoder
from .extractor.extractor import EventExtractor
from .managers import MemoryManager, RecallManager
from .projector.projector import MarkdownProjector
from .repository.sqlite import (
    SQLiteEventRepository,
    SQLiteImpressionRepository,
    SQLitePersonaRepository,
    db_open,
)
from .retrieval.hybrid import HybridRetriever
from .sync.syncer import ReverseSyncer
from .sync.watcher import FileWatcher
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

        db_path = data_dir / "db" / "core.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._exit_stack = AsyncExitStack()
        db = await self._exit_stack.enter_async_context(
            db_open(db_path, vec_dim=_VEC_DIM)
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

        # Encoder: try local model, fall back to null (BM25-only) on any error
        if cfg.embedding_enabled:
            try:
                encoder = SentenceTransformerEncoder(cfg.embedding_model)
                _ = encoder.dim  # trigger lazy load early
            except Exception as exc:
                astrbot_logger.warning(
                    "[%s] embedding model unavailable (%s), vector search disabled",
                    _PLUGIN_NAME, exc,
                )
                encoder = NullEncoder()
        else:
            encoder = NullEncoder()

        retriever = HybridRetriever(
            event_repo=event_repo,
            encoder=encoder,
            bm25_limit=cfg.get_retrieval_config().bm25_limit,
            vec_limit=cfg.get_retrieval_config().vec_limit,
            rrf_k=cfg.get_retrieval_config().rrf_k,
        )

        self.memory = MemoryManager(
            event_repo=event_repo,
            retriever=retriever,
            encoder=encoder,
            decay_config=cfg.get_decay_config(),
        )

        self.recall = RecallManager(
            retriever=retriever,
            retrieval_config=cfg.get_retrieval_config(),
            injection_config=cfg.get_injection_config(),
        )

        extractor = EventExtractor(
            event_repo=event_repo,
            provider_getter=lambda: self._context.get_using_provider(),
            encoder=encoder,
            extractor_config=cfg.get_extractor_config(),
        )

        async def on_event_close(event: Event, window: MessageWindow) -> None:
            asyncio.create_task(extractor(event, window))

        resolver = IdentityResolver(persona_repo)
        detector = EventBoundaryDetector(cfg.get_boundary_config())
        self.router = MessageRouter(
            event_repo=event_repo,
            identity_resolver=resolver,
            detector=detector,
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

        astrbot_logger.info("[%s] initialized — DB at %s", _PLUGIN_NAME, db_path)

    async def teardown(self) -> None:
        if self.watcher is not None:
            await self.watcher.stop()
        if self.webui is not None:
            await self.webui.stop()
        if self.scheduler is not None:
            await self.scheduler.stop()
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
        return "0.1.0"
