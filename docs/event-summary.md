# Event summaries and persona evaluation

Moirai v1.0.17.sub keeps one event for each supplied conversation window in LLM mode and one event for each supplied semantic cluster in distillation mode. The extraction prompt produces one JSON object. Existing array-shaped model responses remain accepted by the parser. Summary changes do not change database schemas, retrieval ranking, event boundaries or the Core protocol.

## Extraction contract

Each summary contains independently readable topic segments in this order:

| Field | Content |
| --- | --- |
| `[What]` | Named speaker, specific object, statement or action, including relevant quantities, conditions, negation and attribution. |
| `[Who]` | People or assistants actually involved in this topic, preserving their display names. |
| `[How]` | Responses, progression, outcome or unresolved questions, without repeating the preceding fact. |
| `[Eval]` | Optional bot-persona commentary, separate from the reported facts and other participants' opinions. |

Segments are separated with ` | `. Related questions, answers, disagreements and resolutions stay together. Different people's unrelated requests remain separate. Topic count need not equal tag count. The prompt removes repetitive acknowledgements while retaining concrete evidence of preferences, emotions, humour and relationships.

The summary must distinguish a question from an established fact, a proposal from a completed action, and someone's opinion from an objective conclusion. Resolve names, pronouns and abbreviations only when the supplied messages support the interpretation. Preserve ambiguity explicitly rather than inventing an expansion or business context. Empty messages and image markers are evidence of non-text activity, not evidence of the image's contents.

Message timestamps are supplied as ISO 8601 UTC instants. Relative expressions remain anchored to the source messages; the prompt does not invent a local date or timezone. This is especially relevant to messages near midnight and historical messages saying “tonight” or “next Friday”.

The output is plain text inside JSON: no Markdown emphasis, HTML entities or Markdown escaping of underscores. Tags remain reusable topic-domain nouns. Salience retains both factual and interpersonal value; confidence concerns the fidelity of the extracted account.

For example, if the source contains a question without an answer:

```text
[What] Sovarlet 向 Wabbajack_114514 询问再做6个月是否还能获赠一个；具体业务和赠品所指未明。
[Who] Sovarlet、Wabbajack_114514
[How] 本段未见答复，赠送条件尚未确认。
```

This example does not establish that an answer was absent from the user's original conversation. The extractor must check its supplied source window.

## Persona mode

The extraction call is always persona-free. Regardless of `persona_influenced_summary`, the extraction and distillation system prompts are the `_NO_EVAL` variant (or an unchanged user-supplied custom prompt), the user prompt carries no `[Bot 视角人格]` header, and the parser runs with `has_bot_persona=False`. Topic split, `[What]/[Who]/[How]` facts, `chat_content_tags` and `salience` are therefore byte-identical whether the switch is on or off. Participants' own opinions and emotions are retained as facts in both modes.

`persona_influenced_summary` gates a separate second pass. Extraction persists the event without `[Eval]` and enqueues it; a single background worker in `EventExtractor` then annotates events **in batches**, and only while no extraction is in flight, so eval calls never interleave with — and never evict the prefix cache of — the extraction calls. Each batch is one LLM call (`task_name="eval"`) that receives only the already-finalised topic segments plus the resolved persona description — the conversation is not resent — and returns one ≤30-character first-person aside per segment per event (`core/extractor/eval_pass.py:annotate_events_evals`), which is spliced back into each `summary` as `[Eval]` via a second `upsert` (the vector is not rebuilt). The aside rules are unchanged (`_EVAL_RULE`): no invented participation, experiences or commitments; `暂无评价` for a deliberate abstention. Any failure of this pass (call error, timeout, no provider, unparseable output) degrades to `未生成评价` for every affected segment and never disturbs the extracted facts. Missing commentary does not lower factual confidence.

Because the pass is deferred, a newly extracted event is briefly visible without its `[Eval]` (typically seconds). `EventExtractor.drain_evals()` forces the queue empty — called by `plugin_initializer.teardown` after `router.flush_all()`, and by `run_realtime_dev.py` once Phase 2 extraction completes — but an unclean crash drops whatever is still queued (recoverable via manual re-extraction). Manual re-extraction (`reextract_event`, the WebUI button) keeps its `[Eval]` inline and immediate: one event, user-triggered. When the switch is off, nothing is enqueued and no `[Eval]` is stored.

`[Eval]` text is excluded from the retrieval embedding: `_batch_index_vectors`, `_index_vector` and the re-extraction embedding all index `strip_evals(summary)`. The FTS index covers only `topic` and `chat_content_tags`, so it is unaffected.

The switch does not move events between persona scopes and does not bulk-rewrite historical memories. Re-extraction runs the same two passes: a persona-free extraction that either produces valid JSON or leaves the event untouched, then the gated `[Eval]` pass whose failure is non-fatal. It preserves the existing event's persona bucket and resolves the description for that named bot, rather than selecting a different, more recently active bot. This uses the available persona profile, not a reconstructed historical profile snapshot. Locked events and failed manual extractions retain their prior content.

## Display compatibility

Event-stream and database detail views accept topic segments missing `[Who]` or `[How]`. Missing fields are hidden, without manufacturing an outcome. Existing `[Eval]` fields remain associated with their own topics; an absent evaluation does not display as “insufficient information”. Legacy outer emphasis, escaped underscores and HTML space entities are cleaned for display. Ordinary brackets such as `[图片]` and literal pipes inside a field are preserved. Unstructured summaries fall back to a full text display, which React escapes normally.

Stored summaries and original message records are not bulk-migrated. New prompt rules apply after new extraction or an explicit re-extraction. Old incorrectly attributed factual content requires source-based re-extraction; formatting cleanup cannot repair its meaning.

## Research basis and limits

[SimpleMem, January 2026, section 2.1 and appendix A.1](https://arxiv.org/html/2601.02553v1) describes self-contained memory units, explicit entity references and temporal grounding. Moirai adopts those extraction principles, with conservative handling of uncertain local dates.

[AnchorMem, April 2026, section 4.1](https://arxiv.org/html/2604.17377v1) separates factual retrieval anchors from retained source context. Moirai uses that distinction to keep summaries evidence-oriented while retaining its existing raw-message/reference paths. This update does not implement AnchorMem's graph, introduce atomic-fact indexes, or alter retrieval ranking.

These are design adaptations, not a reproduction of either paper's system or benchmark claims. Offline regressions verify format and control flow. They do not establish improved semantic recall, extraction completeness or hallucination rates on a live model.

## Local verification and preview

Run from the Moirai root using installed dependencies:

```bash
.venv/bin/python run_realtime_dev.py --self-test --quiet
node tests/event-summary-ui.cjs
cd web/frontend
npm run typecheck
npm run build
```

The self-test uses deterministic providers and in-memory repositories, and temporary files for the realtime setting. It does not open `.dev_data/realtime_test.db`, call an LLM or download an encoder. UI tests render the real detail components with the reported seven-topic example.

`run_realtime_dev.py` persists its Y/N setting in `.dev_data/realtime_settings.json` and passes the same value to the WebUI re-extraction handler. Resuming old data with no saved setting conservatively disables evaluation for subsequent re-extraction, while leaving existing events visible. A fresh run still calls the configured model and may load/download an encoder; it is a separate quality evaluation, not part of `--self-test`.

The backend serves the built assets under `pages/moirai/_app/`. A successful `npm run build` creates `web/frontend/out/`; sync that output using the existing frontend build workflow before expecting the standalone backend to display source changes. For source preview against the realtime backend, use `BACKEND_PORT=2656 ./node_modules/.bin/next dev` from `web/frontend`.

The exact defaults are constructed in `core/config.py` by `_build_system_prompt`. Print either variant with:

```bash
.venv/bin/python -c 'from core.config import DEFAULT_EXTRACTOR_SYSTEM_PROMPT as p; print(p)'
.venv/bin/python -c 'from core.config import DEFAULT_EXTRACTOR_SYSTEM_PROMPT_NO_EVAL as p; print(p)'
```

See [the v1.0.16.sub verification record](verification_v1.0.16.sub.md) for actual results, the offline font build and the incomplete workspace checks.
