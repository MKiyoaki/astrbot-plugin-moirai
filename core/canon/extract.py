"""canon 抽取：调用模型、解析和校验 JSON、失败重试、长场景分块合并。

校验规则见 docs/canon.md。任何一条不满足都算失败并带着问题清单重试，最多 3 次；
另有几项只记为质量指标，不影响成败。证据行数不设上限：canon 是离线构建的，不受实时预算约束。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .prompt import SYSTEM_PROMPT, build_user_prompt, chunk_ranges, retry_suffix

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
IN_WORLD_TIME = ("present", "past", "unknown")
CHANNELS = ("experienced", "witnessed", "told", "recalled", "unstated")
EDGE_TYPES = ("cause", "motivation", "emotion_source", "cognition_update")
ENTITY_TYPES = ("person", "place", "faction", "object", "concept")
MAX_REPORTED_ERRORS = 20
TEXT_LIMITS = {"topic": (20, 30), "summary": (300, 400), "beat": (25, 40), "episode": (200, 300), "stance": (40, 60)}
MAX_RANGE_SPAN = 200
DOCTOR = "{DOCTOR}"
DOCTOR_LITERAL = "博士"

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s*```[a-zA-Z]*\s*|\s*```\s*$")
_LOCAL_ID_RE = re.compile(r"^e\d+$")
_LREF_RE = re.compile(r"^L(\d+)$")
_REF_SPLIT_RE = re.compile(r"[,，、\s]+")
_RANGE_DASH_RE = re.compile(r"\s*[-–—~～至到]\s*")
_REF_TOKEN_RE = re.compile(r"^L?(\d+)(?:-L?(\d+))?$")

Call = Callable[[str, str], Awaitable[Any]]
Observer = Callable[[dict], None]


@dataclass
class ExtractionOutcome:
    status: str
    result: dict | None = None
    error: str | None = None
    attempts: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    quality: dict[str, int] = field(default_factory=dict)


JSON_QUOTE_HINT = "字符串里引用原话时，英文双引号要写成 \\\" 或改用「」"


def repair_quotes(text: str) -> tuple[str, int]:
    """把 JSON 字符串内部没转义的英文双引号改成 \\"，返回修复后的文本和修复的处数。

    字符串内部遇到引号时看它后面第一个非空白字符：是 , : } ] 或文本结尾就当作结束引号，否则当作正文里的引号。
    内部引号后面紧跟半角逗号或冒号时判断不了，会被当作结束引号，解析仍然失败。
    """
    out: list[str] = []
    fixed, inside, i, n = 0, False, 0, len(text)
    while i < n:
        ch = text[i]
        if inside and ch == "\\":
            out.append(text[i:i + 2])
            i += 2
            continue
        if ch == '"':
            if inside:
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                if j < n and text[j] not in ",:}]":
                    out.append('\\"')
                    fixed += 1
                    i += 1
                    continue
            inside = not inside
        out.append(ch)
        i += 1
    return "".join(out), fixed


def parse_json(text: str) -> tuple[Any, int]:
    """去掉 <think> 块和代码围栏后解析 JSON，返回对象和修复的引号处数。

    前后夹杂说明文字时退回到最外层花括号；仍然失败时用 repair_quotes 修复后再解析一次。
    能直接解析的 JSON 不做任何修改；修复后也解析不了就抛出修复前的错误。
    """
    cleaned = _FENCE_RE.sub("", _THINK_RE.sub("", text or "").strip()).strip()
    try:
        return json.loads(cleaned), 0
    except ValueError as exc:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        body, first_error = (cleaned[start:end + 1], None) if start >= 0 and end > start else (cleaned, exc)
    if first_error is None:
        try:
            return json.loads(body), 0
        except ValueError as exc:
            first_error = exc
    repaired, fixed = repair_quotes(body)
    if fixed:
        try:
            return json.loads(repaired), fixed
        except ValueError:
            pass
    raise first_error


def parse_output(text: str) -> Any:
    return parse_json(text)[0]


def _ref_items(value: Any) -> list[str] | None:
    """把一个证据值换成 L 行号列表；只要有一项认不出来就返回 None，原值交给校验。

    认得：整数 2、"2"、"L2"、"l2"、全角"Ｌ２"、区间 "2-5"、"L2–L5"、"L2至5"、"L2, L3"、"L2、L3"，以及由这些组成的数组。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return [f"L{value}"] if value > 0 else None
    if isinstance(value, float):
        return [f"L{int(value)}"] if value.is_integer() and value > 0 else None
    if isinstance(value, str):
        text = _RANGE_DASH_RE.sub("-", unicodedata.normalize("NFKC", value).strip().upper())
        out: list[str] = []
        for token in (t for t in _REF_SPLIT_RE.split(text) if t):
            m = _REF_TOKEN_RE.match(token)
            if not m:
                return None
            first, last = int(m.group(1)), int(m.group(2) or m.group(1))
            if first < 1 or not 0 <= last - first <= MAX_RANGE_SPAN:
                return None
            out += [f"L{n}" for n in range(first, last + 1)]
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            refs = None if isinstance(item, list) else _ref_items(item)
            if refs is None:
                return None
            out += refs
        return out
    return None


def normalize_output(obj: Any) -> int:
    """校验前把没有歧义的格式问题规范掉，返回改了几处；认不出的写法原样留给校验。

    - 证据：见 _ref_items，结果去重并保持顺序。
    - 枚举值（in_world_time、channel、边和实体的 type）：去空格、转小写后是合法值就改。
    - 边的 explicit 写成 "true"/"false"、confidence 写成数字字符串时改成布尔值和数字。
    - participants 写成一个字符串时按 、 , ， 拆成数组。
    - 文字字段里的字面"博士"换成 {DOCTOR}，participants 里的"博士"换成 "@doctor"。剧情里没有别的人物被称作"某某博士"，
      博士只指玩家角色；"他"是否指博士有歧义，不做替换。
    """
    if not isinstance(obj, dict):
        return 0
    fixed = 0

    def dicts(value):
        return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []

    def enum(holder, key, allowed):
        nonlocal fixed
        value = holder.get(key)
        if isinstance(value, str) and value not in allowed and value.strip().lower() in allowed:
            holder[key] = value.strip().lower()
            fixed += 1

    events = dicts(obj.get("events"))
    beats = [b for ev in events for b in dicts(ev.get("beats"))]
    for holder in events + beats + dicts(obj.get("views")) + dicts(obj.get("cognitions")) + dicts(obj.get("edges")):
        value = holder.get("evidence")
        if value is None:
            continue
        refs = _ref_items(value)
        if refs is not None:
            refs = list(dict.fromkeys(refs))
            if refs != value:
                holder["evidence"] = refs
                fixed += 1
    for ev in events:
        enum(ev, "in_world_time", IN_WORLD_TIME)
        for ent in dicts(ev.get("entities")):
            enum(ent, "type", ENTITY_TYPES)
        parts = ev.get("participants")
        if isinstance(parts, str) and parts.strip():
            ev["participants"] = [x.strip() for x in re.split(r"[、,，]", parts) if x.strip()]
            fixed += 1
    for view in dicts(obj.get("views")):
        enum(view, "channel", CHANNELS)
    for edge in dicts(obj.get("edges")):
        enum(edge, "type", EDGE_TYPES)
        explicit = edge.get("explicit")
        if isinstance(explicit, str) and explicit.strip().lower() in ("true", "false"):
            edge["explicit"] = explicit.strip().lower() == "true"
            fixed += 1
        conf = edge.get("confidence")
        if isinstance(conf, str):
            try:
                edge["confidence"] = float(conf.strip())
                fixed += 1
            except ValueError:
                pass
    episode = obj.get("episode")
    texts = [(ev, ("topic", "summary", "in_world_note")) for ev in events]
    texts += [(b, ("text",)) for b in beats]
    texts += [(ent, ("name",)) for ev in events for ent in dicts(ev.get("entities"))]
    texts += [(view, ("note",)) for view in dicts(obj.get("views"))]
    texts += [(cog, ("target", "stance")) for cog in dicts(obj.get("cognitions"))]
    texts += [(episode, ("text",))] if isinstance(episode, dict) else []
    for holder, keys in texts:
        for key in keys:
            value = holder.get(key)
            if isinstance(value, str) and DOCTOR_LITERAL in value:
                holder[key] = value.replace(DOCTOR_LITERAL, DOCTOR)
                fixed += 1
    for ev in events:
        parts = ev.get("participants")
        if isinstance(parts, list) and any(p in (DOCTOR_LITERAL, DOCTOR) for p in parts):
            ev["participants"] = ["@doctor" if p in (DOCTOR_LITERAL, DOCTOR) else p for p in parts]
            fixed += 1
    return fixed


def prune_auxiliary(obj: Any, lo: int, hi: int, character: dict) -> list[str]:
    """丢掉不合格的辅助条目（实体、beats、认知、边），并把没有视角证据的在场渠道降为 unstated；返回做了什么。

    这些问题单条出错不值得整次重试：重试要重新生成整个场景，而丢掉一条只损失这一条。
    标了 experienced / witnessed / told / recalled 却一行视角证据都没给，按总原则 5（无法判断时用 unstated）降级。
    核心字段的其他问题仍交给校验。
    """
    if not isinstance(obj, dict) or not isinstance(obj.get("events"), list):
        return []
    names = character_names(character)
    dropped: list[str] = []
    ids = {ev["id"] for ev in obj["events"] if isinstance(ev, dict) and isinstance(ev.get("id"), str)}

    def keep(items, ok, label):
        kept = []
        for item in items:
            if isinstance(item, dict) and ok(item):
                kept.append(item)
            else:
                dropped.append(f"{label}：{json.dumps(item, ensure_ascii=False)[:80]}")
        return kept

    for ev in obj["events"]:
        if not isinstance(ev, dict):
            continue
        eid = ev.get("id")
        if isinstance(ev.get("entities"), list):
            ev["entities"] = keep(ev["entities"], lambda e: _text(e.get("name"), 1, 20) and e["name"] != DOCTOR
                                  and e.get("type") in ENTITY_TYPES, f"事件 {eid} 的实体")
        if isinstance(ev.get("beats"), list):
            ev["beats"] = keep(ev["beats"], lambda b: _text(b.get("text"), 1, TEXT_LIMITS["beat"][1])
                               and not _refs(b.get("evidence"), lo, hi, allow_empty=False), f"事件 {eid} 的 beat")
    if isinstance(obj.get("views"), list):
        for view in obj["views"]:
            if isinstance(view, dict) and view.get("channel") in CHANNELS and view["channel"] != "unstated" \
                    and view.get("evidence") in (None, []):
                dropped.append(f"事件 {view.get('event')} 的渠道 {view['channel']} 没有视角证据，改为 unstated")
                view["channel"], view["evidence"] = "unstated", []
    if isinstance(obj.get("cognitions"), list):
        obj["cognitions"] = keep(obj["cognitions"], lambda c: c.get("character") in names
                                 and _text(c.get("target"), 1, 10**6) and _text(c.get("stance"), 1, TEXT_LIMITS["stance"][1])
                                 and not _refs(c.get("evidence"), lo, hi, allow_empty=False), "认知")
    if isinstance(obj.get("edges"), list):
        obj["edges"] = keep(obj["edges"], lambda e: e.get("from") in ids and e.get("to") in ids
                            and e.get("type") in EDGE_TYPES and isinstance(e.get("explicit"), bool)
                            and not isinstance(e.get("confidence"), bool)
                            and isinstance(e.get("confidence"), (int, float)) and 0 <= e["confidence"] <= 1
                            and not _refs(e.get("evidence", []), lo, hi, allow_empty=e.get("explicit") is not True),
                            "边")
    return dropped


def character_names(character: dict) -> set[str]:
    return {character["display"], character["character"], *character.get("confirmed_names", [])}


def text_length(text: str) -> int:
    """按显示长度计字数：{DOCTOR} 显示为"博士"，算 2 个字。"""
    return len(text.strip().replace(DOCTOR, DOCTOR_LITERAL))


def _text(value, lo: int, hi: int) -> bool:
    return isinstance(value, str) and lo <= text_length(value) <= hi


def _refs(value, lo: int, hi: int, *, allow_empty: bool) -> str | None:
    """检查证据行号数组，返回问题描述；没问题返回 None。"""
    if not isinstance(value, list):
        return "evidence 必须是数组"
    if not value and not allow_empty:
        return "evidence 不能为空"
    for ref in value:
        m = _LREF_RE.match(ref) if isinstance(ref, str) else None
        if not m:
            return f"证据 {ref!r} 不是 L 加数字的形式"
        if not lo <= int(m.group(1)) <= hi:
            return f"证据 {ref} 超出本场景的行号范围 L{lo}–L{hi}"
    return None


def validate(obj: Any, lo: int, hi: int, character: dict) -> list[str]:
    """按规格的 8 条规则校验一块的输出，返回问题清单（空清单即通过）。"""
    errors: list[str] = []
    names = character_names(character)
    if not isinstance(obj, dict):
        return ["顶层必须是一个 JSON 对象"]
    for key, kind in (("events", list), ("views", list), ("cognitions", list), ("edges", list)):
        if not isinstance(obj.get(key), kind):
            errors.append(f"缺少数组字段 {key}")
    if "episode" not in obj or not (obj["episode"] is None or isinstance(obj["episode"], dict)):
        errors.append("episode 必须是对象或 null")
    if errors:
        return errors

    events = obj["events"]
    if not events:
        errors.append("events 至少要有 1 条")
    ids: list[str] = []
    for i, ev in enumerate(events):
        where = f"events[{i}]"
        if not isinstance(ev, dict):
            errors.append(f"{where} 必须是对象")
            continue
        eid = ev.get("id")
        if not isinstance(eid, str) or not _LOCAL_ID_RE.match(eid):
            errors.append(f"{where}.id 必须是 e1、e2 这样的形式")
        elif eid in ids:
            errors.append(f"事件 id {eid} 重复")
        else:
            ids.append(eid)
            where = f"事件 {eid}"
        if not _text(ev.get("topic"), 1, TEXT_LIMITS["topic"][1]):
            errors.append(f"{where}.topic 必须是 1–{TEXT_LIMITS['topic'][0]} 字")
        if not _text(ev.get("summary"), 1, TEXT_LIMITS["summary"][1]):
            errors.append(f"{where}.summary 必须是 1–{TEXT_LIMITS['summary'][0]} 字")
        if ev.get("in_world_time") not in IN_WORLD_TIME:
            errors.append(f"{where}.in_world_time 只能是 {'/'.join(IN_WORLD_TIME)}")
        note = ev.get("in_world_note")
        if note is not None and not isinstance(note, str):
            errors.append(f"{where}.in_world_note 必须是字符串")
        parts = ev.get("participants")
        if not isinstance(parts, list) or not parts or not all(isinstance(p, str) and p.strip() for p in parts):
            errors.append(f"{where}.participants 必须是非空的字符串数组")
        problem = _refs(ev.get("evidence"), lo, hi, allow_empty=False)
        if problem:
            errors.append(f"{where}：{problem}")
        beats = ev.get("beats", [])
        if not isinstance(beats, list):
            errors.append(f"{where}.beats 必须是数组")
            beats = []
        for j, beat in enumerate(beats):
            if not isinstance(beat, dict) or not _text(beat.get("text"), 1, TEXT_LIMITS["beat"][1]):
                errors.append(f"{where}.beats[{j}].text 必须是 1–{TEXT_LIMITS['beat'][0]} 字")
                continue
            problem = _refs(beat.get("evidence"), lo, hi, allow_empty=False)
            if problem:
                errors.append(f"{where}.beats[{j}]：{problem}")
        ents = ev.get("entities", [])
        if not isinstance(ents, list):
            errors.append(f"{where}.entities 必须是数组")
            ents = []
        for ent in ents:
            if not isinstance(ent, dict) or not _text(ent.get("name"), 1, 20) or ent.get("type") not in ENTITY_TYPES:
                errors.append(f"{where}.entities 里的 {ent!r} 不合规：name 1–20 字，type 只能是 {'/'.join(ENTITY_TYPES)}")
    id_set = set(ids)

    seen_views: dict[str, int] = {}
    for i, view in enumerate(obj["views"]):
        where = f"views[{i}]"
        if not isinstance(view, dict):
            errors.append(f"{where} 必须是对象")
            continue
        if view.get("character") not in names:
            errors.append(f"{where}.character 必须是目标角色 {character['display']}")
            continue
        eid = view.get("event")
        if eid not in id_set:
            errors.append(f"{where}.event {eid!r} 不是已有的事件 id")
            continue
        seen_views[eid] = seen_views.get(eid, 0) + 1
        channel = view.get("channel")
        if channel not in CHANNELS:
            errors.append(f"{where}.channel 只能是 {'/'.join(CHANNELS)}")
        problem = _refs(view.get("evidence"), lo, hi, allow_empty=channel == "unstated")
        if problem:
            errors.append(f"{where}（事件 {eid}）：{problem}"
                          + ("；只有 channel 为 unstated 时 evidence 才能为空" if "不能为空" in problem else ""))
    for eid in ids:
        n = seen_views.get(eid, 0)
        if n != 1:
            errors.append(f"事件 {eid} 必须恰好有 1 条目标角色的 views，现在有 {n} 条")

    for i, edge in enumerate(obj["edges"]):
        where = f"edges[{i}]"
        if not isinstance(edge, dict):
            errors.append(f"{where} 必须是对象")
            continue
        if edge.get("from") not in id_set or edge.get("to") not in id_set:
            errors.append(f"{where} 的 from/to 必须是已有的事件 id")
        if edge.get("type") not in EDGE_TYPES:
            errors.append(f"{where}.type 只能是 {'/'.join(EDGE_TYPES)}")
        explicit = edge.get("explicit")
        if not isinstance(explicit, bool):
            errors.append(f"{where}.explicit 必须是 true 或 false")
        conf = edge.get("confidence")
        if isinstance(conf, bool) or not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
            errors.append(f"{where}.confidence 必须是 0 到 1 的数")
        problem = _refs(edge.get("evidence", []), lo, hi, allow_empty=explicit is not True)
        if problem:
            errors.append(f"{where}：{problem}" + ("（explicit 为 true 时必须给出证据）" if "不能为空" in problem else ""))

    episode = obj["episode"]
    if isinstance(episode, dict):
        if episode.get("character") not in names:
            errors.append(f"episode.character 必须是目标角色 {character['display']}")
        if not _text(episode.get("text"), 1, TEXT_LIMITS["episode"][1]):
            errors.append(f"episode.text 必须是 1–{TEXT_LIMITS['episode'][0]} 字")

    for i, cog in enumerate(obj["cognitions"]):
        where = f"cognitions[{i}]"
        if not isinstance(cog, dict):
            errors.append(f"{where} 必须是对象")
            continue
        if cog.get("character") not in names:
            errors.append(f"{where}.character 必须是目标角色 {character['display']}")
        if not _text(cog.get("target"), 1, 10**6):
            errors.append(f"{where}.target 不能为空")
        if not _text(cog.get("stance"), 1, TEXT_LIMITS["stance"][1]):
            errors.append(f"{where}.stance 必须是 1–{TEXT_LIMITS['stance'][0]} 字")
        problem = _refs(cog.get("evidence"), lo, hi, allow_empty=False)
        if problem:
            errors.append(f"{where}：{problem}")
    return errors[:MAX_REPORTED_ERRORS]


def doctor_literals(result: dict) -> list[tuple[str, str]]:
    """返回写了字面"博士"而没有用 {DOCTOR} 的 (字段, 文本)。"""
    out = []
    for ev in result["events"]:
        for key in ("topic", "summary"):
            if "博士" in ev.get(key, ""):
                out.append((f"{ev['id']}.{key}", ev[key]))
        for j, beat in enumerate(ev.get("beats") or []):
            if "博士" in beat.get("text", ""):
                out.append((f"{ev['id']}.beats[{j}]", beat["text"]))
        for ent in ev.get("entities") or []:
            if "博士" in ent.get("name", ""):
                out.append((f"{ev['id']}.entities", ent["name"]))
    if result.get("episode") and "博士" in result["episode"].get("text", ""):
        out.append(("episode", result["episode"]["text"]))
    for i, cog in enumerate(result["cognitions"]):
        for key in ("target", "stance"):
            if "博士" in cog.get(key, ""):
                out.append((f"cognitions[{i}].{key}", cog[key]))
    return out


def quality_flags(result: dict) -> dict[str, int]:
    """不算失败、只进报告的质量指标。"""
    flags: dict[str, int] = {}
    literal = len(doctor_literals(result))
    if literal:
        flags["写了字面“博士”而非 {DOCTOR}"] = literal
    present = any(v["channel"] in ("experienced", "witnessed") for v in result["views"])
    if present and result["episode"] is None:
        flags["有亲历/目睹事件但 episode 为 null"] = 1
    return flags


def _usage(resp) -> tuple[int | None, int | None]:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None, None
    if isinstance(usage, dict):
        return usage.get("prompt_tokens") or usage.get("input"), usage.get("completion_tokens") or usage.get("output")
    return (getattr(usage, "input", None) or getattr(usage, "prompt_tokens", None),
            getattr(usage, "output", None) or getattr(usage, "completion_tokens", None))


def _ignore(record: dict) -> None:
    return None


def _prefix(result: dict, tag: str) -> dict:
    rename = {ev["id"]: f"{tag}{ev['id']}" for ev in result["events"]}
    out = dict(result)
    out["events"] = [{**ev, "id": rename[ev["id"]]} for ev in result["events"]]
    out["views"] = [{**v, "event": rename[v["event"]]} for v in result["views"]]
    out["edges"] = [{**e, "from": rename[e["from"]], "to": rename[e["to"]]} for e in result["edges"]]
    return out


async def _extract_chunk(call: Call, prompt: str, lo: int, hi: int, character: dict, timeout: float,
                         tokens: list[int | None], observe: Observer) -> tuple[dict | None, int, str | None]:
    errors: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        user_prompt = prompt + (retry_suffix(errors) if errors else "")
        started = time.monotonic()
        try:
            resp = await asyncio.wait_for(call(user_prompt, SYSTEM_PROMPT), timeout)
        except Exception as exc:
            errors = []
            if isinstance(exc, asyncio.TimeoutError):
                last = f"调用失败：超过 {timeout:g} 秒没有返回"
            else:
                last = f"调用失败：{type(exc).__name__}: {exc}"
            logger.warning("[canon] extraction call failed (attempt %d): %s", attempt, last)
            observe({"attempt": attempt, "seconds": time.monotonic() - started, "ok": False, "errors": [last],
                     "prompt_tokens": None, "completion_tokens": None, "quote_fixes": 0, "format_fixes": 0,
                     "dropped": [], "response": None})
            if attempt < MAX_ATTEMPTS:
                await asyncio.sleep(min(2 ** attempt, 10))
            continue
        seconds = time.monotonic() - started
        p, c = _usage(resp)
        if p is not None:
            tokens[0] = (tokens[0] or 0) + p
        if c is not None:
            tokens[1] = (tokens[1] or 0) + c
        text = getattr(resp, "completion_text", "") or ""
        fixes = format_fixes = 0
        dropped: list[str] = []
        try:
            obj, fixes = parse_json(text)
        except ValueError as exc:
            errors = [f"输出不是合法的 JSON：{exc}。{JSON_QUOTE_HINT}"]
        else:
            format_fixes = normalize_output(obj)
            dropped = prune_auxiliary(obj, lo, hi, character)
            errors = validate(obj, lo, hi, character)
        observe({"attempt": attempt, "seconds": seconds, "ok": not errors, "errors": list(errors),
                 "prompt_tokens": p, "completion_tokens": c, "quote_fixes": fixes,
                 "format_fixes": format_fixes, "dropped": dropped, "response": text})
        if not errors:
            return obj, attempt, None
        last = "；".join(errors)
    return None, MAX_ATTEMPTS, last


async def extract_scene(call: Call, scene: dict, character: dict, prev_scene: dict | None,
                        *, timeout: float = 300, observer: Observer | None = None) -> ExtractionOutcome:
    """抽取一个场景。长场景分块时，每块各自重试；任何一块失败，整个场景记为失败。

    observer 在每次模型调用后收到一条记录（块号、第几次、耗时、token、校验问题、原始回复），供基准测试统计。
    """
    ranges = chunk_ranges(scene["lines"])
    tokens: list[int | None] = [None, None]
    parts: list[dict] = []
    attempts = 0
    for k, (start, end) in enumerate(ranges, 1):
        prompt = build_user_prompt(scene, character, prev_scene, start, end)
        observe = (lambda rec, k=k: observer({"chunk": k, "chunks": len(ranges), **rec})) if observer else _ignore
        obj, used, error = await _extract_chunk(call, prompt, start + 1, end, character, timeout, tokens, observe)
        attempts += used
        if obj is None:
            where = f"第 {k}/{len(ranges)} 块：" if len(ranges) > 1 else ""
            return ExtractionOutcome("failed", error=where + (error or "未知错误"), attempts=attempts,
                                     prompt_tokens=tokens[0], completion_tokens=tokens[1])
        parts.append(_prefix(obj, f"c{k}") if len(ranges) > 1 else obj)
    result = {
        "events": [ev for p in parts for ev in p["events"]],
        "views": [v for p in parts for v in p["views"]],
        "episode": parts[-1]["episode"],
        "cognitions": [c for p in parts for c in p["cognitions"]],
        "edges": [e for p in parts for e in p["edges"]],
    }
    return ExtractionOutcome("ok", result=result, attempts=attempts, prompt_tokens=tokens[0],
                             completion_tokens=tokens[1], quality=quality_flags(result))
