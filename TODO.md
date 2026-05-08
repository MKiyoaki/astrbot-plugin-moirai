# Implementation TODO

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
