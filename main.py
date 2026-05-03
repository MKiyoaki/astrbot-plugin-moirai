from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register

from core.adapters.astrbot import MessageRouter
from core.adapters.identity import IdentityResolver
from core.boundary.detector import BoundaryConfig, EventBoundaryDetector
from core.boundary.window import MessageWindow
from core.domain.models import Event
from core.embedding.encoder import NullEncoder, SentenceTransformerEncoder
from core.extractor.extractor import EventExtractor
from core.projector.projector import MarkdownProjector
from core.retrieval.formatter import format_events_for_prompt
from core.tasks.decay import run_salience_decay
from core.tasks.scheduler import TaskScheduler
from core.tasks.summary import run_group_summary
from core.tasks.synthesis import run_impression_aggregation, run_persona_synthesis
from core.retrieval.hybrid import HybridRetriever
from core.repository.sqlite import (
    SQLiteEventRepository,
    SQLiteImpressionRepository,
    SQLitePersonaRepository,
    db_open,
)

_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
_VEC_DIM = 512


@register(
    "astrbot_plugin_enhanced_memory",
    "DrGariton",
    "三轴长期记忆插件：情节轴 × 社会关系轴 × 叙事轴",
    "0.1.0",
    "https://github.com/DrGariton/astrbot-plugin-enhanced-memory",
)
class EnhancedMemoryPlugin(Star):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self._exit_stack: AsyncExitStack | None = None
        self.router: MessageRouter | None = None
        self.retriever: HybridRetriever | None = None
        self.projector: MarkdownProjector | None = None
        self._scheduler: TaskScheduler | None = None

    async def initialize(self) -> None:
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
        try:
            encoder = SentenceTransformerEncoder(_EMBEDDING_MODEL)
            _ = encoder.dim  # trigger lazy load to catch missing model early
        except Exception as exc:
            logger.warning("[EnhancedMemory] embedding model unavailable (%s), vector search disabled", exc)
            encoder = NullEncoder()

        self.retriever = HybridRetriever(event_repo=event_repo, encoder=encoder)

        extractor = EventExtractor(
            event_repo=event_repo,
            provider_getter=lambda: self.context.get_using_provider(),
            encoder=encoder,
        )

        async def on_event_close(event: Event, window: MessageWindow) -> None:
            asyncio.create_task(extractor(event, window))

        resolver = IdentityResolver(persona_repo)
        detector = EventBoundaryDetector(BoundaryConfig())
        self.router = MessageRouter(
            event_repo=event_repo,
            identity_resolver=resolver,
            detector=detector,
            on_event_close=on_event_close,
        )
        provider_getter = lambda: self.context.get_using_provider()  # noqa: E731

        self._scheduler = TaskScheduler()
        self._scheduler.register(
            "salience_decay",
            interval=86_400,
            fn=lambda: run_salience_decay(event_repo),
        )
        self._scheduler.register(
            "projection",
            interval=86_400,
            fn=lambda: self.projector.render_all_personas() if self.projector else None,
        )
        self._scheduler.register(
            "persona_synthesis",
            interval=604_800,
            fn=lambda: run_persona_synthesis(persona_repo, event_repo, provider_getter),
        )
        self._scheduler.register(
            "impression_aggregation",
            interval=604_800,
            fn=lambda: run_impression_aggregation(
                persona_repo, event_repo, impression_repo, provider_getter
            ),
        )
        self._scheduler.register(
            "group_summary",
            interval=86_400,
            fn=lambda: run_group_summary(event_repo, data_dir, provider_getter),
        )
        await self._scheduler.start()
        logger.info("[EnhancedMemory] initialized — DB at %s", db_path)

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """Inject relevant memory context into the system prompt before LLM generation."""
        if self.retriever is None or not req.prompt:
            return
        try:
            results = await self.retriever.search(req.prompt, limit=10)
            if not results:
                return
            injected = format_events_for_prompt(results)
            if injected:
                sep = "\n\n" if req.system_prompt else ""
                req.system_prompt = req.system_prompt + sep + injected
        except Exception as exc:
            logger.warning("[EnhancedMemory] retrieval hook failed: %s", exc)

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
        if self._scheduler is not None:
            await self._scheduler.stop()
        if self.router is not None:
            await self.router.flush_all()
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        logger.info("[EnhancedMemory] terminated")
