"""CommandManager: handler logic for /mrm command group.

Delegates to the appropriate subsystem for each sub-command so that
main.py stays thin.  All methods return plain strings ready to send.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..utils.formatter import format_events_for_prompt

if TYPE_CHECKING:
    from ..managers.context_manager import ContextManager
    from ..managers.recall_manager import RecallManager
    from ..tasks.scheduler import TaskScheduler
    from ..web.server import WebuiServer  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)


class CommandManager:
    def __init__(
        self,
        scheduler: TaskScheduler,
        recall: RecallManager,
        context_manager: ContextManager | None = None,
        webui: object | None = None,
    ) -> None:
        self._scheduler = scheduler
        self._recall = recall
        self._ctx = context_manager
        self._webui = webui

    async def status(self) -> str:
        tasks = self._scheduler.task_names
        sessions = self._ctx.active_sessions_count if self._ctx else "N/A"
        webui_status = "运行中" if (self._webui and getattr(self._webui, "_runner", None)) else "未运行"
        lines = [
            "【Moirai 插件状态】",
            f"已注册任务：{', '.join(tasks) if tasks else '无'}",
            f"活跃会话数：{sessions}",
            f"WebUI：{webui_status}",
        ]
        return "\n".join(lines)

    async def run_task(self, task: str) -> str:
        ok = await self._scheduler.run_now(task.strip())
        if ok:
            return f"任务 '{task}' 已触发执行。"
        available = ", ".join(self._scheduler.task_names)
        return f"未找到任务 '{task}'。可用任务：{available or '无'}"

    async def flush(self, session_id: str) -> str:
        if self._ctx is None:
            return "上下文管理器未启用。"
        window = self._ctx.pop_window(session_id)
        if window is None:
            return "当前会话无活跃上下文窗口。"
        count = len(window.messages) if hasattr(window, "messages") else "?"
        return f"已清空当前会话窗口（{count} 条消息）。"

    async def recall(self, query: str, group_id: str | None = None) -> str:
        results = await self._recall.recall(query, group_id=group_id)
        if not results:
            return f"未找到与「{query}」相关的记忆。"
        return format_events_for_prompt(results, token_budget=800)

    async def help(self) -> str:
        return (
            "【Moirai 插件指令帮助】\n"
            "/mrm status          - 查询插件运行状态\n"
            "/mrm run <task>      - 手动触发周期任务 (decay/synthesis/summary/cleanup)\n"
            "/mrm flush           - 清空当前会话的上下文窗口\n"
            "/mrm recall <query>  - 手动触发记忆检索\n"
            "/mrm webui on|off    - 启用或关闭 WebUI\n"
            "/mrm help            - 显示此帮助信息"
        )

    async def webui(self, action: str) -> str:
        action = action.strip().lower()
        if self._webui is None:
            return "WebUI 模块未加载。"
        if action == "on":
            try:
                await self._webui.start()
                host = getattr(self._webui, "_host", "localhost")
                port = getattr(self._webui, "_port", "?")
                return f"WebUI 已启动：http://{host}:{port}"
            except Exception as e:
                return f"WebUI 启动失败：{e}"
        elif action == "off":
            try:
                await self._webui.stop()
                return "WebUI 已关闭。"
            except Exception as e:
                return f"WebUI 关闭失败：{e}"
        return "用法：/mrm webui on | off"
