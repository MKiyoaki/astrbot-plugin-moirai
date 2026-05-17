"""Centralised plugin configuration.

Reads the raw dict that AstrBot passes via ``self.config`` and exposes
typed accessors for each subsystem.  Keeps main.py free of scattered
``cfg.get(...)`` calls and gives each module a dedicated config object
it can be unit-tested against.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.boundary.detector import BoundaryConfig
from core.utils.i18n import LANG_ZH, LANG_EN, LANG_JA

# ---------------------------------------------------------------------------
# Default extractor system prompt (kept here so _conf_schema.json can
# reference the same text as the factory default).
# ---------------------------------------------------------------------------
DEFAULT_DISTILLATION_SYSTEM_PROMPT = (
    "你是一个聊天记录分析助手。你的任务是为一段已经语义聚类好的对话片段提炼结构化信息。\n\n"
    "只输出单个 JSON 对象，不输出任何其他文字或 markdown 代码块，格式如下：\n"
    '{"topic": "...", "summary": "...", "chat_content_tags": ["...", "..."], "salience": 0.5, "confidence": 0.8, "inherit": false, "participants_personality": {"Alice": {"scores": {"O": 0.6, "E": 0.7}, "evidence": "Alice 主动发起话题、反应积极"}}}\n\n'
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
    "- inherit: 是否是上一个事件的直接延续（true/false）\n"
    "- participants_personality: （可选）参与者五大人格估计，键为显示名，不确定时省略该字段。\n"
    '  格式：{"显示名": {"scores": {"O": 0.6, "E": 0.4}, "evidence": "一句话依据"}}\n'
    "  scores 字段 O/C/E/A/N 范围 -1.0（极低）到 1.0（极高）；\n"
    "  O=开放性（高→好奇创意），C=尽责性（高→自律有序），E=外向性（高→健谈主动），\n"
    "  A=宜人性（高→友善合作），N=神经质（高→易焦虑情绪化）。\n"
    "  每个维度须有对话依据；无法判断的维度可省略不填。evidence 为对该人物本次对话表现的简短总结（≤50字）。"
)

DEFAULT_EXTRACTOR_SYSTEM_PROMPT = (
    "你是一个聊天记录分析助手。你的任务是将一段连续的对话记录划分为一个或多个逻辑事件，并提取结构化信息。\n\n"
    "划分逻辑：\n"
    "1. 话题转换：当对话主题发生明显变化时，划分为新事件。\n"
    "2. 时间大跨度：当两条消息之间的时间间隔非常大（如超过数小时或数天）时，通常应划分为新事件。\n"
    "3. 连续性：如果对话虽然中断但随后继续讨论同一话题，可以视为同一事件的延续（设置 inherit 为 true）。\n\n"
    "输出格式（仅输出一个 JSON Array，包含一个或多个对象，不输出任何其他文字或 markdown 代码块）：\n"
    '[\n'
    '  {"start_idx": 0, "end_idx": 10, "topic": "...", "summary": "...", "chat_content_tags": ["...", "..."], "salience": 0.5, "confidence": 0.8, "inherit": false, "participants_personality": {"Alice": {"scores": {"O": 0.6, "E": 0.7}, "evidence": "Alice 主动发起多个话题、情绪积极"}}},\n'
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
    "- inherit: 是否继承上一个已知事件的主题（即本段是上段的延续）\n"
    "- participants_personality: （可选）对话参与者的人格特征估计。"
    "仅在对话内容足以推断时填写，不确定时省略该字段。\n"
    '  格式：{"显示名": {"scores": {"O": 0.6, "E": 0.4}, "evidence": "一句话依据（≤50字）"}}\n'
    "  scores 字段 O/C/E/A/N 范围 -1.0（极低）到 1.0（极高），0.0 表示中等。\n"
    "  O（开放性）：高→好奇、富创意、乐于接受新思想；低→务实、守旧、偏好熟悉事物。\n"
    "  C（尽责性）：高→有条理、自律、目标导向；低→随意、拖延、缺乏计划性。\n"
    "  E（外向性）：高→健谈、主动、精力充沛；低→内敛、寡言、偏好独处。\n"
    "  A（宜人性）：高→友善、合作、富有同理心；低→竞争性强、怀疑心重、不轻易妥协。\n"
    "  N（神经质）：高→情绪不稳定、易焦虑；低→沉稳、压力耐受力强。\n"
    "  每个维度的评分须有对话中可观察到的具体依据；无法判断的维度可省略不填。"
    "evidence 为对该人物本次对话表现的简短总结（≤50字）。"
)


@dataclass
class DecayConfig:
    lambda_: float = 0.01             # Per-pass decay rate (e.g. 0.01 = 1%)
    archive_threshold: float = 0.05   # Status='archived' if salience falls below this


@dataclass
class BackupConfig:
    enabled: bool = True
    retention_days: int = 7


_DEFAULT_PERSONA_SYSTEM_PROMPT = (
    "你是一个用户画像分析助手。根据提供的事件记录，推断用户的性格特征。\n"
    "只输出单行JSON，字段：\n"
    "- description: 性格简述，≤80字符\n"
    "- big_five: 大五人格评分对象，字段 O/C/E/A/N，范围 -1.0（极低）到 1.0（极高），0.0 表示中等。\n"
    "  O=开放性（高→好奇创意），C=尽责性（高→自律有序），E=外向性（高→健谈主动），\n"
    "  A=宜人性（高→友善合作），N=神经质（高→易焦虑情绪化）。\n"
    "  每个维度须有事件依据；无法判断的维度可省略不填。\n"
    "  若已有评分，可结合历史与新事件小幅调整；若无依据则保留原值。\n"
    "- big_five_evidence: 对象，键为已评分的维度（O/C/E/A/N），值为该维度的证据句（≤120字符）。\n"
    "  句子模板：[个体] 在 [维度名] 上表现出 [高/低/中等] 水平，其显著特征为 [具体行为证据]，\n"
    "  可以推断出 [X%] 的量化结果。\n"
    "  分数换算（内部-1~1 → 展示百分比）：round((score+1)/2×100)%。≥65%=高，35%–64%=中等，≤34%=低。\n"
    "  只填写有充分对话依据的维度，其余省略。\n"
    "不要输出任何其他内容。\n"
    '示例：{"description": "热衷技术讨论，表达直接，偶尔情绪化", '
    '"big_five": {"O": 0.6, "E": 0.4, "N": 0.3}, '
    '"big_five_evidence": {'
    '"O": "Alice 在开放性上表现出高水平，其显著特征为主动引入跨领域话题，可以推断出 80% 的量化结果。", '
    '"E": "Alice 在外向性上表现出中等水平，其显著特征为积极回应但较少主动发起，可以推断出 70% 的量化结果。", '
    '"N": "Alice 在神经质上表现出中等偏高水平，其显著特征为偶因意见分歧情绪波动，可以推断出 65% 的量化结果。"}}'
)

_DEFAULT_IMPRESSION_SYSTEM_PROMPT = (
    "你是一个社交关系分析助手。根据对话事件，更新对某人的印象。"
    "只输出单行JSON，字段：ipc_orientation（以下8种之一：affinity/active/dominant/arrogant/cold/withdrawn/submissive/deferential）、"
    "benevolence（亲和度，-1.0到1.0的浮点数）、power（支配度，-1.0到1.0的浮点数）、"
    "confidence（0.0到1.0 Hendrick 的浮点数）。不要输出任何其他内容。"
)


@dataclass
class SynthesisConfig:
    llm_timeout: float = 30.0
    max_events: int = 10
    persona_system_prompt: str = _DEFAULT_PERSONA_SYSTEM_PROMPT
    impression_system_prompt: str = _DEFAULT_IMPRESSION_SYSTEM_PROMPT
    language: str = LANG_ZH
    llm_provider: str | None = None
    # weight for new synthesis vs existing scores (0=freeze, 1=replace)
    ema_alpha: float = 0.35


_DEFAULT_SUMMARY_SYSTEM_PROMPT = (
    "你是一个对话记录摘要助手。根据提供的事件列表，生成本期群组活动摘要。"
    "只输出[主要话题]部分的正文内容，不超过300字，对时段内所有事件进行总结。"
    "不要输出标题、Markdown装饰或任何其他内容。只输出正文。"
)

_DEFAULT_SUMMARY_MOOD_PROMPT = (
    "你是一个社交关系分析助手。根据以下对话事件，分析群体情感动态。"
    "只输出单行JSON，字段：orientation（以下8种之一：affinity/active/dominant/arrogant/cold/withdrawn/submissive/deferential之一）、"
    "benevolence（亲和度，-1.0到1.0的浮点数）、power（支配度，-1.0到1.0的浮点数）、"
    "positions（对象，key为用户UID，value为该用户的orientation，8种之一）。"
    "不要输出任何其他内容。"
)

_DEFAULT_SUMMARY_UNIFIED_PROMPT = (
    "你是一个对话记录摘要与社交关系分析助手。根据提供的事件列表，生成群组活动摘要并分析群体情感动态。\n\n"
    "请输出一个 JSON 对象，包含以下字段：\n"
    "1. summary: 对时段内所有事件进行总结的正文内容，不超过 300 字。不要包含标题或 Markdown 装饰。\n"
    "2. mood: 一个对象，包含以下社交关系分析字段：\n"
    "   - orientation: 群体整体氛围（affinity/active/dominant/arrogant/cold/withdrawn/submissive/deferential之一）\n"
    "   - benevolence: 整体亲和度 (-1.0 到 1.0)\n"
    "   - power: 整体支配度 (-1.0 到 1.0)\n"
    "   - positions: 对象，key 为用户 UID，value 为该用户的 orientation (8种之一)\n\n"
    "只输出 JSON，不要有其他解释文字。"
)


@dataclass
class SummaryConfig:
    llm_timeout: float = 45.0
    max_events: int = 20
    word_limit: int = 300
    system_prompt: str = _DEFAULT_SUMMARY_SYSTEM_PROMPT
    mood_source: str = "llm"
    mood_prompt: str = _DEFAULT_SUMMARY_MOOD_PROMPT
    unified_prompt: str = _DEFAULT_SUMMARY_UNIFIED_PROMPT
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
    show_thinking_process: bool = False
    """Prepend memory-retrieval debug info to each reply."""
    show_system_prompt: bool = False
    """Prepend the pre-injection system prompt to replies for admin senders."""
    show_injection_summary: bool = False
    """Prepend a sanitized summary of Moirai's actual injected prompt content."""


@dataclass
class IPCConfig:
    enabled: bool = True
    bigfive_x_messages: int = 10
    bigfive_llm_timeout: float = 30.0


@dataclass
class SoulConfig:
    enabled: bool = False
    decay_rate: float = 0.1
    recall_depth_init: float = 0.0
    impression_depth_init: float = 0.0
    expression_desire_init: float = 0.0
    creativity_init: float = 0.0


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
    tag_normalization_threshold: float = 0.85
    tag_seeds: list[str] = field(
        default_factory=lambda: [
            "社交", "日常", "技术", "知识", "工作", "娱乐", "艺术", "情感", "资讯"
        ]
    )
    language: str = LANG_ZH
    llm_provider: str | None = None


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


@dataclass
class EmbeddingConfig:
    provider: str = "local"
    model: str = "BAAI/bge-small-zh-v1.5"
    api_url: str = ""
    api_key: str = ""
    batch_size: int = 50
    request_batch_size: int = 16
    concurrency: int = 1
    batch_interval_ms: int = 5000
    request_interval_ms: int = 5000
    failure_tolerance_ratio: float = 0.02
    retry_max: int = 3
    retry_delay_ms: int = 30000


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
            drift_min_messages=self._int(
                "boundary_topic_drift_min_messages", 20),
            drift_check_interval=self._int("boundary_topic_drift_interval", 5),
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
        return SynthesisConfig(
            llm_timeout=self._float("synthesis_llm_timeout_seconds", 30.0),
            max_events=self._int("synthesis_max_events", 10),
            persona_system_prompt=persona_prompt or _DEFAULT_PERSONA_SYSTEM_PROMPT,
            impression_system_prompt=impression_prompt or _DEFAULT_IMPRESSION_SYSTEM_PROMPT,
            language=self.language,
            llm_provider=self.llm_provider,
        )

    def get_summary_config(self) -> SummaryConfig:
        prompt = self._str("summary_system_prompt", "").strip()
        mood_prompt = self._str("summary_mood_system_prompt", "").strip()
        unified_prompt = self._str("summary_unified_system_prompt", "").strip()
        limit = self._int("summary_word_limit", 300)
        limit = max(200, min(500, limit))
        return SummaryConfig(
            llm_timeout=self._float("summary_llm_timeout_seconds", 45.0),
            max_events=self._int("summary_max_events", 20),
            word_limit=limit,
            system_prompt=prompt or _DEFAULT_SUMMARY_SYSTEM_PROMPT,
            mood_source=self._str("summary_mood_source", "llm"),
            mood_prompt=mood_prompt or _DEFAULT_SUMMARY_MOOD_PROMPT,
            unified_prompt=unified_prompt or _DEFAULT_SUMMARY_UNIFIED_PROMPT,
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

    def get_injection_config(self) -> InjectionConfig:
        pos = self._str("injection_position", "system_prompt").strip()
        valid = {"system_prompt", "user_message_before",
                 "user_message_after", "fake_tool_call"}
        return InjectionConfig(
            position=pos if pos in valid else "system_prompt",
            auto_clear=self._bool("injection_auto_clear", True),
            token_budget=self._int("retrieval_token_budget", 800),
            show_thinking_process=self._bool("show_thinking_process", False),
            show_system_prompt=self._bool("show_system_prompt", False),
            show_injection_summary=self._bool("show_injection_summary", False),
        )

    def get_ipc_config(self) -> IPCConfig:
        return IPCConfig(
            enabled=self._bool("ipc_enabled", True),
            bigfive_x_messages=self._int("bigfive_x_messages", 10),
            bigfive_llm_timeout=self._float(
                "bigfive_llm_timeout_seconds", 30.0),
        )

    def get_soul_config(self) -> SoulConfig:
        return SoulConfig(
            enabled=self._bool("soul_enabled", False),
            decay_rate=self._float("soul_decay_rate", 0.1),
            recall_depth_init=self._float("soul_recall_depth_init", 0.0),
            impression_depth_init=self._float(
                "soul_impression_depth_init", 0.0),
            expression_desire_init=self._float(
                "soul_expression_desire_init", 0.0),
            creativity_init=self._float("soul_creativity_init", 0.0),
        )

    def get_extractor_config(self) -> ExtractorConfig:
        custom_prompt = self._str("extractor_system_prompt", "").strip()
        custom_distill_prompt = self._str(
            "distillation_system_prompt", "").strip()
        tag_seeds_str = self._str("tag_seeds", "社交,日常,技术,知识,工作,娱乐,艺术,情感,资讯")
        tag_seeds = [s.strip() for s in tag_seeds_str.split(",") if s.strip()]
        return ExtractorConfig(
            max_context_messages=self._int("context_window_size", 50),
            llm_timeout=self._float("extractor_llm_timeout_seconds", 30.0),
            system_prompt=custom_prompt or DEFAULT_EXTRACTOR_SYSTEM_PROMPT,
            distillation_system_prompt=custom_distill_prompt or DEFAULT_DISTILLATION_SYSTEM_PROMPT,
            strategy=self._str("extraction_strategy", "llm"),
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
            tag_normalization_threshold=self._float(
                "tag_normalization_threshold",
                0.85
            ),
            tag_seeds=tag_seeds,
            llm_provider=self.llm_provider,
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
        return CleanupConfig(
            enabled=self._bool("memory_cleanup_enabled", True),
            threshold=self._float("memory_cleanup_threshold", 0.3),
            interval_days=self._int("memory_cleanup_interval_days", 7),
            retention_days=self._int("memory_cleanup_retention_days", 30),
        )

    def get_embedding_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            provider=self._str("embedding_provider", "local"),
            model=self._str("embedding_model", "BAAI/bge-small-zh-v1.5"),
            api_url=self._str("embedding_api_url", ""),
            api_key=self._str("embedding_api_key", ""),
            batch_size=self._int("embedding_batch_size", 50),
            request_batch_size=self._int("embedding_request_batch_size", 16),
            concurrency=self._int("embedding_concurrency", 1),
            batch_interval_ms=self._int("embedding_batch_interval_ms", 5000),
            request_interval_ms=self._int("embedding_request_interval_ms", 5000),
            failure_tolerance_ratio=self._float(
                "embedding_failure_tolerance_ratio", 0.02),
            retry_max=self._int("embedding_retry_max", 3),
            retry_delay_ms=self._int("embedding_retry_delay_ms", 30000),
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
        return self._float("impression_update_alpha", 0.4)

    @property
    def persona_default_confidence(self) -> float:
        return self._float("persona_default_confidence", 0.5)

    # ------------------------------------------------------------------
    # Raw dict passthrough (for subsystems that need the full dict)
    # ------------------------------------------------------------------

    def as_dict(self) -> dict:
        return dict(self._raw)
