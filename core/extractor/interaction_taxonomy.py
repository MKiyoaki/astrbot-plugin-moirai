"""Hierarchical interaction taxonomy for fact-only event summary segments."""
from __future__ import annotations

from typing import Any


INTERACTION_SCHEMA_VERSION = 1
INTERACTION_ABSTAIN_OPTION = "other"
UNCATEGORISED_TAG = "uncategorised"


def _criterion(
    what: str,
    not_for: str,
    *examples: str,
) -> dict[str, Any]:
    return {"what": what, "not_for": not_for, "examples": list(examples)}


INTERACTION_GROUPS: dict[str, dict[str, str]] = {
    "describing_sharing": {
        "label": "Describing / Sharing",
        "what": "The segment mainly reports, describes, explains, or announces information, situations, past events, or future intentions.",
        "not_for": "Do not use merely because every summary contains facts; use it only when communicating those facts is an interaction purpose.",
    },
    "personal_stance_evaluation": {
        "label": "Personal Stance & Evaluation",
        "what": "The segment expresses a view, judgment, feeling, observation, or grievance.",
        "not_for": "Neutral information sharing without a personal stance.",
    },
    "social_casual_interaction": {
        "label": "Social / Casual Interaction",
        "what": "The segment maintains social connection through small talk, gossip, catching up, or relationship-oriented conversation.",
        "not_for": "Task-focused discussion with no meaningful relationship-maintenance purpose.",
    },
    "storytelling": {
        "label": "Storytelling",
        "what": "The segment deliberately tells a story, anecdote, sequential recount, or illustrative example.",
        "not_for": "A brief factual report of something that happened without a narrative structure.",
    },
    "playful_interaction": {
        "label": "Playful Interaction",
        "what": "The segment uses humour, joking, teasing, banter, or friendly ridicule as an interaction mode.",
        "not_for": "Serious criticism, grievance, or hostile attack without playful framing.",
    },
    "figuring_things_out": {
        "label": "Figuring Things Out",
        "what": "Participants explore, solve, compare, plan, or decide something together.",
        "not_for": "A direct request for information or action without collaborative reasoning.",
    },
    "advice_guidance": {
        "label": "Advice / Guidance",
        "what": "The segment tells or helps someone understand what they should do or how to do it.",
        "not_for": "Asking another person or bot to perform an action for the speaker.",
    },
    "conflict_disagreement": {
        "label": "Conflict / Disagreement",
        "what": "The segment contains opposed positions, debate, or interpersonal conflict.",
        "not_for": "A one-sided complaint with no disagreement, or clearly friendly teasing without a real dispute.",
    },
    "question_request": {
        "label": "Question / Request",
        "what": "The segment asks for information or asks a person or bot to perform an action.",
        "not_for": "Providing an explanation, jointly exploring a question, or instructing someone for their own guidance.",
    },
}


INTERACTION_LEAF_CRITERIA: dict[str, dict[str, Any]] = {
    "describing_sharing": {
        "past_event_recount": _criterion(
            "A concise factual report of something that happened in the past.",
            "A deliberately narrated sequence with scenes or a story arc (storytelling/recount).",
            "报告昨天发生的事情",
        ),
        "present_situation_commentary": _criterion(
            "A description or commentary about a situation currently unfolding.",
            "A personal judgment whose main purpose is evaluation, or a timeless explanation.",
            "描述群聊当前状态",
        ),
        "general_information_explanation": _criterion(
            "Providing general facts, background, definitions, or an explanation.",
            "Asking for that information (question/request) or debating possible answers.",
            "解释规则或概念",
        ),
        "future_event_intention": _criterion(
            "Announcing a future event, intention, commitment, or expected action.",
            "Working out the steps of a plan or comparing alternatives.",
            "说明之后打算做什么",
        ),
    },
    "personal_stance_evaluation": {
        "opinion": _criterion(
            "A position or belief about what is true, preferable, or should be accepted.",
            "A judgment focused on quality/value (evaluation) or a report of emotion.",
            "表达个人看法",
        ),
        "evaluation": _criterion(
            "A judgment of quality, value, performance, success, or failure.",
            "A neutral observation or a proposal about what should be done.",
            "评价作品或表现",
        ),
        "feeling_emotion": _criterion(
            "A direct expression or discussion of a person's emotional state.",
            "A reasoned evaluation without meaningful emotional disclosure.",
            "表达开心、难过或焦虑",
        ),
        "observation_comment": _criterion(
            "A noticed pattern or interpretive comment presented without a strong value judgment.",
            "Plain factual explanation, explicit opinion, or quality evaluation.",
            "指出一个现象",
        ),
        "complaint_grievance": _criterion(
            "Dissatisfaction, frustration, unfairness, or a grievance directed at a situation or actor.",
            "Neutral criticism or an active two-sided dispute.",
            "吐槽糟糕体验",
        ),
    },
    "social_casual_interaction": {
        "chat_small_talk": _criterion(
            "Low-stakes conversation whose main purpose is casual contact.",
            "Focused information exchange, problem solving, or a developed story.",
            "问候和随口闲聊",
        ),
        "gossip": _criterion(
            "Informal discussion or speculation about absent people and their affairs.",
            "Evidence-based news reporting or direct discussion with the person concerned.",
            "聊别人最近的传闻",
        ),
        "catching_up": _criterion(
            "Exchanging personal updates after time apart or reviewing what people have been doing.",
            "A standalone past-event report with no reconnection purpose.",
            "久别后交换近况",
        ),
        "relationship_oriented_talk": _criterion(
            "Conversation mainly maintaining, negotiating, or reflecting on a relationship.",
            "General small talk or an explicit interpersonal conflict.",
            "讨论彼此关系和相处方式",
        ),
    },
    "storytelling": {
        "narrative": _criterion(
            "An extended story with connected events, progression, and narrative focus.",
            "A short self-contained anecdote or concise factual report.",
            "完整讲述一段经历",
        ),
        "anecdote": _criterion(
            "A short, self-contained, often personal or amusing story.",
            "A long narrative or a story used mainly as evidence for a general point.",
            "分享一件短小趣事",
        ),
        "storytelling_recount": _criterion(
            "A chronological reconstruction emphasizing how events unfolded.",
            "A concise past-event report whose purpose is merely to inform.",
            "按顺序复述事情经过",
        ),
        "exemplum": _criterion(
            "A story or case told mainly to illustrate, support, or warn about a broader point.",
            "A story shared for its own sake without an illustrative function.",
            "举故事说明道理",
        ),
    },
    "playful_interaction": {
        "joking": _criterion(
            "A joke or humorous remark primarily intended to amuse.",
            "Reciprocal teasing between participants or ridicule aimed at someone.",
            "讲笑话或抛梗",
        ),
        "banter_teasing": _criterion(
            "Back-and-forth playful teasing or banter between participants.",
            "One-way joking with no exchange, or genuinely hostile conflict.",
            "朋友间互相调侃",
        ),
        "friendly_ridicule": _criterion(
            "Mockery aimed at a person or thing but framed as friendly and non-hostile.",
            "Hostile humiliation, serious criticism, or mutual light banter without ridicule.",
            "善意嘲笑朋友的失误",
        ),
    },
    "figuring_things_out": {
        "exploring_understanding": _criterion(
            "Open-ended collaborative exploration to understand a topic or situation.",
            "A direct factual question expecting an answer, or a concrete problem with a solution target.",
            "一起梳理问题背景",
        ),
        "problem_solving": _criterion(
            "Working toward a solution for a concrete problem or obstacle.",
            "Merely asking someone else to solve or perform it, or comparing unrelated choices.",
            "排查故障并寻找解决办法",
        ),
        "considering_options": _criterion(
            "Comparing alternatives, trade-offs, or possible courses of action without committing.",
            "Organising execution steps after a direction is chosen.",
            "比较多个方案",
        ),
        "planning": _criterion(
            "Organising future steps, timing, roles, or resources toward a goal.",
            "Announcing an intention without working out steps, or deciding which option to choose.",
            "安排时间和执行步骤",
        ),
        "decision_oriented_discussion": _criterion(
            "Discussion aimed at selecting, rejecting, or committing to an option.",
            "Open comparison with no decision focus, or implementation planning after the choice.",
            "讨论后作出选择",
        ),
    },
    "advice_guidance": {
        "advice": _criterion(
            "A recommendation tailored to what another person should do in their situation.",
            "A tentative idea offered to the group, or procedural teaching.",
            "建议对方如何处理困境",
        ),
        "suggestion": _criterion(
            "A tentative option or proposal offered for consideration.",
            "Firm personal advice or step-by-step instruction.",
            "提议可以换一种做法",
        ),
        "instruction": _criterion(
            "Procedural guidance explaining how the recipient can perform something.",
            "A request or command asking the recipient to perform it for the speaker.",
            "说明具体操作步骤",
        ),
    },
    "conflict_disagreement": {
        "difference_of_opinion": _criterion(
            "Participants hold different views but do not substantially argue them.",
            "A developed exchange of arguments or relationship-level hostility.",
            "双方看法不同但未争论",
        ),
        "debate": _criterion(
            "Participants actively exchange reasons or arguments for opposing positions.",
            "A simple disagreement or personal hostility without substantive argument.",
            "围绕观点展开辩论",
        ),
        "interpersonal_conflict": _criterion(
            "A dispute involving hostility, accusation, relationship strain, or personal confrontation.",
            "Friendly teasing or impersonal debate about an issue.",
            "发生针对个人的冲突",
        ),
    },
    "question_request": {
        "information_seeking": _criterion(
            "A question asking another person or bot for facts, explanation, knowledge, or data.",
            "Joint open-ended exploration, rhetorical questions, or providing information.",
            "询问战绩、时间或概念",
        ),
        "action_request": _criterion(
            "A request or command asking another person or bot to perform an action for the speaker.",
            "Guidance that teaches the recipient how to act, or announcing one's own intention.",
            "请 bot 查询、总结或执行操作",
        ),
    },
}

for _criteria in INTERACTION_LEAF_CRITERIA.values():
    _criteria[INTERACTION_ABSTAIN_OPTION] = _criterion(
        "No leaf in this group fits the segment clearly.",
        "Any segment that reasonably fits one of the declared leaves.",
    )


_LEAF_TO_GROUP: dict[str, str] = {
    leaf: group_id
    for group_id, leaves in INTERACTION_LEAF_CRITERIA.items()
    for leaf in leaves
    if leaf != INTERACTION_ABSTAIN_OPTION
}


def leaf_group(leaf_id: str) -> str:
    """Return the first-layer group of a leaf, or '' when it is not one.

    The placeholder tag for an event whose segments all abstained is its own
    category, so it never falls through to a keyword guess.
    """
    text = str(leaf_id or "").strip()
    if text == UNCATEGORISED_TAG:
        return UNCATEGORISED_TAG
    return _LEAF_TO_GROUP.get(text, "")


def group_question(segment_index: int, group_id: str) -> str:
    group = INTERACTION_GROUPS[group_id]
    return (
        f"To what extent does [Segment {segment_index}] perform the interaction function "
        f"'{group['label']}'? What counts: {group['what']} "
        f"Do not count: {group['not_for']} Multiple interaction groups may apply to the same segment."
    )


def leaf_question(segment_index: int, group_id: str) -> str:
    label = INTERACTION_GROUPS[group_id]["label"]
    return (
        f"Within the interaction group '{label}', which subtype best describes "
        f"[Segment {segment_index}]? Choose 'other' if no subtype fits clearly."
    )
