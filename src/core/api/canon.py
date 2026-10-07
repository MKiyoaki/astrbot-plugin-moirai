"""canon 原作剧情记忆的公共接口：只读访问、一轮对话、Core 生成接入、人格映射与超参数。"""
from __future__ import annotations

from ..adapters.core_canon import CanonGeneration
from ..canon.config import CanonConfig, CanonPersona, parse_persona_map
from ..canon.domain.character import CharacterProfile, profile_for
from ..canon.read.reader import CanonReader
from ..canon.settings import DATASET, SETTINGS, CanonSettings, load_settings
from ..canon.turn.canon_turn import CanonTurn
from ..canon.turn.gateway import CheckReport
