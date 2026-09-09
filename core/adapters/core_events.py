"""Core Event Protocol v1 provider and Moirai-owned legacy scope mappings."""

from __future__ import annotations

import json
from typing import Callable


class InjectionDraft:
    """Collect declarative memory contributions without retaining host objects."""

    def __init__(self, snapshot: dict) -> None:
        self.system_prompt = snapshot["system_prompt"]
        self.prompt = snapshot["prompt"]
        self.model = snapshot["model"]
        self.contexts = [] if snapshot["contexts"] is not None else None
        self.synthetic_tool_fallback = snapshot.get("synthetic_tool_fallback")
        self.contributions: list[dict] = []

    def clear_namespace(self) -> None:
        self.contributions.append({"kind": "clear_namespace"})

    def add_block(self, block_id: str, target: str, position: str, text: str) -> None:
        self.contributions.append({"kind": "text_block", "block_id": block_id,
                                   "target": target, "position": position, "text": text})

    def add_tool_messages(self, messages: list[dict]) -> None:
        if len(messages) % 2:
            raise ValueError("Synthetic tool messages must be paired.")
        for index in range(0, len(messages), 2):
            self.contributions.append({"kind": "tool_pair", "assistant": messages[index],
                                       "tool": messages[index + 1]})


class MoiraiCoreProvider:
    def __init__(self, handler: Callable, scopes: Callable, version: str,
                 core_available: Callable = lambda: True) -> None:
        self._handler, self._scopes = handler, scopes
        self.version, self._core_available = version, core_available

    def _mapping(self) -> dict[str, str]:
        raw = self._scopes()
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not isinstance(raw, dict):
            raise ValueError("core_scope_mappings must be an object.")
        if any(not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
               or v in {"无", "[%None]"} for k, v in raw.items()):
            raise ValueError("Each scope must name one explicit legacy persona bucket.")
        return dict(raw)

    def manifest_v1(self) -> dict:
        return {"extension_id": "moirai", "display_name": "Moirai", "protocol_version": "1",
                "extension_version": self.version, "capabilities": [
                    {"operation": "moirai.scopes.list", "kind": "query", "required_scopes": []},
                ]}

    def events_v1(self) -> dict:
        return {"version": "1", "stages": ["message", "before_generation", "after_generation",
                                              "before_tool", "decorate"],
                "blocks": [{"id": "memory", "start": "<!-- EM:MEMORY:START -->",
                            "end": "<!-- EM:MEMORY:END -->"},
                           {"id": "soul", "start": "<!-- EM:SOUL:START -->",
                            "end": "<!-- EM:SOUL:END -->"}],
                "tool_prefix": "em_recall_", "timeout_seconds": 10.0}

    async def health_v1(self) -> dict:
        try:
            mappings = self._mapping()
        except ValueError:
            return {"state": "degraded", "message": "Core 人格映射配置无效。"}
        if not self._core_available():
            return {"state": "degraded", "message": "事件处理暂停：需要启用 Core Event Protocol v1。"}
        if self._handler() is None or not mappings:
            return {"state": "degraded", "message": "等待 Moirai 初始化及显式人格映射。"}
        return {"state": "ready", "message": "Core 事件入口已就绪。"}

    async def invoke_v1(self, request: dict, context: dict) -> dict:
        if context.get("principal", {}).get("authenticated") is not True:
            return self._error("permission_denied", "需要已认证的管理身份。")
        if request.get("operation") != "moirai.scopes.list" or request.get("kind") != "query":
            return self._error("capability_unsupported", "不支持的操作。")
        try:
            mappings = self._mapping()
        except ValueError:
            return self._error("scope_invalid", "Core 人格映射配置无效。")
        return {"request_id": context["request_id"], "extension_id": "moirai",
                "operation": "moirai.scopes.list", "resolved_scope": request["scope"],
                "data": {"items": [{"id": key, "label": value, "status": "ready"}
                                   for key, value in sorted(mappings.items())]}}

    async def on_event_v1(self, event: dict) -> dict:
        handler = self._handler()
        if not self._core_available() or handler is None:
            raise RuntimeError("Core event dependency or Moirai handler is unavailable.")
        if event.get("version") != "1" or not isinstance(event.get("persona"), dict):
            raise ValueError("A concrete Core persona context is required.")
        scope = event["persona"]["scope"]
        if not scope.get("runtime_persona_id"):
            raise ValueError("A runtime persona is required.")
        bucket = self._mapping().get(scope.get("extension_scopes", {}).get("moirai"))
        if bucket is None:
            raise ValueError("The Moirai scope has no explicit legacy bucket mapping.")
        return {"version": "1", "contributions": await handler.handle_core_event(event, bucket)}

    @staticmethod
    def _error(code: str, message: str) -> dict:
        return {"error": {"code": code, "message": message, "retryable": False, "details": {}}}
