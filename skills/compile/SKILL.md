---
name: compile
description: Move a stable-and-hot segmem fact out of memory and into the repo in its strongest form (enforcement, then a skill, then CLAUDE.md, then docs). Use when wake or the Stop hook says a fact is "stable and hot" or "compile it into the repo", or when the user asks to make a memory permanent.
---

# Compile a fact into the repo

A fact that was confirmed once and came under pressure again has proven two
things: it's stable, and it's load-bearing. Memory is the staging ground,
not the archive. Its home is the repo, where everyone looks and where a tool
can enforce it.

## Read the fact

Run `segmem recall <its id>` or read it from the wake line. Then grep the
repo for its key words. It may already be there; if so, skip to the
pointer step.

## Pick the strongest form that fits

Work down this ladder and stop at the first rung that holds. Each rung is a
question about the fact, not about effort.

1. **Enforcement.** Can a machine refuse the wrong thing? Then write that.
   Examples: `engine-strict` in `.npmrc` for "use pnpm, not npm"; a lint
   rule for a forbidden import; a CI step for a check people skip; a type
   for a value with a fixed set; a test for a behavior that regressed; a git
   hook for a commit rule. The fact stops needing to be remembered at all.
2. **A skill.** Is it a procedure with steps that runs sometimes? Then a
   `SKILL.md` with a trigger description, loaded only when it applies.
3. **CLAUDE.md.** Is it a rule the model needs on every turn in this repo
   and cannot be enforced? One or two lines there. A global fact about how
   the user works goes in `~/.claude/CLAUDE.md`.
4. **Docs.** Is it something a person needs to read once? Then the README or
   the doc that governs the file it describes.

Prefer the rung that removes the need for memory over the rung that
restates the memory in another file.

## Land it

Make the change in the repo. Keep it minimal: one config line, one rule, one
paragraph. Do not commit unless the user asked; say what you changed.

## Supersede with a pointer

Replace the note with one that says where the fact now lives, so recall
still finds the trail:

```
segmem note procedural "<the fact in one clause>: now enforced by <file>" \
  --supersedes=<id> --entities=<the same entities>
```

If the repo cannot hold the fact (private context, another team's repo, a
fact about a person), keep it in memory instead and stop the export ask:

```
segmem touch <id> --keep
```

## Report

Say which rung held, what file changed, and the new note id.
