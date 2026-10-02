# Memory segmentation in the development worktree

The uncommitted v1.2.36 worktree keeps Core Event Protocol v1 unchanged. It adds conservative memory-unit boundaries to Moirai's `llm` extraction strategy. The existing frontend pagination work shares the same unreleased version; this document does not register a new pinned compatibility baseline.

## Extraction boundary

A closed window containing at least 12 messages receives one short segmentation call, at temperature zero when supported by the provider. The V3 prompt describes a remembered experience rather than a topic category: follow-ups, reactions and brief digressions stay with their surrounding conversation. Examples are domain-neutral and labels use the conversation's language.

Segment starts are sorted and deduplicated; an omitted first start is filled with zero. Invalid starts are discarded. A response with no valid starts is rejected. Consecutive ranges cover the entire window without overlapping. Segments shorter than four messages merge into an adjacent segment. If label vectors are available, relative cosine similarity selects the neighbour; otherwise the shorter neighbour wins, with a stable left-first tie. Adjacent labels also determine which ranges merge when the count exceeds `ceil(message_count / extraction_segmentation_messages_per_segment)`.

Segmentation is enabled by default and can be disabled with `extraction_llm_segmentation`. It is skipped for small windows, rule-only teardown and missing providers. Timeout, provider errors or invalid output keep the whole window as one memory unit. The boundary call has a configurable 30-second timeout and no retries. Label encoding, when needed for merging, has the same timeout. These operations remain behind the window-close background extraction callback.

A unit exceeding `extractor_context_messages` is divided into balanced consecutive pages. A cap of 40 divides 41 messages into pages of 21 and 20 instead of creating a one-message tail. Zero means unlimited visibility. Each page becomes one event using the existing single-event extraction prompt. The previous page's factual summary is supplied as context only; it resets at the next memory unit. Event references, raw-message links, timestamps and IPC evidence include only the current page's messages.

All page results are staged before persistence. If a later page raises `ModelUnavailable`, the existing delayed retry starts the window again without leaving previously saved pages. The final attempt retains the existing rule fallback. This prevents duplication due to model retries; it does not turn repository writes into a database-wide transaction or guarantee that an LLM preserves every fact in its summary.

## Drift calibration

Window closing rules remain in place. Vector drift is an auxiliary signal. `boundary_topic_drift_auto_calibration` defaults to true. Until 64 valid observations exist, the configured `boundary_topic_drift_threshold` is used. Thereafter the default threshold is the nearest-rank 85th percentile of the previous 512 observations at most. The current observation is tested against the prior distribution before being recorded. Encoder object, identity or vector dimension changes reset the history; zero vectors, dimension mismatches and non-finite values are ignored. Calibration can be disabled and the percentile is configurable.

The 85th-percentile policy came from the earlier arc:embedvl calibration (about 0.35 on that sample). Relative calibration adapts to a model's distance scale; it has not established equal boundary quality on other models, deployments or conversation shapes. Held-out answer and boundary evaluation is still required.

## Injection and background vectors

Injection reads a cached query vector and stored segment vectors only. Cache misses, unsupported cache interfaces, incomplete segment vectors, text-hash mismatches and encoder-identity mismatches use the previous formatter for the current block. The production EmbeddingManager maintains an identity-scoped bounded cache, including vectors computed through batching.

Missing vectors are queued by RecallManager, with at most 32 pending tasks and one event embedding at a time. Repeated requests coalesce by event ID and encoder identity. The task reads the current event before encoding and skips deleted events; model changes invalidate stored vectors. A full queue skips additional work, which may be offered again on a later recall. Backfill failures are logged and do not fail the current generation. Plugin shutdown cancels these tasks before closing embedding providers or repositories. Development replay and full-flow compositions also close the recall manager.

## Validation

The local tests use scripted providers, in-memory repositories and temporary SQLite databases. `tests/` and `docs/TODO.md` are ignored in this upstream repository; they remain local development evidence. This document is an ordinary untracked documentation addition. Run the suite from `moirai/`:

```bash
.venv/bin/python -m unittest discover -s tests -q
```

From the workspace root:

```bash
PYTHONPATH=core/src moirai/.venv/bin/python scripts/verify-event-runtime.py
PYTHONPATH=core/src moirai/.venv/bin/python scripts/fullflow_test.py --self-test
git diff --check
git -C moirai diff --check
./scripts/status.sh
```

No KCL calls, runtime database rebuilds, dependency installations or model-quality experiments are part of these checks. The earlier V3 prompt experiment established reduced fragmentation, not an answer-quality improvement. The ch0–17 replay and held-out quality evaluation are still pending.

On 2026-10-02, the suite ran 406 tests with one skip and no failures. Joint verification passed 28 tests. The full-flow self-test passed four tests, including 50 Core message/response records extracted into two pages and linked exactly once in temporary SQLite storage. Both diff checks and the status script exited zero; the status script reports the existing uncommitted Moirai worktree. Async SQLite callbacks hung in the execution sandbox even for an independent in-memory query, so the three SQLite-backed checks ran successfully outside that sandbox with automatic approval.
