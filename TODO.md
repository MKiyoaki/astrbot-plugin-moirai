# Implementation TODO

## [Plan] Pure Batch LLM Event Partitioning (Pending Implementation)

### 1. Objective
Refactor event generation to be strictly triggered by message count (`max_messages`). The LLM will partition the batch (e.g., 20 messages) into one or more `Event` objects, using timestamps and recent context to maintain logical continuity.

### 2. Core Tasks
- [ ] **Config**: Simplify `BoundaryConfig` to only keep `max_messages`. Update `DEFAULT_EXTRACTOR_SYSTEM_PROMPT` for JSON Array output.
- [ ] **Detector**: Remove time/drift heuristics; `should_close` only triggers on message count.
- [ ] **Extractor Logic**:
    - Update `prompts.py` to add message index numbers and recent event context.
    - Update `parser.py` to handle JSON Array parsing with `start_idx`/`end_idx`.
    - Update `extractor.py` to generate multiple UUIDs and construct/upsert multiple Events.
- [ ] **Router**: Adjust `MessageRouter` to pass the full window to the extractor without pre-creating an Event shell.
- [ ] **Testing**: Update `run_dataflow_dev.py` and unit tests to verify multi-event partitioning and `inherit_from` linking.

### 3. Verification
- Verify that a 3-day gap in messages is correctly identified by the LLM as a topic boundary.
- Verify that topics spanning across batches are linked via `inherit_from`.
- Ensure extraction tasks are bundled and controlled by `max_messages`.
