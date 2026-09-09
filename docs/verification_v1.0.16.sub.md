# Verification of Moirai v1.0.16.sub

Date: 2026-09-05. This is an uncommitted local worktree verification, not a published release or a pinned cross-repository compatibility baseline. Existing unrelated worktree changes were retained. Only Moirai source, documentation, version and local frontend output were changed for this task.

## Moirai checks

Commands below ran from the Moirai root unless another directory is specified.

| Command | Actual result |
| --- | --- |
| `.venv/bin/python run_realtime_dev.py --self-test --quiet` | Passed: 14 offline tests, including plugin Y/N/Y, semantic distillation, JSON repair, custom prompts, historical re-extraction, persona-name collisions, seven-topic legacy formatting and realtime setting persistence. |
| `node tests/event-summary-ui.cjs` | Passed: 7 parser and actual React detail-component rendering tests, including the event stream and database panel. |
| `npm run typecheck` in `web/frontend` | Passed. |
| `npm run build` in `web/frontend` | Failed: could not fetch Geist, Geist Mono and PT Serif from Google Fonts. |
| `npm run build -- --webpack` in `web/frontend` | Failed without a useful compiler diagnostic before the font cache was supplied. |
| `NEXT_FONT_GOOGLE_MOCKED_RESPONSES=/tmp/moirai-font-cache.cjs npm run build -- --webpack` in `web/frontend` | Passed: compilation, TypeScript and static generation completed, 13/13 generated pages. The response map used CSS and real font files already bundled in the repository, not placeholder fonts. |
| `.venv/bin/python -c 'from core.utils.version import get_plugin_version; print(get_plugin_version())'` | Printed `1.0.16.sub`; matching metadata and dated changelog entry were also checked. |
| `git diff --check` | Passed. |

Changed Python files were parsed with `ast.parse`, and `_conf_schema.json` was decoded with `json.loads`; both checks passed. The frontend output was copied into `pages/moirai/_app/`, preserving an original copy at `/tmp/moirai-event-frontend-backup-hmexqsnx/_app`. Every exported file was compared byte-for-byte with the serving directory, and all 40 distinct HTML references to `/_next/` assets resolved to existing files. Older hashed assets were retained, not deleted. The existing Next.js warning about rewrites during static export remains; production uses the backend's same-origin API routes.

The temporary font response map and build log are at `/tmp/moirai-font-cache.cjs` and `/tmp/moirai-event-cached-build.log`. The attempted automatic approval for a network-enabled build timed out; the completed offline build used no such approval.

The local tests follow the repository's existing ignored `tests/` convention. No dependencies were installed, no running memory database was opened, no model provider or embedding model was invoked, and no commit, push, release or workspace gitlink update was performed.

## Workspace checks

From the workspace root, `git status --short --branch`, `git diff --check` and `./scripts/status.sh` completed successfully. The status script correctly reports the already dirty child worktrees.

The full existing command was attempted:

```bash
PYTHONPATH=core/src moirai/.venv/bin/python scripts/verify-event-runtime.py
```

This run is **not a pass**. The version test expects the literal `1.0.15.sub` and therefore fails after the requested Moirai bump. The run subsequently stopped producing output in `test_sqlite_persona_filters_and_vector_identity` and was interrupted; SQLite verification is incomplete. The workspace script was not edited because this task is limited to Moirai.

The eight relevant in-memory coordination tests were then run explicitly and all passed:

```bash
PYTHONPATH=core/src moirai/.venv/bin/python scripts/verify-event-runtime.py \
  JointEventTests.test_actual_oedipus_query_consumes_public_input \
  JointEventTests.test_every_injection_position_and_fallback \
  JointEventTests.test_extraction_keeps_scope_when_persona_summary_is_disabled \
  JointEventTests.test_missing_mapping_never_becomes_aggregate \
  JointEventTests.test_namespace_cleanup_and_debug_are_request_bound \
  JointEventTests.test_parent_expansion_cannot_cross_persona_or_channel \
  JointEventTests.test_real_recall_keeps_personas_separate \
  JointEventTests.test_switch_and_late_reply_do_not_mix_windows
```

## Remaining validation boundary

No fresh realtime ingestion, paid experiment, live-model comparison or browser interaction test was performed. React server rendering and the static build validate component output and compilation, not interactive browser layout. The new extraction prompt's recall quality and semantic fidelity still require evaluation with the configured model and source conversations. Existing historical factual mistakes are not repaired by display cleanup.
