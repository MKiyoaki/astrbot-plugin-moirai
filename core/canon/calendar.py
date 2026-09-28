"""World-calendar coordinates for canon events, from in-scene date captions and an external dated timeline.

Only coordinates are stored: year, month, day, sort key, display label, precision and origin per event.
The external timeline decides where a scene sits on the axis; none of its text reaches the model.
A date written in the scene outranks it, and an event that recounts an earlier time never takes the date
of the scene that tells it.
"""
from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from urllib.parse import unquote

PARTS = {"初": 1, "新春": 1, "春": 4, "夏": 7, "秋": 10, "冬": 12, "末": 12, "底": 12}
PHASES = {"BEG": "行动前", "END": "行动后"}
WINDOW = 10000
EPIGRAPH_YEARS = 80
MATCH = 0.12
ERA_BASE = -10 ** 9
SKIP_LABELS = frozenset(("来源", "目录", "附表", "编辑指引", "展开泰拉大典", "？？？"))
CAPTION_KINDS = ("caption", "narration")
_CODE = r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+"
_CAPTION = re.compile(
    r"(?:^|[\s，,])(约)?(\d{3,4})\s*年\s*(?:(\d{1,2})\s*月\s*(?:(\d{1,2})\s*日)?)?\s*(初|末|底)?\s*([春夏秋冬])?季?"
    r"\s*(?:(\d{1,2}):(\d{2})\s*(?:([AP])\.?\s*M\.?)?)?(?:[，,\s]\s*[^，,。\d]{1,12})?$")
_BIGRAM = re.compile(r"[一-鿿]{2,}")


@dataclass(frozen=True)
class WorldTime:
    """A point or span on one world axis; unknown parts sort to the middle of the known unit."""

    year: int | None
    month: int | None = None
    day: int | None = None
    part: str = ""
    month_to: int | None = None
    year_to: int | None = None
    minute: int = 0
    approx: bool = False
    hide_day: bool = False
    era: str = ""
    rank: int = 0

    @property
    def key(self) -> float:
        if self.year is None:
            return float(ERA_BASE + self.rank)
        month = self.month or PARTS.get(self.part, 6)
        day = self.day or 15
        return self.year * 10000 + month * 100 + day + self.minute / 2000

    @property
    def precision(self) -> str:
        if self.year is None:
            return "era"
        if self.year_to is not None:
            return "span"
        if self.day and not self.hide_day:
            return "day"
        if self.month:
            return "month"
        return "season" if self.part else "year"

    @property
    def label(self) -> str:
        if self.year is None:
            return self.era
        year = f"前{-self.year}" if self.year < 0 else str(self.year)
        prefix = "约" if self.approx else ""
        if self.year_to is not None:
            if self.year_to - self.year == 9 and self.year % 10 == 0:
                return f"{prefix}{self.year}年代"
            if self.year_to - self.year == 99 and self.year % 100 == 0:
                return f"{prefix}{self.year // 100 + 1}世纪"
            until = f"前{-self.year_to}" if self.year_to < 0 else str(self.year_to)
            return f"{prefix}{year}–{until}年"
        if self.month:
            months = f"{self.month}–{self.month_to}月" if self.month_to else f"{self.month}月"
            return f"{prefix}{year}年{months}" + (f"{self.day}日" if self.day and not self.hide_day else "")
        part = {"初": "初", "新春": "初", "末": "末", "底": "末"}.get(self.part, self.part)
        return f"{prefix}{year}年{part}"

    def coarse(self) -> WorldTime:
        """Shown at month precision for scenes that only inherit a neighbour's date, still sorted after it."""
        return replace(self, hide_day=True) if self.day else self


@dataclass(frozen=True)
class StageRef:
    collection: str = ""
    code: str = ""
    name: str = ""
    phase: str = ""


@dataclass(frozen=True)
class EventTime:
    event_id: str
    time: WorldTime
    origin: str
    sort: float | None = None

    @property
    def key(self) -> float:
        return self.time.key if self.sort is None else self.sort


def section_year(section: str) -> int | None:
    match = re.search(r"(\d{3,4})\s*年\s*$", (section or "").split(" / ")[-1])
    return int(match.group(1)) if match else None


def parse_entry_time(section: str, label: str | None, text: str = "", rank: int = 0) -> WorldTime | None:
    """Read one timeline row's time from its label, falling back to the section heading for the year."""
    label = re.sub(r"\s+", " ", (label or "").strip())
    if not label or label in SKIP_LABELS or "未来" in section:
        return None
    year = section_year(section)
    if label in ("前文明时期", "泰拉纪元前未知年份"):
        return WorldTime(None, era="前文明时期" if label == "前文明时期" else "泰拉纪元前", rank=rank)
    if label == "泰拉历元年":
        return WorldTime(1)
    if match := re.fullmatch(r"(\d{3,4}) ?年 ?（时间未知）", label):
        return WorldTime(int(match.group(1)))
    if match := re.fullmatch(r"(\d{1,2}) ?(?:月)? ?[~～] ?(\d{1,2}) ?月", label):
        return WorldTime(year, int(match.group(1)), month_to=int(match.group(2))) if year else None
    if match := re.fullmatch(r"(\d{1,2}) ?月(?: ?(\d{1,2}) ?日)?", label):
        return WorldTime(year, int(match.group(1)), int(match.group(2)) if match.group(2) else None) if year else None
    if label in ("春季", "夏季", "秋季", "冬季", "年初", "年末", "新春"):
        part = label[0] if label.endswith("季") else ("新春" if label == "新春" else label[1])
        return WorldTime(year, part=part) if year else None
    if match := re.fullmatch(r"(\d{1,2}) ?世纪 ?(\d)0 ?年代", label):
        start = (int(match.group(1)) - 1) * 100 + int(match.group(2)) * 10
        return WorldTime(start, year_to=start + 9)
    if match := re.fullmatch(r"(\d{1,2}) ?世纪", label):
        start = (int(match.group(1)) - 1) * 100
        return WorldTime(start, year_to=start + 99)
    if match := re.fullmatch(r"(约)? ?(前)? ?(\d{1,5}) ?年?(?: ?[~～\-] ?(前)? ?(\d{1,5}) ?年)?(前后)?", label):
        if "年" not in label:
            return None
        first = -int(match.group(3)) if match.group(2) else int(match.group(3))
        last = None if match.group(5) is None else (-int(match.group(5)) if match.group(4) else int(match.group(5)))
        found = WorldTime(first, year_to=last, approx=bool(match.group(1) or match.group(6)))
        day = re.match(r"(\d{1,2})月(\d{1,2})日", text or "")
        return replace(found, month=int(day.group(1)), day=int(day.group(2))) if day and last is None else found
    return None


def caption_time(text: str) -> WorldTime | None:
    """A place-and-date caption such as 「泽尔格勒主城区 1102年1月20日 16:32」, never a sentence that mentions a year."""
    text = (text or "").strip()
    if not text or len(text) > 40 or "。" in text or text.startswith("——"):
        return None
    match = _CAPTION.search(text)
    if not match:
        return None
    year = int(match.group(2))
    month = int(match.group(3)) if match.group(3) else None
    day = int(match.group(4)) if match.group(4) else None
    minute = 0
    if match.group(7):
        hour = int(match.group(7)) % 12 + (12 if match.group(9) == "P" else 0) if match.group(9) else int(match.group(7))
        minute = hour * 60 + int(match.group(8))
    part = "" if month else (match.group(5) or match.group(6) or "")
    return WorldTime(year, month, day, part=part, minute=minute, approx=bool(match.group(1)))


def stage_refs(source: dict) -> list[StageRef]:
    """Story references in one timeline citation: its wiki page links first, then its label text."""
    refs = []
    for url in source.get("urls") or ():
        page = unquote(url.split("/w/", 1)[-1]).replace(" ", "_")
        if match := re.fullmatch(rf"({_CODE})_([^/#]+?)(?:/(BEG|END|NBT))?", page):
            refs.append(StageRef(code=match.group(1), name=match.group(2).replace("_", " "),
                                 phase=PHASES.get(match.group(3) or "", "")))
        elif match := re.search(rf"#[^#]*?：({_CODE})$", page):
            refs.append(StageRef(code=match.group(1)))
        elif "/" not in page and "#" not in page:
            refs.append(StageRef(collection=page.replace("_", " ")))
    head, _, stages = (source.get("label") or "").partition("：")
    names = [re.sub(r"（[^）]*）", "", re.sub(r"^(?:第[一二三四五六七八九十百零\d]+章|序章)\s*", "", part)).strip()
             for part in head.split("、")]
    names = [name for name in names if name]
    if not stages:
        refs += [StageRef(name) for name in names]
    elif not any(ref.code for ref in refs):
        for match in re.finditer(rf"({_CODE})\s*(行动前|行动后)?", stages):
            refs.append(StageRef(names[0] if len(names) == 1 else "", match.group(1), phase=match.group(2) or ""))
    return list(dict.fromkeys(refs))


def _phase(anchor: str) -> str:
    return next((phase for phase in ("行动前", "行动后") if (anchor or "").endswith(phase)), "")


class SceneIndex:
    """Match timeline citations to scenes by story code, story name and phase, or to a whole story."""

    def __init__(self, rows: list[sqlite3.Row]) -> None:
        self.by_code: dict[str, list[sqlite3.Row]] = defaultdict(list)
        self.by_name: dict[str, list[sqlite3.Row]] = defaultdict(list)
        self.by_collection: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            if row["story_code"]:
                self.by_code[row["story_code"]].append(row)
            if row["story_name"]:
                self.by_name[row["story_name"]].append(row)
            if row["collection_name"]:
                self.by_collection[row["collection_name"]].append(row)

    def stages(self, ref: StageRef) -> list[str]:
        if ref.code:
            found = self.by_code.get(ref.code, []) or [
                row for row in self.by_name.get(ref.name, []) if ref.name and not row["story_code"]]
            named = [row for row in found if ref.name and row["story_name"] == ref.name]
            found = named or [row for row in found if not ref.collection or row["collection_name"] == ref.collection]
        elif ref.collection in self.by_name and ref.collection not in self.by_collection:
            found = self.by_name[ref.collection]
        else:
            return []
        if ref.phase:
            found = [row for row in found if _phase(row["anchor"]) in (ref.phase, "")]
        return [row["scene_key"] for row in found]

    def story(self, ref: StageRef) -> str | None:
        rows = self.by_collection.get(ref.collection) if not ref.code else None
        return (rows[0]["collection_id"] or rows[0]["collection_name"]) if rows else None


def _bigrams(text: str) -> set[str]:
    return {run[i:i + 2] for run in _BIGRAM.findall(text or "") for i in range(len(run) - 1)}


def _similarity(first: str, second: str) -> float:
    a, b = _bigrams(first), _bigrams(second)
    return 2 * len(a & b) / (len(a) + len(b)) if a and b else 0.0


def resolve_event_times(db: sqlite3.Connection, entries: list[dict]) -> dict[str, EventTime]:
    """Place every event that has dated support; recounted events without a matched older date stay undated."""
    db.row_factory = sqlite3.Row
    scenes = db.execute("SELECT scene_key,narrative_pos,anchor,collection_id,collection_name,story_code,story_name,"
                        "chapter_no FROM scenes ORDER BY narrative_pos").fetchall()
    index = SceneIndex(scenes)
    stage_entries: dict[str, list[tuple[WorldTime, str]]] = defaultdict(list)
    story_entries: dict[str, list[WorldTime]] = defaultdict(list)
    for rank, entry in enumerate(entries):
        when = parse_entry_time(entry.get("section", ""), entry.get("time"), entry.get("text", ""), rank)
        if when is None:
            continue
        for source in entry.get("sources") or ():
            for ref in stage_refs(source):
                for scene in index.stages(ref):
                    stage_entries[scene].append((when, entry.get("text", "")))
                if story := index.story(ref):
                    story_entries[story].append(when)
    captions: dict[str, list[tuple[int, WorldTime]]] = defaultdict(list)
    for row in db.execute("SELECT scene_key,idx,text FROM lines WHERE kind IN ('caption','narration') "
                          "AND COALESCE(speaker,'')='' ORDER BY scene_key,idx"):
        if found := caption_time(row["text"]):
            captions[row["scene_key"]].append((row["idx"], found))
    events: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in db.execute(
            "SELECT e.event_id,e.scene_key,e.summary,e.in_world_time,e.in_world_note,"
            "(SELECT MIN(l.idx) FROM event_evidence ee JOIN lines l ON l.line_key=ee.line_key "
            " WHERE ee.event_id=e.event_id) AS first_line FROM events e ORDER BY e.scene_key,e.ord"):
        events[row["scene_key"]].append(row)
    stories: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for scene in scenes:
        stories[scene["collection_id"] or scene["collection_name"] or scene["scene_key"]].append(scene)
    out: dict[str, EventTime] = {}
    for story, members in stories.items():
        out.update(_resolve_story(members, stage_entries, story_entries.get(story, []), captions, events))
    return _order_main_line(out, scenes, events)


def _order_main_line(out: dict[str, EventTime], scenes, events) -> dict[str, EventTime]:
    """Main-line chapters run in story order, so a year- or season-only date sorts after the chapter before it."""
    floor = None
    for scene in sorted((scene for scene in scenes if scene["chapter_no"] is not None),
                        key=lambda scene: (scene["chapter_no"], scene["narrative_pos"])):
        for row in events.get(scene["scene_key"], ()):
            item = out.get(row["event_id"])
            if item is None or item.time.year is None:
                continue
            if item.time.precision in ("day", "month"):
                floor = item.key if floor is None else max(floor, item.key)
            elif (item.time.precision in ("year", "season") and floor is not None
                  and int(floor // 10000) == item.time.year and item.key < floor):
                out[row["event_id"]] = replace(item, sort=floor)
    return out


def _resolve_story(members, stage_entries, story_entries, captions, events) -> dict[str, EventTime]:
    dated = [when for scene in members for when, _ in stage_entries.get(scene["scene_key"], ())]
    dated += [when for scene in members for _, when in captions.get(scene["scene_key"], ())]
    dated += story_entries
    numbered = [when.key for when in dated if when.year is not None]
    present = max(numbered) if numbered else None

    def current(when: WorldTime) -> bool:
        return present is not None and when.year is not None and present - when.key < WINDOW

    def epigraph(when: WorldTime) -> bool:
        return present is not None and when.year is not None and present // 10000 - when.year > EPIGRAPH_YEARS

    captions = {key: [(idx, when) for idx, when in marks if not epigraph(when)] for key, marks in captions.items()}
    own: dict[str, tuple[WorldTime, bool]] = {}
    anchors: list[tuple[int, WorldTime]] = []
    for position, scene in enumerate(members):
        key = scene["scene_key"]
        cited = stage_entries.get(key, [])
        now = Counter(when for when, _ in cited if current(when))
        older = [when for when, _ in cited if not current(when)]
        rows = events.get(key, [])
        if now:
            chosen = max(now, key=lambda when: (now[when], when.key))
            own[key] = (chosen, False)
            anchors.append((position, chosen))
        elif older and sum(row["in_world_time"] == "past" for row in rows) * 2 > len(rows):
            year = Counter(when.year for when in older).most_common(1)[0][0]
            same = sorted((when for when in older if when.year == year), key=lambda when: when.key)
            own[key] = (same[0] if len(older) == 1 else WorldTime(year), True)
        anchors += [(position, when) for _, when in captions.get(key, ()) if current(when)]
    story_present = sorted((when for when in story_entries if current(when)), key=lambda when: when.key)
    out: dict[str, EventTime] = {}
    for position, scene in enumerate(members):
        key = scene["scene_key"]
        if key in own:
            base: tuple[WorldTime, str] | None = (own[key][0], "stage")
        else:
            before = [when for at, when in anchors if at < position]
            after = [when for at, when in anchors if at > position]
            near = before[-1] if before else (after[0] if after else None)
            base = ((near.coarse(), "inherited") if near else
                    (story_present[0], "story") if story_present else None)
        flashback = key in own and own[key][1]
        marks = captions.get(key, [])
        older = [(when, text) for when, text in stage_entries.get(key, []) if not current(when)]
        for row in events.get(key, []):
            line = row["first_line"]
            caption = next((when for idx, when in reversed(marks) if line is not None and idx <= line), None)
            if caption is not None:
                out[row["event_id"]] = EventTime(row["event_id"], caption, "text")
            elif row["in_world_time"] == "past" and not flashback:
                found = _recounted(row, older)
                if found:
                    out[row["event_id"]] = found
            elif base:
                out[row["event_id"]] = EventTime(row["event_id"], base[0], base[1])
    return out


def _recounted(row: sqlite3.Row, older: list[tuple[WorldTime, str]]) -> EventTime | None:
    """An older entry dates a recounted event only when its wording matches the event's summary."""
    if older:
        score, when = max(((_similarity(row["summary"], text), when) for when, text in older), key=lambda item: item[0])
        if score >= MATCH:
            return EventTime(row["event_id"], when, "stage")
    match = re.search(r"(1[01]\d\d)年", row["in_world_note"] or "")
    return EventTime(row["event_id"], WorldTime(int(match.group(1))), "note") if match else None


def apply_event_times(db: sqlite3.Connection, times: dict[str, EventTime], source: str) -> None:
    """Replace all stored coordinates in one transaction."""
    db.execute("BEGIN IMMEDIATE")
    try:
        db.execute("DELETE FROM event_times")
        db.executemany(
            "INSERT INTO event_times(event_id,year,month,day,sort_key,label,precision,origin) VALUES (?,?,?,?,?,?,?,?)",
            [(item.event_id, item.time.year, item.time.month, None if item.time.hide_day else item.time.day,
              item.key, item.time.label, item.time.precision, item.origin) for item in times.values()])
        db.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('calendar_source',?)", (source,))
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise
