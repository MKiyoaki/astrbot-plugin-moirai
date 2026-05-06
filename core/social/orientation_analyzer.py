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
    from ..repository.base import ImpressionRepository
    from .big_five_scorer import BigFiveBuffer

logger = logging.getLogger(__name__)


class SocialOrientationAnalyzer:
    """Derive IPC impression coordinates from a closed MessageWindow.

    For each (observer, subject) pair in the window's participant list:
      1. Retrieve the observer's BigFiveVector from the buffer (or zero if absent).
      2. Rotate to IPC coordinates: bigfive_to_ipc() → (B, P).
      3. Weight by message salience (approximated from the event salience).
      4. Compute derived fields: ipc_orientation, affect_intensity, r_squared.
      5. Upsert the Impression record.

    This runs as a background asyncio task after event extraction completes.
    """

    def __init__(self, impression_repo: ImpressionRepository) -> None:
        self._impression_repo = impression_repo

    async def analyze(
        self,
        window: MessageWindow,
        big_five_buffer: BigFiveBuffer,
        event_salience: float = 0.5,
        scope: str = "global",
    ) -> int:
        """Analyze the window and upsert Impressions for all participant pairs.

        Returns the number of Impressions updated.
        """
        participants = window.participants
        if len(participants) < 2:
            return 0

        # Collect messages per participant for salience weighting.
        # Each message contributes weight proportional to event_salience.
        msg_counts: dict[str, int] = {}
        for msg in window.messages:
            msg_counts[msg.uid] = msg_counts.get(msg.uid, 0) + 1
        total_msgs = max(1, sum(msg_counts.values()))

        updated = 0
        for obs_uid in participants:
            bfv = big_five_buffer.get_cached(obs_uid)
            b_obs, p_obs = bigfive_to_ipc(bfv)

            # Weight by how many messages this observer sent in the window.
            weight = msg_counts.get(obs_uid, 0) / total_msgs
            if weight == 0.0:
                # Observer was listed as participant but sent no messages.
                # Use uniform weight rather than skipping entirely.
                weight = 1.0 / len(participants)

            # Scale coordinates by event salience so low-salience events
            # contribute weaker signal to the Impression.
            b_e = b_obs * event_salience * weight
            p_e = p_obs * event_salience * weight

            ipc_o = classify_octant(b_e, p_e)
            ai = affect_intensity(b_e, p_e)
            rs = r_squared(b_e, p_e)

            for subj_uid in participants:
                if subj_uid == obs_uid:
                    continue
                try:
                    await self._upsert_impression(
                        obs_uid, subj_uid, ipc_o, b_e, p_e, ai, rs,
                        scope, window,
                    )
                    updated += 1
                except Exception as exc:
                    logger.warning(
                        "[OrientationAnalyzer] failed to upsert %s→%s: %s",
                        obs_uid[:8], subj_uid[:8], exc,
                    )

        logger.debug(
            "[OrientationAnalyzer] updated %d impressions for session %s",
            updated, window.session_id,
        )
        return updated

    async def _upsert_impression(
        self,
        obs_uid: str, subj_uid: str,
        ipc_o: str, b: float, p: float, ai: float, rs: float,
        scope: str, window: MessageWindow,
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
                confidence=0.5,
                scope=scope,
                evidence_event_ids=[],
                last_reinforced_at=time.time(),
            )
        else:
            # Exponential moving average: new = 0.3 * current + 0.7 * existing.
            # Keeps recent events more influential while retaining history.
            imp = dataclasses.replace(
                existing,
                ipc_orientation=ipc_o,
                benevolence=_ema(b, existing.benevolence),
                power=_ema(p, existing.power),
                affect_intensity=_ema(ai, existing.affect_intensity),
                r_squared=_ema(rs, existing.r_squared),
                last_reinforced_at=time.time(),
            )
        await self._impression_repo.upsert(imp)


def _ema(new: float, old: float, alpha: float = 0.3) -> float:
    """Exponential moving average: alpha * new + (1 - alpha) * old."""
    return alpha * new + (1.0 - alpha) * old
