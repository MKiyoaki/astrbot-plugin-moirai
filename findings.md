# 研究发现

## ipc_orientation 字段现状

### 两条写入路径

| 路径 | 来源 | 当前格式 | 示例 |
|------|------|----------|------|
| `orientation_analyzer` → `classify_octant` | Big Five → IPC 几何计算 | 硬编码中文 | `"亲和"`, `"掌控"` |
| LLM extractor prompt | LLM 自由输出 | 中文约束但未强制 | `"友好"`, `"友谊"` 等 |

### 问题
- 两条路径写同一字段 `Impression.ipc_orientation`，格式不统一
- `classify_octant` 在 `ipc_model.py` 返回硬编码中文字符串
- `config.py` 的 LLM prompt 约束中文列表（亲和/活跃/掌控/高傲/冷淡/孤避/顺应/谦让），但 LLM 可能输出任意变体
- 前端直接显示原始字符串，i18n 无效

### 定义的八象限及拟定 key 映射

| 中文 | 英文 key | 角度 |
|------|----------|------|
| 亲和 | `affinity` | 0° |
| 活跃 | `active` | 45° |
| 掌控 | `dominant` | 90° |
| 高傲 | `arrogant` | 135° |
| 冷淡 | `cold` | 180° |
| 孤避 | `withdrawn` | 225° |
| 顺应 | `submissive` | 270° |
| 谦让 | `deferential` | 315° |

### 影响范围

**后端**
- `core/social/ipc_model.py` — `_OCTANTS` label + `classify_octant` 返回值
- `core/config.py` — LLM prompt 约束列表（3处，含 group mood）
- `core/utils/i18n.py` — 后端 projector 模板的 `ipc_orientation` 字段标签（已有，需补八象限 key 翻译）
- `core/projector/templates/persona_impressions.md.j2` — 显示 `imp.ipc_orientation`（需通过 i18n filter 翻译）
- `core/tasks/summary.py:121` — `label = imp.ipc_orientation`（用于摘要文本）

**测试（需更新中文值）**
- `tests/test_summary_mood.py` — `"活跃"`, `"掌控"`, `"亲和"`
- `tests/test_sync.py` — `"友好"`, `"服从"`, `"敌意"`（这些是自由文本，不是八象限值）
- `tests/test_projector.py` — `"友好"`, `"支配友好"`
- `tests/test_sqlite_repo.py`, `test_memory_repo.py`, `test_domain.py` — `"友好"`
- `tests/test_graph_scope.py` — `"friend"`（英文，已与新方案接近）

**前端**
- `web/frontend/lib/api.ts` — `ImpressionEdge.data.label: string`（类型不变）
- `web/frontend/lib/i18n.ts` — 需新增 `ipc.affinity` 等8个 key 的翻译
- `web/frontend/components/graph/network-graph.tsx` — 边标签显示，需通过 i18n 翻译 key
- `web/frontend/components/graph/node-detail.tsx` — 可能显示 orientation

**迁移**
- `migrations/` — 新建 `010_normalize_ipc_orientation.sql`
- 映射表：已知中文值 + 常见 LLM 变体 → 英文 key
- 未知值 fallback → `"affinity"`（友好默认）

### 迁移映射表（中文/变体 → key）

```sql
CASE ipc_orientation
  WHEN '亲和' THEN 'affinity'    WHEN '友好' THEN 'affinity'
  WHEN '活跃' THEN 'active'      WHEN '积极' THEN 'active'
  WHEN '掌控' THEN 'dominant'    WHEN '支配' THEN 'dominant'   WHEN '掌控友好' THEN 'dominant'
  WHEN '高傲' THEN 'arrogant'    WHEN '傲慢' THEN 'arrogant'
  WHEN '冷淡' THEN 'cold'        WHEN '疏远' THEN 'cold'       WHEN '敌意' THEN 'cold'
  WHEN '孤避' THEN 'withdrawn'   WHEN '孤立' THEN 'withdrawn'
  WHEN '顺应' THEN 'submissive'  WHEN '服从' THEN 'submissive' WHEN '顺从' THEN 'submissive'
  WHEN '谦让' THEN 'deferential' WHEN '谦逊' THEN 'deferential'
  WHEN 'friend' THEN 'affinity'  WHEN 'friendly' THEN 'affinity'
  WHEN 'rival' THEN 'cold'       WHEN 'family' THEN 'affinity'
  WHEN 'stranger' THEN 'cold'
  ELSE 'affinity'  -- unknown fallback
END
```
