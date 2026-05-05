"""Centralised plugin configuration.

Reads the raw dict that AstrBot passes via ``self.config`` and exposes
typed accessors for each subsystem.  Keeps main.py free of scattered
``cfg.get(...)`` calls and gives each module a dedicated config object
it can be unit-tested against.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.boundary.detector import BoundaryConfig

# ---------------------------------------------------------------------------
# Default extractor system prompt (kept here so _conf_schema.json can
# reference the same text as the factory default).
# ---------------------------------------------------------------------------
DEFAULT_EXTRACTOR_SYSTEM_PROMPT = (
    "你是一个聊天记录分析助手。根据对话内容提取结构化信息，严格按照指定 JSON 格式输出，不输出任何其他文字。\n\n"
    "输出格式（仅输出此 JSON，无前缀、无后缀、无 markdown 代码块）：\n"
    '{"topic": "...", "chat_content_tags": ["...", "..."], "salience": 0.5, "confidence": 0.8}\n\n'
    "字段说明：\n"
    "- topic: 对话核心主题，简洁明了，30字以内\n"
    "- chat_content_tags: 2~5个关键词标签，用于检索和分类\n"
    "- salience: 重要性分值 0.0~1.0（重要事件/情绪事件偏高，日常闲聊偏低）\n"
    "- confidence: 本次提取结果的置信度 0.0~1.0"
)


@dataclass
class DecayConfig:
    lambda_: float = 0.01         # exp(-0.01) ≈ 0.99; half-life ≈ 69 days
    archive_threshold: float = 0.05  # events below this salience are archived


_DEFAULT_PERSONA_SYSTEM_PROMPT = (
    "你是一个用户画像分析助手。根据提供的事件记录，更新用户属性。"
    "只输出单行JSON，字段：description（≤50字符）、affect_type（积极/消极/中性之一）、"
    "content_tags（list，≤5项）。不要输出任何其他内容。"
)

_DEFAULT_IMPRESSION_SYSTEM_PROMPT = (
    "你是一个社交关系分析助手。根据对话事件，更新对某人的印象。"
    "只输出单行JSON，字段：relation_type（friend/colleague/stranger/family/rival之一）、"
    "affect（-1.0到1.0的浮点数）、intensity（0.0到1.0的浮点数）、"
    "confidence（0.0到1.0的浮点数）。不要输出任何其他内容。"
)


@dataclass
class SynthesisConfig:
    llm_timeout: float = 30.0
    max_events: int = 10
    persona_system_prompt: str = _DEFAULT_PERSONA_SYSTEM_PROMPT
    impression_system_prompt: str = _DEFAULT_IMPRESSION_SYSTEM_PROMPT


_DEFAULT_SUMMARY_SYSTEM_PROMPT = (
    "你是一个对话记录摘要助手。根据提供的事件列表，生成本期群组活动摘要。"
    "用Markdown格式输出，包含：本期主要话题（无序列表）、成员活跃度（简短说明）、"
    "值得关注的事件。总字数不超过300字。不要输出任何其他内容。"
)


@dataclass
class SummaryConfig:
    llm_timeout: float = 45.0
    max_events: int = 20
    system_prompt: str = _DEFAULT_SUMMARY_SYSTEM_PROMPT


@dataclass
class RetrievalConfig:
    bm25_limit: int = 20              # BM25 candidate pool size
    vec_limit: int = 20               # Vector candidate pool size
    final_limit: int = 10             # Results after fusion
    rrf_k: int = 60                   # RRF k (original paper default)
    salience_weight: float = 0.3      # Weight for event.salience in final score
    recency_weight: float = 0.2       # Weight for recency decay in final score
    relevance_weight: float = 0.5     # Weight for normalised RRF score
    recency_half_life_days: float = 30.0  # Half-life for recency exponential decay
    vector_fallback_enabled: bool = True  # Fall back to vec-only when BM25 returns nothing
    active_only: bool = True          # Exclude archived events from search


# Sentinel strings used to wrap injected memory blocks for auto-clear.
MEMORY_INJECTION_HEADER = "<!-- EM:MEMORY:START -->"
MEMORY_INJECTION_FOOTER = "<!-- EM:MEMORY:END -->"
# Prefix for fake tool-call IDs so they can be cleaned up later.
FAKE_TOOL_CALL_ID_PREFIX = "em_recall_"


@dataclass
class InjectionConfig:
    position: str = "system_prompt"
    """Where to inject recalled memory into the ProviderRequest.
    One of: system_prompt | user_message_before | user_message_after | fake_tool_call
    """
    auto_clear: bool = True
    """Strip previous injection markers from the request before re-injecting."""
    token_budget: int = 800
    """Maximum tokens to fill with injected memory text."""


@dataclass
class ExtractorConfig:
    max_context_messages: int = 20
    llm_timeout: float = 30.0
    system_prompt: str = DEFAULT_EXTRACTOR_SYSTEM_PROMPT


class PluginConfig:
    """Wraps the raw AstrBot config dict and provides typed, named accessors.

    Usage in main.py::

        cfg = PluginConfig(self.config or {})
        boundary_cfg = cfg.get_boundary_config()
        extractor_cfg = cfg.get_extractor_config()
        port = cfg.webui_port
    """

    def __init__(self, raw: dict) -> None:
        self._raw = raw

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _get(self, key: str, default):
        return self._raw.get(key, default)

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self._raw[key])
        except (KeyError, TypeError, ValueError):
            return default

    def _float(self, key: str, default: float) -> float:
        try:
            return float(self._raw[key])
        except (KeyError, TypeError, ValueError):
            return default

    def _bool(self, key: str, default: bool) -> bool:
        val = self._raw.get(key)
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        return str(val).lower() in {"1", "true", "yes"}

    def _str(self, key: str, default: str) -> str:
        val = self._raw.get(key)
        return str(val) if val is not None else default

    # ------------------------------------------------------------------
    # Subsystem config objects
    # ------------------------------------------------------------------

    def get_boundary_config(self) -> BoundaryConfig:
        return BoundaryConfig(
            time_gap_minutes=self._float("boundary_time_gap_minutes", 30.0),
            max_messages=self._int("boundary_max_messages", 50),
            max_duration_minutes=self._float("boundary_max_duration_minutes", 60.0),
            topic_drift_threshold=self._float("boundary_topic_drift_threshold", 0.6),
            topic_check_message_count=self._int("boundary_topic_check_message_count", 20),
        )

    def get_decay_config(self) -> DecayConfig:
        return DecayConfig(
            lambda_=self._float("decay_lambda", 0.01),
            archive_threshold=self._float("decay_archive_threshold", 0.05),
        )

    def get_synthesis_config(self) -> SynthesisConfig:
        persona_prompt = self._str("synthesis_persona_system_prompt", "").strip()
        impression_prompt = self._str("synthesis_impression_system_prompt", "").strip()
        return SynthesisConfig(
            llm_timeout=self._float("synthesis_llm_timeout_seconds", 30.0),
            max_events=self._int("synthesis_max_events", 10),
            persona_system_prompt=persona_prompt or _DEFAULT_PERSONA_SYSTEM_PROMPT,
            impression_system_prompt=impression_prompt or _DEFAULT_IMPRESSION_SYSTEM_PROMPT,
        )

    def get_summary_config(self) -> SummaryConfig:
        prompt = self._str("summary_system_prompt", "").strip()
        return SummaryConfig(
            llm_timeout=self._float("summary_llm_timeout_seconds", 45.0),
            max_events=self._int("summary_max_events", 20),
            system_prompt=prompt or _DEFAULT_SUMMARY_SYSTEM_PROMPT,
        )

    def get_retrieval_config(self) -> RetrievalConfig:
        return RetrievalConfig(
            bm25_limit=self._int("retrieval_bm25_limit", 20),
            vec_limit=self._int("retrieval_vec_limit", 20),
            final_limit=self._int("retrieval_top_k", 10),
            rrf_k=self._int("retrieval_rrf_k", 60),
            salience_weight=self._float("retrieval_salience_weight", 0.3),
            recency_weight=self._float("retrieval_recency_weight", 0.2),
            relevance_weight=self._float("retrieval_relevance_weight", 0.5),
            recency_half_life_days=self._float("retrieval_recency_half_life_days", 30.0),
            vector_fallback_enabled=self._bool("retrieval_vector_fallback_enabled", True),
            active_only=self._bool("retrieval_active_only", True),
        )

    def get_injection_config(self) -> InjectionConfig:
        pos = self._str("injection_position", "system_prompt").strip()
        valid = {"system_prompt", "user_message_before", "user_message_after", "fake_tool_call"}
        return InjectionConfig(
            position=pos if pos in valid else "system_prompt",
            auto_clear=self._bool("injection_auto_clear", True),
            token_budget=self._int("retrieval_token_budget", 800),
        )

    def get_extractor_config(self) -> ExtractorConfig:
        custom_prompt = self._str("extractor_system_prompt", "").strip()
        return ExtractorConfig(
            max_context_messages=self._int("extractor_max_context_messages", 20),
            llm_timeout=self._float("extractor_llm_timeout_seconds", 30.0),
            system_prompt=custom_prompt or DEFAULT_EXTRACTOR_SYSTEM_PROMPT,
        )

    # ------------------------------------------------------------------
    # WebUI
    # ------------------------------------------------------------------

    @property
    def webui_enabled(self) -> bool:
        return self._bool("webui_enabled", True)

    @property
    def webui_port(self) -> int:
        return self._int("webui_port", 2653)

    @property
    def webui_auth_enabled(self) -> bool:
        return self._bool("webui_auth_enabled", True)

    @property
    def webui_session_hours(self) -> int:
        return self._int("webui_session_hours", 24)

    @property
    def webui_sudo_minutes(self) -> int:
        return self._int("webui_sudo_minutes", 30)

    # ------------------------------------------------------------------
    # Embedding / retrieval
    # ------------------------------------------------------------------

    @property
    def embedding_enabled(self) -> bool:
        return self._bool("embedding_enabled", True)

    @property
    def embedding_model(self) -> str:
        return self._str("embedding_model", "BAAI/bge-small-zh-v1.5")

    @property
    def retrieval_top_k(self) -> int:
        return self._int("retrieval_top_k", 10)

    @property
    def retrieval_token_budget(self) -> int:
        return self._int("retrieval_token_budget", 800)

    # ------------------------------------------------------------------
    # Relation / social graph
    # ------------------------------------------------------------------

    @property
    def relation_enabled(self) -> bool:
        return self._bool("relation_enabled", True)

    # ------------------------------------------------------------------
    # Data safety
    # ------------------------------------------------------------------

    @property
    def migration_auto_backup(self) -> bool:
        return self._bool("migration_auto_backup", True)

    # ------------------------------------------------------------------
    # Memory isolation
    # ------------------------------------------------------------------

    @property
    def memory_isolation_enabled(self) -> bool:
        return self._bool("memory_isolation_enabled", True)

    @property
    def persona_isolation_enabled(self) -> bool:
        return self._bool("persona_isolation_enabled", False)

    # ------------------------------------------------------------------
    # Periodic tasks
    # ------------------------------------------------------------------

    @property
    def decay_interval_seconds(self) -> int:
        return self._int("decay_interval_hours", 24) * 3600

    @property
    def summary_interval_seconds(self) -> int:
        return self._int("summary_interval_hours", 24) * 3600

    @property
    def persona_synthesis_interval_seconds(self) -> int:
        return self._int("persona_synthesis_interval_hours", 168) * 3600

    @property
    def impression_aggregation_interval_seconds(self) -> int:
        return self._int("impression_aggregation_interval_hours", 168) * 3600

    @property
    def file_watcher_poll_seconds(self) -> int:
        return self._int("file_watcher_poll_seconds", 30)

    @property
    def impression_event_trigger_enabled(self) -> bool:
        return self._bool("impression_event_trigger_enabled", True)

    @property
    def impression_event_trigger_threshold(self) -> int:
        return self._int("impression_event_trigger_threshold", 5)

    @property
    def impression_trigger_debounce_hours(self) -> float:
        return self._float("impression_trigger_debounce_hours", 1.0)

    # ------------------------------------------------------------------
    # Raw dict passthrough (for subsystems that need the full dict)
    # ------------------------------------------------------------------

    def as_dict(self) -> dict:
        return dict(self._raw)
