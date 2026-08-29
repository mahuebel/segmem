# Altitudes: from personal memory to a company brain

Status: design sketch. The personal-to-project exit (altitude 0 to 1) shipped
in 0.3.0 as the export verdict; everything above it is proposal. Grounding:
the e1/e2 evals in this repo, the WikiSkill paper (arXiv:2608.27454), and
Plantinga's nine-system company-brain survey.

## Thesis

Memory systems fail as databases and succeed as supply chains. A fact moves
up through altitudes as it proves itself, and each crossing is gated by a
human review. Local memory pushes (wake); shared knowledge pulls (recall).
One placement rule governs everything: **a fact lives at the narrowest
altitude whose audience covers everyone who needs it.** Most facts should
die happily at the project rung; the org layer holds only the homeless
cross-project residue.

## Altitude 0: the device

The personal store as it exists today: one SQLite file per person per
machine. Identity, people, raw episodic history, and hot procedural facts.

The kinds are the privacy firewall, structurally rather than by filter:

- `identity` and `people` never leave the device. Not screened out; not
  eligible. There is no code path up.
- `episodic` leaves only as a distilled decision (an ADR-shaped line), by
  explicit agent action, through a review.
- `procedural` is the migratory kind. It starts here and earns its way up.

Wake loads this store whole because it is small, personal, and sub-
millisecond. Nothing shared belongs in the wake path; e2 measured why the
always-injected set is powerful (42 wrong first commands prevented across
160 trials) and therefore dangerous to dilute.

## Altitude 1: the project repo

The 0.3.0 export verdict already targets this rung: a procedural fact that
is confirmed once and comes under pressure again is stable and load-bearing,
and its home is the repo. What 0.3.0 leaves implicit is that "the repo" is a
ladder of forms, ordered by how much trust each demands from the reader:

| Form | Trust required | Memory analog |
|---|---|---|
| enforcement: `packageManager`, a CI check, a lint rule, a Makefile target | none; the mistake fails | (better than memory) |
| a skill | the trigger fires | recall, executable |
| CLAUDE.md | the harness injects | wake, repo-owned |
| README, docs | the reader looks | recall, for humans |

The export nag should ask the form question in descending order: can this
fact be *enforced*? If not, is it a *procedure* (skill)? If not, is it
*doctrine* (CLAUDE.md)? If not, *documentation*. Then supersede the note
with a pointer to where it landed, whichever form won.

Enforcement is the endpoint worth reaching for. e2's grader counts wrong
first commands; a fact compiled into enforcement makes the wrong first
command fail instantly, for every agent and every human, with no memory in
the loop. The WikiSkill ablation is the argument for descending the ladder:
knowledge served conveniently suppresses the pressure to compile it into the
form that needs no serving.

## Altitude 2: the org layer

Only for facts with no project home: cross-repo operational knowledge,
vendor gotchas, institution-wide conventions. The layer is defined by four
properties, not by a technology:

1. a review gate before every write
2. provenance on every claim (who, when, on what evidence)
3. a named owner per fact
4. history

The reference substrate is a knowledge repo: one fact per markdown file,
frontmatter carrying `kind`, `scope` (`org` or `team/<name>`), `entities`,
`witnesses`, `supersedes`; ownership via CODEOWNERS; contribution via PR.
Gorgias Cortex (12,000 markdown nodes, wrong answers become PRs) is the
scale proof. An org whose knowledge owners do not live in git can carry the
same four properties in a doc tool (the Slite shape) or render views from
the repo; the properties are the design, the substrate is a choice.

## Mechanics, generalized from what exists

**The scope ladder grows rungs.** Local beats project beats team beats org,
and wake prints `OVERRIDDEN` pairs exactly as it does today, so the agent
always sees why the nearer fact wins.

**Wake surfaces the org layer only where it disagrees.** The org store is
never loaded whole. At wake, org facts appear only when they share an entity
with a live local fact and conflict with it, plus one summary line so the
agent knows the layer exists. Everything else is pull: `recall` and the
prompt hook search the org index alongside the personal store, hits marked
with provenance. The index is a local FTS cache over the cloned knowledge
repo, rebuilt lazily when git HEAD moves. No daemon, no server, no network
in the hot path.

**Promotion becomes witnessing.** `promote` today lifts a fact global when
the same statement is live in three projects. The org version: a fact is a
candidate when one store contributes it, and it merges when independent
stores co-sign; `segmem contribute <id>` prints the fact file and the PR
command, and an agent that notices its own local fact matching an open
candidate (same `norm()` match promote uses) suggests co-signing. segmem
prints commands; it never pushes. The merge threshold mirrors PROMOTE_MIN:
one observation is an anecdote, three witnesses are institutional knowledge.

**Pressure becomes the contradiction report.** Touch telemetry never leaves
the device. The upward staleness signal is structural instead: when a local
or project fact OVERRIDES an org fact, that disagreement is exactly the
diff Slite mails to a page owner. Doctrine tells the agent to open an issue
on the fact file; CODEOWNERS makes it land on the named human the Plantinga
survey found in every system that holds up.

## Privacy invariants

- `identity` and `people` have no code path off the device.
- An entity that names a person (per the people-note check that already
  nudges tag creation) blocks a fact from contribution.
- Every upward write is a PR authored through a human-run session; segmem
  emits the command and stops.
- Touch telemetry stays local, always.

## What this design refuses

A shared writable memory pool (e1 at org scale, and no named owner);
background consolidation (naps stay lazy and in-band); auto-merge of
candidates; dossiers on people at any shared altitude; telemetry upload.

## Evidence this shape works

- **e1** measured contamination 0 locally; at org scale the same risk is
  other people's claims anchoring your agent, which is why org facts carry
  provenance and enter wake only on conflict.
- **e2** measured the benefit concentrating exactly where visible evidence
  misleads, and rising with model capability; org gotchas are that case at
  fleet scale.
- **#150** in the live store is the killer app in miniature: a wall hit on
  one machine, recorded once, saving every later session. The org layer is
  that motion with more machines.
- **WikiSkill's ablation** (wiki access degraded skill quality) argues for
  the form ladder's descent toward enforcement.
- **Plantinga's survey**: the systems that hold up have a named human on the
  staleness signal. Here that is CODEOWNERS plus contradiction issues.

## Build order, each step shippable alone

1. **Form ladder in the export verdict.** Text change to the 0.3.0 nag.
2. **`SEGMEM_ORG_DIR`.** Read-only index of a cloned knowledge repo;
   recall and the prompt hook search it; wake surfaces conflicts only.
3. **`segmem contribute <id>`.** Prints the fact file and the PR command,
   with the privacy checks applied.
4. **The witnessing convention.** candidates/ directory, co-sign flow,
   merge threshold, CODEOWNERS.

## Open questions

- Whether the team rung ships with the org rung or later (the `scope`
  frontmatter field reserves it either way).
- The bridge for orgs whose knowledge owners do not live in git: rendered
  views from the repo, or a doc-tool substrate holding the four properties.
- Aggregated serve-telemetry as an opt-in staleness signal. Default answer:
  no; contradiction reports carry the signal without shipping behavior data.
