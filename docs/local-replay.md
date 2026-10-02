# Local replay with the realtime development tool

Run commands from the `moirai/` repository using its existing `.venv`. `run_realtime_dev.py` owns the standalone development composition: message routing, raw-message writing, event extraction, indexing, recall and the local WebUI. It exercises Moirai directly; the workspace's Core protocol checks are separate.

## Prepared main-story input

The current local export `tests/mock_data/canon_amiya_main_ch00-17_dialogue.json` contains 65,172 public dialogue messages from main chapters 0–17, including 5,625 internal bot replies. It uses group `arknights_main` and bot ID `char_002_amiya`. Its sidecar manifest records speaker and visibility maps, excludes narration and private thoughts, and hashes the data, line map and persona. The existing export remains untouched. Story assets and the resulting runtime databases must remain local.

## Check before running

`--check` reads the selected data and effective configuration, validates the sidecar hashes when present, then exits. It makes no model request and does not archive data, create a database or start a server. The normal fresh run performs the same validation before archiving anything.

```bash
.venv/bin/python run_realtime_dev.py --check \
  --data tests/mock_data/canon_amiya_main_ch00-17_dialogue.json \
  --dev-data .dev_data/canon_realtime/main-ch00-17-dialogue \
  --persona tests/mock_data/amiya_persona.md --bot-id char_002_amiya \
  --set RETRIEVAL_ENCODER_CONCURRENCY=1 \
  --set RETRIEVAL_ENCODER_REQUEST_INTERVAL_MS=2000 \
  --set RETRIEVAL_ENCODER_RETRY_MAX=6 \
  --set RECALL_BENCHMARK_ENABLED=False \
  --query "切尔诺伯格那场事件大体发生了什么？"
```

This check passed on 2026-10-02. The effective model was KCL `arc:chat`, with three shared LLM slots. Embeddings used `arc:embedvl`, one worker, a 1,000 ms request interval and six retries. Extraction used `llm`, segmentation enabled, one allowed unit per 12 messages, a 30-second boundary timeout and 40-message extraction pages. Drift self-calibration was enabled at the 85th percentile. The proposed output directory did not exist at the time of checking.

## Strict retries in the replay

The replay never trades quality for speed when a service is slow or throttled. It turns on retry-until-success for segmentation, extraction, embedding, persona synthesis and group summaries; ordinary plugin defaults stay unchanged.
- **Retries:** a retryable failure waits at least two seconds, then doubles up to 60 seconds and honours `Retry-After`, and tries again. Retryable failures are HTTP 408/409/425/429/5xx, timeouts, transport errors and unusable model output. It never writes a whole-window or rule-summary fallback.
- **Permanent errors stop the run:** a configuration error or a non-retryable HTTP status.
- **Timeouts:** each timeout multiplies the next attempt's limit by the extractor's timeout growth (default 1.5), up to 300 seconds, so a request that always needs longer still finishes.
- **Stuck requests:** a request still failing after 8 attempts, or after 5 minutes of attempts and retry delays, logs `STILL RETRYING` and keeps retrying; watch the log for that line. Time spent queued for one of the shared model slots does not count, so a backlog alone does not trigger it.
- **Pacing:** chat requests are spaced at `MODEL_REQUEST_INTERVAL_MS`, which must be above 1,000 and defaults to 2,000. Embedding request and retry intervals are raised to at least 2,000 ms.
- **Log:** stdout and stderr are also written to `<dev-data>/run_<timestamp>.log`, or to `--log-file`.
- **Outside the replay:** tasks started by hand from the WebUI keep the plugin defaults.

## Start the real run

Replace `--check` with `--fresh` in the command above. This calls the configured model and embedding services, builds `.dev_data/canon_realtime/main-ch00-17-dialogue/realtime_test.db`, runs the existing subsequent persona-synthesis and group-summary phases, then serves the WebUI on port 2656. The old ch0–8 directory is a different destination and is not used by this command. Fresh rebuilds archive existing output in the selected destination using the tool's existing policy.

The persona question remains interactive. Add `--eval-persona` to enable independent persona commentary and seed the supplied bot persona without that question, or `--no-eval-persona` to disable it. This affects commentary and the existing development persona setup, not whether the supplied messages are ingested. `--resume` opens an existing database without replaying extraction; it does not apply new extraction logic retroactively.

`--query` changes the memory comparison question; `--group-id` changes its group, defaulting to the first group in the selected input. The fixed legacy group-chat benchmark can be disabled with `--set RECALL_BENCHMARK_ENABLED=False`, as above. No benchmark scoring result is implied by these options.

Runtime overrides leave `run_config.py` unchanged. The new extraction overrides are `EXTRACTION_LLM_SEGMENTATION`, `EXTRACTION_SEGMENTATION_MESSAGES_PER_SEGMENT`, `EXTRACTION_SEGMENTATION_TIMEOUT_SECONDS`, `BOUNDARY_TOPIC_DRIFT_AUTO_CALIBRATION` and `BOUNDARY_TOPIC_DRIFT_PERCENTILE`. Their defaults match the plugin configuration. Existing retrieval overrides retain their names.

## Extraction order

A replay closes every window within minutes of starting. The runner extracts them in the order they were created, with at most one more window in progress than the configured model concurrency (four with three slots), and finishes each window before starting another. Each window's segmentation, extraction pages and social analysis therefore run back to back. Started all at once, the windows would share the model slots round-robin: they would finish out of event order, impressions (blended 40% new to 60% old per event) would be updated out of event order, and an interrupted run would lose every half-extracted window. In the 2026-10-02 ch0–17 build, which predates this ordering, the update order of social analysis correlated only 0.45 with event time. A live plugin closes windows as messages arrive and is unaffected.

## Continue an interrupted build

Replace `--fresh` with `--continue` to finish an interrupted fresh build in place. The database stays where it is and is not archived. The persona-evaluation setting saved by the interrupted run applies, so `--eval-persona` may be repeated but not contradicted. The run replays every message through the same router and handles each window as follows:

- **Stored messages:** a message the interrupted build already stored keeps its message ID. It is recognised by its content hash and is not written again; only messages missing from `raw_messages` are written.
- **Router vectors:** the router computes no per-message vectors. Drift therefore cannot close a window, and the windows match the interrupted build whenever drift never fired there. In a fast replay it cannot fire, because the drift vectors arrive after their windows have closed.
- **Untouched windows:** a window none of whose stored messages links to an event is extracted normally.
- **Extracted windows:** a window whose stored messages all link to events is not extracted again. Its events finished post-processing only if their ID prefixes appear on a `window extracted` line in an earlier `run_*.log` of the same directory. For events without such a line, the per-event social analysis (big-five scoring and orientation) runs again.
- **Partly linked windows:** the run stops before guessing.
- **Missing asides:** after extraction, every event whose summary lacks a generated `[Eval]` aside in some topic is queued for the deferred pass. TypeSafe classification uses its existing backfill.

Strict replay never drops a deferred `[Eval]` at the plugin's 500-item queue cap. Ordinary plugin runs keep the cap.

On 2026-10-02 the interrupted ch0–17 build was dry-run offline against a copy of its database, with no model calls. It rebuilt the original 1,295 windows. Of these, 343 were finished, 356 needed the social re-run for 708 events and 596 were untouched. Three source messages had never been stored, and no window was partly linked.

## Finish an extracted build

`--finish` runs the post-extraction phases on a build whose windows are all extracted. It is meant for a run stopped after it printed `[Phase 2] Annotating [Eval] asides`, at which point every extraction and social-analysis task has finished. The database stays where it is and nothing is ingested or extracted again. The run keeps the saved persona-evaluation setting and works in this order:

1. TypeSafe classification continues through its existing background backfill.
2. Group summaries, the RAG probe and the state test run as in a fresh build. The single end-of-build persona synthesis is skipped.
3. The WebUI starts.
4. Persona synthesis is replayed in event order. A live plugin synthesizes a person after 30 new messages (with at least three events and three hours since the last attempt) and through a 72-hour staleness pass, each time from that person's latest ten events, and blends the new big-five scores with the old ones. A replay stores the whole history first, so one synthesis at the end sees only the last ten events of each person. The replay instead clears earlier synthesized attributes, plans the calls the live trigger would have made in event time, and runs each person's calls in order. The supplied bot persona is seeded again first. The log reports `[Finish] Persona synthesis replay done` with the call count.
5. Every event whose summary lacks a generated `[Eval]` aside is queued, and the deferred pass annotates it in the background. Each batch is written as it completes, so the WebUI shows asides as they land. The log ends this step with `[Finish] [Eval] annotation done` and the number of events still missing an aside.

The replay passes the supplied persona file to `[Eval]` as the host persona context, as a live host does, so synthesis cannot shorten the persona the asides are written from. Stopping the WebUI cancels unfinished background work. A later `--finish` replays synthesis again and queues whatever asides are still missing.

On the 2026-10-02 ch0–17 build the plan was 1,528 synthesis calls for 366 people; the longest single chain was the bot persona with 103 calls.

## Restarting a WAL database safely

Before `--fresh` archives an existing database, it switches SQLite to DELETE journal mode to checkpoint committed WAL pages, requires exclusive access, and closes the connection. It refuses to rename the database if a runner or reader still holds it open, or if orphan sidecars remain without a main database. A failed move also stops the run and preserves the database. Stop database monitoring scripts as well as the previous runner before rebuilding; an idle read-only WAL connection can retain shared-memory locks.

The 2026-10-02 ch0–17 restart failed with `disk I/O error` after the old archive step moved only `realtime_test.db` while a background read-only probe retained the old database and the original `realtime_test.db-shm`. The identified probe was stopped and the user-requested cleanup removed the current database, WAL/SHM files and that run's stale database archive. The source export, persona and runtime settings were preserved.

After this fix, `.venv/bin/python -m unittest discover -s tests -p test_realtime_entry.py -v` passed eight tests, and `.venv/bin/python run_realtime_dev.py --self-test` ran 414 tests with one skip and no failures. Cross-process regressions cover idle and transactional WAL readers, blocked archives, retained committed rows, resume behaviour, orphan sidecars and failed moves. The exact `--check` command above passed again and source hashes matched the pre-cleanup values. These were offline checks, without a live replay.

`reset_realtime_dev.py` uses the legacy `.dev_data/` destination; it does not select a custom `--dev-data` directory. For a targeted cleanup, first close all users of the chosen directory, then remove only its generated database, sidecars and unwanted archived run data. Preserve the input fixtures and other replay destinations.

## Offline verification

```bash
.venv/bin/python run_realtime_dev.py --self-test
```

The local entry regressions also replay the first 120 records of the prepared dataset through the same ingestion helper, real routing, extraction, temporary SQLite/sqlite-vec storage, indexing and prompt injection. Scripted chat responses and a mocked embedding transport replace live services. They verify exactly-once raw-message links, bot roles, shared group scope, segment-vector injection and detector/encoder wiring. These checks establish the local composition and input compatibility; they do not prove live-service availability or final answer quality.

On 2026-10-02, the exact entry command above with `--check` exited zero. `.venv/bin/python run_realtime_dev.py --self-test` ran 411 tests with one skip and no failures; the new local-entry regressions account for five tests. The SQLite-backed suite ran outside the confirmed execution-sandbox SQLite restriction with automatic approval. Both diff checks and the workspace status script exited zero. The input data hash was unchanged and the new runtime directory was not created.
