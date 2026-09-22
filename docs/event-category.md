# Topic and event-interaction classification

Moirai v1.2.0.sub classifies two independent axes. TypeSafe System One is the calibrated path; when it is unavailable, the configured extraction LLM can classify the interaction axis against the same taxonomy:

- **Topic:** each concrete `chat_content_tags` value maps to one of eleven broad topic categories used by recall and the WebUI.
- **Event interaction:** each fact-only summary segment maps to zero or more conversational interaction groups and one subtype inside every selected group.

The feature is off by default. With `typesafe_enabled` false, no API key, or both axis switches false, no content is sent to TypeSafe. Extraction prompts, event boundaries, salience, embeddings and the Core protocol are unchanged.

## Topic axis

| Category | Option id | Category | Option id |
| --- | --- | --- | --- |
| 游戏 | `game` | 日常 | `daily` |
| 社交 | `social` | 资讯 | `news` |
| 情感 | `emotion` | 艺术 | `art` |
| 技术 | `tech` | 娱乐 | `entertainment` |
| 知识 | `knowledge` | 创作 | `creation` |
| 工作 | `work` | | |

`other` records an abstention. A tag is asked once, using the first event that claims it as context. Its answer is stored in `tag_categories(tag_text, category, confidence, updated_at)` even when it is an abstention or below the configured threshold. Confident answers populate the process-wide learned map read by `infer_tag_category`; all other reads continue through the keyword fallback without network access.

The offline fallback now includes 娱乐 (`娱乐`, `段子`, `综艺`, `搞笑`, `影视`, `视频`). This is the only topic behaviour change while TypeSafe is disabled.

## Event-interaction axis

The classifier uses `split_subtopics()` to separate the fact-only summary into at most twelve `[What] / [Who] / [How]` segments. `[Eval]` persona asides are removed. Each segment is evaluated independently, so a multi-topic event is not forced into one label.

The static interaction tree has nine first-layer groups and 33 second-layer leaves. Classifier payloads retain the stable English ids. Accepted leaves are persisted to `chat_content_tags` using the Chinese tags in this table:

| First layer (English) | 一级类别（中文） | Second layer (English) | 中文 tag | Internal leaf id |
| --- | --- | --- | --- | --- |
| Describing / Sharing | 描述与分享 | Past Event / Recount | 过去事件简述 | `past_event_recount` |
| Describing / Sharing | 描述与分享 | Present Situation Commentary | 现状描述 | `present_situation_commentary` |
| Describing / Sharing | 描述与分享 | General Information / Explanation | 信息解释 | `general_information_explanation` |
| Describing / Sharing | 描述与分享 | Future Event / Intention | 未来意图 | `future_event_intention` |
| Personal Stance & Evaluation | 个人立场与评价 | Opinion | 观点 | `opinion` |
| Personal Stance & Evaluation | 个人立场与评价 | Evaluation | 评价 | `evaluation` |
| Personal Stance & Evaluation | 个人立场与评价 | Feeling / Emotion | 情绪表达 | `feeling_emotion` |
| Personal Stance & Evaluation | 个人立场与评价 | Observation / Comment | 观察评论 | `observation_comment` |
| Personal Stance & Evaluation | 个人立场与评价 | Complaint / Grievance | 抱怨 | `complaint_grievance` |
| Social / Casual Interaction | 社交与闲聊 | Chat / Small Talk | 闲聊 | `chat_small_talk` |
| Social / Casual Interaction | 社交与闲聊 | Gossip | 八卦 | `gossip` |
| Social / Casual Interaction | 社交与闲聊 | Catching Up | 叙旧 | `catching_up` |
| Social / Casual Interaction | 社交与闲聊 | Relationship-oriented Talk | 关系交流 | `relationship_oriented_talk` |
| Storytelling | 叙事 | Narrative | 完整叙事 | `narrative` |
| Storytelling | 叙事 | Anecdote | 轶事 | `anecdote` |
| Storytelling | 叙事 | Recount | 过程复述 | `storytelling_recount` |
| Storytelling | 叙事 | Exemplum | 例证故事 | `exemplum` |
| Playful Interaction | 玩笑互动 | Joking | 玩笑 | `joking` |
| Playful Interaction | 玩笑互动 | Banter / Teasing | 调侃 | `banter_teasing` |
| Playful Interaction | 玩笑互动 | Friendly Ridicule | 善意嘲弄 | `friendly_ridicule` |
| Figuring Things Out | 探索与解决 | Exploring / Understanding | 探索理解 | `exploring_understanding` |
| Figuring Things Out | 探索与解决 | Problem Solving | 问题解决 | `problem_solving` |
| Figuring Things Out | 探索与解决 | Considering Options | 方案比较 | `considering_options` |
| Figuring Things Out | 探索与解决 | Planning | 规划 | `planning` |
| Figuring Things Out | 探索与解决 | Decision-oriented Discussion | 决策讨论 | `decision_oriented_discussion` |
| Advice / Guidance | 建议与指导 | Advice | 建议 | `advice` |
| Advice / Guidance | 建议与指导 | Suggestion | 提议 | `suggestion` |
| Advice / Guidance | 建议与指导 | Instruction | 操作指导 | `instruction` |
| Conflict / Disagreement | 冲突与分歧 | Difference of Opinion | 意见分歧 | `difference_of_opinion` |
| Conflict / Disagreement | 冲突与分歧 | Debate | 辩论 | `debate` |
| Conflict / Disagreement | 冲突与分歧 | Interpersonal Conflict | 人际冲突 | `interpersonal_conflict` |
| Question / Request | 提问与请求 | Information Seeking | 信息询问 | `information_seeking` |
| Question / Request | 提问与请求 | Action Request | 行动请求 | `action_request` |

If no leaf is accepted, the event receives the Chinese tag `未分类`; its legacy id is `uncategorised`. Migration `019_localize_interaction_tags.sql` translates existing taxonomy-derived English tags while preserving unrelated historical free-form tags.

The two Recount leaves have namespaced internal ids and different criteria: `past_event_recount` is a concise factual report, while `storytelling_recount` is a chronological reconstruction. The criteria also distinguish the other close pairs, including Opinion/Evaluation, Advice/Suggestion and Planning/Decision-oriented Discussion.

Accepted leaves are deduplicated across segments and ranked by group score multiplied by leaf confidence. The TypeSafe path keeps every accepted leaf. The LLM fallback keeps at most the three highest-ranked leaves because its confidence is not calibrated to the TypeSafe scale. The Chinese first-layer name is exposed as each derived tag's `tag_category`; English ids remain readable for legacy records.

Classification has two passes:

1. One Noul question per segment and group returns a `0..1` applicability score. Every group at or above `typesafe_min_confidence` remains active, so Complaint, Playful Interaction and Question / Request can coexist.
2. One Choice question per active group selects its subtype. A low-confidence or `other` result keeps the parent group but does not adopt a subtype.

The first request also carries Choice questions for any unseen tags, so a normal new event needs two requests rather than a separate topic request. If no interaction group reaches the threshold, only the first request is needed.

### Dynamic custom group

`custom / 自定义` is a tenth, runtime-only first-layer group. Its leaves are Chinese interaction-behaviour tags approved for one `bot_persona_name`; the empty name is an isolated legacy scope. Each persona can own at most 50 custom leaves, and a name registered for one persona is not offered to another.

After a complete classification produces only `未分类` from a non-empty fact summary, the classifier runs at most two resolution rounds:

1. The extraction LLM returns exactly `{"tag":"中文标签"}`. The parser accepts only 2–8 Chinese characters describing a reusable interaction behaviour. Person names, entities, topics, one-off details and sentences are invalid; invalid output still consumes the round.
2. A separate TypeSafe Noul Judge scores whether the candidate accurately and reusably explains the event. A score at or above `typesafe_custom_tag_min_score` accepts it. Lower scores add the candidate to the rejection list used by the next generation round.

An accepted existing custom tag is reused. An accepted name matching one of the 33 static tags reuses that static tag without writing the custom vocabulary. A genuinely new accepted name is registered atomically in the current persona scope; registration deduplicates concurrent attempts and enforces the 50-tag cap. If both rounds fail, the event remains `未分类`. A missing TypeSafe client, malformed Judge answer or final Judge network failure stops immediately without another LLM call; TypeSafe's internal HTTP retries remain part of the same round.

Future TypeSafe classification first scores the `自定义` group and then chooses among that persona's approved leaves. When TypeSafe is unavailable, the LLM fallback can choose those same approved leaves but cannot create new ones. The dynamic loop therefore costs up to two LLM completions and two logical Judge calls only for otherwise-complete, non-empty `未分类` events.

The Events and Library filter rows expose the current tree through their theme-coloured tag button. The read-only dialog renders all nine static groups and the current persona scope's `自定义` leaves; the all-personas view shows the distinct union. It reads `/api/tags/tree` on every open, so a newly approved tag appears without rebuilding the frontend. No edit, delete, archive or management action is exposed.

## Persistence

Migration `018_typesafe_classification.sql` adds:

- `events.interaction_classification TEXT NOT NULL DEFAULT ''`, containing versioned JSON;
- the independent `tag_categories` table described above.

Migration `019_localize_interaction_tags.sql` converts the 33 interaction-derived English tag ids and `uncategorised` in existing event rows to their Chinese forms. It does not alter the English ids stored inside `interaction_classification`.

Migration `020_custom_interaction_tags.sql` adds `custom_interaction_tags(bot_persona_name, tag_text, created_at)` with `(bot_persona_name, tag_text)` as its primary key. Persona merges move the source vocabulary into the target scope, keep target rows on name collisions and discard duplicates.

The interaction payload is schema version 2. It records the input hash, threshold, completion state, every group score and each active group's subtype answer. When dynamic resolution runs, `custom_resolution` records its status, each candidate's Judge score and result, the selected tag, and its `static`, `custom_existing` or `custom_new` source. Prompts, provider output and generated explanations are not stored. Low-confidence subtype answers remain available for calibration while `accepted: false` makes the parent-only fallback explicit. Version 1 payloads remain readable, and empty text means the event has never been classified.

`EventRepository.set_interaction_classification()` is a targeted write. General event `upsert()` deliberately preserves the stored interaction JSON so a concurrent deferred `[Eval]` summary rewrite cannot erase it. Manual event creation schedules classification; manual edits and LLM re-extraction clear the stale interaction result and schedule it again.

The JSON APIs expose `interaction_classification` beside the derived `tag_categories`. Recall uses the Chinese leaf tags and their Chinese first-layer categories; the interaction payload remains language-stable for classifier compatibility.

## Failure and backfill

An invalid or incomplete first-pass interaction response does not mark the event classified. A failed second pass preserves the valid parent groups with `complete: false`. Tag failures write no row, allowing a later attempt. HTTP 401 disables the client for the process; 429, 529, other 5xx responses, timeouts and connection errors retry twice; 422 does not retry. API keys and request bodies are never logged.

Topic backfill defaults on. It scans the newest 5000 events, asks unseen tags newest-first, makes at most 200 requests per start and stops after five consecutive failures. It never rewrites old event rows.

Event backfill defaults off because every event normally needs two requests. When explicitly enabled it processes at most 100 recent unclassified events per start.

## What is sent

Normal topic and interaction classification sends only:

- the event topic;
- its concrete tags;
- the fact-only summary split into numbered segments;
- the relevant English question and category descriptions.

Raw messages, message ids, event ids, user ids, group ids, persona text and `[Eval]` asides are not sent. TypeSafe's public documentation does not state a general request-data retention period; review its Data Processing Agreement and Privacy Policy before enabling the feature for real conversations.

Custom generation and Judge requests use a narrower boundary: event topic, numbered fact-only summary segments, the current persona's approved custom tag names, and candidates rejected in the current loop. They do not include the event's current tags, raw messages, event or user ids, persona name, persona text, `[Eval]` content, generated explanations or model transcripts.

## Configuration

| Key | Default | Meaning |
| --- | --- | --- |
| `typesafe_enabled` | `false` | Master switch. |
| `typesafe_topic_enabled` | `true` | Classify concrete tags into eleven topic categories. |
| `typesafe_event_enabled` | `true` | Classify summary segments into interaction types. |
| `typesafe_api_key` | empty | Falls back to `TYPESAFE_API_KEY`. |
| `typesafe_base_url` | `https://api.typesafe.ai` | API root. |
| `typesafe_model` | `jev-latest` | Model identifier. |
| `typesafe_timeout_seconds` | `10` | Per-request timeout. |
| `typesafe_min_confidence` | `0.5` | Shared group, subtype and topic threshold; not calibrated on real data. |
| `typesafe_custom_tag_min_score` | `0.7` | Independent acceptance threshold for a generated custom-tag candidate. |
| `typesafe_topic_backfill` | `true` | Backfill unseen historical tags. |
| `typesafe_event_backfill` | `false` | Backfill historical event interactions. |

The AstrBot plugin configuration panel is generated from `_conf_schema.json`. A key alone does not enable the feature. The ignored development `run_config.py` can set `TYPESAFE_ENABLED` and `TYPESAFE_API_KEY`; the plugin must be reloaded after a configuration change. Moirai's hand-written WebUI configuration page does not currently display this group.

## Verification boundary

`tests/test_event_category.py` uses `httpx.MockTransport`, simulated providers, in-memory repositories and temporary SQLite databases. It covers mixed Choice/Noul parsing, the static and read-only API tree, bilingual tag mapping, dynamic generation and rejection, two-round limits, static/custom reuse, persona scoping, the 50-tag cap, custom Choice and LLM fallback, persona merges, targeted writes, migrations 018–020, extraction scheduling and re-extraction. `run_realtime_dev.py --self-test --quiet` discovers both event-category and event-summary regressions so the complete local behavior can be checked with one command.

No real TypeSafe call has been made. Accuracy on Chinese summaries, the default threshold, and the topic boundary between 游戏 and 娱乐 remain uncalibrated. The ignored development database is never opened in place during offline checks.
