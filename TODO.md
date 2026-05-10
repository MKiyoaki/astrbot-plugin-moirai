# Implementation TODO

## [情感动态] Data Source Options (for SummaryConfig.mood_source)

Two implementation strategies are available. Currently **Option B (LLM)** is active (`mood_source = "llm"`).

### Option A — Impression DB (future upgrade)
- Set `mood_source = "impression_db"` in `SummaryConfig`
- In `core/tasks/summary.py`: after building [事件列表], collect all participant UIDs from events
- For each UID call `impression_repo.get_latest(observer=BOT_UID, subject=uid)` → get `benevolence`, `power`, `ipc_orientation`
- Aggregate group centroid: mean `benevolence` and mean `power` across members with valid impressions
- Classify centroid via `ipc_model.orientation_from_bp(mean_b, mean_p)`
- Members with confidence < threshold (default 0.3) listed as "位置尚未确定"
- **Fallback**: if fewer than 2 members have impression data, fall back to Option B automatically
- Requires: adding `impression_repo` param to `run_group_summary` (already added as optional `persona_repo`)
- Pros: ML-grounded, no extra LLM call. Cons: sparse data risk for new groups.

### Option B — LLM Inference (current)
- Passes event chain (topics, tags, content previews, participants) to second LLM call
- Prompt: `_DEFAULT_SUMMARY_MOOD_PROMPT` in `core/config.py`
- Expects single-line JSON: `{"orientation": "...", "benevolence": 0.x, "power": 0.x, "positions": {"uid": "..."}}`
- Pros: always produces output. Cons: +1 LLM call per summary run, estimated values only.

## [Done] Pure Batch LLM Event Partitioning (Implemented)

### 1. Objective
Refactor event generation to be strictly triggered by message count (`max_messages`). The LLM will partition the batch (e.g., 20 messages) into one or more `Event` objects, using timestamps and recent context to maintain logical continuity.

### 2. Core Tasks
- [x] **Config**: Simplify `BoundaryConfig` to prioritize `max_messages`. Update `DEFAULT_EXTRACTOR_SYSTEM_PROMPT` for JSON Array output.
- [x] **Detector**: Simplified heuristics; `should_close` primarily triggers on message count and time gap.
- [x] **Extractor Logic**:
    - Update `prompts.py` to add message index numbers.
    - Update `parser.py` to handle JSON Array parsing with `start_idx`/`end_idx`.
    - Update `extractor.py` to generate multiple UUIDs and construct/upsert multiple Events.
- [x] **Router**: Adjust `MessageRouter` to pass the full window to the extractor without pre-creating an Event shell.
- [x] **Testing**: Updated unit tests to verify multi-event partitioning and `inherit_from` linking.

### 3. Verification
- [x] Verify that a 3-day gap in messages is correctly identified by the LLM as a topic boundary.
- [x] Verify that topics spanning across batches are linked via `inherit_from`.
- [x] Ensure extraction tasks are bundled and controlled by `max_messages`.

## [Done] Encoder-Driven Semantic Partitioning & Distillation (Implemented)

### 1. Objective
Further refine memory quality and efficiency by using a lightweight Encoder (Embedding) model for real-time topic boundary detection and de-interleaving. Shift the LLM's role from "partitioning" to "semantic distillation" (summarization), ensuring memory remains high-signal and low-noise.

### 2. Core Tasks
- [x] **Semantic Boundary Detector**:
    - Implement `SemanticPartitioner` in `core/extractor/partitioner.py` using DBSCAN clustering.
    - Added support for "Strategy Pattern" allowing users to choose between LLM-based and Semantic-based partitioning.
- [x] **De-interleaving (Clustering)**:
    - Use semantic clustering to separate interleaved topics within a `MessageWindow`.
    - Automatically handle "Noise" messages via vector outlier detection.
- [x] **Semantic Distillation (LLM)**:
    - Updated `Event` model to include a `summary` field (DB Migration 005).
    - Refactored LLM Prompts and Extractor to focus on generating concise, conclusion-oriented summaries.
- [x] **Performance Monitoring**:
    - Implemented `PerfTracker` and `performance_timer` in `core/utils/perf.py`.
    - Integrated tracking for `partition`, `distill`, `retrieval`, and `recall` phases.

### 3. Verification
- [x] Verified that interleaved topics are split into distinct Events via `tests/experimental`.
- [x] Confirmed 100% test pass rate (315+ tests) including new `summary` field and `partitioner` logic.
- [x] Validated Dataflow E2E via `run_dataflow_dev.py`.
