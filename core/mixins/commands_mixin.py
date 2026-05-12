from __future__ import annotations
from typing import TYPE_CHECKING
from astrbot.api.event import filter

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from ..plugin_initializer import PluginInitializer

class CommandsMixin:
    """Mixin for AstrBot command registration and routing."""

    @filter.command_group("mrm")
    def mrm(self):
        """Moirai Memory Manager command group."""
        pass

    @mrm.command("status")
    async def mrm_status(self, event: AstrMessageEvent):
        '''查询插件运行状态。用法：/mrm status'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        cmd = initializer.command_manager
        yield event.plain_result(await cmd.status())

    @mrm.command("run")
    async def mrm_run(self, event: AstrMessageEvent, task: str):
        '''手动触发周期任务。用法：/mrm run <task>（decay / synthesis / summary / cleanup）'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        cmd = initializer.command_manager
        yield event.plain_result(await cmd.run_task(task))

    @mrm.command("flush")
    async def mrm_flush(self, event: AstrMessageEvent):
        '''清空当前会话的上下文窗口。用法：/mrm flush'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        cmd = initializer.command_manager
        session_id = event.unified_msg_origin
        yield event.plain_result(await cmd.flush(session_id))

    @mrm.command("recall")
    async def mrm_recall(self, event: AstrMessageEvent, query: str):
        '''手动触发记忆检索并返回结果。用法：/mrm recall <关键词>'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        cmd = initializer.command_manager
        group_id = event.get_group_id() if hasattr(event, "get_group_id") else None
        yield event.plain_result(await cmd.recall(query, group_id=group_id))

    @mrm.command("webui")
    async def mrm_webui(self, event: AstrMessageEvent, action: str):
        '''启用或关闭 WebUI。用法：/mrm webui on | off'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        cmd = initializer.command_manager
        yield event.plain_result(await cmd.webui(action))

    @mrm.command("help")
    async def mrm_help(self, event: AstrMessageEvent):
        '''显示插件指令介绍。用法：/mrm help'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        cmd = initializer.command_manager
        yield event.plain_result(await cmd.help())
