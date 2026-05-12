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
    }

}

def get_string(key: str, lang: str = LANG_ZH) -> str:
    """Get a localized string by key and language."""
    return _STRINGS.get(lang, _STRINGS[LANG_ZH]).get(key, _STRINGS[LANG_ZH].get(key, key))
