# Backlog

Out of scope for the work that found them. Each says what was seen and why
it was left.

## The engine warns about plugin options on every load

Every flagged session logs `[WARN] plugin segmem: options requested but its
manifest declares no userConfig; every option reads as absent`. The module's
`register` takes only `on`, so nothing asks for options; the warning looks
like the engine reading the second parameter's slot either way. Harmless
noise in the debug log, and it makes a real warning easier to miss. Found
September 5, 2026. Tried September 7 on 2.1.263: an empty `userConfig: {}`
in `plugin.json` does not silence it, so the fix is not on our side, or it
needs a real option declared.

## Gate naps on the evals

A nap is an LLM rewrite of a block and nothing checks it: the pitfall evals
(contamination, hedges) run by hand. Google's Procedural Graphs paper (arXiv
2609.09153, September 2026) commits a rewrite only when a held-out score
does not drop, and that gate is what let a bare skeleton beat hand-built
graphs. The segmem version: run the two evals on a nap's line and refuse a
rewrite that regresses. Left September 10, 2026 with the tool-keyed recall
and the rejection ledger from the same paper shipped: worth doing once a nap
has visibly lost something, not before.
