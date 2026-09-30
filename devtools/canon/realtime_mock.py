"""把剧情包导出为 run_realtime_dev.py 可直接导入的群聊记录：阿米娅作 bot，其余角色作群友，不经模型。"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK = ROOT.parent / "Arknights-Texts" / "exports" / "story_pack"
DEFAULT_PERSONA = Path(__file__).with_name("amiya_persona.txt")
DEFAULT_OUT = ROOT / "tests" / "mock_data"
CST = timezone(timedelta(hours=8))
BOT_ID = "char_002_amiya"
DOCTOR = ("博士", "doctor")
NARRATOR = ("旁白", "narrator")
FORMAT = "canon-realtime-mock-v1"


def parse_chapters(text: str) -> tuple[int, int]:
    first, _, last = text.partition("-")
    lo, hi = int(first), int(last or first)
    if lo > hi:
        raise SystemExit(f"章节范围无效：{text}")
    return lo, hi


def load_scenes(pack: Path, tier: str) -> list[dict]:
    scenes = []
    with (pack / "scenes.jsonl").open(encoding="utf-8") as f:
        for line in f:
            scene = json.loads(line)
            if scene["tier"] == tier:
                scenes.append(scene)
    if not scenes:
        raise SystemExit(f"{pack} 中没有 tier={tier} 的场景")
    return sorted(scenes, key=lambda s: s["narrative_pos"])


def bot_names(pack: Path) -> tuple[str, set[str]]:
    for entry in json.loads((pack / "characters.json").read_text(encoding="utf-8")):
        if entry["character"] == "amiya":
            return entry["display"], set(entry["confirmed_names"])
    raise SystemExit("characters.json 中没有 amiya")


def speaker_id(name: str) -> str:
    return "npc_" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]


def sender(line: dict, bot_display: str, bot_aliases: set[str], narration: str, override=None):
    if override and override["action"] == "delete":
        return None
    if override and override["action"] == "narrator":
        return "user", *NARRATOR
    if line["kind"] == "option":
        return "user", *DOCTOR
    name = override["target"] if override and override["action"] in ("map", "narrator") else line["spk"]
    if (line["kind"] == "dialogue" or override and override["action"] == "map") and name:
        if name in bot_aliases:
            return "assistant", bot_display, BOT_ID
        if name == DOCTOR[0]:
            return "user", *DOCTOR
        return "user", name, speaker_id(name)
    if narration == "drop":
        return None
    return "user", *NARRATOR


def build(args) -> tuple[list[dict], list[dict], dict]:
    lo, hi = parse_chapters(args.chapters)
    scenes = load_scenes(args.pack, args.tier)
    bot_display, bot_aliases = bot_names(args.pack)
    start = datetime.fromisoformat(args.start)
    if start.tzinfo is None:
        start = start.replace(tzinfo=CST)
    base = start.timestamp()
    step, gap = args.line_seconds, args.scene_gap_minutes * 60
    messages, linemap, chosen = [], [], []
    counts = {"assistant": 0, "doctor": 0, "narrator": 0, "npc": 0, "dropped": 0}
    speakers: set[str] = set()
    overrides = None
    rule_counts = {}
    action_counts = {}
    if args.speaker_map:
        entries = json.loads(args.speaker_map.read_text(encoding="utf-8"))
        overrides = {entry["line_key"]: entry for entry in entries}
        if len(overrides) != len(entries):
            raise SystemExit("speaker-map 包含重复 line_key")
    end_pos = None
    if args.end_scene:
        matches = [scene["narrative_pos"] for scene in scenes if scene["scene_key"] == args.end_scene]
        if len(matches) != 1:
            raise SystemExit(f"end-scene 无法唯一定位：{args.end_scene}")
        end_pos = matches[0]
    used_overrides = set()
    slot = 0
    for index, scene in enumerate(scenes):
        selected = (scene["chapter_no"] is not None and lo <= scene["chapter_no"] <= hi
                    and (end_pos is None or scene["narrative_pos"] <= end_pos))
        if selected:
            chosen.append(scene["scene_key"])
        for line in scene["lines"]:
            ts = base + slot * step + index * gap
            slot += 1
            if not selected:
                continue
            override = overrides.get(line["k"]) if overrides is not None else None
            if override is not None:
                if override["original_speaker"] != line["spk"]:
                    raise SystemExit(f"speaker-map 原说话人不匹配：{line['k']}")
                used_overrides.add(line["k"])
                rule = override["rule"]
                rule_counts[rule] = rule_counts.get(rule, 0) + 1
                action = override["action"]
                action_counts[action] = action_counts.get(action, 0) + 1
            who = sender(line, bot_display, bot_aliases, args.narration, override)
            if who is None or not line["text"].strip():
                counts["dropped"] += 1
                continue
            role, nickname, user_id = who
            message = {"role": role}
            if role == "assistant":
                message["platform"] = "internal"
            message.update({
                "nickname": nickname,
                "user_id": user_id,
                "time": datetime.fromtimestamp(ts, CST).strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": float(ts),
                "content": line["text"],
                "group_id": args.group_id,
            })
            messages.append(message)
            row = {"timestamp": float(ts), "line_key": line["k"],
                   "scene_key": scene["scene_key"], "kind": line["kind"], "spk": line["spk"]}
            if overrides is not None:
                row.update({"original_speaker": line["spk"], "cleaned_speaker": nickname,
                            "rule": override["rule"] if override else "original"})
            linemap.append(row)
            if role == "assistant":
                counts["assistant"] += 1
            elif user_id == DOCTOR[1]:
                counts["doctor"] += 1
            elif user_id == NARRATOR[1]:
                counts["narrator"] += 1
            else:
                counts["npc"] += 1
                speakers.add(nickname)
    if overrides is not None and set(overrides) != used_overrides:
        raise SystemExit(f"speaker-map 有 {len(set(overrides) - used_overrides)} 条不在选定范围内")
    if not messages:
        raise SystemExit(f"第 {lo}–{hi} 章没有可导出的行")
    pack_manifest = json.loads((args.pack / "manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "format": FORMAT,
        "pack": {key: pack_manifest.get(key) for key in ("pack_format", "data_version", "upstream_commit", "build_script_version")},
        "scenes_sha256": hashlib.sha256((args.pack / "scenes.jsonl").read_bytes()).hexdigest(),
        "tier": args.tier,
        "chapters": [lo, hi],
        "scene_keys": chosen,
        "timeline": {"start": start.isoformat(), "line_seconds": step, "scene_gap_minutes": args.scene_gap_minutes,
                     "scope": f"全部 tier={args.tier} 场景按 narrative_pos 统一排时，子集沿用同一时间戳"},
        "group_id": args.group_id,
        "bot": {"user_id": BOT_ID, "nickname": bot_display, "aliases": sorted(bot_aliases)},
        "narration": args.narration,
        "counts": {"messages": len(messages), **counts, "npc_speakers": len(speakers)},
        "first": messages[0]["time"],
        "last": messages[-1]["time"],
    }
    if overrides is not None:
        manifest["speaker_map"] = args.speaker_map.name
        manifest["speaker_map_sha256"] = hashlib.sha256(args.speaker_map.read_bytes()).hexdigest()
        manifest["rule_counts"] = rule_counts
        manifest["action_counts"] = action_counts
        if args.end_scene:
            manifest["end_scene"] = args.end_scene
    return messages, linemap, manifest


def persona_markdown(persona: Path, display: str) -> str:
    body = persona.read_text(encoding="utf-8").strip()
    return (f"# Persona prompt — {display}\n\n"
            f"<!-- 由 devtools/canon/realtime_mock.py 从 {persona.name} 生成，A 节即原文，未删改。 -->\n\n"
            f"## A. 人物设定（原始描述，权威）\n\n{body}\n")


def write(path: Path, text: str) -> str:
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    parser.add_argument("--tier", default="main")
    parser.add_argument("--chapters", default="0-5", help="闭区间，如 0-5、6-8、3")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--name", help="输出文件名前缀；默认 canon_amiya_<tier>_chAA-BB")
    parser.add_argument("--group-id", default="arknights_main")
    parser.add_argument("--start", default="2026-09-01T00:00:00+08:00")
    parser.add_argument("--line-seconds", type=int, default=10)
    parser.add_argument("--scene-gap-minutes", type=int, default=45, help="须大于断窗间隔 30 分钟")
    parser.add_argument("--narration", choices=("narrator", "drop"), default="narrator")
    parser.add_argument("--persona", type=Path, default=DEFAULT_PERSONA)
    parser.add_argument("--speaker-map", type=Path)
    parser.add_argument("--end-scene", help="包含指定场景，排除统一时间线中其后的场景")
    args = parser.parse_args(argv)
    if args.scene_gap_minutes <= 30:
        parser.error("--scene-gap-minutes 须大于 30，否则相邻场景会并进同一个窗口")
    messages, linemap, manifest = build(args)
    lo, hi = manifest["chapters"]
    name = args.name or f"canon_amiya_{args.tier}_ch{lo:02d}-{hi:02d}"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        f"{name}.json": json.dumps(messages, ensure_ascii=False, indent=1) + "\n",
        f"{name}.linemap.jsonl": "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in linemap),
    }
    if args.speaker_map:
        persona_text = persona_markdown(args.persona, manifest["bot"]["nickname"])
        manifest["files"] = {file: write(args.out_dir / file, content) for file, content in files.items()}
        manifest["files"]["amiya_persona.md"] = hashlib.sha256(persona_text.encode("utf-8")).hexdigest()
    else:
        files["amiya_persona.md"] = persona_markdown(args.persona, manifest["bot"]["nickname"])
        manifest["files"] = {file: write(args.out_dir / file, content) for file, content in files.items()}
    write(args.out_dir / f"{name}.manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1) + "\n")
    counts = manifest["counts"]
    print(f"{name}: {len(manifest['scene_keys'])} 场景，{counts['messages']} 条消息"
          f"（阿米娅 {counts['assistant']}、博士 {counts['doctor']}、旁白 {counts['narrator']}、"
          f"其他 {counts['npc']} 条 / {counts['npc_speakers']} 人，丢弃 {counts['dropped']}）")
    print(f"时间 {manifest['first']} → {manifest['last']}，输出 {args.out_dir}")


if __name__ == "__main__":
    main()
