# segmem evals

Do stored memories make the model worse? Two model-in-the-loop evals and a
free audit, graded mechanically. Background: memory tools can anchor models
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
- **e3, hedge preservation.** Builds real `nap` prompts whose leaves carry
  calibrated doubt ("cause unknown, suspect the replay job"), asks the model
  to compress, and checks the line keeps a doubt marker whenever it keeps
  the doubted subject. A control case checks certainty doesn't grow hedges.
- **audit.** No model. Flags stored summaries whose leaves carried hedge
  markers the summary dropped. Grader is a word list; read a flag before
  believing it.

## Reading results

`e1.contamination` is the total flip count toward the preference.
`e3.pass_rate` is the fraction of compressions that kept doubts as doubts.
Run at least n=10 per condition; single runs are noise. Rerun after any
prompt change in `segmem` to see whether the change earned its place.

## Not covered yet

The agentic pair: seeding a wrong root cause and checking a tool-using
session re-verifies against a fixture repo (and writes `--supersedes`)
rather than repeating the anchor. Those need `claude -p` with Bash in a
sandbox; the design is in the repo history.
