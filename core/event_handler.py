"""EventHandler: AstrBot event dispatch layer.

Receives AstrBot events and delegates to the appropriate subsystem.
Keeps main.py free of business logic; all routing decisions live here.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from astrbot.api import logger as astrbot_logger

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.provider import ProviderRequest
    from .plugin_initializer import PluginInitializer

_PLUGIN_NAME = "EnhancedMemory"
logger = logging.getLogger(__name__)


class EventHandler:
    """Delegates AstrBot event callbacks to subsystems via PluginInitializer."""

    def __init__(self, initializer: PluginInitializer) -> None:
        self._init = initializer

    async def handle_llm_request(
        self, event: AstrMessageEvent, req: ProviderRequest
    ) -> None:
        """Inject relevant memory context into the request before LLM generation."""
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
            await recall.recall_and_inject(
                query=query,
                req=req,
                session_id=session_id,
                group_id=group_id,
            )
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
