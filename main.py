from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from astrbot.api.event import filter
from astrbot.api.star import StarTools, register

from core.config import PluginConfig
from core.event_handler import EventHandler
from core.plugin_initializer import PluginInitializer

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.provider import ProviderRequest
    from astrbot.api.star import Context, Star

_PLUGIN_VERSION = "0.4.4"


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
        self._initializer: PluginInitializer | None = None
        self._handler: EventHandler | None = None

    @property
    def webui_registry(self):
        """Expose panel registry for other plugins to mount extra panels."""
        if self._initializer and self._initializer.webui:
            return self._initializer.webui.registry
        return None

    async def initialize(self) -> None:
        raw_cfg = self.config if hasattr(self, "config") and self.config else {}
        cfg = PluginConfig(raw_cfg)
        data_dir: Path = StarTools.get_data_dir("astrbot_plugin_enhanced_memory")
        self._initializer = PluginInitializer(self.context, cfg, data_dir)
        await self._initializer.initialize()
        self._handler = EventHandler(self._initializer)

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        if self._handler:
            await self._handler.handle_llm_request(event, req)

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent) -> None:
        if self._handler:
            await self._handler.handle_message(event)

    async def terminate(self) -> None:
        if self._initializer:
            await self._initializer.teardown()
