"""canon 的超参数与数据集内容：数值只写在 configs/canon/default.yaml，数据集专有内容在 configs/data/。

导入时读取一次：src/main.py 交来的配置优先，其次组合 configs/（环境变量 MOIRAI_CONFIG_OVERRIDES 的覆盖项生效），
都不可用时直接读两份默认文件。运行时与工具因此读同一份值；AstrBot 面板的 canon_top_k、canon_token_budget、
canon_evidence_lines 仍按调用参数传入，覆盖这里的默认。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from omegaconf import DictConfig, OmegaConf

from ..utils.config_utils import CONFIG_DIR, current


@dataclass
class ExtractSettings:
    prompt_version: str
    max_attempts: int
    max_reported_errors: int
    text_limits: dict[str, list[int]]
    max_range_span: int
    max_uncovered_run: int
    max_shared_lines: int
    chunk_trigger: int
    chunk_limit: int


@dataclass
class FactSettings:
    prompt_version: str
    max_prompt_chars: int
    max_attempts: int


@dataclass
class ImportSettings:
    vector_batch: int


@dataclass
class RecallSettings:
    turn_budget: int
    verify_extra: int
    window_before: int
    window_after: int
    probe_names: int
    probe_collections: int
    axis_rows: int
    axis_topics: int
    axis_neighbours: int
    recent_rows: int
    recent_events: int


@dataclass
class RetrievalSettings:
    speaker_view: bool
    query_instruction: str
    rerank_blend: float
    route_similarity: float
    fusion_k: int
    channel_weights: dict[str, float]


@dataclass
class TurnSettings:
    max_tool_rounds: int
    archive_sections: int
    archive_chars: int


@dataclass
class GatewaySettings:
    align_min: float
    min_quote: int


@dataclass
class QuerySettings:
    max_subjects: int
    route_idf_mass: float


@dataclass
class OverviewSettings:
    max_events: int
    story_max_events: int
    max_scenes: int
    max_candidates: int


@dataclass
class ReaderSettings:
    lexical_limit: int
    entity_limit: int
    per_scene: int
    recent_months: int


@dataclass
class AnchorSettings:
    tolerance_months: int


@dataclass
class CalendarSettings:
    window: int
    epigraph_years: int
    match: float


@dataclass
class EvalSettings:
    tokens_per_char: list[float]
    match_threshold: float
    cover_share: float
    flagged_limit: int
    max_events_hint: int
    fragment_span: int
    fragment_scene_lines: int
    low_coverage: float


@dataclass
class CanonSettings:
    extract: ExtractSettings
    facts: FactSettings
    importer: ImportSettings
    recall: RecallSettings
    retrieval: RetrievalSettings
    turn: TurnSettings
    gateway: GatewaySettings
    query: QuerySettings
    overview: OverviewSettings
    reader: ReaderSettings
    anchors: AnchorSettings
    calendar: CalendarSettings
    eval: EvalSettings


def _composed() -> DictConfig:
    try:
        return current()
    except Exception:
        return OmegaConf.create({
            "canon": OmegaConf.load(CONFIG_DIR / "canon" / "default.yaml"),
            "data": OmegaConf.load(CONFIG_DIR / "data" / "arknights.yaml"),
        })


def load_settings(canon: Any) -> CanonSettings:
    """按 CanonSettings 的类型校验一组 canon 配置；缺键、多键或类型不符都报错。"""
    return OmegaConf.to_object(OmegaConf.merge(OmegaConf.structured(CanonSettings), canon))


_CONFIG = _composed()
SETTINGS: CanonSettings = load_settings(_CONFIG.canon)
DATASET: dict[str, Any] = OmegaConf.to_container(_CONFIG.data, resolve=True)
