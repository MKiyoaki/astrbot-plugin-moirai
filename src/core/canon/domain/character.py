"""The target character's canon identity: her name, how the player is addressed, whose reports reach her,
and the story events she tells time by.

The values come from the dataset configuration (configs/data/), so runtime modules never spell out a
character and one character's conventions live in one place that can be switched per persona.
"""
from __future__ import annotations

from dataclasses import dataclass

from .anchors import Anchor, Stages
from ..settings import DATASET


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


def _stages(raw: dict) -> Stages:
    return Stages(**{key: tuple(value) if isinstance(value, list) else value for key, value in raw.items()})


def _anchor(raw: dict) -> Anchor:
    return Anchor(name=raw["name"], event=raw["event"], span=tuple(raw["span"]),
                  stages=tuple(_stages(item) for item in raw["stages"]),
                  **{key: raw[key] for key in ("parent", "during", "places") if key in raw})


def _profile(character: str, raw: dict) -> CharacterProfile:
    return CharacterProfile(
        character=character,
        name=raw["name"],
        player=raw["player"],
        player_placeholder=raw["player_placeholder"],
        player_token=raw["player_token"],
        home=raw["home"],
        world=raw["world"],
        report_recipients=tuple(tuple(pair) for pair in raw["report_recipients"]),
        home_status_terms=tuple(raw["home_status_terms"]),
        game_pattern=raw["game_pattern"],
        report_knowledge=raw.get("report_knowledge", True),
        anchors=tuple(_anchor(item) for item in raw.get("anchors", ())),
    )


PROFILES = {name: _profile(name, raw) for name, raw in DATASET["characters"].items()}
DEFAULT_PROFILE = PROFILES[DATASET["default_character"]]


def profile_for(character: str) -> CharacterProfile:
    try:
        return PROFILES[character]
    except KeyError:
        raise ValueError(f"没有角色 {character!r} 的 canon 配置；已有：{', '.join(sorted(PROFILES))}") from None
