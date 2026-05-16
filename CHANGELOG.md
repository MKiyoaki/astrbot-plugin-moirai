# CHANGELOG

## [v0.10.11] — 2026-05-16

### 事件流页面体验优化与 Bug 修复

**Bug Fixes**

- 优化事件节点 Hover 判定：增大热区面积（20px -> 24px），并调整悬浮清理延迟（200ms），解决 Tooltip 闪烁及难以触发的问题。
- 修正统计面板图标：将「已锁定」统计项的图标从 `Zap` 改为中性色的 `Lock`。

**UI/UX Improvements**

- 详细面板自适应：右侧详细面板现在支持自适应宽度（320px ~ 500px），在宽屏下提供更好的视觉体验。
- 显著度分布图表主题适配：图表颜色现已适配 shadcn 主题色，使用 `primary` 变量及其透明度梯度。
- 增强内容间距：优化了详细面板内卡片的 Padding 与自适应表现。

**Refactor**

- 统一 WebUI 筛选组件：将「事件流」页面的紧凑型标签和日期筛选工具栏提取为通用的 `FilterBar` 组件。
- 替换「关系图」和「信息库」原有的筛选栏，实现全站视觉一致性。
- 移除冗余的 `TagFilter` 组件，优化前端代码结构。


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

