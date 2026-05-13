# 前端重构 TODO

> 目标：消除当前"production build 充当 dev 环境"的错误架构，建立两条清晰的路径：
> - **开发路径**：Python 后端 + `npm run dev`（HMR、DevTools 正常）
> - **生产路径**：`npm run build` → aiohttp 独立服务器托管静态 + API，根路径服务，无 basePath

---

## 阶段 0 — 拆分 `run_webui_dev.py`（优先级：最高）

**问题**：`run_webui_dev.py` 调用 `build_frontend(force=True)` 跑生产构建（30s+），
然后用 aiohttp 托管编译产物。这不是开发环境，没有 HMR，没有 source map。

### 修改文件：`run_webui_dev.py`

删除以下两行：
```python
from core.utils.frontend_build import build_frontend
# ...
if not build_frontend(force=True):
    print("  ⚠ 前端构建失败，请检查 Node.js 环境后重试。")
    return
```

`run_webui_dev.py` 的职责缩减为：只注入演示数据、只启动 Python 后端（aiohttp on 2654）。

### 正确的开发工作流（两个终端）

**终端 A — Python 后端：**
```bash
conda activate plugin-dev
python run_webui_dev.py
# 后端运行在 http://localhost:2654
```

**终端 B — React 前端：**
```bash
cd web/frontend
export PATH="/Users/kiyoaki/miniconda3/envs/node/bin:$PATH"
npm run dev
# 前端运行在 http://localhost:3000
```

`next.config.mjs` 里的 rewrites 已经把 `/api/*` 代理到 `localhost:2654/api/*`，所以两者直接协作。

### 阶段 0 测试

1. 按上述两个终端分别启动
2. 打开 `http://localhost:3000`
3. 验证：页面加载，侧边栏显示，Events 页面显示 8 条演示事件
4. 验证：修改 `web/frontend/app/page.tsx` 任意文字 → 浏览器即时热更新（HMR 生效）
5. 验证：`http://localhost:3000/events` 直接访问不 404，SPA 路由正常

---

## 阶段 1 — 修复 `/api/config` schema 格式不匹配（优先级：最高）

**问题**：`_conf_schema.json` 是分组嵌套结构：
```json
{ "webui": { "type": "object", "items": { "webui_enabled": {...}, "webui_port": {...} } } }
```
但 React `config/page.tsx` 期望扁平结构：
```json
{ "schema": { "webui_enabled": {...}, "webui_port": {...} }, "values": {...} }
```
现在 `schema['webui_enabled']` 永远是 `undefined`，config 页面永远卡在 loading。

### 修改文件：`web/server.py` — `_handle_get_config`

将当前实现（约第 537–541 行）替换为：

```python
async def _handle_get_config(self, _: web.Request) -> web.Response:
    raw = json.loads(self._CONF_SCHEMA_PATH.read_text(encoding="utf-8")) if self._CONF_SCHEMA_PATH.exists() else {}
    
    # 展平：把每个 group 的 items 合并到一个 flat dict
    flat_schema: dict = {}
    for group_data in raw.values():
        if isinstance(group_data, dict) and group_data.get("type") == "object":
            flat_schema.update(group_data.get("items", {}))
    
    # 从 flat_schema 的 default 值构建初始 values
    values: dict = {k: v.get("default") for k, v in flat_schema.items()}
    values.update(self._initial_config)
    if self._config_path.exists():
        values.update(json.loads(self._config_path.read_text(encoding="utf-8")))
    
    return _json({"schema": flat_schema, "values": values})
```

同时修复 `_handle_update_config`（约第 546–557 行），校验时查 flat schema：

```python
async def _handle_update_config(self, request: web.Request) -> web.Response:
    body = await request.json()
    raw = json.loads(self._CONF_SCHEMA_PATH.read_text(encoding="utf-8")) if self._CONF_SCHEMA_PATH.exists() else {}
    
    # 构建 flat schema 用于类型校验
    flat_schema: dict = {}
    for group_data in raw.values():
        if isinstance(group_data, dict) and group_data.get("type") == "object":
            flat_schema.update(group_data.get("items", {}))
    
    coerced = {}
    for k, v in body.items():
        if k not in flat_schema:
            continue
        try:
            t = flat_schema[k].get("type", "string")
            coerced[k] = bool(v) if t == "bool" else (int(v) if t == "int" else (float(v) if t == "float" else v))
        except:
            coerced[k] = v
    
    existing = json.loads(self._config_path.read_text(encoding="utf-8")) if self._config_path.exists() else {}
    existing.update(coerced)
    self._config_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return _json({"ok": True, "saved": list(coerced.keys())})
```

### 阶段 1 测试

```bash
# 后端运行中，执行：
curl -s http://localhost:2654/api/config | python3 -c "
import sys, json
d = json.load(sys.stdin)
schema = d['schema']
print('扁平字段数:', len(schema))
print('webui_enabled 存在:', 'webui_enabled' in schema)
print('embedding_enabled 存在:', 'embedding_enabled' in schema)
print('values 中 webui_port:', d['values'].get('webui_port'))
"
```

期望输出：
```
扁平字段数: 72
webui_enabled 存在: True
embedding_enabled 存在: True
values 中 webui_port: 2655
```

然后在浏览器打开 `http://localhost:3000/config`，应看到所有配置分组正常渲染（不再卡 loading）。

---

## 阶段 2 — 去掉 Next.js basePath（优先级：高）

**问题**：`basePath: '/api/pages/astrbot_plugin_moirai/moirai'` 被烧进所有 JS bundle，
导致生产部署必须从这个特定路径提供服务，aiohttp 需要复杂的路由 hack 来匹配。
LivingMemory 没有 basePath，相对 URL 在任何路径下都能工作。

### 修改文件：`web/frontend/next.config.mjs`

```js
/** @type {import('next').NextConfig} */
const isDev = process.env.NODE_ENV === 'development'

const nextConfig = {
  output: 'export',

  images: {
    unoptimized: true,
  },

  trailingSlash: true,

  async rewrites() {
    if (!isDev) return []
    const backendPort = process.env.BACKEND_PORT || '2654'
    return [
      {
        source: '/api/:path*',
        destination: `http://localhost:${backendPort}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
```

变化点：
- 移除 `basePath`（所有环境）
- 移除 `distDir: 'out'`（使用 Next.js 静态导出的默认 `out/` 目录）
- `output: 'export'` 保留（始终导出静态文件）
- dev 下的 rewrites 保留（`npm run dev` 时代理 API）

### 阶段 2 测试

```bash
cd web/frontend
export PATH="/Users/kiyoaki/miniconda3/envs/node/bin:$PATH"
npm run build 2>&1 | grep -E "(Route|error|warn|basePath)"
```

期望：构建成功，输出的 Route 列表里路径是 `/`、`/events`、`/graph` 等（无 `/api/pages/...` 前缀）。

```bash
# 验证生成的 HTML 里没有 basePath
grep -r "api/pages/astrbot" web/frontend/out/ | wc -l
# 期望：0
```

---

## 阶段 3 — 简化 `frontend_build.py`（优先级：高）

**问题**：`frontend_build.py` 做了按目录深度计算相对路径的 HTML 重写，
这只是为了修补 basePath 留下的绝对路径。去掉 basePath 后这段逻辑完全不需要。

### 修改文件：`core/utils/frontend_build.py`

删除整个 HTML 重写循环（最后的 `_BASE` 部分），替换为简单的 copy：

```python
"""Utility for building the Next.js frontend.

`npm run build` outputs a static export to web/frontend/out/.
The output is copied verbatim to pages/moirai/ — no path rewriting needed.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent.parent
_FRONTEND_DIR = _REPO_ROOT / "web" / "frontend"
_OUT_DIR = _FRONTEND_DIR / "out"
_PAGES_DIR = _REPO_ROOT / "pages" / "moirai"
_PAGES_INDEX = _PAGES_DIR / "index.html"

_CONDA_NODE_BIN = Path.home() / "miniconda3" / "envs" / "node" / "bin"

def _find_npm() -> str | None:
    if shutil.which("npm"):
        return "npm"
    candidate = _CONDA_NODE_BIN / "npm"
    if candidate.exists():
        return str(candidate)
    return None


def build_frontend(force: bool = False) -> bool:
    """Build the Next.js frontend and sync output to pages/moirai/.

    Skips the build if pages/moirai/index.html already exists and force=False.
    Returns True on success, False on failure.
    """
    if not force and _PAGES_INDEX.exists():
        logger.debug("[FrontendBuild] pages/moirai/ already built, skipping.")
        return True

    if not _FRONTEND_DIR.exists():
        logger.error("[FrontendBuild] Frontend source not found at %s", _FRONTEND_DIR)
        return False

    npm = _find_npm()
    if npm is None:
        logger.error(
            "[FrontendBuild] npm not found. "
            "Install Node.js or activate the 'node' conda env and retry."
        )
        return False

    env = os.environ.copy()
    if str(_CONDA_NODE_BIN) not in env.get("PATH", ""):
        env["PATH"] = str(_CONDA_NODE_BIN) + os.pathsep + env.get("PATH", "")

    logger.info("[FrontendBuild] Building frontend (npm run build) …")
    try:
        result = subprocess.run(
            [npm, "run", "build"],
            cwd=_FRONTEND_DIR,
            env=env,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        logger.error("[FrontendBuild] npm run build failed to start: %s", exc)
        return False

    if result.returncode != 0:
        logger.error(
            "[FrontendBuild] npm run build failed (exit %d):\n%s\n%s",
            result.returncode,
            result.stdout[-2000:],
            result.stderr[-2000:],
        )
        return False

    if not _OUT_DIR.exists():
        logger.error("[FrontendBuild] Build finished but out/ not found.")
        return False

    if _PAGES_DIR.exists():
        shutil.rmtree(_PAGES_DIR)
    shutil.copytree(_OUT_DIR, _PAGES_DIR)

    logger.info("[FrontendBuild] Frontend built successfully → %s", _PAGES_DIR)
    return True
```

---

## 阶段 4 — 修复 `web/server.py` 静态托管路由（优先级：高）

**问题**：`web/server.py` 现在把静态文件挂载在 `/api/pages/astrbot_plugin_moirai/moirai/{tail:.*}`，
根路径 `/` 只是重定向到这个复杂前缀。去掉 basePath 后，静态文件应直接从 `/` 开始托管。

### 修改文件：`web/server.py`

**删除**：
```python
self._base_path = "/api/pages/astrbot_plugin_moirai/moirai"
```

**修改 `_build_app`** — 删除现有的三条 spa 路由，替换为简单的根路径 catch-all：

原有（删除）：
```python
app.router.add_get(self._base_path, self._handle_spa_fallback)
app.router.add_get(self._base_path + "/", self._handle_spa_fallback)
app.router.add_get(self._base_path + "/{tail:.*}", self._handle_spa_fallback)
```

**同时删除**：
```python
app.router.add_get("/", lambda r: web.HTTPFound(self._base_path + "/"))
```

**替换为**：
```python
app.router.add_get("/", self._handle_spa_fallback)
app.router.add_get("/{tail:.*}", self._handle_spa_fallback)
```

**修改 `_handle_spa_fallback`**（`tail` 直接就是路径，不需要剥离 base_path）：

```python
async def _handle_spa_fallback(self, request: web.Request) -> web.Response:
    tail = request.match_info.get("tail", "").strip("/")
    filename = tail if tail else "index.html"
    target_file = _STATIC_DIR / filename

    # 1. 直接文件（JS/CSS/fonts/favicon 等）
    if target_file.is_file():
        return web.FileResponse(target_file)

    # 2. 目录 → index.html（Next.js trailingSlash: true 生成的结构）
    if (target_file / "index.html").is_file():
        return web.FileResponse(target_file / "index.html")

    # 3. 扩展名省略：/events → events.html（兼容 trailingSlash 关闭时）
    if (_STATIC_DIR / f"{filename}.html").is_file():
        return web.FileResponse(_STATIC_DIR / f"{filename}.html")

    # 4. SPA fallback：所有未匹配路径返回 index.html（前端路由接管）
    index_file = _STATIC_DIR / "index.html"
    if index_file.is_file():
        return web.FileResponse(index_file)

    return web.Response(status=404, text=f"Frontend missing: {filename}")
```

注意：API 路由（`/api/*`）注册在 catch-all 之前，aiohttp 按注册顺序优先匹配，不会被 SPA fallback 拦截。

### 阶段 4 测试（使用独立服务器测试，不依赖 AstrBot）

```bash
# 先构建（阶段 2 完成后）
cd web/frontend && npm run build

# 启动服务器（模拟生产，port 2654 用于和 run_webui_dev.py 兼容）
conda activate plugin-dev && python run_webui_dev.py
```

```bash
# 测试根路径
curl -s -o /dev/null -w "%{http_code}" http://localhost:2654/
# 期望：200（直接返回 HTML，不再是 302）

# 测试页面路由
for route in "" "events/" "graph/" "settings/" "_next/static/"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:2654/$route")
  echo "/$route → $code"
done
# 期望：全部 200

# 测试 API 不被 SPA fallback 拦截
curl -s http://localhost:2654/api/stats | python3 -c "import sys,json; d=json.load(sys.stdin); print('events:', d['events'])"
# 期望：events: 8
```

在浏览器打开 `http://localhost:2654`，验证页面正常渲染（演示数据可见）。

---

## 阶段 5 — 简化 `lib/api.ts` 的 URL 路由逻辑（优先级：中）

**问题**：`_isPluginPageFallback()` 的 iframe 检测在不同环境下行为不可预测。
去掉 basePath 后，API 端点无论从哪里访问都是 `/api/*`（同源），不需要任何 URL 改写。

### 修改文件：`web/frontend/lib/api.ts`

删除以下所有内容：

```typescript
type BridgeContext = { pluginName?: string; displayName?: string }
type BridgeParams = Record<string, string>
type Bridge = { ... }

declare global {
  interface Window {
    AstrBotPluginPage?: Bridge
  }
}

function _bridge() { ... }
let bridgeReady: Promise<void> | null = null
async function _readyBridge(bridge: Bridge) { ... }
function _parsePluginEndpoint(url: string) { ... }
function _methodAlias(endpoint: string, method: string) { ... }
function _jsonBody(body: BodyInit | null | undefined) { ... }
function _isPluginPageFallback() { ... }
function _pluginFetchUrl(url: string) { ... }
```

将 `request` 函数简化为：

```typescript
export type ApiError = { status: number; body: string }

async function request<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  })
  if (!res.ok) {
    const raw = await res.text()
    let detail = raw
    try { const j = JSON.parse(raw); detail = j.error || raw } catch {}
    throw { status: res.status, body: detail } satisfies ApiError
  }
  return res.json() as Promise<T>
}
```

所有 `request('/api/stats')` 调用保持不变 — `/api/stats` 在 dev（3000 端口，被 rewrite 代理）和生产（2655 端口，直接命中）下都能工作。

### 阶段 5 测试

```bash
# dev 环境下
cd web/frontend && npm run dev  # 终端 B
# 打开 http://localhost:3000/stats
# 打开浏览器 DevTools → Network 面板
# 验证 /api/stats 请求：
#   - 请求 URL 是 http://localhost:3000/api/stats（无 /api/plug/moirai/ 改写）
#   - 响应 200，有正确数据
#   - 无 CORS 错误
```

---

## 阶段 6 — 更新 `run_webui_dev.py` 的打印信息（优先级：低）

阶段 0 完成后，`run_webui_dev.py` 打印的访问地址仍然是旧的。

### 修改文件：`run_webui_dev.py`

找到末尾的 print 语句，修改为：

```python
print(f"\n  Enhanced Memory — 后端已启动（仅 API，无静态文件）")
print(f"  API:     http://localhost:{port}/api/stats")
print(f"  前端开发: cd web/frontend && npm run dev → http://localhost:3000")
print(f"  数据目录: {data_dir}")
print(f"  认证: 已关闭（本地调试模式）")
```

---

## 阶段 7（可选）— AstrBot Plugin Pages 正式接入

> 这一阶段针对"在真实 AstrBot 环境中让 WebUI 通过 AstrBot 内置路由可访问"的需求。
> 若当前只需要独立服务器模式，可跳过。

**参考 LivingMemory 的 `core/page_api.py` 和 `main.py`。**

### 7a — 注册 API 路由到 AstrBot Quart 服务器

在插件主文件（`main.py` 或其等价文件）中，参照以下模式：

```python
def _register_page_api(self) -> None:
    """将 API 路由注册到 AstrBot 的 Quart 服务器。"""
    if not hasattr(self.context, "register_web_api"):
        return  # 旧版 AstrBot，跳过
    
    PLUGIN_NAME = "astrbot_plugin_moirai"
    PREFIX = f"/{PLUGIN_NAME}"
    
    register = self.context.register_web_api
    register(f"{PREFIX}/api/stats",   self._api_stats,   ["GET"],  "stats")
    register(f"{PREFIX}/api/events",  self._api_events,  ["GET"],  "events")
    register(f"{PREFIX}/api/graph",   self._api_graph,   ["GET"],  "graph")
    # ... 其余端点
```

### 7b — 前端 API URL 切换（AstrBot 模式）

在 AstrBot 内嵌模式下，API 路径是 `/{plugin_name}/api/*` 而非 `/api/*`。
需要一个轻量的运行时检测（比当前的 iframe 检测更可靠）：

建议方案：在 HTML 模板或 AstrBot bridge 注入时，通过 `data-api-base` 属性传递基准路径：
```html
<meta name="api-base" content="/astrbot_plugin_moirai">
```
前端 `api.ts` 读取这个 meta tag，如果存在则在所有 `/api/` 前缀前加上 plugin prefix。

### 阶段 7 测试

在真实 AstrBot 实例中加载插件，访问 AstrBot 的 plugin pages 地址，验证 API 响应正确。

---

## 实施顺序和优先级总览

| 阶段 | 文件 | 优先级 | 预计改动量 |
|------|------|--------|-----------|
| 0 | `run_webui_dev.py` | 🔴 最高 | 删 5 行 |
| 1 | `web/server.py` (`_handle_get_config`, `_handle_update_config`) | 🔴 最高 | 改 ~25 行 |
| 2 | `web/frontend/next.config.mjs` | 🟠 高 | 改 ~5 行 |
| 3 | `core/utils/frontend_build.py` | 🟠 高 | 删 ~10 行 |
| 4 | `web/server.py` (路由部分) | 🟠 高 | 改 ~15 行 |
| 5 | `web/frontend/lib/api.ts` | 🟡 中 | 删 ~60 行 |
| 6 | `run_webui_dev.py` (打印信息) | 🟢 低 | 改 ~5 行 |
| 7 | AstrBot Plugin Pages 接入 | 🔵 可选 | 新增 ~50 行 |

**阶段 0 → 1 完成后，开发体验问题基本解决（HMR 正常、config 页面不卡 loading）。**
**阶段 2 → 4 完成后，生产部署不再依赖 basePath hack，独立服务器可正常使用。**
**阶段 5 完成后，代码清洁，无隐藏的 URL 改写逻辑。**
