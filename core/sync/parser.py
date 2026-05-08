"""Parse IMPRESSIONS.md files back into Impression dataclasses.

The parser understands the format written by persona_impressions.md.j2.
Fields that cannot be parsed are silently skipped; only blocks where all
required fields (observer_uid, ipc_orientation, benevolence, power,
affect_intensity, r_squared, confidence, scope) are present are returned.
"""
from __future__ import annotations

import re
import time

from ..domain.models import Impression

# Section heading:  ## 来自 `{observer_uid}` 的印象（范围：{scope}）
_SECTION_RE = re.compile(
    r"^## 来自\s+`([^`]+)`\s+的印象（范围：([^）]+)）",
    re.MULTILINE,
)

# Table row regexes (match within a section block)
_ORIENTATION_RE = re.compile(r"^\|\s*社交取向\s*\|\s*([^|]+)\s*\|", re.MULTILINE)
_BENE_RE = re.compile(
    r"^\|\s*亲和度\s*\|\s*[^（]*（([+-]?\d+\.\d+)）\s*\|", re.MULTILINE
)
_POWER_RE = re.compile(
    r"^\|\s*支配度\s*\|\s*[^（]*（([+-]?\d+\.\d+)）\s*\|", re.MULTILINE
)
_INTENSITY_RE = re.compile(r"^\|\s*情感强度\s*\|\s*(\d+)%\s*\|", re.MULTILINE)
_RSQUARED_RE = re.compile(r"^\|\s*拟合优度\s*\|\s*(\d+)%\s*\|", re.MULTILINE)
_CONFIDENCE_RE = re.compile(r"^\|\s*置信度\s*\|\s*(\d+)%\s*\|", re.MULTILINE)
_EVIDENCE_RE = re.compile(r"^\*\*依据事件：\*\*\s*(.+)$", re.MULTILINE)


def parse_impressions_md(content: str, subject_uid: str) -> list[Impression]:
    """Parse an IMPRESSIONS.md file and return a list of Impression objects.

    subject_uid is the persona whose IMPRESSIONS.md this is (the file lives
    under data/personas/{subject_uid}/IMPRESSIONS.md).

    Blocks missing required fields are silently skipped.  last_reinforced_at
    is set to the current wall-clock time because the file was just modified.
    """
    sections = list(_SECTION_RE.finditer(content))
    if not sections:
        return []

    results: list[Impression] = []
    now = time.time()

    for i, match in enumerate(sections):
        observer_uid = match.group(1).strip()
        scope = match.group(2).strip()

        # Extract text from end of this heading to start of the next
        start = match.end()
        end = sections[i + 1].start() if i + 1 < len(sections) else len(content)
        block = content[start:end]

        orient_m = _ORIENTATION_RE.search(block)
        bene_m = _BENE_RE.search(block)
        power_m = _POWER_RE.search(block)
        intensity_m = _INTENSITY_RE.search(block)
        rsquared_m = _RSQUARED_RE.search(block)
        conf_m = _CONFIDENCE_RE.search(block)

        if not (orient_m and bene_m and power_m and intensity_m and rsquared_m and conf_m):
            continue  # incomplete block — skip

        ipc_orientation = orient_m.group(1).strip()
        benevolence = float(bene_m.group(1))
        power = float(power_m.group(1))
        affect_intensity = int(intensity_m.group(1)) / 100.0
        r_squared = int(rsquared_m.group(1)) / 100.0
        confidence = int(conf_m.group(1)) / 100.0

        # Clamp to domain-model valid ranges
        benevolence = max(-1.0, min(1.0, benevolence))
        power = max(-1.0, min(1.0, power))
        affect_intensity = max(0.0, min(1.0, affect_intensity))
        r_squared = max(0.0, min(1.0, r_squared))
        confidence = max(0.0, min(1.0, confidence))

        evidence_event_ids: list[str] = []
        ev_m = _EVIDENCE_RE.search(block)
        if ev_m:
            evidence_event_ids = [
                e.strip() for e in ev_m.group(1).split(",") if e.strip()
            ]

        try:
            imp = Impression(
                observer_uid=observer_uid,
                subject_uid=subject_uid,
                ipc_orientation=ipc_orientation,
                benevolence=benevolence,
                power=power,
                affect_intensity=affect_intensity,
                r_squared=r_squared,
                confidence=confidence,
                scope=scope,
                evidence_event_ids=evidence_event_ids,
                last_reinforced_at=now,
            )
            results.append(imp)
        except ValueError:
            continue  # domain model validation rejected the block

    return results
