"""The target character's canon identity: her name, how the player is addressed, whose reports reach her,
and the story events she tells time by.

Runtime modules read these values from the profile rather than spelling out a character, so one
character's conventions live in one place and can be switched per persona.
"""
from __future__ import annotations

from dataclasses import dataclass

from .anchors import Anchor, Stages


@dataclass(frozen=True)
class CharacterProfile:
    character: str
    name: str
    player: str
    player_placeholder: str
    player_token: str
    home: str
    world: str
    report_recipients: tuple[tuple[str, str], ...]
    home_status_terms: tuple[str, ...]
    game_pattern: str
    report_knowledge: bool = True
    anchors: tuple[Anchor, ...] = ()

    @property
    def self_names(self) -> frozenset[str]:
        return frozenset((self.name, self.player))

    def report_sql(self) -> str:
        """SQL condition on view_access rows for reports that reach her (the reported channel)."""
        by_kind: dict[str, list[str]] = {}
        for kind, recipient in self.report_recipients:
            by_kind.setdefault(kind, []).append(recipient)
        clauses = [f"kind='{kind}' AND recipient='{names[0]}'" if len(names) == 1 else
                   f"kind='{kind}' AND recipient IN ({','.join(repr(n) for n in names)})"
                   for kind, names in by_kind.items()]
        return " OR ".join(clauses)


_BABEL = "巴别塔"
ANCHORS = (
    Anchor("卡兹戴尔内战", "卡兹戴尔内战", (10911201, 10941231), (Stages(collection=_BABEL),)),
    Anchor("博士救阿米娅", "博士救下阿米娅", (10900101, 10910831), (Stages("BB-4@行动前", "BB-4@行动前", _BABEL),),
           parent="卡兹戴尔内战", during="前后"),
    Anchor("阿米娅加入巴别塔", "阿米娅加入巴别塔", (10910901, 10911130),
           (Stages("BB-4@行动后", "BB-4@行动后", _BABEL),), parent="卡兹戴尔内战", during="时"),
    Anchor("特蕾西娅遇刺", "特蕾西娅遇刺与巴别塔瓦解", (10940601, 10940831),
           (Stages(collection=_BABEL, only=("BB-ST-1",)), Stages("BB-9@行动前", "$", _BABEL)),
           parent="卡兹戴尔内战", during="时"),
    Anchor("切城—龙门事件", "切尔诺伯格—龙门危机", (10961223, 10970122),
           (Stages("^", "END8-1", chapters=(0, 8), skip=("R8-", "EG-")),)),
    Anchor("切城救援", "切尔诺伯格救援行动", (10961223, 10961223), (Stages(chapters=(0, 1)),),
           parent="切城—龙门事件"),
    Anchor("米莎事件", "米莎争夺事件", (10961227, 10961229), (Stages(chapters=(2, 3)),), parent="切城—龙门事件"),
    Anchor("霜星阵亡", "霜星阵亡", (10970105, 10970105), (Stages("6-16", "6-17", chapters=(6, 6)),),
           parent="切城—龙门事件", during="时"),
    Anchor("切城核心城之战", "切尔诺伯格核心城阻截战", (10970105, 10970106),
           (Stages("^", "JT8-3@行动后", chapters=(7, 8), skip=("R8-", "EG-")),), parent="切城—龙门事件"),
    Anchor("小丘郡事件", "小丘郡事件", (10970901, 10971130), (Stages("^", "9-20", chapters=(9, 9)),)),
    Anchor("塔露拉被劫走", "整合运动劫走塔露拉", (10980101, 10980630), (Stages("9-21", "$", chapters=(9, 9)),),
           during="时"),
    Anchor("伦蒂尼姆大战", "伦蒂尼姆战争", (10980701, 10981008),
           (Stages(chapters=(10, 14), skip=("11-1", "11-2", "11-3", "EG-6")),
            Stages(collection="追迹日落以西", only=("GO-8", "GO-9")), Stages("15-1", "15-2", chapters=(15, 15)))),
    Anchor("温德米尔公爵遇刺", "温德米尔公爵遇刺", (10980701, 10980930),
           (Stages(chapters=(13, 13), only=("13-3",)),), parent="伦蒂尼姆大战", during="时"),
    Anchor("布伦特伍德之战", "布伦特伍德之战", (10980701, 10980930), (Stages("13-11", "13-21", chapters=(13, 13)),),
           parent="伦蒂尼姆大战"),
    Anchor("飞空艇之战", "飞空艇决战", (10980901, 10980930), (Stages("14-14", "14-22", chapters=(14, 14)),),
           parent="伦蒂尼姆大战"),
    Anchor("伦蒂尼姆收尾", "伦蒂尼姆战争结束", (10981002, 10981008),
           (Stages(collection="追迹日落以西", only=("GO-8", "GO-9")), Stages("15-1", "15-2", chapters=(15, 15))),
           parent="伦蒂尼姆大战", during="时"),
    Anchor("罗德岛本舰事故", "罗德岛本舰危机", (11010601, 11010731),
           (Stages("15-3", "$", chapters=(15, 15), skip=("15-16",)),)),
    Anchor("远北矿区事件", "乌萨斯远北矿区危机", (11010901, 11011130), (Stages("^", "16-19", chapters=(16, 16)),)),
    Anchor("泽尔格勒事件", "泽尔格勒危机", (11020120, 11020123), (Stages("17-4", "17-21", chapters=(17, 17)),)),
    Anchor("凯尔希复活", "凯尔希复生", (11020122, 11020123),
           (Stages("17-17@行动后", "17-18@行动后", chapters=(17, 17)),), parent="泽尔格勒事件", during="时"),
    Anchor("罗德岛冲过天灾", "罗德岛天灾区突围", (10970201, 10970430),
           (Stages(collection="如我所见", only=("我不会全部遗忘",)),), during="时"),
    Anchor("汐斯塔黑曜石节", "汐斯塔黑曜石节危机", (10970601, 10970831), (Stages(collection="火蓝之心"),)),
    Anchor("卡西米尔特锦赛", "第二十四届特锦赛与大骑士领风波", (10971024, 10971130), (Stages(collection="长夜临光"),)),
    Anchor("阿米娅返乡", "雷姆必拓返乡之行", (10970123, 10980630), (Stages(collection="去咧嘴谷"),), places=False),
)

AMIYA = CharacterProfile(
    character="amiya",
    name="阿米娅",
    player="博士",
    player_placeholder="{DOCTOR}",
    player_token="@doctor",
    home="罗德岛",
    world="明日方舟",
    report_recipients=(("direct_report", "阿米娅"), ("command_report", "{DOCTOR}"), ("command_report", "凯尔希")),
    home_status_terms=("在岛上", "在舰上"),
    game_pattern=(r"[二三四五六2-6]星(?:干员|角色|先锋|近卫|重装|狙击|术师|医疗|辅助|特种|(?![一-鿿A-Za-z]))"
                  r"|几星|星级|技能专精|专精[一二三1-3]|精英化|抽卡|卡池|第[一二三四五六七八九十百零〇0-9]+章"),
    anchors=ANCHORS,
)
PROFILES = {AMIYA.character: AMIYA}


def profile_for(character: str) -> CharacterProfile:
    try:
        return PROFILES[character]
    except KeyError:
        raise ValueError(f"没有角色 {character!r} 的 canon 配置；已有：{', '.join(sorted(PROFILES))}") from None
