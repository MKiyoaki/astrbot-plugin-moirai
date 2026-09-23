"""canon 抽取结果之间的对比：按证据行对齐事件，统计事件 F1 与获知渠道的一致性（Cohen's κ）。

对齐借鉴结构化抽取评测里的元组级 P/R/F1（arXiv 2602.10881），匹配依据换成证据行集合的重合系数
（交集除以较小的集合）。v1、v2 的事件证据是挑出的十来行关键行，v3 可能写成整段情节的行区间；同一件事在两边
Jaccard 很低（10 行对 70 行只有 0.14），重合系数仍是 1。阈值 0.5，即较小的一方至少一半的证据行落在对方里。一个事件被拆成几段或几段被并成一个时，
一对一配对只配上一段，其余记为只在一方出现，F1 照样反映粒度差异。
一致性报告机会校正的 κ 而不只是原始一致率（arXiv 2606.19544）。同一配置多次运行之间的对比就是重测信度，
不同 prompt 版本或模型之间的对比给出逐事件的变化。
"""
from __future__ import annotations

import collections
import itertools
import json
from pathlib import Path

MATCH_THRESHOLD = 0.5


def load_results(path: Path | str) -> dict[str, dict]:
    """读取一次运行的全部成功结果：基准运行目录、试跑目录（index.json + out/）或 canon.sqlite。"""
    from .bench import load_replay  # noqa: PLC0415
    return {key: json.loads(raw) for key, raw in load_replay(path).items()}


def _evidence(ev: dict) -> set[str]:
    return set(ev["evidence"])


def align(a: dict, b: dict, threshold: float = MATCH_THRESHOLD) -> tuple[list[tuple[dict, dict, float]], list, list]:
    """贪心地按证据行重合系数从高到低配对两份结果里的事件，低于阈值的不配对；重合系数相同时先配 Jaccard 高的。"""
    candidates = []
    for ea in a["events"]:
        for eb in b["events"]:
            sa, sb = _evidence(ea), _evidence(eb)
            if not sa or not sb:
                continue
            shared = len(sa & sb)
            overlap = shared / min(len(sa), len(sb))
            if overlap >= threshold:
                candidates.append((overlap, shared / len(sa | sb), ea["id"], eb["id"]))
    used_a, used_b, pairs = set(), set(), []
    by_a = {e["id"]: e for e in a["events"]}
    by_b = {e["id"]: e for e in b["events"]}
    for overlap, _, ia, ib in sorted(candidates, key=lambda c: (-c[0], -c[1], c[2], c[3])):
        if ia not in used_a and ib not in used_b:
            used_a.add(ia)
            used_b.add(ib)
            pairs.append((by_a[ia], by_b[ib], round(overlap, 3)))
    return (pairs, [e for e in a["events"] if e["id"] not in used_a],
            [e for e in b["events"] if e["id"] not in used_b])


def cohen_kappa(labels: list[tuple[str, str]]) -> float | None:
    """两位标注者（两次运行）在同一批条目上的 Cohen's κ。只有一种标签且完全一致时记为 1。"""
    if not labels:
        return None
    n = len(labels)
    po = sum(x == y for x, y in labels) / n
    ca = collections.Counter(x for x, _ in labels)
    cb = collections.Counter(y for _, y in labels)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return round((po - pe) / (1 - pe), 3)


def _channels(result: dict) -> dict[str, str]:
    return {v["event"]: v["channel"] for v in result["views"]}


def compare_results(a: dict[str, dict], b: dict[str, dict]) -> dict:
    """对比两次运行在共同场景上的结果：事件 F1、渠道一致率和 κ、渠道变化和新增/丢失的事件。"""
    scenes = sorted(set(a) & set(b))
    total_a = total_b = matched = 0
    labels, changes, only_a, only_b = [], [], [], []
    for key in scenes:
        pairs, rest_a, rest_b = align(a[key], b[key])
        ca, cb = _channels(a[key]), _channels(b[key])
        total_a += len(a[key]["events"])
        total_b += len(b[key]["events"])
        matched += len(pairs)
        for ea, eb, overlap in pairs:
            labels.append((ca.get(ea["id"]), cb.get(eb["id"])))
            if ca.get(ea["id"]) != cb.get(eb["id"]):
                changes.append({"scene": key, "a": ea["id"], "b": eb["id"], "topic_a": ea["topic"], "topic_b": eb["topic"],
                                "channel_a": ca.get(ea["id"]), "channel_b": cb.get(eb["id"]), "overlap": overlap})
        only_a += [{"scene": key, "event": e["id"], "topic": e["topic"], "channel": ca.get(e["id"])} for e in rest_a]
        only_b += [{"scene": key, "event": e["id"], "topic": e["topic"], "channel": cb.get(e["id"])} for e in rest_b]
    agree = sum(x == y for x, y in labels)
    return {
        "scenes": len(scenes), "events_a": total_a, "events_b": total_b, "matched": matched,
        "event_f1": round(2 * matched / (total_a + total_b), 3) if total_a + total_b else None,
        "channel_agreement": round(agree / len(labels), 3) if labels else None,
        "channel_kappa": cohen_kappa(labels),
        "channel_changes": changes, "only_a": only_a, "only_b": only_b,
    }


def stability(runs: list[dict[str, dict]]) -> dict:
    """同一配置多次运行的重测信度：两两对比后取平均和最小值。"""
    pairs = [compare_results(x, y) for x, y in itertools.combinations(runs, 2)]

    def stat(key):
        values = [p[key] for p in pairs if p[key] is not None]
        return {"mean": round(sum(values) / len(values), 3), "min": min(values)} if values else None

    return {"runs": len(runs), "pairs": len(pairs), "event_f1": stat("event_f1"),
            "channel_agreement": stat("channel_agreement"), "channel_kappa": stat("channel_kappa"),
            "events_per_run": [sum(len(r["events"]) for r in run.values()) for run in runs]}


def render_comparison(cmp: dict, name_a: str, name_b: str, limit: int = 40) -> list[str]:
    """两次运行对比的 Markdown 段落。"""
    out = [f"对比：A = {name_a}，B = {name_b}（共同场景 {cmp['scenes']} 个）", "",
           "| 指标 | 值 |", "|---|---|",
           f"| 事件数 A / B | {cmp['events_a']} / {cmp['events_b']} |",
           f"| 对齐的事件 | {cmp['matched']} |",
           f"| 事件 F1 | {cmp['event_f1']} |",
           f"| 渠道一致率 | {cmp['channel_agreement']} |",
           f"| 渠道 Cohen's κ | {cmp['channel_kappa']} |", ""]
    if cmp["channel_changes"]:
        out += ["渠道变化（A → B）：", ""]
        out += [f"- `{c['scene']}` {c['a']}「{c['topic_a']}」{c['channel_a']} → {c['b']}「{c['topic_b']}」{c['channel_b']}"
                for c in cmp["channel_changes"][:limit]]
        out.append("")
    for label, rows in (("只在 A 里的事件", cmp["only_a"]), ("只在 B 里的事件", cmp["only_b"])):
        if rows:
            out += [f"{label}（{len(rows)} 个）：", ""]
            out += [f"- `{r['scene']}` {r['event']}「{r['topic']}」{r['channel']}" for r in rows[:limit]]
            if len(rows) > limit:
                out.append(f"- ……另有 {len(rows) - limit} 个")
            out.append("")
    return out
