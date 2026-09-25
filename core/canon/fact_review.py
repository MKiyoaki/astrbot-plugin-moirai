"""Build reviewable temporal fact packets without promoting model suggestions to truth."""
from __future__ import annotations

import hashlib
from collections import defaultdict


def _id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return prefix + hashlib.sha256(payload).hexdigest()[:24]


def build_review_bundle(db, results: list[dict]) -> dict:
    """Create stable IDs and group conflicting claims for full-library review."""
    points = {}
    facts = {}
    groups = defaultdict(list)
    event_ids = {fact["event_id"] for result in results for fact in result["facts"]}
    events = {}
    for event_id in event_ids:
        row = db.execute(
            "SELECT e.event_id,e.in_world_time,s.scene_key,s.anchor,s.collection_id "
            "FROM events e JOIN scenes s ON s.scene_key=e.scene_key WHERE e.event_id=?",
            (event_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"事实证据事件已失效：{event_id}")
        events[event_id] = dict(row)
    for result in results:
        for claim in result["facts"]:
            event = events[claim["event_id"]]
            if event["scene_key"] != result["scene_key"]:
                raise ValueError(f"事实证据不属于声明场景：{claim['event_id']}")
            point_id = _id("p_", claim["event_id"])
            timeline = ("collection:" + event["collection_id"]
                        if event["in_world_time"] == "present" and event["collection_id"]
                        else "unanchored:" + claim["event_id"])
            points[point_id] = {
                "point_id": point_id, "timeline_id": timeline,
                "scene_key": event["scene_key"], "line_key": None,
                "label": event["anchor"] + " · " + event["in_world_time"],
                "precision": "scene",
            }
            fact_id = _id("f_", event["scene_key"], claim["event_id"], claim["line_key"],
                          claim["subject"], claim["predicate"], claim["object"], str(claim["polarity"]))
            facts[fact_id] = {
                "fact_id": fact_id, "subject": claim["subject"], "predicate": claim["predicate"],
                "object": claim["object"], "polarity": claim["polarity"],
                "point_id": point_id, "persistence": "point", "source_type": "suggested",
                "review_status": "candidate", "evidence": [
                    {"event_id": claim["event_id"], "line_key": claim["line_key"], "relation": "supports"}
                ],
            }
            groups[(claim["subject"], claim["predicate"])].append(fact_id)
    review_groups = []
    for (subject, predicate), ids in sorted(groups.items()):
        objects = {facts[i]["object"] for i in ids}
        if len(objects) > 1 or len(ids) > 1:
            review_groups.append({"subject": subject, "predicate": predicate,
                                  "objects": sorted(objects), "fact_ids": ids,
                                  "needs_timeline_review": len(objects) > 1})
    return {"format": "canon-fact-review-v1", "points": list(points.values()),
            "before": [], "facts": list(facts.values()), "transitions": [], "coverage": [],
            "review_groups": review_groups,
            "instructions": "逐条核对原文。只有明确证据才改 source_type=explicit、review_status=reviewed；"
                            "跨场景先后与状态变更须另填 before/transitions 及其证据。"
                            "未审阅候选不会写入可查询事实；coverage 不会自动标记完整。"}


def approved_payload(bundle: dict) -> dict:
    """Select explicit approvals and the points they reference."""
    if bundle.get("format") != "canon-fact-review-v1":
        raise ValueError("不是 canon-fact-review-v1 审阅包")
    facts = [f for f in bundle["facts"] if f.get("review_status") == "reviewed"]
    if not facts:
        raise ValueError("没有标记 reviewed 的事实")
    used = {f["point_id"] for f in facts}
    used.update(f.get("end_point_id") for f in facts if f.get("end_point_id"))
    before = [b for b in bundle["before"] if b.get("review_status") == "reviewed"]
    for edge in before:
        used.update((edge["earlier"], edge["later"]))
    coverage = [c for c in bundle["coverage"] if c.get("review_status") == "reviewed"]
    used.update(c.get("current_anchor_id") for c in coverage if c.get("current_anchor_id"))
    points = [p for p in bundle["points"] if p["point_id"] in used]
    transitions = [t for t in bundle["transitions"] if t.get("review_status") == "reviewed"]
    fact_ids = {f["fact_id"] for f in facts}
    for transition in transitions:
        if transition["earlier_fact_id"] not in fact_ids or transition["later_fact_id"] not in fact_ids:
            raise ValueError("已审阅变更引用了未批准事实")
    if len(points) != len(used):
        raise ValueError("审阅包缺少已批准事实引用的时间点")
    return {"points": points, "before": before, "facts": facts,
            "transitions": transitions, "coverage": coverage}
