"""世界时间索引：事件的时间标签、相对说法、近期判断与时间锚点。"""
from __future__ import annotations

from ...domain.anchors import belongs, interval, most_specific, place, present, select
from ..reader_support import RECENT_MONTHS


def _month(key: float) -> int:
    return int(key // 10000) * 12 + int(key // 100 % 100)


def _span(year: int, month: int | None, day: int | None, precision: str) -> tuple[int, int]:
    base = year * 10000
    if precision == "day" and month and day:
        return base + month * 100 + day, base + month * 100 + day
    if precision == "month" and month:
        return base + month * 100 + 1, base + month * 100 + 31
    return base + 101, base + 1231


class TimeIndexMixin:
    """世界时间索引：事件的时间标签、相对说法、近期判断与时间锚点。"""

    def _index_times(self) -> None:
        """World-calendar labels per event; "now" is the latest main-story time she knows."""
        self.times: dict[str, tuple[float, str]] = {}
        self.spans: dict[str, tuple[int, int]] = {}
        self.recounted: set[str] = set()
        self.now: tuple[float, str] | None = None
        self.now_precision = ""
        if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_times'").fetchone() is None:
            return
        self.times = {row["event_id"]: (row["sort_key"], row["label"])
                      for row in self.db.execute("SELECT event_id,sort_key,label FROM event_times")}
        self.spans = {row["event_id"]: _span(row["year"], row["month"], row["day"], row["precision"])
                      for row in self.db.execute(
                          "SELECT event_id,year,month,day,precision FROM event_times WHERE year IS NOT NULL "
                          "AND origin IN ('text','stage','story') AND precision IN ('day','month','season','year')")}
        if not self.times:
            return
        self.recounted = {row["event_id"] for row in self.db.execute(
            "SELECT event_id FROM events WHERE in_world_time='past'")} - self.times.keys()
        row = self.db.execute(
            "SELECT t.sort_key,t.label,t.precision FROM event_times t JOIN events e ON e.event_id=t.event_id "
            f"JOIN scenes s ON s.scene_key=e.scene_key JOIN {self.views} v ON v.event_id=t.event_id "
            "WHERE v.character=? AND v.channel!='unstated' AND s.chapter_no IS NOT NULL "
            "ORDER BY t.sort_key DESC LIMIT 1", (self.character,)).fetchone()
        self.now = (row["sort_key"], row["label"]) if row else None
        self.now_precision = row["precision"] if row else ""

    def _before(self, first: str, second: str) -> bool:
        if first in self.story_events and second in self.story_events:
            return ((self.position[first], self.event_order.get(first, 0))
                    < (self.position[second], self.event_order.get(second, 0)))
        return first in self.spans and second in self.spans and self.spans[first][1] < self.spans[second][0]

    def is_recent(self, event_id: str) -> bool:
        """Dated in the current stretch, the only evidence that may speak for the present.

        The stretch is the month of "now" and the month before; a season-precise "now" reaches two months back,
        and a year-precise one covers its year.
        """
        if not self.now or event_id not in self.times:
            return False
        key, now = self.times[event_id][0], self.now[0]
        if self.now_precision in ("year", "span", "era"):
            return int(key // 10000) == int(now // 10000)
        reach = 2 if self.now_precision == "season" else RECENT_MONTHS
        return key <= now and _month(key) >= _month(now) - reach

    def _index_anchors(self) -> None:
        """Each event's anchor: the most specific known anchor whose story range holds its scene.

        Recollections and events whose direct date lies far from the anchor are left to be placed by date. An
        anchor with no event the character knows is dropped, so she never tells time by an event she missed.
        """
        self.anchors: list = []
        self.placing: list = []
        self.anchor_of: dict[str, object] = {}
        self.intervals: dict[str, tuple[int, int]] = {}
        table = self.profile.anchors
        if not table or not self.times:
            return
        scenes = [dict(row) for row in self.db.execute(
            "SELECT scene_key,collection_name,chapter_no,story_code,story_name,avg_tag FROM scenes "
            "ORDER BY narrative_pos")]
        ranges = {anchor.name: set().union(*(select(scenes, stages) for stages in anchor.stages)) for anchor in table}
        direct: dict[str, tuple[int, int] | None] = {}
        for row in self.db.execute("SELECT event_id,year,month,day,precision,sort_key,label,origin FROM event_times"):
            span = interval(row["year"], row["month"], row["day"], row["precision"], row["sort_key"], row["label"])
            if span:
                self.intervals[row["event_id"]] = span
                if row["origin"] in ("text", "stage", "story"):
                    direct[row["event_id"]] = span
        known = {row["event_id"] for row in self.db.execute(
            f"SELECT event_id FROM {self.views} WHERE character=? AND channel!='unstated'", (self.character,))}
        members: dict[str, object] = {}
        for row in self.db.execute("SELECT event_id,scene_key,in_world_time FROM events"):
            if row["in_world_time"] == "past":
                continue
            anchor = most_specific(anchor for anchor in table if row["scene_key"] in ranges[anchor.name]
                                   and belongs(anchor, direct.get(row["event_id"])))
            if anchor:
                members[row["event_id"]] = anchor
        usable = {anchor.name for event_id, anchor in members.items() if event_id in known}
        self.anchors = [anchor for anchor in table if anchor.name in usable]
        self.anchor_of = {event_id: anchor for event_id, anchor in members.items() if anchor.name in usable}
        self.placing = [anchor for anchor in self.anchors if not anchor.parent and anchor.places]

    def time_label(self, event_id: str) -> str:
        if event_id in self.times:
            return self.times[event_id][1]
        return "往事" if event_id in self.recounted else ""

    def time_phrase(self, event_id: str, *, recent: bool = True) -> str:
        """What the character is shown for an event's time: an anchor phrase, or the calendar without anchors.

        Evidence from the current stretch is marked 最近, the only evidence that may speak for the present.
        """
        anchor = self.anchor_of.get(event_id)
        if anchor:
            phrase = anchor.name + anchor.during
        elif self.placing and event_id in self.intervals:
            phrase = place(self.intervals[event_id], self.times[event_id][0], self.placing)
        else:
            phrase = self.time_label(event_id)
        return phrase + ("·最近" if recent and phrase and self.is_recent(event_id) else "")

    def now_phrase(self) -> str:
        return present(self.now[0], self.placing) if self.placing and self.now else ""
