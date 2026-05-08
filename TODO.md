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

## [Plan] Encoder-Driven Semantic Partitioning & Distillation

### 1. Objective
Further refine memory quality and efficiency by using a lightweight Encoder (Embedding) model for real-time topic boundary detection and de-interleaving. Shift the LLM's role from "partitioning" to "semantic distillation" (summarization), ensuring memory remains high-signal and low-noise.

### 2. Core Tasks
- [ ] **Semantic Boundary Detector**:
    - Implement `SemanticBoundaryDetector` in `core/boundary/detector.py` using cosine similarity "pulses".
    - Automatically trigger event closure when a semantic gap exceeds a configurable threshold.
- [ ] **De-interleaving (Clustering)**:
    - Use semantic clustering (e.g., similarity-based grouping) to separate interleaved topics within a `MessageWindow`.
    - Filter out "noise" messages (one-word replies, emoji-only) using vector outlier detection before LLM processing.
- [ ] **Semantic Distillation (LLM)**:
    - Update `Event` model to include a `summary` field.
    - Refactor LLM Prompts to focus on generating a concise, conclusion-oriented summary from a pre-grouped cluster of messages.
- [ ] **Dynamic Resolution Recall**:
    - Update `RecallManager` to implement a "Summary-First" strategy.
    - **Rule**: For events older than 24h or with low-to-mid salience, only inject `Topic + Summary` into the prompt; never show the original `interaction_flow` unless explicitly requested.

### 3. Verification
- Verify that interleaved topics (e.g., User A talks about Code, User B interrupts about Dinner) are split into distinct, pure Events.
- Ensure the Bot can maintain long-term coherence using only distilled summaries without getting bogged down in historical "口水话" (chit-chat).
- Measure Token savings from the "Summary-First" recall strategy.
