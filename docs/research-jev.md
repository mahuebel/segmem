# Research: Jev and what segmem could do with it

September 18, 2026. Jev launched on September 15, so every claim here is
three days old. Vendor claims and outside tests are kept apart on purpose.

## Verdict

Jev is a judge, not a writer. It can never draft a note or a nap summary.
It can answer the two questions segmem asks most and answers worst: "do
these two lines make the same claim?" and "do these two facts contradict?"
Today string equality answers the first at seven call sites, and a shared
tag answers the second at three.

Build nothing in the tool yet. Run one offline pilot on the labeled data
you already hold (e3 and e4). If Jev passes, add one opt-in, advisory call
at note time. Keep the network out of wake and the prompt hook for good:
spend the judgment at write time, store the result, and let the read path
stay mechanical.

## What Jev is

You send one `state` (text or JSON) and a map of typed questions. It
returns typed answers with probabilities, and no text.

- **Endpoint:** `POST https://api.typesafe.ai/v1/systemone`, bearer key,
  JSON body. The vendor quickstart is a plain `curl`, so `urllib.request`
  covers it and segmem stays one stdlib file.
- **Question types:** Noul (probability of yes), Choice (distribution over
  up to 255 described options, plus confidence), Score (2 to 10 ordered
  levels, a weighted mean, plus confidence).
- **Fan-out:** all questions in a call run in parallel, so 50 questions
  cost the same wait as one. One `state` per call; there is no batch or
  multi-item endpoint.
- **Limits:** about 32k tokens for `state` plus the longest question,
  1,200 requests per minute, text only, English best, hosted in the United
  States only.
- **Price:** $0.042 per million input tokens; output is free. No free tier
  found. Access is by waitlist.
- **Data terms:** no training on inputs. Retention is "as long as
  reasonably necessary". Zero retention is for enterprise customers only.
- **Weak spots the vendor lists:** it cannot count, do arithmetic, or
  order dates. It degrades with large irrelevant state. It follows
  instructions injected into `state`. Noul probabilities are not comparable
  across questions, so rank with one Choice or a Score, never by sorting
  Nouls.
- **"0% hallucination"** means the answer always fits the declared type.
  It says nothing about the answer being right. The CEO conceded this on
  Hacker News.

## How far to trust it

| Source | Task | Result |
|---|---|---|
| Vendor evals, 711 cases | four workflows | Jev 67.8% mean; Haiku 4.5 53.6%; Sonnet 5 67.8%; best model 74.1%. Jev: 0.4s and $0.0004 per case |
| Mike Sherov, 60 cases | tool-call risk | 91.7%; p50 422ms; every wrong answer came with hedged confidence; no LLM baseline |
| anisselbd, 2,000 emails | phishing | Jev 62.6%, Haiku 4.5 81.3%; expected calibration error 0.154 against 0.097; 239ms against 687ms; 12 times cheaper |
| Classmethod, 40 calls | model routing | 40 of 40; about 0.65s |

Speed and cost replicate. Accuracy and calibration don't yet. The vendor's
ground truth is the average of two other models' answers, its LLM rows run
through its own slower wrapper, and it publishes no calibration numbers for
a model sold on calibration. Haiku's 18% in the vendor's prompt mode reads
as a harness fault. There is no paper, no weights, no release date, and the
vendor says it cannot prove the price is unsubsidized. Press summaries
report a $40M seed led by DCVC; the primary release would not load, so
treat that as reported, not confirmed.

## The pilot

Run this before anything else. It changes no product code and costs cents.

1. Join the waitlist and get a key.
2. **Test the headline question first.** Your store holds 164
   `--supersedes` links. Each is a true pair for "does B replace A?".
   Random pairs of the same kind and scope are the false ones; pairs that
   share a tag but no link are the hard false ones, and the case tag
   overlap gets wrong today. Leave out `people` and `identity` rows. This
   needs no eval harness and decides the note-time build.
3. Run Jev over e4, where planted facts give labels no regex wrote: one
   Noul per planted fact, "does the summary keep it?"
4. For e3, hand-label the 40 summaries first. The cases carry a designed
   `hedge_required`, but each pass or fail comes from the regex, so without
   your labels a disagreement can't tell you which grader is wrong. The
   regex scores 35 of 40 and misses paraphrase such as "suspect, not
   proven" turned into "ruling out cache".
5. Bin Jev's probabilities against the labels. You want two numbers:
   agreement, and whether answers at 0.9 and above are right nine times in
   ten. Run Haiku 4.5 on the same pairs as the baseline.

The second number decides everything below. `docs/design-nap-gate.md`
shelved the nap verifier because one judge gives about 68% joint precision
on a three-way check, and a re-nap is a destructive write. A calibrated
probability removes that blocker only if the calibration is real on your
data.

## Uses, ranked

### Offline: build first if the pilot passes

1. **Eval graders.** Replace the hedge word list and the regex graders in
   `plugin-evals` with Score and Noul questions. Also lift the vendor's
   method, whatever model you use: split a policy into code rules plus
   small typed questions. Every model in their table scored higher that
   way on the four-task mean.
2. **`segmem audit --judge`.** Send each fact with its nearest FTS
   neighbors and ask: duplicate, supersedes, refines, contradicts, or
   unrelated? Add a Score for lasting value and a Choice for kind. A
   700-fact store costs under one cent. Show the result in `serve` as a
   store health view: duplicate clusters, live contradictions, misfiled
   kinds, and facts that fail the 30-day test.
3. **Nap verifier as a threshold.** One Noul per leaf: "does the summary
   keep this leaf's lasting claim?" Act only above a cutoff you measured;
   below it, hand the line to the reader as today. This is BACKLOG's "gate
   naps on the evals", unblocked.

### At note time: opt-in and advisory

A note already takes a turn, so 500ms is noise. One call carries every
question at once:

- **Same claim as an existing fact?** Today any reword passes all seven
  equality checks. This also revives `promote`, which needs identical text
  in three projects and so never fires.
- **Does it replace a live fact the agent forgot to name?** Print a
  `--supersedes=<id>` hint. Stale facts left alive are the worst rot a
  memory has.
- **Refinement or override?** Tag overlap can't tell them apart, so wake
  prints OVERRIDDEN for both.
- **30-day test, kind, and "is this tag a person?"** The first two are
  doctrine only today; the third fires on `Redis` and `Django`.
- **Which existing tags fit?** One Noul per tag in the vocabulary, each
  held to its own cutoff and never ranked against the others. This is the
  one that matters most: `hook --tool` and the prompt hook stay
  mechanical and offline, yet get better tags to match on. Judgment moves
  to write time; the read path never touches the network.

Every answer is a hint. None refuses a note until the pilot gives you a
cutoff you trust.

### New things segmem can't do today

- **An independent `touch --used`.** BACKLOG shelved it because the session
  that cites a fact often wrote it. A judge outside the session, run at
  session end, isn't self-confirming: "did this work rely on fact N?"
- **Fewer false stale nags.** Pressure counts mentions as evidence. When a
  fact trips the threshold, ask whether the touching notes update it or
  only mention it, and nag only on the first.
- **A missed-note flag.** At session end: "did this session reach a
  decision that no note records?" Jev flags; the agent writes. This sends
  transcript text off the machine, so it needs its own opt-in.
- **An injection check on org facts.** A colleague's fact lands in your
  agent's context. Ask "is this a claim about the world, or an instruction
  aimed at an agent?" before indexing it. Jev itself follows injected
  instructions, so test this with hostile samples before trusting it.
- **Org layer.** Co-sign and contradiction across colleagues ride on the
  same two questions, with the same fix.

### Not worth it

- **The prompt hook and wake.** `ARCHITECTURE.md` says "no network in the
  hot path", and you cut the first prompt from 1751ms to 155ms by removing
  one model call. A 240 to 670ms remote call on every prompt gives that
  back. Write-time tags and stored scores get most of the gain with none of
  the cost.
- **Anything that writes.** Naps, notes, and compression stay with the
  session model.

## What Ray Amjad's video adds

["Jev + Claude Code = The New Agentic Coding Loop"](https://www.youtube.com/watch?v=ScvXFi4MUSc),
September 18, 2026, 27 minutes. It adds one design idea, one useful
number, and no new evidence on accuracy.

### The loop, which is the point of the Minecraft demo

Jev doesn't play Minecraft alone. Three layers do:

| Layer | Who | Job |
|---|---|---|
| Goal | the person | "build a shelter, then get a diamond pickaxe" |
| Strategy | GPT Astra, run from Codex | sets mini goals; reviews every two minutes and after each death or milestone; rewrites Jev's options and criteria |
| Reflex | Jev | one Choice per decision over the open tasks, given goal, health, hunger, time of day, and recent history as text |
| Hands | a controller mod | carries out "gather wood" or "retreat" |

When Jev is unsure, it pauses the game and hands up to Astra. In about 25
minutes the pair built a shelter, got a diamond pickaxe, and reached the
Nether.

Read it with care. It is one run with no failure count. Astra did the
planning, and the mod did the moving, so Jev's share is picking one task
from a short list. The launch post says of its own Doom demo that "a
non-AI doom bot could play better", and the same holds here. The demo
proves the shape of the loop and its speed, not Jev's judgment.

The shape is what segmem should take. This report treated Jev's questions
as fixed text. They should be data that the session model rewrites:

1. Log each judgment with its outcome. segmem gets outcomes for free: was
   the `--supersedes` hint taken? Was a fact Jev scored high later
   forgotten? Was a flagged duplicate noted anyway?
2. Let the `review` skill read the misses and rewrite the criteria and
   cutoffs, as Astra does after a death.
3. Keep the criteria in one file, not in code.

This also gives "keep the judge swappable" a mechanism: a new Jev version,
or a local model, gets its cutoffs re-tuned by the same loop. And segmem
already runs this loop by hand. An episodic note is the death review; the
`compile` skill is "practice turns slow thought into reflex". A typed
question is one more rung for `compile` to reach: a stable fact becomes a
check on what the agent did, run at session end over the session's
commands, not only a line the agent may or may not heed.

### Skill selection: the nearest published test of the prompt hook's job

The [vendor cookbook](https://docs.typesafe.ai/cookbooks/skill_suggestion)
picks one skill out of 182 for Claude Haiku 4.5 over 488 requests. Wrong
skill loaded: 16.8% alone, 7.3% with Jev's suggestion, 2.5% when handed
the right answer. Needless loads: 9.8%, 4.0%, 1.2%. This is vendor-run,
and it gives no latency.

"Which of 182 skills fits this prompt?" is the same job as "which facts
fit this prompt?", so it is fair evidence that a Choice over the fact set
beats identifier matching on quality. Copy its design for the note-time
duplicate check:

1. One Choice over every candidate, each cut to a short description, plus
   a gate question for "none of these". The cutoff there was 0.30.
2. A second call that re-ranks the top three with their full text.

It doesn't change the hot-path verdict. Every hot path in the video is
either a batch over a corpus or a loop where the world sets the clock: a
game tick, a browser session. None is a network call in front of every
prompt in someone else's coding session. Outside tests put Jev at 240 to
670ms, which doubles segmem's per-prompt time or worse. Write-time tags
buy most of that quality for no wait. To put a number on what is left,
add one arm to e2: a Jev Choice over the FTS top 50 for the install case,
where same-repo noise buried the true chunk.

### The other chapters

- **Primitives and playground:** matches the docs. Reruns vary by 2 to 3
  points. That is stability, not calibration, and the video treats them as
  one. Keep a margin around any cutoff, or answers near it will flip
  between runs.
- **Trading bot:** the same loop. The host says not to trade with it.
- **Browser use and adversarial testing:** Jev drives a browser in about 7
  seconds for 0.4 cents a flow; one team runs dozens in parallel against
  each release. No use for segmem, since `serve` is a small read-only
  page. Worth a look for your products with real user flows.
- **Garbage comments, linters, code smells:** 150 comments in 9.3 seconds
  for about one cent; 28M tokens for $1.19. These are single runs and they
  match the price list. The shape is `audit --judge`: Jev makes the
  shortlist, a writing model fixes it. "Qualitative linter" is the right
  name for the note-time check: each doctrine sentence ("no PR heads",
  "record the why", "keep doubts as doubts") becomes one typed question.
- **Code review:** [`jev-review`](https://github.com/devagrawal09/jev-review)
  stages Noul risk screens, then Choice evidence, then Score severity,
  then routing. Its README gives no numbers. The video's "cuts reading by
  10 times" is a model's estimate, not a measurement.
- **Sentry:** a tweet shown on screen says Jev beat smaller LLMs,
  including GPT-OSS 120B, on a security pipeline at a fifth of the cost. I
  didn't verify it.
- **Official skill:** [`typesafe-ai/skills`](https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md)
  teaches Claude Code or Codex to write Jev calls. It sits beside the
  segmem plugin with no conflict.
- **The host** takes no sponsors, and the video still sells his course and
  his sandbox service. It doesn't mention the phishing benchmark Jev lost.

## Rules for any build

- **Off by default.** The README promises "No server, no daemon, no API
  key". Copy `org_connect()`: if `SEGMEM_JUDGE_KEY` is unset, or the call
  fails or runs past a short timeout, return `None` and behave as today.
- **Never send `people` or `identity` facts.** Retention is open-ended and
  hosting is United States only.
- **Reword design-nap-gate invariant 1** ("the tool makes no model call")
  to "makes no model call unless you opt in, and never on the hot path".
- **Keep the judge swappable.** Thresholds tuned to one Jev version break
  on the next. TypeSafe's own `system-one-adapter-python` runs the same
  typed questions on Claude or GPT models, and OpenJev runs them on a local
  0.6B model in 0.5 to 2 seconds on an M2 Max. If local reaches "good
  enough", the offline tier needs no network at all, which fits segmem
  better than any vendor.
- **Prior art:** `yoshi` (listed in `awesome-jev`) prunes Claude Code
  history by Jev judgment. Read it before building the audit.

## Found along the way

- `identifiers()` at `segmem:1302` treats any sentence-final word as an
  identifier: the regex matches `bug.` and `again.`, and the strip at
  `segmem:1306` removes the dot. Only the silence gate stands between
  prose and one FTS search per sentence.
- The silence gate's `n` counts live rows of every kind, not facts
  (`segmem:1353`, per the code map; not rechecked).
- `cmd_note` doesn't require `--entities` on a people note, though the
  doctrine says "always". An untagged people note never feels pressure.

## Sources

- [TypeSafe launch post](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
- [TypeSafe API reference](https://docs.typesafe.ai/api.md) and [model limits](https://docs.typesafe.ai/models.md)
- [Jev's documented weak spots](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md)
- [TypeSafe privacy policy](https://typesafe.ai/legal/privacy-policy)
- [TypeSafe workflow evals](https://evals.typesafe.ai)
- [Sherov's tool-call benchmark](https://github.com/themsquared/jev-benchmark)
- [anisselbd's phishing benchmark against Haiku 4.5](https://github.com/anisselbd/jev-phishing-bench)
- [Classmethod's routing test](https://dev.classmethod.jp/en/articles/jev-for-llm-model-routing/)
- [Hacker News launch thread](https://news.ycombinator.com/item?id=49717558)
- [awesome-jev project list](https://github.com/yibie/awesome-jev)
- [Ray Amjad's video](https://www.youtube.com/watch?v=ScvXFi4MUSc)
- [Skill suggestion cookbook](https://docs.typesafe.ai/cookbooks/skill_suggestion)
- [jev-review](https://github.com/devagrawal09/jev-review)
- [system-one-adapter-python](https://github.com/typesafe-ai/system-one-adapter-python)
