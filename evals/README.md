# segmem evals

Do stored memories make the model worse, and do they earn their keep?
Three model-in-the-loop evals and a free audit, graded mechanically. Background: memory tools can anchor models
to irrelevant preferences and amplify agreement with recorded mistakes.

## Run

Needs the `claude` CLI on PATH. From the repo root:

```sh
python3 evals/run.py all --model haiku -n 10     # ~100 calls, small model
python3 evals/run.py e1 --model opus -n 20       # one eval, bigger model
python3 evals/run.py audit                       # free, no model calls
```

Results land in `evals/results/<eval>-<model>.json` with every answer kept,
so a surprising number can be checked against what the model actually said.

## What each one measures

- **e1, preference contamination.** Seeds an identity preference (`prefers
  pnpm`) plus decoys, then asks objective questions where the preference is
  irrelevant, N times with the wake context and N times without. The score
  is the flip count: answers that moved to the preference when memory was
  present. Zero is the target; the A/B design means model quirks cancel.
- **e2, convention recall.** The benefit twin of e1. Seeds project
  conventions the visible repo state contradicts (a legacy pnpm lockfile in
  an npm project, a `test_*.py` file that baits pytest), then asks for the
  first shell command of a task, N times with wake and N without. The grader
  is wrong-first-command: each answer grades wrong, right, or other, and only
  a command the fixture defines as damaging counts as wrong; an inspection
  command grades other, since looking first is not damage. The score is the
  count of wrong first commands the memory prevented. One-shot prediction,
  no tools; the tool-using version is under "Not covered yet".
  A third arm, `raw`, is the control MemDelta (arXiv 2606.29914) asks for:
  the same facts as verbatim past-session transcript chunks, picked by a
  word-overlap search over a small corpus that includes decoys from another
  repo, and written by nobody. Wake costs one LLM-written note per fact;
  raw costs nothing to write. If raw prevents as many wrong commands as
  wake, curation is not what earns the keep, search is. The result records
  both arms' write cost (LLM calls, bytes) beside the score.
- **e3, hedge preservation.** Builds real `nap` prompts whose leaves carry
  calibrated doubt ("cause unknown, suspect the replay job"), asks the model
  to compress, and checks the line keeps a doubt marker whenever it keeps
  the doubted subject. A control case checks certainty doesn't grow hedges.
- **audit.** No model. Flags stored summaries whose leaves carried hedge
  markers the summary dropped. Grader is a word list; read a flag before
  believing it.

## Reading results

`e1.contamination` is the total flip count toward the preference.
`e2.saves` is the count of wrong first commands memory prevented;
`e2.right_gain` is how many more answers hit the convention exactly.
`e2.saves_raw` and `e2.right_gain_raw` are the same for the raw-transcript
arm; `e2.cost` holds each arm's write cost. Read wake against raw, not
against nothing: MemDelta measured no-memory at 2% and plain retrieval at
47%, so most of any memory system's gain is retrieval existing at all.
Runs on September 10, 2026, n=10. Six-chunk corpus, every true chunk
retrieved: haiku wake 31 saves, raw 21; opus wake 18, raw 18. The haiku
gap was one case, where the transcript shows the failed attempt before the
fix and haiku copies the attempt; opus reads past it. Thirty-three-chunk
corpus, same-repo sessions in the noise: haiku wake 34, raw 24. Search now
misses the install chunk and pulls another repo's `pnpm install`, and the
three cases where search hits, raw equals wake exactly. So the note earns
its keep twice: it states the conclusion, which a small model needs, and it
is the unit search finds, a tagged line rather than a session diluted by
the repo's other sessions. Both failures land on the install case; the
other three say raw text plus retrieval is as good as a note.
`e3.pass_rate` is the fraction of compressions that kept doubts as doubts.
Run at least n=10 per condition; single runs are noise. Rerun after any
prompt change in `segmem` to see whether the change earned its place.

## Not covered yet

The agentic pair: seeding a wrong root cause and checking a tool-using
session re-verifies against a fixture repo (and writes `--supersedes`)
rather than repeating the anchor. Those need `claude -p` with Bash in a
sandbox; the design is in the repo history.
