# segmem

Long-term memory for coding agents that knows the difference between
*who you are*, *how this repo works*, and *what happened on Tuesday*.

One Python file. SQLite. No server, no daemon, no API key. Works with any
agent that can run a shell command. On Claude Code and Codex CLI, hooks make
the startup read and per-prompt recall automatic.

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
#0-3 2026-08-21 chose SQLite over DuckDB; stdlib, WAL, FTS5
#4 2026-08-21 naps come due only for blocks the wake cover prints
#5 2026-08-22 wake runs from a SessionStart hook; the agent skipped it once

You are awake.
```

Global preferences load whole. The project's conventions load whole and win
over global ones, with both shown so the agent knows why. History loads with
detail that decays: yesterday verbatim, last month as one line. People load
as names only; the agent looks them up when they come up.

## Install

Requires Python 3.8 or later and `git`. Nothing else.

### As a Claude Code plugin

```
/plugin marketplace add mahuebel/segmem
/plugin install segmem@segmem
```

That's the whole install: the three hooks register automatically, and the
doctrine (what to record and when) is injected at session start, so there is
no CLAUDE.md paste and no settings.json merge. Skip the manual steps below;
running both doubles wake and recall.

### Any harness

```sh
git clone https://github.com/mahuebel/segmem ~/.segmem/src
~/.segmem/src/segmem init
```

`init` prints two things:

1. A `## Memory` block. Paste it into `~/.claude/CLAUDE.md` (or your agent's
   `AGENTS.md`). It tells the agent what to record and when.
2. A `hooks` block. Merge it into `~/.claude/settings.json` (Claude Code) or
   save it as `~/.codex/hooks.json` (Codex CLI); both use the same shape. It
   makes the harness run `wake` at every session start and search memory on
   every prompt, so neither depends on the agent remembering.

On a harness without hooks (Cursor, Aider, your own), skip step 2. The prompt
block alone carries it: the agent runs `wake` and `recall` itself. That works,
but it relies on the agent following instructions. If your harness can run a
command at session start or pipe each prompt to a command, point it at
`segmem wake` and `segmem hook`; `hook` accepts the JSON that Claude Code and
Codex send, or plain text, on stdin.

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

## Tags

`--entities=a,b` tags a fact with its subjects: people, components, files.
Tags are one vocabulary across projects. When you write one that matches an
existing tag ignoring case, the stored spelling wins; when it's new but close
to an existing one, `note` says so (`new tag: github_actions (similar:
github-actions)`), and you use the suggestion next time. A tag that looks
like a name with no `people` record gets a nudge to create one. `recall`
prints tags in brackets so you can see what's in use.

Tags earn their keep in three places: they pair project facts with the
global facts they override, they let `promote` match the same fact across
projects, and they're what makes a capitalized word in a prompt count as
something worth looking up.

## Scope

A fact is `global` or belongs to one project, keyed by the git main repo
path so every worktree shares it. `identity` and `people` default to global;
`procedural` and `episodic` default to the current project.

**Project wins.** When a project fact and a global fact share a subject (an
entity tag), wake prints `OVERRIDDEN` with both.

**Promotion needs evidence.** A project fact becomes global only when the
same statement is live in three projects. One observation is a convention;
three is a preference.

## Altitudes

Memory is a supply chain, not an archive; ARCHITECTURE.md holds the full
design. A fact lives at the narrowest altitude whose audience covers
everyone who needs it: the device (this store), the project repo (where the
export verdict sends stable, hot facts, strongest form first: enforcement,
a skill, CLAUDE.md, then docs), and an org layer for the cross-project
residue.

The org layer is a cloned knowledge repo of one-fact-per-file markdown.
Point `SEGMEM_ORG_DIR` at it and segmem indexes it read-only, reindexing
when its git HEAD moves. `recall` and the prompt hook search it, hits
marked `(org)`. Wake never loads it whole; it surfaces three things only:
one summary line, conflicts (a local fact overriding an org fact, which is
the org layer's staleness signal: open an issue on the fact's file), and
co-sign nudges when a local fact matches an open candidate.

Upward writes are always a PR a human approves. `segmem contribute <id>`
prints the candidate file and the commands; facts tagged with a person, and
every identity, people, or raw episodic note, never leave the device.
`segmem org-init <dir>` scaffolds a new knowledge repo with the witnessing
convention: candidates merge to facts at three witnesses, and CODEOWNERS
names the human on the other end of every staleness signal.

## Pressure

A stored claim is a claim under test, and the store tracks the evidence
arriving against it. Every time an entity is tagged in a new note (weight 3),
served by `recall` (2), or mentioned in a prompt (1), that's a touch. Touches
are telemetry, not memory: `wake` never prints them as facts.

**People dossiers.** Only a people note or an explicit review resets the
clock; an episodic note *about* a person raises pressure on their dossier, it
never relieves it. When the weighted touches since the last revision reach
the threshold (6):

- `segmem stale` lists the dossiers under pressure, with counts and dates.
- `wake` flags them under the people list: `alice: dossier from 2026-08-24,
  3 notes since`.
- The `Stop` hook interrupts the agent once per session with the same list
  and one instruction: supersede each dossier with what changed, or confirm
  it unchanged with `segmem touch <name>`.

**Procedural facts.** The same clock runs per note, against the touches on
its entities, with a higher threshold (12), because busy components accrue
touches fast. The first time a note comes under pressure, the verdict is
verify: check the claim against the repo, then supersede what changed or
confirm with `segmem touch <id>`, which prints the exact claim back so a
blind reset is at least a visible one.

A confirmed fact that comes under pressure *again* has proven two things:
it's stable, and it's load-bearing. The verdict changes to export: its home
is the repo. Write it into README, CLAUDE.md, or the file it governs
(`~/.claude/CLAUDE.md` for a global fact), then supersede the note with a
pointer to where it landed. Memory is the staging ground, not the archive; a
fact everyone should see belongs where everyone looks. `segmem touch <id>
--keep` is the escape for a fact the repo can't hold (private context,
another team's repo); it stops export suggestions while verify cycles
continue. segmem never writes the repo itself: the agent does, and decides.

`touch` is the honest way out: it records "reviewed, no change needed"
without writing a fake supersede that would pollute history. Nothing ever
rewrites a note without an agent deciding to.

## Commands

| Command | What it does |
|---|---|
| `segmem wake` | print the memory for the current project |
| `segmem note <kind> "<text>" [--entities=a,b] [--scope=global\|project] [--supersedes=id]` | record one fact, up to 280 bytes |
| `segmem recall <query>` | full-text search across every kind and scope |
| `segmem nap <lo>-<hi> "<text>"` | answer a compression request |
| `segmem promote <id>` | lift a project fact to global, if three projects agree |
| `segmem forget <id>` | delete a misfiled note; episodic only when newest |
| `segmem forget <lo>-<hi>` | drop a bad summary; it's rebuilt on request |
| `segmem stale [--min=n] [--hook]` | list people notes and procedural facts under evidence pressure |
| `segmem touch <entity\|id> [--keep]` | claim reviewed, unchanged; resets its pressure; `--keep` marks a procedural fact memory-resident |
| `segmem contribute <id>` | print the org-repo candidate for a procedural fact, and the PR commands |
| `segmem org-init <dir>` | scaffold a knowledge repo with the witnessing convention |
| `segmem hook [--once --session=id --served=command\|function]` | the prompt hook; reads JSON on stdin |
| `segmem serve [--port=7878] [--no-open]` | serve a live page over the store on loopback; Ctrl-C stops it |
| `segmem html [file] [--no-open]` | write a self-contained snapshot page of the store, and open it |
| `segmem mcp` | run as an MCP server over stdio |
| `segmem prompt [--subagent]` | print the doctrine block; `--subagent` prints the read-only paragraph a subagent gets |
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
(16 per project, 8 for global), chosen greedily: a block may be as wide as it is old, so
the newest facts appear verbatim and each doubling of age gets about the same
number of lines. Picking the cover takes one pass and well under a
millisecond at a million memories.

The agent writes each summary itself. When `wake` needs a summary that
doesn't exist, it prints the two halves and asks for one line, and the agent
answers with `nap`. Compression is requested only when wake would print the
block, never ahead of time, and never in the background.

Raw facts are never edited. A misfiled note can be forgotten by id; anything
else is superseded, not deleted. Summaries are a cache: drop one with
`forget <lo>-<hi>` and the next request rebuilds it.

## Hooks

The `init` output includes this block. For Claude Code, merge it into
`~/.claude/settings.json`; for Codex CLI, save it as `~/.codex/hooks.json`:

```json
{"hooks": {
  "SessionStart": [{"hooks": [{"type": "command", "command": "~/.segmem/src/segmem wake"}]}],
  "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "~/.segmem/src/segmem hook"}]}],
  "Stop": [{"hooks": [{"type": "command", "command": "~/.segmem/src/segmem stale --hook"}]}]
}}
```

- `SessionStart` runs `wake` on every start, resume, and compaction and puts
  the output in context. A startup rule the agent has to remember is a rule
  it will sometimes skip; this removes the dependency.
- `UserPromptSubmit` runs `hook`, which pulls identifiers out of your message
  (code spans, `#123`, paths, snake and kebab names, and capitalized words
  that are known tags), searches
  the current project plus global memory, and adds up to eight hits as a
  `<segmem-recall>` block. No identifiers or no hits means no output. It never
  blocks a prompt.
- `Stop` runs `stale --hook`, which interrupts the agent when a people note
  or a procedural fact has fallen behind the evidence, once per subject and
  session, and never
  twice in a row: a stop caused by its own block passes through.

### Function hooks

Claude Code 2.1.261 carries an early-access hook type behind
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`: a TypeScript module the engine runs
in-process, with typed events instead of stdin JSON. The plugin ships one,
`hooks/hooks.ts`. It answers `prompt.context` with the wake output as a
context block named `segmem`, and `prompt.submit` with the recall hits as
typed context beside the prompt. The command hooks stay in `hooks.json`, so
a session without the flag (Desktop, cloud, Codex, an older build) loses
nothing.

With the flag on, both paths run and neither knows the other's order, so
each output path calls the same command with `--once`: `wake --once` for the
memory at start, `hook --once` for the recall on every prompt. The first to
insert a row in the `claims` table owns it, and only the owner prints. The
key is the session, the command, and the source: `startup` for wake, so a
compaction is a new source and wakes again, and `session` for recall, so the
first prompt decides who serves every prompt after it. Without a session id,
`--once` does nothing. The `served` column records which path spoke, so a
transcript that looks wrong can be traced.

The recall path takes every prompt the command hook takes, whatever its
origin: a scheduled prompt, a peer session's message and one you typed all
get the same memories.

At `agent.spawn` the module appends the read-only rule to the subagent's
prompt: read with `wake` and `recall`, never `note`, `nap`, or `promote`,
and report what you learned so the parent records it. It never refuses a
spawn. The rule's text comes from `segmem prompt --subagent`, so it is
written once, in Python. Without the flag the parent is still told to pass
the rule on, which is the line that has always been in the doctrine block.
This path needs no claim: it writes the subagent's prompt, which no command
hook can reach, so there is nothing to double.

To type-check the module after a Claude Code update, run `/plugin-types` in a
session (it writes `.claude/types/`), then `tsc -p tsconfig.json`.
`claude plugin validate .claude-plugin/plugin.json` shows what the engine
reads from the module.

## Seeing what it knows

```sh
segmem serve
```

opens a live page at `http://127.0.0.1:7878/`. It runs in the foreground
while you look and stops on Ctrl-C; nothing in the hooks depends on it, so
the no-daemon promise holds. Stdlib only, loopback only, read-only: every
route is a `SELECT`, and searching from the page never writes a touch, so
browsing doesn't press on a fact. A spine across the top shows every memory
as one tick in id order, colored by kind, superseded ones hollow. Seven tabs,
reachable with `g` then a letter (`o` `c` `e` `h` `t` `n` `l`); `/` jumps to
search:

- **overview**: what the store holds and what needs a hand. Live count,
  pressure, superseded, summaries, scopes, untagged; a kind × scope matrix
  (click a cell to browse it); notes per day; what each scope's wake costs
  in tokens, from the real command; and the hygiene list: facts that are
  stable and hot or under pressure, dossiers behind the evidence,
  compressions due per scope, untagged facts, duplicates, overrides.
- **console**: what the agent sees at wake, byte for byte, for any scope.
  Click a line and the right pane explains why it prints: overrides,
  touches and pressure since its last review, the verdict `stale` would
  give, the export target, its supersede history, and the commands to copy.
  Episodic lines show the wake seq in the gutter and the global id at the
  right, since `wake` numbers by seq and `recall` by id.
- **ledger**: full-text search with the same FTS5 syntax as `recall`, facets
  by kind, scope, and entity, an expandable row per hit, and a live feed of
  touches and notes as they land.
- **hook**: why recall did, or did not, fire. Type a prompt and see which
  words the four rules keep (code spans, `#123`, path-like words,
  capitalized words that are already tags), which they drop and why, the
  FTS5 query, and the exact `<segmem-recall>` block the agent would get.
  It runs `identifiers()` and the hook's query in-process without the touch,
  so trying phrasings presses on nothing.
- **tree**: how history decays. The episodic merge tree as an icicle, with
  summarized blocks filled, the wake cover outlined, and the block `nap`
  would ask for first dashed. Scrub the budget and the stream length to see
  what wake looks like at 200 or 1,000 notes and where compressions land.
- **entities**: what the store is about. A co-occurrence graph of tags (size
  is facts, line is shared facts, tags that share nothing sit on the outer
  ring), every tag with its kinds and scopes, and vocabulary hygiene:
  near-duplicate spellings, name-like tags with no people record, untagged.
- **lineage**: how a fact changed. Every supersede chain as a timeline with
  word-level diffs between versions.

The page re-renders whenever any other connection commits: it holds one
event stream and the server polls `PRAGMA data_version` twice a second.
Where an action is implied it offers a command to copy; the CLI stays the
only path that writes.

```sh
segmem html
```

writes one self-contained HTML file (no libraries, no server, no network) to
`~/.segmem/segmem.html` and opens it: a snapshot you can send to someone.
Five views:

- **overview**: counts by kind and scope
- **facts**: every memory, filtered by kind, scope, entity, or text, with
  superseded ones hidden unless you ask
- **overrides**: each project fact that beats a global one, and the shared
  subject that links them
- **tree**: the episodic merge tree for a scope, with summarised blocks
  shaded and the current wake cover outlined; a budget slider shows how the
  wake preview changes, and what compression would come due
- **entities**: every tag, how often it appears, and what it co-occurs with

The page is read-only. Where an action is implied it offers a command to copy.

## Claude Desktop and other MCP clients

For a client with no shell (the Claude Desktop chat app, for example), segmem
runs as an MCP server over stdio, still with no dependencies:

```json
{"mcpServers": {"segmem": {
  "command": "~/.segmem/src/segmem", "args": ["mcp"],
  "env": {"SEGMEM_PROJECT": "global"}
}}}
```

On macOS that goes in `~/Library/Application Support/Claude/claude_desktop_config.json`;
use a full path for `command`, since MCP clients don't expand `~`. Restart the
app. The tools are `segmem_wake`, `segmem_note`, `segmem_recall`, and
`segmem_nap`. There are no hooks in a chat client, so add one line to your
Project instructions or preferences: "Call `segmem_wake` before anything
else." `SEGMEM_PROJECT` picks the scope; a chat client has no git checkout,
so `global` is the sensible default.

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
| `touches` | usage telemetry: mentions, recalls, and tags pressing on dossiers |

Set `SEGMEM_DIR` to keep the database elsewhere (a synced folder works),
`SEGMEM_PROJECT` to force a scope key, and `SEGMEM_ORG_DIR` to a cloned
knowledge repo to enable the org layer (indexed read-only into
`org-<hash>.db` beside the main database).

To inspect the database by hand, go through Python (`python3 -c "import
sqlite3; ..."`): the stock macOS `sqlite3` CLI is built without FTS5 and
cannot open the index that segmem's queries depend on.

## Test

```sh
python3 test_segmem.py
```

## Credits

The shape of the history window is an exponential histogram: Datar, Gionis,
Indyk, and Motwani, "Maintaining stream statistics over sliding windows,"
SIAM Journal on Computing, 2002.

The repo exit for stable, hot facts follows the compile-experience-into-
artifacts argument in Tang, Rashtchian, Ferng, Tomkins, Juan, and Vu,
"WikiSkill: Compiling Agent Experience into Persistent Knowledge for Skill
Evolution," 2026 (arXiv:2608.27454).
