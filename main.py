from __future__ import annotations
import sys
from pathlib import Path

# Must be first: add plugin root to sys.path before any local imports so
# AstrBot can resolve 'core' regardless of its working directory.
_ROOT_DIR = Path(__file__).parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from core.utils.formatter import format_events_for_prompt
from core.utils.version import get_plugin_version
from core.plugin_initializer import PluginInitializer
from core.event_handler import EventHandler
from core.domain.models import Event
from core.config import PluginConfig
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.api.event import filter
from typing import TYPE_CHECKING
import uuid
import time


if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.provider import ProviderRequest, ProviderResponse
    from astrbot.api.model import CommandResult

_PLUGIN_VERSION = get_plugin_version()


@register(
    "moirai",
    "DrGariton, MKiyoaki",
    "三轴长期记忆插件：在多维世界线下管理机器人的记忆和社交关系理解。",
    _PLUGIN_VERSION,
    "https://github.com/MKiyoaki/astrbot-plugin-moirai",
)
class MoiraiPlugin(Star):
    def __init__(self, context: Context, config: dict | None = None) -> None:
        super().__init__(context, config)
        self.config = config or {}
        self._initializer: PluginInitializer | None = None
        self._handler: EventHandler | None = None

    @property
    def webui_registry(self):
        """Expose panel registry for other plugins to mount extra panels."""
        if self._initializer:
            if hasattr(self._initializer, "plugin_routes") and self._initializer.plugin_routes:
                return self._initializer.plugin_routes.registry
            if self._initializer.webui:
                return self._initializer.webui.registry
        return None

    async def initialize(self) -> None:
        data_dir: Path = StarTools.get_data_dir("astrbot_plugin_moirai")
        raw_cfg = self.config if hasattr(
            self, "config") and self.config else {}
        cfg = PluginConfig(raw_cfg)
        initializer = PluginInitializer(self.context, cfg, data_dir)
        initializer._star = self
        self._initializer = initializer
        await self._initializer.initialize()
        self._handler = EventHandler(self._initializer)

    # ── Message hooks ─────────────────────────────────────────────────────────

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        if self._handler:
            await self._handler.handle_llm_request(event, req)

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: ProviderResponse) -> None:
        if self._handler:
            await self._handler.handle_llm_response(event, resp)

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent) -> None:
        if self._handler:
            result = event.get_result()
            if result is not None:
                await self._handler.handle_decorating_result(event, result)

    @filter.on_using_llm_tool()
    async def on_using_llm_tool(self, event: AstrMessageEvent, tool_name: str, arguments: dict) -> None:
        if self._handler:
            await self._handler.handle_using_llm_tool(event, tool_name, arguments)

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

    # ── Command group: /mrm ───────────────────────────────────────────────────

    @filter.command_group("mrm")
    def mrm():
        pass

    @mrm.command("status")
    async def mrm_status(self, event: AstrMessageEvent):
        '''查询插件运行状态。用法：/mrm status'''
        if not self._initializer:
            yield event.plain_result("插件未初始化。")
            return
        yield event.plain_result(await self._initializer.command_manager.status())

    @mrm.command("persona")
    async def mrm_persona(self, event: AstrMessageEvent, platform_id: str):
        '''查看用户人格档案 + 大五人格。用法：/mrm persona <PlatID>'''
        if not self._initializer:
            yield event.plain_result("插件未初始化。")
            return
        yield event.plain_result(
            await self._initializer.command_manager.persona(
                event.get_platform_name(), platform_id
            )
        )

    @mrm.command("soul")
    async def mrm_soul(self, event: AstrMessageEvent):
        '''查看当前会话情绪状态。用法：/mrm soul'''
        if not self._initializer:
            yield event.plain_result("插件未初始化。")
            return
        soul_states = (
            self._initializer.recall._soul_states
            if self._initializer.recall is not None
            else {}
        )
        yield event.plain_result(
            await self._initializer.command_manager.soul(
                event.unified_msg_origin, soul_states
            )
        )

    @mrm.command("recall")
    async def mrm_recall(self, event: AstrMessageEvent, query: str):
        '''手动触发记忆检索并返回结果。用法：/mrm recall <关键词>'''
        if not self._initializer:
            yield event.plain_result("插件未初始化。")
            return
        group_id = event.get_group_id() if hasattr(event, "get_group_id") else None
        yield event.plain_result(
            await self._initializer.command_manager.recall(query, group_id=group_id)
        )

    @mrm.command("webui")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mrm_webui(self, event: AstrMessageEvent, action: str):
        '''启用或关闭 WebUI。用法：/mrm webui on | off'''
        if not self._initializer:
            yield event.plain_result("插件未初始化。")
            return
        yield event.plain_result(await self._initializer.command_manager.webui(action))

    @mrm.command("flush")
    async def mrm_flush(self, event: AstrMessageEvent):
        '''清空当前会话的上下文窗口（不删数据库）。用法：/mrm flush'''
        if not self._initializer:
            yield event.plain_result("插件未初始化。")
            return
        yield event.plain_result(
            await self._initializer.command_manager.flush(event.unified_msg_origin)
        )

    @mrm.command("language")
    async def mrm_language(self, event: AstrMessageEvent, code: str):
        '''切换指令显示语言。用法：/mrm language <cn/en/ja>'''
        if not self._initializer:
            yield event.plain_result("Plugin not initialized.")
            return
        yield event.plain_result(
            await self._initializer.command_manager.set_language(code)
        )

    @mrm.command("run")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mrm_run(self, event: AstrMessageEvent, task: str):
        '''手动触发周期任务。用法：/mrm run <task>（decay/synthesis/summary/cleanup）'''
        if not self._initializer:
            yield event.plain_result("插件未初始化。")
            return
        yield event.plain_result(
            await self._initializer.command_manager.run_task(task)
        )

    @mrm.command("reset")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mrm_reset(self, event: AstrMessageEvent, scope: str, target: str = ""):
        '''重置数据（均需二次确认）。用法：/mrm reset here | event <id|all> | persona <id|all> | all'''
        if not self._initializer:
            yield event.plain_result("插件未初始化。")
            return
        cmd = self._initializer.command_manager
        session_id = event.unified_msg_origin
        group_id = event.get_group_id() if hasattr(event, "get_group_id") else None
        scope = scope.strip().lower()
        target = target.strip()

        if scope == "here":
            result = await cmd.reset_here(session_id, group_id)
        elif scope == "event":
            if target == "all":
                result = await cmd.reset_event_all(session_id)
            elif target:
                result = await cmd.reset_event_by_group(session_id, target)
            else:
                result = "用法：/mrm reset event <group_id> | all"
        elif scope == "persona":
            if target == "all":
                result = await cmd.reset_persona_all(session_id)
            elif target:
                result = await cmd.reset_persona_one(session_id, event.get_platform_name(), target)
            else:
                result = "用法：/mrm reset persona <PlatID> | all"
        elif scope == "all":
            result = await cmd.reset_all(session_id)
        else:
            result = "用法：/mrm reset here | event <group_id|all> | persona <PlatID|all> | all"

        yield event.plain_result(result)

    @mrm.command("help")
    async def mrm_help(self, event: AstrMessageEvent):
        '''显示插件指令介绍。用法：/mrm help'''
        if not self._initializer:
            yield event.plain_result("插件未初始化。")
            return
        yield event.plain_result(await self._initializer.command_manager.help())

    @mrm.group("dep")
    def mrm_dep():
        pass

    @mrm_dep.command("install")
    @filter.permission_type(filter.PermissionType.ADMIN)
    async def mrm_dep_install(self, event: AstrMessageEvent, lib: str):
        '''安装可选依赖。用法：/mrm dep install <lib>'''
        if not self._initializer:
            yield event.plain_result("插件未初始化。")
            return
        cmd = self._initializer.command_manager
        # Send an immediate feedback as installation might take time
        yield event.plain_result(cmd._t("cmd.dep.installing", lib=lib))
        result = await cmd.install_dependency(lib, event)
        yield event.plain_result(result)

    async def terminate(self) -> None:
        if self._initializer:
            await self._initializer.teardown()
