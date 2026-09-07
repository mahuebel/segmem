# Backlog

Out of scope for the work that found them. Each says what was seen and why
it was left.

## Touches carry no scope

A kerf prompt that says "html" presses a segmem procedural note tagged
`html`: `touches` has no scope column, so project notes feel pressure from
every project. Global notes should; project notes should not. Nothing is
under pressure today, so it costs nothing yet. Found September 6, 2026 in
the store review. Fix by stamping the touch with the project and filtering
in `note_pressure` for project-scoped rows.

## The engine warns about plugin options on every load

Every flagged session logs `[WARN] plugin segmem: options requested but its
manifest declares no userConfig; every option reads as absent`. The module's
`register` takes only `on`, so nothing asks for options; the warning looks
like the engine reading the second parameter's slot either way. Harmless
noise in the debug log, and it makes a real warning easier to miss. Found
September 5, 2026. Tried September 7 on 2.1.263: an empty `userConfig: {}`
in `plugin.json` does not silence it, so the fix is not on our side, or it
needs a real option declared.
