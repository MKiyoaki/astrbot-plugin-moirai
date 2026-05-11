"""Social orientation analyzer — event-level IPC coordinate derivation.

Takes an event's MessageWindow and a BigFiveBuffer, produces IPC-based
Impression updates for every (observer, subject) participant pair.

Two-layer aggregation:
  Single-relation layer: per observer uid → BigFiveVector → (B, P)
  Event layer:           salience-weighted mean across messages from that observer

The resulting (B_e, P_e) is then used to derive ipc_orientation, affect_intensity,
and r_squared via ipc_model functions.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import TYPE_CHECKING

from .ipc_model import bigfive_to_ipc, classify_octant, affect_intensity, r_squared
from ..domain.models import Impression

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow
    from ..repository.base import ImpressionRepository, EventRepository
    from .big_five_scorer import BigFiveBuffer
    from ..config import PluginConfig

logger = logging.getLogger(__name__)


class SocialOrientationAnalyzer:
    """Derive IPC impression coordinates from a closed MessageWindow.

    For each (observer, subject) pair in the window's participant list:
      1. Retrieve the observer's BigFiveVector from the buffer.
      2. If vector is zero (missing LLM data), fallback to heuristic rules:
         - Count shared events between observer and subject.
         - If count >= threshold, assign conservative friendly/dominant scores.
      3. Rotate to IPC coordinates: bigfive_to_ipc() → (B, P).
      4. Weight by message salience and observer activity.
      5. Compute derived fields: ipc_orientation, affect_intensity, r_squared.
      6. Upsert the Impression record using EMA smoothing.
    """

    def __init__(
        self, 
        impression_repo: ImpressionRepository,
        event_repo: EventRepository | None = None,
        cfg: PluginConfig | None = None,
    ) -> None:
        self._impression_repo = impression_repo
        self._event_repo = event_repo
        self._cfg = cfg

    async def analyze(
        self,
        window: MessageWindow,
        big_five_buffer: BigFiveBuffer,
        event_salience: float = 0.5,
        scope: str = "global",
        event_id: str | None = None,
    ) -> int:
        """Analyze the window and upsert Impressions for all participant pairs."""
        participants = window.participants
        if len(participants) < 2:
            return 0

        # Collect messages per participant for salience weighting.
        msg_counts: dict[str, int] = {}
        for msg in window.messages:
            msg_counts[msg.uid] = msg_counts.get(msg.uid, 0) + 1
        total_msgs = max(1, sum(msg_counts.values()))

        updated = 0
        now = time.time()

        for obs_uid in participants:
            bfv = big_five_buffer.get_cached(obs_uid)
            is_zero = all(v == 0.0 for v in [
                bfv.openness, bfv.conscientiousness, bfv.extraversion,
                bfv.agreeableness, bfv.neuroticism
            ])

            for subj_uid in participants:
                if subj_uid == obs_uid:
                    continue

                b_e, p_e = 0.0, 0.0
                
                # Path A: Scientific (LLM Big Five)
                if not is_zero:
                    b_obs, p_obs = bigfive_to_ipc(bfv)
                    weight = msg_counts.get(obs_uid, 0) / total_msgs
                    if weight == 0.0:
                        weight = 1.0 / len(participants)
                    b_e = b_obs * event_salience * weight
                    p_e = p_obs * event_salience * weight
                
                # Path B: Heuristic Fallback (Shared events count)
                elif self._event_repo and self._cfg:
                    # Only trigger if LLM failed AND rule threshold met
                    try:
                        # Debounce check to avoid heavy DB queries on every event
                        existing = await self._impression_repo.get(obs_uid, subj_uid, scope)
                        debounce_sec = self._cfg.impression_trigger_debounce_hours * 3600
                        if existing and (now - existing.last_reinforced_at) < debounce_sec:
                            continue

                        # Shared events lookup
                        obs_events = await self._event_repo.list_by_participant(obs_uid, limit=100)
                        subj_ids = {e.event_id for e in await self._event_repo.list_by_participant(subj_uid, limit=100)}
                        shared_count = sum(1 for e in obs_events if e.event_id in subj_ids and (e.group_id or "global") == scope)
                        
                        if shared_count < self._cfg.impression_event_trigger_threshold:
                            continue
                            
                        # Heuristic scores: conservative and friendly
                        if shared_count >= 10:
                            b_e = min(1.0, 0.3 + event_salience * 0.4)
                            p_e = 0.2
                        else:
                            b_e = min(1.0, 0.1 + event_salience * 0.3)
                            p_e = 0.0
                    except Exception as exc:
                        logger.debug("[OrientationAnalyzer] fallback check failed: %s", exc)
                        continue

                # Skip if neither path produced a signal
                if b_e == 0.0 and p_e == 0.0:
                    continue

                try:
                    ipc_o = classify_octant(b_e, p_e)
                    ai = affect_intensity(b_e, p_e)
                    rs = r_squared(b_e, p_e)
                    await self._upsert_impression(
                        obs_uid, subj_uid, ipc_o, b_e, p_e, ai, rs,
                        scope, window, event_id=event_id,
                    )
                    updated += 1
                except Exception as exc:
                    logger.warning(
                        "[OrientationAnalyzer] failed to upsert %s→%s: %s",
                        obs_uid[:8], subj_uid[:8], exc,
                    )

        return updated

    async def _upsert_impression(
        self,
        obs_uid: str, subj_uid: str,
        ipc_o: str, b: float, p: float, ai: float, rs: float,
        scope: str, window: MessageWindow,
        event_id: str | None = None,
    ) -> None:
        existing = await self._impression_repo.get(obs_uid, subj_uid, scope)
        if existing is None:
            imp = Impression(
                observer_uid=obs_uid,
                subject_uid=subj_uid,
                ipc_orientation=ipc_o,
                benevolence=b,
                power=p,
                affect_intensity=ai,
                r_squared=rs,
                confidence=rs,
                scope=scope,
                evidence_event_ids=[event_id] if event_id else [],
                last_reinforced_at=time.time(),
            )
        else:
            alpha = 0.3
            # Append this event to evidence list (cap at 100 to bound DB growth).
            evidence = list(existing.evidence_event_ids)
            if event_id and event_id not in evidence:
                evidence.append(event_id)
            evidence = evidence[-100:]
            imp = dataclasses.replace(
                existing,
                ipc_orientation=ipc_o,
                benevolence=_ema(b, existing.benevolence, alpha),
                power=_ema(p, existing.power, alpha),
                affect_intensity=_ema(ai, existing.affect_intensity, alpha),
                r_squared=_ema(rs, existing.r_squared, alpha),
                confidence=_ema(rs, existing.confidence, alpha),
                evidence_event_ids=evidence,
                last_reinforced_at=time.time(),
            )
        await self._impression_repo.upsert(imp)


def _ema(new: float, old: float, alpha: float = 0.3) -> float:
    """Exponential moving average: alpha * new + (1 - alpha) * old."""
    return alpha * new + (1.0 - alpha) * old
