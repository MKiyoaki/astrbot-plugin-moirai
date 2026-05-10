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
DEFAULT_DISTILLATION_SYSTEM_PROMPT = (
    "你是一个聊天记录分析助手。你的任务是为一段已经语义聚类好的对话片段提炼结构化信息。\n\n"
    "只输出单个 JSON 对象，不输出任何其他文字或 markdown 代码块，格式如下：\n"
    '{"topic": "...", "summary": "...", "chat_content_tags": ["...", "..."], "salience": 0.5, "confidence": 0.8, "inherit": false}\n\n'
    "字段说明：\n"
    "- topic: 该段对话的核心主题，简洁明了，30字以内\n"
    "- summary: 该段对话的摘要，提炼关键结论和信息，过滤口水话。"
    "按以下格式，每个小话题用 [What]/[Who]/[How] 三元组描述，多个小话题之间用 \" | \" 分隔，"
    "小话题数量与 chat_content_tags 对应（1-5个）。"
    "[What] 和 [How] 各写1-2句，说清楚具体发生了什么或得出了什么结论、以何种方式推进或结束（可包含情绪/态度/结果）；[Who] 保持简短只列人名。"
    "若提示词中提供了 [Bot 视角人格]，则每个三元组末尾还需加上 [Eval] 字段（从该人格视角对该话题的一句话评价）。"
    "格式示例（无人格）：\n"
    "  [What] Alice 分享了三首德彪西钢琴曲并逐一介绍了创作背景 [Who] Alice、Bob [How] Bob 提出疑问后两人深入探讨了印象派风格对现代音乐的影响 | [What] 话题转向了近期音乐会安排，Alice 推荐了一场即将上演的室内乐 [Who] Alice [How] 对话在期待中结束，未确定是否同去\n"
    "格式示例（有人格）：\n"
    "  [What] Alice 分享了三首德彪西钢琴曲并逐一介绍了创作背景 [Who] Alice、Bob [How] Bob 提出疑问后两人深入探讨了印象派风格对现代音乐的影响 [Eval] 这段交流展现了对方对古典音乐的真诚热情，值得深入记录\n"
    "- chat_content_tags: 2~5个关键词标签\n"
    "- salience: 重要性分值 0.0~1.0\n"
    "- confidence: 本次提取结果的置信度 0.0~1.0\n"
    "- inherit: 是否是上一个事件的直接延续（true/false）"
)

DEFAULT_EXTRACTOR_SYSTEM_PROMPT = (
    "你是一个聊天记录分析助手。你的任务是将一段连续的对话记录划分为一个或多个逻辑事件，并提取结构化信息。\n\n"
    "划分逻辑：\n"
    "1. 话题转换：当对话主题发生明显变化时，划分为新事件。\n"
    "2. 时间大跨度：当两条消息之间的时间间隔非常大（如超过数小时或数天）时，通常应划分为新事件。\n"
    "3. 连续性：如果对话虽然中断但随后继续讨论同一话题，可以视为同一事件的延续（设置 inherit 为 true）。\n\n"
    "输出格式（仅输出一个 JSON Array，包含一个或多个对象，不输出任何其他文字或 markdown 代码块）：\n"
    '[\n'
    '  {"start_idx": 0, "end_idx": 10, "topic": "...", "summary": "...", "chat_content_tags": ["...", "..."], "salience": 0.5, "confidence": 0.8, "inherit": false},\n'
    '  {"start_idx": 11, "end_idx": 19, "topic": "...", "summary": "...", "chat_content_tags": ["...", "..."], "salience": 0.3, "confidence": 0.9, "inherit": true}\n'
    ']\n\n'
    "字段说明：\n"
    "- start_idx: 该事件在提供的对话记录中的起始索引（从0开始）\n"
    "- end_idx: 该事件在提供的对话记录中的结束索引（包含）\n"
    "- topic: 该段对话的核心主题，简洁明了，30字以内\n"
    "- summary: 该段对话的摘要，提炼关键结论和信息，过滤掉口水话。"
    "按以下格式，每个小话题用 [What]/[Who]/[How] 三元组描述，多个小话题之间用 \" | \" 分隔，"
    "小话题数量与 chat_content_tags 对应（1-5个）。"
    "[What] 和 [How] 各写1-2句，说清楚具体发生了什么或得出了什么结论、以何种方式推进或结束（可包含情绪/态度/结果）；[Who] 保持简短只列人名。"
    "若提示词中提供了 [Bot 视角人格]，则每个三元组末尾还需加上 [Eval] 字段（从该人格视角对该话题的一句话评价）。"
    "格式示例（无人格）：\n"
    "  [What] Alice 分享了三首德彪西钢琴曲并逐一介绍了创作背景 [Who] Alice、Bob [How] Bob 提出疑问后两人深入探讨了印象派风格对现代音乐的影响 | [What] 话题转向了近期音乐会安排，Alice 推荐了一场即将上演的室内乐 [Who] Alice [How] 对话在期待中结束，未确定是否同去\n"
    "格式示例（有人格）：\n"
    "  [What] Alice 分享了三首德彪西钢琴曲并逐一介绍了创作背景 [Who] Alice、Bob [How] Bob 提出疑问后两人深入探讨了印象派风格对现代音乐的影响 [Eval] 这段交流展现了对方对古典音乐的真诚热情，值得深入记录\n"
    "- chat_content_tags: 2~5个关键词标签\n"
    "- salience: 重要性分值 0.0~1.0\n"
    "- confidence: 本次提取结果的置信度 0.0~1.0\n"
    "- inherit: 是否继承上一个已知事件的主题（即本段是上段的延续）"
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
    "只输出单行JSON，字段：ipc_orientation（以下8种之一：亲和/活跃/掌控/高傲/冷淡/孤避/顺应/谦让）、"
    "benevolence（亲和度，-1.0到1.0的浮点数）、power（支配度，-1.0到1.0的浮点数）、"
    "confidence（0.0到1.0 Hendrick 的浮点数）。不要输出任何其他内容。"
)


@dataclass
class SynthesisConfig:
    llm_timeout: float = 30.0
    max_events: int = 10
    persona_system_prompt: str = _DEFAULT_PERSONA_SYSTEM_PROMPT
    impression_system_prompt: str = _DEFAULT_IMPRESSION_SYSTEM_PROMPT


_DEFAULT_SUMMARY_SYSTEM_PROMPT = (
    "你是一个对话记录摘要助手。根据提供的事件列表，生成本期群组活动摘要。"
    "只输出[主要话题]部分的正文内容，不超过300字，对时段内所有事件进行总结。"
    "不要输出标题、Markdown装饰或任何其他内容。只输出正文。"
)

_DEFAULT_SUMMARY_MOOD_PROMPT = (
    "你是一个社交关系分析助手。根据以下对话事件，分析群体情感动态。"
    "只输出单行JSON，字段：orientation（亲和/活跃/掌控/高傲/冷淡/孤避/顺应/谦让之一）、"
    "benevolence（亲和度，-1.0到1.0的浮点数）、power（支配度，-1.0到1.0的浮点数）、"
    "positions（对象，key为用户UID，value为该用户的orientation，8种之一）。"
    "不要输出任何其他内容。"
)


@dataclass
class SummaryConfig:
    llm_timeout: float = 45.0
    max_events: int = 20
    word_limit: int = 300
    system_prompt: str = _DEFAULT_SUMMARY_SYSTEM_PROMPT
    mood_source: str = "llm"  # "llm" | "impression_db" (see TODO.md for Option A details)
    mood_prompt: str = _DEFAULT_SUMMARY_MOOD_PROMPT


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
class IPCConfig:
    enabled: bool = True
    bigfive_x_messages: int = 10
    bigfive_llm_timeout: float = 30.0


@dataclass
class ExtractorConfig:
    max_context_messages: int = 20
    llm_timeout: float = 30.0
    system_prompt: str = DEFAULT_EXTRACTOR_SYSTEM_PROMPT
    distillation_system_prompt: str = DEFAULT_DISTILLATION_SYSTEM_PROMPT
    strategy: str = "llm"  # "llm" or "semantic"
    semantic_clustering_eps: float = 0.45
    semantic_clustering_min_samples: int = 2
    persona_influenced_summary: bool = False


@dataclass
class ContextConfig:
    vcm_enabled: bool = True
    max_sessions: int = 100
    session_idle_seconds: int = 3600
    window_size: int = 50


@dataclass
class CleanupConfig:
    enabled: bool = True
    threshold: float = 0.3
    interval_days: int = 7


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    model: str = "BAAI/bge-small-zh-v1.5"
    api_url: str = ""
    api_key: str = ""
    batch_size: int = 1
    concurrency: int = 1
    batch_interval_ms: int = 0
    request_interval_ms: int = 0
    failure_tolerance_ratio: float = 0.0
    retry_max: int = 3
    retry_delay_ms: int = 1000


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
            max_messages=self._int("boundary_max_messages", 20),
            max_duration_minutes=self._float("boundary_max_duration_minutes", 60.0),
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
        mood_prompt = self._str("summary_mood_system_prompt", "").strip()
        limit = self._int("summary_word_limit", 300)
        limit = max(200, min(500, limit))
        return SummaryConfig(
            llm_timeout=self._float("summary_llm_timeout_seconds", 45.0),
            max_events=self._int("summary_max_events", 20),
            word_limit=limit,
            system_prompt=prompt or _DEFAULT_SUMMARY_SYSTEM_PROMPT,
            mood_source=self._str("summary_mood_source", "llm"),
            mood_prompt=mood_prompt or _DEFAULT_SUMMARY_MOOD_PROMPT,
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

    def get_ipc_config(self) -> IPCConfig:
        return IPCConfig(
            enabled=self._bool("ipc_enabled", True),
            bigfive_x_messages=self._int("bigfive_x_messages", 10),
            bigfive_llm_timeout=self._float("bigfive_llm_timeout_seconds", 30.0),
        )

    def get_extractor_config(self) -> ExtractorConfig:
        custom_prompt = self._str("extractor_system_prompt", "").strip()
        custom_distill_prompt = self._str("distillation_system_prompt", "").strip()
        return ExtractorConfig(
            max_context_messages=self._int("context_window_size", 50),
            llm_timeout=self._float("extractor_llm_timeout_seconds", 30.0),
            system_prompt=custom_prompt or DEFAULT_EXTRACTOR_SYSTEM_PROMPT,
            distillation_system_prompt=custom_distill_prompt or DEFAULT_DISTILLATION_SYSTEM_PROMPT,
            strategy=self._str("extraction_strategy", "llm"),
            semantic_clustering_eps=self._float("semantic_clustering_eps", 0.45),
            semantic_clustering_min_samples=self._int("semantic_clustering_min_samples", 2),
            persona_influenced_summary=self._bool("persona_influenced_summary", False),
        )

    def get_context_config(self) -> ContextConfig:
        return ContextConfig(
            vcm_enabled=self._bool("vcm_enabled", True),
            max_sessions=self._int("context_max_sessions", 100),
            session_idle_seconds=self._int("context_session_idle_seconds", 3600),
            window_size=self._int("context_window_size", 50),
        )

    def get_cleanup_config(self) -> CleanupConfig:
        return CleanupConfig(
            enabled=self._bool("memory_cleanup_enabled", True),
            threshold=self._float("memory_cleanup_threshold", 0.3),
            interval_days=self._int("memory_cleanup_interval_days", 7),
        )

    def get_embedding_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            provider=self._str("embedding_provider", "local"),
            model=self._str("embedding_model", "BAAI/bge-small-zh-v1.5"),
            api_url=self._str("embedding_api_url", ""),
            api_key=self._str("embedding_api_key", ""),
            batch_size=self._int("embedding_batch_size", 1),
            concurrency=self._int("embedding_concurrency", 1),
            batch_interval_ms=self._int("embedding_batch_interval_ms", 0),
            request_interval_ms=self._int("embedding_request_interval_ms", 0),
            failure_tolerance_ratio=self._float("embedding_failure_tolerance_ratio", 0.0),
            retry_max=self._int("embedding_retry_max", 3),
            retry_delay_ms=self._int("embedding_retry_delay_ms", 1000),
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
    def webui_password(self) -> str:
        return self._str("webui_password", "").strip()

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

    @property
    def impression_update_alpha(self) -> float:
        return self._float("impression_update_alpha", 0.3)

    # ------------------------------------------------------------------
    # Raw dict passthrough (for subsystems that need the full dict)
    # ------------------------------------------------------------------

    def as_dict(self) -> dict:
        return dict(self._raw)
