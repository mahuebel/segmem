// segmem as a function hook: wake and recall as typed results, no stdout
// parsing. Loads only when CLAUDE_CODE_ENABLE_FUNCTION_HOOKS is on (or the
// engine's flag is). The command hooks in hooks.json keep running either
// way; every path here calls the same command with `--once`, and the claims
// table lets exactly one of the two speak.
//
// Wake runs in prompt.context, not session.start: prompt.context fires first.
//
// prompt.context is dispatched more than once and the dispatches OVERLAP;
// the engine keeps whichever answer settles first. So the once-guard caches
// the promise, not the value: a guard that sets its sentinel before the
// await lets the second dispatch through with nothing, and that empty
// answer, being the fast one, is the one the engine keeps.
//
// Ordering. The UserPromptSubmit command hook runs *inside* next(e), so a
// hook that waited for next(e) before claiming could never win. Each hook
// below claims first and holds its output before it calls next, so a claim
// it wins is a claim it can deliver. On wake the race is lost anyway: the
// SessionStart command hook and this module start at the same moment and
// the command hook's process reaches the insert first, every time measured.
// That is fine, because both paths print the same wake. Anything only this
// module can produce must therefore not be gated on winning: see draftNap.
import type { EngineInterface, Register } from "claude-code";

const TIMEOUT = 10_000;

/** What one session start gathers: the memory, and a draft nap if one is due. */
type Gathered = { wake: string; draft: string };

/**
 * Wake, the pressure count, and the nap draft, once per module life.
 *
 * Wake is claimed with `--once`, so it prints only if this path owns the
 * session. The other two are not behind that claim: the two paths race on
 * it and the command hook wins, so anything gated on winning would never
 * ship. Neither doubles anything a command hook prints.
 *
 * The plugin never runs `nap`. It drafts a line and offers it, because a
 * draft that flattens a doubt into a cause is worse than no draft, and only
 * the model can tell the difference.
 */
async function gather($: EngineInterface): Promise<Gathered> {
  const root = $.plugin.root + "/segmem";
  const cwd = await $.session.cwd();
  let wake = "";
  try {
    const r = await $.process.run(
      [root, "wake", "--once", "--session=" + (await $.session.id()),
       "--served=function"],
      { cwd, timeoutMs: TIMEOUT },
    );
    if (r.exitCode === 0) wake = r.stdout.trim();
    else $.ui.log("segmem wake failed: " + r.stderr.trim());
  } catch (err) {
    $.ui.log("segmem wake failed: " + String(err));
  }

  // What the Stop hook will interrupt about, as a line the user can see
  // before it does. The Stop block stays the model's trigger; this is a
  // notice.
  try {
    const r = await $.process.run([root, "stale", "--count"], { cwd, timeoutMs: TIMEOUT });
    const n = r.exitCode === 0 ? Number(r.stdout.trim()) : 0;
    $.ui.status(n > 0 ? "segmem: " + n + " under pressure" : undefined);
  } catch (err) {
    $.ui.log("segmem stale failed: " + String(err));
  }

  // A contradiction is the whole point of the altitudes, and it is easy to
  // miss inside a long wake. Toast the ids so the user sees one without
  // reading it. `wake --conflicts` answers as data and takes no claim: the
  // command hook owns wake's text, and this is not serving that text.
  try {
    const r = await $.process.run([root, "wake", "--conflicts"], { cwd, timeoutMs: TIMEOUT });
    const ids = r.exitCode === 0 ? r.stdout.trim().split("\n").filter(Boolean) : [];
    if (ids.length) $.ui.toast("segmem: " + ids.join("; "), { timeoutMs: 8000 });
  } catch (err) {
    $.ui.log("segmem wake --conflicts failed: " + String(err));
  }

  let draft = "";
  try {
    const r = await $.process.run([root, "next-nap", "--json"], { cwd, timeoutMs: TIMEOUT });
    const nap = r.exitCode === 0 ? JSON.parse(r.stdout || "{}") : {};
    if (typeof nap.range === "string" && typeof nap.prompt === "string") {
      const line = (await $.model.complete({
        model: await $.session.model(),
        prompt: nap.prompt,
        system: "Answer with the compressed line alone: no quotes, no command, "
          + "no preamble, no explanation.",
      })).trim();
      if (line) {
        draft = "A draft for the compression segmem asked for. Run `segmem nap "
          + nap.range + ' "' + line + '"` if it keeps doubts as doubts and '
          + "invents nothing; otherwise write your own line and run that instead.";
      }
    }
  } catch (err) {
    $.ui.log("segmem nap draft failed: " + String(err));
  }
  return { wake, draft };
}

export const register: Register = (on) => {
  let once: Promise<Gathered> | undefined;

  on("prompt.context", async ($, e, next) => {
    let g: Gathered;
    try {
      once ??= gather($);
      g = await once;
    } catch (err) {
      $.ui.log("segmem gather failed: " + String(err));
      return next(e);
    }
    const blocks = [...e.blocks];
    if (g.wake) blocks.push({ name: "segmem", text: g.wake });
    if (g.draft) blocks.push({ name: "segmem-nap-draft", text: g.draft });
    if (blocks.length === e.blocks.length) return next(e);
    return next({ ...e, blocks });
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
