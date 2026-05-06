# Implementation TODO

按优先级排列。每项包含：目标、涉及文件、关键接口/思路。

## P3 — ML Impression 生成器

**目标**：双轨制 Impression 更新——每次 event close 后 ML 快速更新，LLM 周期任务降频做深度校正。

### ML 聚合器

**新文件** `core/impression/ml_aggregator.py`：

```python
class MLImpressionAggregator:
    def fit_impression(self, observer_uid, subject_uid, scope,
                       events: list[Event], existing: Impression | None) -> Impression: ...
```

特征向量：`event_count`、`avg_salience`、`tag_sentiment`（内置情感词典）、`recency_score`、`interaction_frequency`。

降级：`scikit-learn` 未安装时自动回落到规则模式（event_count 阈值 + tag 关键词）。冷启动（event_count < 3）直接返回 `relation_type="stranger"`。

**新增配置项**：
```json
"impression_event_trigger_enabled": {"type": "bool", "default": true},
"impression_event_trigger_threshold": {"type": "int", "default": 5},
"impression_trigger_debounce_hours": {"type": "float", "default": 1.0}
```

触发逻辑：遍历 event.participants 中所有 (obs, subj) 对，检查 `last_reinforced_at` 距今是否超过 debounce，以及该 scope 下新事件数是否 ≥ threshold，满足则调用 `aggregator.fit_impression()` 并 upsert。
