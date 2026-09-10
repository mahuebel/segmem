---
name: import
description: Reconcile Claude Code's markdown memory (~/.claude/projects/<slug>/memory/*.md) with segmem. Use when a project has both, when the user says "import my memory" or "merge the memories", or when a wake contradicts something the markdown memory says.
---

# Import markdown memory into segmem

Two memories that don't know about each other drift and contradict. This
skill moves what matters from the markdown files into segmem, once, and
leaves the markdown side as a pointer.

## Find the directory

The slug is the project path with every `/` turned into `-`:

```
ls ~/.claude/projects/$(pwd | tr / -)/memory/
```

`MEMORY.md` is the index; the other files each hold one fact with a
frontmatter `type` of `user`, `feedback`, `project`, or `reference`.

## Map each file to a note

| Markdown type | segmem kind | Scope |
|---|---|---|
| `user` | identity | global |
| `feedback` about how the user works anywhere | identity | global |
| `feedback` about this repo's rules | procedural | project |
| `project` describing a standing rule or how something works | procedural | project |
| `project` describing a decision, a root cause, or a handoff | episodic | project |
| `reference` (a URL, a dashboard, a ticket) | procedural, with the URL in the text | project |

A workstream status ("in progress", "awaiting review", a list of open
slices) is not a memory. Skip it: it fails the 30-day test.

## For each file

1. Run `segmem recall <two or three words from it>`. If a live note already
   covers the fact, skip the file. If a live note says something the file
   contradicts, decide which is current by checking the repo, then supersede
   the wrong one.
2. Compress the body to one line of at most 280 bytes. Keep the rule and the
   why. Drop the how-to-apply narrative unless it changes a decision. Keep
   a hedge as a hedge.
3. Note it, with entities: the component, file, or person the fact is
   about. Take the tag spelling `note` suggests. Date the text only when the
   fact is about a past event.
4. Do not re-note a file that `note` refused as a duplicate.

Work through the files in one pass and keep a tally: imported, skipped as
status, skipped as already known, superseded.

## Leave a pointer

When the pass is done, offer to replace the directory's contents with a
`MEMORY.md` that says memory lives in segmem and how to search it. Delete
nothing without the user's approval; the markdown files are theirs.

## Report

Give the tally, the ids of what landed, and the files you recommend
removing. Record one episodic note for the import itself only if something
about it would change a future decision (for example, a class of markdown
memory that turned out to be all status).
