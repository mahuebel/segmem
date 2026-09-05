// segmem as a function hook: wake as a typed context block, no stdout parsing.
// Loads only when CLAUDE_CODE_ENABLE_FUNCTION_HOOKS is on (or the engine's
// flag is). The command hooks in hooks.json keep running either way; both
// call `segmem wake --once`, and the claims table lets exactly one speak.
// Wake runs here, not at session.start: prompt.context fires first.
import type { Register } from "claude-code";

export const register: Register = (on) => {
  let wake: string | undefined;

  on("prompt.context", async ($, e, next) => {
    if (wake === undefined) {
      const r = await $.process.run(
        [$.plugin.root + "/segmem", "wake", "--once",
         "--session=" + (await $.session.id()), "--served=function"],
        { cwd: await $.session.cwd(), timeoutMs: 10_000 },
      );
      wake = r.exitCode === 0 ? r.stdout.trim() : "";
      if (r.exitCode !== 0) $.ui.log("segmem wake failed: " + r.stderr.trim());
    }
    if (!wake) return next(e);
    return next({ ...e, blocks: [...e.blocks, { name: "segmem", text: wake }] });
  });
};
