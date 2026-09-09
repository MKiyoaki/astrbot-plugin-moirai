"""Deferred second pass: batch-annotate finalised events with first-person [Eval] asides."""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from .parser import parse_eval_map
from .prompts import build_eval_prompt
from .summary import apply_evals, split_subtopics

logger = logging.getLogger(__name__)

# (user_prompt, system_prompt) -> completion text. Retry / timeout policy is the
# caller's concern so each runtime keeps its own.
EvalCall = Callable[[str, str], Awaitable[str]]


async def annotate_events_evals(
    *,
    call: EvalCall,
    items: list[tuple[str, str, str]],
    bot_persona_desc: str,
    system_prompt: str,
) -> dict[str, str]:
    """Return ``{key: summary_with_evals}`` for a batch of ``(key, topic, summary)``.

    One LLM call for the whole batch. Runs strictly after fact / tag / salience
    extraction, so the persona never perturbs those. Any failure degrades every
    affected summary to a 「未生成评价」 backfill and never propagates.
    """
    subs = {key: split_subtopics(summary) for key, _, summary in items}
    summaries = {key: summary for key, _, summary in items}
    result = {key: apply_evals(summaries[key], []) for key in summaries}

    annotatable = [(key, topic, subs[key]) for key, topic, _ in items if subs[key]]
    if not annotatable:
        return result

    try:
        prompt = build_eval_prompt(bot_persona_desc, annotatable)
        raw = await call(prompt, system_prompt)
        parsed = parse_eval_map(
            raw or "", {key: len(subtopics) for key, _, subtopics in annotatable}
        )
    except Exception as exc:
        logger.warning(
            "[EventExtractor] eval pass failed for %d event(s); backfilling asides: %s",
            len(annotatable), exc,
        )
        return result

    for key, _, _ in annotatable:
        result[key] = apply_evals(summaries[key], parsed.get(key, []))
    return result


async def annotate_event_evals(
    *,
    call: EvalCall,
    topic: str,
    summary: str,
    bot_persona_desc: str,
    system_prompt: str,
) -> str:
    """Single-event convenience wrapper (used by manual re-extraction)."""
    out = await annotate_events_evals(
        call=call,
        items=[("0", topic, summary)],
        bot_persona_desc=bot_persona_desc,
        system_prompt=system_prompt,
    )
    return out["0"]
