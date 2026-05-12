from __future__ import annotations

import sys
from pathlib import Path

# Add the plugin's root directory to sys.path to ensure 'core' can be imported
# when the plugin is loaded by AstrBot in various environments.
_ROOT_DIR = Path(__file__).parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

import time
import uuid
from typing import TYPE_CHECKING

from astrbot.api.event import filter
from astrbot.api.star import Context, Star, StarTools, register

from core.config import PluginConfig
from core.domain.models import Event
from core.event_handler import EventHandler
from core.plugin_initializer import PluginInitializer
from core.utils.version import get_plugin_version
from core.utils.formatter import format_events_for_prompt
from core.mixins.commands_mixin import CommandsMixin

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.provider import ProviderRequest

_PLUGIN_VERSION = get_plugin_version()


@register(
    "moirai",
    "DrGariton, MKiyoaki",
    "三轴长期记忆插件：在多维世界线下管理机器人的记忆和社交关系理解。",
    _PLUGIN_VERSION,
    "https://github.com/MKiyoaki/astrbot-plugin-moirai",
)
class MoiraiPlugin(Star, CommandsMixin):
    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self._initializer: PluginInitializer | None = None
        self._handler: EventHandler | None = None

    @property
    def webui_registry(self):
        """Expose panel registry for other plugins to mount extra panels."""
        if self._initializer:
            # Prefer PluginRoutes registry (AstrBot Plugin Pages path)
            if hasattr(self._initializer, "plugin_routes") and self._initializer.plugin_routes:
                return self._initializer.plugin_routes.registry
            # Fallback to standalone debug server registry
            if self._initializer.webui:
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

    # ── LLM Tools ────────────────────────────────────────────────────────────

    @filter.llm_tool(name="core_memory_remember")
    async def tool_remember(self, event: AstrMessageEvent, content: str, strength: float):
        '''主动将重要信息存入长期记忆。仅在用户明确表示"记住"或对话中出现值得永久保存的关键事实时调用。

        Args:
            content(string): 要记住的内容，应为完整的一句话或一段描述
            strength(float): 重要程度，0.0（低）到 1.0（高），默认 0.7
        '''
        if not self._initializer:
            yield event.plain_result("记忆系统未初始化。")
            return
        salience = max(0.0, min(1.0, float(strength)))
        now = time.time()
        group_id = event.get_group_id() if hasattr(event, "get_group_id") else None
        new_event = Event(
            event_id=str(uuid.uuid4()),
            group_id=group_id,
            start_time=now,
            end_time=now,
            topic="主动记忆",
            summary=content[:200],
            salience=salience,
            confidence=0.9,
        )
        await self._initializer.memory.add_event(new_event)
        yield event.plain_result(f"已记住（重要度 {salience:.1f}）。")

    @filter.llm_tool(name="core_memory_recall")
    async def tool_recall(self, event: AstrMessageEvent, query: str):
        '''主动检索与当前话题相关的历史记忆。仅在需要回忆过去对话内容时调用，不要在每次对话中都调用。

        Args:
            query(string): 检索关键词或问题描述
        '''
        if not self._initializer:
            yield event.plain_result("记忆系统未初始化。")
            return
        group_id = event.get_group_id() if hasattr(event, "get_group_id") else None
        results = await self._initializer.recall.recall(query, group_id=group_id)
        if not results:
            yield event.plain_result("未找到相关记忆。")
            return
        formatted = format_events_for_prompt(results, token_budget=600)
        yield event.plain_result(formatted)

    async def terminate(self) -> None:
        if self._initializer:
            await self._initializer.teardown()
