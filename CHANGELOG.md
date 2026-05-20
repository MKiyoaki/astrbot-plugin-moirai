# CHANGELOG

## [v0.13.1] - 2026-05-20

### Manual summary & relation fixes

- Removed unused `summary_word_limit` config field; word limit is now a fixed internal constant (300 chars).
- Fixed `regenerate_single_summary`: now accepts and forwards `summary_config`, `llm_manager`, and `encoder` so manual re-generation respects user settings, goes through LLM concurrency control, and keeps the NARRATIVE event in the DB in sync with the Markdown file.
- Fixed `_handle_regenerate_summary` in both `plugin_routes.py` and `server.py`: pass live `PluginConfig`-derived `summary_config`, `llm_manager`, and `encoder` to the task function.
- Fixed `reanalyze_impressions_llm`: removed dead `extractor_config` parameter; added optional `persona_repo` to resolve UIDs to display names in the LLM prompt.
- Fixed `_handle_reanalyze_impressions_guarded` (LLM branch): pass `persona_repo` so participant names appear in the analysis prompt.

## [v0.13.0] - 2026-05-20

### Raw message persistence

- Added short-term `raw_messages` / `event_messages` storage for detailed message evidence.
- Added async raw-message batch writing, event-message linking, re-extraction from raw details, recall detail hydration, and raw retention cleanup.
- Added `raw_message_retention_days` config, default 14 days, clamped to 1-14.

## [v0.12.14] - 2026-05-20

### 

- 

## [v0.12.13] - 2026-05-20

### 

- 

## [v0.12.12] - 2026-05-19

### 

- 

The full changelog is maintained at [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

This root-level file is kept for AstrBot/plugin managers that only read
`CHANGELOG.md` from the plugin root.
