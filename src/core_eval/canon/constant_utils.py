"""canon 评测脚本共用的字符串常量：探针类别、判定标签与提示记号。"""
from __future__ import annotations


KINDS = ("cover", "absent", "no_episode", "not_evidence", "not_mention")
PASS = "通过"
COVERED = (PASS, "渠道错误", "被合并")
UNCITED = "范围内未引用"
SUPPORT = ("none", "partial", "full")
NARRATION_KINDS = ("narration", "subtitle", "caption")
DENSITY_BINS = ((0, 0, "0"), (1, 10, "1–10"), (11, 40, "11–40"), (41, 10**9, "41+"))
RETRY_MARK = "\n\n[上次输出的问题]"
