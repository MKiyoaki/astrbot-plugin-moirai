# Core 记忆上下文读取

Moirai 通过现有 Core 扩展提供方额外发布只读能力 `moirai.chat_memory.recall`。此能力只读取现有聊天 `events` 的历史事实；Moirai 独立运行时原有的事件处理、召回注入和 WebUI 不依赖调用者。它不导入 Oedipus，也不计算 DIAMONDS 或决定角色行为。

## 请求与权限

Core 的请求 broker 必须先确认该能力已声明、调用身份已认证，以及请求包含具体运行人格和 `extension_scopes.moirai`。Moirai 再要求身份具有 `moirai.chat_memory.read` 权限，并把 Moirai scope 映射到已显式配置的旧人格数据桶。缺失映射直接拒绝，不进行全人格召回。

请求的 `payload` 恰好包含 `query`、`scope_mode`、`group_id`。`query` 是非空当前文本；`scope_mode` 为 `private` 或 `group`；私聊的 `group_id` 为 `null`，群聊则为非空群组 ID。调用方必须从可信宿主事件取得会话范围，不能根据浏览器选择推断。服务未初始化、Core 不可用、无权限、作用域错误和查询失败分别返回标准提供方错误。

## 响应

成功响应沿用 Core 的 `request_id`、`resolved_scope` 与操作名，`data` 为：

```json
{
  "schema_version": "conversation-context.v1",
  "source_kind": "conversation",
  "events": [{
    "event_id": "source-event-id",
    "topic": "历史话题",
    "factual_summary": "已发生的事实",
    "start_time": 0.0,
    "end_time": 0.0
  }]
}
```

这是结构示例，不是实际对话记录。结果沿用 Moirai 当前混合召回的顺序和配置的事件数量上限，按人格及私聊/群聊范围检索。`factual_summary` 调用现有 `strip_evals()` 移除主观 `[Eval]` 旁白；只剩空内容的事件不会返回。该 `conversation-context.v1` 结果与 Core 的作用域中转信封是两层独立契约。此接口不返回数据库对象、原始消息、提示词块或心理情境分数，不产生额外 LLM 调用。

## 集成边界

Core 负责把只读结果中转给已授权的消费方，不保存业务内容。消费方自行决定如何使用事实；Oedipus 可以选择把历史事实纳入当前情境判断，也可以完全不安装 Moirai。Event Protocol 的文本注入继续独立工作。若同一轮同时需要文本注入与结构化上下文，需在 Core 编排时验证只召回一次；当前提供方接口本身不承诺这一优化，也不承诺已在正式 AstrBot 回合接通。

## 与原作剧情记忆的边界

规划中的 canon 原作剧情记忆属于另一个数据域：独立 `canon.sqlite`、剧情 `line_key` 证据、角色获知渠道与叙事时间点，并通过单独的 `canon` Event Protocol 注入块及 token 预算进入提示词。当前能力不检索 canon，不读其数据库，也不把 canon 事件混入聊天 `events` 或同一个召回上限。聊天事件 ID 不能冒充 canon 证据行。canon 尚未实现；本接口不能替代它。

如果以后需要让 Oedipus 在情境判断中使用 canon，应另定义可选的结构化 canon 查询，保留来源、获知渠道、角色与时间点过滤。Core 只中转有作用域的结果；canon 的提示词注入仍由 Moirai 的 `canon` 块负责，消费方不能再次渲染同一段剧情内容造成重复注入。
