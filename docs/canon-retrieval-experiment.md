# Canon retrieval experiment

Status: 100-scene index built and evaluated (v1.2.9.sub); hybrid is the
default when an index exists. Terminal-only and unreleased.

## Scope and baseline

The 100-scene V7 pilot contains 643 events and no embeddings. Keep its canon
database read-only. A separate derived index stores remote embeddings; it is not
a replacement canon database, a reviewed knowledge source, or a compatibility
baseline. Neither archives nor temporal-fact candidates are indexed in this experiment.

Knowledge Arch's external embedding adapter, provider-aware text cache, and
bounded reranking contract are references, not imported runtime dependencies.
KCL credentials stay in the existing ignored `run_config.py` or environment.

## Design

- One vector per event initially: topic, summary, participants, and beat text.
  Keep source event IDs and original evidence in canon; never ask an embedding
  or reranking model to produce story facts. Event text preparation is versioned.
- SQLite plus the already installed sqlite-vec extension performs exact cosine
  search. Thousands of events do not justify an additional vector service yet.
- Provider endpoint, model, query instruction, text recipe, and measured vector
  dimension identify the index. A content hash caches each event document;
  successful batches commit independently, so interrupted builds resume.
- A completed corpus fingerprint prevents using changed, deleted, or partially
  indexed source events as if coverage were complete. Changing the model uses
  another index path; never silently erase a previous experiment.
- Baseline retains current behavior. Hybrid adds dense candidates to the
  existing lexical/entity candidates. Hybrid-rerank scores the bounded candidate
  union before final scene diversity and evidence selection. All three keep the
  existing knowledge-channel and gateway rules, per-person fan-out, person filter,
  and evidence budget for this controlled comparison; only candidate generation
  and scoring differ.
- Derived files follow the build run: an index and its reports live in
  `<run>/canon.retrieval/` beside that run's `canon.sqlite`. A chat copy under
  `v<N>/chat/` resolves to the one run with the same `imported_at` and prompt
  version; otherwise its files sit beside the copy. There is no shared pool.
- Terminal retrieval caches repeated queries in bounded process memory, and
  supports explicit failure fallback with diagnostics. Evaluation must report
  degraded runs separately from fully functioning model runs.
- Ordinary Moirai memory shares the same providers but never fails startup on
  them: an unreachable endpoint during the one dimension probe, or stored vectors
  from another dimension or model, disables vector recall for that process while
  BM25 recall continues. Stored vectors are never deleted automatically; legacy
  vectors without an identity adopt the configured one.
- Original `--dry-run` remains offline. Remote retrieval requires an explicit
  retrieval mode and remote-call flag; index planning is offline by default.

## Results (2026-09-24)

The labeled set is `questions-v1.jsonl` in the build run's `canon.retrieval/`:
22 of the user's chat-test questions, 38 new coverage questions, 6 paraphrases,
each with expected event IDs, plus 15 small-talk negatives. Event IDs are only
valid for that build, so the file stays beside it. `retrieval probe --questions`
reports, per question, the rank of the first expected event at each stage
(lexical, entities, dense, pool, reranked, final, injected) and a summary.

| Run | Mode | Final recall | Injected recall | MRR |
|---|---|---|---|---|
| r0 (v1.2.8) | baseline | 0.439 | 0.333 | 0.317 |
| r0 | hybrid | 0.697 | 0.485 | 0.483 |
| r0 | hybrid-rerank | 0.333 | 0.258 | 0.196 |
| r5 | baseline | 0.773 | 0.652 | 0.611 |
| r5 | hybrid | 0.955 | 0.939 | 0.798 |
| r6 (v1.2.9, dialogue channel) | baseline | 0.758 | 0.697 | 0.556 |
| r6 | hybrid | 0.970 | 0.955 | 0.797 |

r5 and r6 route all 15 negatives to small talk. The user's own 22 questions go from
0.41 (r0 baseline) to 0.95 (r5 hybrid) final recall.

What changed, in order of effect:

- A second set, `questions-detail-v1.jsonl`, has 18 questions written from raw
  dialogue of seeded random events: 10 whose answer is in the summary, 8 whose
  answer is only in the lines. Hybrid went from 0.722 to 0.944 final and injected
  recall (lines-only: 4 of 8 to 7 of 8) once raw dialogue became its own channel.
- Raw dialogue is a separate bigram BM25 channel over each event's evidence lines;
  names, epithets and quotes that summaries omit are found there, and the one or
  two best-matching lines lead the injected evidence.
- Lexical recall uses in-memory CJK bigram BM25 over topic, summary, beats and
  participants (`core/canon/lexical.py`). Trigram FTS could not match two-character
  words such as 失忆, 手术 or 炸楼; lexical stage recall rose from 0.62 to 0.94.
- Entity recall includes extracted participants (most were missing from
  `event_entities`), ranks linked events by relevance instead of taking the 30
  latest, and recognizes one-character names (陈, 煌, 砾) only between particles,
  outside a small block list, and only for entities that occur in the database.
- Ranking uses relevance only. Channel and tier bonuses no longer reorder hits;
  the knowledge channel still labels evidence for the gateway. Per-scene cap is 3.
- Fusion is weighted RRF (`fuse()`, k=10; dense 1.0, lexical 0.3, dialogue 0.8,
  entities 0.1).
  With k=60 and equal weights, entity-linked events were counted twice and a
  lexical rank-1 answer lost. An offline sweep over cached dense traces showed a
  broad plateau (final recall 0.94–0.955) across k 5–60 and lexical 0.3–1.0.
  Weights were chosen on the same set, which the plateau makes low-risk but not
  free of overfitting.
- The person filter applies only when a turn names two or more people. With one
  person it removed answers that do not name that person.
- Routing: a turn the local rules call small talk goes to canon when the closest
  event's cosine similarity reaches 0.54, measured without the self names. On r4,
  negatives scored 0.38–0.52 and promoted story questions 0.56 and up.

Tried and not adopted:

- KCL `arc:rerankvl` does not discriminate relevance: an English sanity check
  scored "Bananas are yellow." above the Paris answer, "x" against "y" scored
  0.98, and the Qwen3 reranker prompt template did not change that. The usage
  field suggests the endpoint scores raw text pairs without a reranker template.
  hybrid-rerank remains available for a working reranker; `RERANK_BLEND` can mix
  the pre-rerank order back in. Ordinary memory should keep model rerank off.
- Rewriting 我/你 into 博士/阿米娅 for the dense query raised dense@1 (0.67 to 0.73)
  but lowered recall slightly and pushed some small talk toward story events.
- A Qwen-style query instruction lowered dense@5 and raised every small-talk
  similarity, breaking routing. Both remain off switches in `core/canon/retrieval.py`.

Remaining misses: two questions whose answer is an unnamed rescuer (临光 in 0-9;
neither summary nor beats say "rescue"), one small-talk shaped question below the
routing threshold, and one detail question ranked 9th.

V8 assessment: not now. Data-caused retrieval misses are about 3% of the main
set, and the dialogue channel closed the detail gap without re-extraction. A
channel audit found no event labeled unstated while she speaks in it (0 of 386);
of 36 unstated events sandwiched between her present events in one scene, about
10 look mislabeled (she is silently present, e.g. NL-10 result, 6-16 arrow). A
re-extraction changes event splits and would require relabeling every expected
event ID. Fold two prompt changes into the extraction used for the full 618-scene
build instead: state each event's plot function, and mark silent presence during
location cuts as witnessed.

## Validation plan

Use synthetic fixtures for transport and storage tests. Compare baseline,
hybrid, and hybrid-rerank on the same frozen database and questions. Record
source fingerprints, model identity, candidate IDs/scores, final evidence IDs,
latency, requests, cache hits, failures, and stage settings. Reports containing
story text stay under ignored `.dev_data/`.

Do not infer answer accuracy from retrieval hits. Participant-index gaps,
single-character entity recognition, conclusion/status routing, knowledge
labels, and evidence packing remain distinct follow-up experiments. Query and
event vectors must use the same model identity; remote rerank scores are not
added to the old channel/tier bonuses.

Live model calls consume provider credits and are separate from the offline
suite. Endpoint compatibility and retrieval quality remain unverified until
an explicitly requested live run is recorded.


## Full-corpus retrieval check (2026-09-25)

The frozen `retrieval-100-v2.jsonl` bank has 84 answer-line questions and 15
small-talk negatives. The V10 full build has 4,377 events. Its vector index
was validated against that exact corpus, and all 4,377 events were embedded.
The full-corpus hybrid probe completed without retrieval degradation.

| V10 corpus | Mode | Final recall | Injected recall | Answer line injected | MRR | Small-talk route |
|---|---|---:|---:|---:|---:|---:|
| 100 scenes | baseline | 66/84 (0.786) | 60/84 (0.714) | 56/84 (0.667) | 0.580 | 15/15 |
| 100 scenes | hybrid | 77/84 (0.917) | 77/84 (0.917) | 73/84 (0.869) | 0.705 | 12/15 |
| Full build | baseline | 57/84 (0.679) | 50/84 (0.595) | 50/84 (0.595) | 0.470 | 15/15 |
| Full build | hybrid | 72/84 (0.857) | 68/84 (0.810) | 65/84 (0.774) | 0.651 | 11/15 |

The full build has more distractor events, and hybrid loses five final and nine
injected hits compared with the 100-scene V10 corpus. Against the full-corpus
baseline, hybrid gains 15 final and 18 injected hits, net. Four small-talk
negatives are misrouted to canon: `x04`, `x08`, `x11`, and `x12`. These numbers
measure retrieval of marked answer lines, not generated-answer accuracy, and
the bank samples only the original 100 scenes rather than the full story pack.
The JSON reports live beside the ignored full build under
`canon.retrieval/runs/eval-v2-{baseline,hybrid}-via-test.json`.


## Expanded 200-case retrieval check (2026-09-25)

The local `retrieval-200-v1.jsonl` bank retains all 99 cases from
`retrieval-100-v2.jsonl` (84 answer-line questions and 15 small-talk negatives).
It adds 81 questions tied to specific dialogue lines: 19 from scenes in the
older 100-scene builds and 62 from scenes present only in the full build. It
also adds 20 broad, cross-event questions, including Chernobog, Kazimierz,
Londinium, Babel, and Lone Trail. Each broad question has three independently
supported representative facets. The 128-case `retrieval-200-v1-100-compatible.jsonl`
subset contains only cases whose gold evidence exists in all three older
100-scene builds. The new specific questions were drafted from extracted beats
and their source lines, then screened for obvious unsupported or vague wording.
They are a provisional in-domain set, not an independent blind holdout.

All runs completed against their exact corpus indexes with no retrieval
degradation. The following table uses the same 103 answer-line questions in
every build; the 10 broad questions and 15 negatives are scored separately.

| Build | Mode | Final hit | Injected hit | Answer line injected | Small-talk correct |
|---|---|---:|---:|---:|---:|
| V7 original 100 | baseline | 81/103 | 76/103 | 68/103 | 15/15 |
| V7 original 100 | hybrid | 97/103 | 95/103 | 87/103 | 15/15 |
| V7 rerun 100 | baseline | 76/103 | 69/103 | 65/103 | 15/15 |
| V7 rerun 100 | hybrid | 93/103 | 89/103 | 81/103 | 13/15 |
| V10 100 | baseline | 80/103 | 74/103 | 66/103 | 15/15 |
| V10 100 | hybrid | 92/103 | 92/103 | 82/103 | 12/15 |
| V10 full | baseline | 73/103 | 66/103 | 63/103 | 15/15 |
| V10 full | hybrid | 89/103 | 85/103 | 78/103 | 11/15 |

Across all 165 answer-line questions available in the full build, baseline
finds 130 final hits, injects 117 events and 111 marked lines. Hybrid finds
149 final hits, injects 143 events and 134 marked lines. The 62 newly drafted
full-only fact questions are easier (60/62 final hybrid hits), so the 149/165
headline should always be read alongside the matched table and the original
84-question result (72/84 final hybrid hits).

Broad-question scoring is deliberately stricter: a facet counts only when an
event covering one of its selected source lines appears. This is a reproducible
anchor check, not an exhaustive annotation of every relevant event. On the 10
shared broad questions, hybrid finds 4/30 anchors in each V7 build, 3/30 in
V10 100, and 1/30 in V10 full. On all 20 full-build broad questions, baseline
finds 6/60 anchors and hybrid 14/60; hybrid injects 11/60 anchored events and
9/60 marked lines. Four questions have at least two of three anchors in the
final top five, and one has all three. Increasing top-k from five to ten and
the evidence budget from 900 to 1,800 tokens raises hybrid final anchor hits
only to 16/60 and marked-line injection to 13/60.

Manual inspection shows why anchor coverage needs context. The full hybrid
results for Chernobog and Kazimierz often retrieve later commentary or related
side plots instead of enough consecutive developments for a useful overview;
the Doctor's escape from Chernobog and the later ship crisis are particularly
noisy. The Lone Trail question about Kristen retrieves all three selected
facets, while Londinium civilian experiences retrieve two. Some relevant events
outside the selected anchors are present in other results, so the anchor score
understates topical relevance. The observed gap is in broad-query focus and
multi-event evidence assembly; simply increasing top-k makes only a small
difference under this strict check.

The JSON reports are under each build's ignored `canon.retrieval/runs/` as
`eval-200-v1-{baseline,hybrid}.json`. The full build also contains the
`eval-200-v1-general-{baseline,hybrid}-top10.json` budget comparison.


## Small-talk routing gate (2026-09-25)

On the full build four small-talk negatives (`x04`, `x08`, `x11`, `x12`) cross
the 0.54 dense routing threshold. Measured routing similarities on all four
builds show this is a corpus-scale effect, not a miscalibrated constant: the
misrouted negatives and the retrieval-promoted story questions interleave
completely (`x11` 晚安 scores 0.611 on the full build while promoted story
questions reach down to 0.550; on the V7 original build the same question
scores 0.534). Raising the threshold to exclude the greetings would drop most
promoted fact questions, and a threshold tuned on one corpus size does not
transfer to another.

The fix is a second condition in `route()`: a nameless question that the local
rules call small talk promotes to canon only when the closest event's cosine
similarity reaches 0.54 **and** its distinctive mass reaches 2.7. Distinctive
mass is the summed idf of the probe's CJK bigrams present in this corpus,
divided by that corpus's maximum idf (`distinctive_mass` in
`run_canon_chat.py`). The ratio is dimensionless and follows corpus size, where
the similarity threshold does not. Small talk rides on words the corpus also
uses everywhere (greetings, weather); story questions carry corpus-rare terms;
the two separate cleanly at 2.7 on all four builds.

Offline validation on the saved routing similarities of all four builds: every
previously misrouted negative stays small talk on every build, and the mass
floor costs one fact question on one build only — `u22` (你认野菜认得真准)
drops on the V7 original 100 build, whose corpus matches barely two of its
bigrams; its twin phrasing `p06` keeps the hit there. The full 200-case hybrid
eval rerun on the full build (`eval-200-v1-hybrid-routev2.json`) confirms this
end to end: the four fixed negatives route to small talk, the 13 promoted fact
questions still reach canon, final hits on the 165 answer-line questions are
identical question by question (149 both runs), broad-question anchors stay
at 14/60, and small-talk routing becomes 15/15 (from 11/15). Injected recall
(140 vs 143) and answer-line injection (128 vs 134) move within observed
run-to-run variance; the earlier same-build V7 comparison showed a larger
injected spread (95 vs 89).

For the shared 103-question table the full build now reads 89/103 final (as
before), 83/103 injected, 74/103 answer lines, 15/15 small talk. One known
loss: retrieval promotion cannot rescue `f37`-style questions whose phrasing
is casual while their similarity stays below 0.54; they remain in small talk on
every build, as before.

The hybrid probe now also resumes: rerunning the same command with the same
`--out` keeps every answered question in the report and continues from the
first unanswered one, after checking corpus fingerprint and index identity.
This exists because provider rate limits interrupt long runs; the resumed run
must use identical settings to the initial one.


## Broad-question retrieval direction

The 20 overview questions expose a coverage problem: event-level RRF chooses
several individually similar moments but does not assemble the causes, turning
points, and outcomes of one story. A larger top-k alone yielded only 16/60
representative facets, compared with 14/60 at top five. The marked facets are
examples rather than exhaustive relevance labels, so this is a diagnosis of
coverage, not a precise measure of answer completeness.

A suitable next experiment is a two-stage, source-linked overview route:

1. Detect overview intent and resolve the named place, event, or arc to candidate
   collections and scenes. Retrieve at scene or arc level using existing anchors,
   episode text, event summaries, and entities. Keep these summaries as navigation
   aids; factual claims still cite original event lines.
2. Search events within the leading scope for distinct aspects such as setup,
   key developments, and outcome. Select across different scenes and plot beats
   under a dedicated evidence budget, instead of filling the first five slots
   with nearby or repetitive hits. Let the reply state its scope when evidence
   covers only part of the question.
3. Order events by explicit relations where available. A scene's export position
   can order the presentation within a known story sequence but does not prove
   cross-arc world chronology or anyone's current state. Reviewed temporal facts
   can constrain status claims after approval; the current unreviewed candidates
   cannot be used as answer evidence.
4. Compare against the existing 20 questions, add independently written broad
   questions and human relevance judgments, and report answer-line coverage,
   distinct scene coverage, unsupported claims, latency, and small-talk routing.
   Keep the existing 165 specific questions as a regression check.

This route is proposed, not implemented or scored. It requires a corpus-level
experiment before changing the default terminal or Bot retrieval path.
