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
