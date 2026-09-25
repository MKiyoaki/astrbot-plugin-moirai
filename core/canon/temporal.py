"""Evidence-backed timeline facts and partial-order resolution for canon."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

PREDICATES = frozenset(("location", "custody", "affiliation", "life_status"))
FACT_PROMPT_VERSION = "canon-facts-v2"


@dataclass(frozen=True)
class FactDecision:
    status: str
    facts: tuple[dict, ...]
    as_of: str | None
    reason: str


def _rows(db: sqlite3.Connection, sql: str, params=()) -> list[dict]:
    return [dict(row) for row in db.execute(sql, params)]


def _require_evidence(db: sqlite3.Connection, event_id: str, line_key: str) -> None:
    row = db.execute(
        "SELECT 1 FROM events e JOIN lines l ON l.scene_key=e.scene_key "
        "WHERE e.event_id=? AND l.line_key=?", (event_id, line_key)
    ).fetchone()
    if row is None:
        raise ValueError(f"事件与证据行不属于同一场景：{event_id} / {line_key}")


def _reachable(edges: dict[str, set[str]], earlier: str, later: str) -> bool:
    seen = set()
    pending = [earlier]
    while pending:
        node = pending.pop()
        if node == later:
            return True
        if node in seen:
            continue
        seen.add(node)
        pending.extend(edges.get(node, ()))
    return False


def _order(db: sqlite3.Connection) -> dict[str, set[str]]:
    edges: dict[str, set[str]] = {}
    for earlier, later in db.execute("SELECT earlier,later FROM timeline_before"):
        edges.setdefault(earlier, set()).add(later)
    return edges


def apply_reviewed_facts(db: sqlite3.Connection, payload: dict) -> None:
    """Import an explicitly reviewed fact bundle atomically after checking provenance."""
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("BEGIN IMMEDIATE")
    try:
        for item in payload.get("points", []):
            line = item.get("line_key")
            if line:
                row = db.execute("SELECT scene_key FROM lines WHERE line_key=?", (line,)).fetchone()
                if row is None or row[0] != item["scene_key"]:
                    raise ValueError(f"时间点证据行不属于场景：{item['point_id']}")
            db.execute(
                "INSERT INTO timeline_points VALUES (?,?,?,?,?,?)",
                (item["point_id"], item["timeline_id"], item["scene_key"], line,
                 item["label"], item["precision"])
            )
        for item in payload.get("before", []):
            _require_evidence(db, item["event_id"], item["line_key"])
            db.execute(
                "INSERT INTO timeline_before VALUES (?,?,?,?)",
                (item["earlier"], item["later"], item["event_id"], item["line_key"])
            )
        edges = _order(db)
        if any(_reachable(edges, later, earlier)
               for earlier, successors in edges.items() for later in successors):
            raise ValueError("时间先后关系出现环")
        for item in payload.get("facts", []):
            if item["predicate"] not in PREDICATES:
                raise ValueError(f"不支持的事实谓词：{item['predicate']}")
            if item.get("review_status") != "reviewed":
                raise ValueError("只有明确标记 reviewed 的事实才能导入")
            if item.get("source_type") != "explicit":
                raise ValueError("第一阶段只接受人工核实的原文明示事实")
            if type(item.get("polarity", 1)) is not int or item.get("polarity", 1) not in (0, 1):
                raise ValueError("事实极性必须为 0 或 1")
            if not isinstance(item.get("subject"), str) or not item["subject"].strip():
                raise ValueError("事实缺少主体")
            if not isinstance(item.get("object"), str) or not item["object"].strip():
                raise ValueError("事实缺少客体")
            endpoint = item.get("end_point_id")
            if endpoint and not _reachable(edges, item["point_id"], endpoint):
                raise ValueError("事实结束点须晚于起点，并有时间证据链")
            evidence = item.get("evidence") or []
            if not any(e.get("relation") == "supports" for e in evidence):
                raise ValueError(f"事实缺少支持证据：{item['fact_id']}")
            db.execute(
                "INSERT INTO facts VALUES (?,?,?,?,?,?,?,?,?,?)",
                (item["fact_id"], item["subject"], item["predicate"], item["object"],
                 int(item.get("polarity", 1)), item["point_id"], item.get("end_point_id"),
                 item["persistence"], item["source_type"], item["review_status"])
            )
            for ev in evidence:
                _require_evidence(db, ev["event_id"], ev["line_key"])
                db.execute(
                    "INSERT INTO fact_evidence VALUES (?,?,?,?)",
                    (item["fact_id"], ev["event_id"], ev["line_key"], ev["relation"])
                )
        points = dict(db.execute("SELECT point_id,timeline_id FROM timeline_points"))
        facts = {r["fact_id"]: r for r in _rows(db, "SELECT * FROM facts")}
        for item in payload.get("transitions", []):
            old, new = facts[item["earlier_fact_id"]], facts[item["later_fact_id"]]
            if old["subject"] != new["subject"] or old["predicate"] != new["predicate"]:
                raise ValueError("状态变更必须涉及同一主体与谓词")
            if item["relation"] == "supersedes" and not _reachable(
                    edges, old["point_id"], new["point_id"]):
                raise ValueError("覆盖旧事实需要有证据的时间先后关系")
            _require_evidence(db, item["event_id"], item["line_key"])
            linked = db.execute(
                "SELECT 1 FROM fact_evidence WHERE fact_id=? AND event_id=? AND line_key=?",
                (new["fact_id"], item["event_id"], item["line_key"])
            ).fetchone()
            if linked is None:
                raise ValueError("状态变更证据必须链接到后续事实")
            db.execute(
                "INSERT INTO fact_transitions VALUES (?,?,?,?,?)",
                (old["fact_id"], new["fact_id"], item["relation"],
                 item["event_id"], item["line_key"])
            )
        for item in payload.get("coverage", []):
            anchor = item.get("current_anchor_id")
            if anchor and points.get(anchor) != item["timeline_id"]:
                raise ValueError("覆盖锚点不属于所声明的时间线")
            db.execute(
                "INSERT OR REPLACE INTO fact_coverage VALUES (?,?,?,?,?)",
                (item["timeline_id"], item["scene_scope"], item["fact_scope"],
                 anchor, item.get("note", ""))
            )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def resolve(db: sqlite3.Connection, subject: str, predicate: str,
            *, as_of: str | None = None, character: str = "amiya") -> FactDecision:
    """Resolve reviewed facts using only documented ordering and coverage."""
    if predicate not in PREDICATES:
        raise ValueError(f"不支持的事实谓词：{predicate}")
    rows = _rows(
        db, "SELECT f.*,p.timeline_id,p.label AS point_label,s.anchor "
        "FROM facts f JOIN timeline_points p ON p.point_id=f.point_id "
        "JOIN scenes s ON s.scene_key=p.scene_key "
        "WHERE f.subject=? AND f.predicate=? AND f.review_status='reviewed'",
        (subject, predicate)
    )
    if not rows:
        return FactDecision("unknown_current" if as_of is None else "unknown", (), as_of, "没有已审阅事实")
    for row in rows:
        row["evidence"] = _rows(
            db, "SELECT fe.event_id,fe.line_key,fe.relation,l.text,s.anchor,v.channel "
            "FROM fact_evidence fe JOIN lines l ON l.line_key=fe.line_key "
            "JOIN events e ON e.event_id=fe.event_id "
            "JOIN scenes s ON s.scene_key=e.scene_key "
            "LEFT JOIN views v ON v.event_id=e.event_id AND v.character=? "
            "WHERE fe.fact_id=? ORDER BY fe.event_id,fe.line_key",
            (character, row["fact_id"])
        )
        row["transitions"] = _rows(
            db, "SELECT earlier_fact_id,relation,evidence_event_id,evidence_line_key "
            "FROM fact_transitions WHERE later_fact_id=?", (row["fact_id"],)
        )
    edges = _order(db)
    if as_of is None:
        timelines = {row["timeline_id"] for row in rows}
        if len(timelines) != 1:
            return FactDecision("incomparable", tuple(rows), None, "事实分属未锚定的时间线")
        coverage = db.execute(
            "SELECT scene_scope,fact_scope,current_anchor_id FROM fact_coverage "
            "WHERE timeline_id=?", (next(iter(timelines)),)
        ).fetchone()
        if not coverage or coverage[0] != "continuous" or coverage[1] != "reviewed" or not coverage[2]:
            return FactDecision("unknown_current", tuple(rows), None, "导入场景或事实审阅覆盖不足")
        as_of = coverage[2]
    if db.execute("SELECT 1 FROM timeline_points WHERE point_id=?", (as_of,)).fetchone() is None:
        raise ValueError(f"未知的世界时间点：{as_of}")
    eligible = [row for row in rows if row["point_id"] == as_of or
                _reachable(edges, row["point_id"], as_of)]
    incomparable = [
        row for row in rows
        if row["point_id"] != as_of
        and not _reachable(edges, row["point_id"], as_of)
        and not _reachable(edges, as_of, row["point_id"])
    ]
    if incomparable:
        return FactDecision("incomparable", tuple(rows), as_of, "同一状态有不可比较时间线上的证据")
    if not eligible:
        return FactDecision("unknown", (), as_of, "查询点之前没有可用事实")
    transitions = _rows(
        db, "SELECT earlier_fact_id,later_fact_id FROM fact_transitions "
        "WHERE relation='supersedes'"
    )
    active = [
        row for row in eligible
        if (row["persistence"] != "point" or row["point_id"] == as_of)
        and not (row["end_point_id"] and (
            row["end_point_id"] == as_of or _reachable(edges, row["end_point_id"], as_of)))
        and not any(t["earlier_fact_id"] == row["fact_id"] and
                    any(new["fact_id"] == t["later_fact_id"] for new in eligible)
                    for t in transitions)
    ]
    if not active:
        if any(row["persistence"] == "point" and row["point_id"] != as_of for row in eligible):
            return FactDecision("last_known", tuple(eligible), as_of, "仅有过去某点的观察，不能延续到查询点")
        return FactDecision("superseded", tuple(eligible), as_of, "旧事实已有结束点或后续变更")
    if len({(row["object"], row["polarity"]) for row in active}) > 1:
        return FactDecision("conflicted", tuple(active), as_of, "相互冲突的事实没有可靠变更关系")
    if all(row["point_id"] != as_of and row["persistence"] == "until_changed" for row in active):
        coverage = db.execute(
            "SELECT scene_scope,fact_scope,current_anchor_id FROM fact_coverage WHERE timeline_id=?",
            (active[0]["timeline_id"],)
        ).fetchone()
        if not coverage or coverage[0] != "continuous" or coverage[1] != "reviewed" or not (
                coverage[2] == as_of or _reachable(edges, as_of, coverage[2])):
            return FactDecision("last_known", tuple(active), as_of, "没有足够覆盖证明旧状态一直持续")
    return FactDecision("as_of_valid", tuple(active), as_of, "截至指定剧情时间点有已审阅证据")
