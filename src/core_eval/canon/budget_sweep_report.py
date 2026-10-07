"""Aggregate a budget-sweep JSONL into per-budget accuracy, latency and evidence-token summaries."""
from __future__ import annotations

import argparse
import json
import random
import statistics
from pathlib import Path

GROUPS = {
    "全部": None,
    "事实与细节": {"fact", "detail"},
    "综述": {"overview"},
    "对抗与闲聊": {"past_absence", "false_premise", "report_only", "smalltalk"},
}


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = int(position), min(int(position) + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def bootstrap(values: list[float], rounds: int = 2000, seed: int = 7) -> tuple[float, float] | tuple[None, None]:
    if not values:
        return None, None
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(values, k=len(values))) for _ in range(rounds))
    return means[int(rounds * 0.025)], means[int(rounds * 0.975) - 1]


def summarize(rows: list[dict]) -> dict:
    budgets = sorted({row["budget"] for row in rows})
    out = {"budgets": budgets, "groups": {}, "n_rows": len(rows),
           "questions": len({row["id"] for row in rows})}
    for name, kinds in GROUPS.items():
        series = []
        for budget in budgets:
            chosen = [row for row in rows if row["budget"] == budget and row.get("score") is not None
                      and (kinds is None or row["kind"] in kinds)]
            scores = [row["score"] / 2 for row in chosen]
            low, high = bootstrap(scores)
            seconds = [row["seconds"] for row in chosen]
            series.append({
                "budget": budget, "n": len(chosen),
                "accuracy": round(statistics.fmean(scores), 4) if scores else None,
                "ci_low": round(low, 4) if low is not None else None,
                "ci_high": round(high, 4) if high is not None else None,
                "full_marks": round(sum(row["score"] == 2 for row in chosen) / len(chosen), 4) if chosen else None,
                "hallucinated": round(sum(bool(row.get("hallucinated", row.get("fabricated"))) for row in chosen) / len(chosen), 4) if chosen else None,
                "unsupported": round(sum(bool(row.get("unsupported")) for row in chosen) / len(chosen), 4) if chosen else None,
                "recalls_mean": round(statistics.fmean(sum(e["tool"] == "canon_recall" for e in row.get("recalls", [])) for row in chosen), 2) if chosen else None,
                "latency_median": round(quantile(seconds, 0.5), 3) if seconds else None,
                "latency_p90": round(quantile(seconds, 0.9), 3) if seconds else None,
                "tokens_mean": round(statistics.fmean(row["evidence_tokens"] for row in chosen), 1) if chosen else None,
                "tokens_p90": round(quantile([row["evidence_tokens"] for row in chosen], 0.9), 1) if chosen else None,
                "calls_mean": round(statistics.fmean(row["calls"] or 0 for row in chosen), 2) if chosen else None,
                "recall_rate": round(sum("不召回" not in (row.get("tier") or "") for row in chosen) / len(chosen), 4) if chosen else None,
                "deep_rate": round(sum("深度" in (row.get("tier") or "") for row in chosen) / len(chosen), 4) if chosen else None,
            })
        out["groups"][name] = series
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    rows = [json.loads(line) for line in args.results.read_text(encoding="utf-8").splitlines() if line.strip()]
    summary = summarize(rows)
    text = json.dumps(summary, ensure_ascii=False, indent=1)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    for row in summary["groups"]["全部"]:
        print(f"{row['budget']:>5} n={row['n']:>2} acc={row['accuracy']} [{row['ci_low']},{row['ci_high']}] "
              f"halluc={row['hallucinated']} unsup={row['unsupported']} recalls={row['recalls_mean']} lat={row['latency_median']}/{row['latency_p90']}s "
              f"tok={row['tokens_mean']} calls={row['calls_mean']} recall={row['recall_rate']} deep={row['deep_rate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
