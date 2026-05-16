"""Normalize platform-specific message artifacts before they enter the memory pipeline.

Adapters call these helpers at the protocol boundary so that downstream
components (window, extractor, prompts, vector index) operate on clean
human-readable text — free of CQ codes and QQ-number residue from napcat's
display-name rendering.
"""
from __future__ import annotations

import re

_CQ_AT_RE = re.compile(r"\[CQ:at,[^\]]*\]")
_CQ_REPLY_RE = re.compile(r"\[CQ:reply,[^\]]*\]")
_CQ_IMAGE_RE = re.compile(r"\[CQ:image,[^\]]*\]")
_CQ_FACE_RE = re.compile(r"\[CQ:m?face,[^\]]*\]")
_CQ_RECORD_RE = re.compile(r"\[CQ:record,[^\]]*\]")
_CQ_VIDEO_RE = re.compile(r"\[CQ:video,[^\]]*\]")
_CQ_CARD_RE = re.compile(r"\[CQ:(?:json|xml|rich),[^\]]*\]")
_CQ_GENERIC_RE = re.compile(r"\[CQ:[^\]]*\]")
_NAPCAT_NAME_SUFFIX_RE = re.compile(r"\((\d{5,})\)")
_MULTI_WS_RE = re.compile(r"\s+")


def normalize_message_text(raw: str) -> str:
    """Strip CQ codes and napcat display-name residue from a message body.

    Empty inputs pass through as empty strings so upstream fallback logic
    (e.g. parser._first_meaningful_text) can decide how to handle them.
    """
    if not raw:
        return ""

    text = _CQ_AT_RE.sub("@用户", raw)
    text = _CQ_REPLY_RE.sub("", text)
    text = _CQ_IMAGE_RE.sub("[图片]", text)
    text = _CQ_FACE_RE.sub("[表情]", text)
    text = _CQ_RECORD_RE.sub("[语音]", text)
    text = _CQ_VIDEO_RE.sub("[视频]", text)
    text = _CQ_CARD_RE.sub("[卡片]", text)
    text = _CQ_GENERIC_RE.sub("", text)
    text = _NAPCAT_NAME_SUFFIX_RE.sub("", text)
    text = _MULTI_WS_RE.sub(" ", text).strip()
    return text


def normalize_display_name(raw: str) -> str:
    """Remove napcat's trailing (QQ number) suffix from a sender display name."""
    if not raw:
        return ""
    return _NAPCAT_NAME_SUFFIX_RE.sub("", raw).strip()
