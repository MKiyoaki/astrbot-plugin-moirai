from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import StarTools, register

from web.server import WebuiServer

from core.adapters.astrbot import MessageRouter
from core.adapters.identity import IdentityResolver
from core.boundary.detector import EventBoundaryDetector
from core.config import PluginConfig
from core.domain.models import Event
from core.embedding.encoder import NullEncoder, SentenceTransformerEncoder
from core.extractor.extractor import EventExtractor
from core.managers import MemoryManager
from core.projector.projector import MarkdownProjector
from core.retrieval.formatter import format_events_for_prompt
from core.retrieval.hybrid import HybridRetriever
from core.sync.syncer import ReverseSyncer
from core.sync.watcher import FileWatcher
from core.tasks.scheduler import TaskScheduler
from core.tasks.summary import run_group_summary
from core.tasks.synthesis import run_impression_aggregation, run_persona_synthesis
from core.repository.sqlite import (
    SQLiteEventRepository,
    SQLiteImpressionRepository,
    SQLitePersonaRepository,
    db_open,
)

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.provider import ProviderRequest
    from astrbot.api.star import Context, Star
    from core.boundary.window import MessageWindow


_VEC_DIM = 512
_PLUGIN_VERSION = "0.1.0"
_PLUGIN_NAME = "EnhancedMemory"


@register(
    "astrbot_plugin_enhanced_memory",
    "DrGariton",
    "三轴长期记忆插件：情节轴 × 社会关系轴 × 叙事轴",
    _PLUGIN_VERSION,
    "https://github.com/MKiyoaki/astrbot-plugin-enhanced-memory",
)
class EnhancedMemoryPlugin(Star):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self._exit_stack: AsyncExitStack | None = None
        self.router: MessageRouter | None = None
        self.memory: MemoryManager | None = None
        self.projector: MarkdownProjector | None = None
        self._scheduler: TaskScheduler | None = None
        self._webui: WebuiServer | None = None
        self._watcher: FileWatcher | None = None
        self._syncer: ReverseSyncer | None = None

    @property
    def webui_registry(self):
        """对外暴露面板注册表，供其他插件挂载新面板。

        用法（在依赖本插件的插件 B 中）::

            em = context.get_registered_star("astrbot_plugin_enhanced_memory")
            em.webui_registry.register(PanelManifest(...), routes=[...])
        """
        return self._webui.registry if self._webui else None

    async def initialize(self) -> None:
        raw_cfg = self.config if hasattr(self, "config") and self.config else {}
        cfg = PluginConfig(raw_cfg)

        data_dir: Path = StarTools.get_data_dir("astrbot_plugin_enhanced_memory")
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
                _ = encoder.dim  # trigger lazy load to catch missing model early
            except Exception as exc:
                logger.warning(
                    f"[{_PLUGIN_NAME}] embedding model unavailable (%s), "
                    "vector search disabled", exc,
                )
                encoder = NullEncoder()
        else:
            encoder = NullEncoder()

        retriever = HybridRetriever(event_repo=event_repo, encoder=encoder)

        # MemoryManager owns CRUD, lifecycle, decay, and search.
        self.memory = MemoryManager(
            event_repo=event_repo,
            retriever=retriever,
            encoder=encoder,
            decay_config=cfg.get_decay_config(),
        )

        extractor = EventExtractor(
            event_repo=event_repo,
            provider_getter=lambda: self.context.get_using_provider(),
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

        def provider_getter(): return self.context.get_using_provider()  # noqa: E731

        synthesis_cfg = cfg.get_synthesis_config()
        summary_cfg = cfg.get_summary_config()

        self._scheduler = TaskScheduler()
        self._scheduler.register(
            "salience_decay",
            interval=cfg.decay_interval_seconds,
            fn=lambda: self.memory.apply_decay() if self.memory else None,
        )

        async def _projection_and_register() -> None:
            if self.projector:
                await self.projector.render_all_personas()
            if self._syncer:
                await self._syncer.register_all()

        self._scheduler.register(
            "projection",
            interval=cfg.summary_interval_seconds,
            fn=_projection_and_register,
        )
        self._scheduler.register(
            "persona_synthesis",
            interval=cfg.persona_synthesis_interval_seconds,
            fn=lambda: run_persona_synthesis(
                persona_repo, event_repo, provider_getter,
                synthesis_config=synthesis_cfg,
            ),
        )
        self._scheduler.register(
            "impression_aggregation",
            interval=cfg.impression_aggregation_interval_seconds,
            fn=lambda: run_impression_aggregation(
                persona_repo, event_repo, impression_repo, provider_getter,
                synthesis_config=synthesis_cfg,
            ),
        )
        self._scheduler.register(
            "group_summary",
            interval=cfg.summary_interval_seconds,
            fn=lambda: run_group_summary(
                event_repo, data_dir, provider_getter,
                summary_config=summary_cfg,
            ),
        )
        await self._scheduler.start()

        self._webui = WebuiServer(
            persona_repo=persona_repo,
            event_repo=event_repo,
            impression_repo=impression_repo,
            data_dir=data_dir,
            port=cfg.webui_port,
            auth_enabled=cfg.webui_auth_enabled,
            task_runner=self._scheduler.run_now,
            plugin_version=_PLUGIN_VERSION,
            initial_config=cfg.as_dict(),
        )
        if cfg.webui_enabled:
            await self._webui.start()
        else:
            logger.info(f"[{_PLUGIN_NAME}] WebUI disabled by config")

        self._watcher = FileWatcher()
        self._syncer = ReverseSyncer(
            data_dir=data_dir,
            persona_repo=persona_repo,
            impression_repo=impression_repo,
            watcher=self._watcher,
        )
        await self._syncer.register_all()
        await self._watcher.start()
        logger.info(f"[{_PLUGIN_NAME}] initialized — DB at %s", db_path)

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """Inject relevant memory context into the system prompt before LLM generation."""
        if self.memory is None or not req.prompt:
            return
        try:
            results = await self.memory.search(req.prompt, limit=10, active_only=True)
            if not results:
                return
            injected = format_events_for_prompt(results)
            if injected:
                sep = "\n\n" if req.system_prompt else ""
                req.system_prompt = req.system_prompt + sep + injected
        except Exception as exc:
            logger.warning(f"[{_PLUGIN_NAME}] retrieval hook failed: %s", exc)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent) -> None:
        if self.router is None:
            return
        await self.router.process(
            platform=event.get_platform_name(),
            physical_id=event.get_sender_id(),
            display_name=event.get_sender_name(),
            text=event.message_str,
            raw_group_id=event.get_group_id() or None,
            now=event.created_at,
        )

    async def terminate(self) -> None:
        if self._watcher is not None:
            await self._watcher.stop()
        if self._webui is not None:
            await self._webui.stop()
        if self._scheduler is not None:
            await self._scheduler.stop()
        if self.router is not None:
            await self.router.flush_all()
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        logger.info(f"[{_PLUGIN_NAME}] terminated")
