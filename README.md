# segmem

Segmented, scoped memory for agents. One Python file, SQLite, no daemon.

It keeps OptMem's shape (append-only facts, an agent-written summary tree,
a decaying wake) and adds two axes OptMem lacks: **kind** and **scope**.

## Kinds

| Kind | Holds | At wake | Decay | New fact replaces old? |
|---|---|---|---|---|
| `identity` | who you are, how you like to work | loaded whole | none | yes, with `--supersedes` |
| `procedural` | how this project works and why | loaded whole | none | yes |
| `episodic` | what happened: decisions, root causes, handoffs | decaying cover | fast | no, it's history |
| `people` | who someone is | names only | none | yes |

## Scope

Every fact is `global` or belongs to a project (the git main repo path, shared
across worktrees). `identity` and `people` default to global; `procedural` and
`episodic` default to the current project. At wake, project facts override
global facts on the same subject, and both are printed so the agent sees why.

## Install

```sh
git clone <this repo> ~/.segmem/src
~/.segmem/src/segmem init    # prints the prompt; paste it into CLAUDE.md or AGENTS.md
```

## Commands

| | |
|---|---|
| `segmem wake` | read the memory for the current project; first call of every session |
| `segmem note <kind> "..." [--scope=global\|project] [--entities=a,b] [--supersedes=id]` | record one fact, max 280 bytes |
| `segmem nap <lo>-<hi> "..."` | answer the compression that came due |
| `segmem recall <query>` | FTS5 search across every kind and scope |
| `segmem promote <id>` | lift a project fact to global, if `should_promote` agrees |
| `segmem forget <lo>-<hi>` | drop a bad summary; the next nap rebuilds it |
| `segmem project` | print the scope key for the cwd |

Set `SEGMEM_DIR` to move the database, `SEGMEM_PROJECT` to force a scope.

## Test

```sh
python3 test_segmem.py
```
