"""Backend i18n support for Moirai."""
from __future__ import annotations

from typing import Dict, Any

# Supported languages
LANG_ZH = "zh-CN"
LANG_EN = "en-US"
LANG_JA = "ja-JP"

_STRINGS: Dict[str, Dict[str, str]] = {
    LANG_ZH: {
        # Extractor (prompts stay Chinese, but we might use these for fallback/labels)
        "extractor.user_prompt_header": "[Bot 视角人格] {desc}\n注意：请在 summary 每个小话题三元组末尾加上 [Eval] 字段，以上述人格视角对该话题做一句话评价。",
        "extractor.tags_header": "[现有标签体系] {tags}\n注意：chat_content_tags 请优先从上述现有标签中选择。只有在现有标签均不适用时，才创建更宏观、抽象的新标签。",
        "extractor.conversation_record": "对话记录（共{count}条消息，时间跨度约{duration}分钟）：",
        "extractor.semantic_record": "以下是一组语义高度相关的对话记录（共{count}条）：",
        "extractor.distillation_json_instruction": "\n请为这段对话提炼结构化信息，输出单个 JSON 对象，包含以下字段：\n"
                                                  '{"topic": "核心主题(≤30字)", "summary": "摘要", '
                                                  '"chat_content_tags": ["标签1", "标签2"], "salience": 0.5, "confidence": 0.8, "inherit": false, '
                                                  '"participants_personality": {"Alice": {"O": 0.6, "C": 0.5, "E": 0.7, "A": 0.4, "N": -0.2}}}',
        "extractor.default_user_name": "用户",
        "extractor.topic_placeholder": "核心主题(≤30字)",
        "extractor.fallback_summary": "聚合了 {count} 条相关消息。",
        "extractor.distill_failed": "提炼失败，原始消息：{text}...",

        # Summary task
        "summary.no_events": "（暂无事件）",
        "summary.untitled_topic": "未命名话题",
        "summary.topic_shift": "*在{sender}发出「{preview}」后话题转向了",
        "summary.position_unknown": "[{names}位置尚未确定]",
        "summary.position_known": "[{names}处于群体中的{label}位置]",
        "summary.mood_overall": "群体情感动态整体偏向[{orientation}] | [平均亲和度：{b}；平均支配度：{p}] | ",
        "summary.mood_failed": "（情感动态生成失败）",
        "summary.private_chat": "私聊",
        "summary.word_limit_hint": "请生成主要话题摘要。",
        "summary.timeout": "（生成超时）",
        "summary.failed": "（生成失败）",
        "summary.header": "# {label} 活动摘要 — {date} {start} - {end}",
        "summary.section_topic": "[主要话题]",
        "summary.section_events": "[事件列表]",
        "summary.section_mood": "[情感动态]",

        # Config hints (for future i18n of _conf_schema.json)
        "config.retrieval_weighted_random.hint": "开启后将使用 Softmax 采样替代确定性 Top-K 截断，使记忆表现更自然（偶尔想起低分事件）",
        "config.retrieval_sampling_temperature.hint": "仅在加权随机模式下生效。1.0 为标准采样，数值越低越接近确定性排名，数值越高随机性越强。",

        # Projector / Markdown
        "projector.bot_persona_title": "# Bot 身份档案",
        "projector.bot_persona_desc": "> 本文件记录机器人自身的 Persona 信息，由插件自动生成。",
        "projector.base_info": "## 基本信息",
        "projector.field": "字段",
        "projector.value": "值",
        "projector.name": "名称",
        "projector.confidence": "置信度",
        "projector.created_at": "创建时间",
        "projector.last_active": "最后活跃",
        "projector.bindings": "## 绑定身份",
        "projector.no_bindings": "暂无绑定身份",
        "projector.attrs": "## 属性",
        "projector.no_attrs": "暂无属性记录",
        "projector.impression_title": "# {name} 的印象记录",
        "projector.impression_desc": "> 本文件可由用户手动编辑，修改将在下次同步时写回数据库（Phase 10）。",
        "projector.impression_from": "## 来自 `{observer}` 的印象（范围：{scope}）",
        "projector.ipc_orientation": "社交取向",
        "projector.benevolence": "亲和度",
        "projector.power": "支配度",
        "projector.intensity": "情感强度",
        "projector.r_squared": "拟合优度",
        "projector.last_reinforced": "最近强化",
        "projector.evidence": "**依据事件：** ",
        "projector.no_impressions": "暂无印象记录",
        "projector.profile_desc": "> 本文件由插件自动生成，请勿直接编辑。如需修改印象记录，请编辑同目录下的 IMPRESSIONS.md。",
        "projector.uid": "内部 UID",
        "projector.platform": "平台",
        "projector.physical_id": "物理 ID",
        "projector.personal_attrs": "## 个人属性",
        "projector.recent_events": "## 近期参与事件（最近 {count} 条）",
        "projector.no_events": "暂无事件记录",
        "projector.affect_positive": "正面（{value:+.2f}）",
        "projector.affect_negative": "负面（{value:+.2f}）",
        "projector.affect_neutral": "中性（{value:+.2f}）",

        # IPC Labels
        "ipc.亲和": "亲和",
        "ipc.活跃": "活跃",
        "ipc.掌控": "掌控",
        "ipc.高傲": "高傲",
        "ipc.冷淡": "冷淡",
        "ipc.孤避": "孤避",
        "ipc.顺应": "顺应",
        "ipc.谦让": "谦让",
        "ipc.unknown": "未知",
        "ipc.未知": "未知",

        # Formatter
        "formatter.minutes_ago": "{count}分钟前",
        "formatter.hours_ago": "{count}小时前",
        "formatter.days_ago": "{count}天前",
        "formatter.recall_header": "## 相关历史记忆\n",

        # Command manager responses
        "cmd.not_init": "插件未初始化。",
        "cmd.status.header": "【Moirai 插件状态】",
        "cmd.status.tasks": "已注册任务：{tasks}",
        "cmd.status.tasks_none": "无",
        "cmd.status.sessions": "活跃会话数：{count}",
        "cmd.status.webui_running": "运行中",
        "cmd.status.webui_stopped": "未运行",
        "cmd.status.webui": "WebUI：{status}",
        "cmd.status.memory": "记忆 event：{events} 条 | 人格：{personas} 个 | 印象：{impressions} 条",
        "cmd.status.avg_response": "平均响应时间：{ms}ms",
        "cmd.status.window": "当前会话进度：{current}/{total} 轮（已累积 {msgs} 条消息）",
        "cmd.status.window_none": "当前会话暂无对话记录",
        "cmd.persona.header": "【人格档案】{name}（{id}）",
        "cmd.persona.description": "描述：{desc}",
        "cmd.persona.bigfive_header": "大五人格：",
        "cmd.persona.bigfive_dim": "  {label} {pct}%",
        "cmd.persona.bigfive_dim_ev": "  {label} {pct}%：{ev}",
        "cmd.persona.tags": "标签：{tags}",
        "cmd.persona.confidence": "置信度：{pct}%",
        "cmd.persona.not_found": "未找到平台 {platform} 上 ID 为 {id} 的人格档案。",
        "cmd.persona.no_repo": "人格仓库未加载。",
        "cmd.soul.header": "【当前会话情绪状态】",
        "cmd.soul.neutral": "当前会话情绪状态：中立（无偏移）",
        "cmd.soul.recall_depth": "记忆检索驱动：{val}",
        "cmd.soul.impression_depth": "社交关注度：{val}",
        "cmd.soul.expression_desire": "表达欲：{val}",
        "cmd.soul.creativity": "创意度：{val}",
        "cmd.soul.level_high": "偏高",
        "cmd.soul.level_low": "偏低",
        "cmd.soul.level_neutral": "中立",
        "cmd.recall.not_found": "未找到与「{query}」相关的记忆。",
        "cmd.task.triggered": "任务 '{task}' 已触发执行。",
        "cmd.task.not_found": "未找到任务 '{task}'。可用任务：{available}",
        "cmd.flush.no_ctx": "上下文管理器未启用。",
        "cmd.flush.no_window": "当前会话无活跃上下文窗口。",
        "cmd.flush.done": "已清空当前会话窗口（{count} 条消息）。",
        "cmd.webui.not_loaded": "WebUI 模块未加载。",
        "cmd.webui.started": "WebUI 已启动：http://{host}:{port}",
        "cmd.webui.start_failed": "WebUI 启动失败：{error}",
        "cmd.webui.stopped": "WebUI 已关闭。",
        "cmd.webui.stop_failed": "WebUI 关闭失败：{error}",
        "cmd.webui.usage": "用法：/mrm webui on | off",
        "cmd.reset.confirm_warn": "⚠️ 此操作将{desc}。\n确认请在 {ttl} 秒内再次发送相同命令。",
        "cmd.reset.no_event_repo": "事件仓库未加载。",
        "cmd.reset.no_persona_repo": "人格仓库未加载。",
        "cmd.reset.no_repo": "仓库未完全加载，无法执行全量重置。",
        "cmd.reset.here_done": "已删除本群 {count} 条事件记录",
        "cmd.reset.summary_suffix": "{count} 个摘要文件",
        "cmd.reset.event_group_done": "已删除群组 {gid} 的 {count} 条事件记录",
        "cmd.reset.event_all_done": "已删除全部 {count} 条事件记录。",
        "cmd.reset.persona_not_found": "未找到平台 {platform} 上 ID 为 {id} 的人格档案。",
        "cmd.reset.persona_one_done": "已删除 {name}（{id}）的人格档案。",
        "cmd.reset.persona_all_done": "已删除全部 {count} 个人格档案。",
        "cmd.reset.all_done": "已清空全部插件数据：{ev_count} 条事件、{p_count} 个人格档案及所有投影文件。",
        "cmd.reset.usage": "用法：/mrm reset here | event <group_id|all> | persona <PlatID|all> | all",
        "cmd.reset.event_usage": "用法：/mrm reset event <group_id> | all",
        "cmd.reset.persona_usage": "用法：/mrm reset persona <PlatID> | all",
        "cmd.reset.desc_here": "删除{scope}所有事件记录与摘要文件，且不可恢复",
        "cmd.reset.desc_event_group": "删除群组 {gid} 所有事件记录与摘要文件，且不可恢复",
        "cmd.reset.desc_event_all": "删除所有事件记录，且不可恢复",
        "cmd.reset.desc_persona_one": "删除用户 {id} 的人格数据，且不可恢复",
        "cmd.reset.desc_persona_all": "删除全部人格数据，且不可恢复",
        "cmd.reset.desc_all": "清空全部插件数据（事件、人格、摘要文件），此操作完全不可逆",
        "cmd.reset.scope_group": "群组 {gid}",
        "cmd.reset.scope_private": "私聊",
        "cmd.lang.set": "语言已切换为：{lang}",
        "cmd.lang.invalid": "不支持的语言代码。可选：cn（中文）/ en（English）/ ja（日本語）",
        "cmd.dep.usage": "用法：/mrm dep install <sentence-transformers|scikit-learn>",
        "cmd.dep.installing": "正在安装 {lib}... 这可能需要几分钟，请稍候。",
        "cmd.dep.installed": "✅ {lib} 安装成功！请重启插件以启用相关功能。",
        "cmd.dep.failed": "❌ {lib} 安装失败：{error}",
        "cmd.dep.invalid": "不支持的依赖包。可选：sentence-transformers, scikit-learn",
        "cmd.init.header": "【Moirai 初始化成功】",
        "cmd.init.module": " - {name}: {status}",
        "cmd.init.model": " - {name}模型: {model}",
        "cmd.init.active": "已启用",
        "cmd.init.inactive": "未启用",
        "cmd.init.none": "无",
        "cmd.help.full": (
            "【Moirai 指令帮助】\n"
            "--- 信息查询 ---\n"
            "/mrm status               - 查询插件运行状态\n"
            "/mrm persona <PlatID>     - 查看用户人格档案 + 大五人格\n"
            "/mrm soul                 - 查看当前会话情绪状态\n"
            "/mrm recall <关键词>      - 手动触发记忆检索\n"
            "--- 操作 ---\n"
            "/mrm webui on|off         - 启动或关闭 WebUI\n"
            "/mrm flush                - 清空当前会话上下文窗口（不删数据库）\n"
            "/mrm run <task>           - 手动触发后台任务 (decay/synthesis/summary/cleanup)\n"
            "/mrm language <cn/en/ja>  - 切换指令显示语言\n"
            "/mrm dep install <lib>    - 安装可选依赖 (sentence-transformers/scikit-learn)\n"
            "--- 重置（均需二次确认）⚠️ ---\n"
            "/mrm reset here           - 删除当前群所有事件与摘要\n"
            "/mrm reset event <gid>    - 删除指定群组的事件与摘要\n"
            "/mrm reset event all      - 删除所有事件记录\n"
            "/mrm reset persona <id>   - 删除指定用户的人格档案\n"
            "/mrm reset persona all    - 删除全部人格数据\n"
            "/mrm reset all            - 清空全部插件数据\n"
            "--- 其他 ---\n"
            "/mrm help                 - 显示此帮助信息"
        ),
    },
    LANG_EN: {
        # Extractor
        "extractor.user_prompt_header": "[Bot Persona] {desc}\nNote: Please add an [Eval] field at the end of each summary triplet, providing a one-sentence evaluation of the topic from the persona's perspective.",
        "extractor.tags_header": "[Existing Tags] {tags}\nNote: Please prioritize selecting chat_content_tags from the existing tags above. Only create new, more macro and abstract tags if none of the existing ones are applicable.",
        "extractor.conversation_record": "Conversation record ({count} messages, spanning approx {duration} minutes):",
        "extractor.semantic_record": "The following is a group of semantically highly related conversation records ({count} messages):",
        "extractor.distillation_json_instruction": "\nPlease refine the structured information for this conversation and output a single JSON object containing the following fields:\n"
                                                  '{"topic": "Core Topic(≤30 chars)", "summary": "Summary", '
                                                  '"chat_content_tags": ["tag1", "tag2"], "salience": 0.5, "confidence": 0.8, "inherit": false, '
                                                  '"participants_personality": {"Alice": {"O": 0.6, "C": 0.5, "E": 0.7, "A": 0.4, "N": -0.2}}}',
        "extractor.default_user_name": "User",
        "extractor.topic_placeholder": "Core Topic(≤30 chars)",
        "extractor.fallback_summary": "Aggregated {count} related messages.",
        "extractor.distill_failed": "Distillation failed, raw message: {text}...",

        # Summary task
        "summary.no_events": "(No events)",
        "summary.untitled_topic": "Untitled Topic",
        "summary.topic_shift": "*After {sender} sent \"{preview}\", the topic shifted to",
        "summary.position_unknown": "[{names} position not yet determined]",
        "summary.position_known": "[{names} is in the {label} position within the group]",
        "summary.mood_overall": "Group emotional dynamics overall lean towards [{orientation}] | [Avg Benevolence: {b}; Avg Power: {p}] | ",
        "summary.mood_failed": "(Failed to generate emotional dynamics)",
        "summary.private_chat": "Private",
        "summary.word_limit_hint": "Please generate a summary of the main topics.",
        "summary.timeout": "(Generation timed out)",
        "summary.failed": "(Generation failed)",
        "summary.header": "# {label} Activity Summary — {date} {start} - {end}",
        "summary.section_topic": "[Main Topics]",
        "summary.section_events": "[Event List]",
        "summary.section_mood": "[Mood Dynamics]",

        # Config hints (for future i18n of _conf_schema.json)
        "config.retrieval_weighted_random.hint": "When enabled, use Softmax sampling instead of deterministic Top-K truncation to make memory more natural (occasionally recalling lower-score events).",
        "config.retrieval_sampling_temperature.hint": "Only effective in weighted random mode. 1.0 is standard; lower values approach deterministic ranking, higher values increase randomness.",

        # Projector / Markdown
        "projector.bot_persona_title": "# Bot Identity Profile",
        "projector.bot_persona_desc": "> This file records the bot's own persona information, automatically generated by the plugin.",
        "projector.base_info": "## Basic Information",
        "projector.field": "Field",
        "projector.value": "Value",
        "projector.name": "Name",
        "projector.confidence": "Confidence",
        "projector.created_at": "Created At",
        "projector.last_active": "Last Active",
        "projector.bindings": "## Bound Identities",
        "projector.no_bindings": "No bound identities",
        "projector.attrs": "## Attributes",
        "projector.no_attrs": "No attribute records",
        "projector.impression_title": "# Impression Records for {name}",
        "projector.impression_desc": "> This file can be manually edited by the user, and changes will be synced back to the database in Phase 10.",
        "projector.impression_from": "## Impression from `{observer}` (Scope: {scope})",
        "projector.ipc_orientation": "Social Orientation",
        "projector.benevolence": "Benevolence",
        "projector.power": "Power",
        "projector.intensity": "Affect Intensity",
        "projector.r_squared": "Goodness of Fit",
        "projector.last_reinforced": "Last Reinforced",
        "projector.evidence": "**Evidence Events:** ",
        "projector.no_impressions": "No impression records",
        "projector.profile_desc": "> This file is automatically generated by the plugin, please do not edit directly. To modify impression records, please edit IMPRESSIONS.md in the same directory.",
        "projector.uid": "Internal UID",
        "projector.platform": "Platform",
        "projector.physical_id": "Physical ID",
        "projector.personal_attrs": "## Personal Attributes",
        "projector.recent_events": "## Recent Events (Last {count})",
        "projector.no_events": "No event records",
        "projector.affect_positive": "Positive ({value:+.2f})",
        "projector.affect_negative": "Negative ({value:+.2f})",
        "projector.affect_neutral": "Neutral ({value:+.2f})",

        # IPC Labels
        "ipc.亲和": "Friendly",
        "ipc.活跃": "Outgoing",
        "ipc.掌控": "Dominant",
        "ipc.高傲": "Arrogant",
        "ipc.冷淡": "Cold",
        "ipc.孤避": "Withdrawn",
        "ipc.顺应": "Submissive",
        "ipc.谦让": "Humble",
        "ipc.未知": "Unknown",

        # Formatter
        "formatter.minutes_ago": "{count} min ago",
        "formatter.hours_ago": "{count} hours ago",
        "formatter.days_ago": "{count} days ago",
        "formatter.recall_header": "## Related Historical Memories\n",

        # Command manager responses
        "cmd.not_init": "Plugin not initialized.",
        "cmd.status.header": "【Moirai Plugin Status】",
        "cmd.status.tasks": "Registered tasks: {tasks}",
        "cmd.status.tasks_none": "none",
        "cmd.status.sessions": "Active sessions: {count}",
        "cmd.status.webui_running": "Running",
        "cmd.status.webui_stopped": "Stopped",
        "cmd.status.webui": "WebUI: {status}",
        "cmd.status.memory": "Memory events: {events} | Personas: {personas} | Impressions: {impressions}",
        "cmd.status.avg_response": "Avg response time: {ms}ms",
        "cmd.status.window": "Session progress: {current}/{total} rounds ({msgs} messages accumulated)",
        "cmd.status.window_none": "No conversation recorded in this session yet",
        "cmd.persona.header": "【Persona Profile】{name} ({id})",
        "cmd.persona.description": "Description: {desc}",
        "cmd.persona.bigfive_header": "Big Five:",
        "cmd.persona.bigfive_dim": "  {label} {pct}%",
        "cmd.persona.bigfive_dim_ev": "  {label} {pct}%: {ev}",
        "cmd.persona.tags": "Tags: {tags}",
        "cmd.persona.confidence": "Confidence: {pct}%",
        "cmd.persona.not_found": "No persona found for ID {id} on platform {platform}.",
        "cmd.persona.no_repo": "Persona repository not loaded.",
        "cmd.soul.header": "【Current Session Mood State】",
        "cmd.soul.neutral": "Current session mood: Neutral (no deviation)",
        "cmd.soul.recall_depth": "Recall Drive: {val}",
        "cmd.soul.impression_depth": "Social Attention: {val}",
        "cmd.soul.expression_desire": "Expression Desire: {val}",
        "cmd.soul.creativity": "Creativity: {val}",
        "cmd.soul.level_high": "High",
        "cmd.soul.level_low": "Low",
        "cmd.soul.level_neutral": "Neutral",
        "cmd.recall.not_found": "No memories found related to \"{query}\".",
        "cmd.task.triggered": "Task '{task}' has been triggered.",
        "cmd.task.not_found": "Task '{task}' not found. Available: {available}",
        "cmd.flush.no_ctx": "Context manager is not enabled.",
        "cmd.flush.no_window": "No active context window for this session.",
        "cmd.flush.done": "Session window cleared ({count} messages).",
        "cmd.webui.not_loaded": "WebUI module not loaded.",
        "cmd.webui.started": "WebUI started: http://{host}:{port}",
        "cmd.webui.start_failed": "WebUI failed to start: {error}",
        "cmd.webui.stopped": "WebUI stopped.",
        "cmd.webui.stop_failed": "WebUI failed to stop: {error}",
        "cmd.webui.usage": "Usage: /mrm webui on | off",
        "cmd.reset.confirm_warn": "⚠️ This will {desc}.\nTo confirm, send the same command again within {ttl} seconds.",
        "cmd.reset.no_event_repo": "Event repository not loaded.",
        "cmd.reset.no_persona_repo": "Persona repository not loaded.",
        "cmd.reset.no_repo": "Repositories not fully loaded. Cannot perform full reset.",
        "cmd.reset.here_done": "Deleted {count} events from this group",
        "cmd.reset.summary_suffix": "{count} summary file(s)",
        "cmd.reset.event_group_done": "Deleted {count} events from group {gid}",
        "cmd.reset.event_all_done": "Deleted all {count} event records.",
        "cmd.reset.persona_not_found": "No persona found for ID {id} on platform {platform}.",
        "cmd.reset.persona_one_done": "Deleted persona for {name} ({id}).",
        "cmd.reset.persona_all_done": "Deleted all {count} persona records.",
        "cmd.reset.all_done": "All plugin data cleared: {ev_count} events, {p_count} personas, and all projection files.",
        "cmd.reset.usage": "Usage: /mrm reset here | event <group_id|all> | persona <PlatID|all> | all",
        "cmd.reset.event_usage": "Usage: /mrm reset event <group_id> | all",
        "cmd.reset.persona_usage": "Usage: /mrm reset persona <PlatID> | all",
        "cmd.reset.desc_here": "delete all events and summaries for {scope} — irreversible",
        "cmd.reset.desc_event_group": "delete all events and summaries for group {gid} — irreversible",
        "cmd.reset.desc_event_all": "delete ALL event records — irreversible",
        "cmd.reset.desc_persona_one": "delete persona data for user {id} — irreversible",
        "cmd.reset.desc_persona_all": "delete ALL persona data — irreversible",
        "cmd.reset.desc_all": "wipe ALL plugin data (events, personas, projection files) — completely irreversible",
        "cmd.reset.scope_group": "group {gid}",
        "cmd.reset.scope_private": "private chat",
        "cmd.lang.set": "Language switched to: {lang}",
        "cmd.lang.invalid": "Unsupported language code. Options: cn (Chinese) / en (English) / ja (Japanese)",
        "cmd.dep.usage": "Usage: /mrm dep install <sentence-transformers|scikit-learn>",
        "cmd.dep.installing": "Installing {lib}... This may take a few minutes, please wait.",
        "cmd.dep.installed": "✅ {lib} installed successfully! Please restart the plugin to enable related features.",
        "cmd.dep.failed": "❌ {lib} installation failed: {error}",
        "cmd.dep.invalid": "Unsupported dependency. Options: sentence-transformers, scikit-learn",
        "cmd.init.header": "【Moirai Initialized Successfully】",
        "cmd.init.module": " - {name}: {status}",
        "cmd.init.model": " - {name} Model: {model}",
        "cmd.init.active": "Active",
        "cmd.init.inactive": "Inactive",
        "cmd.init.none": "None",
        "cmd.help.full": (
            "【Moirai Command Help】\n"
            "--- Info ---\n"
            "/mrm status               - Plugin running status\n"
            "/mrm persona <PlatID>     - User persona profile + Big Five\n"
            "/mrm soul                 - Current session mood state\n"
            "/mrm recall <keywords>    - Manual memory retrieval\n"
            "--- Actions ---\n"
            "/mrm webui on|off         - Start or stop WebUI\n"
            "/mrm flush                - Clear session context window (DB intact)\n"
            "/mrm run <task>           - Trigger background task (decay/synthesis/summary/cleanup)\n"
            "/mrm language <cn/en/ja>  - Switch command display language\n"
            "/mrm dep install <lib>    - Install optional dependency (sentence-transformers/scikit-learn)\n"
            "--- Reset (2-step confirm required) ⚠️ ---\n"
            "/mrm reset here           - Delete current group events & summaries\n"
            "/mrm reset event <gid>    - Delete specified group events & summaries\n"
            "/mrm reset event all      - Delete all event records\n"
            "/mrm reset persona <id>   - Delete specified user's persona\n"
            "/mrm reset persona all    - Delete all persona data\n"
            "/mrm reset all            - Wipe all plugin data\n"
            "--- Other ---\n"
            "/mrm help                 - Show this help"
        ),
    },
    LANG_JA: {
        # Extractor
        "extractor.user_prompt_header": "[Bot ペルソナ] {desc}\n注意：summary の各トリプレットの最後に [Eval] フィールドを追加し、上記のペルソナの視点からそのトピックについて一言評価を加えてください。",
        "extractor.tags_header": "[既存のタグ体系] {tags}\n注意：chat_content_tags は、上記の既存のタグから優先的に選択してください。既存のタグがどれも適切でない場合にのみ、よりマクロで抽象的な新しいタグを作成してください。",
        "extractor.conversation_record": "対話記録（計{count}件のメッセージ、時間スパンは約{duration}分）：",
        "extractor.semantic_record": "以下は意味的に高度に関連する一連の対話記録です（計{count}件）：",
        "extractor.distillation_json_instruction": "\nこの対話の構造化情報を抽出してください。以下のフィールドを含む単一の JSON オブジェクトを出力してください：\n"
                                                  '{"topic": "コアトピック(30文字以内)", "summary": "要約", '
                                                  '"chat_content_tags": ["タグ1", "タグ2"], "salience": 0.5, "confidence": 0.8, "inherit": false, '
                                                  '"participants_personality": {"Alice": {"O": 0.6, "C": 0.5, "E": 0.7, "A": 0.4, "N": -0.2}}}',
        "extractor.default_user_name": "ユーザー",
        "extractor.topic_placeholder": "コアトピック(30文字以内)",
        "extractor.fallback_summary": "{count}件の関連メッセージを集計しました。",
        "extractor.distill_failed": "抽出に失敗しました。元のメッセージ：{text}...",

        # Summary task
        "summary.no_events": "（イベントなし）",
        "summary.untitled_topic": "無題のトピック",
        "summary.topic_shift": "*{sender}が「{preview}」を送信した後、話題は次のように変わりました：",
        "summary.position_unknown": "[{names}の位置はまだ確定していません]",
        "summary.position_known": "[{names}はグループ内の{label}の位置にいます]",
        "summary.mood_overall": "グループ全体の感情動態は[{orientation}]に傾いています | [平均親和度：{b}、平均支配度：{p}] | ",
        "summary.mood_failed": "（感情動態の生成に失敗しました）",
        "summary.private_chat": "プライベート",
        "summary.word_limit_hint": "主要なトピックの要約を生成してください。",
        "summary.timeout": "（生成タイムアウト）",
        "summary.failed": "（生成失敗）",
        "summary.header": "# {label} 活動要約 — {date} {start} - {end}",
        "summary.section_topic": "[主要トピック]",
        "summary.section_events": "[イベントリスト]",
        "summary.section_mood": "[感情動態]",

        # Config hints (for future i18n of _conf_schema.json)
        "config.retrieval_weighted_random.hint": "有効にすると、決定論的なTop-Kの代わりにSoftmaxサンプリングを使用し、記憶の想起をより自然にします（時々スコアの低いイベントを思い出します）。",
        "config.retrieval_sampling_temperature.hint": "加重ランダムモードでのみ有効です。1.0が標準です。数値が低いほど決定論的なランキングに近づき、高いほどランダム性が増します。",

        # Projector / Markdown
        "projector.bot_persona_title": "# Bot プロフィール",
        "projector.bot_persona_desc": "> このファイルはボット自身のペルソナ情報を記録しており、プラグインによって自動生成されます。",
        "projector.base_info": "## 基本情報",
        "projector.field": "フィールド",
        "projector.value": "値",
        "projector.name": "名称",
        "projector.confidence": "信頼度",
        "projector.created_at": "作成日時",
        "projector.last_active": "最終活動",
        "projector.bindings": "## バインディング済みID",
        "projector.no_bindings": "バインディングされたIDはありません",
        "projector.attrs": "## 属性",
        "projector.no_attrs": "属性の記録はありません",
        "projector.impression_title": "# {name} の印象記録",
        "projector.impression_desc": "> このファイルはユーザーが手動で編集でき、変更はフェーズ10でデータベースに同期されます。",
        "projector.impression_from": "## `{observer}` からの印象（範囲：{scope}）",
        "projector.ipc_orientation": "社会的取向",
        "projector.benevolence": "親和度",
        "projector.power": "支配度",
        "projector.intensity": "感情强度",
        "projector.r_squared": "適合度",
        "projector.last_reinforced": "最終強化",
        "projector.evidence": "**証拠イベント：** ",
        "projector.no_impressions": "印象記録はありません",
        "projector.profile_desc": "> このファイルはプラグインによって自動生成されます。直接編集しないでください。印象記録を変更するには、同じディレクトリ内的 IMPRESSIONS.md を編集してください。",
        "projector.uid": "内部 UID",
        "projector.platform": "プラットフォーム",
        "projector.physical_id": "物理 ID",
        "projector.personal_attrs": "## 個人属性",
        "projector.recent_events": "## 最近の参加イベント（直近 {count} 件）",
        "projector.no_events": "イベント記録はありません",
        "projector.affect_positive": "ポジティブ（{value:+.2f}）",
        "projector.affect_negative": "ネガティブ（{value:+.2f}）",
        "projector.affect_neutral": "ニュートラル（{value:+.2f}）",

        # IPC Labels
        "ipc.亲和": "親和的",
        "ipc.活跃": "社交的",
        "ipc.掌控": "支配的",
        "ipc.高傲": "傲慢的",
        "ipc.冷淡": "冷淡な",
        "ipc.孤避": "離絶的",
        "ipc.顺应": "服従的",
        "ipc.谦让": "謙虚な",
        "ipc.未知": "未知",

        # Formatter
        "formatter.minutes_ago": "{count}分前",
        "formatter.hours_ago": "{count}時間前",
        "formatter.days_ago": "{count}日前",
        "formatter.recall_header": "## 関連する歴史的記憶\n",

        # Command manager responses
        "cmd.not_init": "プラグインが初期化されていません。",
        "cmd.status.header": "【Moirai ステータス】",
        "cmd.status.tasks": "登録済みタスク：{tasks}",
        "cmd.status.tasks_none": "なし",
        "cmd.status.sessions": "アクティブセッション数：{count}",
        "cmd.status.webui_running": "実行中",
        "cmd.status.webui_stopped": "停止中",
        "cmd.status.webui": "WebUI：{status}",
        "cmd.status.memory": "記憶 event：{events} 件 | ペルソナ：{personas} 個 | 印象：{impressions} 件",
        "cmd.status.avg_response": "平均応答時間：{ms}ms",
        "cmd.status.window": "現在セッション進捗：{current}/{total} ラウンド（{msgs} メッセージ蓄積）",
        "cmd.status.window_none": "現在のセッションにはまだ会話記録がありません",
        "cmd.persona.header": "【ペルソナプロフィール】{name}（{id}）",
        "cmd.persona.description": "説明：{desc}",
        "cmd.persona.bigfive_header": "ビッグファイブ：",
        "cmd.persona.bigfive_dim": "  {label} {pct}%",
        "cmd.persona.bigfive_dim_ev": "  {label} {pct}%：{ev}",
        "cmd.persona.tags": "タグ：{tags}",
        "cmd.persona.confidence": "信頼度：{pct}%",
        "cmd.persona.not_found": "プラットフォーム {platform} に ID {id} のペルソナが見つかりません。",
        "cmd.persona.no_repo": "ペルソナリポジトリが読み込まれていません。",
        "cmd.soul.header": "【現在のセッション感情状態】",
        "cmd.soul.neutral": "現在のセッション感情状態：中立（偏りなし）",
        "cmd.soul.recall_depth": "記憶検索ドライブ：{val}",
        "cmd.soul.impression_depth": "社会的注目度：{val}",
        "cmd.soul.expression_desire": "表現欲：{val}",
        "cmd.soul.creativity": "創造性：{val}",
        "cmd.soul.level_high": "高め",
        "cmd.soul.level_low": "低め",
        "cmd.soul.level_neutral": "中立",
        "cmd.recall.not_found": "「{query}」に関連する記憶が見つかりません。",
        "cmd.task.triggered": "タスク '{task}' の実行をトリガーしました。",
        "cmd.task.not_found": "タスク '{task}' が見つかりません。利用可能：{available}",
        "cmd.flush.no_ctx": "コンテキストマネージャが有効になっていません。",
        "cmd.flush.no_window": "このセッションにアクティブなコンテキストウィンドウがありません。",
        "cmd.flush.done": "セッションウィンドウをクリアしました（{count} 件のメッセージ）。",
        "cmd.webui.not_loaded": "WebUI モジュールが読み込まれていません。",
        "cmd.webui.started": "WebUI 起動済み：http://{host}:{port}",
        "cmd.webui.start_failed": "WebUI の起動に失敗しました：{error}",
        "cmd.webui.stopped": "WebUI を停止しました。",
        "cmd.webui.stop_failed": "WebUI の停止に失敗しました：{error}",
        "cmd.webui.usage": "使い方：/mrm webui on | off",
        "cmd.reset.confirm_warn": "⚠️ この操作は{desc}。\n{ttl} 秒以内に同じコマンドを再度送信して確認してください。",
        "cmd.reset.no_event_repo": "イベントリポジトリが読み込まれていません。",
        "cmd.reset.no_persona_repo": "ペルソナリポジトリが読み込まれていません。",
        "cmd.reset.no_repo": "リポジトリが完全に読み込まれていないため、全量リセットは実行できません。",
        "cmd.reset.here_done": "このグループの {count} 件のイベント記録を削除しました",
        "cmd.reset.summary_suffix": "要約ファイル {count} 件",
        "cmd.reset.event_group_done": "グループ {gid} の {count} 件のイベント記録を削除しました",
        "cmd.reset.event_all_done": "全 {count} 件のイベント記録を削除しました。",
        "cmd.reset.persona_not_found": "プラットフォーム {platform} に ID {id} のペルソナが見つかりません。",
        "cmd.reset.persona_one_done": "{name}（{id}）のペルソナを削除しました。",
        "cmd.reset.persona_all_done": "全 {count} 件のペルソナを削除しました。",
        "cmd.reset.all_done": "全プラグインデータをクリアしました：イベント {ev_count} 件、ペルソナ {p_count} 件、および全投影ファイル。",
        "cmd.reset.usage": "使い方：/mrm reset here | event <group_id|all> | persona <PlatID|all> | all",
        "cmd.reset.event_usage": "使い方：/mrm reset event <group_id> | all",
        "cmd.reset.persona_usage": "使い方：/mrm reset persona <PlatID> | all",
        "cmd.reset.desc_here": "{scope}の全イベント記録と要約ファイルを削除します（復元不可）",
        "cmd.reset.desc_event_group": "グループ {gid} の全イベント記録と要約ファイルを削除します（復元不可）",
        "cmd.reset.desc_event_all": "全イベント記録を削除します（復元不可）",
        "cmd.reset.desc_persona_one": "ユーザー {id} のペルソナデータを削除します（復元不可）",
        "cmd.reset.desc_persona_all": "全ペルソナデータを削除します（復元不可）",
        "cmd.reset.desc_all": "全プラグインデータ（イベント、ペルソナ、投影ファイル）を完全に削除します（完全に復元不可）",
        "cmd.reset.scope_group": "グループ {gid}",
        "cmd.reset.scope_private": "プライベートチャット",
        "cmd.lang.set": "言語を切り替えました：{lang}",
        "cmd.lang.invalid": "サポートされていない言語コードです。オプション：cn（中文）/ en（English）/ ja（日本語）",
        "cmd.dep.usage": "使い方：/mrm dep install <sentence-transformers|scikit-learn>",
        "cmd.dep.installing": "{lib} をインストールしています... 数分かかる場合があります。お待ちください。",
        "cmd.dep.installed": "✅ {lib} のインストールが完了しました！関連機能を有効にするにはプラグインを再起動してください。",
        "cmd.dep.failed": "❌ {lib} のインストールに失敗しました：{error}",
        "cmd.dep.invalid": "サポートされていない依存関係です。オプション：sentence-transformers, scikit-learn",
        "cmd.init.header": "【Moirai 初期化成功】",
        "cmd.init.module": " - {name}: {status}",
        "cmd.init.model": " - {name}モデル: {model}",
        "cmd.init.active": "有効",
        "cmd.init.inactive": "無効",
        "cmd.init.none": "なし",
        "cmd.help.full": (
            "【Moirai コマンドヘルプ】\n"
            "--- 情報照会 ---\n"
            "/mrm status               - プラグインの実行状態を確認\n"
            "/mrm persona <PlatID>     - ユーザーのペルソナプロフィール + ビッグファイブ\n"
            "/mrm soul                 - 現在のセッション感情状態を確認\n"
            "/mrm recall <キーワード>  - 手動で記憶を検索\n"
            "--- 操作 ---\n"
            "/mrm webui on|off         - WebUI の起動または停止\n"
            "/mrm flush                - セッションコンテキストウィンドウをクリア（DB は保持）\n"
            "/mrm run <task>           - バックグラウンドタスクをトリガー (decay/synthesis/summary/cleanup)\n"
            "/mrm language <cn/en/ja>  - コマンド表示言語を切り替え\n"
            "/mrm dep install <lib>    - オプションの依存関係をインストール (sentence-transformers/scikit-learn)\n"
            "--- リセット（二段階確認が必要）⚠️ ---\n"
            "/mrm reset here           - 現在のグループのイベントと要約を削除\n"
            "/mrm reset event <gid>    - 指定グループのイベントと要約を削除\n"
            "/mrm reset event all      - 全イベント記録を削除\n"
            "/mrm reset persona <id>   - 指定ユーザーのペルソナを削除\n"
            "/mrm reset persona all    - 全ペルソナデータを削除\n"
            "/mrm reset all            - 全プラグインデータをクリア\n"
            "--- その他 ---\n"
            "/mrm help                 - このヘルプを表示"
        ),
    }

}

def get_string(key: str, lang: str = LANG_ZH) -> str:
    """Get a localized string by key and language."""
    return _STRINGS.get(lang, _STRINGS[LANG_ZH]).get(key, _STRINGS[LANG_ZH].get(key, key))
