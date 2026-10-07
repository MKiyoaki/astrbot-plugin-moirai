# Verification — Moirai v1.2.42.sub

Recorded on 2026-10-06 for the uncommitted `cb5t-loop-wiring` worktree.
This is development evidence, not a release or a pinned compatibility baseline.

## Authorized implementation

The user authorized the Moirai phase, sections 7.1–7.4 of the workspace
[construction plan](../../docs/cb5t-loop-wiring-plan.md), on this branch. The
opening progress report listed the annotation/raw-storage, one-turn notes,
commitment storage/recall/settlement, and persona-view/default/version work.
The default-off decision was confirmed before the affected configuration edits.
The later Core dialogue controls were recorded as follow-up work, not claimed
as complete. No stage, commit, push, dependency install or gitlink update occurred.

## Final evidence

- [x] Complete unittest suite: `Ran 473 tests in 12.910s`, `OK (skipped=1)`.
  Baseline was 455 tests with the same one skip; 18 loop tests were added locally.
- [x] Existing real-Core/Moirai joint event check: `Ran 28 tests in 0.802s`, `OK`.
- [x] Frontend TypeScript check: exit 0, no output.
- [x] Actual event detail React component static-render checks: 8 passes, 0 failures.
- [x] Branch/HEAD/index and workspace/submodule status inspected; all four branches
  and HEADs still match section 4 of the plan. Staged diffs are empty.
- [x] Workspace and Moirai `git diff --check`: exit 0, no output.

These commands used existing environments, temporary stores, local fake HTTP
servers and scripted/null providers. No real model, KCL hub or experiment was
run. Test output contains intentional simulated provider failures, retries,
archive operations on temporary databases, and a loaded `model_type=kcl`
configuration; these messages do not indicate a live model request or changes
to the user's runtime database.

The restricted sandbox could not support the local async/socket tests. Completed
Python validation runs used the automatically reviewed execution override for
local tests only. No dependency installation accompanied it.

## Tested behavior and limits

The new loop tests cover closed annotation validation and detached values;
default configuration/schema/translations; separate provider roles; raw metadata
persistence and router return compatibility; note replacement, person/persona/
session/window isolation; first delivery, request matching, single consumption,
TTL and cache cap; relevant commitment count, group/persona filtering, fake-vector
ranking, idempotent storage and closing only open/listed IDs; persona-view raw
links and legacy Eval; settlement in both existing extraction paths; and leaving
future commitments and rule fallbacks open. Setting the reserved persona-view
injection switch true is also tested to inject neither persona view nor legacy
Eval. Component rendering checks separation from facts and escaped text.

The first new loop run failed because its FakeEncoder weather fixture used
`下次带伞`, which lacks the fake encoder's `雨` discriminator and therefore
received its generic vector. The unrelated fixture was changed to `下雨给你带伞`;
the relevance assertion and runtime ranking code were retained. The failed run
is included below, followed by passing runs.

- [ ] New full Core → Oedipus → Moirai loop verifier cases: next workspace phase.
  The existing 28-case event check is not proof of all new loop paths.
- [ ] Live models, KCL, T1–T6 and other experiments: not run.
- [ ] Real semantic clustering: unavailable scikit-learn exercised the existing
  single-partition fallback; no dependency was installed.
- [ ] Browser, AstrBot, production bundle build/deployment and real database migration:
  not run; migration/storage tests used temporary databases.
- [ ] Commitment relevance quality, vector-service latency/cost and the reused
  0.35 threshold: not measured on real data. Enabled vectors can request embeddings
  for uncached queries and commitment texts; no separate chat-model call is added.
- [ ] Group addressee reasoning and intermediate tool-message hidden blocks:
  not measured. The target remains the triggering sender.
- [ ] Core dialogue debugging controls: follow-up recorded, interface not implemented.

The upstream `.gitignore` ignores `tests/`; new Python tests and the component
harness remain local/ignored and were not force-added. Factual summaries were not
rewritten. Persona-view recall injection is a reserved switch only; the formatter
and Soul Layer remain. The provider consumes the published annotation format
without importing Core or Oedipus runtime source.

## Exact command outputs

Working directories below are relative to the workspace root. Each text block is
an unedited captured stdout/stderr stream; empty streams are stated explicitly.
Exit codes come from the actual completed commands. Captures were made under
`/tmp/cb5t-moirai-*.txt`; their contents are retained here so the record survives
cleanup of temporary files.

### Baseline

Directory: `moirai`. Exit: `0`.

```bash
PYTHONPATH=.:tests/mocks .venv/bin/python -m unittest discover -s tests -p "test_*.py"
```

```text
..22:02:08.454 [WARNING][core.social.big_five_scorer] [BigFiveScorer] scoring failed: busy
.22:02:08.455 [WARNING][core.utils.model_retry] [ModelRetry] task=big_five_score attempt=1 retry_in=0.00s timeout=30.0 reason=HTTPStatusError error=busy
22:02:08.456 [WARNING][core.utils.model_retry] [ModelRetry] task=big_five_score attempt=2 retry_in=0.00s timeout=30.0 reason=ModelOutputError error=Invalid Big Five result
...........22:02:09.188 [WARNING][asyncio] Executing <Task finished name='Task-41' coro=<BenchTests.test_http_error_carries_response_body() done, defined at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_canon.py:886> result=None created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.497 seconds
..22:02:09.821 [WARNING][asyncio] Executing <Task finished name='Task-53' coro=<BenchTests.test_replay_goes_through_real_http_client() done, defined at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_canon.py:860> result=None created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.473 seconds
.................22:02:11.495 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 1): 调用失败：超过 0.05 秒没有返回
22:02:11.546 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 2): 调用失败：超过 0.05 秒没有返回
22:02:11.596 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 3): 调用失败：超过 0.05 秒没有返回
22:02:11.647 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 4): 调用失败：超过 0.05 秒没有返回
.......................................................................................................................................................................s...........................................................................22:02:14.553 [WARNING][core.extractor.category_pass] [CategoryPass] classification failed for e1: TypeSafe HTTP 500: error
..22:02:14.556 [WARNING][core.extractor.category_pass] [CategoryPass] incomplete interaction groups for e1; event result not stored
.................22:02:14.611 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:02:14.611 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['2cd5bfdc']
.22:02:14.635 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['4a9c5c2f']
.................22:02:14.999 [ERROR][core.utils.typesafe] [TypeSafe] API key rejected (401); disabling classification for this process.
....22:02:15.002 [WARNING][core.utils.typesafe] [TypeSafe] attempt 1/3 failed (TypeSafe HTTP 529: busy); retrying in 0.0s
.....22:02:15.007 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:02:15.008 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['662ad857']
..22:02:15.010 [WARNING][core.extractor.extractor] [EventExtractor] LLM extraction parse_error; attempting JSON repair (session=test:group, message_count=2, snippet='not json')
....22:02:15.013 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:02:15.014 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['029597b4']
22:02:15.014 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['98253ade']
.....22:02:15.018 [WARNING][core.extractor.extractor] [EventExtractor] LLM extraction parse_error; attempting JSON repair (session=test:group, message_count=2, snippet='not json')
22:02:15.018 [WARNING][core.extractor.extractor] [EventExtractor] JSON repair parse_error; falling back (session=test:group, message_count=2, repair_snippet='not json')
22:02:15.018 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=parse_error, session=test:group, message_count=2, retries_used=0
22:02:15.018 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.000s ids=['06397bb7']
.22:02:15.019 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/3 (session=test:group, message_count=2)
22:02:15.020 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['3146400b']
.22:02:15.020 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/3 (session=test:group, message_count=2)
22:02:15.021 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 3/3 (session=test:group, message_count=2)
22:02:15.021 [WARNING][core.extractor.extractor] [EventExtractor] LLM batch extraction timed out (retries_used=0)
22:02:15.021 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=timeout, session=test:group, message_count=2, retries_used=0
22:02:15.021 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.001s ids=['1dfbd8d5']
..22:02:15.023 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 600s before attempt 2/3 (session=test:group, message_count=2)
22:02:15.023 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:group, message_count=2
22:02:15.023 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.000s ids=['8d26a38b']
.........22:02:15.024 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'hold' (priority=10, active=1)
22:02:15.025 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'hold' finished in 0.00s
22:02:15.025 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'after' (priority=10, active=1)
22:02:15.025 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'after' finished in 0.00s
.22:02:15.026 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'hold' (priority=10, active=1)
22:02:15.026 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'hold' finished in 0.00s
22:02:15.026 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'synthesis' (priority=10, active=1)
22:02:15.026 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'synthesis' finished in 0.00s
22:02:15.026 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'synthesis' (priority=10, active=1)
22:02:15.026 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'synthesis' finished in 0.00s
22:02:15.027 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'eval' (priority=20, active=1)
22:02:15.027 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'eval' finished in 0.00s
22:02:15.027 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'eval' (priority=20, active=1)
22:02:15.027 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'eval' finished in 0.00s
.22:02:15.028 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=1)
22:02:15.028 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=2)
22:02:15.028 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=3)
22:02:15.039 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:02:15.039 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:02:15.039 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:02:15.039 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=1)
22:02:15.039 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=2)
22:02:15.039 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=3)
22:02:15.049 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:02:15.050 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:02:15.050 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:02:15.050 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=1)
22:02:15.050 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=2)
22:02:15.050 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=3)
22:02:15.061 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:02:15.061 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:02:15.061 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
...........................22:02:16.828 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.00, reason=unavailable
22:02:16.829 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=41 partitions=1 events=3 low_conf=0 duration=0.001s ids=['77cacfea', 'edb72abd', 'e1b0e425']
22:02:16.830 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.00, reason=segmentation requires a segments array
22:02:16.831 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=41 partitions=1 events=3 low_conf=0 duration=0.001s ids=['b1359ed7', 'a6dfd927', '5ed88c64']
.22:02:16.833 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=25 partitions=1 events=3 low_conf=0 duration=0.001s ids=['6fd3fa39', 'ccb538c8', '5ec45bd9']
.22:02:16.834 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/2 (session=test:dm, message_count=25)
22:02:16.835 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=25 partitions=1 events=3 low_conf=0 duration=0.001s ids=['a1dd7ee7', '06942749', '31518da2']
.22:02:16.836 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=45, segments=1, seconds=0.00
22:02:16.837 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=45 partitions=1 events=3 low_conf=0 duration=0.001s ids=['01fb3865', '7cbf5e5d', '1d9ff519']
.22:02:16.839 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=24, segments=2, seconds=0.00
22:02:16.843 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=24 partitions=1 events=4 low_conf=0 duration=0.004s ids=['1166d1cc', 'f600d152', '13b9fe1a', '49e10e5e']
.22:02:16.845 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:02:16.845 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:02:16.845 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:02:16.846 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=45 partitions=1 events=3 low_conf=3 duration=0.001s ids=['d7338cee', '9badee6f', 'ad43dc06']
.22:02:16.948 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.10, reason=
.22:02:16.950 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=11 partitions=1 events=1 low_conf=0 duration=0.000s ids=['cca71a71']
22:02:16.950 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=20 partitions=1 events=1 low_conf=0 duration=0.000s ids=['1e3f0a0b']
.22:02:16.951 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=24, segments=2, seconds=0.00
......22:02:17.065 [WARNING][core.utils.model_retry] [ModelRetry] task=segmentation attempt=1 retry_in=0.00s timeout=0.1 reason=TimeoutError error=TimeoutError()
22:02:17.185 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=12, segments=1, seconds=0.22
...22:02:17.208 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=1 retry_in=0.00s timeout=0.02 reason=TimeoutError error=TimeoutError()
22:02:17.249 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=2 retry_in=0.00s timeout=0.04 reason=TimeoutError error=TimeoutError()
.22:02:17.301 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=1 retry_in=0.00s timeout=0.1 reason=TimeoutError error=TimeoutError()
22:02:17.302 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=2 retry_in=0.00s timeout=0.30000000000000004 reason=TimeoutError error=TimeoutError()
22:02:17.304 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=3 retry_in=0.00s timeout=0.5 reason=TimeoutError error=TimeoutError()
22:02:17.305 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=4 retry_in=0.00s timeout=0.5 reason=TimeoutError error=TimeoutError()
.........22:02:17.681 [WARNING][asyncio] Executing <Task pending name='Task-1045' coro=<LocalReplayTests.test_export_sample_routes_extracts_indexes_and_injects_without_live_calls() running at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_realtime_entry.py:262> wait_for=<Future pending cb=[Task.task_wakeup()] created at /usr/lib/python3.12/asyncio/base_events.py:449> cb=[_run_until_complete_cb() at /usr/lib/python3.12/asyncio/base_events.py:182] created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.211 seconds
22:02:17.787 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=discord:arknights_main, messages=60, segments=1, seconds=0.00
22:02:17.805 [DEBUG][core.adapters.astrbot] [MessageRouter] waiting for 20 brain tasks to finish
22:02:17.811 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=discord:arknights_main, messages=60, segments=1, seconds=0.00
22:02:17.826 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=discord:arknights_main strategy=llm messages=60 partitions=1 events=2 low_conf=0 duration=0.049s ids=['679a6d65', 'f0f03c37']
22:02:17.831 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=discord:arknights_main strategy=llm messages=60 partitions=1 events=2 low_conf=0 duration=0.020s ids=['4c8eec53', 'e85b6cdd']
.................22:02:17.904 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e2
22:02:17.904 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e3
22:02:17.904 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e4
....22:02:18.023 [WARNING][core.repository.sqlite] [db_open] adopting existing 3-dimensional vectors as first; rebuild them if they came from another model
.....22:02:18.234 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: embedding endpoint unavailable at startup (embedding: HTTP 503)
..22:02:18.239 [WARNING][core.retrieval.hybrid] [HybridRetriever] model rerank unavailable: rerank: HTTP 503
.22:02:18.240 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: invalid embedding settings: Retrieval base URL must be an HTTP(S) endpoint without credentials
.22:02:18.241 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: invalid embedding settings: KCL retrieval models and API key must be configured
22:02:18.251 [ERROR][core.retrieval.providers] [Retrieval] model rerank disabled: invalid rerank settings: Retrieval base URL must be an HTTP(S) endpoint without credentials
...........22:02:18.309 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=t:dm strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['fdb90c24']
............
----------------------------------------------------------------------
Ran 455 tests in 9.923s

OK (skipped=1)
[Config] Loaded run_config.py  (model_type=kcl)
[Dev] 旧会话没有评价开关记录；保留历史事件，本次重新提取默认关闭评价。
[Dev] 评价开关记录无法读取；本次重新提取默认关闭评价。
[Archive] Resuming — keeping existing realtime_test.db in place.
[Archive] Moved stale realtime_test.db → realtime_test_stale_20261006_220217.db
[Archive] Resuming — keeping existing realtime_test.db in place.
[Archive] Moved stale realtime_test.db → realtime_test_stale_20261006_220217.db
[Config] --set RETRIEVAL_ENCODER_CONCURRENCY=1 (not in run_config.py)
[Config] --set RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS=1000 (not in run_config.py)
[Config] --set RETRIEVAL_ENCODER_RETRY_MAX=6 (not in run_config.py)
[Config] --set EXTRACTION_LLM_SEGMENTATION=False (not in run_config.py)
[Config] --set BOUNDARY_TOPIC_DRIFT_PERCENTILE=90 (not in run_config.py)
```

### Storage/event-handler checkpoint

Directory: `.`. Exit: `0`.

```bash
PYTHONPATH=core/src moirai/.venv/bin/python scripts/verify-event-runtime.py
```

```text
test_actual_oedipus_query_consumes_public_input (__main__.JointEventTests.test_actual_oedipus_query_consumes_public_input) ... ok
test_every_injection_position_and_fallback (__main__.JointEventTests.test_every_injection_position_and_fallback) ... ok
test_extraction_keeps_scope_when_persona_summary_is_disabled (__main__.JointEventTests.test_extraction_keeps_scope_when_persona_summary_is_disabled) ... [EventExtractor] LLM provider is None; falling back to rule-based extraction
[EventExtractor] event fell back to rule extraction: reason=provider_none, session=isolated-extraction, message_count=1
ok
test_host_persona_instructions_reach_only_deferred_eval (__main__.JointEventTests.test_host_persona_instructions_reach_only_deferred_eval) ... ok
test_missing_mapping_never_becomes_aggregate (__main__.JointEventTests.test_missing_mapping_never_becomes_aggregate) ... Event turn:one:before_generation extension moirai: failed
ok
test_namespace_cleanup_and_debug_are_request_bound (__main__.JointEventTests.test_namespace_cleanup_and_debug_are_request_bound) ... ok
test_parent_expansion_cannot_cross_persona_or_channel (__main__.JointEventTests.test_parent_expansion_cannot_cross_persona_or_channel) ... ok
test_persona_eval_pass_does_not_shift_tags_or_salience (__main__.JointEventTests.test_persona_eval_pass_does_not_shift_tags_or_salience) ... ok
test_real_recall_keeps_personas_separate (__main__.JointEventTests.test_real_recall_keeps_personas_separate) ... ok
test_sqlite_persona_filters_and_vector_identity (__main__.JointEventTests.test_sqlite_persona_filters_and_vector_identity) ... ok
test_sqlite_scope_is_applied_before_candidate_limit (__main__.JointEventTests.test_sqlite_scope_is_applied_before_candidate_limit) ... ok
test_switch_and_late_reply_do_not_mix_windows (__main__.JointEventTests.test_switch_and_late_reply_do_not_mix_windows) ... ok
test_unavailable_dependency_pauses_event_handling (__main__.JointEventTests.test_unavailable_dependency_pauses_event_handling) ... ok
test_actual_oedipus_query_consumes_public_input (__main__.JointGenerationTests.test_actual_oedipus_query_consumes_public_input) ... ok
test_canon_tools_and_review_run_through_core (__main__.JointGenerationTests.test_canon_tools_and_review_run_through_core) ... ok
test_every_injection_position_and_fallback (__main__.JointGenerationTests.test_every_injection_position_and_fallback) ... ok
test_extraction_keeps_scope_when_persona_summary_is_disabled (__main__.JointGenerationTests.test_extraction_keeps_scope_when_persona_summary_is_disabled) ... [EventExtractor] event fell back to rule extraction: reason=provider_none, session=isolated-extraction, message_count=1
ok
test_host_persona_instructions_reach_only_deferred_eval (__main__.JointGenerationTests.test_host_persona_instructions_reach_only_deferred_eval) ... ok
test_missing_mapping_never_becomes_aggregate (__main__.JointGenerationTests.test_missing_mapping_never_becomes_aggregate) ... Event turn:one:before_generation extension moirai: failed
ok
test_namespace_cleanup_and_debug_are_request_bound (__main__.JointGenerationTests.test_namespace_cleanup_and_debug_are_request_bound) ... ok
test_parent_expansion_cannot_cross_persona_or_channel (__main__.JointGenerationTests.test_parent_expansion_cannot_cross_persona_or_channel) ... ok
test_persona_eval_pass_does_not_shift_tags_or_salience (__main__.JointGenerationTests.test_persona_eval_pass_does_not_shift_tags_or_salience) ... ok
test_real_recall_keeps_personas_separate (__main__.JointGenerationTests.test_real_recall_keeps_personas_separate) ... ok
test_sqlite_persona_filters_and_vector_identity (__main__.JointGenerationTests.test_sqlite_persona_filters_and_vector_identity) ... ok
test_sqlite_scope_is_applied_before_candidate_limit (__main__.JointGenerationTests.test_sqlite_scope_is_applied_before_candidate_limit) ... ok
test_switch_and_late_reply_do_not_mix_windows (__main__.JointGenerationTests.test_switch_and_late_reply_do_not_mix_windows) ... ok
test_unavailable_dependency_pauses_event_handling (__main__.JointGenerationTests.test_unavailable_dependency_pauses_event_handling) ... ok
test_unmapped_persona_gets_memory_but_no_canon (__main__.JointGenerationTests.test_unmapped_persona_gets_memory_but_no_canon) ... ok

----------------------------------------------------------------------
Ran 28 tests in 0.555s

OK
```

### Initial loop test: fixture failure

Directory: `moirai`. Exit: `1`.

```bash
PYTHONPATH=.:tests/mocks .venv/bin/python -m unittest discover -s tests -p 'test_turn_loop.py'
```

```text
............[EventExtractor] LLM provider is None; falling back to rule-based extraction
[EventExtractor] event fell back to rule extraction: reason=provider_none, session=test:dm, message_count=1
..F
======================================================================
FAIL: test_semantic_ranking_reuses_the_existing_encoder (test_turn_loop.LoopTests.test_semantic_ranking_reuses_the_existing_encoder)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/usr/lib/python3.12/unittest/async_case.py", line 90, in _callTestMethod
    if self._callMaybeAsync(method) is not None:
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/unittest/async_case.py", line 112, in _callMaybeAsync
    return self._asyncioRunner.run(
           ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete
    return future.result()
           ^^^^^^^^^^^^^^^
  File "/home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_turn_loop.py", line 229, in test_semantic_ranking_reuses_the_existing_encoder
    self.assertNotIn("带伞", text)
AssertionError: '带伞' unexpectedly found in '[你对这个人尚未完成的约定]\n- 帮你备好晚饭\n- 下次带伞'

----------------------------------------------------------------------
Ran 15 tests in 0.714s

FAILED (failures=1)
```

### Corrected loop test

Directory: `moirai`. Exit: `0`.

```bash
PYTHONPATH=.:tests/mocks .venv/bin/python -m unittest discover -s tests -p 'test_turn_loop.py'
```

```text
............[EventExtractor] LLM provider is None; falling back to rule-based extraction
[EventExtractor] event fell back to rule extraction: reason=provider_none, session=test:dm, message_count=1
...
----------------------------------------------------------------------
Ran 15 tests in 0.721s

OK
```

### First complete suite after wiring

Directory: `moirai`. Exit: `0`.

```bash
PYTHONPATH=.:tests/mocks .venv/bin/python -m unittest discover -s tests -p "test_*.py"
```

```text
..22:11:57.589 [WARNING][core.social.big_five_scorer] [BigFiveScorer] scoring failed: busy
.22:11:57.590 [WARNING][core.utils.model_retry] [ModelRetry] task=big_five_score attempt=1 retry_in=0.00s timeout=30.0 reason=HTTPStatusError error=busy
22:11:57.590 [WARNING][core.utils.model_retry] [ModelRetry] task=big_five_score attempt=2 retry_in=0.00s timeout=30.0 reason=ModelOutputError error=Invalid Big Five result
...........22:11:58.313 [WARNING][asyncio] Executing <Task finished name='Task-41' coro=<BenchTests.test_http_error_carries_response_body() done, defined at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_canon.py:886> result=None created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.496 seconds
..22:11:58.949 [WARNING][asyncio] Executing <Task finished name='Task-53' coro=<BenchTests.test_replay_goes_through_real_http_client() done, defined at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_canon.py:860> result=None created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.473 seconds
.................22:12:00.654 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 1): 调用失败：超过 0.05 秒没有返回
22:12:00.705 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 2): 调用失败：超过 0.05 秒没有返回
22:12:00.756 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 3): 调用失败：超过 0.05 秒没有返回
22:12:00.807 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 4): 调用失败：超过 0.05 秒没有返回
.......................................................................................................................................................................s...........................................................................22:12:03.826 [WARNING][core.extractor.category_pass] [CategoryPass] classification failed for e1: TypeSafe HTTP 500: error
..22:12:03.829 [WARNING][core.extractor.category_pass] [CategoryPass] incomplete interaction groups for e1; event result not stored
.................22:12:03.881 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:12:03.882 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['708f2a9a']
.22:12:03.905 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['e3f0c858']
.................22:12:04.265 [ERROR][core.utils.typesafe] [TypeSafe] API key rejected (401); disabling classification for this process.
....22:12:04.268 [WARNING][core.utils.typesafe] [TypeSafe] attempt 1/3 failed (TypeSafe HTTP 529: busy); retrying in 0.0s
.....22:12:04.273 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:12:04.274 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['fa9412ad']
..22:12:04.276 [WARNING][core.extractor.extractor] [EventExtractor] LLM extraction parse_error; attempting JSON repair (session=test:group, message_count=2, snippet='not json')
....22:12:04.279 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:12:04.280 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['c4529edf']
22:12:04.281 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['ebbfbd82']
.....22:12:04.285 [WARNING][core.extractor.extractor] [EventExtractor] LLM extraction parse_error; attempting JSON repair (session=test:group, message_count=2, snippet='not json')
22:12:04.285 [WARNING][core.extractor.extractor] [EventExtractor] JSON repair parse_error; falling back (session=test:group, message_count=2, repair_snippet='not json')
22:12:04.285 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=parse_error, session=test:group, message_count=2, retries_used=0
22:12:04.285 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.000s ids=['ecccb192']
.22:12:04.286 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/3 (session=test:group, message_count=2)
22:12:04.286 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['0bf0d787']
.22:12:04.287 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/3 (session=test:group, message_count=2)
22:12:04.287 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 3/3 (session=test:group, message_count=2)
22:12:04.287 [WARNING][core.extractor.extractor] [EventExtractor] LLM batch extraction timed out (retries_used=0)
22:12:04.288 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=timeout, session=test:group, message_count=2, retries_used=0
22:12:04.288 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.000s ids=['234903c1']
..22:12:04.289 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 600s before attempt 2/3 (session=test:group, message_count=2)
22:12:04.289 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:group, message_count=2
22:12:04.289 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.000s ids=['77de72b6']
.........22:12:04.291 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'hold' (priority=10, active=1)
22:12:04.291 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'hold' finished in 0.00s
22:12:04.291 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'after' (priority=10, active=1)
22:12:04.291 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'after' finished in 0.00s
.22:12:04.292 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'hold' (priority=10, active=1)
22:12:04.292 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'hold' finished in 0.00s
22:12:04.293 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'synthesis' (priority=10, active=1)
22:12:04.293 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'synthesis' finished in 0.00s
22:12:04.293 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'synthesis' (priority=10, active=1)
22:12:04.293 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'synthesis' finished in 0.00s
22:12:04.293 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'eval' (priority=20, active=1)
22:12:04.293 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'eval' finished in 0.00s
22:12:04.293 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'eval' (priority=20, active=1)
22:12:04.293 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'eval' finished in 0.00s
.22:12:04.294 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=1)
22:12:04.294 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=2)
22:12:04.294 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=3)
22:12:04.305 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:12:04.305 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:12:04.305 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:12:04.305 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=1)
22:12:04.305 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=2)
22:12:04.305 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=3)
22:12:04.316 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:12:04.316 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:12:04.316 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:12:04.316 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=1)
22:12:04.316 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=2)
22:12:04.316 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=3)
22:12:04.326 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:12:04.327 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:12:04.327 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
...........................22:12:06.085 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.00, reason=unavailable
22:12:06.086 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=41 partitions=1 events=3 low_conf=0 duration=0.001s ids=['71d556aa', 'fdc9430b', '166932ca']
22:12:06.087 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.00, reason=segmentation requires a segments array
22:12:06.088 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=41 partitions=1 events=3 low_conf=0 duration=0.001s ids=['85154f87', '4372c997', 'f11b3963']
.22:12:06.090 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=25 partitions=1 events=3 low_conf=0 duration=0.001s ids=['6533d315', 'd0d9fa27', '86c82cf0']
.22:12:06.091 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/2 (session=test:dm, message_count=25)
22:12:06.092 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=25 partitions=1 events=3 low_conf=0 duration=0.001s ids=['f3ed717b', '148eb786', '94251af6']
.22:12:06.093 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=45, segments=1, seconds=0.00
22:12:06.093 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=45 partitions=1 events=3 low_conf=0 duration=0.001s ids=['a6bae09b', '4c4e5354', 'b8ea0c90']
.22:12:06.094 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=24, segments=2, seconds=0.00
22:12:06.095 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=24 partitions=1 events=4 low_conf=0 duration=0.001s ids=['8b9d1038', '08a54d3d', '27a836b4', '8508025f']
.22:12:06.096 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:12:06.096 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:12:06.096 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:12:06.096 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=45 partitions=1 events=3 low_conf=3 duration=0.001s ids=['0bf746cb', 'e6d24b99', 'd3d77ba3']
.22:12:06.198 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.10, reason=
.22:12:06.199 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=11 partitions=1 events=1 low_conf=0 duration=0.000s ids=['6c8c3ffb']
22:12:06.200 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=20 partitions=1 events=1 low_conf=0 duration=0.001s ids=['5fd90fb6']
.22:12:06.201 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=24, segments=2, seconds=0.00
......22:12:06.314 [WARNING][core.utils.model_retry] [ModelRetry] task=segmentation attempt=1 retry_in=0.00s timeout=0.1 reason=TimeoutError error=TimeoutError()
22:12:06.435 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=12, segments=1, seconds=0.22
...22:12:06.458 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=1 retry_in=0.00s timeout=0.02 reason=TimeoutError error=TimeoutError()
22:12:06.499 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=2 retry_in=0.00s timeout=0.04 reason=TimeoutError error=TimeoutError()
.22:12:06.551 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=1 retry_in=0.00s timeout=0.1 reason=TimeoutError error=TimeoutError()
22:12:06.553 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=2 retry_in=0.00s timeout=0.30000000000000004 reason=TimeoutError error=TimeoutError()
22:12:06.554 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=3 retry_in=0.00s timeout=0.5 reason=TimeoutError error=TimeoutError()
22:12:06.555 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=4 retry_in=0.00s timeout=0.5 reason=TimeoutError error=TimeoutError()
.........22:12:06.841 [WARNING][asyncio] Executing <Task pending name='Task-1045' coro=<LocalReplayTests.test_export_sample_routes_extracts_indexes_and_injects_without_live_calls() running at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_realtime_entry.py:262> wait_for=<Future pending cb=[Task.task_wakeup()] created at /usr/lib/python3.12/asyncio/base_events.py:449> cb=[_run_until_complete_cb() at /usr/lib/python3.12/asyncio/base_events.py:182] created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.120 seconds
22:12:06.962 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=discord:arknights_main, messages=60, segments=1, seconds=0.00
22:12:06.979 [DEBUG][core.adapters.astrbot] [MessageRouter] waiting for 20 brain tasks to finish
22:12:06.985 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=discord:arknights_main, messages=60, segments=1, seconds=0.00
22:12:07.000 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=discord:arknights_main strategy=llm messages=60 partitions=1 events=2 low_conf=0 duration=0.055s ids=['943b76a4', 'e2c2b53c']
22:12:07.002 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=discord:arknights_main strategy=llm messages=60 partitions=1 events=2 low_conf=0 duration=0.018s ids=['9e81f227', '6e89366b']
.................22:12:07.075 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e2
22:12:07.076 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e3
22:12:07.076 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e4
....22:12:07.202 [WARNING][core.repository.sqlite] [db_open] adopting existing 3-dimensional vectors as first; rebuild them if they came from another model
.....22:12:07.444 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: embedding endpoint unavailable at startup (embedding: HTTP 503)
..22:12:07.449 [WARNING][core.retrieval.hybrid] [HybridRetriever] model rerank unavailable: rerank: HTTP 503
.22:12:07.451 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: invalid embedding settings: Retrieval base URL must be an HTTP(S) endpoint without credentials
.22:12:07.452 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: invalid embedding settings: KCL retrieval models and API key must be configured
22:12:07.467 [ERROR][core.retrieval.providers] [Retrieval] model rerank disabled: invalid rerank settings: Retrieval base URL must be an HTTP(S) endpoint without credentials
...........22:12:07.527 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=t:dm strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['2060a613']
........................22:12:08.227 [WARNING][core.extractor.extractor] [EventExtractor] LLM provider is None; falling back to rule-based extraction
22:12:08.228 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=provider_none, session=test:dm, message_count=1
22:12:08.228 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=1 partitions=1 events=1 low_conf=1 duration=0.001s ids=['4a4ca41d']
.22:12:08.291 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.002s ids=['4c3bd641']
..
----------------------------------------------------------------------
Ran 470 tests in 10.764s

OK (skipped=1)
[Config] Loaded run_config.py  (model_type=kcl)
[Dev] 旧会话没有评价开关记录；保留历史事件，本次重新提取默认关闭评价。
[Dev] 评价开关记录无法读取；本次重新提取默认关闭评价。
[Archive] Resuming — keeping existing realtime_test.db in place.
[Archive] Moved stale realtime_test.db → realtime_test_stale_20261006_221206.db
[Archive] Resuming — keeping existing realtime_test.db in place.
[Archive] Moved stale realtime_test.db → realtime_test_stale_20261006_221206.db
[Config] --set RETRIEVAL_ENCODER_CONCURRENCY=1 (not in run_config.py)
[Config] --set RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS=1000 (not in run_config.py)
[Config] --set RETRIEVAL_ENCODER_RETRY_MAX=6 (not in run_config.py)
[Config] --set EXTRACTION_LLM_SEGMENTATION=False (not in run_config.py)
[Config] --set BOUNDARY_TOPIC_DRIFT_PERCENTILE=90 (not in run_config.py)
```

### Expanded loop boundary cases

Directory: `moirai`. Exit: `0`.

```bash
PYTHONPATH=.:tests/mocks .venv/bin/python -m unittest discover -s tests -p 'test_turn_loop.py'
```

```text
.............[EventExtractor] LLM provider is None; falling back to rule-based extraction
[EventExtractor] event fell back to rule extraction: reason=provider_none, session=test:dm, message_count=1
..[SemanticPartitioner] scikit-learn is not installed. Falling back to single partition. Run `pip install scikit-learn` to enable semantic clustering.
..
----------------------------------------------------------------------
Ran 17 tests in 0.907s

OK
```

### Frontend type check

Directory: `moirai/web/frontend`. Exit: `0`.

```bash
node node_modules/typescript/bin/tsc --noEmit --incremental false
```

Output: empty.

### Initial event-summary component render

Directory: `moirai`. Exit: `0`.

```bash
node tests/event-summary-ui.cjs
```

```text
✔ legacy sample renders all seven topics without How or Eval (0.824691ms)
✔ partial topics preserve brackets, literal pipes and evaluation ownership (0.143608ms)
✔ plain or mixed unstructured summaries fall back without dropping text (0.114747ms)
✔ field markers accept case and omitted topic separators (0.114219ms)
✔ actual event detail renders neutral sample without a fake evaluation row (247.32559ms)
✔ actual event detail renders only the evaluation of its own topic as text (2.224838ms)
✔ database event details also hide absent evaluations and show all topics (30.967184ms)
ℹ tests 7
ℹ suites 0
ℹ pass 7
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 286.073954
```

### Final event-summary/persona-view component render

Directory: `moirai`. Exit: `0`.

```bash
node tests/event-summary-ui.cjs
```

```text
✔ legacy sample renders all seven topics without How or Eval (0.985936ms)
✔ partial topics preserve brackets, literal pipes and evaluation ownership (0.158379ms)
✔ plain or mixed unstructured summaries fall back without dropping text (0.093235ms)
✔ field markers accept case and omitted topic separators (1.195619ms)
✔ actual event detail renders neutral sample without a fake evaluation row (216.403139ms)
✔ actual event detail renders only the evaluation of its own topic as text (2.726421ms)
✔ actual event detail shows persona view separately and escapes annotation text (2.380886ms)
✔ database event details also hide absent evaluations and show all topics (35.110724ms)
ℹ tests 8
ℹ suites 0
ℹ pass 8
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 269.303854
```

### Joint event check before the last router adjustment

Directory: `.`. Exit: `0`.

```bash
PYTHONPATH=core/src moirai/.venv/bin/python scripts/verify-event-runtime.py
```

```text
test_actual_oedipus_query_consumes_public_input (__main__.JointEventTests.test_actual_oedipus_query_consumes_public_input) ... ok
test_every_injection_position_and_fallback (__main__.JointEventTests.test_every_injection_position_and_fallback) ... ok
test_extraction_keeps_scope_when_persona_summary_is_disabled (__main__.JointEventTests.test_extraction_keeps_scope_when_persona_summary_is_disabled) ... [EventExtractor] LLM provider is None; falling back to rule-based extraction
[EventExtractor] event fell back to rule extraction: reason=provider_none, session=isolated-extraction, message_count=1
ok
test_host_persona_instructions_reach_only_deferred_eval (__main__.JointEventTests.test_host_persona_instructions_reach_only_deferred_eval) ... ok
test_missing_mapping_never_becomes_aggregate (__main__.JointEventTests.test_missing_mapping_never_becomes_aggregate) ... Event turn:one:before_generation extension moirai: failed
ok
test_namespace_cleanup_and_debug_are_request_bound (__main__.JointEventTests.test_namespace_cleanup_and_debug_are_request_bound) ... ok
test_parent_expansion_cannot_cross_persona_or_channel (__main__.JointEventTests.test_parent_expansion_cannot_cross_persona_or_channel) ... ok
test_persona_eval_pass_does_not_shift_tags_or_salience (__main__.JointEventTests.test_persona_eval_pass_does_not_shift_tags_or_salience) ... ok
test_real_recall_keeps_personas_separate (__main__.JointEventTests.test_real_recall_keeps_personas_separate) ... ok
test_sqlite_persona_filters_and_vector_identity (__main__.JointEventTests.test_sqlite_persona_filters_and_vector_identity) ... ok
test_sqlite_scope_is_applied_before_candidate_limit (__main__.JointEventTests.test_sqlite_scope_is_applied_before_candidate_limit) ... ok
test_switch_and_late_reply_do_not_mix_windows (__main__.JointEventTests.test_switch_and_late_reply_do_not_mix_windows) ... ok
test_unavailable_dependency_pauses_event_handling (__main__.JointEventTests.test_unavailable_dependency_pauses_event_handling) ... ok
test_actual_oedipus_query_consumes_public_input (__main__.JointGenerationTests.test_actual_oedipus_query_consumes_public_input) ... ok
test_canon_tools_and_review_run_through_core (__main__.JointGenerationTests.test_canon_tools_and_review_run_through_core) ... ok
test_every_injection_position_and_fallback (__main__.JointGenerationTests.test_every_injection_position_and_fallback) ... ok
test_extraction_keeps_scope_when_persona_summary_is_disabled (__main__.JointGenerationTests.test_extraction_keeps_scope_when_persona_summary_is_disabled) ... [EventExtractor] event fell back to rule extraction: reason=provider_none, session=isolated-extraction, message_count=1
ok
test_host_persona_instructions_reach_only_deferred_eval (__main__.JointGenerationTests.test_host_persona_instructions_reach_only_deferred_eval) ... ok
test_missing_mapping_never_becomes_aggregate (__main__.JointGenerationTests.test_missing_mapping_never_becomes_aggregate) ... Event turn:one:before_generation extension moirai: failed
ok
test_namespace_cleanup_and_debug_are_request_bound (__main__.JointGenerationTests.test_namespace_cleanup_and_debug_are_request_bound) ... ok
test_parent_expansion_cannot_cross_persona_or_channel (__main__.JointGenerationTests.test_parent_expansion_cannot_cross_persona_or_channel) ... ok
test_persona_eval_pass_does_not_shift_tags_or_salience (__main__.JointGenerationTests.test_persona_eval_pass_does_not_shift_tags_or_salience) ... ok
test_real_recall_keeps_personas_separate (__main__.JointGenerationTests.test_real_recall_keeps_personas_separate) ... ok
test_sqlite_persona_filters_and_vector_identity (__main__.JointGenerationTests.test_sqlite_persona_filters_and_vector_identity) ... ok
test_sqlite_scope_is_applied_before_candidate_limit (__main__.JointGenerationTests.test_sqlite_scope_is_applied_before_candidate_limit) ... ok
test_switch_and_late_reply_do_not_mix_windows (__main__.JointGenerationTests.test_switch_and_late_reply_do_not_mix_windows) ... ok
test_unavailable_dependency_pauses_event_handling (__main__.JointGenerationTests.test_unavailable_dependency_pauses_event_handling) ... ok
test_unmapped_persona_gets_memory_but_no_canon (__main__.JointGenerationTests.test_unmapped_persona_gets_memory_but_no_canon) ... ok

----------------------------------------------------------------------
Ran 28 tests in 0.574s

OK
```

### Complete suite before the last router adjustment

Directory: `moirai`. Exit: `0`.

```bash
PYTHONPATH=.:tests/mocks .venv/bin/python -m unittest discover -s tests -p "test_*.py"
```

```text
..22:14:34.688 [WARNING][core.social.big_five_scorer] [BigFiveScorer] scoring failed: busy
.22:14:34.689 [WARNING][core.utils.model_retry] [ModelRetry] task=big_five_score attempt=1 retry_in=0.00s timeout=30.0 reason=HTTPStatusError error=busy
22:14:34.690 [WARNING][core.utils.model_retry] [ModelRetry] task=big_five_score attempt=2 retry_in=0.00s timeout=30.0 reason=ModelOutputError error=Invalid Big Five result
...........22:14:35.427 [WARNING][asyncio] Executing <Task finished name='Task-41' coro=<BenchTests.test_http_error_carries_response_body() done, defined at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_canon.py:886> result=None created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.495 seconds
..22:14:36.061 [WARNING][asyncio] Executing <Task finished name='Task-53' coro=<BenchTests.test_replay_goes_through_real_http_client() done, defined at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_canon.py:860> result=None created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.479 seconds
.................22:14:37.746 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 1): 调用失败：超过 0.05 秒没有返回
22:14:37.797 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 2): 调用失败：超过 0.05 秒没有返回
22:14:37.848 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 3): 调用失败：超过 0.05 秒没有返回
22:14:37.898 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 4): 调用失败：超过 0.05 秒没有返回
.......................................................................................................................................................................s...........................................................................22:14:40.894 [WARNING][core.extractor.category_pass] [CategoryPass] classification failed for e1: TypeSafe HTTP 500: error
..22:14:40.896 [WARNING][core.extractor.category_pass] [CategoryPass] incomplete interaction groups for e1; event result not stored
.................22:14:40.951 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:14:40.952 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['3a0261d9']
.22:14:40.977 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['c64455c9']
.................22:14:41.343 [ERROR][core.utils.typesafe] [TypeSafe] API key rejected (401); disabling classification for this process.
....22:14:41.347 [WARNING][core.utils.typesafe] [TypeSafe] attempt 1/3 failed (TypeSafe HTTP 529: busy); retrying in 0.0s
.....22:14:41.353 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:14:41.354 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['1be655f1']
..22:14:41.356 [WARNING][core.extractor.extractor] [EventExtractor] LLM extraction parse_error; attempting JSON repair (session=test:group, message_count=2, snippet='not json')
....22:14:41.360 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:14:41.360 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['3e83cd59']
22:14:41.361 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['772159d2']
.....22:14:41.366 [WARNING][core.extractor.extractor] [EventExtractor] LLM extraction parse_error; attempting JSON repair (session=test:group, message_count=2, snippet='not json')
22:14:41.366 [WARNING][core.extractor.extractor] [EventExtractor] JSON repair parse_error; falling back (session=test:group, message_count=2, repair_snippet='not json')
22:14:41.366 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=parse_error, session=test:group, message_count=2, retries_used=0
22:14:41.366 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.001s ids=['20ac9f0b']
.22:14:41.367 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/3 (session=test:group, message_count=2)
22:14:41.367 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['bcf3de12']
.22:14:41.368 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/3 (session=test:group, message_count=2)
22:14:41.368 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 3/3 (session=test:group, message_count=2)
22:14:41.369 [WARNING][core.extractor.extractor] [EventExtractor] LLM batch extraction timed out (retries_used=0)
22:14:41.369 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=timeout, session=test:group, message_count=2, retries_used=0
22:14:41.369 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.000s ids=['1ed71faa']
..22:14:41.370 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 600s before attempt 2/3 (session=test:group, message_count=2)
22:14:41.371 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:group, message_count=2
22:14:41.371 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.000s ids=['3b1b1f72']
.........22:14:41.372 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'hold' (priority=10, active=1)
22:14:41.373 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'hold' finished in 0.00s
22:14:41.373 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'after' (priority=10, active=1)
22:14:41.373 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'after' finished in 0.00s
.22:14:41.374 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'hold' (priority=10, active=1)
22:14:41.374 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'hold' finished in 0.00s
22:14:41.374 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'synthesis' (priority=10, active=1)
22:14:41.377 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'synthesis' finished in 0.00s
22:14:41.378 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'synthesis' (priority=10, active=1)
22:14:41.378 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'synthesis' finished in 0.00s
22:14:41.378 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'eval' (priority=20, active=1)
22:14:41.378 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'eval' finished in 0.00s
22:14:41.378 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'eval' (priority=20, active=1)
22:14:41.378 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'eval' finished in 0.00s
.22:14:41.379 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=1)
22:14:41.379 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=2)
22:14:41.379 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=3)
22:14:41.390 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:14:41.390 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:14:41.390 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:14:41.390 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=1)
22:14:41.390 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=2)
22:14:41.390 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=3)
22:14:41.401 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:14:41.401 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:14:41.401 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:14:41.401 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=1)
22:14:41.401 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=2)
22:14:41.401 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=3)
22:14:41.412 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:14:41.412 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:14:41.412 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
...........................22:14:43.218 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.00, reason=unavailable
22:14:43.219 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=41 partitions=1 events=3 low_conf=0 duration=0.001s ids=['02bf6ea1', 'd5753758', '8720cdc5']
22:14:43.219 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.00, reason=segmentation requires a segments array
22:14:43.220 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=41 partitions=1 events=3 low_conf=0 duration=0.001s ids=['b4f03178', '90b75cd9', '9f8c76e3']
.22:14:43.222 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=25 partitions=1 events=3 low_conf=0 duration=0.001s ids=['0b5d3db7', '2855eab8', '3b0b4252']
.22:14:43.223 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/2 (session=test:dm, message_count=25)
22:14:43.224 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=25 partitions=1 events=3 low_conf=0 duration=0.001s ids=['236a40ec', '7028655d', 'ec6b37cd']
.22:14:43.225 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=45, segments=1, seconds=0.00
22:14:43.225 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=45 partitions=1 events=3 low_conf=0 duration=0.001s ids=['653441c9', 'a3e7c339', '001c1527']
.22:14:43.226 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=24, segments=2, seconds=0.00
22:14:43.227 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=24 partitions=1 events=4 low_conf=0 duration=0.001s ids=['6bf9184e', 'dd8e6e57', '8013425f', '4d5e79b9']
.22:14:43.228 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:14:43.228 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:14:43.228 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:14:43.228 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=45 partitions=1 events=3 low_conf=3 duration=0.001s ids=['8a0b0d27', '18a3e96e', 'a7824a6d']
.22:14:43.330 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.10, reason=
.22:14:43.332 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=11 partitions=1 events=1 low_conf=0 duration=0.000s ids=['fa0987b6']
22:14:43.332 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=20 partitions=1 events=1 low_conf=0 duration=0.001s ids=['ebf507da']
.22:14:43.333 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=24, segments=2, seconds=0.00
......22:14:43.446 [WARNING][core.utils.model_retry] [ModelRetry] task=segmentation attempt=1 retry_in=0.00s timeout=0.1 reason=TimeoutError error=TimeoutError()
22:14:43.567 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=12, segments=1, seconds=0.22
...22:14:43.590 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=1 retry_in=0.00s timeout=0.02 reason=TimeoutError error=TimeoutError()
22:14:43.631 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=2 retry_in=0.00s timeout=0.04 reason=TimeoutError error=TimeoutError()
.22:14:43.684 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=1 retry_in=0.00s timeout=0.1 reason=TimeoutError error=TimeoutError()
22:14:43.685 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=2 retry_in=0.00s timeout=0.30000000000000004 reason=TimeoutError error=TimeoutError()
22:14:43.686 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=3 retry_in=0.00s timeout=0.5 reason=TimeoutError error=TimeoutError()
22:14:43.687 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=4 retry_in=0.00s timeout=0.5 reason=TimeoutError error=TimeoutError()
.........22:14:43.964 [WARNING][asyncio] Executing <Task pending name='Task-1045' coro=<LocalReplayTests.test_export_sample_routes_extracts_indexes_and_injects_without_live_calls() running at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_realtime_entry.py:262> wait_for=<Future pending cb=[Task.task_wakeup()] created at /usr/lib/python3.12/asyncio/base_events.py:449> cb=[_run_until_complete_cb() at /usr/lib/python3.12/asyncio/base_events.py:182] created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.106 seconds
22:14:44.075 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=discord:arknights_main, messages=60, segments=1, seconds=0.00
22:14:44.095 [DEBUG][core.adapters.astrbot] [MessageRouter] waiting for 20 brain tasks to finish
22:14:44.100 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=discord:arknights_main, messages=60, segments=1, seconds=0.00
22:14:44.115 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=discord:arknights_main strategy=llm messages=60 partitions=1 events=2 low_conf=0 duration=0.050s ids=['09c1fec3', '74223903']
22:14:44.118 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=discord:arknights_main strategy=llm messages=60 partitions=1 events=2 low_conf=0 duration=0.018s ids=['7f0332cc', 'a5f35aed']
.................22:14:44.192 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e2
22:14:44.192 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e3
22:14:44.192 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e4
....22:14:44.312 [WARNING][core.repository.sqlite] [db_open] adopting existing 3-dimensional vectors as first; rebuild them if they came from another model
.....22:14:44.544 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: embedding endpoint unavailable at startup (embedding: HTTP 503)
..22:14:44.549 [WARNING][core.retrieval.hybrid] [HybridRetriever] model rerank unavailable: rerank: HTTP 503
.22:14:44.550 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: invalid embedding settings: Retrieval base URL must be an HTTP(S) endpoint without credentials
.22:14:44.551 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: invalid embedding settings: KCL retrieval models and API key must be configured
22:14:44.562 [ERROR][core.retrieval.providers] [Retrieval] model rerank disabled: invalid rerank settings: Retrieval base URL must be an HTTP(S) endpoint without credentials
...........22:14:44.621 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=t:dm strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['9e1da562']
.........................22:14:45.383 [WARNING][core.extractor.extractor] [EventExtractor] LLM provider is None; falling back to rule-based extraction
22:14:45.383 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=provider_none, session=test:dm, message_count=1
22:14:45.384 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=1 partitions=1 events=1 low_conf=1 duration=0.002s ids=['0210864d']
.22:14:45.440 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.002s ids=['42e9b69e']
.22:14:45.499 [WARNING][core.extractor.partitioner] [SemanticPartitioner] scikit-learn is not installed. Falling back to single partition. Run `pip install scikit-learn` to enable semantic clustering.
22:14:45.501 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=semantic messages=2 partitions=1 events=1 low_conf=0 duration=0.003s ids=['d482d14a']
..
----------------------------------------------------------------------
Ran 472 tests in 10.878s

OK (skipped=1)
[Config] Loaded run_config.py  (model_type=kcl)
[Dev] 旧会话没有评价开关记录；保留历史事件，本次重新提取默认关闭评价。
[Dev] 评价开关记录无法读取；本次重新提取默认关闭评价。
[Archive] Resuming — keeping existing realtime_test.db in place.
[Archive] Moved stale realtime_test.db → realtime_test_stale_20261006_221443.db
[Archive] Resuming — keeping existing realtime_test.db in place.
[Archive] Moved stale realtime_test.db → realtime_test_stale_20261006_221443.db
[Config] --set RETRIEVAL_ENCODER_CONCURRENCY=1 (not in run_config.py)
[Config] --set RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS=1000 (not in run_config.py)
[Config] --set RETRIEVAL_ENCODER_RETRY_MAX=6 (not in run_config.py)
[Config] --set EXTRACTION_LLM_SEGMENTATION=False (not in run_config.py)
[Config] --set BOUNDARY_TOPIC_DRIFT_PERCENTILE=90 (not in run_config.py)
```

### Final complete suite

Directory: `moirai`. Exit: `0`.

```bash
PYTHONPATH=.:tests/mocks .venv/bin/python -m unittest discover -s tests -p "test_*.py"
```

```text
..22:17:29.417 [WARNING][core.social.big_five_scorer] [BigFiveScorer] scoring failed: busy
.22:17:29.418 [WARNING][core.utils.model_retry] [ModelRetry] task=big_five_score attempt=1 retry_in=0.00s timeout=30.0 reason=HTTPStatusError error=busy
22:17:29.419 [WARNING][core.utils.model_retry] [ModelRetry] task=big_five_score attempt=2 retry_in=0.00s timeout=30.0 reason=ModelOutputError error=Invalid Big Five result
...........22:17:29.756 [WARNING][asyncio] Executing <Task pending name='Task-41' coro=<BenchTests.test_http_error_carries_response_body() running at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_canon.py:892> cb=[_run_until_complete_cb() at /usr/lib/python3.12/asyncio/base_events.py:182] created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.113 seconds
22:17:30.262 [WARNING][asyncio] Executing <Task finished name='Task-41' coro=<BenchTests.test_http_error_carries_response_body() done, defined at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_canon.py:886> result=None created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.495 seconds
..22:17:30.928 [WARNING][asyncio] Executing <Task finished name='Task-53' coro=<BenchTests.test_replay_goes_through_real_http_client() done, defined at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_canon.py:860> result=None created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.476 seconds
.................22:17:32.637 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 1): 调用失败：超过 0.05 秒没有返回
22:17:32.689 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 2): 调用失败：超过 0.05 秒没有返回
22:17:32.740 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 3): 调用失败：超过 0.05 秒没有返回
22:17:32.791 [WARNING][core.canon.extract] [canon] extraction call failed (attempt 4): 调用失败：超过 0.05 秒没有返回
.......................................................................................................................................................................s...........................................................................22:17:36.698 [WARNING][core.extractor.category_pass] [CategoryPass] classification failed for e1: TypeSafe HTTP 500: error
..22:17:36.701 [WARNING][core.extractor.category_pass] [CategoryPass] incomplete interaction groups for e1; event result not stored
.................22:17:36.759 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:17:36.760 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['a8cff588']
.22:17:36.785 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['05245261']
.................22:17:37.267 [ERROR][core.utils.typesafe] [TypeSafe] API key rejected (401); disabling classification for this process.
....22:17:37.270 [WARNING][core.utils.typesafe] [TypeSafe] attempt 1/3 failed (TypeSafe HTTP 529: busy); retrying in 0.0s
.....22:17:37.277 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:17:37.278 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['9422819f']
..22:17:37.280 [WARNING][core.extractor.extractor] [EventExtractor] LLM extraction parse_error; attempting JSON repair (session=test:group, message_count=2, snippet='not json')
....22:17:37.283 [DEBUG][core.extractor.extractor] [EventExtractor] [window-persona] no bot msg, using last_active_persona 'OldBot'
22:17:37.284 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['bfe6d4b0']
22:17:37.284 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.000s ids=['b2f2d0db']
.....22:17:37.289 [WARNING][core.extractor.extractor] [EventExtractor] LLM extraction parse_error; attempting JSON repair (session=test:group, message_count=2, snippet='not json')
22:17:37.290 [WARNING][core.extractor.extractor] [EventExtractor] JSON repair parse_error; falling back (session=test:group, message_count=2, repair_snippet='not json')
22:17:37.290 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=parse_error, session=test:group, message_count=2, retries_used=0
22:17:37.290 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.001s ids=['89bce9f4']
.22:17:37.291 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/3 (session=test:group, message_count=2)
22:17:37.292 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.001s ids=['c8288384']
.22:17:37.293 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/3 (session=test:group, message_count=2)
22:17:37.294 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 3/3 (session=test:group, message_count=2)
22:17:37.294 [WARNING][core.extractor.extractor] [EventExtractor] LLM batch extraction timed out (retries_used=0)
22:17:37.294 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=timeout, session=test:group, message_count=2, retries_used=0
22:17:37.295 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.001s ids=['d0991e82']
..22:17:37.296 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 600s before attempt 2/3 (session=test:group, message_count=2)
22:17:37.296 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:group, message_count=2
22:17:37.296 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:group strategy=llm messages=2 partitions=1 events=1 low_conf=1 duration=0.000s ids=['efef605e']
.........22:17:37.298 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'hold' (priority=10, active=1)
22:17:37.299 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'hold' finished in 0.00s
22:17:37.299 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'after' (priority=10, active=1)
22:17:37.299 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'after' finished in 0.00s
.22:17:37.299 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'hold' (priority=10, active=1)
22:17:37.300 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'hold' finished in 0.00s
22:17:37.300 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'synthesis' (priority=10, active=1)
22:17:37.300 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'synthesis' finished in 0.00s
22:17:37.300 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'synthesis' (priority=10, active=1)
22:17:37.300 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'synthesis' finished in 0.00s
22:17:37.300 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'eval' (priority=20, active=1)
22:17:37.300 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'eval' finished in 0.00s
22:17:37.300 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'eval' (priority=20, active=1)
22:17:37.300 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'eval' finished in 0.00s
.22:17:37.301 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=1)
22:17:37.301 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=2)
22:17:37.301 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=3)
22:17:37.312 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:17:37.312 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:17:37.312 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:17:37.312 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=1)
22:17:37.312 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=2)
22:17:37.312 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=10, active=3)
22:17:37.323 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:17:37.323 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:17:37.323 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:17:37.323 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=1)
22:17:37.323 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=2)
22:17:37.324 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Starting task 'w' (priority=20, active=3)
22:17:37.334 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:17:37.334 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
22:17:37.335 [DEBUG][core.managers.llm_manager] [LLMTaskManager] Task 'w' finished in 0.01s
...........................22:17:39.606 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.00, reason=unavailable
22:17:39.607 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=41 partitions=1 events=3 low_conf=0 duration=0.001s ids=['c70a6957', 'db28980d', 'f234db5a']
22:17:39.608 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.00, reason=segmentation requires a segments array
22:17:39.608 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=41 partitions=1 events=3 low_conf=0 duration=0.001s ids=['4e773e67', 'a4fefe03', '97f962b0']
.22:17:39.611 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=25 partitions=1 events=3 low_conf=0 duration=0.001s ids=['a3f11f08', '6492eee1', '48325cdd']
.22:17:39.611 [WARNING][core.extractor.extractor] [EventExtractor] extraction got no answer; window waits 0s before attempt 2/2 (session=test:dm, message_count=25)
22:17:39.612 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=25 partitions=1 events=3 low_conf=0 duration=0.001s ids=['533ab87d', '75f1195d', 'b7b40179']
.22:17:39.614 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=45, segments=1, seconds=0.00
22:17:39.615 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=45 partitions=1 events=3 low_conf=0 duration=0.001s ids=['1eb38567', 'c4cccf15', 'ce13606b']
.22:17:39.616 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=24, segments=2, seconds=0.00
22:17:39.617 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=24 partitions=1 events=4 low_conf=0 duration=0.001s ids=['e12a078b', 'cec26507', 'ab667c8f', 'd8083182']
.22:17:39.617 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:17:39.618 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:17:39.618 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=teardown_after_no_answer, session=test:dm, message_count=15
22:17:39.618 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=45 partitions=1 events=3 low_conf=3 duration=0.001s ids=['557fa449', '2f79d18c', '0421b7e1']
.22:17:39.720 [WARNING][core.extractor.extractor] [EventExtractor] segmentation fell back to whole window: session=test:dm, seconds=0.10, reason=
.22:17:39.722 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=11 partitions=1 events=1 low_conf=0 duration=0.000s ids=['8d58f084']
22:17:39.722 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=20 partitions=1 events=1 low_conf=0 duration=0.000s ids=['2e7e4895']
.22:17:39.723 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=24, segments=2, seconds=0.00
......22:17:39.836 [WARNING][core.utils.model_retry] [ModelRetry] task=segmentation attempt=1 retry_in=0.00s timeout=0.1 reason=TimeoutError error=TimeoutError()
22:17:39.957 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=test:dm, messages=12, segments=1, seconds=0.22
...22:17:39.980 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=1 retry_in=0.00s timeout=0.02 reason=TimeoutError error=TimeoutError()
22:17:40.021 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=2 retry_in=0.00s timeout=0.04 reason=TimeoutError error=TimeoutError()
.22:17:40.073 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=1 retry_in=0.00s timeout=0.1 reason=TimeoutError error=TimeoutError()
22:17:40.075 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=2 retry_in=0.00s timeout=0.30000000000000004 reason=TimeoutError error=TimeoutError()
22:17:40.076 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=3 retry_in=0.00s timeout=0.5 reason=TimeoutError error=TimeoutError()
22:17:40.078 [WARNING][core.utils.model_retry] [ModelRetry] task=t attempt=4 retry_in=0.00s timeout=0.5 reason=TimeoutError error=TimeoutError()
.........22:17:40.407 [WARNING][asyncio] Executing <Task pending name='Task-1045' coro=<LocalReplayTests.test_export_sample_routes_extracts_indexes_and_injects_without_live_calls() running at /home/gar1ton/DEV-WORKSPACE/projects/Project-Oedipus-workspace/moirai/tests/test_realtime_entry.py:262> wait_for=<Future pending cb=[Task.task_wakeup()] created at /usr/lib/python3.12/asyncio/base_events.py:449> cb=[_run_until_complete_cb() at /usr/lib/python3.12/asyncio/base_events.py:182] created at /usr/lib/python3.12/asyncio/runners.py:100> took 0.149 seconds
22:17:40.545 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=discord:arknights_main, messages=60, segments=1, seconds=0.00
22:17:40.565 [DEBUG][core.adapters.astrbot] [MessageRouter] waiting for 20 brain tasks to finish
22:17:40.574 [INFO][core.extractor.extractor] [EventExtractor] segmentation: session=discord:arknights_main, messages=60, segments=1, seconds=0.00
22:17:40.593 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=discord:arknights_main strategy=llm messages=60 partitions=1 events=2 low_conf=0 duration=0.061s ids=['1fd8ccb7', '5960a616']
22:17:40.600 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=discord:arknights_main strategy=llm messages=60 partitions=1 events=2 low_conf=0 duration=0.026s ids=['d06797e0', '404463cf']
.................22:17:40.677 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e2
22:17:40.677 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e3
22:17:40.677 [WARNING][core.extractor.extractor] [EventExtractor] eval queue full (2); skipping [Eval] for e4
....22:17:40.814 [WARNING][core.repository.sqlite] [db_open] adopting existing 3-dimensional vectors as first; rebuild them if they came from another model
.....22:17:41.079 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: embedding endpoint unavailable at startup (embedding: HTTP 503)
..22:17:41.085 [WARNING][core.retrieval.hybrid] [HybridRetriever] model rerank unavailable: rerank: HTTP 503
.22:17:41.088 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: invalid embedding settings: Retrieval base URL must be an HTTP(S) endpoint without credentials
.22:17:41.088 [ERROR][core.managers.embedding_manager] [EmbeddingManager] vector recall disabled: invalid embedding settings: KCL retrieval models and API key must be configured
22:17:41.100 [ERROR][core.retrieval.providers] [Retrieval] model rerank disabled: invalid rerank settings: Retrieval base URL must be an HTTP(S) endpoint without credentials
...........22:17:41.160 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=t:dm strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.002s ids=['ae626eb9']
..........................22:17:42.116 [WARNING][core.extractor.extractor] [EventExtractor] LLM provider is None; falling back to rule-based extraction
22:17:42.116 [WARNING][core.extractor.extractor] [EventExtractor] event fell back to rule extraction: reason=provider_none, session=test:dm, message_count=1
22:17:42.118 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=1 partitions=1 events=1 low_conf=1 duration=0.002s ids=['9442f077']
.22:17:42.183 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=llm messages=2 partitions=1 events=1 low_conf=0 duration=0.003s ids=['8a42d0a4']
.22:17:42.243 [WARNING][core.extractor.partitioner] [SemanticPartitioner] scikit-learn is not installed. Falling back to single partition. Run `pip install scikit-learn` to enable semantic clustering.
22:17:42.249 [INFO][core.extractor.extractor] [EventExtractor] window extracted: session=test:dm strategy=semantic messages=2 partitions=1 events=1 low_conf=0 duration=0.006s ids=['7faa5eb0']
..
----------------------------------------------------------------------
Ran 473 tests in 12.910s

OK (skipped=1)
[Config] Loaded run_config.py  (model_type=kcl)
[Dev] 旧会话没有评价开关记录；保留历史事件，本次重新提取默认关闭评价。
[Dev] 评价开关记录无法读取；本次重新提取默认关闭评价。
[Archive] Resuming — keeping existing realtime_test.db in place.
[Archive] Moved stale realtime_test.db → realtime_test_stale_20261006_221740.db
[Archive] Resuming — keeping existing realtime_test.db in place.
[Archive] Moved stale realtime_test.db → realtime_test_stale_20261006_221740.db
[Config] --set RETRIEVAL_ENCODER_CONCURRENCY=1 (not in run_config.py)
[Config] --set RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS=1000 (not in run_config.py)
[Config] --set RETRIEVAL_ENCODER_RETRY_MAX=6 (not in run_config.py)
[Config] --set EXTRACTION_LLM_SEGMENTATION=False (not in run_config.py)
[Config] --set BOUNDARY_TOPIC_DRIFT_PERCENTILE=90 (not in run_config.py)
```

### Final joint event check

Directory: `.`. Exit: `0`.

```bash
PYTHONPATH=core/src moirai/.venv/bin/python scripts/verify-event-runtime.py
```

```text
test_actual_oedipus_query_consumes_public_input (__main__.JointEventTests.test_actual_oedipus_query_consumes_public_input) ... ok
test_every_injection_position_and_fallback (__main__.JointEventTests.test_every_injection_position_and_fallback) ... ok
test_extraction_keeps_scope_when_persona_summary_is_disabled (__main__.JointEventTests.test_extraction_keeps_scope_when_persona_summary_is_disabled) ... [EventExtractor] LLM provider is None; falling back to rule-based extraction
[EventExtractor] event fell back to rule extraction: reason=provider_none, session=isolated-extraction, message_count=1
ok
test_host_persona_instructions_reach_only_deferred_eval (__main__.JointEventTests.test_host_persona_instructions_reach_only_deferred_eval) ... ok
test_missing_mapping_never_becomes_aggregate (__main__.JointEventTests.test_missing_mapping_never_becomes_aggregate) ... Event turn:one:before_generation extension moirai: failed
ok
test_namespace_cleanup_and_debug_are_request_bound (__main__.JointEventTests.test_namespace_cleanup_and_debug_are_request_bound) ... ok
test_parent_expansion_cannot_cross_persona_or_channel (__main__.JointEventTests.test_parent_expansion_cannot_cross_persona_or_channel) ... ok
test_persona_eval_pass_does_not_shift_tags_or_salience (__main__.JointEventTests.test_persona_eval_pass_does_not_shift_tags_or_salience) ... ok
test_real_recall_keeps_personas_separate (__main__.JointEventTests.test_real_recall_keeps_personas_separate) ... ok
test_sqlite_persona_filters_and_vector_identity (__main__.JointEventTests.test_sqlite_persona_filters_and_vector_identity) ... ok
test_sqlite_scope_is_applied_before_candidate_limit (__main__.JointEventTests.test_sqlite_scope_is_applied_before_candidate_limit) ... ok
test_switch_and_late_reply_do_not_mix_windows (__main__.JointEventTests.test_switch_and_late_reply_do_not_mix_windows) ... ok
test_unavailable_dependency_pauses_event_handling (__main__.JointEventTests.test_unavailable_dependency_pauses_event_handling) ... ok
test_actual_oedipus_query_consumes_public_input (__main__.JointGenerationTests.test_actual_oedipus_query_consumes_public_input) ... ok
test_canon_tools_and_review_run_through_core (__main__.JointGenerationTests.test_canon_tools_and_review_run_through_core) ... ok
test_every_injection_position_and_fallback (__main__.JointGenerationTests.test_every_injection_position_and_fallback) ... ok
test_extraction_keeps_scope_when_persona_summary_is_disabled (__main__.JointGenerationTests.test_extraction_keeps_scope_when_persona_summary_is_disabled) ... [EventExtractor] event fell back to rule extraction: reason=provider_none, session=isolated-extraction, message_count=1
ok
test_host_persona_instructions_reach_only_deferred_eval (__main__.JointGenerationTests.test_host_persona_instructions_reach_only_deferred_eval) ... ok
test_missing_mapping_never_becomes_aggregate (__main__.JointGenerationTests.test_missing_mapping_never_becomes_aggregate) ... Event turn:one:before_generation extension moirai: failed
ok
test_namespace_cleanup_and_debug_are_request_bound (__main__.JointGenerationTests.test_namespace_cleanup_and_debug_are_request_bound) ... ok
test_parent_expansion_cannot_cross_persona_or_channel (__main__.JointGenerationTests.test_parent_expansion_cannot_cross_persona_or_channel) ... ok
test_persona_eval_pass_does_not_shift_tags_or_salience (__main__.JointGenerationTests.test_persona_eval_pass_does_not_shift_tags_or_salience) ... ok
test_real_recall_keeps_personas_separate (__main__.JointGenerationTests.test_real_recall_keeps_personas_separate) ... ok
test_sqlite_persona_filters_and_vector_identity (__main__.JointGenerationTests.test_sqlite_persona_filters_and_vector_identity) ... ok
test_sqlite_scope_is_applied_before_candidate_limit (__main__.JointGenerationTests.test_sqlite_scope_is_applied_before_candidate_limit) ... ok
test_switch_and_late_reply_do_not_mix_windows (__main__.JointGenerationTests.test_switch_and_late_reply_do_not_mix_windows) ... ok
test_unavailable_dependency_pauses_event_handling (__main__.JointGenerationTests.test_unavailable_dependency_pauses_event_handling) ... ok
test_unmapped_persona_gets_memory_but_no_canon (__main__.JointGenerationTests.test_unmapped_persona_gets_memory_but_no_canon) ... ok

----------------------------------------------------------------------
Ran 28 tests in 0.802s

OK
```

## Final worktree audit

The status snapshot was taken after creating the verification document and before
replacing its placeholder with this full record. No implementation changed after
the final Python runs. Documentation content is checked again at report completion.

Directory: `.`. Exit: `0`.

```bash
git branch --show-current
```

```text
cb5t-loop-wiring
```

Directory: `.`. Exit: `0`.

```bash
git rev-parse HEAD
```

```text
08a773248c5db8c637ce9cc1f01b4400801a9e68
```

Directory: `.`. Exit: `0`.

```bash
git remote -v
```

```text
origin	https://github.com/Gar1ton/Project-Oedipus-workspace.git (fetch)
origin	https://github.com/Gar1ton/Project-Oedipus-workspace.git (push)
```

Directory: `.`. Exit: `0`.

```bash
git status --porcelain
```

```text
 M README.md
 M core
 M moirai
 M oedipus
?? docs/cb5t-loop-wiring-plan.md
```

Directory: `.`. Exit: `0`.

```bash
git diff --cached --raw
```

Output: empty.

Directory: `core`. Exit: `0`.

```bash
git branch --show-current
```

```text
cb5t-loop-wiring
```

Directory: `core`. Exit: `0`.

```bash
git rev-parse HEAD
```

```text
f33001211df0ff21877e9315863c7960f69fc08a
```

Directory: `core`. Exit: `0`.

```bash
git remote -v
```

```text
origin	https://github.com/Gar1ton/Project-Oedipus-core.git (fetch)
origin	https://github.com/Gar1ton/Project-Oedipus-core.git (push)
```

Directory: `core`. Exit: `0`.

```bash
git status --porcelain
```

```text
 M README.md
 M contracts/README.md
 M docs/CHANGELOG.md
 M docs/README.md
 M docs/TODO.md
 M docs/architecture.md
 M docs/compatibility.md
 M docs/extension_protocol.md
 M integrations/astrbot_plugin/README.md
 M integrations/astrbot_plugin/discovery.py
 M integrations/astrbot_plugin/event_adapter.py
 M metadata.yaml
 M pyproject.toml
 M scripts/README.md
 M scripts/chat.py
 M src/README.md
 M src/oedipus_core/__init__.py
 M src/oedipus_core/application/reconciliation.py
 M src/oedipus_core/protocol/wire_facade.py
 M src/oedipus_core/runtime/core.py
 M src/oedipus_core/web/application.py
 M tests/README.md
 M uv.lock
 M web/frontend/package-lock.json
 M web/frontend/package.json
?? contracts/fixtures/annotation-v1/
?? contracts/v1/annotation-call.schema.json
?? contracts/v1/annotation-declaration.schema.json
?? contracts/v1/annotation-response.schema.json
?? contracts/v1/turn-annotation.schema.json
?? docs/annotation_protocol.md
?? docs/verification_v0.10.0.md
?? src/oedipus_core/application/annotation.py
?? src/oedipus_core/domain/annotation.py
?? src/oedipus_core/ports/annotation.py
?? src/oedipus_core/protocol/annotation.py
?? tests/contract/test_annotation_fixtures.py
?? tests/unit/test_annotation.py
```

Directory: `core`. Exit: `0`.

```bash
git diff --cached --raw
```

Output: empty.

Directory: `oedipus`. Exit: `0`.

```bash
git branch --show-current
```

```text
cb5t-loop-wiring
```

Directory: `oedipus`. Exit: `0`.

```bash
git rev-parse HEAD
```

```text
49054c2843f30ab6b7a7e9735bcfaed2b90136aa
```

Directory: `oedipus`. Exit: `0`.

```bash
git remote -v
```

```text
origin	https://github.com/Gar1ton/Project-Oedipus.git (fetch)
origin	https://github.com/Gar1ton/Project-Oedipus.git (push)
```

Directory: `oedipus`. Exit: `0`.

```bash
git status --porcelain
```

```text
 M .gitignore
 M README.md
 M data/README.md
 M docs/CHANGELOG.md
 M docs/README.md
 M docs/TODO.md
 M docs/core_provider_protocol.md
 M experiments/README.md
 M integrations/astrbot_plugin/README.md
 M integrations/astrbot_plugin/core_events.py
 M integrations/astrbot_plugin/core_provider.py
 M integrations/astrbot_plugin/metadata.yaml
 M pyproject.toml
 M src/README.md
 M src/oedipus/__init__.py
 M src/oedipus/situations/README.md
 M src/oedipus/situations/state.py
 M src/oedipus_eval/benchmark/README.md
 M src/oedipus_eval/benchmark/schemes.py
 M src/tools/README.md
 M tests/README.md
 M tests/test_core_event_provider.py
 M uv.lock
?? data/personas/README.md
?? docs/cb5t_state_loop_experiments.md
?? docs/verification_v0.7.4.md
?? experiments/cb5t_state_loop/
?? experiments/configs/models/kcl_hub_local_arc_chat.yaml
?? experiments/configs/models/kcl_hub_local_arc_nexus.yaml
?? src/oedipus/appraisal/
?? src/oedipus/personas/README.md
?? src/oedipus/personas/coverage_cache.py
?? src/oedipus_eval/benchmark/state_loop/
?? src/tools/persona_coverage.py
?? src/tools/state_loop.py
?? tests/annotation_schema.py
?? tests/fixtures/annotation-v1/
?? tests/test_appraisal.py
?? tests/test_core_annotation_provider.py
?? tests/test_persona_coverage_cache.py
?? tests/test_turn_annotation.py
```

Directory: `oedipus`. Exit: `0`.

```bash
git diff --cached --raw
```

Output: empty.

Directory: `moirai`. Exit: `0`.

```bash
git branch --show-current
```

```text
cb5t-loop-wiring
```

Directory: `moirai`. Exit: `0`.

```bash
git rev-parse HEAD
```

```text
c8d82bea7c8f9a1da9f05fa73073b1c7d5e11b8a
```

Directory: `moirai`. Exit: `0`.

```bash
git remote -v
```

```text
origin	https://github.com/MKiyoaki/astrbot-plugin-moirai.git (fetch)
origin	https://github.com/MKiyoaki/astrbot-plugin-moirai.git (push)
```

Directory: `moirai`. Exit: `0`.

```bash
git status --porcelain
```

```text
 M .astrbot-plugin/i18n/en-US.json
 M .astrbot-plugin/i18n/zh-CN.json
 M CHANGELOG.md
 M README.md
 M README_EN.md
 M _conf_schema.json
 M core/adapters/astrbot.py
 M core/adapters/core_events.py
 M core/api.py
 M core/boundary/window.py
 M core/config.py
 M core/event_handler.py
 M core/extractor/extractor.py
 M core/extractor/parser.py
 M core/extractor/prompts.py
 M core/managers/recall_manager.py
 M core/plugin_initializer.py
 M core/repository/sqlite.py
 M metadata.yaml
 M web/frontend/components/events/event-dialogs.tsx
 M web/frontend/lib/api.ts
 M web/plugin_routes.py
 M web/server.py
?? core/repository/commitments.py
?? core/turn_annotations.py
?? docs/cb5t-loop-wiring.md
?? docs/verification_v1.2.42.sub.md
?? migrations/023_commitments.sql
```

Directory: `moirai`. Exit: `0`.

```bash
git diff --cached --raw
```

Output: empty.

Directory: `.`. Exit: `0`.

```bash
git status --short --branch
```

```text
## cb5t-loop-wiring
 M README.md
 M core
 m moirai
 M oedipus
?? docs/cb5t-loop-wiring-plan.md
```

Directory: `.`. Exit: `0`.

```bash
./scripts/status.sh
```

```text
## cb5t-loop-wiring
 M README.md
 M core
 m moirai
 M oedipus
?? docs/cb5t-loop-wiring-plan.md
+f33001211df0ff21877e9315863c7960f69fc08a core (heads/cb5t-loop-wiring)
 c8d82bea7c8f9a1da9f05fa73073b1c7d5e11b8a moirai (heads/Oedipus-Sub)
+49054c2843f30ab6b7a7e9735bcfaed2b90136aa oedipus (heads/cb5t-loop-wiring)
## cb5t-loop-wiring
 M README.md
 M contracts/README.md
 M docs/CHANGELOG.md
 M docs/README.md
 M docs/TODO.md
 M docs/architecture.md
 M docs/compatibility.md
 M docs/extension_protocol.md
 M integrations/astrbot_plugin/README.md
 M integrations/astrbot_plugin/discovery.py
 M integrations/astrbot_plugin/event_adapter.py
 M metadata.yaml
 M pyproject.toml
 M scripts/README.md
 M scripts/chat.py
 M src/README.md
 M src/oedipus_core/__init__.py
 M src/oedipus_core/application/reconciliation.py
 M src/oedipus_core/protocol/wire_facade.py
 M src/oedipus_core/runtime/core.py
 M src/oedipus_core/web/application.py
 M tests/README.md
 M uv.lock
 M web/frontend/package-lock.json
 M web/frontend/package.json
?? contracts/fixtures/annotation-v1/
?? contracts/v1/annotation-call.schema.json
?? contracts/v1/annotation-declaration.schema.json
?? contracts/v1/annotation-response.schema.json
?? contracts/v1/turn-annotation.schema.json
?? docs/annotation_protocol.md
?? docs/verification_v0.10.0.md
?? src/oedipus_core/application/annotation.py
?? src/oedipus_core/domain/annotation.py
?? src/oedipus_core/ports/annotation.py
?? src/oedipus_core/protocol/annotation.py
?? tests/contract/test_annotation_fixtures.py
?? tests/unit/test_annotation.py
## cb5t-loop-wiring
 M .gitignore
 M README.md
 M data/README.md
 M docs/CHANGELOG.md
 M docs/README.md
 M docs/TODO.md
 M docs/core_provider_protocol.md
 M experiments/README.md
 M integrations/astrbot_plugin/README.md
 M integrations/astrbot_plugin/core_events.py
 M integrations/astrbot_plugin/core_provider.py
 M integrations/astrbot_plugin/metadata.yaml
 M pyproject.toml
 M src/README.md
 M src/oedipus/__init__.py
 M src/oedipus/situations/README.md
 M src/oedipus/situations/state.py
 M src/oedipus_eval/benchmark/README.md
 M src/oedipus_eval/benchmark/schemes.py
 M src/tools/README.md
 M tests/README.md
 M tests/test_core_event_provider.py
 M uv.lock
?? data/personas/README.md
?? docs/cb5t_state_loop_experiments.md
?? docs/verification_v0.7.4.md
?? experiments/cb5t_state_loop/
?? experiments/configs/models/kcl_hub_local_arc_chat.yaml
?? experiments/configs/models/kcl_hub_local_arc_nexus.yaml
?? src/oedipus/appraisal/
?? src/oedipus/personas/README.md
?? src/oedipus/personas/coverage_cache.py
?? src/oedipus_eval/benchmark/state_loop/
?? src/tools/persona_coverage.py
?? src/tools/state_loop.py
?? tests/annotation_schema.py
?? tests/fixtures/annotation-v1/
?? tests/test_appraisal.py
?? tests/test_core_annotation_provider.py
?? tests/test_persona_coverage_cache.py
?? tests/test_turn_annotation.py
## cb5t-loop-wiring
 M .astrbot-plugin/i18n/en-US.json
 M .astrbot-plugin/i18n/zh-CN.json
 M CHANGELOG.md
 M README.md
 M README_EN.md
 M _conf_schema.json
 M core/adapters/astrbot.py
 M core/adapters/core_events.py
 M core/api.py
 M core/boundary/window.py
 M core/config.py
 M core/event_handler.py
 M core/extractor/extractor.py
 M core/extractor/parser.py
 M core/extractor/prompts.py
 M core/managers/recall_manager.py
 M core/plugin_initializer.py
 M core/repository/sqlite.py
 M metadata.yaml
 M web/frontend/components/events/event-dialogs.tsx
 M web/frontend/lib/api.ts
 M web/plugin_routes.py
 M web/server.py
?? core/repository/commitments.py
?? core/turn_annotations.py
?? docs/cb5t-loop-wiring.md
?? docs/verification_v1.2.42.sub.md
?? migrations/023_commitments.sql
```

Directory: `.`. Exit: `0`.

```bash
git diff --check
```

Output: empty.

Directory: `.`. Exit: `0`.

```bash
git ls-files --stage core oedipus moirai
```

```text
160000 33e55fe7958d237832ab54b14aafa4e3dd62a6f2 0	core
160000 c8d82bea7c8f9a1da9f05fa73073b1c7d5e11b8a 0	moirai
160000 fd0718c6d18354bbb2940ba8f8e3e28811764ad0 0	oedipus
```

Directory: `moirai`. Exit: `0`.

```bash
git diff --check
```

Output: empty.

## Documentation completion checks

`--no-index` reports exit 1 because each new file differs from `/dev/null`;
all five streams are empty, with no whitespace error diagnostics. Normal
tracked-file diff checks report exit 0. These were run after writing this record.

```bash
git diff --no-index --check /dev/null core/turn_annotations.py
```

Exit: `1`. Output: empty.

```bash
git diff --no-index --check /dev/null core/repository/commitments.py
```

Exit: `1`. Output: empty.

```bash
git diff --no-index --check /dev/null migrations/023_commitments.sql
```

Exit: `1`. Output: empty.

```bash
git diff --no-index --check /dev/null docs/cb5t-loop-wiring.md
```

Exit: `1`. Output: empty.

```bash
git diff --no-index --check /dev/null docs/verification_v1.2.42.sub.md
```

Exit: `1`. Output: empty.

```bash
(in .) git diff --check
```

Exit: `0`. Output: empty.

```bash
(in moirai) git diff --check
```

Exit: `0`. Output: empty.

A direct whitespace check of the five new files also passed: no trailing
spaces/tabs, and each file ends with a newline.
