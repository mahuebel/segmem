---
name: review
description: Health review of the segmem store: size, wake cost per project, pressure and where it comes from, duplicates, untagged facts, session bursts. Use when the user asks how memory is doing, says "review segmem" or "audit the store", or once a month.
---

# Review the store

Run `segmem audit`. It prints the numbers; this skill is how to read them
and what to do. Fix what is cheap in the store as you go, then report.

## Read each section

**Memories.** Live versus total by kind. A superseded share above a third
in one kind is normal churn; in identity it means the user's preferences
are being re-noted instead of held.

**Per project.** Wake bytes, procedural notes hidden by the cap, episodic
rows printed raw because no compression landed, and compressions pending.
A wake above about 12 KB costs the session real tokens. The lever is the
pending nap: answer it now with `segmem nap`. Hidden procedural notes are
fine; recall still finds them.

**Pressure.** Each fact or dossier under pressure, with the projects and
sessions its touches came from. A fact pressed mostly from another project
or from a burst of short sessions is not really under pressure; its
evidence is noise. Confirm it with `segmem touch <id>` and look for the
source of the noise below.

**Sessions per day.** A day with many times the usual session count is a
harness, a builder fleet, or an eval, not a person. Those sessions should
run with `SEGMEM_QUIET=1` in their environment: they still read memory but
leave no touches and take no Stop nag. Find the spawner and set it.

**Duplicates.** Live notes with identical text. Keep the older id and
`segmem forget` the newer one.

**Untagged procedural.** Facts with no entities never feel pressure and so
never get reviewed. Supersede each with the same text and the entities it
should carry, or forget it if it fails the 30-day test.

**Store.** Database and write-ahead log sizes. A log many times the
database means a long-lived process holds a connection (`segmem serve`, an
MCP client); harmless. Integrity should say ok.

## Judgment, not just numbers

Look at what the numbers do not show: does the wake read like a briefing a
colleague would want, or like a changelog? Are recent episodic notes
recording why, or only what? Say so.

## Report

Lead with the one thing that changes what the user does next. Then a short
table of the numbers that matter. Then what you fixed in the store and what
needs a person: a spawner to quiet, a fact to verify against a repo you
cannot see. Record one episodic note only for a finding that would change
a future decision.
