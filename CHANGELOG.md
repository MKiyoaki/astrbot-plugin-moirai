# CHANGELOG

## [v0.9.9] — 2026-05-13

### 紧急修复：移除无效的页面注册调用

- 修复了加载插件时出现的 `'MoiraiPlugin' object has no attribute 'register_page'` 错误。
- 遵循 AstrBot 的约定优于配置原则，移除 `main.py` 中冗余的显式页面注册。现在 AstrBot 会通过插件目录下的 `pages/` 结构自动识别并注册 WebUI 页面。

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
