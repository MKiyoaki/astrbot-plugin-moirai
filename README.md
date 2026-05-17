<div align="center">

<img src="https://raw.githubusercontent.com/MKiyoaki/astrbot-plugin-moirai/main/logo.png" width="96" alt="Moirai Logo" />

# Moirai

**AstrBot 三轴长期记忆与数据可视化插件**

[![version](https://img.shields.io/badge/版本-v0.10.9-blueviolet)](metadata.yaml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-APGL-green)](LICENSE)
[![en](https://img.shields.io/badge/English-README__EN.md-blue)](README_EN.md)

*情节轴 · 社交轴 · 叙事轴*

Made with ♥ by MKiyoaki & Gariton

</div>

---

## ⚡ 快速上手

### 第一步：安装

**方式一：AstrBot 插件市场**（推荐）

在 AstrBot 管理面板的插件市场中搜索 `astrbot_plugin_moirai`，点击安装。

**方式二：手动克隆**

```bash
cd <astrbot数据目录>/plugins
git clone https://github.com/MKiyoaki/astrbot-plugin-moirai
```

安装后重启 AstrBot，插件会自动完成数据库初始化。

> **推荐额外安装**（可选但强烈建议）：
> ```bash
> pip install sentence-transformers bcrypt
> ```
> - `sentence-transformers`：启用语义向量检索（约 100 MB 模型，首次运行自动下载）
> - `bcrypt`：WebUI 密码安全加密（缺失时降级为 SHA-256 并输出警告）

### 第二步：设置 WebUI 密码

在 AstrBot 管理面板 → 插件配置 → Moirai 中，找到 `webui_password` 字段并填入密码。留空则自动生成，请查看 AstrBot 日志获取。

### 第三步：打开 WebUI

浏览器访问 `http://<你的服务器IP>:2655`，输入密码登录，即可看到完整的记忆管理面板。

> 默认端口 `2655`，可在配置中通过 `webui_port` 修改。

---

## ✨ 功能特性

Moirai 采用**三轴记忆架构**，将对话历史沿三个独立维度建模：

| 轴 | 数据实体 | 说明 |
|----|---------|------|
| **情节轴** | `Event` | 离散对话窗口，含主题、摘要、标签与显著度评分 |
| **社交轴** | `Impression` | 基于人际环 (IPC) 模型的有向人际关系图谱 |
| **叙事轴** | `Summary` | 每日群组摘要（`YYYY-MM-DD.md`），记录情绪动态与关键事件 |

**其他核心能力：**

- **混合检索**：BM25 关键词搜索 + 向量语义搜索并行，RRF 融合，贪心填充至 Token 预算
- **事件边界检测**：无需 LLM，依靠空闲时间、话题漂移、消息数量等启发式信号自动切分
- **WebUI 管理面板**：7 个可视化页面，全面管理三轴记忆数据
- **Soul Layer**（实验性，默认关闭）：四维情绪状态向量，影响回复风格

**模块化开关：**

| 功能 | 配置键 | 默认 |
|------|--------|------|
| WebUI 面板 | `webui_enabled` | ✅ 开 |
| 语义向量检索 | `embedding_enabled` | ✅ 开 |
| 话题漂移检测 | `boundary_topic_drift_enabled` | ✅ 开 |
| 社交关系图谱 | `relation_enabled` | ✅ 开 |
| 每日群组摘要 | `summary_enabled` | ✅ 开 |
| 人格档案合成 | `persona_synthesis_enabled` | ✅ 开 |
| 显著度衰减 | `decay_enabled` | ✅ 开 |
| 自动清理 | `memory_cleanup_enabled` | ✅ 开 |
| Soul Layer | `soul_enabled` | ❌ 关 |
| Markdown 投影 | `markdown_projection_enabled` | ✅ 开 |
| VCM 状态机 | `vcm_enabled` | ✅ 开 |

---

## 📋 /mrm 指令参考

所有管理指令通过 `/mrm` 指令组发送，需要 AstrBot **管理员权限**。

> 使用 `/mrm language cn` 可将指令响应切换为中文。

### 信息查询

| 指令 | 说明 |
|------|------|
| `/mrm status` | 查看插件运行状态（任务列表、活跃会话、WebUI 状态） |
| `/mrm persona <平台ID>` | 查看指定用户的人格档案（描述、Big Five 评分、支撑事件） |
| `/mrm soul` | 查看当前会话的四维情绪状态 |
| `/mrm recall <关键词>` | 手动触发混合记忆检索，返回匹配事件与评分 |

### 操作指令

| 指令 | 说明 |
|------|------|
| `/mrm webui on\|off` | 启动或停止 WebUI 服务 |
| `/mrm flush` | 清除当前会话上下文窗口（不影响数据库） |
| `/mrm language <cn\|en\|ja>` | 切换指令响应语言（重启后保留） |
| `/mrm run decay` | 手动触发显著度衰减任务 |
| `/mrm run synthesis` | 手动触发人格合成任务 |
| `/mrm run summary` | 手动触发所有群组摘要生成 |
| `/mrm run cleanup` | 手动触发低显著度事件清理 |
| `/mrm help` | 显示帮助文档 |

### 重置指令 ⚠️

> **需要二次确认**：首次发送后会返回警告，**30 秒内再次发送相同指令**才会执行。

| 指令 | 操作范围 |
|------|---------|
| `/mrm reset here` | 删除当前群的所有事件与摘要文件 |
| `/mrm reset event <群组ID>` | 删除指定群的所有事件与摘要文件 |
| `/mrm reset event all` | 删除**全部**事件记录 |
| `/mrm reset persona <平台ID>` | 删除指定用户的人格档案 |
| `/mrm reset persona all` | 删除**全部**人格档案 |
| `/mrm reset all` | 清空**全部**插件数据（事件、人格、投影文件） |

---

## ⚙️ 配置项速查

在 AstrBot 插件配置页或 `_conf_schema.json` 中调整，以下为最常用项：

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `webui_port` | `2655` | WebUI 端口 |
| `webui_auth_enabled` | `true` | 是否启用登录验证 |
| `embedding_enabled` | `true` | 关闭则仅用 BM25 关键词检索 |
| `embedding_provider` | `"local"` | `"local"` 本地模型 / `"api"` 远程 API |
| `retrieval_top_k` | `10` | 每次最多注入几条记忆事件 |
| `retrieval_token_budget` | `800` | 注入记忆的 Token 上限 |
| `boundary_time_gap_minutes` | `30` | 空闲多久后切分新事件 |
| `summary_interval_hours` | `24` | 群组摘要生成频率（小时） |
| `relation_enabled` | `true` | 是否构建社交关系图谱 |
| `soul_enabled` | `false` | 是否启用情绪状态（实验性） |

<details>
<summary>📖 完整配置项参考（展开）</summary>

### 向量嵌入

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `embedding_model` | `"BAAI/bge-small-zh-v1.5"` | 本地模型名称或 API 模型名 |
| `embedding_api_url` | `""` | API 模式的端点地址 |
| `embedding_api_key` | `""` | API 密钥 |
| `embedding_batch_size` | `1` | 每批处理消息数 |
| `embedding_retry_max` | `3` | 失败重试次数 |

### 检索

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `retrieval_weighted_random` | `false` | 启用 Softmax 加权随机采样（替代确定性 Top-K） |
| `retrieval_sampling_temperature` | `1.0` | 采样温度（仅加权随机模式生效） |
| `retrieval_active_only` | `true` | 仅检索活跃事件，排除已归档 |
| `retrieval_recency_half_life_days` | `30.0` | 时间衰减半衰期（天） |

### 事件边界

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `boundary_max_messages` | `50` | 单事件消息数硬上限 |
| `boundary_max_duration_minutes` | `60` | 单事件时长硬上限（分钟） |
| `boundary_topic_drift_threshold` | `0.6` | 话题漂移触发阈值（余弦距离） |
| `boundary_topic_drift_min_messages` | `20` | 启动漂移检测所需最少消息数 |

### 社交关系

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `impression_update_alpha` | `0.4` | EMA 平滑系数（越大越快响应新数据） |
| `impression_event_trigger_threshold` | `5` | 共享事件数达到多少时触发印象更新 |
| `impression_aggregation_interval_hours` | `168` | 印象聚合频率（默认每周） |

### 记忆清理与衰减

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `decay_lambda` | `0.01` | 衰减速率（半衰期约 69 天） |
| `decay_archive_threshold` | `0.05` | 低于此显著度则归档 |
| `memory_cleanup_threshold` | `0.3` | 低于此显著度则永久删除 |
| `memory_cleanup_interval_days` | `7` | 清理任务执行频率（天） |
| `memory_cleanup_retention_days` | `30` | 归档事件在永久删除前的保留期（天） |

### Soul Layer（情绪状态）

| 配置键 | 默认值 | 说明 |
|--------|--------|------|
| `soul_decay_rate` | `0.1` | 每轮衰减比例（0.1 = 10%） |
| `soul_recall_depth_init` | `0.0` | 记忆检索驱动初始值（-20 ~ +20） |
| `soul_impression_depth_init` | `0.0` | 社交关注度初始值（-20 ~ +20） |
| `soul_expression_desire_init` | `0.0` | 表达欲初始值（-20 ~ +20） |
| `soul_creativity_init` | `0.0` | 创造力初始值（-20 ~ +20） |

</details>

---

## 🖥️ WebUI 页面说明

| 页面 | 路径 | 功能 |
|------|------|------|
| **事件流** | `/events` | 按时序浏览事件，支持搜索、标签过滤、内联编辑、回收站 |
| **关系图谱** | `/graph` | Cytoscape.js 交互式人际关系图，节点为人格，边为印象 |
| **叙事摘要** | `/summary` | 按群组与日期查看/编辑每日摘要（主要话题 · 事件列表 · 情绪动态） |
| **记忆检索** | `/recall` | 手动触发混合检索，查看命中事件与评分 |
| **数据库** | `/library` | 人格 · 人物事件 · 印象 · 标签 分标签浏览 |
| **统计** | `/stats` | 事件/人格数量、标签分布、活跃时序图、流水线性能 |
| **设置** | `/settings` | 主题 · 语言 · 密码 · 手动任务触发 |

> WebUI 采用双层认证：**登录**（密码存于 `data_dir/.webui_password`）+ **Sudo 提权**（写操作前需重新输入密码）。纯本地部署可设 `webui_auth_enabled: false` 跳过。

---

## 🛡️ 可靠性与已知局限

**可靠性保障：**
- 单文件持久化：SQLite WAL 模式 + 自动迁移前备份，语料库可单文件迁移
- 优雅降级：Embedding 模型不可用时自动降级为 BM25，不中断对话
- 故障隔离：社交图谱、摘要、Soul Layer 各自独立，一个失败不影响其他
- 二步确认：所有 `/mrm reset` 指令需 30 秒内二次确认，防止误操作

**已知局限：**

| 领域 | 说明 |
|------|------|
| 并行对话 | 同群内并行对话视为单一事件，无回复链解缠（v2 规划） |
| 事件层级 | 仅支持平铺结构，无嵌套事件（v2 规划） |
| 嵌入模型 | 本地模型针对中文优化，英文为主的部署建议配置 API 嵌入提供商 |
| 图谱规模 | 设计目标为消费级规模（< 500 节点），超大群组历史可能影响 UI 性能 |
| LLM 质量 | 话题标注、Big Five 评分、摘要质量取决于所配置 LLM 的能力 |
| Soul Layer | 实验性功能，极端参数下行为可能异常 |
| Token 上限 | 800 Token 注入为硬上限，高活跃群组中部分相关事件可能被截断 |

---

<details>
<summary>🔧 技术实现（开发者 / 高级用户）</summary>

### 架构总览

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

### LLM 调用预算

| 触发时机 | 任务 | 调用次数 |
|---------|------|---------|
| 每条消息（热路径） | 检索与注入 | **0** |
| 每个事件关闭 | 核心提取 | **1** |
| 每个事件（社交） | Big Five 评分 | **0**（命中统一提取）或 **1** |
| 每周 | 人格合成 | **每活跃用户 1 次** |
| 每日/每周 | 群组摘要 | **每活跃群组 ≤ 2 次** |
| 周期 | 印象聚合 | **0**（纯数学） |

### 社交关系推断公式（IPC 模型）

Big Five 评分（O/C/E/A/N）通过以下公式映射至 IPC 坐标：

```
亲和度 = 0.70 × 宜人性 + 0.35 × 外向性 − 0.20 × 神经质
权力感 = 0.70 × 外向性 + 0.35 × 尽责性 − 0.15 × 神经质
```

印象以 EMA（指数移动平均，α 可配置）方式更新，并归入八象限标签（亲和 / 活跃 / 掌控 / 高傲 / 冷淡 / 孤避 / 顺应 / 谦让）。

### 跨平台身份统一

所有实体通过内部稳定 `uid` 关联（而非平台 ID）。映射 `(platform, physical_id) → uid` 在适配器边界维护，支持同一用户跨平台账号合并。

</details>

---

## 致谢

参考实现：
- [LivingMemory](https://github.com/lxfight-s-Astrbot-Plugins/astrbot_plugin_livingmemory) — 反思阈值、时间衰减、混合检索 RRF
- [Memorix](https://github.com/exynos967/astrbot_plugin_memorix) — 范围路由、生命周期状态、图谱可视化
- [Scriptor](https://github.com/ysf7762-dev/astrbot_plugin_scriptor) — 身份统一、文件即记忆、睡眠整合
- MaiBot — chat_stream 作为一等公民概念
