# CHANGELOG

## [v0.9.8] — 2026-05-13

### WebUI 深度集成与双端口架构

**官方页面支持 (AstrBot Plugin Pages)**
- 在 AstrBot 管理面板中注册官方页面。用户现在可以通过侧边栏的 “Moirai” 直接进入 WebUI。
- API 路由已深度集成至 AstrBot 官方 Web 服务（`/api/plug/moirai/*`），共享官方鉴权机制。
- 前端已适配 iframe 嵌套环境，自动识别 API 路径前缀。

**独立 WebUI 服务器增强**
- 独立 WebUI 服务器现在默认启动（端口 2655），方便局域网内直连访问。
- `WebuiServer` 启动逻辑增加端口占用检测与容错处理，避免冲突导致插件加载失败。
- `/mrm webui on/off` 命令逻辑优化，支持手动控制独立端口的开关，并实时反馈状态。
- 独立端口保留基于密码的二次鉴权逻辑，确保非 AstrBot 环境下的安全性。

**其他修复与优化**
- 修正 `web/server.py` 中的静态资源路径，确保独立服务器与官方页面共用同一套构建产物。
- 完善 `PluginInitializer` 的生命周期管理，确保插件卸载时正确关闭 WebUI 服务。

## [v0.9.7] — 2026-05-12

### 配置层级化 (Config Schema Hierarchy)

- 重构 `_conf_schema.json`：将原有 64 个平铺字段按功能组织为 10 个嵌套 `object` 分组（`general` / `webui` / `embedding` / `retrieval` / `vcm` / `soul` / `cleanup` / `summaries` / `boundary` / `relation`），与 AstrBot 原生配置 UI 的分组渲染机制对齐，消除无层级的平铺列表。
- 修改 `core/config.py` `PluginConfig.__init__`：在构造时对 AstrBot 传入的原始 dict 执行单层展平，将嵌套 group dict 合并到统一命名空间，所有现有平铺键名访问器（`_get` / `_int` / `_bool` 等）无需改动，同时保持对旧版平铺配置的向后兼容。
