"""The target character's canon identity: her name, how the player is addressed, and whose reports reach her.

Runtime modules read these values from the profile rather than spelling out a character, so one
character's conventions live in one place and can be switched per persona.
"""
from __future__ import annotations

from dataclasses import dataclass


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
)
PROFILES = {AMIYA.character: AMIYA}


def profile_for(character: str) -> CharacterProfile:
    try:
        return PROFILES[character]
    except KeyError:
        raise ValueError(f"没有角色 {character!r} 的 canon 配置；已有：{', '.join(sorted(PROFILES))}") from None
