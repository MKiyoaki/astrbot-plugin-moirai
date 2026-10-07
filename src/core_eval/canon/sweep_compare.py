"""Paired comparison of budget-sweep runs: per-question score deltas, bootstrap CI, hallucination and latency split.

usage: python sweep_compare.py BASE.judged.jsonl NEW.judged.jsonl [MORE.judged.jsonl ...] [--budget 2000] [--kinds fact,detail]
The first file is the baseline; every later file is compared with it on the questions both graded.
"""
import argparse
import json
import random
import statistics
from pathlib import Path

GROUPS = {"全部": None, "事实与细节": {"fact", "detail"}, "综述": {"overview"},
          "对抗与闲聊": {"past_absence", "false_premise", "report_only", "smalltalk"}, "近期": {"recent"}, "跨章节因果": {"cross"}}


def load(path, budget):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["id"]: row for row in rows if row["budget"] == budget and row.get("score") is not None}


def quantile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def paired_ci(diffs, rounds=4000, seed=7):
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(rounds))
    return means[int(rounds * 0.025)], means[int(rounds * 0.975) - 1]


def side(rows):
    seconds = [row["seconds"] for row in rows]
    flagged = [row["seconds"] for row in rows if row.get("problems")]
    clean = [row["seconds"] for row in rows if not row.get("problems")]
    return {
        "n": len(rows),
        "acc": statistics.fmean(row["score"] / 2 for row in rows),
        "full": sum(row["score"] == 2 for row in rows) / len(rows),
        "zero": sum(row["score"] == 0 for row in rows) / len(rows),
        "hall": sum(bool(row.get("hallucinated")) for row in rows) / len(rows),
        "unsup": sum(bool(row.get("unsupported")) for row in rows) / len(rows),
        "prompt_sum": sum(row.get("prompt_tokens") or 0 for row in rows),
        "compl_sum": sum(row.get("completion_tokens") or 0 for row in rows),
        "total_mean": statistics.fmean((row.get("prompt_tokens") or 0) + (row.get("completion_tokens") or 0) for row in rows),
        "total_med": statistics.median((row.get("prompt_tokens") or 0) + (row.get("completion_tokens") or 0) for row in rows),
        "total_p90": quantile([(row.get("prompt_tokens") or 0) + (row.get("completion_tokens") or 0) for row in rows], 0.9),
        "total_max": max((row.get("prompt_tokens") or 0) + (row.get("completion_tokens") or 0) for row in rows),
        "flagged": len(flagged),
        "tok": statistics.fmean(row["evidence_tokens"] for row in rows),
        "tok_max": max(row["evidence_tokens"] for row in rows),
        "order_bad": sum(row.get("order_ok") is False for row in rows),
        "calls": statistics.fmean(row["calls"] or 0 for row in rows),
        "prompt": statistics.fmean(row.get("prompt_tokens") or 0 for row in rows),
        "compl": statistics.fmean(row.get("completion_tokens") or 0 for row in rows),
    }


def fmt(value, spec=".3f"):
    return "-" if value is None else format(value, spec)


def compare(name, base, new, ids, kinds):
    ids = [i for i in ids if kinds is None or base[i]["kind"] in kinds]
    if not ids:
        return
    a, b = side([base[i] for i in ids]), side([new[i] for i in ids])
    diffs = [(new[i]["score"] - base[i]["score"]) / 2 for i in ids]
    low, high = paired_ci(diffs) if len(diffs) > 1 else (None, None)
    print(f"\n### {name}  (n={len(ids)})")
    print("| 指标 | 基线 | 新版 | 差 |\n|---|---|---|---|")
    for label, key, spec in (("准确度(0-1)", "acc", ".3f"), ("满分率", "full", ".2f"), ("零分率", "zero", ".2f"),
                             ("幻觉率", "hall", ".3f"), ("含无依据说法", "unsup", ".2f"),
                             ("输入 token 合计", "prompt_sum", ",.0f"), ("输出 token 合计", "compl_sum", ",.0f"),
                             ("每题 token 均值(输入+输出)", "total_mean", ",.0f"), ("每题 token 中位", "total_med", ",.0f"),
                             ("每题 token p90", "total_p90", ",.0f"), ("单题 token 最大", "total_max", ",.0f"),
                             ("有问题的轮数", "flagged", ".0f"), ("证据 token 均值", "tok", ".0f"), ("证据 token 最大值", "tok_max", ".0f"), ("先后被判颠倒的题数", "order_bad", ".0f"),
                             ("模型调用均值", "calls", ".2f"), ("prompt token 均值", "prompt", ".0f"),
                             ("completion token 均值", "compl", ".0f")):
        x, y = a[key], b[key]
        print(f"| {label} | {fmt(x, spec)} | {fmt(y, spec)} | {fmt(None if x is None or y is None else y - x, '+' + spec)} |")
    better = sum(d > 0 for d in diffs)
    worse = sum(d < 0 for d in diffs)
    print(f"\n配对准确度差 {statistics.fmean(diffs):+.3f}，95% CI [{fmt(low)}, {fmt(high)}]；变好 {better} 题，变差 {worse} 题，持平 {len(diffs) - better - worse} 题")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--budget", type=int, default=2000)
    parser.add_argument("--changed", action="store_true", help="list every question whose score changed")
    args = parser.parse_args()
    runs = [(path.name, load(path, args.budget)) for path in args.files]
    base_name, base = runs[0]
    for new_name, new in runs[1:]:
        ids = sorted(set(base) & set(new))
        print(f"\n## {base_name} → {new_name}  @ budget {args.budget}；两边都有评分的题 {len(ids)} 道"
              f"（基线独有 {len(set(base) - set(new))}，新版独有 {len(set(new) - set(base))}）")
        for name, kinds in GROUPS.items():
            compare(name, base, new, ids, kinds)
        moved = [i for i in ids if new[i]["score"] != base[i]["score"]]
        print(f"\n### 分数变动的题（{len(moved)}）")
        for i in moved:
            print(f"- {i} [{base[i]['kind']}] {base[i]['score']}→{new[i]['score']}"
                  f"  幻觉 {bool(base[i].get('hallucinated'))}→{bool(new[i].get('hallucinated'))}"
                  f"  路线 {base[i].get('tier')}→{new[i].get('tier')}  {new[i]['question'][:36]}")
            if args.changed:
                print(f"    新版评语：{new[i].get('reason', '')}")


if __name__ == "__main__":
    main()
