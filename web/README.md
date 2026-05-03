# WebUI — 三轴记忆可视化面板

Enhanced Memory 插件内置的轻量级 Web 界面，基于 **aiohttp** 提供 HTTP 服务，通过三个独立面板呈现三轴记忆模型的运行状态。

## 目录结构

```
web/
├── server.py          # aiohttp 服务器 + JSON API 实现
├── static/
│   └── index.html     # 单页前端（纯 HTML/CSS/JS，CDN 依赖）
└── README.md          # 本文件
```

## 访问方式

插件启动后，WebUI 默认在本机端口 **2653** 提供服务：

```
http://localhost:2653/
```

端口可通过插件配置项 `webui_port` 修改，WebUI 也可通过 `webui_enabled: false` 整体关闭。

## 三轴面板说明

### ① 事件流（Event Flow）

- 渲染库：[vis-timeline 7.7.3](https://visjs.github.io/vis-timeline/)
- 数据源：`GET /api/events?group_id=<gid>&limit=<n>`
- 每个条目对应一个 `Event` 实体，颜色深浅反映 `salience`（重要度）
- 点击关系图中的印象边 → 高亮该印象关联的所有事件

### ② 关系图（Relation Graph）

- 渲染库：[Cytoscape.js 3.29.2](https://cytoscape.org/)
- 数据源：`GET /api/graph`
- 节点 = `Persona`，边 = `Impression`（有向）
- 边宽度 → `intensity`；边颜色 → `affect`（绿色=正面，红色=负面）
- 机器人节点以粉色高亮区分；点击边 → 关联事件高亮跳转至事件流面板

### ③ 摘要记忆（Summarised Memory）

- 渲染库：[marked.js 9.1.6](https://marked.js.org/)
- 数据源：`GET /api/summaries` → `GET /api/summary?group_id=<gid>&date=<YYYY-MM-DD>`
- 读取 `data_dir/groups/<gid>/summaries/*.md` 和 `data_dir/global/summaries/*.md`
- 左侧列表按群组 + 日期排序，点击条目即时渲染 Markdown 正文

## JSON API 参考

| 方法 | 路径 | 参数 | 返回 |
|------|------|------|------|
| GET | `/` | — | HTML 单页应用 |
| GET | `/api/events` | `group_id` (可选), `limit` (默认 100) | `{"items": [EventDict, ...]}` |
| GET | `/api/graph` | — | `{"nodes": [...], "edges": [...]}` |
| GET | `/api/summaries` | — | `[{group_id, date, label}, ...]` |
| GET | `/api/summary` | `group_id` (可选), `date` (必填, YYYY-MM-DD) | `{"content": "<markdown>"}` |

错误码：`400 Bad Request`（缺少 `date` 参数）、`404 Not Found`（文件不存在）。

### EventDict 结构

```json
{
  "id": "evt_abc123",
  "content": "讨论 Python 异步编程",
  "start": "2024-01-15T10:00:00+00:00",
  "end":   "2024-01-15T10:45:00+00:00",
  "group": "group_42",
  "salience": 0.72,
  "tags": ["技术", "Python"],
  "inherit_from": ["evt_prev"],
  "participants": ["uid_alice", "uid_bob"]
}
```

### Graph Node/Edge 结构

```json
// Node (Cytoscape 格式)
{ "data": { "id": "uid_alice", "label": "Alice", "confidence": 0.9, "attrs": {} } }

// Edge (Cytoscape 格式)
{
  "data": {
    "id": "uid_alice--uid_bob--global",
    "source": "uid_alice",
    "target": "uid_bob",
    "label": "friend",
    "affect": 0.65,
    "intensity": 0.8,
    "confidence": 0.75,
    "scope": "global",
    "evidence_event_ids": ["evt_abc123"]
  }
}
```

## 代码结构

`WebuiServer` 的数据构建方法（`events_data`、`graph_data`、`summaries_data`、`summary_content`）与 HTTP 路由处理器解耦：数据方法是纯异步函数，不依赖 HTTP 上下文，可在测试中直接调用；路由处理器只负责解析请求参数和序列化响应。

```python
# 在 main.py 中启动
from web.server import WebuiServer

webui = WebuiServer(
    persona_repo=persona_repo,
    event_repo=event_repo,
    impression_repo=impression_repo,
    data_dir=data_dir,
    port=2653,           # 对应配置项 webui_port
)
await webui.start()
# ...
await webui.stop()
```

## 测试

WebUI 测试位于 `tests/test_webui.py`，覆盖：

- 序列化辅助函数（`event_to_dict`、`persona_to_node`、`impression_to_edge`）
- 数据构建方法（不启动 HTTP 服务器，直接调用异步方法）
- HTTP API（通过 `aiohttp.test_utils.TestClient` + `TestServer`）

```bash
pytest tests/test_webui.py -v
```

## 扩展指南

### 新增 API 端点

在 `server.py` 的 `_build_app()` 中注册路由，并实现对应的数据方法和路由处理器：

```python
def _build_app(self) -> web.Application:
    app = web.Application()
    # ... 现有路由 ...
    app.router.add_get("/api/personas", self._handle_personas)  # 新增
    return app

async def personas_data(self) -> list[dict]:
    personas = await self._persona_repo.list_all()
    return [persona_to_node(p) for p in personas]

async def _handle_personas(self, _: web.Request) -> web.Response:
    return _json(await self.personas_data())
```

### 修改前端面板

前端代码完整包含在 `static/index.html` 中，使用 CDN 加载的 vis-timeline、Cytoscape.js 和 marked.js，无需构建步骤。面板间通过 `highlightEvents(eventIds)` 函数实现跨面板联动。

如需引入构建流程（如 Vue/React），建议：
1. 在 `web/` 下新建 `frontend/` 子目录存放源码
2. 构建产物输出到 `web/static/`
3. `server.py` 保持不变，仍从 `web/static/` 提供静态文件

### 静态文件目录

`_STATIC_DIR = Path(__file__).parent / "static"` 指向 `web/static/`。如需提供多个静态文件（CSS、JS 模块等），可在 `_build_app()` 中改为 `add_static`:

```python
app.router.add_static("/static", _STATIC_DIR)
```
