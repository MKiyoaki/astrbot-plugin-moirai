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
                 core_available: Callable = lambda: True,
                 *, recall: Callable = lambda: None) -> None:
        self._handler, self._scopes = handler, scopes
        self.version, self._core_available = version, core_available
        self._recall = recall

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
                    {"operation": "moirai.chat_memory.recall", "kind": "query",
                     "required_scopes": ["runtime_persona", "extension"]},
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
        principal = context.get("principal", {})
        if principal.get("authenticated") is not True:
            return self._error("permission_denied", "需要已认证的身份。")
        operation = request.get("operation")
        if request.get("kind") != "query":
            return self._error("capability_unsupported", "不支持的操作。")
        if operation == "moirai.chat_memory.recall":
            return await self._recall_context(request, context)
        if operation != "moirai.scopes.list":
            return self._error("capability_unsupported", "不支持的操作。")
        try:
            mappings = self._mapping()
        except ValueError:
            return self._error("scope_invalid", "Core 人格映射配置无效。")
        return {"request_id": context["request_id"], "extension_id": "moirai",
                "operation": "moirai.scopes.list", "resolved_scope": request["scope"],
                "data": {"items": [{"id": key, "label": value, "status": "ready"}
                                   for key, value in sorted(mappings.items())]}}

    async def _recall_context(self, request: dict, context: dict) -> dict:
        permissions = context["principal"].get("permissions", [])
        if not isinstance(permissions, (list, tuple, set, frozenset)) or "moirai.chat_memory.read" not in permissions:
            return self._error("permission_denied", "缺少记忆上下文读取权限。")
        if not self._core_available():
            return self._error("extension_unavailable", "Core 事件入口不可用。")
        manager = self._recall()
        if manager is None:
            return self._error("extension_unavailable", "记忆召回尚未就绪。")
        scope = request.get("scope")
        if not isinstance(scope, dict) or not scope.get("runtime_persona_id"):
            return self._error("scope_invalid", "需要明确的运行人格。")
        extension_scopes = scope.get("extension_scopes")
        if not isinstance(extension_scopes, dict):
            return self._error("scope_invalid", "需要 Moirai 人格作用域。")
        try:
            bucket = self._mapping().get(extension_scopes.get("moirai"))
        except (TypeError, ValueError):
            return self._error("scope_invalid", "Core 人格映射配置无效。")
        if bucket is None:
            return self._error("scope_invalid", "Moirai 人格作用域没有显式映射。")
        payload = request.get("payload")
        if not isinstance(payload, dict) or set(payload) != {"query", "scope_mode", "group_id"}:
            return self._error("payload_invalid", "记忆查询字段无效。")
        query, mode, group = payload["query"], payload["scope_mode"], payload["group_id"]
        if not isinstance(query, str) or not query.strip():
            return self._error("payload_invalid", "记忆查询文本不能为空。")
        if not isinstance(mode, str) or mode not in {"private", "group"} or (mode == "private" and group is not None) or (mode == "group" and (not isinstance(group, str) or not group.strip())):
            return self._error("payload_invalid", "会话作用域无效。")
        try:
            events = await manager.recall_context(
                query.strip(), group_id=group, scope_mode=mode, bot_persona_name=bucket,
            )
        except Exception:
            return self._error("extension_failure", "记忆召回失败。")
        return {"request_id": context["request_id"], "extension_id": "moirai",
                "operation": "moirai.chat_memory.recall", "resolved_scope": scope,
                "data": {"schema_version": "conversation-context.v1",
                         "source_kind": "conversation", "events": events}}

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
