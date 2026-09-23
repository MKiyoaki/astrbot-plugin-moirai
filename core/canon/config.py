"""canon 配置：开关、路径、人格映射与检索预算。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DOCTOR_MODES = ("off", "all", "bound")


@dataclass(frozen=True)
class CanonPersona:
    """一个人格桶扮演哪个原作角色，以及对方是否视为博士。"""
    character: str
    user_is_doctor: str = "off"
    doctor_uids: tuple[str, ...] = ()
    time_point: str = "latest"


@dataclass(frozen=True)
class CanonConfig:
    enabled: bool = False
    db_path: str = ""
    pack_path: str = ""
    persona_map: dict[str, CanonPersona] = field(default_factory=dict)
    persona_map_error: str | None = None
    top_k: int = 5
    token_budget: int = 600
    evidence_lines: int = 3
    time_filter: bool = False
    extract_concurrency: int = 2
    extract_timeout: int = 300

    def resolve_db_path(self, data_dir: Path) -> Path:
        return Path(self.db_path) if self.db_path else Path(data_dir) / "canon" / "canon.sqlite"

    def resolve_pack_path(self, data_dir: Path) -> Path:
        return Path(self.pack_path) if self.pack_path else Path(data_dir) / "canon" / "story_pack"


def parse_persona_map(raw) -> tuple[dict[str, CanonPersona], str | None]:
    """解析 canon_persona_map。格式有任何错误都返回空映射和错误说明，canon 对所有人格都不生效。"""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return {}, None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError) as exc:
        return {}, f"不是合法的 JSON：{exc}"
    if not isinstance(data, dict):
        return {}, "顶层必须是对象"
    out: dict[str, CanonPersona] = {}
    for name, item in data.items():
        if not isinstance(name, str) or not name.strip():
            return {}, "人格桶名不能为空"
        if not isinstance(item, dict):
            return {}, f"{name}：必须是对象"
        unknown = set(item) - {"character", "user_is_doctor", "doctor_uids", "time_point"}
        if unknown:
            return {}, f"{name}：未知字段 {sorted(unknown)}"
        character = item.get("character")
        if not isinstance(character, str) or not character.strip():
            return {}, f"{name}：缺少 character"
        mode = item.get("user_is_doctor", "off")
        if mode not in DOCTOR_MODES:
            return {}, f"{name}：user_is_doctor 只能是 {'/'.join(DOCTOR_MODES)}"
        uids = item.get("doctor_uids", [])
        if not isinstance(uids, list) or not all(isinstance(u, str) and u for u in uids):
            return {}, f"{name}：doctor_uids 必须是字符串数组"
        time_point = item.get("time_point", "latest")
        if not isinstance(time_point, str) or not time_point.strip():
            return {}, f"{name}：time_point 必须是 latest 或 scene_key"
        out[name.strip()] = CanonPersona(character.strip(), mode, tuple(uids), time_point.strip())
    return out, None
