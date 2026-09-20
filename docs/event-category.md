# Topic and event-interaction classification through TypeSafe

Moirai v1.0.18.sub can use the TypeSafe System One API to classify two independent axes:

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

The interaction tree has nine groups:

| Group | Subtypes |
| --- | --- |
| Describing / Sharing | Past Event / Recount; Present Situation Commentary; General Information / Explanation; Future Event / Intention |
| Personal Stance & Evaluation | Opinion; Evaluation; Feeling / Emotion; Observation / Comment; Complaint / Grievance |
| Social / Casual Interaction | Chat / Small Talk; Gossip; Catching Up; Relationship-oriented Talk |
| Storytelling | Narrative; Anecdote; Recount; Exemplum |
| Playful Interaction | Joking; Banter / Teasing; Friendly Ridicule |
| Figuring Things Out | Exploring / Understanding; Problem Solving; Considering Options; Planning; Decision-oriented Discussion |
| Advice / Guidance | Advice; Suggestion; Instruction |
| Conflict / Disagreement | Difference of Opinion; Debate; Interpersonal Conflict |
| Question / Request | Information Seeking; Action Request |

The two Recount leaves have namespaced internal ids and different criteria: `past_event_recount` is a concise factual report, while `storytelling_recount` is a chronological reconstruction. The criteria also distinguish the other close pairs, including Opinion/Evaluation, Advice/Suggestion and Planning/Decision-oriented Discussion.

Classification has two passes:

1. One Noul question per segment and group returns a `0..1` applicability score. Every group at or above `typesafe_min_confidence` remains active, so Complaint, Playful Interaction and Question / Request can coexist.
2. One Choice question per active group selects its subtype. A low-confidence or `other` result keeps the parent group but does not adopt a subtype.

The first request also carries Choice questions for any unseen tags, so a normal new event needs two requests rather than a separate topic request. If no interaction group reaches the threshold, only the first request is needed.

## Persistence

Migration `018_typesafe_classification.sql` adds:

- `events.interaction_classification TEXT NOT NULL DEFAULT ''`, containing versioned JSON;
- the independent `tag_categories` table described above.

The event JSON records the input hash, threshold, completion state, every group score and each active group's subtype answer. Low-confidence subtype answers remain available for calibration while `accepted: false` makes the parent-only fallback explicit. Empty text means the event has never been classified.

`EventRepository.set_interaction_classification()` is a targeted write. General event `upsert()` deliberately preserves the stored interaction JSON so a concurrent deferred `[Eval]` summary rewrite cannot erase it. Manual event creation schedules classification; manual edits and LLM re-extraction clear the stale interaction result and schedule it again.

The JSON APIs expose `interaction_classification` beside the unchanged derived `tag_categories`. No current recall score depends on interaction labels.

## Failure and backfill

An invalid or incomplete first-pass interaction response does not mark the event classified. A failed second pass preserves the valid parent groups with `complete: false`. Tag failures write no row, allowing a later attempt. HTTP 401 disables the client for the process; 429, 529, other 5xx responses, timeouts and connection errors retry twice; 422 does not retry. API keys and request bodies are never logged.

Topic backfill defaults on. It scans the newest 5000 events, asks unseen tags newest-first, makes at most 200 requests per start and stops after five consecutive failures. It never rewrites old event rows.

Event backfill defaults off because every event normally needs two requests. When explicitly enabled it processes at most 100 recent unclassified events per start.

## What is sent

Each request sends only:

- the event topic;
- its concrete tags;
- the fact-only summary split into numbered segments;
- the relevant English question and category descriptions.

Raw messages, message ids, event ids, user ids, group ids, persona text and `[Eval]` asides are not sent. TypeSafe's public documentation does not state a general request-data retention period; review its Data Processing Agreement and Privacy Policy before enabling the feature for real conversations.

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
| `typesafe_topic_backfill` | `true` | Backfill unseen historical tags. |
| `typesafe_event_backfill` | `false` | Backfill historical event interactions. |

The AstrBot plugin configuration panel is generated from `_conf_schema.json`. A key alone does not enable the feature. The ignored development `run_config.py` can set `TYPESAFE_ENABLED` and `TYPESAFE_API_KEY`; the plugin must be reloaded after a configuration change. Moirai's hand-written WebUI configuration page does not currently display this group.

## Verification boundary

`tests/test_event_category.py` uses `httpx.MockTransport`, in-memory repositories and temporary SQLite databases. It covers mixed Choice/Noul parsing, the nine-group tree, multi-label segments, the Question / Request group, parent fallback, tag caching, both backfills, targeted writes, migration 018, extraction scheduling and re-extraction.

No real TypeSafe call has been made. Accuracy on Chinese summaries, the default threshold, and the topic boundary between 游戏 and 娱乐 remain uncalibrated. The ignored development database is never opened in place during offline checks.
