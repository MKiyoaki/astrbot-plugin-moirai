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
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import SummaryConfig
    from ..repository.base import EventRepository

logger = logging.getLogger(__name__)
_MODULE_NAME = "Summary"


async def run_group_summary(
    event_repo: EventRepository,
    data_dir: Path,
    provider_getter: Callable,
    summary_config: SummaryConfig | None = None,
) -> int:
    """Generate and write a daily summary for every active group.

    Discovers groups automatically via event_repo.list_group_ids().
    Returns number of summary files written.
    """
    from ..config import SummaryConfig as _SC
    cfg = summary_config or _SC()

    # Dynamic word limit injection
    system_prompt = cfg.system_prompt
    if "不超过300字" in system_prompt:
        system_prompt = system_prompt.replace("不超过300字", f"不超过{cfg.word_limit}字")

    provider = provider_getter()
    if provider is None:
        logger.debug(f"[{_MODULE_NAME}] no provider, skipping group summary")
        return 0

    group_ids = await event_repo.list_group_ids()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    written = 0

    for group_id in group_ids:
        events = await event_repo.list_by_group(group_id, limit=cfg.max_events)
        if not events:
            continue

        # Calculate time range of summarized events
        start_ts = min(e.start_time for e in events)
        end_ts = max(e.end_time for e in events)
        start_time_str = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%H:%M")
        end_time_str = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%H:%M")
        time_range_str = f"{start_time_str} - {end_time_str}"

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
                provider.text_chat(prompt=prompt, system_prompt=system_prompt),
                timeout=cfg.llm_timeout,
            )
            content = (
                f"# {group_label} 活动摘要 — {today} {time_range_str}\n\n"
                f"{resp.completion_text.strip()}\n"
            )

            if group_id is None:
                summary_dir = data_dir / "global" / "summaries"
            else:
                summary_dir = data_dir / "groups" / group_id / "summaries"

            summary_dir.mkdir(parents=True, exist_ok=True)
            (summary_dir / f"{today}.md").write_text(content, encoding="utf-8")
            written += 1
            logger.debug(f"[{_MODULE_NAME}] wrote summary for group %r", group_label)

        except asyncio.TimeoutError:
            logger.warning(f"[{_MODULE_NAME}] timeout for group %r", group_label)
        except Exception as exc:
            logger.warning(f"[{_MODULE_NAME}] failed for group %r: %s", group_label, exc)

    logger.info(f"[{_MODULE_NAME}] group summaries written: %d/%d", written, len(group_ids))
    return written
