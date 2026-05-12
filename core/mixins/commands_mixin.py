from __future__ import annotations
from typing import TYPE_CHECKING
from astrbot.api.event import filter

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from ..plugin_initializer import PluginInitializer


class CommandsMixin:
    """Mixin for AstrBot command registration and routing."""

    @filter.command_group("mrm")
    def mrm():
        """Moirai Memory Manager command group."""
        pass

    # ------------------------------------------------------------------
    # Info queries
    # ------------------------------------------------------------------

    @mrm.command("status")
    async def mrm_status(self, event: AstrMessageEvent):
        '''查询插件运行状态。用法：/mrm status'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        yield event.plain_result(await initializer.command_manager.status())

    @mrm.command("persona")
    async def mrm_persona(self, event: AstrMessageEvent, platform_id: str):
        '''查看用户人格档案 + 大五人格。用法：/mrm persona <PlatID>'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        platform = event.get_platform_name()
        yield event.plain_result(
            await initializer.command_manager.persona(platform, platform_id)
        )

    @mrm.command("soul")
    async def mrm_soul(self, event: AstrMessageEvent):
        '''查看当前会话情绪状态。用法：/mrm soul'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        session_id = event.unified_msg_origin
        soul_states = (
            initializer.recall._soul_states
            if initializer.recall is not None
            else {}
        )
        yield event.plain_result(
            await initializer.command_manager.soul(session_id, soul_states)
        )

    @mrm.command("recall")
    async def mrm_recall(self, event: AstrMessageEvent, query: str):
        '''手动触发记忆检索并返回结果。用法：/mrm recall <关键词>'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        group_id = event.get_group_id() if hasattr(event, "get_group_id") else None
        yield event.plain_result(
            await initializer.command_manager.recall(query, group_id=group_id)
        )

    # ------------------------------------------------------------------
    # Action commands
    # ------------------------------------------------------------------

    @mrm.command("webui")
    async def mrm_webui(self, event: AstrMessageEvent, action: str):
        '''启用或关闭 WebUI。用法：/mrm webui on | off'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        yield event.plain_result(await initializer.command_manager.webui(action))

    @mrm.command("flush")
    async def mrm_flush(self, event: AstrMessageEvent):
        '''清空当前会话的上下文窗口（不删数据库）。用法：/mrm flush'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        session_id = event.unified_msg_origin
        yield event.plain_result(await initializer.command_manager.flush(session_id))

    @mrm.command("language")
    async def mrm_language(self, event: AstrMessageEvent, code: str):
        '''切换指令显示语言。用法：/mrm language <cn/en/ja>'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("Plugin not initialized.")
            return
        yield event.plain_result(await initializer.command_manager.set_language(code))

    @mrm.command("run")
    async def mrm_run(self, event: AstrMessageEvent, task: str):
        '''手动触发周期任务。用法：/mrm run <task>（decay / synthesis / summary / cleanup）'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        yield event.plain_result(await initializer.command_manager.run_task(task))

    # ------------------------------------------------------------------
    # Reset commands (two-step confirmation required)
    # ------------------------------------------------------------------

    @mrm.command("reset")
    async def mrm_reset(self, event: AstrMessageEvent, scope: str, target: str = ""):
        '''
        重置数据（均需二次确认）。用法：
          /mrm reset here                — 删除当前群所有事件与摘要
          /mrm reset event <group_id>    — 删除指定群组事件与摘要
          /mrm reset event all           — 删除所有事件记录
          /mrm reset persona <PlatID>    — 删除指定用户人格档案
          /mrm reset persona all         — 删除全部人格数据
          /mrm reset all                 — 清空全部插件数据
        '''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return

        cmd = initializer.command_manager
        session_id = event.unified_msg_origin
        platform = event.get_platform_name()
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
                result = await cmd.reset_persona_one(session_id, platform, target)
            else:
                result = "用法：/mrm reset persona <PlatID> | all"
        elif scope == "all":
            result = await cmd.reset_all(session_id)
        else:
            result = (
                "用法：/mrm reset here | "
                "event <group_id|all> | "
                "persona <PlatID|all> | "
                "all"
            )

        yield event.plain_result(result)

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    @mrm.command("help")
    async def mrm_help(self, event: AstrMessageEvent):
        '''显示插件指令介绍。用法：/mrm help'''
        initializer: PluginInitializer = getattr(self, "_initializer", None)
        if not initializer:
            yield event.plain_result("插件未初始化。")
            return
        yield event.plain_result(await initializer.command_manager.help())
