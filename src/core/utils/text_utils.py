"""汉字文本的基础判断：取汉字连续段、判断一段文字是否全是汉字；canon 的词法索引、证据打包和库表共用。"""
from __future__ import annotations

import re

_CJK = re.compile(r"[一-鿿]+")


def cjk_runs(text: str | None) -> list[str]:
    return _CJK.findall(text or "")


def is_cjk(text: str | None) -> bool:
    return bool(text) and _CJK.fullmatch(text) is not None
