"""canon 只读访问的公共辅助：别名匹配与检索限额，被 CanonReader 和它的 mixin 共用。"""
from __future__ import annotations

import re

from ...utils.text_utils import is_cjk
from ..constant_utils import SINGLE_LEFT, SINGLE_RIGHT
from ..settings import SETTINGS


LEXICAL_LIMIT = SETTINGS.reader.lexical_limit
ENTITY_LIMIT = SETTINGS.reader.entity_limit
PER_SCENE = SETTINGS.reader.per_scene
LATIN_WORD = re.compile(r"^[A-Za-z0-9'.-]+$")


def matches_alias(query: str, alias: str) -> list[tuple[int, int]]:
    if LATIN_WORD.fullmatch(alias):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])"
        return [(m.start(), m.end()) for m in re.finditer(pattern, query)]
    if len(alias) == 1 and is_cjk(alias):
        return [(i, i + 1) for i, char in enumerate(query) if char == alias and single_ok(query, i)]
    found = []
    start = 0
    while (pos := query.find(alias, start)) >= 0:
        found.append((pos, pos + len(alias)))
        start = pos + len(alias)
    return found


def single_ok(text: str, i: int) -> bool:
    """A one-character name counts only between non-letters or name-friendly particles, never inside a word."""
    left = text[i - 1] if i > 0 else ""
    right = text[i + 1] if i + 1 < len(text) else ""
    return ((not left or not is_cjk(left) or left in SINGLE_LEFT)
            and (not right or not is_cjk(right) or right in SINGLE_RIGHT))


RECENT_MONTHS = SETTINGS.reader.recent_months
