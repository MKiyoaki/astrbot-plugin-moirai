<div align="center">

<img src="https://raw.githubusercontent.com/MKiyoaki/astrbot-plugin-moirai/main/logo.png" width="96" alt="Moirai Logo" />

# Moirai - 世界线

**AstrBot 三轴长期记忆与数据可视化插件**

[![version](https://img.shields.io/badge/版本-v0.12.4-blueviolet)](metadata.yaml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-APGL-green)](LICENSE)
[![en](https://img.shields.io/badge/English-README__EN.md-blue)](README_EN.md)

*情节轴 · 社交轴 · 叙事轴*

Made with ♥ by MKiyoaki & Gariton

</div>

---

## 这是什么

Moirai 为 AstrBot 增加三轴持久记忆：每段对话自动切分为**情节事件**，参与者间的互动积累为**社交印象**，每日活动凝练为**叙事摘要**。三轴数据在响应时混合检索注入上下文，无需手动管理。

核心亮点：

- **可视化记忆管理**：7 页 WebUI 覆盖完整数据生命周期——事件时间轴、交互式社交关系图、叙事摘要阅读器、混合检索调试、人格档案库与实时统计，所有数据均可在线查看和编辑
- **高度可定制**：70+ 配置项，各子系统（社交图谱、摘要、Soul Layer、VCM）均可独立开关；检索策略、事件切分阈值、衰减速率均可按场景精细调节
- **记忆召回不消耗额外 LLM**：每条消息的记忆检索与上下文注入零 LLM 调用，不增加 API 费用也不拉长响应链路；BM25 关键词与向量语义并行搜索，RRF 融合排序后按 Token 预算贪心填充
- **可靠降级**：Embedding 不可用时自动退回 BM25；社交图谱、摘要、Soul Layer 各自独立，单模块故障不影响记忆注入主路径

---

## 快速开始

### 安装

**方式一：AstrBot 插件市场**（推荐）

在 AstrBot 管理面板的插件市场中搜索 `astrbot_plugin_moirai`，点击安装后重启 AstrBot。

**方式二：手动克隆**

```bash
cd <astrbot数据目录>/plugins
git clone https://github.com/MKiyoaki/astrbot-plugin-moirai
```

重启 AstrBot，插件首次运行时自动完成数据库初始化。

**推荐额外安装**（可选但建议）：

```bash
pip install sentence-transformers bcrypt
```

- `sentence-transformers`：启用语义向量检索（约 100 MB 模型，首次运行自动下载）
- `bcrypt`：WebUI 密码安全加密（缺失时降级为 SHA-256 并输出警告）

### 基础配置

在 AstrBot 管理面板 → 插件配置 → Moirai 中设置：

| 配置键 | 说明 |
|--------|------|
| `webui_password` | WebUI 登录密码，留空则自动生成（查看 AstrBot 日志获取） |
| `webui_port` | WebUI 端口，默认 `2655` |

### 验证插件生效

1. 浏览器访问 `http://<服务器IP>:2655`，输入密码登录
2. 在 AstrBot 中与机器人对话，几条消息后发送 `/mrm status`
3. 返回结果中 `active_sessions` 不为空、`events` 计数递增，即表示记忆管线正常运行

---

## 使用指南

### 插件在做什么

插件在后台自动完成以下流程，无需任何手动干预：

| 时机 | 行为 |
|------|------|
| 每条消息 | 检索历史事件注入上下文；消息写入当前事件窗口；后台计算向量 |
| 对话静默 / 话题漂移 | 关闭当前事件窗口，触发异步提取（主题、摘要、标签、Big Five） |
| 每日 | 显著度衰减 · 群组叙事摘要 · 低显著度事件清理 |
| 每周 | 人格档案合成 · 社交印象聚合 |

### /mrm 指令速查

所有指令需要 AstrBot **管理员权限**。发送 `/mrm language cn` 切换响应语言为中文。

**常用查询**

| 指令 | 说明 |
|------|------|
| `/mrm status` | 插件运行状态（任务、活跃会话、WebUI 状态） |
| `/mrm recall <关键词>` | 手动触发混合记忆检索，返回匹配事件与评分 |
| `/mrm persona <平台ID>` | 查看指定用户的人格档案（Big Five 评分、支撑事件） |
| `/mrm soul` | 当前会话四维情绪状态（需启用 Soul Layer） |

**操作指令**

| 指令 | 说明 |
|------|------|
| `/mrm flush` | 清除当前会话上下文窗口（不影响数据库） |
| `/mrm webui on\|off` | 启动或停止 WebUI 服务 |
| `/mrm language <cn\|en\|ja>` | 切换指令响应语言（持久保存） |
| `/mrm run decay` | 手动触发显著度衰减 |
| `/mrm run synthesis` | 手动触发人格合成 |
| `/mrm run summary` | 手动触发所有群组摘要生成 |
| `/mrm run cleanup` | 手动触发低显著度事件清理 |
| `/mrm help` | 显示帮助 |

**重置指令 ⚠️**

> 需要二步确认：首次发送后返回警告，**30 秒内再次发送同一指令**才会执行。

| 指令 | 操作范围 |
|------|---------|
| `/mrm reset here` | 当前群组的所有事件与摘要 |
| `/mrm reset event <群组ID>` | 指定群组的所有事件与摘要 |
| `/mrm reset event all` | 全部事件记录 |
| `/mrm reset persona <平台ID>` | 指定用户的人格档案 |
| `/mrm reset persona all` | 全部人格档案 |
| `/mrm reset all` | 全部插件数据（事件、人格、投影文件） |

### WebUI 面板导览

| 页面 | 路径 | 说明 |
|------|------|------|
| 事件流 | `/events` | 按时序浏览事件，支持搜索、标签过滤、内联编辑、回收站 |
| 关系图谱 | `/graph` | 交互式人际关系图，节点为人格，边为印象，可查看证据事件 |
| 叙事摘要 | `/summary` | 按群组与日期浏览每日摘要（话题 · 事件列表 · 情绪动态） |
| 记忆检索 | `/recall` | 手动混合检索，查看命中事件与 RRF 评分 |
| 数据库 | `/library` | 人格 · 人物事件 · 印象 · 标签 分标签浏览 |
| 统计 | `/stats` | 事件/人格数量、标签分布、时序图、管线性能 |
| 设置 | `/settings` | 主题 · 语言 · 密码 · 手动任务触发 |

WebUI 采用双层认证：**登录**（密码存于 `data_dir/.webui_password`）+ **Sudo 提权**（写操作前重新输入密码）。纯本地部署可设 `webui_auth_enabled: false` 跳过。

---

## 高级配置与调优

### 核心模块开关

| 功能 | 配置键 | 默认 |
|------|--------|------|
| WebUI 面板 | `webui_enabled` | ✅ 开 |
| 语义向量检索 | `embedding_enabled` | ✅ 开 |
| 话题漂移检测 | `boundary_topic_drift_enabled` | ✅ 开 |
| 性格视角记忆事件 | `persona_influenced_summary` | ✅ 开 |
| 社交关系图谱 | `relation_enabled` | ✅ 开 |
| 每日群组摘要 | `summary_enabled` | ✅ 开 |
| 人格档案合成 | `persona_synthesis_enabled` | ✅ 开 |
| 显著度衰减 | `decay_enabled` | ✅ 开 |
| 自动清理 | `memory_cleanup_enabled` | ✅ 开 |
| Soul Layer | `soul_enabled` | ❌ 关 |
| Markdown 投影 | `markdown_projection_enabled` | ✅ 开 |
| VCM 状态机 | `vcm_enabled` | ✅ 开 |

### 记忆质量调优

以下参数对记忆质量影响最大，其余参数使用默认值即可。

**检索注入**

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `retrieval_top_k` | `10` | 每次最多注入几条记忆事件 |
| `retrieval_token_budget` | `800` | 注入记忆的 Token 上限 |
| `retrieval_active_only` | `true` | 仅检索活跃事件，排除已归档 |

**事件切分**

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `boundary_time_gap_minutes` | `30` | 空闲多久后切分新事件 |
| `boundary_max_messages` | `50` | 单事件消息数硬上限 |
| `boundary_topic_drift_threshold` | `0.6` | 话题漂移触发阈值（余弦距离，越小越敏感） |

**向量嵌入（API 模式）**

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `embedding_provider` | `"local"` | `"local"` 本地模型 / `"api"` 远程 API |
| `embedding_api_url` | `""` | API 端点地址 |
| `embedding_api_key` | `""` | API 密钥 |
| `embedding_model` | `"BAAI/bge-small-zh-v1.5"` | 本地模型名或 API 模型名 |

**记忆衰减与清理**

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `decay_lambda` | `0.01` | 衰减速率（半衰期约 69 天） |
| `memory_cleanup_threshold` | `0.3` | 低于此显著度则永久删除 |
| `memory_cleanup_retention_days` | `30` | 归档事件在永久删除前的保留天数 |

### 常见问题

**WebUI 无法连接**

检查：① `webui_enabled` 是否为 `true`；② 端口 `webui_port`（默认 2655）未被防火墙屏蔽；③ AstrBot 日志中无 WebUI 启动报错。

**Embedding 模型下载失败**

本地模型首次启动时从 HuggingFace 下载，国内网络可能超时。解决方案：配置 `embedding_provider: "api"` 使用远程 API，或设置 HuggingFace 镜像环境变量 `HF_ENDPOINT`。

### 已知局限

| 领域 | 说明 |
|------|------|
| 并行对话 | 同群内并行对话视为单一事件，无回复链解缠（v2 规划） |
| 事件层级 | 仅支持平铺结构，无嵌套事件（v2 规划） |
| 嵌入模型 | 本地模型针对中文优化，英文为主的部署建议配置 API 提供商 |
| 图谱规模 | 设计目标 < 500 节点，超大群组历史可能影响 UI 性能 |
| LLM 质量 | 话题标注、Big Five 评分、摘要质量取决于所配置 LLM 的能力 |
| Soul Layer | 实验性，极端参数下行为可能异常 |
| Token 上限 | 800 Token 注入为硬上限，高活跃群组中部分相关事件可能被截断 |

---

## 技术架构（开发者）

### 三轴记忆模型

| 轴 | 数据实体 | 说明 |
|----|---------|------|
| 情节轴 | `Event` | 离散对话窗口，含主题、摘要、标签与显著度评分 |
| 社交轴 | `Impression` | 基于 IPC 人际环模型的有向人际关系图谱 |
| 叙事轴 | `Summary` | 每日群组摘要（`YYYY-MM-DD.md`），记录情绪动态与关键事件 |

### 数据流与 RAG 检索管线

```
AstrBot 消息流
        │
        ▼
 ① 热路径（每条消息，0 次 LLM 调用）
        │  身份解析 → uid 查找
        │  MessageWindow 累积
        │  后台：单次编码 + O(1) 质心更新
        │  混合 RAG → System Prompt 注入
        │
        ▼（窗口关闭时）
 ② 事件提取（异步，每事件 1 次 LLM 调用）
        │  LLM 分段 或 语义 DBSCAN 聚类
        │  统一提取：主题 / 摘要 / 标签 / Big Five
        │  标签向量归一化
        │
        ▼
 ③ IPC 分析（异步，Big Five 命中缓存则 0 次额外 LLM）
        │  Big Five → IPC 坐标映射（纯数学）
        │  EMA 印象更新 → SQLite upsert
        │
 ④ 周期任务（调度器，并发执行）
        │  每日：显著度衰减 · 群组摘要 · 记忆清理
        │  每周：人格合成 · 印象聚合
```

**LLM 调用预算**

| 触发时机 | 任务 | 调用次数 |
|---------|------|---------|
| 每条消息（热路径） | 检索与注入 | **0** |
| 每个事件关闭 | 核心提取 | **1** |
| 每个事件（社交） | Big Five 评分 | **0**（命中统一提取）或 **1** |
| 每周 | 人格合成 | **每活跃用户 1 次** |
| 每日/每周 | 群组摘要 | **每活跃群组 ≤ 2 次** |
| 周期 | 印象聚合 | **0**（纯数学） |

### 存储布局

```
data/plugins/<plugin_name>/data/
├── db/
│   └── core.db          # SQLite WAL：events + FTS5 + sqlite-vec（单文件）
├── personas/
│   └── <uid>/
│       ├── PROFILE.md   # 只读投影，每周重新生成
│       └── IMPRESSIONS.md  # 用户可编辑，变更自动合并回 DB
├── groups/
│   └── <gid>/
│       └── summaries/
│           └── YYYY-MM-DD.md
└── global/
    ├── SOP.md
    └── BOT_PERSONA.md
```

单文件持久化：SQLite WAL 模式 + 自动迁移前备份，数据库可单文件迁移。

### 社交关系推断（IPC 模型）

Big Five 评分（O/C/E/A/N）通过以下公式映射至 IPC 坐标：

```
亲和度 = 0.70 × 宜人性 + 0.35 × 外向性 − 0.20 × 神经质
权力感 = 0.70 × 外向性 + 0.35 × 尽责性 − 0.15 × 神经质
```

印象以 EMA（指数移动平均，α 可配置）方式更新，归入八象限标签（亲和 / 活跃 / 掌控 / 高傲 / 冷淡 / 孤避 / 顺应 / 谦让）。

所有实体通过内部稳定 `uid` 关联（而非平台 ID）。映射 `(platform, physical_id) → uid` 在适配器边界维护，支持同一用户跨平台账号合并。

---

## 致谢

参考实现：
- [LivingMemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) — 反思阈值、时间衰减、混合检索 RRF
- [Memorix](https://github.com/exynos967/astrbot_plugin_memorix) — 范围路由、生命周期状态、图谱可视化
- [Scriptor](https://github.com/ysf7762-dev/astrbot_plugin_scriptor) — 身份统一、文件即记忆、睡眠整合
- MaiBot — chat_stream 作为一等公民概念
