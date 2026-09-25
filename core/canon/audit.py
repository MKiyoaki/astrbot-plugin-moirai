"""canon 抽取结果的自动质量检查：说话人、证据、{DOCTOR} 与代词、外部知识、目标角色台词覆盖率。

只做能从原文机械判断的检查（思路同 GroundEval，arXiv 2606.22737：能确定判断的就不交给 LLM 裁判）。
结果是给人工审阅的线索，不是成败标准：标成"疑似"的条目允许误报，需要对照原文确认。
"""
from __future__ import annotations

import collections
import re

from .extract import (CHANNELS, DOCTOR, DOCTOR_LITERAL, TEXT_LIMITS, doctor_literals, event_lines, format_runs,
                      line_runs, shared_lines, text_length, uncovered_runs)

SPEAKING_KINDS = ("dialogue", "inner_voice")
NARRATION_KINDS = ("narration", "subtitle", "caption")
_SENTENCE = re.compile(r"[。！？!?\n]")
_HE = re.compile(r"他(?!们)")
_TA = re.compile(r"(?<![A-Za-z])ta(?![A-Za-z])")
DENSITY_BINS = ((0, 0, "0"), (1, 10, "1–10"), (11, 40, "11–40"), (41, 10**9, "41+"))
_GENERIC = re.compile(r"的|们|[？?]|^[“\"「]|[\u4e00-\u9fff][A-Za-z0-9]$"
                      r"|[人者员兵官民童士手工商众客徒师匪卫队生女儿佣警板理编教群兽族]$")


MAX_EVENTS_HINT = 8
FRAGMENT_SPAN = 3
FRAGMENT_SCENE_LINES = 20
LOW_COVERAGE = 0.9

def person_lexicon(seeds: list[dict], character: dict) -> dict[str, str]:
    """外部知识检查用的人名词典：别名 → 实体名。

    character_table 里的角色全部保留；只来自"高频说话人"的名字里混着"军官""孩童"这类泛称，
    按 _GENERIC 过滤掉（会误删少数带称号的具名角色，这项检查本来就只是线索）。
    目标角色、博士和带问号的变体名不参与检查。旧版 story_pack 的种子没有 sources，一律按说话人处理。
    """
    skip = {character["display"], *character.get("confirmed_names", []), "博士"}
    out = {}
    for seed in seeds:
        name = seed["name"]
        if name in skip or ("character_table" not in (seed.get("sources") or []) and _GENERIC.search(name)):
            continue
        for alias in dict.fromkeys([name, *seed.get("aliases", [])]):
            if len(alias) >= 2 and alias not in skip:
                out[alias] = name
    return out


def output_texts(result: dict, *, with_names: bool = False) -> list[tuple[str, str]]:
    out = []
    for ev in result["events"]:
        out += [(f"{ev['id']}.topic", ev.get("topic", "")), (f"{ev['id']}.summary", ev.get("summary", ""))]
        out += [(f"{ev['id']}.beats[{j}]", b.get("text", "")) for j, b in enumerate(ev.get("beats") or [])]
        if with_names:
            out += [(f"{ev['id']}.participants", "、".join(ev.get("participants") or [])),
                    (f"{ev['id']}.entities", "、".join(e.get("name", "") for e in ev.get("entities") or []))]
    if result.get("episode"):
        out.append(("episode", result["episode"].get("text", "")))
    for i, cog in enumerate(result["cognitions"]):
        out.append((f"cognitions[{i}]", f"{cog.get('target', '')}｜{cog.get('stance', '')}"))
    return out


def doctor_pronouns(result: dict) -> list[tuple[str, str]]:
    """疑似用"他"指代博士的句子：同一句里既有 {DOCTOR}（或字面"博士"）又有单数的"他"。

    "她"不做机械检查：目标角色是女性，摘要里的"她"几乎都指她本人，按位置判断误报太多。
    是否遵守"用 ta 指代博士"看 ta 的使用次数和人工抽查。
    """
    out = []
    for field, text in output_texts(result):
        for sent in _SENTENCE.split(text):
            if ("{DOCTOR}" in sent or "博士" in sent) and _HE.search(sent):
                out.append((field, sent))
    return out


def foreign_persons(result: dict, source: str, lexicon: dict[str, str]) -> list[tuple[str, str]]:
    """输出里提到、但这个人物的任何别名都没在原文（含官方简介和前情）出现过的 (字段, 人物)。

    模型只应依据本场景的文本；原文里没有的角色名多半来自外部知识或后续剧情。
    """
    present = {name for alias, name in lexicon.items() if alias in source}
    out = []
    for field, text in output_texts(result, with_names=True):
        found = {name for alias, name in lexicon.items() if alias in text and name not in present}
        out += [(field, name) for name in sorted(found)]
    return out


def cited_lines(event: dict, view: dict | None) -> set[int]:
    """一个事件精确引用的行号：有 beats 时取 beats 和视角证据，没有时取事件证据和视角证据。

    v3 的事件是一段连贯情节，模型可能把事件证据写成整段的行区间：这些行只说明事件管哪一段，不代表每行都被挑为关键行，
    拿来算命中会让覆盖类指标几乎自动满分。精确出处在 beats 和视角证据里。v1、v2 没有 beats，事件证据本来就是挑出的关键行。
    """
    refs = [r for b in event.get("beats") or [] for r in b.get("evidence") or []] if event.get("beats") else event["evidence"]
    return {int(r[1:]) for r in [*refs, *((view or {}).get("evidence") or [])]}


def audit_scene(scene: dict, result: dict, character: dict, *, lexicon: dict[str, str] | None = None,
                context: str = "") -> dict:
    """检查一个场景的抽取结果，返回统计量和问题清单。

    lexicon 是 person_lexicon() 的结果，给了才做外部知识检查；context 是 prompt 里同样给了模型的前情简介。
    """
    lines = scene["lines"]
    names = {character["display"], *character.get("confirmed_names", [])}
    pending = set(character.get("pending_names") or [])
    target = {i for i, ln in enumerate(lines, 1) if ln["kind"] in SPEAKING_KINDS and ln.get("spk") in names}
    mentioned = {i for i, ln in enumerate(lines, 1) if any(n in ln["text"] for n in names)}
    narrated = {i for i in mentioned if lines[i - 1]["kind"] in NARRATION_KINDS}
    source = "\n".join([scene.get("anchor") or "", scene.get("official_summary") or "", context,
                        *(f"{ln.get('spk') or ''}：{ln['text']}" for ln in lines)])
    views = {v["event"]: v for v in result["views"]}
    issues: list[dict] = []

    def issue(kind: str, where: str, detail: str) -> None:
        issues.append({"kind": kind, "where": where, "detail": detail})

    channels: collections.Counter = collections.Counter()
    cited: set[int] = set()
    evidence_sizes = []
    concept, entities, beats = [], 0, 0
    last_first = 0
    if len(result["events"]) > MAX_EVENTS_HINT:
        issue(f"事件超过 {MAX_EVENTS_HINT} 条", "events", f"{len(result['events'])} 个事件，可能拆得过细")
    for ev in result["events"]:
        eid = ev["id"]
        view = views.get(eid, {})
        channel = view.get("channel")
        channels[channel] += 1
        evl = sorted(int(r[1:]) for r in ev["evidence"])
        vl = sorted(int(r[1:]) for r in view.get("evidence") or [])
        cited.update(cited_lines(ev, view))
        evidence_sizes.append(len(evl))
        if evl and evl[0] < last_first:
            issue("事件顺序颠倒", eid, f"首条证据 L{evl[0]} 早于上一事件的 L{last_first}")
        if evl and len(lines) >= FRAGMENT_SCENE_LINES and evl[-1] - evl[0] + 1 < FRAGMENT_SPAN:
            issue(f"事件只覆盖不到 {FRAGMENT_SPAN} 行", eid, f"L{evl[0]}–L{evl[-1]}，可能是从一段情节里拆出的碎片")
        for field, text, limit in ((f"{eid}.topic", ev.get("topic", ""), "topic"),
                                   (f"{eid}.summary", ev.get("summary", ""), "summary"),
                                   *((f"{eid}.beats[{j}]", b.get("text", ""), "beat")
                                     for j, b in enumerate(ev.get("beats") or []))):
            if text_length(text) > TEXT_LIMITS[limit][0]:
                issue("超过建议长度", field, f"{text_length(text)} 字，prompt 建议不超过 {TEXT_LIMITS[limit][0]} 字")
        for j, beat in enumerate(ev.get("beats") or []):
            beats += 1
            outside = sorted({int(r[1:]) for r in beat.get("evidence") or []} - set(evl))
            if outside:
                issue("beat 证据不在事件证据里", f"{eid}.beats[{j}]", "、".join(f"L{n}" for n in outside))
        if evl:
            last_first = evl[0]
            spoken = sorted(target & set(range(evl[0], evl[-1] + 1)))
            if channel == "unstated" and spoken:
                issue("她说了话却标 unstated", eid, "她在证据范围内的台词：" + "、".join(f"L{n}" for n in spoken[:8]))
        if channel in ("experienced", "witnessed") and not (target | mentioned) & set(vl):
            issue("在场缺少文本依据", eid, f"{channel} 的视角证据里既没有她的台词，也没有提到她")
        foreign = [n for n in vl if lines[n - 1].get("spk") in pending]
        if foreign:
            issue("名单外说话人被当作她的证据", eid,
                  "、".join(f"L{n}（{lines[n - 1]['spk']}）" for n in foreign))
        for ent in ev.get("entities") or []:
            entities += 1
            if ent.get("type") == "concept":
                concept.append(ent["name"])
            if ent["name"].replace(DOCTOR, DOCTOR_LITERAL) not in source:
                issue("实体名不在原文（弱信号，多为改写）", eid, f"{ent['name']}/{ent.get('type')}")
    for field, text in doctor_literals(result):
        issue("字面“博士”", field, text)
    for field, text in doctor_pronouns(result):
        issue("疑似用“他”指代博士", field, text)
    for field, name in foreign_persons(result, source, lexicon or {}):
        issue("疑似外部知识：原文没有的人物", field, name)
    episode = result.get("episode")
    over = [("episode", (episode or {}).get("text", ""), "episode")]
    over += [(f"cognitions[{i}]", c.get("stance", ""), "stance") for i, c in enumerate(result["cognitions"])]
    for field, text, limit in over:
        if text_length(text) > TEXT_LIMITS[limit][0]:
            issue("超过建议长度", field, f"{text_length(text)} 字，prompt 建议不超过 {TEXT_LIMITS[limit][0]} 字")
    if episode and not target and not narrated:
        issue("她未出场却写了 episode", "episode", "本场景她没有台词，旁白也没写到她")
    owned = event_lines(result["events"])
    gaps = uncovered_runs(owned, 1, len(lines))
    if gaps:
        issue("有连续行不在任何事件里", "events", format_runs(gaps))
    for a, b, common in shared_lines(owned):
        issue("事件范围重叠", f"{a}/{b}", format_runs(line_runs(common)))
    covered = set().union(*(ls for _, ls in owned)) & set(range(1, len(lines) + 1))
    ta = sum(len(_TA.findall(text)) for _, text in output_texts(result))
    return {
        "events": len(result["events"]),
        "beats": beats,
        "channels": {c: channels.get(c, 0) for c in CHANNELS},
        "episode": bool(episode),
        "cognitions": len(result["cognitions"]),
        "edges": len(result["edges"]),
        "explicit_edges": sum(1 for e in result["edges"] if e.get("explicit") is True),
        "entities": entities,
        "concept_entities": concept,
        "ta": ta,
        "target_lines": len(target),
        "target_lines_cited": len(target & cited),
        "evidence_mean": round(sum(evidence_sizes) / len(evidence_sizes), 1) if evidence_sizes else 0,
        "evidence_max": max(evidence_sizes, default=0),
        "scene_lines": len(lines),
        "covered_lines": len(covered),
        "issues": issues,
    }


def summarize_audits(audits: list[dict]) -> dict:
    """把多个场景的检查结果合计成一份。

    她的台词覆盖率按场景里她的台词数分段统计：台词越密的场景越容易被压缩成少数几个事件而漏掉内容
    （结构化抽取里的"多实例压缩"，arXiv 2602.10881）。
    """
    channels: collections.Counter = collections.Counter()
    kinds: collections.Counter = collections.Counter()
    bins = {label: [0, 0, 0] for _, _, label in DENSITY_BINS}
    for a in audits:
        channels.update(a["channels"])
        kinds.update(i["kind"] for i in a["issues"])
        label = next(lb for lo, hi, lb in DENSITY_BINS if lo <= a["target_lines"] <= hi)
        bins[label][0] += 1
        bins[label][1] += a["target_lines"]
        bins[label][2] += a["target_lines_cited"]
    target = sum(a["target_lines"] for a in audits)
    events = sum(a["events"] for a in audits)
    scene_lines = sum(a.get("scene_lines", 0) for a in audits)
    return {
        "scenes": len(audits),
        "events": events,
        "events_per_scene": round(events / len(audits), 1) if audits else 0,
        "beats": sum(a.get("beats", 0) for a in audits),
        "channels": {c: channels.get(c, 0) for c in CHANNELS},
        "episodes": sum(a["episode"] for a in audits),
        "cognitions": sum(a["cognitions"] for a in audits),
        "edges": sum(a["edges"] for a in audits),
        "explicit_edges": sum(a["explicit_edges"] for a in audits),
        "entities": sum(a["entities"] for a in audits),
        "concept_entities": sum(len(a["concept_entities"]) for a in audits),
        "ta": sum(a["ta"] for a in audits),
        "target_line_coverage": round(sum(a["target_lines_cited"] for a in audits) / target, 3) if target else None,
        "evidence_max": max((a["evidence_max"] for a in audits), default=0),
        "scene_coverage": round(sum(a.get("covered_lines", 0) for a in audits) / scene_lines, 3) if scene_lines else None,
        "low_coverage_scenes": sum(1 for a in audits if a.get("scene_lines")
                                   and a["covered_lines"] / a["scene_lines"] < LOW_COVERAGE),
        "coverage_by_density": {label: {"scenes": n, "target_lines": t,
                                        "coverage": round(c / t, 3) if t else None}
                                for label, (n, t, c) in bins.items() if n},
        "issues": dict(sorted(kinds.items(), key=lambda kv: -kv[1])),
    }
