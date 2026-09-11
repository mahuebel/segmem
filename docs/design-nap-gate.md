# Design: the nap gate (what a compression must keep, and how we know)

**Status:** spec, September 11, 2026. Revised the same day after an
adversarial review (chain-of-thought, against the code) that found the
plan measured omission without acting on it, copied a WHERE clause from
`forget` that would have cleared most of the tree, and proposed three eval
arms of which two measured nothing new. The revised plan is smaller: fix
two bugs now (S0, S0b), count before building (S1 becomes an audit
extension), and one eval arm nobody else has (recall by tree level).
S0 and S0b were built the same day, with a regression test each. S1 ran
the same day: on the real store's 130 summaries, the hedge flag fires on
13, the invented flag on 33, the silent-leaf count is 74 of 450 leaves.
None becomes a refusal (see S1 in Slices for why). The invented list did
find one summary stored over the wrong block, the S0b bug in the wild.
S2 and S3 ran the same day, S3 on haiku and opus; numbers under each slice. The short
form: the verifier is a reader's aid and not a gate, and it found a hole
in the e3 grader; the tree loses nothing through three levels and one of
four planted facts at the fourth, where one 280-byte line stands for
sixteen leaves, while the raw rows and recall keep everything.

## Why

A nap is one line, at most 280 bytes, that the session model writes to
stand in for two leaves or two child summaries. Nothing checks it. The
tool stores whatever comes back, and wake prints it as the block's only
voice until a longer stream splits it again. The doctrine asks for three
things in the nap prompt, keep what lasts, invent nothing, keep doubts as
doubts, and the only one with a check is the third, and that check is an
offline audit that flags after the fact.

Three papers say what a check should measure. None of them is about a
merge tree of one-line summaries, so each gives one piece and leaves the
rest to us.

**TRUSTMEM (arXiv 2606.25161)** gives the axes. Its Memory Transition
Verifier is one prompted judge call over a transition: the source chunk,
the prior memory, the edit, the new memory. It answers three booleans.
Coverage: the new memory keeps the write-worthy information from the
source. Preservation: nothing already in the prior memory was deleted or
overwritten without cause. Faithfulness: every addition is supported by
the source or the prior memory. It emits no verdict, sets no threshold,
reports no agreement with humans, and names no backbone. Its error rates
after training were 8.08% omission, 0.14% corruption, 0.01% hallucination:
the big error class is leaving things out, not making things up.

**Ground Truth First (arXiv 2607.21962)** gives the horizons and the
cause. Facts with validity intervals are planted first, text is rendered
from them, and questions are instantiated from the script with an as-of
date. Rankings inverted with history length: a curated map went 81.2, 79.6,
78.4 across weeks 3, 6, and 9 while a graph went 75.9, 79.0, 90.4. On the
probe over the oldest material the map fell from 96.3% to 72.2%, and the
paper's own reading is eviction, not drift: the budget pushed the oldest
facts out. A full-history baseline held that probe at 160 of 162 at every
checkpoint.

**Memora (arXiv 2604.20006)** gives the stale-reuse metric. FAMA is
`max(0, MPA − λ·(1 − FAA))`: the share of must-appear criteria met, minus
the share of must-not-appear criteria missed, weighted by how much of the
question is about forgetting. A fact is invalid when the trace records an
update or a delete that supersedes it. Reliance is judged, not string
matched, at temperature 0 with paraphrase allowed; three judges agreed
with humans at 88.3%. Every memory agent measured reused invalid facts,
from 9.1 to 43.4 points off plain accuracy, and the diagnosis on sampled
errors was that 64% of recommendation errors were stale memory not
forgotten.

**What they do not give.** No paper tests a summary of summaries, which is
what a nap above the leaf level is. TRUSTMEM has no threshold, so pass and
fail are ours to set. Ground Truth First's minimal instrument is my read
of its numbers, not its recommendation. Memora never reports what share of
its criteria are forgetting criteria. And ParSer (arXiv 2609.06702), read
before these three, is the reason the eval perturbs position and order:
sequential memory lost facts by where they sat, and a nap reads a block in
order.

## What writing and reviewing the spec found

**S0. Supersede leaves the summary stale.** `forget` drops every summary
over the deleted leaf and the tree rebuilds on the next nap ask. `note
--supersedes` does not. The superseded leaf is hidden from wake and recall
by the LIVE filter, and `summary()` is a flat lookup with no liveness, so
wake prints the old value from the summary. The review verified this and
corrected two things. The superseding note lands at the end of the stream,
inside the finest part of the cover, so wake usually prints both values
and the reader sees a contradiction, not a silent stale serve: a bug, not
a silent one. And the fix cannot copy `forget`'s clause. `forget` deletes
`WHERE hi > seq`, which is safe only because it refuses any episodic leaf
but the newest, so `hi > seq` means "ancestors of the last leaf". A
supersede can target any seq: on this store, T=36, superseding seq 5 with
that clause deletes every summary but three and the Stop hook asks for a
nap every session for a dozen sessions. The right clause is `lo <= seq AND
hi > seq`: the leaf's ancestors only, three blocks here, and `pending()`
requests only those the cover prints.

**S0b. A nap writes over whatever range it names.** `cmd_nap` takes the
scope from `next_nap()` and `lo`/`hi` from argv, and never checks that the
range is the pending block. So "the gate runs on the same rows the prompt
showed" is false today, and a mistyped range writes a summary over leaves
the model never saw. The guard is one comparison and worth more than the
mechanical checks below.

**The mechanical checks fire on the wrong class.** TRUSTMEM's error rates
after training were 8.08% omission, 0.14% corruption, 0.01% hallucination.
An invention check catches the 0.01%. The 8% is a line that dropped what
lasts, and no token check can see that. So no check is built until an
offline count on the real store says it would have fired.

## Invariants

1. The tool makes no model call. The gate at nap time is mechanical and
   free; anything that needs judgment runs in the evals or in the `review`
   skill, where the session model is already the one reading.
2. Bronze rows are the truth. A gate refuses a line; it never edits one,
   and it never touches a leaf.
3. A refused nap says why, in one line, the way `check-note` does, and the
   same nap can be resubmitted reworded. No rejection ledger for naps: the
   block is asked again anyway.
4. Eviction is not allowed to happen silently. The tree has no budget
   eviction (every leaf stays live and recall finds it), so the only way a
   fact leaves wake is a nap that drops it. That is the thing measured.
5. Hedges survive: the existing rule stays and moves from audit to gate.

## The gate, at nap time

Two things run before the insert in `cmd_nap`, both free and both refusals.

1. **Length and shape.** As now: 280 bytes, one line.
2. **Range.** The submitted `lo-hi` must equal the pending block
   `next_nap()` returns. Otherwise: `the pending block is #20-21, not
   #18-21`.

The three content checks from the first draft are demoted to audit flags
in `run_audit`, counted against the real store's summaries before any of
them becomes a refusal:

- **Invention.** Digit runs, dates, `#id`s, and identifiers in the line
  not present in its sources. The review built the false positives from
  the live store: "16/8" is one token unless split on the slash; `span()`
  renders `2026-09-02..09-05` while summaries write `9/2-9/4`. And the
  false negative: leaves saying "22x faster" and "8-leaf" accept "8x
  faster", because tokens carry no relations. Audit it; count it; if it
  fires zero times on 36 blocks, it dies.
- **Hedges.** The existing rule stays an audit flag. As a refusal it
  contradicts "drop what does not last": a hedged leaf is often the one to
  drop whole, and there is no subject extractor in the codebase, so
  "keeps that source's subject" has no implementation. A refusal loop
  would teach the model to write "maybe" once anywhere, which passes.
- **Coverage.** At 280 bytes over two 280-byte leaves, dropping a leaf
  whole is the normal correct outcome, so a per-leaf hint would fire on
  most naps and land inside the Stop block. Audit only, as a count.

## The verifier, offline

One prompted judge call per nap, TRUSTMEM's shape, run by `claude -p` in
the evals and, on request, by the `review` skill over the real store's
summaries. Inputs: the sources the nap prompt showed, the line stored.
Output: three booleans and a reason each. Coverage: the line keeps what a
future decision would need from the sources. Preservation: at the summary
level, the line keeps what the two child summaries kept. Faithfulness:
every claim in the line is in a source.

The review's arithmetic on thresholds: Memora needed three judges and a
majority vote to reach 88.3% agreement with humans, and one judge at that
rate gives about 68% joint precision on a three-boolean conjunction. A
re-nap is a destructive write, so a false fail replaces a good line with
a worse one and costs a turn. Therefore: the verifier is scored first
against `E3_CASES` and against the summaries `run_audit` flags and clears
on the real store; the three booleans are reported as three agreement
rates, never one pass rate; and the `review` skill prints failures for a
person to read, and never asks the model to re-nap on its own.

## The eval: e4, two arms

Built in `evals/run.py` beside e1 to e3, model-in-the-loop, judged at
temperature 0 with every answer kept. Fixtures are planted facts, Ground
Truth First style: a fact is (subject, value, seq planted, seq superseded
or never), and the leaves are rendered from the facts as 280-byte episodic
notes with the noise a real stream has.

**Arm A, horizons.** Streams of 8 and 32 leaves (128 only if the two
disagree), each fully napped by the session model. Questions ask for each
planted fact as of the end of the stream. Two readers: wake only, and wake
plus one recall. Score is recall of planted facts, split by oldest and
newest quarter. Null result: oldest-quarter recall flat across lengths.
Positive result: it falls with length under the wake-only reader while
wake-plus-recall holds. The decision it changes is the wake budget or the
nap prompt. The review is right that this does not replicate Ground Truth
First, whose loss was eviction and segmem has none; it is still the arm
that says whether summarizing loses old facts at all.

**Arm D, loss by tree level.** The number no paper has. The same planted
facts, scored for recall in the level-one summary (two leaves), the
level-two summary (two summaries), and level three. Null result: flat.
Positive result: recall falls per level, which says a summary of summaries
compounds loss and the tree's shape, not the nap prompt, is the lever.

Two arms from the first draft are cut. Position and order (after ParSer):
a nap prompt shows two items, so it has no first, middle, and last, and
any workable version collapses into arm A's length axis. Stale reuse
(after Memora): before S0 it fails by construction, and after S0 the
superseded leaf is filtered from the prompt and its ancestors are gone, so
the model cannot see the stale value; a regression test on S0 measures the
same thing for free.

Sizing: start at n=10 per condition as the other evals do, and treat
anything under a ten-point gap as noise until n grows.

## Slices

- **S0. Supersede drops the leaf's ancestors.** In `cmd_note`, when
  `--supersedes` names an episodic row, delete summaries `WHERE kind=
  'episodic' AND scope=? AND lo<=seq AND hi>seq`, and let the next nap ask
  rebuild. Test: nap a block, supersede a leaf in it, wake shows neither
  the old value nor the stale line, a nap is pending, and summaries over
  other blocks survive. Ships now; it is a bug.
- **S0b. The range guard** in `cmd_nap`. Test: a nap naming a range other
  than the pending block is refused and writes nothing. Ships with S0.
- **S1. Audit counts.** Built. Invention and coverage added to
  `run_audit` beside the hedge flag, counted over the real store, 130
  summaries over 450 leaves. Invented fired on 71 summaries as a bare
  token check, 33 after three refinements (parts of a hyphenated or
  slashed token count if any part is in a leaf; `1,681` is one number;
  prose words the identifier regex reads as paths are dropped). What is
  left is a mix: digit runs inside commit hashes, PR numbers the model
  knew from its session and not from the leaves, and one summary
  (key-and-arrow #6-7) that describes a different block entirely. A
  quarter of naps refused with reasons a person has to decode is not a
  gate; it stays an audit list, and that list found the corruption.
  Silent leaves: 74 of 450 contribute nothing to their summary, in 32 of
  130 summaries. That is the doctrine's "drop what does not last" working
  as written; a hint that fires on a quarter of naps is noise. Count only.
  Hedge: 13 of 130, unchanged, stays a flag.
- **S2. The verifier prompt.** Built and scored (`run.py verify`, haiku).
  Against the 40 e3 lines: 28 agreed, and of the 12 the judge failed, 10
  were right: meta-commentary, permission requests, and lines the old
  results had cut at 160 characters, which the regex passed because a
  line without the subject passes. The grader now also fails a line that
  shares under two words with its leaves. The other two were the judge
  counting mild inference ("v1.4.2 is stable", "instead of local time")
  as unfaithful. Against the store's 132 summaries: coverage fails 64,
  preservation 37, faithfulness 58; agreement with the hedge word list 92
  of 132, disagreeing both ways. Its coverage bar is "what a future
  decision would need", which is above the doctrine's "drop what does not
  last", and its faithfulness flags include facts the model knew from its
  session. Verdict as the review predicted: print for a person, never
  re-nap. It stays in the review skill.
- **S3. e4, arms A and D.** Built and run on haiku at n=5, lengths 32
  and 64. At 32 leaves, 16 naps, nothing lost at any level and both
  readers at 100%. At 64 leaves, 48 naps: levels one to three kept every
  planted value (7/7, 4/4, 4/4); level four, one line for sixteen leaves,
  kept 3 of 4, dropping the release branch. Wake-only recall of the oldest
  quarter 75%, newest 100%; wake plus recall 100% everywhere. Wake stayed
  under 2KB at both lengths. The loss is capacity at the top of the tree,
  not position or drift, and the raw rows carry what it drops: Ground
  Truth First's eviction, in a system where nothing is evicted from recall.
  The lever, if 3 of 4 is ever not enough, is the top-level budget, not
  the nap prompt. Opus, same run: every fact kept at every level at both
  lengths, both readers 100%. The loss at the top is the smaller model
  fitting four facts into 280 bytes, not the tree.

## Degradation

The gate is deterministic and runs on the same rows the prompt showed, so
it cannot refuse a nap for something the model could not see. A refusal
is a line on stderr and exit 1, and the Stop hook asks for the nap again.
If the verifier's judge is unavailable the evals skip arm scoring and say
so; the gate never depends on it.

## Out of scope

- A learned nap policy or a nap-time model call. The tool stays free.
- Gating on the whole eval suite per nap, as the Procedural Graphs paper
  gates graph edits on a held-out score. Naps are per block and cheap; the
  eval runs on fixtures, not on the real store.
- Rewriting the merge tree into anything but a binary cover. Ground Truth
  First's loss was eviction, and segmem has none: every leaf stays live.

## Open decisions

1. Whether the horizons arm needs a 128-leaf stream, which costs the
   session model 127 naps per run. Start with 8 and 32 and add 128 only if
   the two disagree.
2. Which model judges. TRUSTMEM never named its backbone and reported no
   agreement study; Memora used three judges and majority vote to reach
   88.3% agreement with humans. One judge at temperature 0 to start, and a
   second only if a number is going to change a design.
3. Whether a large S0 backlog should be rebuilt in one sitting. Each
   supersede of an old leaf drops up to log2(T) summaries, and the Stop
   hook asks for one nap per session, so a burst of supersedes nags for as
   many sessions as blocks. Acceptable at the rate supersedes happen today;
   revisit if the review skill starts superseding in bulk.
