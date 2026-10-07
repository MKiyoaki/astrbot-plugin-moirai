"""Moirai 的稳定公共接口：WebUI 路由、工具和工作区宿主只从这里导入。

memory 的函数直接导出；runtime、canon、retrieval 的名字在第一次访问时才导入对应模块，
这样只用 WebUI 查询函数的调用方不会连带加载整个运行时。
"""
import importlib

from .memory import (
    attach_persona_views,
    delete_event,
    event_to_dict,
    get_event,
    get_stats,
    impression_to_dict,
    list_archived_events,
    list_events,
    persona_to_dict,
    update_event,
)

__all__ = [
    "attach_persona_views",
    "delete_event",
    "event_to_dict",
    "get_event",
    "get_stats",
    "impression_to_dict",
    "list_archived_events",
    "list_events",
    "persona_to_dict",
    "update_event",
]

_LAZY = {
    **dict.fromkeys((
        "BoundaryConfig", "ContextConfig", "ContextManager", "Event", "EventBoundaryDetector",
        "EventExtractor", "EventHandler", "ExtractorConfig", "IdentityResolver", "InjectionConfig",
        "LLMTaskManager", "MessageRouter", "MoiraiCoreProvider", "PluginConfig", "RawMessageWriter",
        "RecallManager", "RetrievalConfig", "SQLiteCommitmentRepository", "SQLiteEventRepository",
        "SQLiteImpressionRepository", "SQLitePersonaGroupRepository", "SQLitePersonaRepository",
        "SQLiteRawMessageRepository", "db_open", "get_plugin_version",
    ), "runtime"),
    **dict.fromkeys((
        "CanonConfig", "CanonGeneration", "CanonPersona", "CanonReader", "CanonSettings", "CanonTurn",
        "CharacterProfile", "CheckReport", "DATASET", "SETTINGS", "load_settings", "parse_persona_map",
        "profile_for",
    ), "canon"),
    **dict.fromkeys((
        "HybridRetriever", "ProviderBridge", "build_retrieval_providers", "development_config",
        "open_shared_encoder",
    ), "retrieval"),
}


def __getattr__(name: str):
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(importlib.import_module(f".{module}", __name__), name)
