# Backlog

Out of scope for the work that found them. Each says what was seen and why
it was left.

## The engine warns about plugin options on every load

Every flagged session logs `[WARN] plugin segmem: options requested but its
manifest declares no userConfig; every option reads as absent`. The module's
`register` takes only `on`, so nothing asks for options; the warning looks
like the engine reading the second parameter's slot either way. Harmless
noise in the debug log, and it makes a real warning easier to miss. Found
September 5, 2026 while building the function hooks. Fix by declaring an
empty `userConfig` in `plugin.json`, if that silences it.

## The test suite leaks file handles in org_repo()

`python3 test_segmem.py` prints a ResourceWarning per fact file that
`org_repo()` writes, because it uses `open(...).write(...)` without closing.
Pre-existing and cosmetic; the suite passes. Fix with a `with` block.
