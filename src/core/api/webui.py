"""宿主（如 Core 页面桥）复用的 WebUI 路由处理类；只在第一次访问时导入。"""
from __future__ import annotations

from web.plugin_routes import PluginRoutes

__all__ = ["PluginRoutes"]
