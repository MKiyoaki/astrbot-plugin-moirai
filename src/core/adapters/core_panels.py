"""Core Panel Protocol v1 页面桥：把 Moirai WebUI 的页面声明为 Core 面板，并把面板的读写请求
转给宿主委托认证的 WebUI 路由处理函数（与 AstrBot 的 PluginRoutes 同一套）。

登录、改密码、sudo 与管理任务路由不经过这座桥；Core 负责身份与权限。Core 作用域映射到某个人格
桶时，`persona` 参数以该桶为准，浏览器传来的值被覆盖。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable
from urllib.parse import unquote

logger = logging.getLogger(__name__)

READ_OPERATION = "moirai.webui.read"
WRITE_OPERATION = "moirai.webui.write"

# ---------------------------------------------------------------------------
# 面板声明
# ---------------------------------------------------------------------------

PAGES: tuple[tuple[str, str, str, int], ...] = (
    ("moirai.events", "Events", "resources", 10),
    ("moirai.graph", "Relationship graph", "graph", 20),
    ("moirai.summaries", "Summaries", "memory", 30),
    ("moirai.recall", "Recall", "memory", 40),
    ("moirai.stats", "Statistics", "evaluation", 50),
    ("moirai.library", "Library", "resources", 60),
    ("moirai.bindings", "Account bindings", "persona", 70),
    ("moirai.config", "Plugin config", "settings", 90),
)

_BLOCKED_PREFIXES = ("/api/admin/", "/api/auth/")
_BLOCKED_PATHS = frozenset({"/api/panels"})
_METHODS = {READ_OPERATION: frozenset({"GET"}), WRITE_OPERATION: frozenset({"POST", "PUT", "DELETE"})}
_SEGMENT = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_PAYLOAD_KEYS = frozenset({"method", "path", "query", "body"})


class PageRequestError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code, self.message = code, message


class _PageRequest:
    """处理函数只通过 args / view_args / get_json 读取请求，这里给出这三项。"""

    def __init__(self, query: dict[str, str], match: dict[str, str], body: Any) -> None:
        self.args, self.view_args, self._body = query, match, body

    async def get_json(self) -> Any:
        return self._body


def _pattern(path: str) -> re.Pattern[str]:
    parts, last = [], 0
    for match in _SEGMENT.finditer(path):
        parts.append(re.escape(path[last:match.start()]))
        parts.append(f"(?P<{match.group(1)}>[^/]+)")
        last = match.end()
    parts.append(re.escape(path[last:]))
    return re.compile("^" + "".join(parts) + "$")


class CorePageBridge:
    """``routes`` 返回带 ``route_table()`` 的对象（PluginRoutes）；尚未初始化时返回 None。"""

    def __init__(self, routes: Callable[[], Any]) -> None:
        self._routes = routes
        self._compiled: tuple[Any, list[tuple[re.Pattern[str], Any, frozenset[str]]]] | None = None

    @staticmethod
    def capabilities() -> list[dict]:
        return [{"operation": READ_OPERATION, "kind": "query", "required_scopes": []},
                {"operation": WRITE_OPERATION, "kind": "command", "required_scopes": []}]

    @staticmethod
    def panel_items() -> list[dict]:
        return [{"panel_id": panel_id, "label": label, "view": "custom", "icon": icon, "order": order,
                 "query_operation": READ_OPERATION, "command_operation": WRITE_OPERATION,
                 "required_permissions": []} for panel_id, label, icon, order in PAGES]

    def _table(self) -> list[tuple[re.Pattern[str], Any, frozenset[str]]] | None:
        routes = self._routes()
        if routes is None:
            return None
        if self._compiled is None or self._compiled[0] is not routes:
            table = [(_pattern(path), handler, frozenset(methods))
                     for path, handler, methods, _ in routes.route_table()
                     if path not in _BLOCKED_PATHS and not path.startswith(_BLOCKED_PREFIXES)]
            self._compiled = (routes, table)
        return self._compiled[1]

    async def dispatch(self, operation: str, payload: Any, bucket: str | None) -> dict:
        if operation not in _METHODS:
            raise PageRequestError("capability_unsupported", "不支持的页面操作。")
        if (not isinstance(payload, dict) or not {"method", "path"} <= payload.keys()
                or payload.keys() - _PAYLOAD_KEYS):
            raise PageRequestError("payload_invalid", "页面请求字段无效。")
        method, path = payload["method"], payload["path"]
        if not isinstance(method, str) or method not in _METHODS[operation]:
            raise PageRequestError("payload_invalid", "这个页面操作不接受该请求方法。")
        if not isinstance(path, str) or not path.startswith("/api/"):
            raise PageRequestError("payload_invalid", "页面请求路径无效。")
        query = payload.get("query") or {}
        if not isinstance(query, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                              for k, v in query.items()):
            raise PageRequestError("payload_invalid", "页面查询参数必须是字符串。")
        body = payload.get("body")
        if method == "GET" and body is not None:
            raise PageRequestError("payload_invalid", "读取请求不带请求体。")
        table = self._table()
        if table is None:
            raise PageRequestError("extension_unavailable", "Moirai WebUI 路由尚未就绪。")
        for pattern, handler, methods in table:
            found = pattern.match(path)
            if found and method in methods:
                break
        else:
            raise PageRequestError("payload_invalid", "没有这个页面接口。")
        if bucket is not None:
            query = {**query, "persona": bucket}
            if isinstance(body, dict) and "persona" in body:
                body = {**body, "persona": bucket}
        match = {key: unquote(value) for key, value in found.groupdict().items()}
        try:
            response = await handler(_PageRequest(dict(query), match, body))
            status = int(getattr(response, "status_code", getattr(response, "status", 200)))
            if hasattr(response, "get_data"):
                text = await response.get_data(as_text=True)
            else:
                text = getattr(response, "text", "") or ""
        except PageRequestError:
            raise
        except Exception:
            logger.exception("[CorePageBridge] %s %s failed", method, path)
            raise PageRequestError("extension_failure", "页面请求失败。") from None
        try:
            data: Any = json.loads(text) if text else None
        except ValueError:
            data = text
        return {"status": status, "body": data}
