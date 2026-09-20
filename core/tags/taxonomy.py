"""Category mapping for concrete chat content tags.

The extractor should keep ``chat_content_tags`` specific. This module derives a
stable upper category for each concrete tag so retrieval and UI can use broad
facets without polluting the concrete tag layer.

Two sources feed ``infer_tag_category``. Categories learned from the external
classifier (see ``core/extractor/category_pass.py``) win; the deterministic
keyword rule below is the offline fallback and the answer for any tag that has
not been classified. Learned categories live in a process-wide map replaced
wholesale on update, so readers stay synchronous and never touch the network.
"""
from __future__ import annotations

from typing import Any, Mapping

DEFAULT_TAG_CATEGORIES = (
    "游戏",
    "社交",
    "情感",
    "技术",
    "知识",
    "工作",
    "创作",
    "日常",
    "资讯",
    "艺术",
    "娱乐",
)

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("游戏", ("游戏", "攻略", "明日方舟", "原神", "卫戍", "深渊", "剧情", "王者", "抽卡", "角色", "玩家")),
    ("技术", ("技术", "代码", "系统", "模型", "diffusion", "图片生成", "bot", "机器人", "记忆", "算法", "优化", "接口", "工程")),
    ("知识", ("学术", "大五人格", "性格分析", "论文", "数学", "凸优化", "高考", "教育", "分析", "解释", "理论", "实数域")),
    ("工作", ("工作", "导师", "稿费", "项目", "任务", "排期", "论文分享", "职场", "合作")),
    ("情感", ("告白", "喜欢", "示好", "思念", "调情", "撒娇", "依恋", "难过", "情绪", "恋爱")),
    ("社交", ("社交", "互动", "对话", "调侃", "吐槽", "玩笑", "群聊", "问候", "挑衅", "性取向")),
    ("创作", ("诗", "写作", "评论区", "图片", "创作", "素材", "文案", "绘画")),
    ("艺术", ("艺术", "音乐", "文学", "诗歌", "摄影", "绘画")),
    ("娱乐", ("娱乐", "段子", "综艺", "搞笑", "影视", "视频")),
    ("资讯", ("资讯", "新闻", "消息", "难度", "公告")),
    ("日常", ("日常", "闲聊", "早安", "下午好", "晚安", "测试")),
)

# Option id the classifier may pick to abstain; it maps to no category.
ABSTAIN_OPTION = "other"

# (option id sent to the classifier, category name, criteria). Option ids and
# descriptions are English on purpose: the classifier handles CJK less well than
# English, so only the conversation text itself is left in Chinese.
_CATEGORY_SPECS: tuple[tuple[str, str, dict[str, Any]], ...] = (
    ("game", "游戏", {
        "what": "Content about one specific video, mobile, board or tabletop game: mechanics, characters, ships, numbers, strategy, patch news, matches.",
        "not_for": "General entertainment such as memes or videos (entertainment); making creative works (creation).",
        "examples": ["战舰世界", "抽卡", "游戏攻略"],
    }),
    ("social", "社交", {
        "what": "Interpersonal chatter among the people in the conversation: greetings, teasing, banter, group dynamics.",
        "not_for": "Romantic or emotional disclosure (emotion); plain daily-life talk (daily).",
        "examples": ["调侃", "群聊", "问候"],
    }),
    ("emotion", "情感", {
        "what": "Feelings and intimate relationships: affection, confession, longing, sadness, mood, romance.",
        "not_for": "Casual teasing or greetings (social).",
        "examples": ["告白", "思念", "难过"],
    }),
    ("tech", "技术", {
        "what": "Software, hardware, AI models, programming, bots, systems, engineering and optimisation.",
        "not_for": "Academic theory or general explanations (knowledge); scheduling and deadlines (work).",
        "examples": ["代码", "机器人", "模型"],
    }),
    ("knowledge", "知识", {
        "what": "Academic or explanatory content: science, mathematics, education, theories, analysis of how things work.",
        "not_for": "Hands-on software or engineering work (tech).",
        "examples": ["数学", "论文", "高考"],
    }),
    ("work", "工作", {
        "what": "Jobs, projects, tasks, deadlines, collaboration, income and career matters.",
        "not_for": "Discussing the technology itself (tech).",
        "examples": ["排期", "导师", "稿费"],
    }),
    ("creation", "创作", {
        "what": "Making or sharing one's own creative output: writing, poetry, drawing, image generation, copywriting, source material.",
        "not_for": "Discussing or consuming existing works (art, entertainment).",
        "examples": ["写作", "绘画", "文案"],
    }),
    ("daily", "日常", {
        "what": "Everyday life routines: meals, health, sleep, weather, exercise, errands, small talk with no other topic.",
        "not_for": "Any topic that fits a more specific category.",
        "examples": ["早安", "饮食", "晚安"],
    }),
    ("news", "资讯", {
        "what": "News, announcements, updates and information lookup: current events, release notes, data queries.",
        "not_for": "Mechanics or strategy of a specific game (game).",
        "examples": ["新闻", "公告", "数据查询"],
    }),
    ("art", "艺术", {
        "what": "Art appreciation and criticism: music, literature, poetry, photography, painting as subjects of discussion.",
        "not_for": "Producing one's own creative work (creation); casual videos and memes (entertainment).",
        "examples": ["音乐", "摄影", "文学"],
    }),
    ("entertainment", "娱乐", {
        "what": "General entertainment consumption not tied to one specific game: memes, jokes, videos, shows, celebrity chatter, casual fun.",
        "not_for": "Mechanics, characters or numbers of a specific game (game).",
        "examples": ["段子", "综艺", "搞笑"],
    }),
)

CATEGORY_CRITERIA: dict[str, Any] = {
    option: criteria for option, _, criteria in _CATEGORY_SPECS
}
CATEGORY_CRITERIA[ABSTAIN_OPTION] = {
    "what": "None of the categories above fits, or the label is too ambiguous to place.",
    "not_for": "Anything that reasonably fits one of the categories above.",
    "examples": [],
}

_CATEGORY_BY_OPTION: dict[str, str] = {option: name for option, name, _ in _CATEGORY_SPECS}

_learned: dict[str, str] = {}


def category_for_option(option: str) -> str | None:
    """Category name for a classifier option id; None for abstention or unknown."""
    return _CATEGORY_BY_OPTION.get(option)


def set_learned_categories(mapping: Mapping[str, str]) -> None:
    """Replace the learned map. Unknown categories and blank tags are dropped."""
    global _learned
    valid = set(DEFAULT_TAG_CATEGORIES)
    _learned = {
        str(tag).strip(): category
        for tag, category in mapping.items()
        if str(tag).strip() and category in valid
    }


def learn_category(tag: str, category: str) -> None:
    """Add one learned tag category, replacing the map so readers never see a partial write."""
    global _learned
    text = str(tag or "").strip()
    if text and category in DEFAULT_TAG_CATEGORIES:
        _learned = {**_learned, text: category}


def clear_learned_categories() -> None:
    global _learned
    _learned = {}


def infer_tag_category(tag: str) -> str:
    """Resolve a tag to its broad category, preferring the interaction taxonomy.

    Derived tags are leaf ids whose parent group is their category, so the
    answer is exact. The learned cache and keyword table below only serve tags
    left over from free-form extraction.
    """
    text = str(tag or "").strip()
    if not text:
        return "日常"
    from ..extractor.interaction_taxonomy import leaf_group

    derived = leaf_group(text)
    if derived:
        return derived
    learned = _learned.get(text)
    if learned:
        return learned
    lower = text.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword.lower() in lower for keyword in keywords):
            return category
    return "日常"


def derive_tag_categories(tags: list[str] | tuple[str, ...] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for tag in tags or []:
        value = str(tag or "").strip()
        if value:
            result[value] = infer_tag_category(value)
    return result
