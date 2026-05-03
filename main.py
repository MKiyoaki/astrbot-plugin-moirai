from __future__ import annotations

from contextlib import AsyncExitStack
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

from core.adapters.astrbot import MessageRouter
from core.adapters.identity import IdentityResolver
from core.boundary.detector import BoundaryConfig, EventBoundaryDetector
from core.repository.sqlite import (
    SQLiteEventRepository,
    SQLiteImpressionRepository,
    SQLitePersonaRepository,
    db_open,
)


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

    async def initialize(self) -> None:
        data_dir: Path = StarTools.get_data_dir("astrbot_plugin_enhanced_memory")
        db_path = data_dir / "db" / "core.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._exit_stack = AsyncExitStack()
        db = await self._exit_stack.enter_async_context(db_open(db_path))

        persona_repo = SQLitePersonaRepository(db)
        event_repo = SQLiteEventRepository(db)
        _impression_repo = SQLiteImpressionRepository(db)

        resolver = IdentityResolver(persona_repo)
        detector = EventBoundaryDetector(BoundaryConfig())
        self.router = MessageRouter(
            event_repo=event_repo,
            identity_resolver=resolver,
            detector=detector,
            on_event_close=None,  # Phase 4 will wire the LLM extractor here
        )
        logger.info("[EnhancedMemory] initialized — DB at %s", db_path)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent) -> None:
        if self.router is None:
            return
        platform = event.get_platform_name()
        physical_id = event.get_sender_id()
        display_name = event.get_sender_name()
        text = event.message_str
        raw_group_id = event.get_group_id() or None
        timestamp = event.created_at

        await self.router.process(
            platform=platform,
            physical_id=physical_id,
            display_name=display_name,
            text=text,
            raw_group_id=raw_group_id,
            now=timestamp,
        )

    async def terminate(self) -> None:
        if self.router is not None:
            await self.router.flush_all()
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
        logger.info("[EnhancedMemory] terminated")
