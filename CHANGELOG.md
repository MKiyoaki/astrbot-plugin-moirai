# CHANGELOG

## [v0.10.10] — 2026-05-15

### WebUI 登录页视觉升级

**Features**

- 全新编辑风格登录页：左右分栏布局、丝线背景动画、右下角悬浮设置控件
- 字体统一为 PT Serif（400/700），品牌标题 `π` 与 `.` 使用 primary color
- 登录页版本号直接读取后端 `/api/auth/status`，不再硬编码
- `run_webui_dev.py` 新增 `--auth` 参数，可本地预览登录页
- 「忘记密码」Hover 提示，引导用户查看 AstrBot Token 或插件配置

**Bug Fix**

- 补全 `api.ts` 缺失的 `listArchived` / `archive` / `unarchive` 方法，修复构建报错

完整更新日志见 [docs/CHANGELOG.md](docs/CHANGELOG.md)。

