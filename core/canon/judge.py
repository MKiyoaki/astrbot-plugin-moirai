"""canon 抽取结果的可选 LLM 裁判：逐事件判断证据行能否支撑摘要、哪些证据行多余、视角证据能否支撑获知渠道。

指标沿用 ALCE（arXiv 2305.14627）的引证召回率和引证精确率，只是用 LLM 代替 NLI 模型：
召回率 = 证据完全支撑摘要的事件占比；精确率只在完全支撑的事件上计算，多余的证据行扣分。
按 arXiv 2606.19544 的建议，裁判温度设为 0，可以重复多次报告重测一致性（Cohen's κ），
也可以和人工标注对比 κ；裁判本身未经人工校准前，它的数字只能当参考。
裁判会把被引用的原文行发给裁判模型的接口，默认不运行。
"""
from __future__ import annotations

import asyncio
import collections
import itertools
import json

from .compare import cohen_kappa
from .extract import CHANNELS, Call, parse_output
from .prompt import SYSTEM_PROMPT, render_line

JUDGE_VERSION = "canon-judge-v1"
SUPPORT = ("none", "partial", "full")
FLAGGED_LIMIT = 80
CHANNEL_DEFS = "\n".join(ln.strip() for ln in SYSTEM_PROMPT.splitlines() if ln.strip().split(" ")[0] in CHANNELS)

JUDGE_SYSTEM = f"""你是剧情记忆抽取结果的审核员。输入是一个游戏剧情场景里被引用到的原文行，以及从这个场景抽取出的事件。逐个事件判断，只依据给出的原文行，不要使用任何外部知识。

对每个事件给出：
- support：只看这个事件自己的 evidence 行，summary 里的每一个说法是否都有依据。full = 全部有依据；partial = 有说法缺少依据或与原文不符；none = 基本没有依据。
- unsupported：缺少依据或与原文不符的说法，每条不超过 30 字；没有就是空数组。
- irrelevant：evidence 里和 summary 无关、删掉也不影响支撑的行号，例如 ["L12"]；没有就是空数组。
- channel_ok：只看 view_evidence 行，目标角色和这个事件的关系是否确实是给出的 channel。true 或 false。
- channel_note：channel_ok 为 false 时写应该是哪个渠道和理由，不超过 30 字；否则为空字符串。

渠道定义：
{CHANNEL_DEFS}

说明：{{DOCTOR}} 指玩家角色博士，"ta" 是指代博士的代词；显示名为"博士（选项）"的行是博士说的话。只有显示名在目标角色已确认名字里的台词才是她说的。

只输出 JSON：{{"events": [{{"id": "e1", "support": "full", "unsupported": [], "irrelevant": [], "channel_ok": true, "channel_note": ""}}]}}"""


def build_judge_prompt(scene: dict, result: dict, character: dict) -> str:
    """只列出被引用的原文行，事件按抽取顺序给出，保证同一输入得到同一 prompt。"""
    views = {v["event"]: v for v in result["views"]}
    refs = set()
    for ev in result["events"]:
        refs.update(int(r[1:]) for r in ev["evidence"])
        refs.update(int(r[1:]) for r in views.get(ev["id"], {}).get("evidence") or [])
    lines = scene["lines"]
    out = [f"[目标角色] {character['display']}（已确认显示名：{'、'.join(character['confirmed_names'])}）",
           f"[场景] {scene['anchor']}", "[原文行]"]
    out += [render_line(n, lines[n - 1]) for n in sorted(refs) if 1 <= n <= len(lines)]
    out.append("[事件]")
    for ev in result["events"]:
        view = views.get(ev["id"], {})
        out.append(json.dumps({"id": ev["id"], "topic": ev["topic"], "summary": ev["summary"], "evidence": ev["evidence"],
                               "channel": view.get("channel"), "view_evidence": view.get("evidence") or []},
                              ensure_ascii=False))
    return "\n".join(out)


def parse_verdicts(text: str, result: dict) -> dict[str, dict]:
    """解析裁判输出，按事件 id 返回规范化后的判断。缺事件或字段不合法就报错。"""
    obj = parse_output(text)
    items = obj.get("events") if isinstance(obj, dict) else None
    if not isinstance(items, list):
        raise ValueError("裁判输出缺少 events 数组")
    ids = [ev["id"] for ev in result["events"]]
    out = {}
    for item in items:
        if not isinstance(item, dict) or item.get("id") not in ids:
            continue
        support = item.get("support")
        if support not in SUPPORT or not isinstance(item.get("channel_ok"), bool):
            raise ValueError(f"事件 {item.get('id')} 的 support 或 channel_ok 不合法")
        out[item["id"]] = {
            "support": support,
            "unsupported": [str(x) for x in item.get("unsupported") or []],
            "irrelevant": sorted({str(x) for x in item.get("irrelevant") or []}),
            "channel_ok": item["channel_ok"],
            "channel_note": str(item.get("channel_note") or ""),
        }
    missing = [i for i in ids if i not in out]
    if missing:
        raise ValueError(f"裁判输出缺少事件 {missing}")
    return out


async def judge_scene(call: Call, scene: dict, result: dict, character: dict, *, repeats: int = 1,
                      timeout: float = 300) -> list[dict[str, dict]]:
    """对一个场景调用裁判 repeats 次，返回每次的判断。"""
    prompt = build_judge_prompt(scene, result, character)
    runs = []
    for _ in range(repeats):
        resp = await asyncio.wait_for(call(prompt, JUDGE_SYSTEM), timeout)
        runs.append(parse_verdicts(getattr(resp, "completion_text", "") or "", result))
    return runs


def majority(verdicts: list[dict]) -> dict:
    """多次判断合成一个：support 取众数，平票取更严的；channel_ok 过半才算 true。"""
    counts = collections.Counter(v["support"] for v in verdicts)
    top = max(counts.values())
    support = min((s for s, n in counts.items() if n == top), key=SUPPORT.index)
    ok = sum(v["channel_ok"] for v in verdicts) * 2 > len(verdicts)
    first = verdicts[0]
    return {"support": support, "channel_ok": ok, "unsupported": first["unsupported"],
            "irrelevant": first["irrelevant"], "channel_note": first["channel_note"]}


async def judge_run(call: Call, scenes: dict[str, dict], results: dict[str, dict], character: dict, *,
                    repeats: int = 1, concurrency: int = 2, timeout: float = 300,
                    progress=None) -> tuple[list[dict], dict[str, str]]:
    """对一次运行的全部成功场景做裁判，返回逐事件记录和失败的场景（场景 → 原因）。"""
    sem = asyncio.Semaphore(max(1, concurrency))
    records, failures = [], {}

    async def one(key: str) -> None:
        result = results[key]
        async with sem:
            try:
                runs = await judge_scene(call, scenes[key], result, character, repeats=repeats, timeout=timeout)
            except Exception as exc:
                failures[key] = f"{type(exc).__name__}: {exc}"
                if progress:
                    progress(key, "失败")
                return
        views = {v["event"]: v for v in result["views"]}
        for ev in result["events"]:
            verdicts = [run[ev["id"]] for run in runs]
            records.append({"scene": key, "event": ev["id"], "topic": ev["topic"], "evidence": len(ev["evidence"]),
                            "channel": views.get(ev["id"], {}).get("channel"), "runs": verdicts, **majority(verdicts)})
        if progress:
            progress(key, "ok")

    await asyncio.gather(*(one(k) for k in results))
    order = {k: i for i, k in enumerate(results)}
    records.sort(key=lambda r: (order[r["scene"]], r["event"]))
    return records, failures


def summarize_judge(records: list[dict], failures: dict[str, str], *, model: str, repeats: int,
                    labels: dict[tuple[str, str], dict] | None = None) -> dict:
    """ALCE 式的引证召回率 / 精确率、渠道支撑率，以及重测一致性和与人工标注的一致性。"""
    n = len(records)
    full = [r for r in records if r["support"] == "full"]
    cited = sum(r["evidence"] for r in full)
    irrelevant = sum(len(r["irrelevant"]) for r in full)
    out = {
        "version": JUDGE_VERSION, "model": model, "repeats": repeats, "events": n,
        "failed_scenes": failures,
        "support": dict(collections.Counter(r["support"] for r in records)),
        "citation_recall": round(len(full) / n, 3) if n else None,
        "citation_precision": round(1 - irrelevant / cited, 3) if cited else None,
        "channel_support": round(sum(r["channel_ok"] for r in records) / n, 3) if n else None,
        "flagged": [{k: r[k] for k in ("scene", "event", "topic", "channel", "support", "unsupported", "channel_ok",
                                       "channel_note")}
                    for r in records if r["support"] != "full" or not r["channel_ok"]][:FLAGGED_LIMIT],
    }
    if repeats > 1 and records:
        pairs = list(itertools.combinations(range(repeats), 2))
        out["retest"] = {
            "support_kappa": _mean(cohen_kappa([(r["runs"][i]["support"], r["runs"][j]["support"]) for r in records])
                                   for i, j in pairs),
            "channel_kappa": _mean(cohen_kappa([(r["runs"][i]["channel_ok"], r["runs"][j]["channel_ok"]) for r in records])
                                   for i, j in pairs),
        }
    if labels:
        both = [(r, labels[(r["scene"], r["event"])]) for r in records if (r["scene"], r["event"]) in labels]
        out["human"] = {
            "events": len(both),
            "support_kappa": cohen_kappa([(r["support"], h["support"]) for r, h in both if "support" in h]),
            "channel_kappa": cohen_kappa([(r["channel_ok"], h["channel_ok"]) for r, h in both if "channel_ok" in h]),
        }
    return out


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 3) if values else None
