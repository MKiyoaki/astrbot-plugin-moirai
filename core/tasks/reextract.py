"""Single-event LLM re-extraction without fallback overwrite."""
from __future__ import annotations

import asyncio
import dataclasses
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..boundary.window import MessageWindow
from ..config import ExtractorConfig
from ..extractor.parser import parse_llm_output
from ..extractor.persona_context import resolve_bot_persona_context
from ..extractor.prompts import build_user_prompt

if TYPE_CHECKING:
    from ..embedding.encoder import Encoder
    from ..repository.base import EventRepository, PersonaRepository, RawMessageRepository
    from ..managers.llm_manager import LLMTaskManager
    from ..domain.models import Event


_NON_TEXT_PREVIEWS = {
    "[图片]", "[表情]", "[语音]", "[视频]", "[卡片]",
    "[image]", "[emoji]", "[voice]", "[video]", "[card]",
}
_NON_TEXT_PREVIEWS_LOWER = {item.lower() for item in _NON_TEXT_PREVIEWS}


@dataclass
class ReextractResult:
    event: Event
    source_count: int


class ReextractError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _response_text(resp: object) -> str:
    for attr in ("completion_text", "text"):
        value = getattr(resp, attr, None)
        if value is None or callable(value):
            continue
        text = value if isinstance(value, str) else str(value)
        if text:
            return text
    return ""


def _is_meaningful_source(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    if value.lower() in _NON_TEXT_PREVIEWS_LOWER:
        return False
    return True


async def _display_name(persona_repo: PersonaRepository | None, uid: str) -> str:
    if persona_repo is None:
        return uid
    try:
        persona = await persona_repo.get(uid)
        if persona and persona.primary_name:
            return persona.primary_name
    except Exception:
        pass
    return uid


async def _build_window_from_event(
    event: Event,
    persona_repo: PersonaRepository | None,
    raw_message_repo: RawMessageRepository | None = None,
) -> MessageWindow:
    if raw_message_repo is not None:
        try:
            raw_messages = [
                message for message in await raw_message_repo.list_by_event(event.event_id)
                if _is_meaningful_source(message.text or "")
            ]
        except Exception:
            raw_messages = []
        if raw_messages:
            window = MessageWindow(
                session_id=f"reextract:{event.event_id}",
                group_id=event.group_id,
                start_time=min(message.created_at for message in raw_messages),
                last_message_time=max(message.created_at for message in raw_messages),
            )
            for message in raw_messages:
                window.add_message(
                    uid=message.sender_uid,
                    text=(message.text or "").strip(),
                    timestamp=message.created_at,
                    display_name=message.display_name or await _display_name(
                        persona_repo, message.sender_uid
                    ),
                    bot_persona_name=message.bot_persona_name,
                    message_id=message.message_id,
                    platform=message.platform,
                    physical_id=message.physical_id,
                    role=message.role,
                    content_hash=message.content_hash,
                )
            return window

    refs = event.interaction_flow or []
    source_refs = [
        ref for ref in refs
        if _is_meaningful_source(ref.content_preview or "")
    ]
    if not source_refs:
        raise ReextractError(
            "missing_source_messages",
            "重新提取失败：缺少原始消息数据，无法安全重新生成。",
        )

    window = MessageWindow(
        session_id=f"reextract:{event.event_id}",
        group_id=event.group_id,
        start_time=min(ref.timestamp for ref in source_refs),
        last_message_time=max(ref.timestamp for ref in source_refs),
    )
    for ref in source_refs:
        window.add_message(
            uid=ref.sender_uid,
            text=(ref.content_preview or "").strip(),
            timestamp=ref.timestamp,
            display_name=await _display_name(persona_repo, ref.sender_uid),
        )
    return window


async def reextract_event(
    event_repo: EventRepository,
    persona_repo: PersonaRepository | None,
    event_id: str,
    provider_getter,
    extractor_config: ExtractorConfig | None = None,
    llm_manager: LLMTaskManager | None = None,
    encoder: Encoder | None = None,
    raw_message_repo: RawMessageRepository | None = None,
) -> ReextractResult:
    """Re-run LLM extraction for one existing event.

    This function intentionally does not use EventExtractor._extract_batch(),
    because that method falls back to rule extraction.  A manual re-extract must
    either produce valid LLM JSON or leave the existing event untouched.
    """
    event = await event_repo.get(event_id)
    if event is None:
        raise ReextractError("not_found", "事件不存在。")
    if event.is_locked:
        raise ReextractError("locked", "重新提取失败：事件已锁定。")

    cfg = extractor_config or ExtractorConfig()
    window = await _build_window_from_event(event, persona_repo, raw_message_repo)
    bot_name, bot_desc = await resolve_bot_persona_context(
        persona_repo,
        cfg.persona_influenced_summary,
    )

    provider = provider_getter() if callable(provider_getter) else None
    if provider is None:
        raise ReextractError("provider_none", "重新提取失败：没有可用 LLM provider。")

    prompt = build_user_prompt(
        window,
        cfg.max_context_messages,
        bot_persona_desc=bot_desc,
    )

    try:
        if llm_manager:
            resp = await llm_manager.run(
                asyncio.wait_for,
                provider.text_chat(prompt=prompt, system_prompt=cfg.system_prompt),
                timeout=cfg.llm_timeout,
                task_name="extraction",
            )
        else:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=cfg.system_prompt),
                timeout=cfg.llm_timeout,
            )
    except asyncio.TimeoutError as exc:
        raise ReextractError("timeout", "重新提取失败：LLM 调用超时。") from exc
    except Exception as exc:
        raise ReextractError("exception", f"重新提取失败：{exc}") from exc

    parsed = parse_llm_output(_response_text(resp), window.message_count - 1)
    if not parsed:
        raise ReextractError("parse_error", "重新提取失败：LLM 输出无法解析。")

    primary = parsed[0]
    updated = dataclasses.replace(
        event,
        topic=primary["topic"],
        summary=primary.get("summary", ""),
        chat_content_tags=primary.get("chat_content_tags", []),
        salience=primary["salience"],
        confidence=primary["confidence"],
        bot_persona_name=bot_name if cfg.persona_influenced_summary and bot_name else event.bot_persona_name,
        last_accessed_at=time.time(),
    )
    await event_repo.upsert(updated)

    if encoder is not None and getattr(encoder, "dim", 0) > 0:
        text = " ".join(
            part for part in [
                updated.topic,
                updated.summary,
                " ".join(updated.chat_content_tags or []),
            ]
            if part
        )
        if text.strip():
            embedding = await encoder.encode(text)
            await event_repo.upsert_vector(updated.event_id, embedding)

    return ReextractResult(event=updated, source_count=window.message_count)
