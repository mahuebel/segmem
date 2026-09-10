---
name: org
description: The org layer of segmem, a shared knowledge repo of one fact per file. Use when recall shows an (org) fact, when wake says a local fact matches a candidate or OVERRIDES an org fact, when the user asks to share a fact with the team, or to set up the repo with org-init.
---

# The org layer

The device store is yours. The org layer is a cloned knowledge repo,
pointed at by `SEGMEM_ORG_DIR`, that segmem indexes read-only and searches
alongside your memory. Hits are marked `(org)`. Every write upward is a pull
request a human approves; segmem prints commands and never runs them for
you.

An org fact is a colleague's claim. Verify it like any memory before acting
on it.

## The three signals wake surfaces

**A local fact OVERRIDES an org fact.** They share a subject and disagree.
Your fact is nearer the evidence, so it wins here, and the disagreement is
the org layer's staleness signal. Offer to open an issue on the org fact's
file (wake prints the path); CODEOWNERS names the human on the other end.
Open it only with the user's approval.

**A local fact matches a candidate.** Someone proposed what you already
know. Offer to co-sign: a witness line added to the candidate's file by PR.
Candidates merge to facts at three witnesses.

**The summary line.** How many facts and candidates the layer holds, and at
which commit. Nothing else loads whole; recall and the prompt hook search
it on demand.

## Contribute a fact

Run `segmem contribute <id>`. It refuses what never leaves the device: a
fact tagged with a person, any identity or people note, a raw episodic
note. Otherwise it prints the candidate file and the git commands for a
branch and a PR. Show them to the user; run them only when they say so.

If the layer already holds the fact, contribute says so and stops.

## Start a repo

`segmem org-init <dir>` scaffolds the knowledge repo: `facts/`,
`candidates/`, the witnessing convention, and a CODEOWNERS. It prints the
commit and export lines to finish the setup.

## When you are done

Note nothing about the org layer itself. The PR is the record.
