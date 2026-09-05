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
# Default extractor system prompts. Both are hand-maintained in parallel and
# differ only in the segmentation section; keep edits to one mirrored in the
# other. Users may override either via the `extractor_system_prompt` /
# `distillation_system_prompt` config keys.
#
# Design notes, since these are long and every line costs prefill:
#   * The worked example is filled in rather than a placeholder skeleton — a
#     sample answer conveys schema, granularity and score calibration at once,
#     and models follow it more reliably than the equivalent prose. It is
#     explicitly labelled as structural, so it does not anchor output length.
#   * No cap is placed on anything the memory is supposed to retain: triple
#     count, summary length and the number of people described all scale with
#     the conversation. Caps apply only to fields that are titles or asides
#     (topic, [Eval]).
# ---------------------------------------------------------------------------

_CRITERION = (
    "判定标准：没读过原对话的人，只看 summary 就能说清"
    "「谁、就什么事、说了或做了什么、结果如何」。\n\n"
)

_EXAMPLE_NOTE = (
    "范本只示意结构与字段；三元组个数、每段长度、写几个人，都随实际对话的信息量伸缩。"
    "若提示词未提供 [Bot 视角人格]，则省略 [Eval] 字段；提供了则每个三元组都要有。\n\n"
)

_CONTRAST = (
    "[What] 必须写具体，不要写成泛称：\n"
    "  ✗ 几人讨论了周末的安排并交换了看法\n"
    "  ✓ Alice 提议周六下午去，Carol 说自己五点后才有空，最后定了周六但钟点待定\n"
    "  ✗ 两人就方案产生分歧，最后达成一致\n"
    "  ✓ Bob 主张先上线再修，Carol 认为必须先补测试；争了几轮后 Bob 让步，同意周五前补完测试再发\n\n"
)

_FIELDS_SUMMARY = (
    "- topic：核心主题，≤30 字；要具体到能和同群别的日子区分开——"
    "点明具体的游戏/作品/事件/话题，避免「日常闲聊」「群内互动」这类放到哪天都成立的写法。\n"
    "- summary：由若干 [What]/[Who]/[How] 三元组组成，用 \" | \" 分隔，与 chat_content_tags 对应。\n"
    "  · 划分：话题、对象或叙事重心切换即另起一个；追问、补充、评价、情绪、方案属于同一三元组的展开；"
    "极短的附和、单条表情、复读并入相邻三元组。对话里有几个小话题就写几个三元组，不要为了凑数而合并或拆分。\n"
    "  · [What]：写清这个小话题实际发生了什么，要能被没读过原文的人独立读懂。"
    "专有名词、日期、时间、数量、金额、链接、结论一律照留；"
    "代词和模糊指代（\"那个\"、\"他\"、\"上次说的\"）解析成具体所指；"
    "观点、决定、约定、问答要写清是谁提的、有没有得到回应；分歧要写清最后怎么收场。"
    "对话记录里冒号后为空的行，是图片/表情/语音/视频等非文本消息：它们只说明谁在何时参与、"
    "互动节奏如何，不承载可提炼的文字，请优先依据有文字的消息来写 [What]，不要因为空行多就判定整段无信息。\n"
    "  · [How]：如何推进、以何种方式结束，可含情绪、态度、结论、是否悬而未决。\n"
    "  · [Who]：只列人名。\n"
    "  · 长度随信息量伸缩、不设上限；宁可写长，也不要把具体信息压成概括。"
    "只有当整段几乎没有任何带文字的消息时，才可整体概括成一句具体描述"
    "（如「三人互发表情包玩梗，无文字内容」）；只要有哪怕几条带文字的消息，"
    "就必须具体提炼那几条，不能被图片/表情的空行淹没成一句「无实质话题」。\n"
    "  · [Eval]：若提示词提供了 [Bot 视角人格]，每个三元组末尾【必须】加 [Eval]，"
    "以该人格第一人称给一句 ≤30 字的评价或态度。[Eval] 只是旁白，实质内容一律写进 [What]。"
    "信息不足也要写 [Eval] 信息不足，不允许省略。\n"
)

_FIELDS_TAIL = (
    "- chat_content_tags：2~5 个名词或名词短语，禁止句子、原文片段、动词短语、人名。"
    "应是【可复用的话题域标签】，同类对话下次能复用同一个；鼓励具体名词（作品名、游戏名、技术名词、机制名），"
    "但不要把只属于这次对话的情节细节写成标签（如「上周三那次失误」）。\n"
    "- salience：这段记忆日后值得被回忆起来的程度，取【事实价值】与【人物价值】的较高者，0.0~1.0："
    "0.1–0.2 既无信息也无人物色彩（纯表情刷屏、单纯复读；夹带少量有内容文字的不算此档）；"
    "0.3–0.4 有一点具体信息，或有一点性格、关系的流露；"
    "0.5–0.6 明确的偏好/立场/关系动态，或一段有来有回、能看出各人性格的互动，或一次完整问答；"
    "0.7–0.8 重要事实或承诺（约定、计划、个人信息），强烈情绪事件，显著冲突；"
    "0.9+ 罕见的关键节点。"
    "一段看似「没营养」但很能体现某人是什么样的人、或两人是什么关系的对话，不算低分。\n"
    "- confidence：对「summary 是否忠实反映了有文字的那部分对话」的把握，0.0~1.0；"
    "与非文本消息（图片/表情/语音等）占比无关——大部分是图片但少量文字清晰的对话，"
    "confidence 仍可以偏高；只有对话本身跳跃、指代混乱、需要你猜测时才降低。\n"
    "- participant_style：（可选）{\"显示名\": \"一句话\"}。"
    "为本段中【每个实际发言且有辨识度】的人各写一句，描述其说话方式："
    "语气（毒舌/认真/阴阳怪气/怯生生…）、幽默方式（谐音/玩梗/自嘲…）、"
    "腔调（网络黑话/方言/中英夹杂/文绉绉…）、情绪、在关系里的角色（带节奏/捧哏/被起哄/打圆场）。"
    "可以直接引用其原话。只写真实观察到的，不脑补；未发言的人不列入。\n"
    "- participants_personality：（可选）"
    "{\"显示名\": {\"scores\": {\"O/C/E/A/N\": -1.0~1.0}, \"evidence\": \"依据\"}}。"
    "为【每个有对话依据】的人填写，只填有依据的维度，其余省略；evidence 用一两句话说清依据。"
    "无把握则整个字段省略。仅依据该人【冒号右侧的实际发言】，忽略显示名本身。"
)

DEFAULT_DISTILLATION_SYSTEM_PROMPT = (
    "你是一个聊天记录分析助手。你的任务是为一段已经语义聚类好的对话片段提炼结构化信息。\n\n"
    + _CRITERION +
    "只输出单个 JSON 对象，不输出任何其他文字或 markdown 代码块。"
    "下面是格式与写作粒度的范本：\n"
    '{"topic": "周末聚餐安排", "summary": '
    '"[What] Alice 说她上周去过 Bob 推荐的那家店，人均一百二，觉得偏贵但环境安静 '
    '[Who] Alice、Bob [How] Bob 追问要不要提前订位，Alice 说周末必须订 [Eval] 这个价位偏好记一下 | '
    '[What] Alice 提议周六下午去，Carol 说自己五点后才有空，三人没谈拢钟点 '
    '[Who] Alice、Bob、Carol [How] 定了周六，具体时间待 Carol 确认 [Eval] 周末有安排了", '
    '"chat_content_tags": ["聚餐", "餐厅推荐", "周末安排"], '
    '"salience": 0.6, "confidence": 0.55, "inherit": false, '
    '"participant_style": {"Alice": "说话直接，爱用具体数字佐证观点，习惯先给结论再解释", '
    '"Carol": "回话简短偏被动，常以「都行」收尾"}, '
    '"participants_personality": {"Alice": {"scores": {"O": 0.4, "E": 0.6}, '
    '"evidence": "主动分享经历并给出建议，对细节有掌控欲"}}}\n'
    + _EXAMPLE_NOTE
    + _CONTRAST +
    "字段说明：\n"
    + _FIELDS_SUMMARY +
    "- inherit: 是否是上一个事件的直接延续（true/false）\n"
    + _FIELDS_TAIL
)

DEFAULT_EXTRACTOR_SYSTEM_PROMPT = (
    "你是一个聊天记录分析助手。你的任务是将一段连续的对话记录提炼为会话事件，并提取结构化信息。\n\n"
    "这段对话已经由系统按时间、消息数量和语义漂移边界截取。默认请将它提炼为一个会话事件。\n\n"
    "划分逻辑：\n"
    "1. 默认输出一个覆盖 start_idx=0 到 end_idx=最后一条消息的 JSON 对象。\n"
    "2. 不要因为自然推进、追问、补充说明、评价、情绪表达、解决方案、相邻子话题切换而拆成多个数据库事件。\n"
    "   这些内容应作为同一事件 summary 内的多个小话题三元组，用 \" | \" 分隔，"
    "并通过 chat_content_tags 覆盖关键主题。\n"
    "3. 只有当片段之间存在明显跨时间、完全无关、无法作为同一语境理解的独立对话时，才输出多个事件。\n"
    "4. 连续性：如果对话虽然中断但随后继续讨论同一话题，可以视为同一事件的延续（设置 inherit 为 true）。\n\n"
    + _CRITERION +
    "输出格式（仅输出一个 JSON Array，包含一个或多个对象，不输出任何其他文字或 markdown 代码块）。"
    "下面是格式与写作粒度的范本：\n"
    "[\n"
    '  {"start_idx": 0, "end_idx": 12, "topic": "周末聚餐安排", "summary": '
    '"[What] Alice 说她上周去过 Bob 推荐的那家店，人均一百二，觉得偏贵但环境安静 '
    '[Who] Alice、Bob [How] Bob 追问要不要提前订位，Alice 说周末必须订 [Eval] 这个价位偏好记一下 | '
    '[What] Alice 提议周六下午去，Carol 说自己五点后才有空，三人没谈拢钟点 '
    '[Who] Alice、Bob、Carol [How] 定了周六，具体时间待 Carol 确认 [Eval] 周末有安排了", '
    '"chat_content_tags": ["聚餐", "餐厅推荐", "周末安排"], '
    '"salience": 0.6, "confidence": 0.55, "inherit": false, '
    '"participant_style": {"Alice": "说话直接，爱用具体数字佐证观点，习惯先给结论再解释", '
    '"Carol": "回话简短偏被动，常以「都行」收尾"}, '
    '"participants_personality": {"Alice": {"scores": {"O": 0.4, "E": 0.6}, '
    '"evidence": "主动分享经历并给出建议，对细节有掌控欲"}}},\n'
    '  {"start_idx": 13, "end_idx": 20, "topic": "显卡驱动排查", "summary": '
    '"[What] Dave 说装了补丁后加载时间从 40 秒降到 12 秒，Bob 那边仍卡在读条 '
    '[Who] Bob、Dave [How] Dave 建议先更新显卡驱动，约定周五还不行就远程帮看 [Eval] 记下这个约定", '
    '"chat_content_tags": ["硬件故障", "游戏性能"], '
    '"salience": 0.5, "confidence": 0.8, "inherit": false}\n'
    "]\n"
    + _EXAMPLE_NOTE +
    "（第二个对象示范了可选字段可以整个省略。）\n\n"
    + _CONTRAST +
    "字段说明：\n"
    "- start_idx: 该事件在提供的对话记录中的起始索引（从0开始）\n"
    "- end_idx: 该事件在提供的对话记录中的结束索引（包含）\n"
    + _FIELDS_SUMMARY +
    "- inherit: 是否继承上一个已知事件的主题（即本段是上段的延续）\n"
    + _FIELDS_TAIL
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
    "- speaking_style: 一句话概括这个人的说话风格——语气、口癖、幽默方式、腔调、在群里的角色，≤80字符。\n"
    "  只基于提示词中的「说话风格观察」与事件依据；无依据则省略该字段。若已有值，可结合新观察小幅调整。\n"
    "- style_quotes: 1–3 条最能代表其说话风格的原话，从「说话风格观察」的引用里挑，逐字保留；无则省略。\n"
    "不要输出任何其他内容。\n"
    '示例：{"description": "热衷技术讨论，表达直接，偶尔情绪化", '
    '"big_five": {"O": 0.6, "E": 0.4, "N": 0.3}, '
    '"big_five_evidence": {'
    '"O": "Alice 在开放性上表现出高水平，其显著特征为主动引入跨领域话题，可以推断出 80% 的量化结果。", '
    '"E": "Alice 在外向性上表现出中等水平，其显著特征为积极回应但较少主动发起，可以推断出 70% 的量化结果。", '
    '"N": "Alice 在神经质上表现出中等偏高水平，其显著特征为偶因意见分歧情绪波动，可以推断出 65% 的量化结果。"}, '
    '"speaking_style": "说话直接爱抬杠，常用反问，偶尔阴阳怪气", '
    '"style_quotes": ["就这？", "你这不对吧"]}'
)

_DEFAULT_IMPRESSION_SYSTEM_PROMPT = (
    "你是一个社交关系分析助手。根据对话事件，更新对某人的印象。"
    "只输出单行JSON，字段：ipc_orientation（以下8种之一：affinity/active/dominant/arrogant/cold/withdrawn/submissive/deferential）、"
    "benevolence（亲和度，-1.0到1.0的浮点数）、power（支配度，-1.0到1.0的浮点数）、"
    "confidence（0.0到1.0 Hendrick 的浮点数）。不要输出任何其他内容。"
)

_DEFAULT_REANALYZE_IMPRESSION_SYSTEM_PROMPT = (
    "你是一个社交关系分析器。根据用户提供的互动事件摘要，输出单行 JSON，"
    "包含两个浮点字段：benevolence（亲和度，0.0~1.0，越高越友善正向）和 "
    "power（支配度，0.0~1.0，越高越强势权威）。不要输出任何其他内容。"
)


@dataclass
class SynthesisConfig:
    llm_timeout: float = 30.0
    max_events: int = 10
    persona_system_prompt: str = _DEFAULT_PERSONA_SYSTEM_PROMPT
    impression_system_prompt: str = _DEFAULT_IMPRESSION_SYSTEM_PROMPT
    reanalyze_system_prompt: str = _DEFAULT_REANALYZE_IMPRESSION_SYSTEM_PROMPT
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
# Soul state is always injected into system_prompt via its own separate markers.
SOUL_INJECTION_HEADER = "<!-- EM:SOUL:START -->"
SOUL_INJECTION_FOOTER = "<!-- EM:SOUL:END -->"
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
class SoulConfig:
    enabled: bool = False
    decay_rate: float = 0.1
    recall_depth_init: float = 0.0
    impression_depth_init: float = 0.0
    expression_desire_init: float = 0.0
    creativity_init: float = 0.0
    states_ttl_hours: float = 24.0


@dataclass
class ExtractorConfig:
    max_context_messages: int = 20
    llm_timeout: float = 30.0
    llm_max_retries: int = 2
    llm_timeout_growth: float = 1.5
    system_prompt: str = DEFAULT_EXTRACTOR_SYSTEM_PROMPT
    distillation_system_prompt: str = DEFAULT_DISTILLATION_SYSTEM_PROMPT
    strategy: str = "llm"  # "llm" or "semantic"
    semantic_clustering_eps: float = 0.45
    semantic_clustering_min_samples: int = 2
    persona_influenced_summary: bool = True
    # When non-empty, every extracted Event is force-filed under this exact
    # bot_persona_name, bypassing automatic persona resolution. Use this to
    # pin cross-platform deployments of one persona to a single data bucket.
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
            persona_system_prompt=persona_prompt or _DEFAULT_PERSONA_SYSTEM_PROMPT,
            impression_system_prompt=impression_prompt or _DEFAULT_IMPRESSION_SYSTEM_PROMPT,
            reanalyze_system_prompt=reanalyze_prompt or _DEFAULT_REANALYZE_IMPRESSION_SYSTEM_PROMPT,
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
        pos = self._str("injection_position", "user_message_before").strip()
        valid = {"system_prompt", "user_message_before",
                 "user_message_after", "fake_tool_call"}
        relation_enabled = self._bool("relation_enabled", True)
        return InjectionConfig(
            position=pos if pos in valid else "user_message_before",
            auto_clear=self._bool("injection_auto_clear", True),
            token_budget=self._int("retrieval_token_budget", 800),
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
            states_ttl_hours=self._float("soul_states_ttl_hours", 24.0),
        )

    def get_extractor_config(self) -> ExtractorConfig:
        custom_prompt = self._str("extractor_system_prompt", "").strip()
        custom_distill_prompt = self._str(
            "distillation_system_prompt", "").strip()
        tag_seeds_str = self._str("tag_seeds", "社交,日常,技术,知识,工作,娱乐,艺术,情感,资讯")
        tag_seeds = [s.strip() for s in tag_seeds_str.split(",") if s.strip()]
        return ExtractorConfig(
            max_context_messages=self._int(
                "extractor_context_messages",
                min(40, self._int("context_window_size", 50)),
            ),
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
                True
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
