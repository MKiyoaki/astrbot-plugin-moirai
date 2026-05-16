"""Tests for napcat/OneBot message normalization at the adapter boundary."""
from __future__ import annotations

import pytest

from core.adapters.message_normalizer import normalize_message_text, normalize_display_name


@pytest.mark.parametrize("raw, expected", [
    ("[CQ:at,qq=123] 你好", "@用户 你好"),
    ("[CQ:reply,id=42][CQ:at,qq=1] 收到", "@用户 收到"),
    ("@卢比鹏(1783088492) 在吗", "@卢比鹏 在吗"),
    ("[CQ:image,file=xx.jpg]", "[图片]"),
    ("[CQ:face,id=0]", "[表情]"),
    ("[CQ:mface,id=12]", "[表情]"),
    ("[CQ:record,file=a.amr]", "[语音]"),
    ("[CQ:video,file=b.mp4]", "[视频]"),
    ("[CQ:json,data={...}]", "[卡片]"),
    ("[CQ:at,qq=1]", "@用户"),
    ("普通消息没有 CQ", "普通消息没有 CQ"),
    ("", ""),
    ("[CQ:unknown_type,foo=bar]", ""),
    ("@A(11111) 和 @B(22222) 一起吃饭", "@A 和 @B 一起吃饭"),
])
def test_normalize_message_text(raw, expected):
    assert normalize_message_text(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("卢比鹏(1783088492)", "卢比鹏"),
    ("Alice", "Alice"),
    ("", ""),
    ("无后缀昵称", "无后缀昵称"),
    ("名字(12345)", "名字"),
    ("名字(1234)", "名字(1234)"),  # 短于 5 位的数字不剥离 (谨慎)
])
def test_normalize_display_name(raw, expected):
    assert normalize_display_name(raw) == expected


def test_normalize_preserves_meaning():
    """Strip QQ id but keep @nickname semantics for tag/summary extraction."""
    raw = "@卢比鹏(1783088492) 你看这个文档"
    out = normalize_message_text(raw)
    assert "1783088492" not in out
    assert "@卢比鹏" in out
    assert "你看这个文档" in out


def test_pure_at_collapses_via_first_meaningful_text_path():
    """A pure CQ:at message normalizes to '@用户' (non-empty), so first_text logic still works."""
    raw = "[CQ:at,qq=12345]"
    out = normalize_message_text(raw)
    assert out == "@用户"
    assert out  # non-empty — won't trigger "（无内容）"
