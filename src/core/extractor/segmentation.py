"""Conservative memory-unit boundaries with complete, consecutive message coverage."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class MemorySegment:
    start: int
    end: int
    label: str = ""


def parse_segments(text: str, count: int) -> list[MemorySegment]:
    value = text.strip()
    if value.startswith("```"):
        value = "\n".join(value.splitlines()[1:-1])
    data = json.loads(value)
    if not isinstance(data, dict) or not isinstance(data.get("segments"), list):
        raise ValueError("segmentation requires a segments array")
    starts = {}
    for item in data["segments"]:
        if not isinstance(item, dict):
            continue
        start, label = item.get("start"), item.get("label", "")
        if type(start) is int and 0 <= start < count and isinstance(label, str):
            starts[start] = label.strip()[:10]
    if not starts:
        raise ValueError("segmentation contains no valid start")
    starts.setdefault(0, "")
    positions = sorted(starts)
    return [MemorySegment(a, b, starts[a]) for a, b in zip(positions, positions[1:] + [count])]


def merge_segments(segments: list[MemorySegment], count: int, messages_per_segment: int = 12,
                   label_vectors: dict[str, list[float]] | None = None) -> list[MemorySegment]:
    parts = list(segments)
    vectors = label_vectors or {}

    def similarity(a, b):
        left, right = vectors.get(parts[a].label), vectors.get(parts[b].label)
        if not left or not right or len(left) != len(right):
            return 0.0
        norm = math.sqrt(sum(v * v for v in left) * sum(v * v for v in right))
        return sum(x * y for x, y in zip(left, right)) / norm if norm else 0.0

    def combine(a, b):
        lo, hi = min(a, b), max(a, b)
        label = max((parts[lo], parts[hi]), key=lambda p: p.end - p.start).label
        parts[lo:hi + 1] = [MemorySegment(parts[lo].start, parts[hi].end, label)]

    while len(parts) > 1:
        i = min(range(len(parts)), key=lambda k: parts[k].end - parts[k].start)
        if parts[i].end - parts[i].start >= 4:
            break
        neighbours = [k for k in (i - 1, i + 1) if 0 <= k < len(parts)]
        j = max(neighbours, key=lambda k: (similarity(i, k), -(parts[k].end - parts[k].start)))
        combine(i, j)
    cap = max(1, math.ceil(count / max(1, messages_per_segment)))
    while len(parts) > cap:
        i = max(range(len(parts) - 1), key=lambda k: similarity(k, k + 1))
        combine(i, i + 1)
    return parts


def paginate_segment(segment: MemorySegment, limit: int) -> list[MemorySegment]:
    size = segment.end - segment.start
    pages = math.ceil(size / limit) if limit > 0 else 1
    width, extra = divmod(size, pages)
    result, start = [], segment.start
    for i in range(pages):
        end = start + width + (i < extra)
        result.append(MemorySegment(start, end, segment.label))
        start = end
    return result
