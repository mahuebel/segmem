# Design: segmem on function hooks (from stdout hooks to a typed in-process layer)

**Status:** design (September 4, 2026, distilled from an ideation session).
Everything here ships behind Claude Code's own flag,
`CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`. A session without the flag runs the
command hooks in `hooks/hooks.json` exactly as before and loses nothing.
S0 is built and verified in the working tree; S1 to S8 are the work.

## Why

segmem's hooks are shell commands that print stdout into context. That works
on every harness, and it stays. Claude Code 2.1.261 carries an early-access
second kind: a TypeScript module (`hooks/hooks.ts`) the engine runs in its own
worker, with typed events and an engine interface `$` for every side effect.
Each idea below moves a rule from the model's memory (CLAUDE.md, doctrine
text) into the harness, which is the top rung of segmem's own form ladder:
enforcement beats a skill beats CLAUDE.md.

The mixed-fleet problem shapes everything. The flag is per process, set by an
env var or a GrowthBook rollout (`tengu_plugin_hooks_modules`), so a user's
sessions will be split between flagged and unflagged for a long time, and
Desktop, cloud sessions, and Codex never have the flag. Both hook kinds run in
a flagged session, and the engine promises no order between them. The
`claims` table in `segmem.db` resolves that: each path that would speak calls
the same command with `--once`, whichever inserts the claim row first speaks,
and the other prints nothing.

**Considered and rejected:**

- Command hook checks the env var and exits early. Rejected: it misses a
  GrowthBook rollout with no env var set. (Do not revisit.)
- A sentinel file per session written by the function hook. Rejected: the
  database already exists, the claim row leaves an audit trail (`served`
  column), and one file per session is litter.
- The function hook suppresses the command path outright. Rejected: a module
  that crashes the worker is unloaded and "what it withheld stays withheld",
  so the command floor must never depend on the module. (Do not revisit.)
- Wake at `session.start`. Rejected by evidence: `prompt.context` fires before
  `session.start` in the 2.1.261 engine, so a wake gathered there never
  reaches the first message. Wake runs inside `prompt.context`, cached.
- Reimplementing note validation (280-byte trim, tag canon) in TypeScript.
  Rejected: one implementation, in Python; the module shells out.
- `ui.render` panels (a wake-budget view inside Claude Code). Deferred, not
  rejected: `segmem serve` covers it; reopen if a user asks for it in the
  terminal.
- Automatic background naps. Rejected by the user: the model stays in the
  loop so hedges survive compression (the pitfall evals measured an 8-point
  loss when the doubts line was dropped).
- `$.ui.ask` dialogs for pressure nags. Rejected by the user: the model
  verifies claims against the repo; the user only sees a notice.
- Registering `note` as a tool. Rejected by the user: note stays a Bash
  command so the "subagents never note" rule holds with no extra enforcement.
- Auto-detecting the org directory from `$.session.repo()`. Deferred, not
  rejected: no convention exists for where an org knowledge repo lives.
  `SEGMEM_ORG_DIR` stays the only switch.

## Invariants

1. The command hooks in `hooks/hooks.json` stay, unchanged in behavior for an
   unflagged session. `hooks.ts` never disables or replaces them; only the
   `claims` table decides which path speaks.
2. Every output path added to `hooks.ts` gets a claim, and its command-hook
   counterpart calls the same command with `--once`. No double output, ever.
   The consistency test `test_plugin_hooks_match_cli` guards this; extend it.
3. `segmem` stays one stdlib Python file over SQLite. Logic lives there;
   `hooks.ts` shells out through `$.process.run` with `timeoutMs` at most
   10000 and never reimplements a rule.
4. A hook never throws its way out. Catch, `$.ui.log` the error, and
   `return next(e)`. The engine skips a failing hook, but a clean fallback is
   the contract.
5. Spell out every `$` call (`$.process.run`, never `$[name]`); the engine's
   validator refuses dynamic access and the module would not load.
6. The plugin never writes memory on its own. No `note`, `nap`, `promote`,
   `forget`, or `touch` call from TypeScript. The model does those. `recall`
   and `hook` may touch entities as they do today; browsing via `serve` must
   still never touch.
7. Subagents may run `wake` and `recall`, never `note`, `nap`, or `promote`.
8. `wake` never blocks and never exits non-zero as a hook.
9. `.claude/types/` is generated per build and stays out of git. Regenerate
   after a Claude Code update; never hand-edit.
10. Every new user-facing behavior lands in `README.md` under
    "Function hooks", in the docs style already used there.
11. `python3 test_segmem.py < /dev/null` must stay green. The stdin redirect
    matters: `hook_input()` reads stdin when it is not a terminal.

## Verification, shared by every slice

```
python3 test_segmem.py < /dev/null
tsc -p tsconfig.json
CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude plugin validate .claude-plugin/plugin.json
```

The types come from the running build. Once per session, or after an update:

```
CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 claude -p --bare "/plugin-types $PWD/.claude/types" < /dev/null
```

Live check, the pattern every slice adapts (a scratch project with its own
store, so the developer's real memory is untouched):

```
S=$(mktemp -d); mkdir -p $S/seg $S/proj; (cd $S/proj && git init -q)
SEGMEM_DIR=$S/seg SEGMEM_PROJECT=$S/proj ./segmem note procedural "the secret word is pomegranate"
cd $S/proj && SEGMEM_DIR=$S/seg CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1 \
  claude -p --plugin-dir ~/Node/segmem --debug-file $S/debug.log --model haiku \
  "What is the secret word in your memory?" < /dev/null
grep -E "hooks module|process.run|prompt\." $S/debug.log
```

The debug log is where the engine names a module it refused, a hook that
threw or overran, and a result it dropped. Read it on every live check.

## The slices

### S0: claims table and wake --once (built, verify and commit first)

- What: `claims(session, cmd, source, served)` in the schema; `claim()`;
  `wake --once [--session=… --source=… --served=…]` reads stdin JSON when no
  session flag is given; `hooks.ts` answers `prompt.context` with a block
  named `segmem`; `hooks.json` names `modules: ["hooks.ts"]` and calls
  `wake --once`; `tsconfig.json`; README section; tests.
- Where: `segmem`, `hooks/hooks.ts`, `hooks/hooks.json`, `test_segmem.py`,
  `README.md`, `tsconfig.json`, `.gitignore`.
- Verify: the three commands above are green; a live check shows one claim
  row per session and the model answers "pomegranate".
- Commit: the working tree also holds the September 2 store review (wake
  budget 16/8, procedural cap, recall ranking). Commit it all as one or two
  commits before S1.

### S1: recall as a typed prompt result

- What: `hook --once` joins the claims mechanism with `cmd='hook'` and
  `source='session'`: the first path to claim on the first prompt serves every
  prompt of that session. Change `claim()` to return the owner (`served`
  value) so both paths can say "speak only if the owner is me". In
  `hooks.ts`, hook `prompt.submit`: run `segmem hook --once --session=<id>
  --served=function` with the stdin JSON `{"prompt": e.text,
  "session_id": <id>}` via `$.process.run`'s `stdin`, then return the chain's
  result with the output appended to `context` (`PromptSubmitResult.context`
  is `readonly string[]`). Empty output adds nothing.
- Where: `segmem` (`claim`, `cmd_hook`), `hooks/hooks.ts`, `hooks/hooks.json`
  (`hook --once`), tests for the owner rule and the hooks consistency test.
- Verify: unit test for owner semantics across two paths and two sessions;
  live check with a prompt naming a known tag shows one `<segmem-recall>`
  block, and the claims table shows `hook/session` served by one path.
- Executor's choice: whether to skip origins that are not a person's prompt
  (`e.origin.kind` other than `composer`, `bridge`, `sdk`). Constraint: parity
  with the command hook is the default; skipping is fine if it is documented.

### S2: subagent doctrine on agent.spawn

- What: hook `agent.spawn` and return `next({ ...e, prompt: e.prompt + "\n\n"
  + DOCTRINE })`, where DOCTRINE is the two-sentence rule: you may run
  `<root>/segmem wake` and `<root>/segmem recall`, never `note`, `nap`, or
  `promote`; report what you learned and the parent records it. Never deny a
  spawn.
- Where: `hooks/hooks.ts`; the doctrine text lives in `segmem` (`PROMPT`)
  today, so add a `segmem prompt --subagent` that prints only that paragraph
  and have the hook call it once and cache it, keeping one source of truth.
- Verify: live check where the prompt asks the model to spawn one Explore
  agent that prints its instructions' last paragraph; the debug log shows
  the `agent.spawn` hook settled; the unflagged path is untouched (CLAUDE.md
  still says to tell subagents, and that line stays).

### S3: note validation before the shell runs

- What: hook `tool.call` with matcher `{ tool: "Bash" }`. When the command
  invokes `segmem note` (match on the plugin's own path or a bare `segmem`),
  run `segmem check-note` with the whole command string on stdin. Python
  `shlex.split`s it, finds the `note` arguments, and runs the same
  `check_len` and `canon` the real note runs, without inserting: too long or
  bad usage prints the trim mark and exits 1; hints (tag spelling, scope tag,
  people hints) print and exit 0. The hook returns `{ deny: <stderr> }` on
  exit 1, otherwise the chain's result with the hints added to `context`.
- Where: `segmem` (`cmd_check_note`, reuse `check_len`, `canon`, `scope_hints`),
  `hooks/hooks.ts`, tests for `check-note` on a too-long line, a near tag, and
  a non-note command (no output, exit 0).
- Verify: unit tests; live check where the prompt asks the model to record a
  300-byte procedural note and the transcript shows the deny with the trim
  mark and a second, trimmed attempt that succeeds.

### S4: pressure visible in the terminal

- What: after wake in `prompt.context`, run `segmem stale` (existing) and
  show a count in `$.ui.status("segmem: N under pressure")` when N > 0, else
  clear it with `undefined`. The Stop-hook block stays as the model's
  trigger. No dialog.
- Where: `hooks/hooks.ts`; `segmem stale` may gain a `--count` flag if the
  existing output is awkward to parse.
- Verify: live check with a store whose dossier is under pressure (seed
  touches, see `test_segmem.py` for how the tests do it) shows the status
  line in the debug log; the unflagged Stop block still fires.

### S5: recall as a registered tool

- What: at `session.start`, `$.tool.register({ name: "recall", description,
  inputSchema: { query: string } })`. Hook `tool.call` with matcher
  `{ tool: "mcp__segmem__recall" }`, run `segmem recall <query>`, and return
  `{ result: <text> }` in the shape the types give for an MCP tool result.
  Recall touches entities as it does from Bash; that is the intended pressure
  signal. Note is not registered.
- Where: `hooks/hooks.ts`; README "Function hooks" gains a line saying the
  tool exists in flagged sessions and Bash recall keeps working everywhere.
- Verify: live check where the prompt says "use the recall tool for
  pomegranate"; the debug log shows the registration and the call; the
  claims table is untouched by this slice.

### S6: nap drafts in context

- What: when wake output ends with a "Compress episodic memories #lo-hi"
  request, call `$.model.complete({ model: await $.session.model(), prompt:
  <the nap prompt text wake printed> })` and add a context block
  `segmem-nap-draft` with the line, framed as a proposal: "run `segmem nap
  lo-hi "<line>"` if it keeps doubts as doubts, else write your own". The
  plugin never runs `nap` itself.
- Where: `hooks/hooks.ts`; `segmem` may gain `next-nap --json` so the hook
  does not parse prose.
- Verify: scratch store with 18 episodic notes (see
  `test_nap_only_when_cover_needs_it`); live check shows the draft block, and
  the model runs `nap` with a line at most 280 bytes.

### S7: org contradictions as a toast

- What: when wake output contains an `OVERRIDDEN` line or an org
  contradiction line, `$.ui.toast` a one-line summary naming the ids, so the
  user sees it without reading wake. No detection of the org directory;
  `SEGMEM_ORG_DIR` stays the only switch.
- Where: `hooks/hooks.ts`.
- Verify: live check with `SEGMEM_ORG_DIR` pointing at a repo made the way
  `org_repo()` in the tests makes one, plus a local fact that overrides it;
  the debug log shows the toast text.

### S8: compaction re-wake, settle the open question

- What: in a flagged interactive session, find out whether `prompt.context`
  fires again after `/compact`. If it does: on that refire, re-run wake (drop
  the cache) and make the command hook's `source=compact` wake stay silent
  when a `startup` claim served by `function` exists for the session, so a
  compaction wakes exactly once. If it does not: leave S0's behavior (the
  command hook wakes on compaction, and the function hook's cached block is
  gone with the compacted context), and record that in the README.
- Where: `segmem` (`claim` lookup by session), `hooks/hooks.ts`, README.
- Verify: the finding written in this spec's Resolved decisions with the
  debug-log lines that prove it; tests for whichever claim rule lands.
- This slice needs an interactive session: `claude --plugin-dir ~/Node/segmem
  --debug-file …` under the flag, then `/compact`. If the executor cannot run
  one, stop and report at this slice; do not guess.

## Degradation and safety defaults

- Flag off, or the module fails to load: the command hooks serve everything,
  as today. The debug log names the module and the reason.
- Module loads but a hook throws or overruns its budget: the engine skips it
  for that dispatch; with invariant 4 the hook has already logged and passed
  `next(e)`. The command hook's claim wins and the session is served.
- Module crashes the worker: the plugin is unloaded for the session and its
  withheld events stay withheld. Nothing in `hooks.ts` withholds, so the
  cost is only the typed extras.
- The claims table grows one row per session per command. Fine for years;
  add a prune to `segmem stale` only if a store shows it (out of scope).

## Out of scope

`ui.render` panels; automatic naps; `note` as a tool; org directory
detection; any change to the MCP server for Desktop; Codex or other
harnesses; changes to `serve`; pruning claims; publishing the plugin
version (bump `plugin.json` only when Mark asks).

## Resolved decisions

- Wake runs in `prompt.context`, cached per module life, not in
  `session.start`: decided by evidence (event order in the debug log).
- Claim key is `(session, cmd, source)`; `--once` with no session id is a
  no-op; `hook_input()` is skipped when `--session` is given so a manual run
  on a pipe cannot hang: decided this session.
- Recall claim is per session, not per prompt (no shared per-prompt id
  between the two paths): decided this session.
- Invariant 2 (a claim per output path) does not reach `agent.spawn`: it
  writes the subagent's prompt, which no command hook can reach, so there
  is no double output to arbitrate. The invariant guards double output, not
  hook count: decided this session.
- `check-note` finds the note by scanning the command's tokens for one
  whose basename is `segmem` followed by `note`, so a compound command
  (`cd x && segmem note ...`) is read too. Quoting `shlex` cannot parse is
  silence and exit 0: never block a command on a guess. `note_scope()` is
  shared with `cmd_note`, so the check and the write cannot drift.
- `stale --count` prints one number and returns before the `--hook` path,
  so counting for the status line never writes a nag touch. The status call
  runs inside the same once-per-module-life branch as wake; `prompt.context`
  is cached by the engine, so refreshing it per prompt would buy nothing.
- A `-p` run has no surface, so `$.ui.status` is dropped and the engine logs
  `no session bound; dropped: <text>`. That is the line the live check reads:
  the call is well formed and has nowhere to draw.
- Two matched `tool.call` registrations in one module are accepted: the
  engine's "one hook per event" rule covers plain registrations, and
  `plugin validate` lists `tool.call{tool=Bash}` and
  `tool.call{tool=mcp__segmem__recall}` side by side. Measured this session.
- The registered tool's full name is `mcp__segmem__recall` under
  `--plugin-dir` too, so the literal matcher holds; the engine serves it
  over a loopback MCP server it starts itself.
- `prompt.context` is dispatched more than once and the dispatches
  OVERLAP; the engine keeps whichever answer settles FIRST. S0's once-guard
  set its sentinel before its await, so the second dispatch passed through
  with an empty value and, being the fast one, won. The typed wake block had
  therefore never once reached a model: every green live check was answered
  by the command hook's wake instead. The guard now caches the promise, not
  the value. Measured this session from two `prompt.context settled` lines,
  2.4ms and 1177.5ms.
- On wake the two paths race and the command hook wins the claim every time
  measured: it and the module start together and its process reaches the
  insert first. Harmless for wake, since both paths print the same text, but
  anything only the module can produce (the nap draft) must not be gated on
  winning, or it never ships.
- `$` may be passed only to a function declared at the top of the file; the
  loader refuses a helper declared inside `register` and names the line.
  `claude plugin validate` catches it, so run all three checks before every
  live check, not two of them.
- S7 reads `wake --conflicts` rather than scanning wake's prose, and takes
  no claim: gating it on the wake claim would have made it dead code the way
  S6's draft nearly was. wake collects the id pairs beside the lines it
  already prints, so there is still one implementation of the rule.
- Naps: draft only, the model approves: user, September 4, 2026.
- Pressure nags: the model verifies via the Stop block, the user sees a
  status line: user, September 4, 2026.
- Tools: register `recall` only: user, September 4, 2026.
- Origin filtering in S1: no filtering. Parity with the command hook is
  the default and costs no code; a scheduled or peer prompt gets the same
  memories a typed one does. Documented in the README.
- The UserPromptSubmit command hook runs *inside* `next(e)` at
  `prompt.submit`, so a function hook that awaited `next(e)` before claiming
  could never win the race. Every hook in `hooks.ts` claims and holds its
  output before it calls `next`, so a claim it wins is a claim it can
  deliver: decided this session.
- Names of new Python flags (`check-note`, `stale --count`, `next-nap
  --json`, `prompt --subagent`): executor's choice; constraint: each is
  documented in the README command list and has one test.
- S8's outcome: open until measured; the rule for each outcome is written
  above, so the executor decides from the log, not from taste.

## Status

- [x] S0 claims table and wake --once (built; commit pending)
- [x] S1 recall as a typed prompt result
- [x] S2 subagent doctrine on agent.spawn
- [x] S3 note validation before the shell runs
- [x] S4 pressure visible in the terminal
- [x] S5 recall as a registered tool
- [x] S6 nap drafts in context
- [x] S7 org contradictions as a toast
- [ ] S8 compaction re-wake settled
