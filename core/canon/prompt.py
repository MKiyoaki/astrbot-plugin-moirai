"""canon 抽取 prompt：system prompt 常量、user prompt 构造和长场景切块。

user prompt 完全由场景数据确定性生成。system prompt 的任何修改都要递增 PROMPT_VERSION，
已缓存的抽取结果会因此全部失效并重新抽取。
"""
from __future__ import annotations

PROMPT_VERSION = "canon-extract-v3"

SYSTEM_PROMPT = """你是剧情记忆标注员。输入是一个游戏剧情场景的逐行文本，每行带编号 L1、L2……。你的任务是为指定的"目标角色"整理这一场景中的事件，以及她和每个事件的关系。只输出一个 JSON 对象，不要输出任何其他文字。

总原则
1. 只依据本场景的文本。不要使用你对这部作品的任何外部知识，不要补充文本里没有的信息，不要推测后续剧情。
2. 每条结论都必须给出证据行编号（L 编号），而且只能引用本场景里存在的行。
3. 说话人以显示名为准。只有显示名在"已确认显示名"名单里的台词，才算目标角色说的；名单外的相似名字（比如带问号或引号的）当作另一个说话人，他们的台词不能作为目标角色视角的证据。显示名为"？？？"的说话人，不要猜测是谁。
4. "博士"是玩家角色。在 topic、summary、beats、episode、target、stance 里提到博士时，一律写成 {DOCTOR}；需要用代词指代博士时写"ta"，不要写"他"或"她"。在 participants 里写成 "@doctor"；entities 里不要列出博士。类型为"选项"的行，是博士说出的话。
5. 文本没有写到的事，不等于没有发生。无法判断时，用 unstated 或 unknown，不要硬判。

输出字段
events：本场景里值得记住的事件，按发生顺序排列。
  一个事件是目标角色视角下一段连贯的情节：一个场面、一轮交锋、一段围绕同一话题的对话，而不是每一次出手或每一句话。只在自然的断点切开：场景或地点转换、一段对话或一轮交锋结束、话题转折、她的参与方式改变（比如从旁观变成亲自下令）；她回忆或讲述的往事见 views 的说明。连续的攻防、同一场对话里的来回合成一个事件；她不在场的部分可以更粗，一段连续的情节写成一条。一个事件通常覆盖 8–40 行（场景很短时除外），每个场景通常 2–8 个事件，很长的场景也不超过 12 个。目标角色在场参与的重要情节不要遗漏。
  id：e1、e2……
  topic：不超过 20 字的短标题
  summary：不超过 300 字，用第三人称客观叙述。按发生顺序缩写这段情节：起因、经过中的关键动作和台词要点、结果，不要只写一句概括。提到人物时用文本里出现的名字
  beats：这个事件里值得单独检索的细节，按顺序排列，0–5 条，[{text, evidence}]。text 不超过 25 字，写一个具体的动作、转折或台词要点；evidence 是这条细节的行号，取自本事件的 evidence。事件很短、没有可拆的细节时为空数组
  in_world_time：present（场景当下正在发生）/ past（这一场景里被回忆、讲述的过去；旁白表明整个场景都在讲述往事时也用 past）/ unknown
  in_world_note：文本明确给出了时间（比如"约十年前""三天前"）就要填写，只能写文本明确给出的信息；没有就留空
  participants：参与这个事件的人物（显示名或 "@doctor"）
  entities：事件涉及的有专名的人物、地点、势力、物品、概念，[{name, type}]，type ∈ person / place / faction / object / concept。只收文本里出现的专有名称，不要收"希望""死亡""故事""父亲"这类普通名词或泛称
  evidence：支撑这个事件的行号，数量不限，关键台词都要列出
views：对每个事件，给出目标角色和它的关系，每个事件恰好一条。
  character：目标角色的名字
  event：事件 id
  channel：
    experienced 她是这件事的参与者（说话、行动，或者被别人直接作用）
    witnessed   她在场，但不是主要参与者（文本表明她在场）
    told        这件事发生在别处或过去，她在本场景里是听别人讲述或读到的
    recalled    她自己回忆、梦见，或者以其他方式想起了这件事
    unstated    文本没有表明她在场或知情（这不等于她不知道）
  evidence：能说明这种关系的行号；channel 为 unstated 时可以为空数组
  note：可选，不超过 30 字
  她在本场景里回忆或讲述的往事，要单独作为一个 in_world_time 为 past 的事件，channel 用 recalled，不要和当下发生的事合并成一个事件。
episode：如果目标角色本人在本场景里出场（说话、行动，或旁白写明她在场），并且有 experienced 或 witnessed 的事件，就用她的第一人称写一段不超过 200 字的场景回忆：她经历了什么，当时的感受和想法（只写文本能支持的）。否则为 null。格式：{"character": 目标角色, "text": ...}
cognitions：本场景里目标角色对某个对象（人物、势力、力量、概念等）表现出的看法或态度，[{character, target, stance（不超过 40 字）, evidence}]，没有就是空数组
edges：本场景里事件之间的关系，[{from, to, type, explicit, confidence, evidence}]
  type：cause（from 导致 to）/ motivation（from 是 to 的动机）/ emotion_source（from 引起了 to 中的情绪）/ cognition_update（from 改变了某人在 to 中的认知）
  explicit：原文明确说出了这层关系就是 true，只是你推断的就是 false
  confidence：0 到 1
  evidence：explicit 为 true 时必须给出
  原文用"因为""所以""为了""于是"之类的话明确说出了因果或动机时，要写成 explicit 为 true 的边。

只输出 JSON。"""

KIND_LABEL = {
    "dialogue": "对白", "inner_voice": "心声", "narration": "旁白", "subtitle": "字幕",
    "caption": "屏幕文字", "option": "选项", "title": "标题", "header": "标题",
    "tutorial": "教程", "other": "其他",
}
SPEAKING_KINDS = ("dialogue", "inner_voice")
CHUNK_TRIGGER = 20000
CHUNK_LIMIT = 12000
CUT_KINDS = ("narration", "title", "header")


def render_line(no: int, line: dict) -> str:
    kind = line["kind"]
    label = KIND_LABEL.get(kind, "其他")
    if kind == "option":
        speaker = "博士（选项）"
    elif kind in SPEAKING_KINDS:
        speaker = line.get("spk") or "（无名）"
    else:
        speaker = line.get("spk") or ""
    body = f"{speaker}：{line['text']}" if speaker else line["text"]
    return f"L{no} [{label}] {body}"


def character_header(character: dict) -> str:
    names = "、".join(character["confirmed_names"]) or character["display"]
    ids = "、".join(character.get("char_ids") or []) or "无"
    header = f"[目标角色] {character['display']}（已确认显示名：{names}；干员ID：{ids}"
    pending = character.get("pending_names") or []
    if pending:
        header += f"；以下显示名是其他说话人，不是她：{'、'.join(pending)}"
    return header + "）"


def chunk_ranges(lines: list[dict]) -> list[tuple[int, int]]:
    """返回 [start, end) 的行下标区间。正文不超过 CHUNK_TRIGGER 时只有一块。

    切块只落在行边界上，优先在旁白或标题行之前切；找不到这样的行就在超限前一行切。
    """
    rendered = [len(render_line(i + 1, line)) + 1 for i, line in enumerate(lines)]
    if sum(rendered) <= CHUNK_TRIGGER:
        return [(0, len(lines))]
    ranges, start = [], 0
    while start < len(lines):
        size, end, cut = 0, start, None
        while end < len(lines) and size + rendered[end] <= CHUNK_LIMIT:
            if end > start and lines[end]["kind"] in CUT_KINDS:
                cut = end
            size += rendered[end]
            end += 1
        if end < len(lines) and cut is not None:
            end = cut
        end = max(end, start + 1)
        ranges.append((start, end))
        start = end
    return ranges


def build_user_prompt(scene: dict, character: dict, prev_scene: dict | None,
                      start: int = 0, end: int | None = None) -> str:
    """构造一块的 user prompt。L 编号取场景内的全局序号，切块后也不重新从 1 开始。"""
    lines = scene["lines"]
    end = len(lines) if end is None else end
    summary = (scene.get("official_summary") or "").strip() or "无"
    if prev_scene and (prev_scene.get("official_summary") or "").strip():
        prev = f"上一场景「{prev_scene['anchor']}」的官方简介：{prev_scene['official_summary'].strip()}"
    else:
        prev = "无"
    out = [
        character_header(character),
        f"[场景] {scene['anchor']}",
        f"[官方简介] {summary}",
        f"[前情] {prev}",
        "[台词] 每行的格式是：编号 [类型] 显示名：文本",
    ]
    out.extend(render_line(i + 1, lines[i]) for i in range(start, end))
    return "\n".join(out)


def retry_suffix(errors: list[str]) -> str:
    return "\n\n[上次输出的问题]\n" + "\n".join(f"- {e}" for e in errors) + "\n请修正后重新输出完整的 JSON。"
