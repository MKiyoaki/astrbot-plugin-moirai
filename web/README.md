# Enhanced Memory — WebUI

三轴长期记忆管理 WebUI，基于 aiohttp 提供，无需构建步骤。

## 目录结构

```
web/
├── __init__.py
├── server.py          # WebuiServer：aiohttp 应用 + 认证中间件 + 路由注册
├── auth.py            # AuthManager：bcrypt 密码 + session/sudo 状态
├── registry.py        # PanelRegistry：第三方面板挂载点
├── static/
│   ├── index.html     # 壳（shell）：仅含 sidebar + 空 panel 容器 + script 标签
│   ├── css/           # 按关注点拆分的 CSS 文件
│   │   ├── variables.css     CSS 自定义属性、色彩主题预设、全局 reset
│   │   ├── layout.css        登录覆盖层、侧边栏、主内容区、panel-view
│   │   ├── components.css    通用组件：按钮、输入框、徽章、模态框、toast、详情面板
│   │   ├── timeline.css      事件时间线与列表视图
│   │   ├── graph.css         关系图（Cytoscape）与列表视图
│   │   ├── summary.css       摘要记忆面板
│   │   ├── recall.css        记忆召回测试面板
│   │   ├── settings.css      设置面板
│   │   └── landing.css       首页（Landing）
│   ├── pages/         # 各面板的 HTML 片段，由 JS 按需 fetch 注入
│   │   ├── landing.html      首页：统计卡片 + 快速导航
│   │   ├── events.html       事件流：时间线/列表视图 + 搜索 + CRUD 工具栏
│   │   ├── graph.html        关系图：Cytoscape/列表视图 + 搜索 + 人格管理工具栏
│   │   ├── summary.html      摘要记忆：侧边列表 + Markdown 渲染/编辑器
│   │   ├── recall.html       记忆召回测试：查询输入 + 结果列表
│   │   └── settings.html     设置：色彩主题 + 认证 + 后台任务 + 演示数据
│   ├── components/    # 全局组件，启动时一次性加载
│   │   └── modals.html       所有 CRUD 模态框（事件/人格/印象/回收站）
│   └── js/            # 按职责拆分的 JS 模块（普通 script，无模块系统）
│       ├── state.js          全局 State 对象
│       ├── api.js            fetchJson、renderIcons、toast、modal 工具函数
│       ├── auth.js           登录、登出、sudo 模式、密码修改
│       ├── timeline.js       事件流渲染、桥接线、搜索过滤、CRUD、回收站
│       ├── graph.js          关系图渲染、高亮、人格/印象 CRUD
│       ├── summary.js        摘要面板加载、Markdown 编辑器
│       ├── recall.js         记忆召回测试
│       ├── settings.js       统计、后台任务、演示数据、色彩主题
│       └── app.js            启动（boot）、面板切换、页面动态加载、主题切换
└── README.md          本文件
```

## 功能概览

### 面板

| 面板 | 功能 |
|------|------|
| 首页 | 统计概览（人格/事件/印象/群组数）、快速导航入口 |
| 事件流 | 自定义时间线 + 列表视图；搜索（话题/标签/参与者）；新建/编辑/删除事件；批量删除；回收站还原；密度滑杆过滤 |
| 关系图 | Cytoscape.js 图谱 + 列表视图；邻域高亮；点击印象边查看证据事件并跳转时间线；新建/编辑/删除人格；编辑印象 |
| 摘要记忆 | Markdown 渲染；在线编辑 |
| 记忆召回 | FTS5 全文检索测试，查看检索结果与重要度 |
| 设置 | 色彩主题预设（6 种）；认证管理；后台任务触发；演示数据注入 |

### 认证

- **登录**：bcrypt 密码 → 会话 Cookie（默认 24 h）
- **Sudo**：同一密码二次确认 → 约 30 min 写权限，写操作（创建/删除/更新）均需此模式
- **禁用**：`webui_auth_enabled: false` 跳过全部认证（仅限本地开发）

### API 路由

权限：`public` / `auth`（需登录） / `sudo`（需 Sudo 二级验证）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/auth/status` | public | 当前认证状态 |
| POST | `/api/auth/setup` | public | 首次设置密码 |
| POST | `/api/auth/login` | public | 登录 |
| POST | `/api/auth/logout` | auth | 登出 |
| POST | `/api/auth/sudo` | auth | 进入 sudo 模式 |
| POST | `/api/auth/sudo/exit` | auth | 退出 sudo |
| POST | `/api/auth/password` | sudo | 修改密码 |
| GET | `/api/events` | auth | 列举事件 |
| POST | `/api/events` | sudo | 创建事件 |
| PUT | `/api/events/{id}` | sudo | 更新事件 |
| DELETE | `/api/events/{id}` | sudo | 删除事件（移入回收站） |
| DELETE | `/api/events` | sudo | 清空全部事件 |
| GET | `/api/recycle_bin` | auth | 回收站列表 |
| POST | `/api/recycle_bin/restore` | sudo | 还原事件 |
| DELETE | `/api/recycle_bin` | sudo | 清空回收站 |
| GET | `/api/graph` | auth | 人格节点与印象边 |
| POST | `/api/personas` | sudo | 创建人格 |
| PUT | `/api/personas/{uid}` | sudo | 更新人格 |
| DELETE | `/api/personas/{uid}` | sudo | 删除人格 |
| PUT | `/api/impressions/{obs}/{sub}/{scope}` | sudo | 更新印象 |
| GET | `/api/summaries` | auth | 摘要列表 |
| GET | `/api/summary` | auth | 摘要内容 |
| PUT | `/api/summary` | auth | 保存摘要 |
| GET | `/api/recall` | auth | 记忆召回测试 |
| GET | `/api/stats` | auth | 统计数据 |
| POST | `/api/admin/run_task` | sudo | 触发后台任务 |
| POST | `/api/admin/demo` | sudo | 注入演示数据 |
| GET | `/api/panels` | auth | 已注册第三方面板列表 |

### 第三方面板挂载

其他 AstrBot 插件可向本插件注册额外面板（无需独立 HTTP 服务器）：

```python
em = self.context.get_registered_star("astrbot_plugin_enhanced_memory")
if em and em.webui_registry:
    em.webui_registry.register(
        PanelManifest(
            plugin_id="my_plugin",
            panel_id="my_panel",
            title="我的面板",
            icon="cube",          # Lucide 图标名（不用 Emoji）
            api_prefix="/api/ext/my_plugin",
            permission="auth",
        ),
        routes=[
            PanelRoute("GET", "/api/ext/my_plugin/data", my_handler, permission="auth"),
        ],
    )
```

前端通过 `/api/panels` 自动发现已注册面板；权限校验复用同一套中间件。

### 前端设计规范

- **无构建步骤**：CDN UMD 加载 Cytoscape 3.29.2、Marked 9.1.6、Lucide 0.456.0
- **图标**：Lucide SVG（`<i data-lucide="name">` + `renderIcons()`）；UI 装饰禁用 Emoji
- **色彩令牌**：CSS 变量，支持暗/亮主题 + 6 种强调色预设（sky / red / orange / green / purple / zinc）
- **动态加载**：面板 HTML 片段首次访问时 fetch 注入，避免首屏加载全部代码
- **shadcn 风格**：手写 CSS 对应 shadcn Button / Input / Card / Modal / Separator 等原语；使用 slate 调色板

### 本地开发

```bash
python run_webui_dev.py           # 默认端口 2654，认证禁用，自动注入演示数据
python run_webui_dev.py --port 3000
```

浏览器访问 `http://localhost:2654` 即可预览完整 WebUI。
