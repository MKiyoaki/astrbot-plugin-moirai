"""canon 共用的字符串常量：词表、标签和格式记号。会改变结果的数字在 configs/canon/，只属于某个数据集的内容在 configs/data/。"""
from __future__ import annotations

# ── 回复核验（turn/gateway.py） ──────────────────
META_TERMS = ("原作", "剧情", "章节", "数据库", "知识库", "检索", "试跑", "语言模型", "人工智能")

MEMORY_CHANNEL = {
    "experienced": "你亲历",
    "witnessed": "你在场看到",
    "told": "你听人说起",
    "recalled": "你回忆往事",
    "reported": "你经汇报得知，只知道汇报的内容",
    "unstated": "你是否知道此事不明",
}

FORWARD = ("再往后", "再后来", "紧接着", "后来", "随后", "之后", "接着", "然后", "不久", "最后")
BACKWARD = ("在那之前", "在那以前", "那之前", "早在", "此前", "先前", "之前")
CAUSAL = ("正因为这样", "正因如此", "所以", "因此", "于是", "因而", "这才")
JUDGMENT = ("在我看来", "我觉得", "我想", "我猜", "也许", "或许", "大概", "想来", "说不定")

DENIAL = ("记不清", "记不太清", "不记得", "想不起", "没印象", "没收到", "不清楚", "说不准", "不确定",
          "需要一点时间", "需要些时间", "无法直接", "没办法给", "不够全面", "不够完整")

QUANTITY = ("所有人", "所有的", "全部", "全都", "大家都", "一个都", "无一", "唯一")
NOW_WORDS = ("现在", "目前", "如今", "至今", "最近")
PAST_FRAME = ("当时", "那时")
REPORTING = ("说", "提到", "告诉", "表示", "称")
LISTENER = "您"
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
REPLY_GENERIC_CHARS = frozenset("我你您他她它们的了是在和与就也都还又把被让给这那个一有没不很吗呢吧啊呀说着过")
CLOSING_OPEN = tuple(lead + you for lead in ("如果", "要是", "假如", "倘若") for you in ("您", "你"))
CLOSING_OFFER = ("我可以", "我会", "我能", "我再", "随时", "尽力")
DIGITS = "0123456789"
NUMERALS = "二两三四五六七八九十百千万"
UNITS = "个名人支座条件次天年月日周岁分秒小时里米吨份层艘辆架"
SENTENCE_ENDS = "。！？"
CJK_DIGIT_VALUES = dict(zip("零一二两三四五六七八九", (0, 1, 2, 2, 3, 4, 5, 6, 7, 8, 9)))

# ── 问句规划（read/query.py） ──────────────────────
GENERIC_CHARS = frozenset(
    "还记得是什么怎么样了吗呢吧啊呀的地得在有没这那你我他她它们个些时候事情知道觉得想要会能可以说过去上次当时一下"
)

QUERY_PAST = ("那次", "那一次", "上次", "当时", "那时", "那天", "那场", "还记得")
PERSON_REFERENCES = ("她", "他", "那个人")
OTHER_REFERENCES = ("它", "那里", "那座城", "那个地方")
EVENT_REFERENCES = ("那件事", "那次", "那一回")
REASON_MARKERS = ("为什么", "为何", "原因", "缘由", "动机", "目的")
IMPRESSION_MARKERS = ("印象", "看法", "怎么看", "感觉如何")

STATUS_TERMS = (
    "今天", "今晚", "现在", "目前", "最近", "近况", "还在", "还好吗",
    "如今", "怎么样了", "在哪",
)

LOOKUP = ("档案", "资料", "履历", "生日", "身高", "种族", "体检", "病历", "病情", "感染情况", "出身", "作战情报")
RECOUNT = ("经过", "复述", "怎么回事", "之战", "之役", "那一战", "讲讲", "说说", "讲一下", "讲一遍", "详细")

# ── 只读访问（read/reader.py） ────────────────────
LEXICAL_NOISE = ("还记得", "那一次", "那时候", "那次", "那天", "那时", "那场", "当时", "上次", "后来",
                 "为什么", "是什么", "是谁", "什么", "怎么", "知道", "是不是")

SINGLE_LEFT = frozenset("和跟与被让叫问找给对向同帮见把替等陪救及或是说像连带请看喊")
SINGLE_RIGHT = frozenset("第被和跟与的是在说也都就还又为把让给对向从同去来呢吗吧啊呀了着过当之他她那这会能要有没不怎以讲问叫救帮打做看找见一")

# ── 证据打包（read/packing.py） ──────────────────
CHANNEL_LABEL = {
    "experienced": "亲历",
    "witnessed": "在场目睹",
    "told": "听人讲述",
    "recalled": "回忆",
    "reported": "经汇报得知",
    "unstated": "文本未表明是否知情",
}

RATIONALE_CUES = ("动机", "来意", "理想", "原因", "因为", "为了", "目的是", "阻止", "避免", "而战")

# ── 抽取结果的取值（build/extract.py） ──────────
IN_WORLD_TIME = ("present", "past", "unknown")
CHANNELS = ("experienced", "witnessed", "told", "recalled", "unstated")
ACCESS_KINDS = ("direct_report", "command_report", "record_available", "role_candidate")
EDGE_TYPES = ("cause", "motivation", "emotion_source", "cognition_update")
ENTITY_TYPES = ("person", "place", "faction", "object", "concept")
DOCTOR = "{DOCTOR}"

# ── 场景文本的行类型 ────────────────────────────────────────────
SPEAKING_KINDS = ("dialogue", "inner_voice")
CUT_KINDS = ("narration", "title", "header")

# ── 回忆工具（turn/recall.py） ────────────────────
PATHS = ("event", "reason", "impression", "arc", "latest", "timeline", "recent")
DEPTHS = ("light", "deep")
AXIS_MARK = {"reported": "（汇报）", "told": "（听说）"}

# ── 档案查询（turn/canon_turn.py） ────────────
ARCHIVE_KIND = {"operator": "干员档案", "npc": "情报资料", "enemy": "作战情报"}
ARCHIVE_DEFAULT = ("基础档案", "客观履历", "情报资料一", "作战情报")

# ── 世界历法（domain/calendar.py） ────────────
PARTS = {"初": 1, "新春": 1, "春": 4, "夏": 7, "秋": 10, "冬": 12, "末": 12, "底": 12}
PHASES = {"BEG": "行动前", "END": "行动后"}
CAPTION_KINDS = ("caption", "narration")

# ── 时间事实 ────────────────────────────────────────────────────
PREDICATES = frozenset(("location", "custody", "affiliation", "life_status"))

# ── 人格映射（config.py） ──────────────────────────────
DOCTOR_MODES = ("off", "all", "bound")

# ── 时间锚点（domain/anchors.py） ──────────────
CJK_DIGITS = "零一二三四五六七八九"

POLARITY_TEXT = {"1": 1, "0": 0, "-1": 0, "true": 1, "false": 0, "yes": 1, "no": 0,
                 "positive": 1, "negative": 0, "肯定": 1, "否定": 0, "是": 1, "否": 0}
