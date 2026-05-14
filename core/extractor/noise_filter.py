"""Pre-LLM noise filter for semantic partitioning pipeline.

Applied after DBSCAN partitioning and before LLM distillation to strip
low-signal messages (pure emoji, very short, character-repeat "复读") from
each partition. Partitions that are predominantly noise are discarded to
avoid wasting LLM tokens on meaningless content.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow
    from .partitioner import Partition

# Matches Unicode emoji blocks (supplementary + misc symbols)
_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001F9FF"
    r"\U00002600-\U000027BF"
    r"\U0000FE00-\U0000FE0F"
    r"‍"
    r"]+"
)

# Minimum non-whitespace characters required to be considered meaningful
_MIN_CONTENT_LEN = 3

# If a single character makes up more than this fraction of the text, treat as 复读
_REPEAT_CHAR_RATIO = 0.70

# Drop an entire partition when the noisy message fraction exceeds this threshold
_PARTITION_NOISE_THRESHOLD = 0.80


def is_noisy_message(text: str) -> bool:
    """Return True if the message text carries no extractable signal."""
    clean = text.strip()
    if len(clean) < _MIN_CONTENT_LEN:
        return True
    # Remove emoji to check remaining content
    non_emoji = _EMOJI_RE.sub("", clean)
    if len(non_emoji.strip()) < _MIN_CONTENT_LEN:
        return True
    # Detect 复读 pattern: a single character dominates
    if clean:
        max_char_count = max(clean.count(c) for c in set(clean))
        if max_char_count / len(clean) > _REPEAT_CHAR_RATIO and len(clean) > 5:
            return True
    return False


def filter_partition(
    partition: Partition,
    window: MessageWindow,
) -> Partition | None:
    """Return a filtered Partition with noisy messages removed, or None to skip entirely."""
    from .partitioner import Partition as _Partition

    if not partition.indices:
        return None

    kept = [
        i for i in partition.indices
        if not is_noisy_message(
            getattr(window.messages[i], "content_preview", None) or
            getattr(window.messages[i], "content", None) or ""
        )
    ]

    if not kept:
        return None

    noisy_fraction = 1.0 - len(kept) / len(partition.indices)
    if noisy_fraction > _PARTITION_NOISE_THRESHOLD:
        return None

    if len(kept) == len(partition.indices):
        return partition  # Nothing filtered — return as-is

    return _Partition(indices=kept, metadata=partition.metadata)


def filter_partitions(
    partitions: list[Partition],
    window: MessageWindow,
) -> list[Partition]:
    """Filter all partitions in a list, dropping fully-noisy ones."""
    result = []
    for part in partitions:
        filtered = filter_partition(part, window)
        if filtered is not None:
            result.append(filtered)
    return result
