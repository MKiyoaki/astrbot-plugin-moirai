"""Group summarised-memory generation (daily LLM task).

Writes one Markdown file per active group per day:
    data_dir/groups/<gid>/summaries/<YYYY-MM-DD>.md
    data_dir/global/summaries/<YYYY-MM-DD>.md  (for private-chat / group_id=None)

Output format — three sections:
    [主要话题]   LLM-generated free-form summary (≤word_limit chars)
    [事件列表]   Deterministic event chain built from Event dataclass fields
    [情感动态]   Group mood descriptor (LLM inference by default; see SummaryConfig.mood_source)
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import SummaryConfig
    from ..domain.models import Event
    from ..repository.base import EventRepository, PersonaRepository, ImpressionRepository

from ..utils.i18n import get_string, LANG_ZH

logger = logging.getLogger(__name__)
_MODULE_NAME = "Summary"


def _build_event_list_section(
    events: list[Event],
    uid_to_name: dict[str, str],
    lang: str = LANG_ZH,
) -> str:
    """Deterministically build the [事件列表] chain from Event fields."""
    if not events:
        return get_string("summary.no_events", lang)

    parts: list[str] = []
    for i, ev in enumerate(events):
        entry = f"[{ev.topic or get_string('summary.untitled_topic', lang)}] - [{ev.event_id[:8]}]"
        parts.append(entry)
        if i < len(events) - 1:
            last_msg = ev.interaction_flow[-1] if ev.interaction_flow else None
            if last_msg:
                sender = uid_to_name.get(last_msg.sender_uid, last_msg.sender_uid)
                raw = last_msg.content_preview or ""
                preview = raw[:20]
                ellipsis = "…" if len(raw) > 20 else ""
                shift_tpl = get_string("summary.topic_shift", lang)
                parts.append(shift_tpl.format(sender=sender, preview=f"{preview}{ellipsis}"))
    return " | ".join(parts)


async def _build_mood_section_db(
    events: list[Event],
    uid_to_name: dict[str, str],
    impression_repo: ImpressionRepository,
    persona_repo: PersonaRepository | None = None,
    lang: str = LANG_ZH,
) -> str | None:
    """Option A: Aggregate group mood from Impression DB. 
    Returns None if data density is too low for fallback.
    """
    # Try to find the actual Bot UID from personas (identity='internal')
    bot_uid = "bot" 
    if persona_repo:
        try:
            personas = await persona_repo.list_all()
            for p in personas:
                if any(bi[0] == "internal" for bi in (p.bound_identities or [])):
                    bot_uid = p.uid
                    break
        except Exception:
            pass

    participants: set[str] = set()
    for ev in events:
        for uid in (ev.participants or []):
            if uid != bot_uid:
                participants.add(uid)
    
    if not participants:
        return None

    valid_impressions = []
    for uid in participants:
        # Currently, the Bot is the observer for social analysis
        imp = await impression_repo.get(bot_uid, uid, scope="global")
        if imp and imp.confidence >= 0.3:
            valid_impressions.append((uid, imp))

    # Threshold for Option A: at least 2 members with data, or 100% of single-user chats
    if len(valid_impressions) < 2 and len(participants) > 1:
        return None
    if not valid_impressions:
        return None

    # Calculate centroid
    avg_b = sum(i[1].benevolence for i in valid_impressions) / len(valid_impressions)
    avg_p = sum(i[1].power for i in valid_impressions) / len(valid_impressions)

    from ..social import ipc_model
    orientation = ipc_model.classify_octant(avg_b, avg_p)
    # Localize orientation label
    orientation_label = get_string(f"ipc.{orientation.lower() if hasattr(orientation, 'lower') else orientation}", lang)
    
    # Group names by their orientation
    orientation_map: dict[str, list[str]] = {}
    for uid, imp in valid_impressions:
        name = uid_to_name.get(uid, uid)
        orientation_map.setdefault(imp.ipc_orientation, []).append(name)
    
    position_clauses = []
    known_tpl = get_string("summary.position_known", lang)
    for label, names in sorted(orientation_map.items()):
        # Localize label if possible
        localized_label = get_string(f"ipc.{label.lower()}", lang)
        position_clauses.append(known_tpl.format(names=", ".join(names), label=localized_label))
    
    # Participants with unknown position
    covered_uids = {i[0] for i in valid_impressions}
    unknown_names = sorted([uid_to_name.get(u, u) for u in participants if u not in covered_uids])
    if unknown_names:
        unknown_tpl = get_string("summary.position_unknown", lang)
        position_clauses.append(unknown_tpl.format(names=", ".join(unknown_names)))

    b_str = f"{avg_b:+.2f}"
    p_str = f"{avg_p:+.2f}"
    
    overall_tpl = get_string("summary.mood_overall", lang)
    return (
        overall_tpl.format(orientation=orientation_label, b=b_str, p=p_str) +
        f"{' | '.join(position_clauses)}"
    )


async def _build_mood_section_llm(
    events: list[Event],
    uid_to_name: dict[str, str],
    provider,
    cfg: SummaryConfig,
) -> str:
    """Call LLM to infer group mood (Option B). Returns formatted [情感动态] string."""
    lang = cfg.language or LANG_ZH
    participants: set[str] = set()
    for ev in events:
        for uid in (ev.participants or []):
            participants.add(uid)

    event_lines = "\n".join(
        "- [{}] {}{}，标签：{}，参与者：{}".format(
            datetime.fromtimestamp(e.start_time, tz=timezone.utc).strftime("%m-%d %H:%M"),
            get_string("summary.section_topic", lang).strip("[]") + "：",
            e.topic or get_string("summary.untitled_topic", lang),
            "、".join(e.chat_content_tags) if e.chat_content_tags else "无",
            "、".join(uid_to_name.get(u, u) for u in (e.participants or [])),
        )
        for e in events
    )
    prompt = f"对话事件列表：\n{event_lines}\n\n参与者UID列表：{', '.join(participants)}\n请输出群体情感动态JSON。"

    try:
        resp = await asyncio.wait_for(
            provider.text_chat(prompt=prompt, system_prompt=cfg.mood_prompt),
            timeout=cfg.llm_timeout,
        )
        raw = resp.completion_text.strip()
        # Strip markdown code block if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        orientation = data.get("orientation", "亲和")
        # Localize orientation if it matches an IPC label key
        orientation_label = get_string(f"ipc.{orientation.lower()}", lang)
        
        benevolence = float(data.get("benevolence", 0.0))
        power = float(data.get("power", 0.0))
        positions: dict = data.get("positions", {})

        # Group members by their orientation
        orientation_groups: dict[str, list[str]] = {}
        for uid, pos in positions.items():
            name = uid_to_name.get(uid, uid)
            if isinstance(pos, dict):
                pos = pos.get("orientation", pos.get("position", "未知位置"))
            
            localized_pos = get_string(f"ipc.{str(pos).lower()}", lang)
            orientation_groups.setdefault(localized_pos, []).append(name)

        # Build the position clause list; any participants missing get "未知位置"
        all_named = {uid_to_name.get(u, u) for u in participants}
        covered = {n for names in orientation_groups.values() for n in names}
        unknown = all_named - covered
        if unknown:
            unknown_label = get_string("ipc.unknown", lang)
            orientation_groups.setdefault(unknown_label, []).extend(sorted(unknown))

        known_tpl = get_string("summary.position_known", lang)
        position_clauses = " | ".join(
            known_tpl.format(names=", ".join(names), label=pos)
            for pos, names in orientation_groups.items()
        )
        b_str = f"{benevolence:+.2f}"
        p_str = f"{power:+.2f}"
        
        overall_tpl = get_string("summary.mood_overall", lang)
        return (
            overall_tpl.format(orientation=orientation_label, b=b_str, p=p_str) +
            position_clauses
        )
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:
        logger.warning(f"[{_MODULE_NAME}] mood LLM failed: %s", exc)
        return get_string("summary.mood_failed", lang)


async def _generate_summary_for_group(
    group_id: str | None,
    events: list[Event],
    today: str,
    provider,
    cfg: SummaryConfig,
    uid_to_name: dict[str, str],
    impression_repo: ImpressionRepository | None = None,
    persona_repo: PersonaRepository | None = None,
) -> str:
    """Generate the full three-section markdown content for one group."""
    lang = cfg.language or LANG_ZH
    group_label = group_id or get_string("summary.private_chat", lang)
    start_ts = min(e.start_time for e in events)
    end_ts = max(e.end_time for e in events)
    start_str = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%H:%M")
    end_str = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%H:%M")

    # Parallelize Section 1 (Topic) and Section 3 (Mood LLM) if needed
    topic_task = None
    mood_task = None

    # Section 1: [主要话题] — LLM
    event_lines = "\n".join(
        "- [{}] {}{}".format(
            datetime.fromtimestamp(e.start_time, tz=timezone.utc).strftime("%m-%d %H:%M"),
            e.topic or get_string("summary.untitled_topic", lang),
            "（{}）".format("、".join(e.chat_content_tags)) if e.chat_content_tags else "",
        )
        for e in events
    )
    topic_prompt = (
        f"群组：{group_label}，统计日期：{today}。\n"
        f"事件列表：\n{event_lines}\n"
        f"{get_string('summary.word_limit_hint', lang)}"
    )

    async def _get_topic():
        try:
            resp = await asyncio.wait_for(
                provider.text_chat(prompt=topic_prompt, system_prompt=cfg.system_prompt),
                timeout=cfg.llm_timeout,
            )
            return resp.completion_text.strip()
        except asyncio.TimeoutError:
            logger.warning(f"[{_MODULE_NAME}] topic LLM timeout for group %r", group_label)
            return get_string("summary.timeout", lang)
        except Exception as exc:
            logger.warning(f"[{_MODULE_NAME}] topic LLM failed for group %r: %s", group_label, exc)
            return get_string("summary.failed", lang)

    topic_task = asyncio.create_task(_get_topic())

    # Section 3: [情感动态] — LLM (Option B) or impression DB (Option A)
    mood_text = None
    if cfg.mood_source == "impression_db" and impression_repo:
        mood_text = await _build_mood_section_db(events, uid_to_name, impression_repo, persona_repo, lang=lang)
    
    if not mood_text:
        # Fallback to Option B (LLM) - parallelize it
        mood_task = asyncio.create_task(_build_mood_section_llm(events, uid_to_name, provider, cfg))

    # Wait for both
    if mood_task:
        topic_text, mood_text = await asyncio.gather(topic_task, mood_task)
    else:
        topic_text = await topic_task

    # Section 2: [事件列表] — Deterministic
    event_list_text = _build_event_list_section(events, uid_to_name, lang=lang)

    header = get_string("summary.header", lang).format(
        label=group_label, date=today, start=start_str, end=end_str
    )
    return (
        f"{header}\n\n"
        f"{get_string('summary.section_topic', lang)}\n{topic_text}\n\n"
        f"{get_string('summary.section_events', lang)}\n{event_list_text}\n\n"
        f"{get_string('summary.section_mood', lang)}\n{mood_text}\n"
    )


async def run_group_summary(
    event_repo: EventRepository,
    data_dir: Path,
    provider_getter: Callable,
    summary_config: SummaryConfig | None = None,
    persona_repo: PersonaRepository | None = None,
    impression_repo: ImpressionRepository | None = None,
) -> int:
    """Generate and write a daily summary for every active group.

    Discovers groups automatically via event_repo.list_group_ids().
    Returns number of summary files written.
    """
    from ..config import SummaryConfig as _SC
    cfg = summary_config or _SC()

    provider = provider_getter()
    if provider is None:
        logger.debug(f"[{_MODULE_NAME}] no provider, skipping group summary")
        return 0

    # Build uid→name lookup if persona_repo is available
    uid_to_name: dict[str, str] = {}
    if persona_repo is not None:
        try:
            personas = await persona_repo.list_all()
            uid_to_name = {p.uid: p.primary_name for p in personas}
        except Exception:
            pass

    group_ids = await event_repo.list_group_ids()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    
    # Use a semaphore to limit concurrent LLM calls (summaries are heavy)
    sem = asyncio.Semaphore(2)

    async def _process_one(group_id) -> bool:
        events = await event_repo.list_by_group(group_id, limit=cfg.max_events)
        if not events:
            return False
        
        # Optional: Skip if summary for today already exists and is newer than last event
        # (For simplicity in dev runner, we just always generate)
        
        async with sem:
            try:
                content = await _generate_summary_for_group(
                    group_id, events, today, provider, cfg, uid_to_name, impression_repo, persona_repo
                )
                if group_id is None:
                    summary_dir = data_dir / "global" / "summaries"
                else:
                    summary_dir = data_dir / "groups" / group_id / "summaries"
                summary_dir.mkdir(parents=True, exist_ok=True)
                (summary_dir / f"{today}.md").write_text(content, encoding="utf-8")
                logger.debug(f"[{_MODULE_NAME}] wrote summary for group %r", group_id or "私聊")
                return True
            except Exception as exc:
                logger.warning(f"[{_MODULE_NAME}] failed for group %r: %s", group_id, exc)
                return False

    results = await asyncio.gather(*[_process_one(gid) for gid in group_ids])
    written = sum(1 for r in results if r)

    logger.info(f"[{_MODULE_NAME}] group summaries written: %d/%d", written, len(group_ids))
    return written


async def regenerate_single_summary(
    event_repo: EventRepository,
    data_dir: Path,
    provider_getter: Callable,
    group_id: str | None,
    date: str,
    summary_config: SummaryConfig | None = None,
    persona_repo: PersonaRepository | None = None,
    impression_repo: ImpressionRepository | None = None,
) -> str | None:
    """Regenerate summary for a specific group + date and return new content.

    Used by the WebUI [调用LLM重新总结] button.
    """
    from ..config import SummaryConfig as _SC
    cfg = summary_config or _SC()

    provider = provider_getter()
    if provider is None:
        return None

    uid_to_name: dict[str, str] = {}
    if persona_repo is not None:
        try:
            personas = await persona_repo.list_all()
            uid_to_name = {p.uid: p.primary_name for p in personas}
        except Exception:
            pass

    events = await event_repo.list_by_group(group_id, limit=cfg.max_events)
    if not events:
        return None

    content = await _generate_summary_for_group(
        group_id, events, date, provider, cfg, uid_to_name, impression_repo, persona_repo
    )

    if group_id is None:
        summary_dir = data_dir / "global" / "summaries"
    else:
        summary_dir = data_dir / "groups" / group_id / "summaries"
    summary_dir.mkdir(parents=True, exist_ok=True)
    (summary_dir / f"{date}.md").write_text(content, encoding="utf-8")
    return content
