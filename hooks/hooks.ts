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
      // What the Stop hook will interrupt about, as a line the user can see
      // before it does. The block in the Stop hook stays the model's trigger.
      try {
        const r = await $.process.run(
          [$.plugin.root + "/segmem", "stale", "--count"],
          { cwd: await $.session.cwd(), timeoutMs: TIMEOUT },
        );
        const n = r.exitCode === 0 ? Number(r.stdout.trim()) : 0;
        $.ui.status(n > 0 ? "segmem: " + n + " under pressure" : undefined);
      } catch (err) {
        $.ui.log("segmem stale failed: " + String(err));
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

  // The note rules, before the shell runs rather than after it failed. The
  // check writes nothing: Python re-runs its own length and tag checks on
  // the command text and says refuse or warn. Any other Bash command passes
  // untouched, and the substring test keeps the shell-out off that path.
  on("tool.call", { tool: "Bash" }, async ($, e, next) => {
    if (!e.command.includes("segmem")) return next(e);
    let hint = "";
    try {
      const r = await $.process.run(
        [$.plugin.root + "/segmem", "check-note"],
        { cwd: await $.session.cwd(), timeoutMs: TIMEOUT, stdin: e.command },
      );
      if (r.exitCode !== 0) return { deny: r.stderr.trim() || r.stdout.trim() };
      hint = r.stdout.trim();
    } catch (err) {
      $.ui.log("segmem check-note failed: " + String(err));
    }
    const r = await next(e);
    if (!hint || r.deny !== undefined) return r;
    return { ...r, context: [...(r.context ?? []), hint] };
  });

  // Recall as a tool the model can call directly. Bash recall keeps working
  // everywhere, so an unflagged session loses nothing. `note` is not
  // registered: it stays a Bash command, which is what keeps "subagents
  // never note" true with no extra enforcement.
  on("session.start", async ($, e, next) => {
    try {
      const t = await $.tool.register({
        name: "recall",
        description:
          "Search segmem, the project's memory, across every kind and scope. " +
          "Use it when a prompt names a person, component, branch, issue, or " +
          "past decision.",
        inputSchema: {
          type: "object",
          required: ["query"],
          properties: { query: { type: "string", description: "words to search for" } },
        },
      });
      $.ui.log("segmem registered " + t.tool);
    } catch (err) {
      $.ui.log("segmem tool.register failed: " + String(err));
    }
    return next(e);
  });

  on("tool.call", { tool: "mcp__segmem__recall" }, async ($, e, next) => {
    try {
      const r = await $.process.run(
        [$.plugin.root + "/segmem", "recall", String(e.query ?? "")],
        { cwd: await $.session.cwd(), timeoutMs: TIMEOUT },
      );
      if (r.exitCode === 0) return { result: r.stdout.trim() };
      return { deny: r.stderr.trim() || "segmem recall failed" };
    } catch (err) {
      $.ui.log("segmem recall failed: " + String(err));
      return next(e);
    }
  });
};
