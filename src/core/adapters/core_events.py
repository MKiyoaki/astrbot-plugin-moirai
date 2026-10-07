"""Core Event and Generation Protocol v1 provider and Moirai-owned legacy scope mappings."""

from __future__ import annotations

import json
import logging
from typing import Callable

from .core_canon import BLOCK as CANON_BLOCK, NO_TURN
from ..turn_annotations import COMMITMENTS_BLOCK, NOTES_BLOCK, validate_annotation

logger = logging.getLogger(__name__)


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
                 *, recall: Callable = lambda: None, canon: Callable = lambda: None) -> None:
        self._handler, self._scopes = handler, scopes
        self.version, self._core_available = version, core_available
        self._recall, self._canon = recall, canon

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
                           dict(CANON_BLOCK),
                           dict(NOTES_BLOCK), dict(COMMITMENTS_BLOCK)],
                "tool_prefix": "em_recall_", "timeout_seconds": 10.0}

    def annotation_v1(self) -> dict:
        return {"version": "1", "produce": None, "consume": True, "timeout_seconds": 10.0}

    async def on_annotation_v1(self, call: dict) -> dict:
        if (not isinstance(call, dict) or set(call) != {"version", "kind", "event", "annotation", "producer"}
                or call.get("version") != "1" or call.get("kind") != "deliver"
                or not isinstance(call.get("producer"), str) or not call["producer"].strip()):
            raise ValueError("只支持 Annotation Protocol v1 的 deliver 调用。")
        handler = self._handler()
        if not self._core_available() or handler is None:
            raise RuntimeError("Core 事件入口或 Moirai 尚未就绪。")
        event = call["event"]
        if not isinstance(event, dict) or event.get("version") != "1" or event.get("stage") != "before_generation":
            raise ValueError("每轮便签必须对应 before_generation 事件。")
        bucket = self._bucket(event)
        if bucket is None:
            raise ValueError("每轮便签没有明确的 Moirai 人格映射。")
        handler.cache_annotation(event, bucket, validate_annotation(call["annotation"]))
        return {"version": "1", "kind": "deliver"}

    def generation_v1(self) -> dict:
        """Canon tools and reply review; without a canon service the declaration offers nothing."""
        canon = self._canon()
        if canon is None:
            return {"version": "1", "tools": [], "review": False, "timeout_seconds": 10.0}
        return canon.declaration()

    async def on_generation_v1(self, call: dict) -> dict:
        canon = self._canon()
        kind = call.get("kind") if isinstance(call, dict) else None
        if canon is not None and self._core_available():
            return await canon.on_generation(call, self._bucket(call.get("event") or {}))
        if kind == "offer":
            return {"version": "1", "kind": "offer", "tools": [], "review": False}
        if kind == "tool":
            return {"version": "1", "kind": "tool", "text": NO_TURN}
        return {"version": "1", "kind": "review", "action": "keep"}

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
        bucket = self._bucket(event)
        if bucket is None:
            raise ValueError("The Moirai scope has no explicit legacy bucket mapping.")
        contributions = await handler.handle_core_event(event, bucket)
        canon = self._canon()
        if canon is not None and event.get("stage") == "before_generation":
            try:
                contributions = [*contributions, *await canon.before_generation(event, bucket)]
            except Exception:
                logger.warning("[Moirai] canon turn could not start; this reply goes without canon",
                               exc_info=True)
        return {"version": "1", "contributions": contributions}

    def _bucket(self, event: dict) -> str | None:
        persona = event.get("persona")
        scope = persona.get("scope") if isinstance(persona, dict) else None
        if not isinstance(scope, dict) or not scope.get("runtime_persona_id"):
            raise ValueError("A runtime persona is required.")
        return self._mapping().get((scope.get("extension_scopes") or {}).get("moirai"))

    @staticmethod
    def _error(code: str, message: str) -> dict:
        return {"error": {"code": code, "message": message, "retryable": False, "details": {}}}
