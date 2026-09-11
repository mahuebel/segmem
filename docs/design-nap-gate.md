# Design: the nap gate (what a compression must keep, and how we know)

**Status:** spec, September 11, 2026. Not built. Backlog said to build it
once a nap has visibly lost something. Writing the spec found one loss that
needs no eval to see: a summary keeps carrying a value after the leaf that
held it is superseded (S0 below). Everything else here waits for that
condition, or for the eval in S3 to show a number worth moving.

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

## What writing the spec found

**S0. Supersede leaves the summary stale.** `forget` drops every summary
over the deleted leaf (`DELETE FROM summaries ... WHERE hi > seq`), and the
tree rebuilds on the next nap ask. `note --supersedes` does not. The
superseded leaf is hidden from wake and recall by the LIVE filter, and the
summary that was written from it still says the old thing, in the block's
only voice. This is Memora's failure exactly: the trace records the
update, the memory keeps serving the prior value. It is the one nap loss
that needs no eval to see, and the fix is the forget precedent applied to
supersede.

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

`segmem nap <lo>-<hi> "<line>"` runs these before the insert, in order,
and the first failure refuses with its reason. Each is a few lines of
Python over the leaves (or the two half-summaries) the prompt showed.

1. **Length and shape.** As now: 280 bytes, one line.
2. **Invention (faithfulness).** Every number, date, `#id`, and identifier
   in the line (the same `identifiers()` the hook uses, plus bare numbers)
   must appear in the sources. A date may appear in either form the store
   uses (`2026-09-02` or `9/2`). Anything novel refuses: `invented: 0.11.0
   is in no leaf`. TRUSTMEM measured hallucination at 0.01% after
   training, so this will rarely fire, and when it does it is right.
3. **Hedges (preservation of doubt).** If a source carries a hedge marker
   and the line keeps that source's subject, the line must keep a hedge
   marker. This is `run_audit`'s rule and the e3 grader's rule, moved to
   write time. It refuses.
4. **Coverage floor.** Each source must contribute at least one identifier
   or entity to the line, or be dropped whole with a hint, not a refusal:
   `#19 contributes nothing to this line`. The doctrine allows dropping
   what does not last, so the tool cannot refuse; it can make the drop
   visible in the same breath. TRUSTMEM's 8.08% omission is the class this
   watches.
5. **Supersede consistency.** A line may not state a value that a live
   row in the same scope supersedes. Cheap version: if any source leaf is
   superseded at nap time, the prompt has already excluded it (LIVE), and
   S0 ensures no summary was written from it. Nothing to check at write
   time once S0 is in.

Nothing here judges whether the line kept the *right* things. That is the
verifier's job, and it costs a model call.

## The verifier, offline

One prompted judge call per nap, TRUSTMEM's shape, run by `claude -p` in
the evals and, on request, by the `review` skill over the real store's
summaries. Inputs: the sources the nap prompt showed, the line stored.
Output: three booleans and a reason each. Coverage: the line keeps what a
future decision would need from the sources. Preservation: at the summary
level, the line keeps what the two child summaries kept. Faithfulness:
every claim in the line is in a source.

Thresholds, which TRUSTMEM leaves open: a nap passes when all three are
true. The evals report the three failure rates separately, as TRUSTMEM's
error judge does, so omission and hallucination are never one number.

The `review` skill runs this over summaries whose leaves it can still see,
prints the failures, and asks the session model to re-nap the failed
blocks. It is a skill because it costs one call per summary and only a
person decides to spend that.

## The eval: e4, three arms

Built in `evals/run.py` beside e1 to e3, model-in-the-loop, graded by a
judge at temperature 0 with every answer kept. Fixtures are planted facts,
Ground Truth First style: a fact is (subject, value, seq planted, seq
superseded or never), and the leaves are rendered from the facts as
280-byte episodic notes with the noise a real stream has.

**Arm A, horizons.** Streams of 8, 32, and 128 leaves, each fully napped
by the session model. Questions ask for each planted fact, as of the end
of the stream. Two readers: wake only, and wake plus one recall. Score is
recall of planted facts, split into oldest quarter and newest quarter. The
crossover to look for is the curated-map one: wake-only recall of the
oldest quarter falling with stream length while wake-plus-recall holds.
If it falls, the tree evicts by summarizing, and the fix is in the nap
prompt or the budget, not in the gate.

**Arm B, perturbation.** The same 32-leaf stream with the planted facts
moved: each fact at the first, middle, and last position of its block,
and the block order reversed. Same questions, wake-only reader. A fact
whose survival depends on its position is a nap that reads the block in
order, and the number to report is the spread between best and worst
position.

**Arm C, stale reuse.** Streams where a third of the planted facts are
superseded mid-stream by a later leaf. Questions ask for the current
value. Each superseded value is one must-not-appear criterion; each
current value one must-appear. Score is Memora's FAMA, with the judge
asked whether the answer relies on the old value. The number to report is
plain accuracy minus FAMA. Before S0 this arm fails by construction and
proves the finding; after S0 it measures whether re-napping restores the
block.

Sizing: Memora separated systems at 150 questions; Ground Truth First was
at the floor of its randomization test with six users. Start at n=10 per
condition as the other evals do, and treat anything under a ten-point gap
as noise until n grows.

## Slices

- **S0. Supersede drops summaries.** In `cmd_note`, when `--supersedes`
  names an episodic row, delete the summaries over its block the way
  `forget` does, and let the next nap ask rebuild. Test: nap a block,
  supersede a leaf in it, wake shows neither the old value nor the stale
  line, and a nap is pending. Ships now; it is a bug.
- **S1. The mechanical gate.** Checks 2 to 4 in `cmd_nap`, shared with a
  `check-nap` the function hook can call before the shell runs, as
  `check-note` is. Test: an invented version number refuses, a dropped
  hedge refuses, a leaf that contributes nothing hints.
- **S2. The verifier prompt** in `evals/run.py` and in the `review` skill,
  with e3's hedge cases as the first fixtures so the judge is checked
  against a grader we trust.
- **S3. e4, arms A and B.** Fixture generator, the two readers, the judge.
  Run on haiku and opus at n=10 and record the numbers in the eval README
  as e2's are.
- **S4. e4, arm C.** After S0, so the arm measures re-napping and not the
  bug.

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

1. Whether check 4 (coverage floor) should ever refuse. The doctrine says
   drop what does not last; a leaf that only said "PR is open" should be
   droppable without ceremony. Hint until e4 arm A says otherwise.
2. Whether the horizons arm needs a 128-leaf stream, which costs the
   session model 127 naps per run. Start with 8 and 32 and add 128 only if
   the two disagree.
3. Which model judges. TRUSTMEM never named its backbone and reported no
   agreement study; Memora used three judges and majority vote to reach
   88.3% agreement with humans. One judge at temperature 0 to start, and a
   second only if a number is going to change a design.
