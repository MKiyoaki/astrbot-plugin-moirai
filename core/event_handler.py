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
_PERSONA_INSTRUCTIONS_HEADING_RE = _re.compile(r"^#\s+Persona Instructions?\s*$", _re.IGNORECASE)
_SKILLS_HEADING_RE = _re.compile(r"^##\s+Skills\s*$", _re.IGNORECASE)
_AVAILABLE_SKILLS_HEADING_RE = _re.compile(r"^###\s+Available skills\s*$", _re.IGNORECASE)
_ANY_HEADING_RE = _re.compile(r"^#{1,6}\s+")
_TOP_LEVEL_HEADING_RE = _re.compile(r"^#{1,2}\s+")
_SKILL_LINE_RE = _re.compile(r"^\s*-\s*([A-Za-z0-9._-]+)(?=\s*:|\s|$)")


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
    segment = Plain(text)
    chain = getattr(result, "chain", None)
    if isinstance(chain, list):
        chain.insert(0, segment)
        return

    insert = getattr(result, "insert", None)
    if callable(insert):
        insert(0, segment)
        return

    logger.warning("[%s] cannot prepend debug prefix to result type %s", _PLUGIN_NAME, type(result))


def _response_text(resp: object) -> str:
    """Return response text across AstrBot/provider response versions."""
    for attr in ("completion_text", "text"):
        value = getattr(resp, attr, None)
        if value is None or callable(value):
            continue
        if isinstance(value, str):
            if value:
                return value
            continue
        text = str(value)
        if text:
            return text
    return ""


def _normalize_persona_name(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text == "[%None]":
        return "无"
    return text


def _extract_skill_names(lines: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in lines:
        match = _SKILL_LINE_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        if name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def _extract_system_prompt_skill_names(system_prompt: str) -> list[str]:
    """Extract active skill names from AstrBot's build_skills_prompt() block."""
    lines = system_prompt.splitlines()
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        if _SKILLS_HEADING_RE.match(stripped):
            block = [lines[i]]
            i += 1
            while i < len(lines) and not _TOP_LEVEL_HEADING_RE.match(lines[i].strip()):
                block.append(lines[i])
                i += 1
            available_lines: list[str] = []
            in_available = False
            for block_line in block:
                block_stripped = block_line.strip()
                if _AVAILABLE_SKILLS_HEADING_RE.match(block_stripped):
                    in_available = True
                    continue
                if in_available and _ANY_HEADING_RE.match(block_stripped):
                    break
                if in_available:
                    available_lines.append(block_line)
            if available_lines:
                return _extract_skill_names(available_lines)

            fallback_lines: list[str] = []
            for block_line in block[1:]:
                block_stripped = block_line.strip()
                if block_stripped.lower().startswith("### skill rules"):
                    break
                fallback_lines.append(block_line)
            return _extract_skill_names(fallback_lines)

        i += 1

    return []


def _format_system_prompt_for_debug(
    system_prompt: str,
    persona_name: str | None = None,
    skill_names: list[str] | None = None,
) -> str:
    """Compact AstrBot system prompt — whitelist summary only.

    The original prompt body is intentionally ignored. We only show the active
    persona name and active skill names so large Persona/Skill rules never leak
    into the user-facing debug message.
    """
    has_persona_block = any(
        _PERSONA_INSTRUCTIONS_HEADING_RE.match(line.strip())
        for line in system_prompt.splitlines()
    )
    resolved_persona = persona_name or ("未知" if has_persona_block else "无")
    resolved_skill_names = (
        list(skill_names)
        if skill_names is not None
        else _extract_system_prompt_skill_names(system_prompt)
    )

    return "\n".join(
        [
            f"Persona Instruction：{resolved_persona}",
            "已启用 Skill：" + (", ".join(resolved_skill_names) if resolved_skill_names else "无"),
        ]
    )


def _result_content_type_name(result: object) -> str:
    content_type = getattr(result, "result_content_type", None)
    name = getattr(content_type, "name", None)
    if name:
        return str(name)
    return str(content_type or "")


def _is_llm_like_result(result: object) -> bool:
    is_llm_result = getattr(result, "is_llm_result", None)
    if callable(is_llm_result):
        try:
            if is_llm_result():
                return True
        except Exception:
            pass

    # AstrBot v4.24.x reports stream completion as STREAMING_FINISH. It is still
    # an LLM response and needs the same debug decoration path.
    return _result_content_type_name(result) in {"LLM_RESULT", "STREAMING_FINISH"}


def _format_injection_debug_for_display(debug: dict) -> str:
    """Render sanitized Moirai injection debug data without exposing internal prompts."""
    lines = [
        "[Moirai 实际注入摘要]",
    ]

    error = debug.get("_error")
    if error:
        lines.append(f"注入错误：{error}")

    memory = debug.get("memory") if isinstance(debug.get("memory"), dict) else {}
    if memory.get("injected"):
        lines.append(f"记忆注入：{memory.get('count', 0)} 条")
        for ev in memory.get("events", [])[:8]:
            label = ev.get("label") or ("叙事" if ev.get("type") == "narrative" else "情节")
            topic = ev.get("topic") or "未命名记忆"
            summary = ev.get("summary") or ""
            if summary:
                lines.append(f"  ▸ [{label}] {topic}：{summary}")
            else:
                lines.append(f"  ▸ [{label}] {topic}")
    else:
        lines.append("记忆注入：无")

    lines.append("")

    persona = debug.get("persona") if isinstance(debug.get("persona"), dict) else None
    if persona:
        dims = []
        for dim in persona.get("dimensions", []):
            label = dim.get("label")
            percent = dim.get("percent")
            if label is None or percent is None:
                continue
            dims.append(f"{label} {percent}%")
        lines.append("用户画像参考：已注入")
        if dims:
            lines.append("  ▸ " + "，".join(dims))
        lines.append("  ▸ 已隐藏证据句与完整画像 prompt")
    else:
        lines.append("用户画像参考：未注入")

    soul = debug.get("soul") if isinstance(debug.get("soul"), dict) else None
    if soul:
        ordered = [
            f"recall_depth={soul.get('recall_depth')}",
            f"impression_depth={soul.get('impression_depth')}",
            f"expression_desire={soul.get('expression_desire')}",
            f"creativity={soul.get('creativity')}",
        ]
        lines.append("")
        lines.append("Soul Layer：已注入")
        lines.append("  ▸ " + ", ".join(ordered))

    lines.append("")
    hidden = debug.get("hidden")
    if isinstance(hidden, list) and hidden:
        lines.append("已隐藏：" + "、".join(str(item) for item in hidden))
    else:
        lines.append("已隐藏：完整 System Prompt、后台任务 prompt、完整 Persona 内容、Skill Rules、Big Five evidence 原文")
    lines.append("─" * 20)
    return "\n".join(lines)

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
        self._pre_inject_persona_name: dict[str, str | None] = {}
        self._pre_inject_skill_names: dict[str, list[str]] = {}

    async def _resolve_persona_name(self, event: AstrMessageEvent, req: ProviderRequest) -> str | None:
        try:
            from astrbot.core import sp

            session_cfg = await sp.get_async(
                scope="umo",
                scope_id=event.unified_msg_origin,
                key="session_service_config",
                default={},
            )
            name = _normalize_persona_name(session_cfg.get("persona_id"))
            if name:
                return name
        except Exception:
            pass

        conversation = getattr(req, "conversation", None)
        name = _normalize_persona_name(getattr(conversation, "persona_id", None))
        if name:
            return name

        try:
            context = getattr(self._init, "_context", None)
            get_config = getattr(context, "get_config", None)
            if callable(get_config):
                try:
                    cfg = get_config(umo=event.unified_msg_origin)
                except TypeError:
                    cfg = get_config()
                if isinstance(cfg, dict):
                    provider_settings = cfg.get("provider_settings", cfg)
                    if isinstance(provider_settings, dict):
                        return _normalize_persona_name(provider_settings.get("default_personality"))
        except Exception:
            pass

        return None

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

            icfg = None
            session_id = event.unified_msg_origin
            try:
                group_id = event.get_group_id() or None

                icfg = self._init.cfg.get_injection_config()
                astrbot_logger.debug(
                    "[%s] debug config on request: show_thinking_process=%s, show_system_prompt=%s, show_injection_summary=%s",
                    _PLUGIN_NAME,
                    icfg.show_thinking_process,
                    icfg.show_system_prompt,
                    icfg.show_injection_summary,
                )

                # Capture system_prompt before injection for show_system_prompt feature.
                if icfg.show_system_prompt:
                    raw_system_prompt = getattr(req, "system_prompt", "") or ""
                    self._pre_inject_sys_prompt[session_id] = (
                        raw_system_prompt
                    )
                    self._pre_inject_persona_name[session_id] = await self._resolve_persona_name(
                        event, req
                    )
                    self._pre_inject_skill_names[session_id] = _extract_system_prompt_skill_names(
                        raw_system_prompt
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

                if icfg.show_injection_summary:
                    try:
                        recall._last_injection_debug[session_id] = {
                            "injected": False,
                            "position": "unknown",
                            "memory": {"injected": False, "count": 0, "events": []},
                            "persona": None,
                            "soul": None,
                            "hidden": [],
                            "_error": "recall_and_inject 未生成注入摘要",
                        }
                    except Exception:
                        pass

                injected_count = await recall.recall_and_inject(
                    query=query,
                    req=req,
                    session_id=session_id,
                    group_id=group_id,
                    sender_uid=sender_uid,
                    store_debug=icfg.show_thinking_process,
                    store_injection_debug=icfg.show_injection_summary,
                )
                
                # Sync VCM state with hit rate feedback
                cm = self._init.context_manager
                if cm is not None:
                    cm.update_state(session_id, recall_hit=(injected_count > 0))
                    
            except Exception as exc:
                astrbot_logger.warning("[%s] recall hook failed: %s", _PLUGIN_NAME, exc)
                if icfg is not None and icfg.show_injection_summary:
                    try:
                        recall._last_injection_debug[session_id] = {
                            "injected": False, "position": "unknown",
                            "memory": {"injected": False, "count": 0, "events": []},
                            "persona": None, "soul": None,
                            "hidden": [], "_error": str(exc),
                        }
                    except Exception:
                        pass

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
        text = _response_text(resp)
        if router is None or not text:
            return

        # Use a special internal UID for the bot to distinguish it from users.
        # router.process will handle get_or_create_uid.
        await router.process(
            platform="internal",
            physical_id="bot",
            display_name="Bot",
            text=text,
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
        # Only decorate actual LLM responses; tool call results (GENERAL_RESULT) must
        # not receive the prefix — they would corrupt conversation history and cause
        # the LLM to loop on core_memory_recall calls.
        result_content_type = getattr(result, "result_content_type", None)
        if not _is_llm_like_result(result):
            astrbot_logger.debug(
                "[%s] skip debug decoration: result_content_type=%s",
                _PLUGIN_NAME,
                result_content_type,
            )
            return

        recall = self._init.recall
        if recall is None:
            return
        icfg = self._init.cfg.get_injection_config()
        astrbot_logger.debug(
            "[%s] debug config on decoration: show_thinking_process=%s, show_system_prompt=%s, show_injection_summary=%s, result_content_type=%s",
            _PLUGIN_NAME,
            icfg.show_thinking_process,
            icfg.show_system_prompt,
            icfg.show_injection_summary,
            result_content_type,
        )
        if (
            not icfg.show_thinking_process
            and not icfg.show_system_prompt
            and not icfg.show_injection_summary
        ):
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

        if icfg.show_injection_summary:
            pop_injection_debug = getattr(recall, "pop_injection_debug", None)
            debug = pop_injection_debug(session_id) if callable(pop_injection_debug) else None
            if debug:
                prefix_parts.append(_format_injection_debug_for_display(debug))
            else:
                astrbot_logger.warning(
                    "[%s] show_injection_summary=True but no debug for session %s",
                    _PLUGIN_NAME, session_id,
                )
                prefix_parts.append(
                    "[Moirai 实际注入摘要]\n注入摘要不可用（recall_and_inject 未完成或发生异常）\n" + "─" * 20
                )

        if icfg.show_system_prompt:
            raw_sp = self._pre_inject_sys_prompt.pop(session_id, None)
            persona_name = self._pre_inject_persona_name.pop(session_id, None)
            skill_names = self._pre_inject_skill_names.pop(session_id, None)
            cleaned = _EM_BLOCK_RE.sub("", raw_sp or "").strip()
            display = _format_system_prompt_for_debug(cleaned, persona_name, skill_names)
            if display:
                prefix_parts.append(
                    f"[System Prompt（摘要，记忆注入块已过滤）]\n{display}\n{'─' * 20}"
                )

        if not prefix_parts:
            astrbot_logger.debug("[%s] no debug prefix parts produced", _PLUGIN_NAME)
            return
        _prepend_to_result(result, "[系统测试消息]\n\n" + "\n\n".join(prefix_parts) + "\n\n")
        astrbot_logger.debug(
            "[%s] prepended debug prefix: parts=%d, chain_len=%s",
            _PLUGIN_NAME,
            len(prefix_parts),
            len(getattr(result, "chain", [])),
        )
