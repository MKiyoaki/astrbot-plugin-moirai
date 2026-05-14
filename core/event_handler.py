"""EventHandler: AstrBot event dispatch layer.

Receives AstrBot events and delegates to the appropriate subsystem.
Keeps main.py free of business logic; all routing decisions live here.
"""
from __future__ import annotations

import logging
import re as _re
from typing import TYPE_CHECKING

_EM_BLOCK_RE = _re.compile(
    r"<!-- EM:MEMORY:START -->.*?<!-- EM:MEMORY:END -->",
    _re.DOTALL,
)


def _check_is_admin(event) -> bool:
    try:
        role = getattr(event, "role", None)
        if role is not None:
            return str(role).lower() in ("admin", "superadmin", "operator", "owner")
    except Exception:
        pass
    return False


def _prepend_to_result(result, text: str) -> None:
    """Prepend text to a CommandResult (MessageEventResult inherits MessageChain = list)."""
    from astrbot.api.message_components import Plain
    result.insert(0, Plain(text))

from astrbot.api import logger as astrbot_logger

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.provider import ProviderRequest, ProviderResponse
    from astrbot.api.model import CommandResult
    from .plugin_initializer import PluginInitializer

_PLUGIN_NAME = "EnhancedMemory"
logger = logging.getLogger(__name__)


class EventHandler:
    """Delegates AstrBot event callbacks to subsystems via PluginInitializer."""

    def __init__(self, initializer: PluginInitializer) -> None:
        self._init = initializer
        self._pre_inject_sys_prompt: dict[str, str] = {}

    async def handle_llm_request(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        """Inject relevant memory context into the request before LLM generation."""
        from .utils.perf import performance_timer
        async with performance_timer("response"):
            recall = self._init.recall
            if recall is None:
                return

            # Use the raw message text as the query to avoid injecting stale memory
            # as part of the query (req.prompt may already contain injected content).
            query = event.message_str
            if not query:
                query = req.prompt or ""
            if not query:
                return

            try:
                session_id = event.unified_msg_origin
                group_id = event.get_group_id() or None

                # Capture system_prompt before injection for show_system_prompt feature.
                if recall is not None:
                    icfg = self._init.cfg.get_injection_config()
                    if icfg.show_system_prompt:
                        self._pre_inject_sys_prompt[session_id] = (
                            getattr(req, "system_prompt", "") or ""
                        )

                # Resolve sender uid for OCEAN persona injection (best-effort).
                sender_uid: str | None = None
                resolver = self._init.resolver
                if resolver is not None:
                    try:
                        sender_uid = await resolver.get_or_create_uid(
                            platform=event.get_platform_name(),
                            physical_id=event.get_sender_id(),
                            display_name=event.get_sender_name(),
                        )
                    except Exception:
                        pass

                injected_count = await recall.recall_and_inject(
                    query=query,
                    req=req,
                    session_id=session_id,
                    group_id=group_id,
                    sender_uid=sender_uid,
                )
                
                # Sync VCM state with hit rate feedback
                cm = self._init.context_manager
                if cm is not None:
                    cm.update_state(session_id, recall_hit=(injected_count > 0))
                    
            except Exception as exc:
                astrbot_logger.warning("[%s] recall hook failed: %s", _PLUGIN_NAME, exc)

    async def handle_message(self, event: AstrMessageEvent) -> None:
        """Route incoming messages through the event boundary detector."""
        router = self._init.router
        if router is None:
            return
        await router.process(
            platform=event.get_platform_name(),
            physical_id=event.get_sender_id(),
            display_name=event.get_sender_name(),
            text=event.message_str,
            raw_group_id=event.get_group_id() or None,
            now=event.created_at,
        )

    async def handle_llm_response(
        self, event: AstrMessageEvent, resp: ProviderResponse
    ) -> None:
        """Record the bot's own response into the memory stream."""
        router = self._init.router
        if router is None or not resp.text:
            return
            
        # Use a special internal UID for the bot to distinguish it from users.
        # router.process will handle get_or_create_uid.
        await router.process(
            platform="internal",
            physical_id="bot",
            display_name="Bot",
            text=resp.text,
            raw_group_id=event.get_group_id() or None,
        )

    async def handle_using_llm_tool(
        self, event: AstrMessageEvent, tool_name: str, arguments: dict
    ) -> None:
        """Monitor tool usage as a potential salience signal."""
        # For now, we just log it. Future: inject 'meta' messages into the window
        # or increase the salience of the current event window.
        logger.debug("[%s] Tool used: %s with args %s", _PLUGIN_NAME, tool_name, arguments)

    async def handle_decorating_result(
        self, event: AstrMessageEvent, result: CommandResult
    ) -> None:
        """Prepend memory-retrieval debug info and/or system prompt to the reply."""
        recall = self._init.recall
        if recall is None:
            return
        icfg = self._init.cfg.get_injection_config()
        if not icfg.show_thinking_process and not icfg.show_system_prompt:
            return

        session_id = event.unified_msg_origin
        prefix_parts: list[str] = []

        if icfg.show_thinking_process:
            debug = recall.pop_recall_debug(session_id)
            if debug:
                lines = [
                    "[Moirai 记忆检索]",
                    f"查询词：\"{debug['query']}\"",
                    f"分类策略：{debug['granularity']}",
                    f"召回数量：{debug['total']} 条",
                ]
                for ev in debug["events"]:
                    tag = "叙事" if ev["type"] == "narrative" else "情节"
                    lines.append(f"  ▸ [{tag}] {ev['topic']}")
                lines.append(f"注入位置：{debug['position']}")
                lines.append("─" * 20)
                prefix_parts.append("\n".join(lines))

        if icfg.show_system_prompt and _check_is_admin(event):
            raw_sp = self._pre_inject_sys_prompt.pop(session_id, None)
            if raw_sp:
                cleaned = _EM_BLOCK_RE.sub("", raw_sp).strip()
                if cleaned:
                    prefix_parts.append(
                        f"[System Prompt（记忆注入块已过滤）]\n{cleaned}\n{'─' * 20}"
                    )

        if not prefix_parts:
            return
        _prepend_to_result(result, "\n\n".join(prefix_parts) + "\n\n")
