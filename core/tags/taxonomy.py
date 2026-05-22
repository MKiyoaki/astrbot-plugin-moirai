"""Deterministic category mapping for concrete chat content tags.

The extractor should keep ``chat_content_tags`` specific. This module derives a
stable upper category for each concrete tag so retrieval and UI can use broad
facets without polluting the concrete tag layer.
"""
from __future__ import annotations

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
    ("资讯", ("资讯", "新闻", "消息", "难度", "公告")),
    ("日常", ("日常", "闲聊", "早安", "下午好", "晚安", "测试")),
)


def infer_tag_category(tag: str) -> str:
    text = str(tag or "").strip()
    if not text:
        return "日常"
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
