"""第三方插件面板注册中心。

允许其他 AstrBot 插件（依赖本插件）在统一 WebUI 中挂载新面板：

    # 在依赖本插件的插件 B 中：
    from astrbot.api.star import Context

    em = context.get_registered_star("astrbot_plugin_enhanced_memory")
    em.webui_registry.register(PanelManifest(
        plugin_id="astrbot_plugin_xxx",
        panel_id="my_panel",
        title="我的面板",
        icon="🔮",
        api_prefix="/api/ext/xxx",
        frontend_url="https://cdn.example.com/my_panel.js",
        permission="auth",
    ))

前端通过 GET /api/panels 拉取所有已注册面板，按 manifest.frontend_url
动态加载脚本（脚本需挂载一个 mount(rootEl, ctx) 全局函数到 window）。
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from aiohttp import web

from .auth import PermLevel

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PanelManifest:
    plugin_id: str
    panel_id: str
    title: str
    icon: str = "📦"
    api_prefix: str = ""
    frontend_url: str = ""
    permission: PermLevel = "auth"
    description: str = ""

    @property
    def key(self) -> str:
        return f"{self.plugin_id}/{self.panel_id}"


# 路由处理器签名：接收 aiohttp 请求，返回响应；可选传入 AuthState 由 server 包装
RouteHandler = Callable[[web.Request], Awaitable[web.StreamResponse]]


@dataclass(slots=True)
class PanelRoute:
    method: str
    path: str
    handler: RouteHandler
    permission: PermLevel = "auth"


class PanelRegistry:
    """单例风格的面板注册表，由 WebuiServer 持有，对外暴露给其他插件。"""

    def __init__(self) -> None:
        self._panels: dict[str, PanelManifest] = {}
        self._routes: dict[str, list[PanelRoute]] = {}
        self._on_change: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # 面板生命周期
    # ------------------------------------------------------------------

    def register(self, manifest: PanelManifest, routes: list[PanelRoute] | None = None) -> None:
        if manifest.key in self._panels:
            logger.warning("[Panels] %s already registered, overwriting", manifest.key)
        self._panels[manifest.key] = manifest
        if routes:
            self._routes[manifest.key] = list(routes)
        logger.info("[Panels] registered %s (%s)", manifest.key, manifest.title)
        self._notify()

    def unregister(self, plugin_id: str, panel_id: str) -> None:
        key = f"{plugin_id}/{panel_id}"
        self._panels.pop(key, None)
        self._routes.pop(key, None)
        logger.info("[Panels] unregistered %s", key)
        self._notify()

    def list(self) -> list[dict[str, Any]]:
        return [asdict(m) for m in self._panels.values()]

    def all_routes(self) -> list[PanelRoute]:
        out: list[PanelRoute] = []
        for routes in self._routes.values():
            out.extend(routes)
        return out

    # ------------------------------------------------------------------
    # 变更监听（内部使用，前端轮询 /api/panels 已经够用，监听是可选优化）
    # ------------------------------------------------------------------

    def on_change(self, callback: Callable[[], None]) -> None:
        self._on_change.append(callback)

    def _notify(self) -> None:
        for cb in self._on_change:
            try:
                cb()
            except Exception:
                logger.exception("[Panels] on_change callback failed")
