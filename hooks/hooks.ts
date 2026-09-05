// segmem as a function hook: wake and recall as typed results, no stdout
// parsing. Loads only when CLAUDE_CODE_ENABLE_FUNCTION_HOOKS is on (or the
// engine's flag is). The command hooks in hooks.json keep running either
// way; every path here calls the same command with `--once`, and the claims
// table lets exactly one of the two speak.
//
// Wake runs in prompt.context, not session.start: prompt.context fires first.
//
// Ordering: the UserPromptSubmit command hook runs *inside* next(e), so a
// hook that waited for next(e) before claiming could never win. Each hook
// below claims first and holds its output before it calls next, so a claim
// it wins is a claim it can deliver.
import type { Register } from "claude-code";

const TIMEOUT = 10_000;

export const register: Register = (on) => {
  let wake: string | undefined;

  on("prompt.context", async ($, e, next) => {
    if (wake === undefined) {
      wake = "";
      try {
        const r = await $.process.run(
          [$.plugin.root + "/segmem", "wake", "--once",
           "--session=" + (await $.session.id()), "--served=function"],
          { cwd: await $.session.cwd(), timeoutMs: TIMEOUT },
        );
        if (r.exitCode === 0) wake = r.stdout.trim();
        else $.ui.log("segmem wake failed: " + r.stderr.trim());
      } catch (err) {
        $.ui.log("segmem wake failed: " + String(err));
      }
    }
    if (!wake) return next(e);
    return next({ ...e, blocks: [...e.blocks, { name: "segmem", text: wake }] });
  });

  // Recall on every prompt, as the UserPromptSubmit command hook does. No
  // origin filtering: parity with that hook is the default, so a scheduled
  // or peer prompt gets the same memories a typed one does.
  on("prompt.submit", async ($, e, next) => {
    let found = "";
    try {
      const id = await $.session.id();
      const r = await $.process.run(
        [$.plugin.root + "/segmem", "hook", "--once",
         "--session=" + id, "--served=function"],
        {
          cwd: await $.session.cwd(),
          timeoutMs: TIMEOUT,
          stdin: JSON.stringify({ prompt: e.text, session_id: id }),
        },
      );
      if (r.exitCode === 0) found = r.stdout.trim();
      else $.ui.log("segmem hook failed: " + r.stderr.trim());
    } catch (err) {
      $.ui.log("segmem hook failed: " + String(err));
    }
    const r = await next(e);
    if (!found || r.drop !== undefined) return r;
    return { ...r, context: [...(r.context ?? []), found] };
  });

  // The rule the parent is told to pass on, passed on by the harness instead.
  // No claim: this writes the subagent's prompt, which no command hook can
  // reach, so there is nothing to double. Never denies a spawn.
  let doctrine: string | undefined;

  on("agent.spawn", async ($, e, next) => {
    if (doctrine === undefined) {
      doctrine = "";
      try {
        const r = await $.process.run(
          [$.plugin.root + "/segmem", "prompt", "--subagent"],
          { cwd: await $.session.cwd(), timeoutMs: TIMEOUT },
        );
        if (r.exitCode === 0) doctrine = r.stdout.trim();
        else $.ui.log("segmem prompt --subagent failed: " + r.stderr.trim());
      } catch (err) {
        $.ui.log("segmem prompt --subagent failed: " + String(err));
      }
    }
    if (!doctrine) return next(e);
    return next({ ...e, prompt: e.prompt + "\n\n" + doctrine });
  });
};
