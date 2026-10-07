"""Centralised plugin configuration.

Reads the raw dict that AstrBot passes via ``self.config`` and exposes
typed accessors for each subsystem.  Keeps main.py free of scattered
``cfg.get(...)`` calls and gives each module a dedicated config object
it can be unit-tested against.
"""
from __future__ import annotations

import os

from dataclasses import dataclass, field
from pathlib import Path

from core.boundary.detector import BoundaryConfig
from core.utils.i18n import LANG_ZH, LANG_EN, LANG_JA
from core.utils.prompts.prompt_memory_utils import (
    DEFAULT_DISTILLATION_SYSTEM_PROMPT,
    DEFAULT_EXTRACTOR_SYSTEM_PROMPT,
    DEFAULT_IMPRESSION_SYSTEM_PROMPT,
    DEFAULT_PERSONA_SYSTEM_PROMPT,
    DEFAULT_REANALYZE_IMPRESSION_SYSTEM_PROMPT,
    DEFAULT_SUMMARY_MOOD_PROMPT,
    DEFAULT_SUMMARY_SYSTEM_PROMPT,
    DEFAULT_SUMMARY_UNIFIED_PROMPT,
)


@dataclass
class DecayConfig:
    lambda_: float = 0.01             # Per-pass decay rate (e.g. 0.01 = 1%)
    archive_threshold: float = 0.05   # Status='archived' if salience falls below this


@dataclass
class BackupConfig:
    enabled: bool = True
    retention_days: int = 7


@dataclass
class SynthesisConfig:
    retry_until_success: bool = False
    retry_delay_seconds: float = 2.0
    llm_timeout: float = 30.0
    max_events: int = 10
    persona_system_prompt: str = DEFAULT_PERSONA_SYSTEM_PROMPT
    impression_system_prompt: str = DEFAULT_IMPRESSION_SYSTEM_PROMPT
    reanalyze_system_prompt: str = DEFAULT_REANALYZE_IMPRESSION_SYSTEM_PROMPT
    language: str = LANG_ZH
    llm_provider: str | None = None
    # weight for new synthesis vs existing scores (0=freeze, 1=replace)
    ema_alpha: float = 0.30


@dataclass
class SummaryConfig:
    retry_until_success: bool = False
    retry_delay_seconds: float = 2.0
    llm_timeout: float = 45.0
    max_events: int = 20
    word_limit: int = 300
    system_prompt: str = DEFAULT_SUMMARY_SYSTEM_PROMPT
    mood_source: str = "llm"
    mood_prompt: str = DEFAULT_SUMMARY_MOOD_PROMPT
    unified_prompt: str = DEFAULT_SUMMARY_UNIFIED_PROMPT
    language: str = LANG_ZH
    llm_provider: str | None = None


@dataclass
class RetrievalConfig:
    bm25_limit: int = 20              # BM25 candidate pool size
    vec_limit: int = 20               # Vector candidate pool size
    final_limit: int = 3              # Results after fusion
    active_limit: int = 5             # Max results for active retrieval tool
    rrf_k: int = 60                   # RRF k (original paper default is 60)
    salience_weight: float = 0.1      # Weight for event.salience in final score
    recency_weight: float = 0.2       # Weight for recency decay in final score
    relevance_weight: float = 0.5     # Weight for normalised RRF score
    recency_half_life_days: float = 30.0  # Half-life for recency exponential decay
    # Fall back to vec-only when BM25 returns nothing
    vector_fallback_enabled: bool = True
    active_only: bool = True          # Exclude archived events from search
    weighted_random: bool = False     # Use softmax sampling instead of Top-K
    sampling_temperature: float = 1.0  # Temperature for softmax sampling


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
    commitment_max_items: int = 3
    """Maximum relevant open commitments injected, matching the three-event recall default."""
    persona_view_injection_enabled: bool = False
    """Reserved switch; injecting persona views is deferred, even when this is set."""
    show_thinking_process: bool = False
    """Prepend memory-retrieval debug info to each reply."""
    show_system_prompt: bool = False
    """Prepend the pre-injection system prompt to replies for admin senders."""
    show_injection_summary: bool = False
    """Prepend a sanitized summary of Moirai's actual injected prompt content."""
    impression_injection_enabled: bool = True
    """Inject low-weight social impression hints into the system prompt."""
    impression_injection_max_items: int = 3
    """Maximum social impression rows injected for the active sender."""
    impression_injection_min_confidence: float = 0.2
    """Minimum confidence required before a social impression can be injected."""
    account_merge_synthesis_only: bool = False
    """When True, bound-account merging applies to persona synthesis only;
    recall does not expand a sender_uid across its bound group."""


@dataclass
class IPCConfig:
    enabled: bool = True
    bigfive_x_messages: int = 10
    bigfive_llm_timeout: float = 30.0


@dataclass
class ExtractorConfig:
    retry_until_success: bool = False
    eval_concurrency: int = 1
    llm_retry_delay_seconds: float = 2.0
    max_context_messages: int = 20
    llm_timeout: float = 30.0
    llm_max_retries: int = 2
    llm_timeout_growth: float = 1.5
    requeue_attempts: int = 2
    requeue_delay_seconds: float = 60.0
    system_prompt: str = DEFAULT_EXTRACTOR_SYSTEM_PROMPT
    distillation_system_prompt: str = DEFAULT_DISTILLATION_SYSTEM_PROMPT
    strategy: str = "llm"  # "llm" or "semantic"
    llm_segmentation: bool = True
    segmentation_messages_per_segment: int = 12
    segmentation_timeout: float = 30.0
    semantic_clustering_eps: float = 0.45
    semantic_clustering_min_samples: int = 2
    persona_influenced_summary: bool = False
    # Deprecated: configure explicit bindings and the global override in Core.
    bot_persona_name_override: str = ""
    tag_normalization_threshold: float = 0.85
    # A newly seen tag is only a candidate; it must recur this many times
    # before other tags may be normalized onto it.
    tag_promotion_min_df: int = 3
    # Candidates that never reach tag_promotion_min_df expire after this long.
    tag_candidate_ttl_days: int = 30
    tag_seeds: list[str] = field(
        default_factory=lambda: [
            "社交", "日常", "技术", "知识", "工作", "娱乐", "艺术", "情感", "资讯"
        ]
    )
    language: str = LANG_ZH
    llm_provider: str | None = None


@dataclass
class TypeSafeConfig:
    """External topic and interaction classification through the TypeSafe API.

    Off by default: with ``enabled`` false or no key, nothing is sent anywhere.
    """
    enabled: bool = False
    topic_enabled: bool = True
    event_enabled: bool = True
    api_key: str = ""
    base_url: str = "https://api.typesafe.ai"
    model: str = "jev-latest"
    timeout: float = 10.0
    # Low Choice answers are stored but not adopted; the same threshold selects
    # active Noul interaction groups. Not calibrated against real data yet.
    min_confidence: float = 0.5
    custom_tag_min_score: float = 0.7
    topic_backfill: bool = True
    event_backfill: bool = False
    llm_fallback: bool = True

    @property
    def active(self) -> bool:
        return (
            self.enabled
            and bool(self.api_key)
            and (self.topic_enabled or self.event_enabled)
        )

    @property
    def interaction_via_typesafe(self) -> bool:
        return self.event_enabled and self.active

    @property
    def interaction_via_llm(self) -> bool:
        """The interaction axis runs on the extraction LLM instead.

        Independent of ``enabled``: turning TypeSafe off is exactly when the
        fallback is wanted, because the event tags are derived from this axis.
        """
        return (
            self.event_enabled
            and self.llm_fallback
            and not self.interaction_via_typesafe
        )


@dataclass
class ContextConfig:
    vcm_enabled: bool = True
    max_sessions: int = 100
    session_idle_seconds: int = 3600
    window_size: int = 50
    max_history_messages: int = 1000
    cleanup_batch_size: int = 50


@dataclass
class CleanupConfig:
    enabled: bool = True
    threshold: float = 0.3
    interval_days: int = 7
    retention_days: int = 30
    raw_message_retention_days: int = 14


@dataclass
class MaintenanceConfig:
    """Periodic window flush — proactively turns stable prefixes into Events
    so 0-bot user-chatter doesn't sit unprocessed until a boundary fires."""
    periodic_flush_enabled: bool = True
    periodic_flush_minutes: float = 30.0   # 建议 15–120
    periodic_flush_tail_keep: int = 10     # 建议 3–30


@dataclass
class EmbeddingConfig:
    retry_until_success: bool = False
    provider: str = "local"
    model: str = "BAAI/bge-small-zh-v1.5"
    api_url: str = ""
    api_key: str = ""
    batch_size: int = 50
    request_batch_size: int = 16
    concurrency: int = 1
    batch_interval_ms: int = 50
    request_interval_ms: int = 0
    failure_tolerance_ratio: float = 0.02
    retry_max: int = 3
    retry_delay_ms: int = 30000
    timeout_seconds: float = 60.0
    dimensions: int = 0


@dataclass
class RerankConfig:
    enabled: bool = False
    model: str = "arc:rerankvl"
    api_url: str = ""
    api_key: str = ""
    max_candidates: int = 40
    timeout_seconds: float = 60.0
    retry_max: int = 1


class PluginConfig:
    """Wraps the raw AstrBot config dict and provides typed, named accessors.

    Usage in main.py::

        cfg = PluginConfig(self.config or {})
        boundary_cfg = cfg.get_boundary_config()
        extractor_cfg = cfg.get_extractor_config()
        port = cfg.webui_port
    """

    def __init__(self, raw: dict, data_dir: Path | None = None) -> None:
        # AstrBot delivers nested structures when _conf_schema.json uses "type": "object".
        # We flatten one level so existing code continues to work.
        # CRITICAL: We check for .items() because AstrBot config objects are not always plain dicts.
        flat: dict = {}
        
        # Helper to safely get items from a dict or dict-like object
        def get_items(obj):
            if hasattr(obj, "items") and callable(getattr(obj, "items")):
                return obj.items()
            return []

        for k, v in get_items(raw):
            items = get_items(v)
            if items:
                # It's a nested group
                for sub_k, sub_v in items:
                    flat[sub_k] = sub_v
            else:
                # It's a top-level key
                flat[k] = v
        
        self._raw = flat

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

    @property
    def language(self) -> str:
        val = self._str("language", LANG_ZH)
        # Normalise to supported constants
        if val in {"zh", "zh-CN", "chinese"}:
            return LANG_ZH
        if val in {"en", "en-US", "english"}:
            return LANG_EN
        if val in {"ja", "ja-JP", "japanese"}:
            return LANG_JA
        return val if val in {LANG_ZH, LANG_EN, LANG_JA} else LANG_ZH

    @property
    def llm_provider(self) -> str | None:
        val = self._str("llm_provider", "").strip()
        return val if val else None

    # ------------------------------------------------------------------
    # Subsystem config objects
    # ------------------------------------------------------------------

    def get_boundary_config(self) -> BoundaryConfig:
        return BoundaryConfig(
            time_gap_minutes=self._float("boundary_time_gap_minutes", 30.0),
            max_messages=self._int("boundary_max_messages", 50),
            max_duration_minutes=self._float(
                "boundary_max_duration_minutes", 60.0),
            summary_trigger_rounds=self._int("summary_trigger_rounds", 30),
            drift_detection_enabled=self._bool(
                "boundary_topic_drift_enabled", True),
            drift_threshold=self._float("boundary_topic_drift_threshold", 0.6),
            drift_auto_calibration=self._bool("boundary_topic_drift_auto_calibration", True),
            drift_percentile=self._float("boundary_topic_drift_percentile", 85.0),
            drift_min_messages=self._int(
                "boundary_topic_drift_min_messages", 20),
            drift_check_interval=self._int("boundary_topic_drift_interval", 5),
        )

    def get_maintenance_config(self) -> MaintenanceConfig:
        return MaintenanceConfig(
            periodic_flush_enabled=self._bool("periodic_flush_enabled", True),
            periodic_flush_minutes=self._float("periodic_flush_minutes", 30.0),
            periodic_flush_tail_keep=self._int("periodic_flush_tail_keep", 10),
        )

    def get_decay_config(self) -> DecayConfig:
        return DecayConfig(
            lambda_=self._float("decay_lambda", 0.01),
            archive_threshold=self._float("decay_archive_threshold", 0.05),
        )

    def get_backup_config(self) -> BackupConfig:
        return BackupConfig(
            enabled=self._bool("backup_enabled", True),
            retention_days=self._int("backup_retention_days", 7),
        )

    def get_synthesis_config(self) -> SynthesisConfig:
        persona_prompt = self._str(
            "synthesis_persona_system_prompt", "").strip()
        impression_prompt = self._str(
            "synthesis_impression_system_prompt", "").strip()
        reanalyze_prompt = self._str(
            "synthesis_reanalyze_system_prompt", "").strip()
        return SynthesisConfig(
            llm_timeout=self._float("synthesis_llm_timeout_seconds", 30.0),
            max_events=self._int("synthesis_max_events", 10),
            persona_system_prompt=persona_prompt or DEFAULT_PERSONA_SYSTEM_PROMPT,
            impression_system_prompt=impression_prompt or DEFAULT_IMPRESSION_SYSTEM_PROMPT,
            reanalyze_system_prompt=reanalyze_prompt or DEFAULT_REANALYZE_IMPRESSION_SYSTEM_PROMPT,
            language=self.language,
            llm_provider=self.llm_provider,
        )

    def get_summary_config(self) -> SummaryConfig:
        prompt = self._str("summary_system_prompt", "").strip()
        mood_prompt = self._str("summary_mood_system_prompt", "").strip()
        unified_prompt = self._str("summary_unified_system_prompt", "").strip()
        return SummaryConfig(
            llm_timeout=self._float("summary_llm_timeout_seconds", 45.0),
            max_events=self._int("summary_max_events", 20),
            system_prompt=prompt or DEFAULT_SUMMARY_SYSTEM_PROMPT,
            mood_source=self._str("summary_mood_source", "llm"),
            mood_prompt=mood_prompt or DEFAULT_SUMMARY_MOOD_PROMPT,
            unified_prompt=unified_prompt or DEFAULT_SUMMARY_UNIFIED_PROMPT,
            language=self.language,
            llm_provider=self.llm_provider,
        )

    def get_retrieval_config(self) -> RetrievalConfig:
        return RetrievalConfig(
            bm25_limit=self._int("retrieval_bm25_limit", 20),
            vec_limit=self._int("retrieval_vec_limit", 20),
            final_limit=self._int("retrieval_top_k", 3),
            active_limit=self._int("retrieval_active_top_k", 5),
            rrf_k=self._int("retrieval_rrf_k", 60),
            salience_weight=self._float("retrieval_salience_weight", 0.1),
            recency_weight=self._float("retrieval_recency_weight", 0.2),
            relevance_weight=self._float("retrieval_relevance_weight", 0.5),
            recency_half_life_days=self._float(
                "retrieval_recency_half_life_days", 30.0),
            vector_fallback_enabled=self._bool(
                "retrieval_vector_fallback_enabled", True),
            active_only=self._bool("retrieval_active_only", True),
            weighted_random=self._bool("retrieval_weighted_random", False),
            sampling_temperature=self._float(
                "retrieval_sampling_temperature", 1.0),
        )

    def get_canon_config(self):
        """原作剧情记忆的配置。canon_persona_map 格式错误时 persona_map 为空并带上错误说明。"""
        from .canon.config import CanonConfig, parse_persona_map

        persona_map, error = parse_persona_map(self._raw.get("canon_persona_map", "{}"))
        return CanonConfig(
            enabled=self._bool("canon_enabled", False),
            db_path=self._str("canon_db_path", "").strip(),
            pack_path=self._str("canon_pack_path", "").strip(),
            persona_map=persona_map,
            persona_map_error=error,
            top_k=max(1, self._int("canon_top_k", 5)),
            token_budget=max(0, self._int("canon_token_budget", 2000)),
            evidence_lines=max(0, self._int("canon_evidence_lines", 4)),
            time_filter=self._bool("canon_time_filter", False),
            extract_concurrency=max(1, self._int("canon_extract_concurrency", 2)),
            extract_timeout=max(1, self._int("canon_extract_timeout", 300)),
        )

    def get_injection_config(self) -> InjectionConfig:
        pos = self._str("injection_position", "user_message_before").strip()
        valid = {"system_prompt", "user_message_before",
                 "user_message_after", "fake_tool_call"}
        relation_enabled = self._bool("relation_enabled", True)
        return InjectionConfig(
            position=pos if pos in valid else "user_message_before",
            auto_clear=self._bool("injection_auto_clear", True),
            token_budget=self._int("retrieval_token_budget", 800),
            commitment_max_items=max(0, self._int("commitment_max_items", 3)),
            persona_view_injection_enabled=self._bool("persona_view_injection_enabled", False),
            show_thinking_process=self._bool("show_thinking_process", False),
            show_system_prompt=self._bool("show_system_prompt", False),
            show_injection_summary=self._bool("show_injection_summary", False),
            impression_injection_enabled=(
                relation_enabled
                and self._bool("impression_injection_enabled", True)
            ),
            impression_injection_max_items=max(
                0, min(8, self._int("impression_injection_max_items", 3))
            ),
            impression_injection_min_confidence=max(
                0.0, min(1.0, self._float("impression_injection_min_confidence", 0.2))
            ),
            account_merge_synthesis_only=self._bool(
                "account_merge_synthesis_only", False
            ),
        )

    def get_ipc_config(self) -> IPCConfig:
        return IPCConfig(
            enabled=self._bool("ipc_enabled", True),
            bigfive_x_messages=self._int("bigfive_x_messages", 10),
            bigfive_llm_timeout=self._float(
                "bigfive_llm_timeout_seconds", 30.0),
        )

    def get_extractor_config(self) -> ExtractorConfig:
        custom_prompt = self._str("extractor_system_prompt", "").strip()
        custom_distill_prompt = self._str(
            "distillation_system_prompt", "").strip()
        tag_seeds_str = self._str("tag_seeds", "社交,日常,技术,知识,工作,娱乐,艺术,情感,资讯")
        tag_seeds = [s.strip() for s in tag_seeds_str.split(",") if s.strip()]
        return ExtractorConfig(
            retry_until_success=self._bool("extraction_retry_until_success", False),
            llm_retry_delay_seconds=max(2.0, self._float("model_retry_delay_seconds", 2.0)),
            max_context_messages=self._int(
                "extractor_context_messages",
                min(40, self._int("context_window_size", 50)),
            ),
            llm_timeout=self._float("extractor_llm_timeout_seconds", 30.0),
            requeue_attempts=self._int("extractor_requeue_attempts", 2),
            requeue_delay_seconds=self._float("extractor_requeue_delay_seconds", 60.0),
            system_prompt=custom_prompt or DEFAULT_EXTRACTOR_SYSTEM_PROMPT,
            distillation_system_prompt=custom_distill_prompt or DEFAULT_DISTILLATION_SYSTEM_PROMPT,
            strategy=self._str("extraction_strategy", "llm"),
            llm_segmentation=self._bool("extraction_llm_segmentation", True),
            segmentation_messages_per_segment=max(1, self._int("extraction_segmentation_messages_per_segment", 12)),
            segmentation_timeout=max(0.1, self._float("extraction_segmentation_timeout_seconds", 30.0)),
            semantic_clustering_eps=self._float(
                "semantic_clustering_eps",
                0.45
            ),
            semantic_clustering_min_samples=self._int(
                "semantic_clustering_min_samples",
                2
            ),
            persona_influenced_summary=self._bool(
                "persona_influenced_summary",
                False
            ),
            bot_persona_name_override=self._str(
                "bot_persona_name_override", ""
            ).strip(),
            tag_normalization_threshold=self._float(
                "tag_normalization_threshold",
                0.85
            ),
            tag_promotion_min_df=self._int("tag_promotion_min_df", 3),
            tag_candidate_ttl_days=self._int("tag_candidate_ttl_days", 30),
            tag_seeds=tag_seeds,
            llm_provider=self.llm_provider,
        )

    def get_typesafe_config(self) -> TypeSafeConfig:
        return TypeSafeConfig(
            enabled=self._bool("typesafe_enabled", False),
            topic_enabled=self._bool("typesafe_topic_enabled", True),
            event_enabled=self._bool("typesafe_event_enabled", True),
            api_key=(
                self._str("typesafe_api_key", "").strip()
                or os.environ.get("TYPESAFE_API_KEY", "").strip()
            ),
            base_url=(
                self._str("typesafe_base_url", "").strip()
                or "https://api.typesafe.ai"
            ),
            model=self._str("typesafe_model", "").strip() or "jev-latest",
            timeout=self._float("typesafe_timeout_seconds", 10.0),
            min_confidence=self._float("typesafe_min_confidence", 0.5),
            custom_tag_min_score=self._float(
                "typesafe_custom_tag_min_score", 0.7
            ),
            topic_backfill=self._bool("typesafe_topic_backfill", True),
            event_backfill=self._bool("typesafe_event_backfill", False),
            llm_fallback=self._bool("typesafe_llm_fallback", True),
        )

    def get_context_config(self) -> ContextConfig:
        return ContextConfig(
            vcm_enabled=self._bool("vcm_enabled", True),
            max_sessions=self._int("context_max_sessions", 100),
            session_idle_seconds=self._int(
                "context_session_idle_seconds", 3600),
            window_size=self._int("context_window_size", 50),
            max_history_messages=self._int("context_max_history_messages", 1000),
            cleanup_batch_size=self._int("context_cleanup_batch_size", 50),
        )

    def get_cleanup_config(self) -> CleanupConfig:
        raw_retention_days = self._int("raw_message_retention_days", 14)
        raw_retention_days = max(1, min(14, raw_retention_days))
        return CleanupConfig(
            enabled=self._bool("memory_cleanup_enabled", True),
            threshold=self._float("memory_cleanup_threshold", 0.3),
            interval_days=self._int("memory_cleanup_interval_days", 7),
            retention_days=self._int("memory_cleanup_retention_days", 30),
            raw_message_retention_days=raw_retention_days,
        )

    def get_embedding_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            retry_until_success=self._bool("embedding_retry_until_success", False),
            provider=self._str("embedding_provider", "local"),
            model=self._str("embedding_model", "BAAI/bge-small-zh-v1.5"),
            api_url=self._str("embedding_api_url", ""),
            api_key=self._str("embedding_api_key", ""),
            batch_size=self._int("embedding_batch_size", 50),
            request_batch_size=self._int("embedding_request_batch_size", 16),
            concurrency=self._int("embedding_concurrency", 1),
            batch_interval_ms=self._int("embedding_batch_interval_ms", 50),
            request_interval_ms=self._int("embedding_request_interval_ms", 0),
            failure_tolerance_ratio=self._float(
                "embedding_failure_tolerance_ratio", 0.02),
            retry_max=self._int("embedding_retry_max", 3),
            retry_delay_ms=self._int("embedding_retry_delay_ms", 30000),
            timeout_seconds=self._float("embedding_timeout_seconds", 60.0),
            dimensions=self._int("embedding_dimensions", 0),
        )

    def get_rerank_config(self) -> RerankConfig:
        return RerankConfig(
            enabled=self._bool("rerank_enabled", False),
            model=self._str("rerank_model", "arc:rerankvl"),
            api_url=self._str("rerank_api_url", ""),
            api_key=self._str("rerank_api_key", ""),
            max_candidates=self._int("rerank_max_candidates", 40),
            timeout_seconds=self._float("rerank_timeout_seconds", 60.0),
            retry_max=self._int("rerank_retry_max", 1),
        )

    # ------------------------------------------------------------------
    # WebUI
    # ------------------------------------------------------------------

    @property
    def webui_enabled(self) -> bool:
        return self._bool("webui_enabled", True)

    @property
    def webui_port(self) -> int:
        return self._int("webui_port", 2655)

    @property
    def webui_auth_enabled(self) -> bool:
        return self._bool("webui_auth_enabled", True)

    @property
    def webui_auto_restart_on_save(self) -> bool:
        return self._bool("webui_auto_restart_on_save", True)

    @property
    def webui_password(self) -> str:
        return self._str("webui_password", "").strip()

    @property
    def webui_session_hours(self) -> int:
        return self._int("webui_session_hours", 1)

    @property
    def webui_sudo_minutes(self) -> int:
        return self._int("webui_sudo_minutes", 30)

    @property
    def llm_concurrency(self) -> int:
        return self._int("llm_concurrency", 2)

    @property
    def show_llm_call_details(self) -> bool:
        return self._bool("show_llm_call_details", False)

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
        return self._bool("persona_isolation_enabled", True)

    @property
    def persona_isolation_legacy_visible(self) -> bool:
        return self._bool("persona_isolation_legacy_visible", True)

    @property
    def persona_merge_audit_enabled(self) -> bool:
        return self._bool("persona_merge_audit_enabled", True)

    @property
    def persona_default_view_mode(self) -> str:
        val = self._str("persona_default_view_mode", "remember")
        if val not in {"remember", "all", "force_pick"}:
            return "remember"
        return val

    @property
    def bot_persona_name_override(self) -> str:
        """Explicit bot_persona_name bucket; empty string means auto-resolve."""
        return self._str("bot_persona_name_override", "").strip()

    # ------------------------------------------------------------------
    # Periodic tasks
    # ------------------------------------------------------------------

    @property
    def decay_enabled(self) -> bool:
        return self._bool("decay_enabled", True)

    @property
    def summary_enabled(self) -> bool:
        return self._bool("summary_enabled", True)

    @property
    def persona_synthesis_enabled(self) -> bool:
        return self._bool("persona_synthesis_enabled", True)

    @property
    def markdown_projection_enabled(self) -> bool:
        return self._bool("markdown_projection_enabled", True)

    @property
    def decay_interval_seconds(self) -> int:
        return self._int("decay_interval_hours", 24) * 3600

    @property
    def summary_interval_seconds(self) -> int:
        return self._int("summary_interval_hours", 24) * 3600

    @property
    def persona_synthesis_interval_seconds(self) -> int:
        return self._int("persona_synthesis_interval_hours", 72) * 3600

    @property
    def persona_synthesis_trigger_messages(self) -> int:
        return self._int("persona_synthesis_trigger_messages", 30)

    @property
    def persona_synthesis_min_events(self) -> int:
        return self._int("persona_synthesis_min_events", 3)

    @property
    def persona_synthesis_cooldown_hours(self) -> float:
        return self._float("persona_synthesis_cooldown_hours", 3.0)

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
        return self._float("impression_update_alpha", 0.4)

    @property
    def persona_default_confidence(self) -> float:
        return self._float("persona_default_confidence", 0.5)

    # ------------------------------------------------------------------
    # Raw dict passthrough (for subsystems that need the full dict)
    # ------------------------------------------------------------------

    def as_dict(self) -> dict:
        return dict(self._raw)
