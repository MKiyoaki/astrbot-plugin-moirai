# 前端重构 TODO

> 目标：消除当前"production build 充当 dev 环境"的错误架构，建立两条清晰的路径：
> - **开发路径**：Python 后端 + `npm run dev`（HMR、DevTools 正常）
> - **生产路径**：`npm run build` → aiohttp 独立服务器托管静态 + API，根路径服务，无 basePath

---

## 阶段 7 — AstrBot Plugin Pages 接入策略（独立服务器模式）

> **结论：不走 AstrBot Plugin Pages iframe 路线。**
>
> AstrBot 官方文档明确：Plugin Pages 运行在受限 iframe 中，只有 `allow-scripts`、
> `allow-forms`、`allow-downloads` 权限。这与我们 React SPA 的架构存在根本冲突：
>
> | 我们的功能 | iframe 限制 |
> |---|---|
> | `localStorage`（settings、sudo guard、language、主题） | **禁止** |
> | `em_session` session cookie（auth 系统） | **无法访问** |
> | Next.js App Router 客户端路由 | 行为不确定 |
> | `next-themes` 主题持久化 | **禁止** |
>
> LivingMemory 出于同样原因选择了独立服务器模式（FastAPI on dedicated port），
> 而不是把完整 WebUI 嵌入 AstrBot iframe。我们采用相同策略。
>
> 另外，AstrBot Plugin Pages 的 bridge API 路径格式为 `/api/plug/<plugin_name>/<endpoint>`，
> 而原方案 7a 里写的 `/{PLUGIN_NAME}/api/stats` 格式是错误的。

### 生产部署方案（独立服务器，选项 A）

插件在 AstrBot 中启动时：

1. `WebuiServer` 在 `webui_port`（默认 2655）启动独立 aiohttp 服务器
2. 同时从 `pages/moirai/` 托管完整 React SPA 静态文件
3. 所有 `/api/*` 路由由同一个 aiohttp 进程处理（同源，无 CORS）
4. 用户访问 `http://<host>:2655` 即可进入完整 WebUI

### 7a — `main.py` 启动插件时调用 `build_frontend`

在插件加载时（`__init__` 或 `initialize` 方法），触发一次生产构建：

```python
from core.utils.frontend_build import build_frontend

async def initialize(self) -> None:
    # 仅在 pages/moirai/ 不存在时构建（force=False），避免每次启动都重建
    if not build_frontend(force=False):
        logger.warning("[Moirai] Frontend build failed — WebUI may be unavailable")
    
    self._webui = WebuiServer(
        persona_repo=...,
        event_repo=...,
        impression_repo=...,
        data_dir=self._data_dir,
        port=self._config.webui_port,
        auth_enabled=self._config.webui_auth_enabled,
        plugin_version=get_plugin_version(),
        initial_config=self._config.to_dict(),
    )
    await self._webui.start()
    logger.info("[Moirai] WebUI running at http://localhost:%d", self._config.webui_port)
```

**注意**：`build_frontend(force=False)` 在 `pages/moirai/index.html` 已存在时跳过构建，
所以生产环境下通常直接用打包好的静态文件，不会每次重建。

### 7b — 在 AstrBot 面板入口处显示跳转提示（可选）

在 `pages/moirai/` 里同时保留完整 React SPA——这本身就是我们的独立服务器内容。
AstrBot 面板会把 `pages/moirai/index.html` 显示在受限 iframe 里，内容大概率渲染异常。

如果需要给 AstrBot 面板一个友好的入口页，可在 `pages/moirai/` 根目录放一个极简
`index.html` 作为 AstrBot 面板入口，同时把真正的 React SPA 放在子路径。

但这会让独立服务器访问变复杂——**不推荐**。更干净的做法是什么都不改，
让 AstrBot 面板展示加载失败，同时在插件启动日志里打印独立服务器地址即可：

```python
logger.info("[Moirai] WebUI: http://localhost:%d (独立服务器，非 AstrBot 面板)", port)
```

### 阶段 7 测试

```bash
# 验证独立服务器完整工作
curl -s -o /dev/null -w "%{http_code}" http://localhost:2655/           # 200
curl -s -o /dev/null -w "%{http_code}" http://localhost:2655/events/    # 200
curl -s http://localhost:2655/api/stats | python3 -c "import sys,json; d=json.load(sys.stdin); print('events:', d['events'])"
# 期望：events: 8
```

### 静态文件 404 的排查步骤

如果访问独立服务器出现 JS/CSS 404，原因一定是 `pages/moirai/` 为空或被删除。修复：

```bash
# 确认 out/ 已有最新构建产物
ls web/frontend/out/_next/static/chunks/ | wc -l   # 应 > 0

# 如果 out/ 不存在，先重建
export PATH="/Users/kiyoaki/miniconda3/envs/node/bin:$PATH"
cd web/frontend && npm run build && cd ../..

# 把 out/ 复制到 pages/moirai/
python3 -c "from core.utils.frontend_build import build_frontend; build_frontend(force=True)"

# 确认
ls pages/moirai/_next/static/chunks/ | wc -l   # 应与 out/ 中数量一致
```

---

## 实施顺序和优先级总览

| 阶段 | 文件 | 优先级 | 状态 |
|------|------|--------|------|
| 0 | `run_webui_dev.py` | 最高 | 完成 |
| 1 | `web/server.py` (config schema) | 最高 | 完成 |
| 2 | `web/frontend/next.config.mjs` | 高 | 完成 |
| 3 | `core/utils/frontend_build.py` | 高 | 完成 |
| 4 | `web/server.py` (路由) | 高 | 完成 |
| 5 | `web/frontend/lib/api.ts` | 中 | 完成 |
| 6 | `run_webui_dev.py` (打印信息) | 低 | 完成 |
| 7 | AstrBot Plugin Pages — 独立服务器模式确认 | 参考 | 本文档 |

**最终部署架构**：独立 aiohttp 服务器（默认 2655 端口）托管 React SPA + API，
用户直接访问该端口，与 AstrBot dashboard 完全解耦。
