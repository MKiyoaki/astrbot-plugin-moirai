"""Group summarised-memory generation (daily LLM task).

Writes one Markdown file per active group per day:
    data_dir/groups/<gid>/summaries/<YYYY-MM-DD>.md
    data_dir/global/summaries/<YYYY-MM-DD>.md  (for private-chat / group_id=None)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ..repository.base import EventRepository

logger = logging.getLogger(__name__)

_LLM_TIMEOUT = 45.0
_MAX_EVENTS = 20

_SUMMARY_SYSTEM = (
    "你是一个对话记录摘要助手。根据提供的事件列表，生成本期群组活动摘要。"
    "用Markdown格式输出，包含：本期主要话题（无序列表）、成员活跃度（简短说明）、"
    "值得关注的事件。总字数不超过300字。不要输出任何其他内容。"
)


async def run_group_summary(
    event_repo: EventRepository,
    data_dir: Path,
    provider_getter: Callable,
    llm_timeout: float = _LLM_TIMEOUT,
) -> int:
    """Generate and write a daily summary for every active group.

    Discovers groups automatically via event_repo.list_group_ids().
    Returns number of summary files written.
    """
    provider = provider_getter()
    if provider is None:
        logger.debug("[Summary] no provider, skipping group summary")
        return 0

    group_ids = await event_repo.list_group_ids()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    written = 0

    for group_id in group_ids:
        events = await event_repo.list_by_group(group_id, limit=_MAX_EVENTS)
        if not events:
            continue

        group_label = group_id or "私聊"
        event_list = "\n".join(
            "- [{}] {}{}".format(
                datetime.fromtimestamp(e.start_time, tz=timezone.utc).strftime("%m-%d %H:%M"),
                e.topic,
                "（{}）".format("、".join(e.chat_content_tags)) if e.chat_content_tags else "",
            )
            for e in events
        )
        prompt = (
            f"群组：{group_label}，统计日期：{today}。\n"
            f"事件列表：\n{event_list}\n"
            "请生成摘要。"
        )

        try:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=_SUMMARY_SYSTEM),
                timeout=llm_timeout,
            )
            content = (
                f"# {group_label} 活动摘要 — {today}\n\n"
                f"{resp.completion_text.strip()}\n"
            )

            if group_id is None:
                summary_dir = data_dir / "global" / "summaries"
            else:
                summary_dir = data_dir / "groups" / group_id / "summaries"

            summary_dir.mkdir(parents=True, exist_ok=True)
            (summary_dir / f"{today}.md").write_text(content, encoding="utf-8")
            written += 1
            logger.debug("[Summary] wrote summary for group %r", group_label)

        except asyncio.TimeoutError:
            logger.warning("[Summary] timeout for group %r", group_label)
        except Exception as exc:
            logger.warning("[Summary] failed for group %r: %s", group_label, exc)

    logger.info("[Summary] group summaries written: %d/%d", written, len(group_ids))
    return written
