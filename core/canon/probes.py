"""canon 抽取的金标准探针：人工审定的"必须抽到"和"不能越界"条目，确定性地评估召回、渠道和边界。

分两组统计再合成一个分数，借鉴 ReverieMem（arXiv 2606.25632）的知识边界评测：覆盖组对应"她该记住的事记住没有"，
边界组对应"不该有的东西混进来没有"；合成分数用样本加权的调和平均，任何一组崩掉都会拉低总分。
覆盖组的召回按重要度加权（arXiv 2604.03141）。失败按原因分类（未抽出 / 渠道错误 / 被合并 / 越界 / 场景失败），
参照 arXiv 2602.10881 的结构化抽取失败分类和 arXiv 2605.30771 按阶段归因的做法。
探针只引用 scene_key 和 line_key，line_key 不在场景里（上游改过）的探针记为过期，不参与统计。
命中只看精确引用的行（audit.cited_lines）：v3 的事件证据可能是整段情节的行区间，拿它算命中几乎总能覆盖锚点。
事件管的整段（事件证据加精确引用）只用来判断几条探针是否被并进了同一个事件。
"""
from __future__ import annotations

import collections
import json
import math
from pathlib import Path

from .audit import cited_lines, output_texts

KINDS = ("cover", "absent", "no_episode", "not_evidence", "not_mention")
COVER_SHARE = 0.5
PASS = "通过"
COVERED = (PASS, "渠道错误", "被合并")
UNCITED = "范围内未引用"


def load_probes(path: Path | str) -> list[dict]:
    """读取探针文件（JSONL，空行和 # 开头的行忽略），格式有错就报出行号。"""
    probes, seen = [], set()
    for no, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            probe = json.loads(raw)
        except ValueError as exc:
            raise ValueError(f"探针文件第 {no} 行不是合法的 JSON：{exc}") from exc
        kind = probe.get("kind")
        if kind not in KINDS or not probe.get("id") or not probe.get("scene"):
            raise ValueError(f"探针文件第 {no} 行：需要 id、scene，kind 只能是 {'/'.join(KINDS)}")
        if probe["id"] in seen:
            raise ValueError(f"探针文件第 {no} 行：id {probe['id']} 重复")
        if kind in ("cover", "not_evidence") and not probe.get("anchors"):
            raise ValueError(f"探针文件第 {no} 行：{kind} 需要 anchors（line_key 数组）")
        if kind == "not_mention" and not probe.get("text"):
            raise ValueError(f"探针文件第 {no} 行：not_mention 需要 text")
        seen.add(probe["id"])
        probes.append(probe)
    return probes


def _cited(result: dict) -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    """返回每个事件精确引用的行和它管的整段。"""
    views = {v["event"]: v for v in result["views"]}
    precise = {ev["id"]: cited_lines(ev, views.get(ev["id"])) for ev in result["events"]}
    span = {ev["id"]: {int(r[1:]) for r in ev["evidence"]} | precise[ev["id"]] for ev in result["events"]}
    return precise, span


def _need(anchors: list[int]) -> int:
    return max(1, math.ceil(len(anchors) * COVER_SHARE))


def _best(cited: dict[str, set[int]], anchors: list[int]) -> tuple[str | None, int]:
    best, hits = None, 0
    for eid, lines in cited.items():
        n = len(lines & set(anchors))
        if n > hits:
            best, hits = eid, n
    return best, hits


def evaluate_probes(probes: list[dict], scenes: dict[str, dict], results: dict[str, dict | None]) -> dict:
    """用探针评估一次运行。scenes 是 story_pack 的场景，results 是各场景的抽取结果（失败为 None）。

    只统计本次运行涉及的场景；一个覆盖探针算"覆盖"，要求某个事件精确引用的行（beats、视角证据，没有 beats 时是事件证据）
    命中至少一半锚点。锚点只落在某个事件的整段里、没被精确引用时记为"范围内未引用"，不算覆盖。
    """
    resolved = []
    skipped = stale = 0
    for probe in probes:
        if probe["scene"] not in results:
            skipped += 1
            continue
        index = {ln["k"]: i for i, ln in enumerate(scenes[probe["scene"]]["lines"], 1)}
        anchors = [index.get(k) for k in probe.get("anchors") or []]
        if None in anchors:
            stale += 1
            continue
        resolved.append((probe, anchors))
    covers = collections.defaultdict(list)
    for probe, anchors in resolved:
        if probe["kind"] == "cover":
            covers[probe["scene"]].append((probe, anchors))

    items = []
    for probe, anchors in resolved:
        result = results[probe["scene"]]
        item = {"id": probe["id"], "scene": probe["scene"], "kind": probe["kind"],
                "importance": probe.get("importance", 1), "status": probe.get("status", ""), "note": probe.get("note", ""),
                "event": None, "channel": None, "detail": ""}
        if result is None:
            item["outcome"] = "场景失败"
        elif probe["kind"] == "cover":
            precise, span = _cited(result)
            best, hits = _best(precise, anchors)
            home = best if hits >= _need(anchors) else None
            if home is None:
                in_span, span_hits = _best(span, anchors)
                home = in_span if span_hits >= _need(anchors) else None
            channel = {v["event"]: v["channel"] for v in result["views"]}.get(home or best)
            item.update(event=home or best, channel=channel, detail=f"命中 {hits}/{len(anchors)} 个锚点")
            allowed = set(probe.get("channels") or [])
            rivals = [p["id"] for p, a in covers[probe["scene"]]
                      if p["id"] != probe["id"] and home and len(span[home] & set(a)) >= _need(a)
                      and allowed and set(p.get("channels") or []) and not allowed & set(p["channels"])]
            if home is None:
                item["outcome"] = "未抽出"
            elif rivals:
                item["outcome"] = "被合并"
                item["detail"] += f"；同一事件还覆盖了 {'、'.join(rivals)}"
                if hits < _need(anchors):
                    item["detail"] += "（锚点只在范围里，beats 和视角证据没有引用）"
            elif hits < _need(anchors):
                item["outcome"] = UNCITED
                item["detail"] += f"；锚点在 {home} 的范围里，但 beats 和视角证据没有引用"
            elif allowed and channel not in allowed:
                item["outcome"] = "渠道错误"
                item["detail"] += f"；应为 {'/'.join(sorted(allowed))}"
            else:
                item["outcome"] = PASS
        else:
            item["outcome"], item["detail"] = _boundary(probe, anchors, result)
        item["ok"] = item["outcome"] == PASS
        items.append(item)
    return _score(items, skipped=skipped, stale=stale)


def _boundary(probe: dict, anchors: list[int], result: dict) -> tuple[str, str]:
    kind = probe["kind"]
    if kind == "absent":
        bad = [f"{v['event']}={v['channel']}" for v in result["views"] if v["channel"] != "unstated"]
        if result.get("episode"):
            bad.append("写了 episode")
        return ("越界", "；".join(bad)) if bad else (PASS, "")
    if kind == "no_episode":
        return ("越界", "写了 episode") if result.get("episode") else (PASS, "")
    if kind == "not_evidence":
        used = sorted({n for v in result["views"] for n in (int(r[1:]) for r in v.get("evidence") or [])} & set(anchors))
        return ("越界", "视角证据用了 " + "、".join(f"L{n}" for n in used)) if used else (PASS, "")
    hits = [field for field, text in output_texts(result, with_names=True) if probe["text"] in text]
    return ("越界", f"出现在 {'、'.join(hits)}") if hits else (PASS, "")


def _score(items: list[dict], *, skipped: int, stale: int) -> dict:
    cover = [i for i in items if i["kind"] == "cover"]
    bound = [i for i in items if i["kind"] != "cover"]
    weight = sum(i["importance"] for i in cover)

    def ratio(num, den):
        return round(num / den, 3) if den else None

    covered = [i for i in cover if i["outcome"] in COVERED]
    passed_cover = sum(i["ok"] for i in cover)
    passed_bound = sum(i["ok"] for i in bound)
    acc_c, acc_b = ratio(passed_cover, len(cover)), ratio(passed_bound, len(bound))
    if acc_c is None or acc_b is None:
        kbf = acc_c if acc_b is None else acc_b
    elif acc_c == 0 or acc_b == 0:
        kbf = 0.0
    else:
        kbf = round((len(cover) + len(bound)) / (len(cover) / acc_c + len(bound) / acc_b), 3)
    return {
        "probes": len(items), "cover_probes": len(cover), "boundary_probes": len(bound),
        "skipped": skipped, "stale": stale, "draft": sum(1 for i in items if i["status"] == "draft"),
        "weighted_coverage": ratio(sum(i["importance"] for i in covered), weight),
        "weighted_recall": ratio(sum(i["importance"] for i in cover if i["ok"]), weight),
        "channel_accuracy": ratio(sum(i["ok"] for i in covered), len(covered)),
        "cover_accuracy": acc_c, "boundary_accuracy": acc_b, "kbf": kbf,
        "failures": dict(collections.Counter(i["outcome"] for i in items if not i["ok"]).most_common()),
        "items": items,
    }
