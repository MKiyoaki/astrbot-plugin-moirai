"""宿主组装 Moirai 时用到的运行时类：AstrBot 适配、Core 提供者、事件处理、管理器、仓库与配置。"""
from __future__ import annotations

from ..adapters.astrbot import MessageRouter
from ..adapters.core_events import MoiraiCoreProvider
from ..adapters.identity import IdentityResolver
from ..boundary.detector import BoundaryConfig, EventBoundaryDetector
from ..config import ContextConfig, ExtractorConfig, InjectionConfig, PluginConfig, RetrievalConfig
from ..domain.models import Event
from ..event_handler import EventHandler
from ..extractor.extractor import EventExtractor
from ..managers.context_manager import ContextManager
from ..managers.llm_manager import LLMTaskManager
from ..managers.raw_message_writer import RawMessageWriter
from ..managers.recall_manager import RecallManager
from ..repository.commitments import SQLiteCommitmentRepository
from ..repository.sqlite import (
    SQLiteEventRepository,
    SQLiteImpressionRepository,
    SQLitePersonaGroupRepository,
    SQLitePersonaRepository,
    SQLiteRawMessageRepository,
    db_open,
)
from ..utils.version import get_plugin_version
