# Implementation TODO

IPC 社交取向分析架构（Layer 2 + 3，Layer 1 不动）。
当前版本：v0.2.2。

Topic 以 tag 形式存储于 Event.chat_content_tags，不独立建模。
Event 表结构、EventExtractor 逻辑均不变。

---

## Phase A — 数据基础（Breaking 变更，优先）

### A-1: BigFiveVector 数据类型
**文件**: `core/domain/models.py`
```python
@dataclass(frozen=True)
class BigFiveVector:
    openness: float           # [-1, 1]
    conscientiousness: float
    extraversion: float
    agreeableness: float
    neuroticism: float
```

### A-2: Impression domain model 重构（Breaking Change）
**文件**: `core/domain/models.py`
- `relation_type: str` → `ipc_orientation: str`（8 种中文标签之一）
- `affect: float [-1,1]` → `benevolence: float [-1,1]`（改名，语义不变）
- `intensity: float [0,1]` → `affect_intensity: float [0,1]`（改名，语义变为 IPC 模长）
- 新增 `power: float [-1,1]`
- 新增 `r_squared: float [0,1]`
- 保留 `confidence: float [0,1]`
- 常量：`IPC_VALID_ORIENTATIONS = frozenset({"友好","主导友好","主导","主导敌意","敌意","服从敌意","服从","服从友好"})`

### A-3: 数据库迁移脚本
**新文件**: `migrations/005_ipc_impression.sql`
```sql
ALTER TABLE impressions RENAME COLUMN relation_type TO ipc_orientation;
ALTER TABLE impressions RENAME COLUMN affect TO benevolence;
ALTER TABLE impressions RENAME COLUMN intensity TO affect_intensity;
ALTER TABLE impressions ADD COLUMN power REAL NOT NULL DEFAULT 0.0;
ALTER TABLE impressions ADD COLUMN r_squared REAL NOT NULL DEFAULT 0.0;
-- 旧 relation_type 映射：
-- friend→友好, rival→敌意, stranger→友好(低置信), family→服从友好, colleague→主导友好
```
Event 表不做任何变更。

### A-4: SQLite Repository 更新
**文件**: `core/repository/sqlite.py`
- 更新 `_row_to_impression()` 读取新字段名
- 更新 impression 写入逻辑（power, r_squared 字段）
- 注册 005 migration 到 auto-migration runner

### A-5: InMemory Repository 同步
**文件**: `core/repository/memory.py`
- `InMemoryImpressionRepository` 同步字段变更

### A-6: Synthesis 兼容更新
**文件**: `core/tasks/synthesis.py`
- 替换 `_VALID_RELATIONS` → `IPC_VALID_ORIENTATIONS`
- 更新 impression aggregation LLM prompt 输出：`{"ipc_orientation": str, "benevolence": float, "power": float, "confidence": float}`
- 调用 `ipc_model.affect_intensity()` + `ipc_model.r_squared()` 计算衍生字段

### A-7: API 序列化更新
**文件**: `core/api.py`
- `impression_to_dict()` 输出：`ipc_orientation`, `benevolence`, `power`, `affect_intensity`, `r_squared`
- 移除旧字段：`relation_type`, `affect`, `intensity`

---

## Phase C — Layer 2: IPC + Big Five

### C-1: IPC 模型
**新文件**: `core/social/ipc_model.py`

8 中文标签 + 理论质心（单位圆 45° 间隔）：

| 标签      | θ    | B (cos θ) | P (sin θ) |
|-----------|------|-----------|-----------|
| 友好      | 0°   |  1.000    |  0.000    |
| 主导友好  | 45°  |  0.707    |  0.707    |
| 主导      | 90°  |  0.000    |  1.000    |
| 主导敌意  | 135° | -0.707    |  0.707    |
| 敌意      | 180° | -1.000    |  0.000    |
| 服从敌意  | 225° | -0.707    | -0.707    |
| 服从      | 270° |  0.000    | -1.000    |
| 服从友好  | 315° |  0.707    | -0.707    |

实现函数：
- `classify_octant(B, P) -> str`
- `affect_intensity(B, P) -> float`：`√(B²+P²) / √2`
- `r_squared(B, P) -> float`：`1 - d²/(r+ε)²`
- `bigfive_to_ipc(bfv: BigFiveVector) -> tuple[float, float]`
  - `benevolence ≈ 0.70×A + 0.35×E − 0.20×N`
  - `power ≈ 0.70×E + 0.35×C − 0.15×N`
  - 系数为近似值，实现前查阅 DeYoung 2013 附录精确数值

### C-2: BigFiveScorer 独立模块
**新文件**: `core/social/big_five_scorer.py`

```python
class BigFiveScorer(Protocol):
    """可替换接口：未来可接入 BERT 实现。"""
    async def score(self, context: str, provider) -> BigFiveVector: ...

class LLMBigFiveScorer:
    """Approach A：文本 → 单次 LLM → [O,C,E,A,N]。"""
    # system prompt: 分析发言者大五人格倾向，输出 {"O":f,"C":f,"E":f,"A":f,"N":f}，各维 -1 到 1
    async def score(self, context: str, provider) -> BigFiveVector: ...
```

### C-3: BigFiveBuffer
**文件**: `core/social/big_five_scorer.py`
- per-session per-user 消息计数 + `BigFiveVector` 缓存
- 消息数达 `bigfive_x_messages`（默认 10）→ 后台异步触发评分 → 更新缓存
- 失败 fallback：零向量，不阻断主流程
- session 过期时清理（与 ContextManager LRU 对齐）

### C-4: SocialOrientationAnalyzer
**新文件**: `core/social/orientation_analyzer.py`

Event 粒度聚合，per (observer_uid, subject_uid) pair：
- 对 window 中每条 obs→subj 消息：从 BigFive cache 取 `BigFiveVector` → `bigfive_to_ipc()` → `(B_msg, P_msg)`
- 均值：`(B_e, P_e) = Σ(B_msg × salience_msg) / Σ(salience_msg)`
- 输出：`ipc_orientation`, `benevolence`, `power`, `affect_intensity`, `r_squared`

### C-5: EventExtractor 集成
**文件**: `core/extractor/extractor.py`
- event close 后台任务中调用 `SocialOrientationAnalyzer.analyze(window, big_five_buffer)`
- 对 event.participants 所有 (obs, subj) pair → upsert Impression（新 IPC 字段）

### C-6: 配置项新增
**文件**: `core/config.py` + `_conf_schema.json`
```json
"ipc_enabled": {"type": "bool", "default": true},
"bigfive_x_messages": {"type": "int", "default": 10}
```

---

## Phase D — 整合与测试

### D-1: Synthesis 深度更新（Weekly LLM 校正）
**文件**: `core/tasks/synthesis.py`
- `run_impression_aggregation`：LLM prompt 输出 IPC 字段
- 调用 `ipc_model` 计算所有衍生字段

### D-2: MarkdownProjector 更新
**文件**: `core/projector/projector.py` + templates
- IMPRESSIONS.md 展示 `ipc_orientation` + 坐标 `(B: +0.65, P: +0.32)`

### D-3: 测试套件
- `tests/test_ipc_model.py`：8 标准点；R²=1 在质心；affect_intensity(1,0)=1/√2
- `tests/test_big_five_scorer.py`：LLM stub → agreeableness > 0 → benevolence > 0
- `tests/test_orientation_analyzer.py`：Event 层聚合数学验证
- `tests/test_repositories.py`（更新）：Impression 新字段读写

---

## Phase E — 前端可视化与 Bug 修复

### E-1: 关系图 IPC 可视化控制
**文件**: `web/frontend/app/graph/page.tsx`
- 右侧控制面板新增：
  - 边标签开关（显示/隐藏 `ipc_orientation` 文字）
  - 边颜色模式选择：`关系类型`（8 色映射）/ `强度`（affect_intensity 蓝→红渐变）
  - 边粗细开关（是否与 `affect_intensity` 正相关）

### E-2: i18n 更新
**文件**: `web/frontend/lib/i18n.ts`
- IPC 8 种中文标签常量 + 控制面板 UI 字符串

### E-3: 数据库页面批量删除
- 列表 checkbox 多选 + 删除选中（sudo）+ 一键全删（sudo + 二次确认）

### E-4: 数据库页面跳转导航
- 列表行点击跳详情；关系图节点 → Library Persona 记录

### E-5: 事件流密度滑条间距调节
**文件**: `web/frontend/components/events/event-timeline.tsx`
- density slider 同时控制：过滤事件数量 + 气泡上下间距（`gap` CSS 变量）

### E-6: 依赖关系 UI 同步 Bug 修复
- 编辑 `inherit_from` 后触发 Timeline 重渲染

### E-7: 跨群依赖限制
**文件**: `web/frontend/components/events/event-dialogs.tsx`
- `EventInheritPicker` 候选过滤：仅同 `group_id` 的事件

---

## 遗留待确认

- [ ] IPC 旋转系数精确数值：查阅 DeYoung 2013 / Markey 2013 附录
- [ ] BigFive LLM prompt 稳定性：实现前做 3–5 次同输入方差评估
