# Bounded canon dialogue retrieval

This is an unreleased terminal experiment on `Oedipus-Sub`. It uses the existing
canon database and shared retrieval providers. It does not connect canon to the
Bot, alter the Core provider contract, approve temporal facts, or rebuild corpus
data. Live KCL evaluation was explicitly authorized on 2026-09-26.

This file is a dated record of why the terminal changed and what each change
measured. For the terminal's current behavior see [canon terminal](canon-terminal.md);
for the code structure and the path to the Bot runtime see
[canon runtime architecture](canon-runtime-architecture.md).

## Retrieval and knowledge boundaries

The terminal distinguishes factual questions, broad accounts, impressions,
reasons, predictions, and references to the conversation itself. A unique
single-character substitution inside a name of at least four characters can
normalize the search query; exact names take precedence and ambiguous matches
remain unresolved. This never changes the stored entity ontology.

Short broad questions start from their strongest retrieved event. Other events
in that chapter are not automatically part of the same incident. Structural
navigation follows event edges and source-scene predecessor/successor links for
at most two hops. Each expansion inspects at most four seeds, eight frontier
events per subsequent hop, twelve incident edges per frontier event, two
successor scenes and twenty-four events per visited scene. The returned pool is
capped at forty-eight candidates. Selection uses query relevance, affinity to
the seed event and path type; at most six context events are returned, with at
most three per scene. This adds no embedding calls or model calls of its own.

An extracted causal edge is a navigation hint, including when it has no source
citation. Source-scene adjacency is also only a navigation hint: neither proves
world chronology, causation or character knowledge. The final evidence retains
event identifiers and exact selected source-line keys. Existing explicit broad
queries retain their diverse overview route, augmented with bounded context.

Events whose character channel is `unstated` remain searchable as navigation
anchors but are excluded from injected memories. An uncertainty phrase does not
grant permission to reveal those details. This reduces the old all-corpus
injection metric: the old question bank includes answers whose character
knowledge is unconfirmed. Reports retain that overall metric and separately
report `character_known`; neither metric should be presented as the other.
Incorrect channel labels still require corpus review, not automatic promotion.

The current evidence budget and per-turn pipeline are defined once in
[canon terminal](canon-terminal.md) (Chinese); the dated sections below record
the limits in force at each step. Event topics survive overview summary
compression, and overview evidence prefers substantive lines over isolated names
or acknowledgements. Oversized events do not prevent a subsequent smaller event
from fitting. There is no new vector index, graph service, resident model or
dependency.

## Conversation and answer checking

The generator and reviewer share a selection of complete exchanges, capped at
5,000 estimated content tokens: the opening exchange when it fits within a
quarter of that budget, recent exchanges and relevant older exchanges, at most
ten pairs in total. The complete session remains in process memory; this is an
API context bound, not a bound on total session storage. Named topics survive
up to two intervening small-talk turns. Existing model tool rounds remain
bounded at two.

Conversation citations (`C1`, etc.) establish who said something in this chat.
They cannot establish a world fact. Source memories retain `E` identifiers,
archives `A`, and reviewed temporal facts `F`. Predictions must have supported
premises and remain explicitly tentative. Subjective reactions and natural
questions are allowed without inventing past actions, relationships or habits.

The answer prompt asks for the conversational point first and usually two to
four sentences unless details are requested; this is guidance, not a hard
length cut. It must not convert evidence order into chronology. A malformed
review can retry once per turn. A factual revision may reorganize the answer,
but every revised sentence is reviewed, including claims without explicit names.
An invalid recheck fails closed. This can add latency and does not guarantee
fewer model calls.

Out-of-character cleanup uses explicit meta-language markers rather than a
blanket ban on chapter titles, since a title may also be an organization name.
Present-day reflection on a past event is distinct from asserting a current
world state. Source narration pronouns are resolved from their context rather
than always treating "you" as the roleplayed character.

## Reproducible checks

Offline tests use synthetic text and temporary databases:

```bash
.venv/bin/python -m unittest discover -s tests -q
git diff --check
```

The existing offline question bank remains available:

```bash
.venv/bin/python run_canon_chat.py --questions \
  --retrieval baseline --out .dev_data/canon/eval/retrieval-new.json
```

Live dialogue runs are explicit and write local reports containing source text:

```bash
.venv/bin/python devtools/canon/dialogue_eval.py \
  --conversations .dev_data/canon/eval/conversations.jsonl \
  --db .dev_data/canon/v10/all/build/canon.sqlite \
  --retrieval hybrid --allow-remote \
  --out .dev_data/canon/eval/dialogue-new.json
```

Each JSONL case has `id`, optional `split`, and a `turns` list of user messages.
An optional `history` list seeds complete user/assistant exchanges for long
context checks. `--code-root` selects a preserved implementation snapshot;
the before snapshot includes pre-existing uncommitted changes. Existing output
paths are rejected. Reports include generated answers, selected evidence,
review and tool traces, API-reported token usage, model-response latency,
whole-turn latency and process peak RSS. Provider completion counts can include
reasoning tokens. The first-response field measures the first model request,
not streamed time to first token. Peak RSS includes corpus and vector indexes.
The terminal displays per-turn evidence estimates, time and API token totals
when the provider supplies usage.

Compare matching cases with the same corpus, model, temperature and retrieval
mode. Network latency, generation randomness and parallel provider load make
single-run timing directional rather than a controlled performance benchmark.
Inspect both drafts and final answers; passing retrieval tests does not establish
naturalness. Corpus excerpts and evaluation reports remain under ignored
`.dev_data/`, and are never release assets.


## Measured results — 2026-09-26

The final offline suite passed **249 tests** using the command above. Workspace
`git status --short --branch`, `git diff --check`, `./scripts/status.sh` and the
child whitespace check also completed successfully. Existing dirty changes were
preserved; no commit, release or compatibility pin was created.

An eighteen-turn matched KCL comparison used the supplied development dialogue,
six fresh questions and two questions after twenty-five seeded exchanges:

| Measure | Before | Structural iteration |
|---|---:|---:|
| Generation and review calls | 48 | 48 |
| Provider input tokens | 71,459 | 75,877 |
| Provider completion tokens, including reasoning | 91,862 | 104,620 |
| Total turn time | 388.0 s | 388.8 s |
| Peak process RSS | 368.6 MiB | 369.2 MiB |
| Maximum evidence estimate | 896 tokens | 899 tokens |

These resource measurements precede the last targeted review/history fixes;
they are not an exact paired benchmark of every final prompt change. A local
no-network, twenty-five-query warm retrieval probe measured median latency
89.0 → 137.8 ms and peak RSS 348.4 → 349.4 MiB. Structural expansion itself
adds no model or embedding calls. Review retries can increase individual-turn
costs; a final broad-event probe needed four calls and 64.7 seconds.

The 200-case offline regression retained final candidate recall of 130/165
specific questions (78.8%) and all fifteen negative routes. **Overall answer
evidence injection decreased from 112/165 to 49/165 (67.9% → 29.7%)** when
unconfirmed character knowledge was excluded. For the eighty-nine questions
having character-known answers, injection changed from 45/89 to 49/89
(50.6% → 55.1%). The remaining seventy-six questions have only unconfirmed
answer events. Broad-query final facet recall stayed 13/60, while injection
fell from 12/60 to 5/60. This is a material coverage limitation requiring corpus
review, not a recall improvement across the full question bank.

The final targeted broad-event answer retained both the central confrontation
and the ship's outcome after unsupported claims were removed. The long-history
probe recalled and quoted the opening user message. Some corrected responses
still sound compressed or stiff, and ambiguous questions remain sensitive to
the retrieved anchor and model interpretation. There has been no blinded human
acceptance. These results support the bounded implementation and specific bug
fixes, not a claim that all dialogue-quality problems are solved.

Local reports, final probe text and a blind-review packet are under
`.dev_data/canon/eval/dialogue-20260926/`; `assessment.md` records the exact
comparison inputs and limitations. The reports contain source excerpts and
remain ignored development artifacts.

## Research rationale

[HippoRAG 2](https://arxiv.org/abs/2502.14802) motivates linking passages through
relationships rather than requiring every useful passage to directly match the
question. [RAPTOR](https://arxiv.org/abs/2401.18059) and
[GraphRAG](https://arxiv.org/abs/2404.16130) motivate retrieving at different
levels of context for broad questions. This implementation reuses existing
scene structure; it does not implement their full algorithms or claim their
benchmark results. Hierarchical summaries and inferred cross-scene causal
graphs remain separate work requiring measured benefit and source validation.

## Evidence synthesis iteration — 2026-09-26

The user-supplied question “我们和普瑞赛斯之间发生了什么，我和她什么关系”
exposed an evidence-selection failure in V10. `15-15_beg@e4` contains
Priestess's claim that Originium was her and the Doctor's joint creation and
that their connection survives his memory loss. `15-15_beg@e2` contains their
reunion with Amiya present. These are character-known records. The old single
query spent its first 900-token pack on overlapping final-confrontation events;
raising the limit to 1,800 without changing candidate choice still favored the
same incident. The implementation now reserves an event facet and a separate
Doctor-relationship facet when the question explicitly asks for both, then
uses bounded structural context to add a nearby known event. It treats
Priestess's relationship statements as her claims, not independently proved
facts about a private past. A subsequent KCL revision also repeated the
Doctor's unspoken feeling from a narrator-style event summary as if Amiya
remembered it. The packer now omits summary sentences that explicitly
attribute thoughts or feelings to the Doctor while keeping source dialogue and
observable actions. This is a conservative visibility filter, not a complete
classification of every narrator sentence; the remaining viewpoint boundary
needs source-level review.

Factual search now excludes `unstated` candidates before its per-scene and
`top_k` limits. The overview selector retains such events for scope discovery
but selects character-known events for injection. Its diversity contribution is
one quarter of the previous weight, with at most three events per scene. At this stage, the
base cumulative evidence limit remained 900 estimated tokens. When a broad
selection had known events that did not fit, one additional local packing pass
raised the effective turn limit by at most 300, capped at 1,200; all subsequent
tools and archive additions share that limit. The contextual `canon_overview`
path no longer sorts the evidence pack after adding memories, so bounded tool
result trimming can safely remove the most recently added item.

The saved pre-iteration baseline and the new implementation were evaluated on
the same V10 database and 200-question set with offline lexical retrieval:

| Measure | Saved baseline | Current |
|---|---:|---:|
| Character-known specific answers injected | 49/89 | 55/89 |
| Previously injected known answers lost | — | 0 |
| Negative-route accuracy | 15/15 | 15/15 |
| Broad character-known facets injected | 5/27 | 10/27 |
| Broad answer lines injected for known facets, corrected scoring | 2/27 | 4/27 |
| Largest evidence pack | 900 | 1,200 estimated tokens |

The 200-question set contains sixty broad anchors, of which only twenty-seven
have an event labeled within Amiya's knowledge. Overall specific-question
candidate recall changes from 130/165 to 67/165 because `final` now means
knowledge-filtered candidates; the old count included events she cannot use.
The character-known comparison is the relevant injection measure. The new
KCL-backed hybrid probe of the twenty broad questions injected 12/27 known
facets and six source answer lines under corrected scoring; it is not paired
with an identical saved pre-change hybrid probe. Relevance and diversity were tuned on these existing
anchors, so an independent question set is still required.

Three single-turn KCL answer checks used the same V10 corpus. The exact
Priestess question with hybrid retrieval and tools off first used 826/900
evidence tokens, four model calls, 77.5 seconds, and returned her joint-creation
claim along with the confrontation. Its reviewer removed unsupported chronology
and misleading quotation marks. A later run then exposed an unspoken Doctor
feeling that the reviewer had accepted. After the visibility filter and tighter
three-event selection, the same question used 724/900 tokens, four calls, and
70.0 seconds; its final answer retained the claimed joint creation and
confrontation without asserting that private feeling. It still needed extensive
revision and ended cautiously, so one run cannot establish natural dialogue.
“罗德岛在切尔诺伯格救出博士后是怎么撤离的？” used 1,087/1,200 estimated
evidence tokens, two calls, and 50.5 seconds. Its reviewed answer covered the
westward rendezvous, interrupted communications, pursuit and the order to reach
the first assembly point. Single runs do not establish typical latency.

The 249 existing offline tests pass. No V11 data was built and no database was
changed. Broad coverage is still partial: fifteen of twenty-seven known broad
anchors were not injected even with hybrid retrieval. Some are absent from the
ranked candidate pool, and others lose to related events from the same chapter.
A further phase should audit those paths and compare hierarchical scene
summaries or source-linked cross-scene evidence against the current selector
before proposing a corpus rebuild. [RECOMP](https://arxiv.org/abs/2310.04408)
supports query-conditioned selective evidence, [RAPTOR](https://arxiv.org/abs/2401.18059)
motivates multiple retrieval levels, and [Lost in the Middle](https://arxiv.org/abs/2307.03172)
warns against simply inserting ever longer context. None of those algorithms
has been implemented or credited with these local results.

## Generality audit — 2026-09-27

The reported Priestess question was a diagnostic case, not the tuning target for
this pass. The audit covered all eighty-nine specific questions with at least one
Amiya-known V10 answer event, all fifteen small-talk negatives, and twenty broad
questions. Before changing packing, a baseline budget ablation raised 900 to
1,200, 1,800 and 2,400 estimated tokens: known-answer injection was 55, 56, 59
and 59 of 89 respectively. Extra context alone did little because many answers
were missing from the selected candidates or displaced by earlier event text.

A crowded initial hybrid fact pack now retries once with a shared cap of at most
1,200 and event summaries clipped at 220 characters. It prioritizes the configured
source lines, which are more useful for exact factual claims than extra episode
prose. Multiple named people in one factual question share one evidence pack
without per-subject fan-out; multi-person status questions retain separate subjects. Offline lexical
retrieval keeps its 900-token fact cap: applying this expansion there increased
mean evidence from 698 to 841 tokens across the 200 cases without increasing
known-answer injection. These are local packing decisions, not changes to the
V10 corpus or to Bot memory.

The evaluator previously counted matching wording in another injected event as
an answer line. It now requires the matching event ID. On the same V10 database,
question set, hybrid mode and provider, the saved pre-audit run and final run
compare as follows:

| Measure, 89 known specific questions | Pre-audit | Final |
|---|---:|---:|
| Answer event among final candidates | 81 | 81 |
| Answer event injected | 72 | 80 |
| Answer source-line text prefix injected, event-scoped | 68 | 76 |
| Mean injected evidence estimate | 843 | 1,087 tokens |
| Questions using more than 900 evidence tokens | 1 | 82 |

The old saved report displayed 70 source-line hits; two were cross-event false
positives. There were eight newly injected answer events and no previously
injected known answer lost. The full 200-case lexical run retained 55/89 known
specific injections and all fifteen negative routes; a separate hybrid run also
routed all fifteen negatives correctly. The twenty broad-question hybrid run
injected twelve of twenty-seven character-known representative facets and six
source answer lines. These strict anchors are not a human assessment of answer
completeness; broad causal synthesis remains the main unresolved retrieval gap.

A second failure appeared in a multi-person exact-wording question: the initial
pack contained “白兔子” but missed two source lines where 煌 said “白毛兔子”,
so one KCL reply incorrectly said she had not used that wording. The factual
path now checks source dialogue when a question explicitly supplies a concrete
quoted phrase or appellation, prioritizes up to three character-known matching
events, and retains those matching original lines. It does not infer that an
unfound phrase was never spoken. The KCL recheck answered that case affirmatively
with the exact source wording in its evidence, using two generation/review calls,
1,134/1,200 estimated evidence tokens and 11.4 seconds. A changed-word negative
probe did not affirm the nonexistent wording, but needed four model calls and
still phrased uncertainty imperfectly. These are single runs, not a dialogue
quality benchmark.

Eight additional quote questions were constructed from original lines in eight
different story collections. Both local and hybrid retrieval injected the exact
source line in 8/8; disabling literal lookup in the local counterfactual gave
7/8. Since those questions were derived from the answers, this checks the
mechanism's breadth rather than independently written question quality. Of the
original eighty-nine known specific questions, nine still lack injected answer
evidence. A simple overlapping three-scene lexical window prototype also failed
to cover broad anchors reliably: some representative facets sat beyond the top
forty windows. Existing KCL `arc:rerankvl` was previously measured below hybrid
retrieval in [the retrieval experiment](canon-retrieval-experiment.md), so it was
not enabled as a shortcut.

[RECOMP](https://arxiv.org/abs/2310.04408) motivates evaluating compression by
retained answer utility, not by the number of event IDs that fit. The present
220-character fallback is a bounded local heuristic and does not implement its
trained compressors. [RAPTOR](https://arxiv.org/abs/2401.18059) and
[GraphRAG](https://arxiv.org/abs/2404.16130) suggest hierarchical retrieval for
long explanations, but a V11 build is deferred until independent broad questions,
source-level causal links, and character-knowledge labels are audited. More raw
data alone cannot fix an event that is present but selected or packed poorly.

## Broad retrieval prototype — 2026-09-27

An additional local audit found that twenty-three of twenty-seven
character-known broad facets sit in a collection ranked within the top three
by the existing lexical collection score. For most missed facets, the bottleneck
is identifying the right scene and event inside a plausible collection, not
finding the collection at all. A read-only prototype averaged the already
indexed event vectors into local scene centroids and embedded only the twenty
existing evaluation questions. At twenty retrieved scenes it covered 9/27
known facet scenes; existing scene lexical ranking covered 13/27 and grouping
the existing top event-vector hits covered 13/27. At forty scenes the counts
were 12/27, 15/27 and 17/27 respectively. Scene centroids were therefore not
integrated. Widening the existing event-vector list from forty to two hundred
candidates increased known-facet candidate coverage only from 12/27 to 17/27;
all three selected anchors for two broad questions remained outside the top
two hundred. A fresh scene-text embedding index and a V11 corpus build were
not performed. The next broad-retrieval iteration needs independently written
questions, source-backed multi-step facet labels, and a method that retains
scene/event provenance while testing long causal chains.

## Source-ordered long-story outline — 2026-09-27

The implementation now uses a separate path only for explicit multi-event
story questions. It keeps the same collection and scene navigation, selects up
to sixteen character-known event candidates across plot phases, groups them by
source chapter and scene order, and first inserts compact event summaries with
scene labels. Remaining room is assigned to original lines, up to four per
event. This is a two-level evidence pack: a wider outline for narrative coverage
and narrower original text for concrete claims. Scene order is textual source
order; the generator is told not to turn it into unsupported cross-chapter world
time or causation. The shared evidence limit starts at 900 and can grow to 2,400
estimated tokens only for this path. Short facts, literal quotes, impressions and
small talk retain their prior retrieval, packing and limits.

Local V10 ablations found that simply increasing the existing overview selector
to sixteen or twenty events with 1,800–2,400 tokens raised known-facet injection
only from 10/27 to 14–15/27 in baseline mode, with little gain in original
answer lines. A scene-centroid index was worse than current lexical or grouped
event search. A pure scene-diversity ranker and extra global lexical anchors also
lost or barely gained facets. Those variants were not integrated. The selected
outline keeps source provenance visible and spends extra tokens on original
lines; it still depends on the current collection candidate pool and does not
claim complete causal reconstruction.

On the same twenty broad questions and V10 database, comparison with the saved
pre-iteration reports is:

| Mode and character-known facets | Previous | Source-ordered outline |
|---|---:|---:|
| Baseline answer event injected | 10/27 | 14/27 |
| Baseline answer source line injected | 4/27 | 12/27 |
| Hybrid answer event injected | 12/27 | 16/27 |
| Hybrid answer source line injected | 6/27 | 14/27 |
| Hybrid mean evidence estimate | 1,052 | 2,121 tokens |
| Hybrid maximum evidence estimate | 1,198 | 2,400 tokens |

The full 200-question offline baseline retained exactly the same injected event
IDs and routes for every non-broad case as the saved prior report, including all
fifteen negative questions. This guards the short-recall performance contract
for local retrieval; no paired generated-answer timing or blinded quality rating
has yet demonstrated an improvement in naturalness. Eleven of twenty-seven
known broad anchors still have no selected answer event; thirteen of the
twenty-seven still lack their answer source line. The anchors were used during iteration and are
not an independent test set. No scene-text corpus was sent to the embedding
provider and no V11 build was started.

A full KCL chat/review attempt for a broad relationship progression question
returned HTTP 502 after the upstream waited 300 seconds. A separate single
generation call using the same 2,400-token evidence pack returned in 10.1
seconds (2,640 input and 2,712 completion tokens, including reasoning), but its
draft was not reviewed and is not a quality result. This leaves end-to-end
latency and reviewed answer quality unverified for the new pack.

## Three-state review and targeted repair — 2026-09-28

A live terminal test report attributed most visible errors to the hand-offs
between retrieval, generation, review and repair rather than to any single
stage. Three faults were traced to the checker:

- A coherent revision was rechecked sentence by sentence, and every failing
  sentence was simply cut. Numbered answers then opened with "the second one
  was…", and long accounts lost whole nodes.
- The review returned only true or false. A claim that contradicts the
  evidence and a claim the current pack does not cover landed in one bucket,
  so the logs could not tell a generation error from a retrieval miss.
- A detail missing from the pack was never looked up. The pre-review refetch
  searches only for names absent from the pack. So a place or ordering detail
  that the canon does contain, and that an earlier turn had retrieved, was
  deleted as unsupported.

The review now returns `supported`, `contradicted` or `uncovered` per sentence.
A conflict must cite the evidence it conflicts with, or it counts as a gap. At
most three uncovered claim sentences are searched once with their own text,
through the same `EvidenceAssembler.fetch` and turn budget as the existing name
refetch. Revision notes differ by status: a conflict is corrected from the cited
evidence. A gap costs only the unsupported detail and is never turned into a
hedge, since the output rules forbid hinting at unknown events through
uncertainty. A revised sentence that still fails gets one targeted second
revision, and only its changed sentences are rechecked. After any code-side
drop, a deterministic mend renumbers "第N个/点/条" list items and strips a
leading connective whose preceding sentence was dropped. Counted events such
as "第二次" are never renumbered, because they state facts.

`CheckReport.stages` records every review, lookup, revision and recheck. The
terminal's opt-in `--trace`, `dialogue_eval.py` and `budget_sweep.py` write it
out, so a failed answer can be attributed to a stage. The 312 offline tests
pass. The 316-question retrieval parity comparison is identical, because
retrieval and packing were not touched.

A live run on KCL `arc:chat` used the V11 chat copy at the 2,000-token budget.
It had two parts: the 40-question sweep bank v2 judged by `arc:nexus`, and an
eight-turn replay of the questions in the test report with `--trace`. g04 was
dropped again after four judge timeouts.

Compared with v1.2.24 at the same budget (n = 39, single runs, 95% interval
about ±0.15):

| Measure | v1.2.24 | v1.2.25 |
|---|---:|---:|
| Accuracy | 0.577 | 0.526 |
| Full marks | 0.41 | 0.44 |
| Hallucinated | 5.1% | 0% |
| Unsupported claim present | 23% | 18% |
| Median latency | 5.2 s | 8.3 s |
| Median latency, turns with problems | 11.0 s | 13.9 s |
| Mean calls | 4.05 | 4.72 |
| Mean evidence tokens | 1,200 | 1,476 |

Six questions went up and ten went down.

- Seven of the ten came from a different recall route or a weaker draft, with
  no repair involved.
- One (new32) had an empty draft and fell back to the fixed "cannot remember"
  line.
- Three involved the second pass:
  - d08: the second revision produced the correct answer, but the recheck
    returned invalid JSON and failed closed.
  - d17: a "no such memory" sentence was typed `conversation` without a C
    citation, so the parser downgraded it.
  - g01: a second revision split one sentence at "；", and the old quota on
    fresh sentences dropped a supported one. The quota no longer applies to
    the fully rechecked second pass.

Turns without problems kept their latency; the cost sits in turns with
problems, whose prompts grow with looked-up evidence. Of 31 reviewed turns:

- Issue statuses: 28 uncovered, 2 contradicted.
- Lookups: 27 claims in 20 turns; 16 claims added evidence.
- Second pass: 8 turns.

In the replay, the reviewer caught a borrowed place (a chapter-14 location
attached to the chapter-12 event) and a speculation stated as fact (corrected
to "she guessed"). Both were fixed with minimal edits. It also showed three
remaining limits:

- Deep turns fill the whole budget, so lookups in them find no room.
- A lookup cannot widen an overview item that was clipped.
- A recheck may reject a clause that an earlier pass accepted.

The "turning points since Chernobog" answer still covered only two periods,
because retrieval returned only two. The previous-question bleed did not
reproduce, because the prior answer in history was intact.

## Storyline evidence and alignment check ("先排后说") — 2026-09-29

The user's 布伦特伍德 recount, the 杜宾 and 凯尔希 archive turns, and a
diagnosis page showed three problems:
- the evidence pack was in relevance order;
- the drafting call never saw the evidence instructions;
- the sentence-level review, whole-reply revision and regex patching
  (`mend`, `tidy`) broke narratives apart and encouraged disclaimers.

The user required that no budget rise and chose the local Gemma-4-26B-A4B as
the test model. The terminal flow in [canon terminal](canon-terminal.md)
describes the result (v1.2.28.sub).

Method. HEAD fe17122 (v1.2.27.sub) was run as arm A against the working tree
as arm B, with the same V11 chat database and baseline retrieval (no embedding
calls). Answers came from local gemma at temperature 0.3. KCL arc:chat judged
at temperature 0, with the existing `budget_sweep` judge and the
`sweep_wrap` cross-question rubric.

The bank was sweep-bank-v4 (55 questions) plus six new items:
- two recounts, including the 布伦特伍德 case;
- four archive lookups, including 杜宾, 凯尔希, and a birthday the archive
  leaves 未公开.

Each question ran three times per arm. g04 is skipped by the judge as before.
One arc:chat judge call timed out (HTTP 502) and one was rate-limited (429,
retried). A separate blind arc:chat pass rated narrative shape for the 13
overview, cross and recount questions.

B was revised once after an interim look at the same bank:
- the safety-net recall had been blocked whenever the model had consulted an
  archive for a story question;
- fact answers skipped parts of multi-part questions;
- the old "answer a why question with a stated motive" rule had been dropped.

Both B versions are reported. A 30-question held-out set was then drawn from
retrieval-200-v3-audited. It keeps questions whose answer lines fall in events
Amiya knows and that are not in the bank. Its references are unreviewed, so it
gives direction only.

| Measure (paired by question, 95% bootstrap CI) | A | B first | B final |
|---|---:|---:|---:|
| Accuracy (score / 2) | 0.447 | 0.480 | 0.522, +0.075 (+0.014, +0.142) |
| Hallucinated answers | 9.4% | 8.4% | 7.8%, −1.7 pt (−5.6, +2.2) |
| Unsupported claims per answer | 0.68 | 0.48 | 0.41 (−0.47, −0.09) |
| Model calls per turn | 3.52 | 1.99 | 2.06 |
| Prompt tokens per turn | 13,269 | 7,381 | 7,687 (−42%) |
| Completion tokens per turn | 352 | 122 | 135 |
| Latency median / P90 (s) | 12.4 / 25.4 | 7.2 / 10.6 | 7.5 / 11.1 |
| Answers with disclaimers | 13.8% | 1.5% | 4.3% |
| Archive lookups, accuracy | 0.25 | — | 0.92 |
| Single-incident recounts, accuracy | 0.33 | — | 0.50 |

Held-out set (30 questions, one run per arm):

| Measure | A | B final |
|---|---:|---:|
| Accuracy | 0.450 | 0.417 (−0.20, +0.13) |
| Hallucinated answers | 13.3% | 13.3% |
| Model calls | 3.17 | 2.00 |
| Prompt tokens | 11,718 | 7,593 |
| Latency median (s) | 11.1 | 7.6 |

The cost reduction holds on both sets, and hallucination did not rise on
either. The accuracy gain on the tuned bank does not replicate on the held-out
set, where the difference is within noise.

Narrative shape did not improve for cross-chapter accounts. The blind rating of
naturalness was 4.41 for A and 4.18 for B (paired −0.23, CI −0.56 to +0.10).
The share of answers that reach an outcome fell from 0.64 to 0.46, and
cross/overview answers became shorter.

The cause is the incident window. It was applied whenever the model chose a
light `arc` recall, and a cross-chapter outcome lies outside the anchor's
scene, so gemma correctly said it did not remember the ending. Single-incident
recounts improved.

Proposed next step, not yet run: keep the incident window for one incident and
use the chapter outline for 来龙去脉 / 前因后果 wording.

Local reports, the extra bank, the held-out bank and the analysis scripts are
under `.dev_data/canon/eval/ab-20260929/`. They contain source text and remain
ignored.

## Outline pointers for recounts — 2026-09-30

The user asked for a light chain of thought before speaking. Several variants were tried on local gemma: summary notes, direction-guided notes, and pointer outlines. Summary notes compressed the answer. Pointer outlines were adopted: the model lists memory numbers per block and then expands each block from those memories.

Version C put the outline on every recall turn and was run on the same 55 questions × 3. Compared with the fixed v1.2.28 (B1):

| Measure | B1 | C |
|---|---:|---:|
| Accuracy | 0.494 | 0.497 |
| Hallucinated answers | 7.4% | 8.6% |
| Unsupported claims per answer | 0.41 | 0.60 |
| Output tokens per turn | 131 | 223 |
| Median latency (s) | 7.5 | 12.5 |

Blind narrative rating of the overview and cross questions:

| Measure | B1 | C |
|---|---:|---:|
| Naturalness | 4.12 | 4.39 |
| Told in order | 0.82 | 0.94 |
| Reached the outcome | 0.45 | 0.55 |

C's extra hallucinations came from two sources:
- expansion adding detail the memory lacks;
- accepting a false premise, because the answer block seeks support.

A premise block (C2) was tested on the 29 false-premise, fact and detail questions. It fixed the acceptance once in three runs but did not raise accuracy (0.517 against B1's 0.540). The outline therefore stays on recounts only, and fact and reason turns keep B1's behaviour.

Combining C's measured rows for recount-routed questions with B1's rows for the rest gives:
- accuracy 0.497;
- hallucinated answers 8.0%;
- 2.20 calls per turn;
- median latency 7.5 s.

This is essentially B1, because the current wording rules route only 4 of the 55 questions to recount. Seven of the eleven overview and cross questions are routed to fact or reason, even though the model itself chose deep recall on 27 of their 33 turns. Other kinds almost never choose deep. Routing a turn to recount when the model recalls with `depth=deep` is the proposed next step and has not been measured.

The seven regular expressions added in v1.2.28 were replaced with plain string handling. There are 339 offline tests and all pass. The data, scripts and the version-history page live under `.dev_data/canon/eval/ab-20260929/`.

## Check-chain replay — 2026-09-30

The local model was off, so the stored B1 and C turns were replayed offline (`replay.py` in the same folder). Only the turns whose answer would change were re-judged by KCL arc:chat: 22 turns, with no API errors.

The repair itself behaves. Across all repairs, every sentence that was not flagged (142 of 142) came back unchanged. The problems come from false flags.

The present-tense check raised 24 flags. Fifteen were false, in two ways:
- a continuation word such as 还在 or 依然 marks aspect, not the present;
- the now-word sits inside someone's reported words, as in "阿洛伊泽说……现在已经没有人知道".

On c-t04, a repair turned a correct "现在" into "当时", and the judge marked the change as unsupported four times.

Two changes were replayed:

| Change | Turns | Score | Hallucinated | Key points | Unsupported | Calls |
|---|---:|---:|---:|---:|---:|---:|
| Narrow the present-tense check | 13 | 8 → 8 | 1 → 1 | 10 → 13 | 12 → 11 | −13 |
| Keep the repair instead of the memory-sentence fallback | 9 | 4 → 5 | 1 → 3 | 6 → 8 | 5 → 4 | 0 |

- **Narrowing the check was adopted** (`speaks_of_now`). It ignores continuation words, sentences framed by 当时 or 那时, and a now-word that follows a reporting verb.
- **Removing the fallback was rejected.** On x-c02, the fallback's drop had removed a real order inversion. The fallback's memory sentence now addresses the Doctor as 您 rather than 对方（博士）.

Other findings:
- **Denial check.** It raised 5 flags, all on questions where "没印象" was the right answer. It caught none of the 6 real denials of known facts among B1's 14 hallucinations. Structure cannot tell the two apart, so the check is unchanged.
- **Wasted first draft.** On 60 of 183 B1 turns, the model answered without recalling, so its first draft was discarded. Requiring a tool call on the first round would need a gemma run to measure.
- **Recount gap recall.** Under the "无"-only rule, the gap recall fired on none of the 12 recount turns.

The 2026-09-26 visibility filter (`visible_summary`) was removed. It deleted whole summary sentences in which the Doctor "感到/觉得/意识到". Among Amiya's 1,700 known events, 10 were hit:
- **Seven were deletions in error.** They removed Amiya's own feelings, lines spoken aloud, another character's remark about the Doctor, or Priestess's feeling.
- **Three did concern the Doctor's inner state.** They also took visible facts with them, such as the calamity cloud vanishing.

The viewpoint boundary for the Doctor's unspoken thoughts belongs in the build, where each sentence can be tagged, not in a runtime word pattern.
