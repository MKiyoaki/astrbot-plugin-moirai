"""EventHandler: AstrBot event dispatch layer.

Receives Core Event Protocol v1 values and delegates to Moirai services.
Keeps main.py free of business logic; all routing decisions live here.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
import re as _re

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
            label = ev.get("label") or "情节"
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

    relation = debug.get("relation") if isinstance(debug.get("relation"), dict) else None
    if relation and relation.get("injected"):
        lines.append("")
        lines.append(f"Social impression hints: injected {relation.get('count', 0)} item(s)")
        for item in relation.get("items", [])[:5]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "  - "
                f"{item.get('observer')} -> {item.get('subject')}: "
                f"{item.get('orientation')} "
                f"benevolence={item.get('benevolence')} "
                f"power={item.get('power')} "
                f"confidence={item.get('confidence')}"
            )
    else:
        lines.append("")
        lines.append("Social impression hints: not injected")

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

class EventHandler:
    """Apply scoped Core events to Moirai services and produce owned contributions."""

    def __init__(self, initializer) -> None:
        self._init = initializer
        self._locks = {}
        self._turns = OrderedDict()

    async def handle_core_event(self, event: dict, persona_name: str) -> list[dict]:
        message = event["payload"]["message"]
        session = message["stream_id"] or (
            f"{message['platform']}:private:{message['sender_id']}"
        )
        entry = self._locks.setdefault(session, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                return await self._handle(event, persona_name, session)
        finally:
            entry[1] -= 1
            if entry[1] == 0:
                self._locks.pop(session, None)
            now = time.monotonic()
            for key, (_, created) in tuple(self._turns.items()):
                if now - created > 900:
                    self._turns.pop(key, None)
            while len(self._turns) > 1024:
                self._turns.popitem(last=False)

    async def _handle(self, event: dict, persona: str, session: str) -> list[dict]:
        from .adapters.core_events import InjectionDraft

        payload = event["payload"]
        message = payload["message"]
        stage, correlation = event["stage"], event["correlation_id"]
        router = self._init.router
        group = message["stream_group_id"]
        state_key = json.dumps([event["source_instance"],
                               event["persona"]["scope"]["runtime_persona_id"], session])
        if stage in {"message", "after_generation"} and router is not None:
            text = message["text"] if stage == "message" else payload["response_text"]
            if not text:
                return []
            await router.prepare_persona(session, persona)
            await router.process(
                platform=message["platform"] if stage == "message" else "internal",
                physical_id=message["sender_id"] if stage == "message" else f"bot:{persona}",
                display_name=message["sender_name"] if stage == "message" else persona,
                text=text, raw_group_id=message["raw_group_id"],
                now=event["timestamp"] if stage == "message" else None,
                session_platform=message["platform"], session_id_override=session,
                stream_group_id=group, bot_persona_name=persona,
            )
            return []
        recall = self._init.recall
        if recall is None:
            return []
        if stage == "before_generation":
            if router is not None:
                await router.prepare_persona(session, persona)
            snapshot = payload["request"]
            if snapshot is None:
                return []
            query = message["text"] or snapshot["prompt"]
            if not query:
                return []
            cfg = self._init.cfg.get_injection_config()
            draft = InjectionDraft(snapshot)
            sender_uid = None
            if self._init.resolver is not None:
                sender_uid = await self._init.resolver.get_or_create_uid(
                    platform=message["platform"], physical_id=message["sender_id"],
                    display_name=message["sender_name"],
                )
            count = await recall.recall_and_inject(
                query=query, req=draft, session_id=state_key, group_id=group,
                sender_uid=sender_uid, store_debug=cfg.show_thinking_process,
                store_injection_debug=cfg.show_injection_summary,
                scope_mode="group" if group is not None else "private", bot_persona_name=persona,
            )
            if self._init.context_manager is not None:
                self._init.context_manager.update_state(session, recall_hit=count > 0)
            info = {"persona": persona, "system_prompt": snapshot["system_prompt"],
                    "recall": recall.pop_recall_debug(state_key) if cfg.show_thinking_process else None,
                    "injection": recall.pop_injection_debug(state_key) if cfg.show_injection_summary else None}
            self._turns[correlation] = (info, time.monotonic())
            return draft.contributions
        if stage == "decorate" and payload["llm_like"]:
            saved = self._turns.pop(correlation, None)
            if saved is None:
                return []
            info, _ = saved
            cfg = self._init.cfg.get_injection_config()
            parts = []
            if cfg.show_thinking_process and info["recall"]:
                debug = info["recall"]
                lines = ["[Moirai 记忆检索]", f"查询词：{debug['query']}", f"召回数量：{debug['total']} 条"]
                lines.extend(f"  ▸ [情节] {item['topic']}" for item in debug["events"])
                lines.extend([f"注入位置：{debug['position']}", "─" * 20])
                parts.append("\n".join(lines))
            if cfg.show_injection_summary:
                parts.append(_format_injection_debug_for_display(info["injection"]) if info["injection"]
                             else "[Moirai 实际注入摘要]\n注入摘要不可用。")
            if cfg.show_system_prompt:
                cleaned = _EM_BLOCK_RE.sub("", info["system_prompt"]).strip()
                display = _format_system_prompt_for_debug(cleaned, info["persona"],
                                                          _extract_system_prompt_skill_names(cleaned))
                if display:
                    parts.append(f"[System Prompt（摘要，记忆注入块已过滤）]\n{display}\n{'─' * 20}")
            return [{"kind": "reply_prefix", "text": "[系统测试消息]\n\n" + "\n\n".join(parts) + "\n\n"}] if parts else []
        return []
