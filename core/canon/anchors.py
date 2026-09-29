"""Story-event time anchors: an event's world time said against well-known events instead of a calendar year.

The calendar stays underneath for sorting and recency; only the words shown to the model change. The anchor table
itself is story data and lives on the character profile.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

TOLERANCE_MONTHS = 24
_DIGITS = "零一二三四五六七八九"
_MONTH_RANGE = re.compile(r"(\d+)–(\d+)月")


@dataclass(frozen=True)
class Stages:
    """Scenes from ``first`` to ``last`` in story order, or exactly the ``only`` references.

    A reference is a stage code, a code with its phase (``1-4@行动前``) or, for stories without stage codes, the
    story name; ``^`` and ``$`` stand for the first and last scene of the selection. ``skip`` drops scenes whose
    code equals an entry or, for an entry ending in ``-``, starts with it.
    """

    first: str = "^"
    last: str = "$"
    collection: str = ""
    chapters: tuple[int, int] | None = None
    skip: tuple[str, ...] = ()
    only: tuple[str, ...] = ()


@dataclass(frozen=True)
class Anchor:
    """A well-known event: ``name`` is what the character says, ``event`` the formal name for reviewers.

    ``span`` is the world-time interval as yyyymmdd integers. ``during`` is appended for events inside it
    (期间, or 时 for a moment). ``places`` is false for an anchor whose span is too vague to place other events.
    """

    name: str
    event: str
    span: tuple[int, int]
    stages: tuple[Stages, ...]
    parent: str = ""
    during: str = "期间"
    places: bool = True


def _number(value: int) -> str:
    if value == 2:
        return "两"
    if value < 10:
        return _DIGITS[value]
    tens, ones = divmod(value, 10)
    return (_DIGITS[tens] if tens > 1 else "") + "十" + (_DIGITS[ones] if ones else "")


def month_index(key: float) -> int:
    return int(key // 10000) * 12 + int(key // 100 % 100)


def distance(months: int, *, yearly: bool = False) -> str:
    """How far apart, never finer than the date allows: a year-only date is said in whole years."""
    if yearly and months < 12:
        return "一年内"
    if months < 1:
        return "不久"
    if months < 12:
        return f"约{_number(months)}个月"
    years = (months + 6) // 12
    return "很久" if years >= 100 else f"约{_number(years)}年"


def interval(year: int | None, month: int | None, day: int | None, precision: str, key: float,
             label: str) -> tuple[int, int] | None:
    """The yyyymmdd interval a calendar row stands for; a season covers its middle month and the two beside it."""
    if year is None or precision not in ("day", "month", "season", "year"):
        return None
    base = year * 10000
    if precision == "day" and month and day:
        return base + month * 100 + day, base + month * 100 + day
    if precision == "month" and month:
        found = _MONTH_RANGE.search(label or "")
        last = int(found.group(2)) if found else month
        return base + month * 100 + 1, base + last * 100 + 31
    if precision == "season":
        middle = int(key // 100 % 100)
        return base + max(1, middle - 1) * 100 + 1, base + min(12, middle + 1) * 100 + 31
    return base + 101, base + 1231


def _gap(first: tuple[int, int], second: tuple[int, int]) -> int:
    if first[1] < second[0]:
        return month_index(second[0]) - month_index(first[1])
    if second[1] < first[0]:
        return month_index(first[0]) - month_index(second[1])
    return 0


def belongs(anchor: Anchor, direct: tuple[int, int] | None) -> bool:
    """A scene inside an anchor's range still holds recollections; a direct date far from the span marks one."""
    return direct is None or _gap(direct, anchor.span) <= TOLERANCE_MONTHS


def _matches(scene: Mapping, reference: str) -> bool:
    code, _, phase = reference.partition("@")
    if scene["story_code"]:
        return scene["story_code"] == code and (not phase or scene["avg_tag"] == phase)
    return scene["story_name"] == code


def _skipped(scene: Mapping, skip: tuple[str, ...]) -> bool:
    code = scene["story_code"] or ""
    return any(code.startswith(entry) if entry.endswith("-") else code == entry for entry in skip)


def select(scenes: list[Mapping], stages: Stages) -> set[str]:
    """Scene keys a range covers; scenes arrive in story order and a missing endpoint selects nothing."""
    pool = [scene for scene in scenes
            if (not stages.collection or scene["collection_name"] == stages.collection)
            and (stages.chapters is None or scene["chapter_no"] is not None
                 and stages.chapters[0] <= scene["chapter_no"] <= stages.chapters[1])]
    if stages.only:
        chosen = [scene for scene in pool if any(_matches(scene, ref) for ref in stages.only)]
    else:
        starts = [i for i, scene in enumerate(pool) if stages.first == "^" and i == 0 or _matches(scene, stages.first)]
        ends = [i for i, scene in enumerate(pool)
                if stages.last == "$" and i == len(pool) - 1 or _matches(scene, stages.last)]
        if not starts or not ends or starts[0] > ends[-1]:
            return set()
        chosen = pool[starts[0]:ends[-1] + 1]
    return {scene["scene_key"] for scene in chosen if not _skipped(scene, stages.skip)}


def _width(anchor: Anchor) -> int:
    return month_index(anchor.span[1]) - month_index(anchor.span[0])


def most_specific(candidates: Iterable[Anchor]) -> Anchor | None:
    return min(candidates, key=lambda anchor: (not anchor.parent, _width(anchor)), default=None)


def place(span: tuple[int, int], key: float, anchors: list[Anchor]) -> str:
    """Words for a dated event outside every anchor range, relative to the nearest anchor."""
    if not anchors:
        return ""
    inside = [anchor for anchor in anchors if anchor.span[0] <= span[0] and span[1] <= anchor.span[1]]
    if inside:
        anchor = min(inside, key=_width)
        return anchor.name + ("期间" if anchor.during == "期间" else "前后")
    point = (int(key), int(key))
    yearly = month_index(span[1]) - month_index(span[0]) >= 11
    overlap = [anchor for anchor in anchors if anchor.span[0] <= span[1] and span[0] <= anchor.span[1]]
    if overlap:
        anchor = min(overlap, key=lambda anchor: (_gap(point, anchor.span), _width(anchor)))
        return anchor.name + ("那一年" if yearly else "前后")
    before = max((anchor for anchor in anchors if anchor.span[1] < span[0]), key=lambda anchor: anchor.span[1],
                 default=None)
    after = min((anchor for anchor in anchors if anchor.span[0] > span[1]), key=lambda anchor: anchor.span[0],
                default=None)
    if before and (after is None or _gap(before.span, point) <= _gap(point, after.span)):
        return before.name + "之后" + distance(_gap(before.span, point), yearly=yearly)
    return after.name + "以前" + distance(_gap(point, after.span), yearly=yearly)


def present(key: float, anchors: list[Anchor]) -> str:
    """"Now" as the latest anchor it falls in or follows."""
    point = (int(key), int(key))
    inside = [anchor for anchor in anchors if anchor.span[0] <= point[0] <= anchor.span[1]]
    if inside:
        return min(inside, key=_width).name + "刚结束的时候"
    before = max((anchor for anchor in anchors if anchor.span[1] < point[0]), key=lambda anchor: anchor.span[1],
                 default=None)
    return before.name + "之后" + distance(_gap(before.span, point)) if before else ""
