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
- **Pacing:** chat requests are spaced at `MODEL_REQUEST_INTERVAL_MS`, which must be above 1,000 and defaults to 2,000. Embedding request and retry intervals are raised to at least 2,000 ms.
- **Log:** stdout and stderr are also written to `<dev-data>/run_<timestamp>.log`, or to `--log-file`.
- **Outside the replay:** tasks started by hand from the WebUI keep the plugin defaults.

## Start the real run

Replace `--check` with `--fresh` in the command above. This calls the configured model and embedding services, builds `.dev_data/canon_realtime/main-ch00-17-dialogue/realtime_test.db`, runs the existing subsequent persona-synthesis and group-summary phases, then serves the WebUI on port 2656. The old ch0–8 directory is a different destination and is not used by this command. Fresh rebuilds archive existing output in the selected destination using the tool's existing policy.

The persona question remains interactive. Add `--eval-persona` to enable independent persona commentary and seed the supplied bot persona without that question, or `--no-eval-persona` to disable it. This affects commentary and the existing development persona setup, not whether the supplied messages are ingested. `--resume` opens an existing database without replaying extraction; it does not apply new extraction logic retroactively.

`--query` changes the memory comparison question; `--group-id` changes its group, defaulting to the first group in the selected input. The fixed legacy group-chat benchmark can be disabled with `--set RECALL_BENCHMARK_ENABLED=False`, as above. No benchmark scoring result is implied by these options.

Runtime overrides leave `run_config.py` unchanged. The new extraction overrides are `EXTRACTION_LLM_SEGMENTATION`, `EXTRACTION_SEGMENTATION_MESSAGES_PER_SEGMENT`, `EXTRACTION_SEGMENTATION_TIMEOUT_SECONDS`, `BOUNDARY_TOPIC_DRIFT_AUTO_CALIBRATION` and `BOUNDARY_TOPIC_DRIFT_PERCENTILE`. Their defaults match the plugin configuration. Existing retrieval overrides retain their names.

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
