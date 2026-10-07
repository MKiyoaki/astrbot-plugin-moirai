"""插件目录布局：AstrBot 需要的文件在插件根目录，Python 包都在 src/ 下。"""
from __future__ import annotations

from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = SRC_ROOT.parent
