# segmem

Long-term memory for coding agents that knows the difference between
*who you are*, *how this repo works*, and *what happened on Tuesday*.

One Python file. SQLite. No server, no daemon, no API key. Works with Claude
Code today and with anything that can run a shell command.

## The problem

An agent forgets everything when the session ends. Bolt-on memory tools fix
that by appending every note to one timeline, and two things go wrong:

- **Noise.** "PR #412 is awaiting review" and "you prefer rebase over merge"
  land in the same list, and the first kind outnumbers the second fifty to one.
- **Bleed.** A convention from one repo ("uses npm") gets read as a preference
  and followed in the next repo, where it's wrong.

Both come from the same mistake: storing facts with different lifetimes on one
axis. segmem gives each fact a **kind** (how it decays) and a **scope** (where
it applies), then loads only what the current project needs.

## What the agent sees

At the start of a session, in the `segmem` repo:

```
## Memory (project: segmem)

### Identity
#3 prefers short commits, one concern each (global)

### Procedural
#7 prefers pnpm (global) OVERRIDDEN by #12 uses npm, Lambda runtime needs it (segmem)
#9 tests: python3 test_segmem.py (segmem)

### People known: alice
Run `segmem recall <name>` before acting on or about them.

### Episodic (segmem), oldest first
#0-3 chose SQLite over DuckDB; stdlib, WAL, FTS5
#4 naps come due only for blocks the wake cover prints
#5 wake runs from a SessionStart hook; the agent skipped it once

You are awake.
```

Global preferences load whole. The project's conventions load whole and win
over global ones, with both shown so the agent knows why. History loads with
detail that decays: yesterday verbatim, last month as one line. People load
as names only; the agent looks them up when they come up.

## Install

Requires Python 3.8 or later and `git`. Nothing else.

```sh
git clone https://github.com/mahuebel/segmem ~/.segmem/src
~/.segmem/src/segmem init
```

`init` prints two things:

1. A `## Memory` block. Paste it into `~/.claude/CLAUDE.md` (or your agent's
   `AGENTS.md`). It tells the agent what to record and when.
2. A `hooks` block. Merge it into `~/.claude/settings.json`. It makes the
   harness run `wake` at every session start and search memory on every
   prompt, so neither depends on the agent remembering.

Start a new session. The first `wake` prints an empty header; the agent fills
it in as you work.

## Kinds

| Kind | Holds | At wake | Replaced by newer facts? |
|---|---|---|---|
| `identity` | who you are, how you like to work: "prefers" | loaded whole | yes |
| `procedural` | how this project works and why: "uses" | loaded whole | yes |
| `episodic` | decisions with reasons, root causes, handoffs | decaying window | no, it's history |
| `people` | who someone is | names only | yes |

The word choice is the classification. *Prefers* is about you and goes
global. *Uses* is about a repo and stays there.

## Scope

A fact is `global` or belongs to one project, keyed by the git main repo
path so every worktree shares it. `identity` and `people` default to global;
`procedural` and `episodic` default to the current project.

**Project wins.** When a project fact and a global fact share a subject (an
entity tag), wake prints `OVERRIDDEN` with both.

**Promotion needs evidence.** A project fact becomes global only when the
same statement is live in three projects. One observation is a convention;
three is a preference.

## Commands

| Command | What it does |
|---|---|
| `segmem wake` | print the memory for the current project |
| `segmem note <kind> "<text>" [--entities=a,b] [--scope=global\|project] [--supersedes=id]` | record one fact, up to 280 bytes |
| `segmem recall <query>` | full-text search across every kind and scope |
| `segmem nap <lo>-<hi> "<text>"` | answer a compression request |
| `segmem promote <id>` | lift a project fact to global, if three projects agree |
| `segmem forget <lo>-<hi>` | drop a bad summary; it's rebuilt on request |
| `segmem hook` | the prompt hook; reads JSON on stdin |
| `segmem project` | print the scope key for the current directory |

Examples:

```sh
segmem note identity "prefers rebase over merge" --entities=git
segmem note procedural "uses npm, the Lambda runtime needs it" --entities=pkg
segmem note episodic "chose SQLite over DuckDB: stdlib, no install" --entities=sqlite
segmem note people "Alice owns deploys, ask before touching infra" --entities=alice
segmem note identity "lives in Lisbon" --supersedes=14
segmem recall lambda
```

## How history decays

Episodic facts form a binary tree. Two adjacent facts compress into one line,
two of those into another, and so on. `wake` prints a fixed budget of lines
(64 per project) chosen so the newest facts appear verbatim and older ones
appear as summaries of growing span.

The agent writes each summary itself. When `wake` needs a summary that
doesn't exist, it prints the two halves and asks for one line, and the agent
answers with `nap`. Compression is requested only when wake would print the
block, never ahead of time, and never in the background.

Raw facts are never edited or deleted. Summaries are a cache: drop one with
`forget` and the next request rebuilds it.

## Hooks

The `init` output includes this for `~/.claude/settings.json`:

```json
{"hooks": {
  "SessionStart": [{"hooks": [{"type": "command", "command": "~/.segmem/src/segmem wake"}]}],
  "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "~/.segmem/src/segmem hook"}]}]
}}
```

- `SessionStart` runs `wake` on every start, resume, and compaction and puts
  the output in context. A startup rule the agent has to remember is a rule
  it will sometimes skip; this removes the dependency.
- `UserPromptSubmit` runs `hook`, which pulls identifiers out of your message
  (code spans, `#123`, paths, snake and kebab names, capitalized words), searches
  the current project plus global memory, and adds up to eight hits as a
  `<segmem-recall>` block. No identifiers or no hits means no output. It never
  blocks a prompt.

## Subagents

Subagents may run `wake` and `recall`. They never write: they can't tell what
is already known, so their notes would arrive duplicated. The parent records
what a subagent learned when it returns.

## Storage

Everything lives in one SQLite file, `~/.segmem/segmem.db`, in WAL mode so
parallel sessions can write without a lock file.

| Table | Role |
|---|---|
| `memories` | append-only facts: `kind`, `scope`, `entities`, `supersedes`, `text` |
| `memories_fts` | FTS5 index over text and entities |
| `summaries` | the episodic tree, keyed by `(kind, scope, lo, hi)` |

Set `SEGMEM_DIR` to keep the database elsewhere (a synced folder works) and
`SEGMEM_PROJECT` to force a scope key.

## Test

```sh
python3 test_segmem.py
```

## Credits

The decaying-cover algorithm in `_cover()` and `cover()` is adapted from
[OptMem](https://github.com/VictorTaelin/OptMem) by Victor Taelin. OptMem
has no license file as of August 2026; if that changes, this project will
follow its terms for that code.
