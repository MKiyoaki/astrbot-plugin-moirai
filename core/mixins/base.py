from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Set

if TYPE_CHECKING:
    from abc import ABC
    from astrbot.api import Context
    # TODO ... import from

class BaseMixin(ABC):
    """
    Abstract base class of all mixins, which provides 
    """