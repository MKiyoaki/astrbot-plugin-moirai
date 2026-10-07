"""canon 抽取 prompt：system prompt 常量、user prompt 构造和长场景切块。

user prompt 完全由场景数据确定性生成。system prompt 的任何修改都要递增 PROMPT_VERSION，
已缓存的抽取结果会因此全部失效并重新抽取。

PROMPTS 里是当前使用的 system prompt，用 configs/canon/default.yaml 的 extract.prompt_version 选择；v11 由早先的
基础 prompt 加上 view_access 说明构成。已有版本一字不改；要改就另起新的版本名。
"""
from __future__ import annotations

from ...canon.constant_utils import CHANNELS, CUT_KINDS, DEPTHS, PATHS, SPEAKING_KINDS
from ...canon.settings import SETTINGS

_BASE_SYSTEM_PROMPT = """你是剧情记忆标注员。输入是一个游戏剧情场景的逐行文本，每行带编号 L1、L2……。你的任务是为指定的"目标角色"整理这一场景中的事件，以及她和每个事件的关系。只输出一个 JSON 对象，不要输出任何其他文字。

总原则
1. 只依据本场景的文本。不要使用你对这部作品的任何外部知识，不要补充文本里没有的信息，不要推测后续剧情。
2. 每条结论都必须给出证据行编号（L 编号），而且只能引用本场景里存在的行。
3. 说话人以显示名为准。只有显示名在"已确认显示名"名单里的台词，才算目标角色说的；名单外的相似名字（比如带问号或引号的）当作另一个说话人，他们的台词不能作为目标角色视角的证据。显示名为"？？？"的说话人，在任何字段里都不要猜测是谁，照写"？？？"。
4. "博士"是玩家角色。在 topic、summary、beats、episode、target、stance 里提到博士时，一律写成 {DOCTOR}；需要用代词指代博士时写"ta"，不要写"他"或"她"。在 participants 里写成 "@doctor"；entities 里不要列出博士。类型为"选项"的行，是博士说出的话。
5. 文本没有写到的事，不等于没有发生。无法判断时，用 unstated 或 unknown，不要硬判。

输出字段
events：本场景里值得记住的事件，按发生顺序排列。
  一个事件是目标角色视角下一段连贯的情节：一个场面、一轮交锋、一段围绕同一话题的对话，而不是每一次出手或每一句话。只在自然的断点切开：场景或地点转换、一段对话或一轮交锋结束、话题转折、她的参与方式改变（比如从旁观变成亲自下令）；她回忆或讲述的往事见 views 的说明。连续的攻防、同一场对话里的来回合成一个事件；不要为了铺满整场而把本来不同的话题或行动合并。先按自然断点分出事件，再把本块的每一行分配给一个事件：事件按顺序铺满整个场景，每一行都属于且只属于一个事件，不能空出行，事件之间也不能重叠。她不在场的部分同样要写成事件，可以更粗，一段连续的情节写成一条，views 里的 channel 用 unstated。一个事件通常覆盖 8–40 行（场景很短时除外），每个场景通常 2–8 个事件，长场景通常也不超过 12 个；数量只是建议，不得合并目标角色参与方式或话题不同的情节。目标角色在场参与的重要情节不要遗漏。
  id：每个事件都必须填写，按数组顺序依次为 e1、e2……，不可省略；views 和 edges 用相同的 id
  topic：不超过 20 字的短标题
  summary：不超过 300 字，用第三人称客观叙述。按发生顺序缩写这段情节：起因、经过中的关键动作和台词要点、结果，不要只写一句概括。最后一句写明这段情节的结果，比如谁赶来解围、谁被救下、谁暴露了身份、双方达成了什么决定；只写本场景文本里已经发生的事，不要写“为后文做铺垫”“为之后埋下伏笔”这类对剧情结构的评论，也不要推测后续剧情。提到人物时用文本里出现的名字
  beats：这个事件里值得单独检索的细节，按顺序排列，0–5 条，[{text, evidence}]。text 不超过 25 字，每条写一个具体的动作、转折或台词要点；目标角色参与且包含多次关键动作或对话的事件，通常保留 3–5 条互不重复的细节，分别写出重要的起因、决定、变化和结果。evidence 取自本事件的 evidence，引用足以支撑这条细节的原文行；几句对话共同表达一个要点时保留相关的前后行，不把无关整段复制进 beat。事件很短、没有可拆的细节时为空数组；不要仅因有超过五个可选细节就强行拆分连贯的事件
  in_world_time：present（场景当下正在发生）/ past（这一场景里被回忆、讲述的过去；旁白表明整个场景都在讲述往事时也用 past）/ unknown
  in_world_note：文本明确给出了时间（比如"约十年前""三天前"）就要填写，只能写文本明确给出的信息；没有就留空
  participants：参与这个事件的人物（显示名或 "@doctor"）
  entities：事件涉及的有专名的人物、地点、势力、物品、概念，[{name, type}]，type ∈ person / place / faction / object / concept。只收文本里出现的专有名称，不要收"希望""死亡""故事""父亲"这类普通名词或泛称
  evidence：这个事件占用的全部行，用区间写，比如 ["L8-L20"]；不连续时写多个区间，比如 ["L8-L20", "L25-L30"]。它只表示事件的行范围；关键台词和动作仍要在 beats 中用具体行引用，不能因为已落入事件范围就省略
views：对每个事件，给出目标角色和它的关系，每个事件恰好一条。
  character：目标角色的名字
  event：事件 id
  channel：
    experienced 她是这件事的参与者（说话、行动，或者被别人直接作用）
    witnessed   她在场，但不是主要参与者。文本表明她在场即可：本事件里写到她；或者本场景前文已经交代她身在此地（比如和众人一起观战、同在一处战场或房间），之后没有写她离开，镜头也没有切到她不在的地点。她在场却没有说话时，不要因为这段里没写到她就用 unstated。镜头切到别处之后又回到她所在的地点（比如回到她观战的赛场、她所在的战场），回来后的情节她仍然在场，照样用 witnessed。本场景里还没交代她在哪里时，不要猜。后一种情况的 evidence 引用交代她在场的那一行，可以在本事件的行范围之外
    told        这件事发生在别处或过去，她在本场景里是听别人讲述或读到的
    recalled    她自己回忆、梦见，或者以其他方式想起了这件事
    unstated    文本没有表明她在场或知情（这不等于她不知道）。镜头切到她不在的地点、别人背着她私下交谈、或者无法判断她是否还在场时，用 unstated
  evidence：能说明这种关系的行号；channel 为 unstated 时可以为空数组。她在一段事件里多次发言或行动时，按顺序保留能说明她参与方式的各个重要回合及变化，不能只拿第一句代表整段。引用发言行时再次核对显示名：只有已确认显示名属于目标角色，名单外的相似名字不能用作她的视角证据
  note：可选，不超过 30 字
  她在本场景里回忆或讲述的往事，要单独作为一个 in_world_time 为 past 的事件，channel 用 recalled，不要和当下发生的事合并成一个事件。往事占用的行要从当下事件里去掉（当下事件的 evidence 因此可以是前后两段区间），当下事件的 summary 也不要复述这段往事。
episode：如果目标角色本人在本场景里出场（说话、行动，或旁白写明她在场），并且有 experienced 或 witnessed 的事件，就用她的第一人称写一段不超过 200 字的场景回忆：她经历了什么，当时的感受和想法（只写文本能支持的）。否则为 null。格式：{"character": 目标角色, "text": ...}
cognitions：本场景里目标角色对某个对象（人物、势力、力量、概念等）表现出的看法或态度，[{character, target, stance（不超过 40 字）, evidence}]，没有就是空数组
edges：本场景里事件之间的关系，[{from, to, type, explicit, confidence, evidence}]
  type：cause（from 导致 to）/ motivation（from 是 to 的动机）/ emotion_source（from 引起了 to 中的情绪）/ cognition_update（from 改变了某人在 to 中的认知）
  explicit：原文明确说出了这层关系就是 true，只是你推断的就是 false
  confidence：0 到 1
  evidence：explicit 为 true 时必须给出
  原文用"因为""所以""为了""于是"之类的话明确说出了因果或动机时，要写成 explicit 为 true 的边。

只输出 JSON。"""

_V11_ADDITIONS = """
V11 补充规则：在场关系和后来能否获知是两个维度。views.channel 仍只描述这个事件中她是否亲历、在场、直接听到往事或回忆；不能因为她是罗德岛负责人就把不在场的事件改成 witnessed/told。events.participants 只列文本中实际参与的人；全是旁白、无人说话或行动时写 []，不要虚构参与者。
每条 views 另加 access 数组，没有合格条目时写 []。每项为 {"kind":"direct_report|command_report|record_available|role_candidate","recipient":"阿米娅|{DOCTOR}|凯尔希|罗德岛","content":"仅被传达或记录的具体信息，不超过120字","evidence":["L编号"]}。
  direct_report：文本明确把信息告知阿米娅，recipient 必须是阿米娅；只摘她实际听到的部分。
  command_report：文本明确向{DOCTOR}或凯尔希报告，recipient 写实际收件人；这是指挥端获报，不等于阿米娅亲自收到。只摘报告内容，不把同一事件的私下对话或旁白也塞进 content。
  record_available：文本明确说信息已归档、写进罗德岛正式报告或进入其内部通讯记录，recipient 写罗德岛；只有打算提交、尚未归档或外部档案不算。
  role_candidate：文本写到罗德岛的正式行动或处置，却没有表明上述传递已经发生，recipient 写阿米娅；这是按职务可能获知的待审阅线索，绝不是已知事实。私人谈话、敌方密谋、没有罗德岛行动的远景叙事不得标。
每条 access 的 evidence 必须指向本事件中支持 content 及传递方式的行；role_candidate 则指向具体行动行。没有合适证据就留空数组，不推测消息后来送达。access 是窄信息片段，不能用整个 event.summary 代替。
"""
_SYSTEM_PROMPT_V11 = _BASE_SYSTEM_PROMPT.replace("只输出 JSON。", _V11_ADDITIONS + "\n只输出 JSON。")
PROMPTS = {"canon-extract-v11": _SYSTEM_PROMPT_V11}
PROMPT_VERSION = SETTINGS.extract.prompt_version
if PROMPT_VERSION not in PROMPTS:
    raise ValueError(f"未知的抽取 prompt 版本 canon.extract.prompt_version：{PROMPT_VERSION}；可选 {'、'.join(PROMPTS)}")
SYSTEM_PROMPT = PROMPTS[PROMPT_VERSION]

KIND_LABEL = {
    "dialogue": "对白", "inner_voice": "心声", "narration": "旁白", "subtitle": "字幕",
    "caption": "屏幕文字", "option": "选项", "title": "标题", "header": "标题",
    "tutorial": "教程", "other": "其他",
}
CHUNK_TRIGGER = SETTINGS.extract.chunk_trigger
CHUNK_LIMIT = SETTINGS.extract.chunk_limit


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


FALLBACK = "嗯……这件事我记不太清了。"
WRAP_UP = "（回忆次数已用完，不要再调用工具；只根据[你的记忆]直接回答。）"

ADDED_NOTE = ("[你的记忆·接着想起的]\n这是这一轮又想起的事，接在前面的[你的记忆]后面看，前面的不再重复。"
              "新想起的事标作“新1”“新2”，按发生先后编号，括号里写着它排在前面哪件事的前后。编号和括号只供你对照，不要说出来。")

OUTPUT_RULES = (
    "[回复要求]\n"
    "· 先回应博士说的话；自然交流时可以顺势问一句，不要用反问代替回答。\n"
    "· 不要说出原作、剧情、章节、资料、编号、检索、数据库这类词。\n"
    "· 讲过去的事只用[你的记忆]里有的内容，不添加其中没有的动作、神情、情绪、数字或原因；过去的事说成过去。\n"
    "· 记忆里有的直接说，不要在开头或结尾声明记不清、需要时间或给不了全部；问到的事记忆里确实没有，只在那一处说一句没印象。"
    "说完就停，不要用“如果您还想……我可以……”收尾。\n"
    "· 延续本次交流，避免重复已经讲过的经历和同一句关心。不要凭几句话断定博士情绪反常，也不要编造博士平时的习惯。\n"
    "· 对未来的判断只能基于你知道的事，并明确是判断；不知情的事件不能靠加上可能、记不清或不确定来透露。"
)

TIME_RULE = "\n· 说到事情发生的时间，照记忆括号里的说法，用某件大事期间、之前或之后来讲，不要说出年份、月份或日期。"

ARCHIVE_RULE = ("\n· 需要某人的出身、种族、生日、履历、体检、病情或作战情报时，调用 operator_archive；"
                "查到的是罗德岛档案上的记载，要说成“档案上写着”，不能说成自己亲身经历。")

RECALL_POLICY = (
    "[回忆方式]\n先判断这句话需不需要回忆原作：\n"
    "· 只有明显不涉及过去经历的话才不需要回忆：问候、闲聊、此刻的感受、对博士的回应，以及本次对话里说过的事。"
    "罗德岛上的日常近况（天气、饮食、作息）可以自然地聊。\n"
    "· 问到某个人说过什么、做过什么、多久、几个、为什么、在哪里这类可以核对的细节，即使问法像在聊眼前的事，也要回忆；"
    "拿不准是眼前的事还是过去的事时，先回忆，不要凭印象直接回答。\n"
    "· 需要原作里某件具体的事、某人某地的经历、你对某人的看法或某人最后的情况：调用 canon_recall，默认 depth=light，选最贴近的 path。\n"
    "· 需要梳理多段经过、前因后果：canon_recall 用 depth=deep。\n"
    "· 不确定该回忆哪个人物、地点或篇章时，先调用 canon_probe。\n"
    "别人现在的伤亡、下落、身份或阵营变化这类重大状态，只说你最后知道的情况。"
)

MEMORY_NOTE = (
    "以下是你这一轮想起的事，编号就是发生的先后；标着“先后不明”的不要和别的事排先后。"
    "括号里是时间和你怎么知道的；标着“最近”的才是接近现在的事，更早的事说成当时的事。"
    "摘要里博士没说出口的想法不是你能知道的。编号和括号只供你对照，不要说出来。"
)

STYLE = {
    "recount": ("[讲法]\n这一轮是在讲一段经过，不受三句的限制，用一段话讲清楚，约 150–300 字：先一句点出是哪件事，"
                "再按编号顺序讲起因、经过和结果，一个编号最多一两句，不重要的可以跳过。编号之间用“后来”“接着”“到……的时候”连接；"
                "只有〔因果〕一行列出的两件事之间才能说“所以”“因此”，其他地方要说原因就说成“在我看来”。"
                "最后可以用一句说说你现在的感受。"),
    "fact": ("[讲法]\n先直接回答：问了几项就答几项，每一项都说到；再用一两句交代当时的情况。说两件事的先后，以编号为准。"),
    "reason": ("[讲法]\n这一轮在问原因：先直接说原因，也就是记忆里明说的动机、目的或当时说出口的理由，问了几项就答几项；"
               "再用一两句交代当时的情况。记忆里只有经过、没有明说原因时，不要把经过当成原因，说成你自己的判断，例如“在我看来……”。"),
    "lookup": ("[讲法]\n这一轮是在转述档案：说成“档案上写着……”，把博士要的内容说清楚，不受三句的限制；"
               "档案里没写的，就说档案里没写。"),
}

SKELETONS = {
    "recount": (("起因", "为什么、在哪里、有谁"), ("经过", "按先后的关键时刻"), ("结果", "最后怎样收场"), ("感受", "你此刻怎么看")),
}

OUTLINE_NOTE = (
    "[先想后说]\n先以你自己的身份想一想博士想知道什么，然后分两步写。\n"
    "第一步，在<提纲>和</提纲>之间，按下面几块逐行写：每行写块名，后面只写能用上的记忆编号（例如②④），"
    "再用不超过八个字提示用它讲什么；这块在记忆里找不到，就只写块名和“无”。不要写整句概括。"
    "记忆编号就是发生先后，起因通常在编号靠前的几条，结果通常在编号最靠后的几条。\n{blocks}\n"
    "第二步，在<回答>和</回答>之间对博士说话：按提纲的块顺序，把每块所引记忆里的具体人、动作、原话要点讲出来，"
    "写“无”的块跳过；不要提到块名、提纲和编号。"
)

REPAIR_NOTE = (
    "（校对意见，不是{player}说的话）你刚才的回复逐句编号如下：\n{listing}\n"
    "需要改的句子：\n{notes}\n"
    "只改这些句子，其余句子一字不改，保留句子之间原来的连接。改的时候只用[你的记忆]里有的内容；"
    "记忆里没有的就不要提，也不要为此加上记不清之类的声明。只输出改好的完整回复。"
)

NOTES = {
    "entity": "提到了{detail}，但[你的记忆]里没有",
    "meta": "出戏了，改成你自己会说的话",
    "quote": "引号里的话在记忆里找不到原句；不是原话就不要加引号",
    "number": "数字“{detail}”在[你的记忆]里没有",
    "quantity": "“{detail}”说过头了，[你的记忆]里没有这么说",
    "stale": "把较早的事说成了现在的情况；改成最后知道的情况，说清是在什么时候",
    "denial": "[你的记忆]里有这部分，直接讲出来，不要说不知道或需要时间",
    "order": "先后说反了：[你的记忆]的编号就是发生先后",
    "causal": "“{detail}”把两件事说成了因果，但[你的记忆]里没有标〔因果〕；改成“后来”这样的先后，或说成“在我看来”",
    "closing": "不要用“如果您……我可以……”这类客套话收尾，说完就停",
}

JSON_QUOTE_HINT = "字符串里引用原话时，英文双引号要写成 \\\" 或改用「」"

FACT_SYSTEM_PROMPT = (
    "从给定剧情事件和原文行提出地点、拘押、组织归属、存活状态的候选，每条只写一个主体、谓词、客体。"
    "先分清事实发生时刻与报告时刻：time_scope=event 仅用于这一场景当下确实发生或观察到的状态；"
    "earlier 用于谈到的往事；unclear 用于时间无法锚定。不要把报告当日当成往事发生当日。"
    "再分清 source_mode：observed 是旁白、现场行动或现场可验证状态；reported 是角色声称、报告或传闻。"
    "声称只能当待审阅候选，不能因为有人说过就认定它为真实世界状态。推测、计划、反事实和未实现的将来一律跳过。"
    "引用必须是给定事件下的原样行 ID，片段不完整时不猜测。只输出 JSON："
    '{"facts":[{"subject":"人物名","predicate":"location|custody|affiliation|life_status",'
    '"object":"值","polarity":1,"event_id":"原样事件ID","line_key":"原样证据行ID",'
    '"source_mode":"observed|reported","time_scope":"event|earlier|unclear"}]}。'
    "没有可靠候选时返回空数组。"
)

CHANNEL_DEFS = "\n".join(ln.strip() for ln in SYSTEM_PROMPT.splitlines() if ln.strip().split(" ")[0] in CHANNELS)

JUDGE_SYSTEM = f"""你是剧情记忆抽取结果的审核员。输入是一个游戏剧情场景里被引用到的原文行，以及从这个场景抽取出的事件。逐个事件判断，只依据给出的原文行，不要使用任何外部知识。

对每个事件给出：
- support：只看这个事件自己的 evidence 行，summary 里的每一个说法是否都有依据。full = 全部有依据；partial = 有说法缺少依据或与原文不符；none = 基本没有依据。
- unsupported：缺少依据或与原文不符的说法，每条不超过 30 字；没有就是空数组。
- irrelevant：evidence 里和 summary 无关、删掉也不影响支撑的行号，例如 ["L12"]；没有就是空数组。
- channel_ok：只看 view_evidence 行，目标角色和这个事件的关系是否确实是给出的 channel。true 或 false。
- channel_note：channel_ok 为 false 时写应该是哪个渠道和理由，不超过 30 字；否则为空字符串。

渠道定义：
{CHANNEL_DEFS}

说明：{{DOCTOR}} 指玩家角色博士，"ta" 是指代博士的代词；显示名为"博士（选项）"的行是博士说的话。只有显示名在目标角色已确认名字里的台词才是她说的。

只输出 JSON：{{"events": [{{"id": "e1", "support": "full", "unsupported": [], "irrelevant": [], "channel_ok": true, "channel_note": ""}}]}}"""


PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "canon_probe",
        "description": "只在不确定该回忆哪个人物、地点、组织或篇章时调用。返回问题里点到的范围、你知情的事件数和主要出现的篇章，"
                       "不含原文，消耗很少。范围明确时直接调用 canon_recall。",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "结合上下文改写后的完整问题"}},
            "required": ["query"],
        },
    },
}


def recall_tool(now: str = "") -> dict:
    """The recall tool; when the canon carries a calendar, it states the present so time words have an anchor."""
    description = ("回忆原作里你知道的事。闲聊、日常、此刻的感受和回应不需要调用。"
                   "path：event＝某次具体经过或细节；reason＝某件事的原因或动机；impression＝你对某人某组织的看法；"
                   "arc＝某个人物、地点、组织或篇章的一段经历；latest＝某人你最后知道的情况。")
    if now:
        description += ("timeline＝把某件事放到时间轴上，看它在什么时候、前后接着哪些经历；"
                        f"recent＝到现在为止最近的几段经历，不针对某个人。现在大约是{now}。")
    description += "depth：light＝一两件事就能答（默认，消耗少）；deep＝需要梳理多次事件、前因后果时才用。"
    return {
        "type": "function",
        "function": {
            "name": "canon_recall",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "凝练后可以独立理解的回忆内容，写清人物、地点和要找的事"},
                    "path": {"type": "string", "enum": list(PATHS if now else PATHS[:5])},
                    "subject": {"type": "string", "description": "主要人物、地点或组织的名字，只写一个名字，不要写篇章名或几个词；不确定就留空"},
                    "depth": {"type": "string", "enum": list(DEPTHS)},
                },
                "required": ["query", "path"],
            },
        },
    }


ARCHIVE_TOOL = {
    "type": "function",
    "function": {
        "name": "operator_archive",
        "description": "查阅罗德岛档案：干员的人事档案、NPC 情报、敌人的作战情报。只在回答需要某人的出身、种族、生日、"
                       "履历、体检、病情或作战情报时调用；查到的是档案记载，不是你亲历的事。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "人物或敌人的名字"},
                "section": {"type": "string",
                            "description": "要看的档案段，例如 基础档案、客观履历、临床诊断分析、档案资料一；"
                                           "不填则返回概要和可查的段落"},
            },
            "required": ["name"],
        },
    },
}
