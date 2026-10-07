# Per-reply notes and commitments

This is uncommitted development on `cb5t-loop-wiring`, based on the upstream
`Oedipus-Sub` revision `c8d82be`. The approved version is `v1.2.42.sub`.
Implementation is authorized for this branch only; no package restructuring,
release, dependency installation or submodule pin change is included.

The owning workspace plan is
[`docs/cb5t-loop-wiring-plan.md`](../../docs/cb5t-loop-wiring-plan.md).
Core publishes the independently optional
[`Annotation Protocol v1`](../../core/docs/annotation_protocol.md) and
[`turn-annotation.v1`](../../core/contracts/v1/turn-annotation.schema.json).
Event Protocol v1 and Generation Protocol v1 keep their existing wire formats.
Moirai imports neither Core nor Oedipus source. Its annotation validator copies
the published closed format; the workspace verifier must check that copy
against the actual Core codec when it exercises the new three-provider loop.

## Delivery and raw-message storage

`MoiraiCoreProvider.annotation_v1()` declares a consumer and no producer.
`on_annotation_v1()` accepts a `deliver` call for a `before_generation` event,
requires an explicit Moirai scope-to-persona mapping and validates the entire
annotation before caching it. Invalid content is never retained.

`EventHandler` keeps annotations separately from the existing decoration state,
which has already been consumed when Core delivers the annotation. The key
includes source instance, correlation, runtime persona, Moirai bucket, binding
and configuration revisions, platform, stream, sender and group identities.
Only the first delivery for a key is retained. Entries expire after 900 seconds
and the cache is capped at 1024, following the existing turn-state limits.

On `after_generation`, the matching annotation is consumed once. The triggering
sender is resolved to a Moirai person uid. `MessageRouter.process()` receives
optional metadata containing `reply_to_uid` and, when present,
`turn_annotation`. It retains the same return contract and detaches the metadata
from the caller. The open window and the existing raw-message writer receive
these values; persisted storage uses `raw_messages.metadata_json`. An unannotated
reply still records its addressee, so it can replace that person's previous notes.

## One-turn notes

During `before_generation`, the handler reads the latest assistant message in
the current session's open window for the same persona and addressee. It uses
window metadata so the next request does not depend on the background raw
writer having flushed yet. A valid annotation contributes nonempty expectation,
feeling and goal lines under `[上一轮你回复这个人时心里想的]`.

This is an Event Protocol text block with separate `EM:NOTES` markers, not a
notes-query operation. A newer unannotated reply to that person clears the
previous notes. Settlement or removal of the window also ends them. Empty
annotations produce no block. Commitments survive these cases independently.

## Persistent commitments

Migration `023_commitments.sql` creates independent storage for persona bucket,
person uid, source session and group, text, source message, creation time,
status, closing time and closing event. Statuses are `open`, `done` and
`dropped`. There is no raw-message foreign key: raw retention must not remove an
uncompleted commitment. IDs derive from source message ID and item position,
making repeated insertion of the same source item harmless. An item is also
skipped when the same persona already has an open commitment with identical
text to the same person in the same private or group scope, so a promise
restated on a later turn stays one row. Different wording is stored as a new
commitment, and the same text written after the earlier one closed opens a new
row.

After an annotated assistant reply, the router writes each `记下` item as open.
Recall filters by the current persona, addressee and private/group scope. It
uses existing query terms, evidence scoring, cosine similarity, lexical weight
and the existing encoder. Items meeting the existing `0.35` evidence threshold
are ranked and capped by `commitment_max_items`, default 3. Zero disables this
injection. The block is separate from event memory and uses `EM:COMMITMENTS`
markers with the heading `[你对这个人尚未完成的约定]`.

The `0.35` threshold is also reused for semantic similarity; it has not been
calibrated on real commitment data. With vectors enabled, uncached queries and
open texts may cause calls to the configured embedding service. This introduces
no extra chat-model call, but embedding cost and latency have not been measured.
Encoder errors fall back to keyword relevance.

Both existing extraction paths list the participants' open commitments, with
IDs, in their existing prompt. The list is scoped to the window's persona and
group and excludes commitments created after the messages being extracted.
The same extraction result may return `commitments_closed` entries containing
`id` and `status` (`done` or `dropped`). Fact extraction remains persona-free:
the prompt adds commitment text and person labels, not a persona description.

Only IDs actually supplied to that extraction call can close. Unknown IDs,
conflicting statuses and uncertain results do nothing. Rule-summary fallback
never closes commitments. Already closed rows are not overwritten. The closing
event and its end time are recorded after event persistence and raw-message
linking. Existing extraction repair/retry behavior remains; there is no separate
commitment-settlement model call.

## Persona view and defaults

Event serialization projects `persona_view` from linked raw assistant messages'
annotations. SQLite reads the links in bulk through `event_messages` and
`raw_messages`, with event-persona filtering. Each view contains message ID,
what happened, feeling and goal. It does not alter the factual summary.
Core API helpers accept an optional raw repository; real WebUI list serializers
attach the projection. Serializers without a repository return an empty view.

The existing event dialog displays these values as escaped text in a separate
`当时的我` section. Legacy `[Eval]` content still renders as before. Existing
stored summaries are not rewritten.

| Setting | Default | Effect |
|---|---|---|
| `persona_influenced_summary` | `false` | Keeps the existing deferred evaluation code available, with evaluation disabled by default. |
| `persona_view_injection_enabled` | `false` | Reserved switch only; even `true` does not inject persona view into recall. |
| `commitment_max_items` | `3` | Caps relevant open-commitment injection; `0` disables that block. |

The existing recall formatter and Soul Layer remain. The user requested these
debugging controls in Core's dialogue interface as follow-up work; this Moirai
phase does not implement that interface. Oedipus's loop defaults off in its own
provider; Moirai does not configure or import it.

## Verification boundary

See [the command/output record](verification_v1.2.42.sub.md). Tests use existing
environments, scripted/null models and temporary stores. New tests remain in
the upstream-ignored `tests/` directory; no force-add was performed. The UI was
typechecked and its actual React component statically rendered; production
bundles were not rebuilt or deployed.

The existing joint event verifier passes, but its new full three-repository loop
cases belong to the next workspace phase. Live models, KCL hub, experiments,
AstrBot, browser behavior, real semantic clustering and retrieval quality remain
unverified. Group-target reasoning is still the triggering sender; interpreting
a model's intended addressee is outside this change.
