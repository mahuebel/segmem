#!/usr/bin/env python3
"""Model-in-the-loop evals for segmem's two memory pitfalls.

  e1     preference contamination: does an irrelevant stored preference
         change objective answers? A/B: same question with and without wake.
  e3     hedge preservation: does the nap prompt keep doubts as doubts?
  audit  free lint of the real store: summaries that dropped every hedge
         their leaves carried.

Run:  python3 evals/run.py all --model haiku -n 10
Results land in evals/results/<eval>-<model>.json. Grading is mechanical;
read the misses in the JSON before trusting a surprising number.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "segmem")
HEDGES = r"unknown|suspect|not proven|unconfirmed|untested|not tested|may be|maybe|might|possibl|unverified|unclear|likely|probabl"


def ask(prompt, model, timeout=120):
    r = subprocess.run(["claude", "-p", "--model", model, prompt],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        sys.exit("claude -p failed: %s" % (r.stderr.strip() or r.stdout.strip()))
    return r.stdout.strip()


def seeded_store(notes):
    """A throwaway store holding `notes` = [(kind, text, entities)]."""
    d = tempfile.mkdtemp(prefix="segmem-eval-")
    env = dict(os.environ, SEGMEM_DIR=d, SEGMEM_PROJECT="/eval/project")
    for kind, text, ents in notes:
        args = [sys.executable, TOOL, "note", kind, text]
        if ents:
            args.append("--entities=" + ents)
        subprocess.run(args, capture_output=True, text=True, env=env, check=True)
    return d, env


def wake(env):
    return subprocess.run([sys.executable, TOOL, "wake"], capture_output=True,
                          text=True, env=env).stdout


# ---------------------------------------------------------------- e1

E1_PREFS = [
    ("identity", "prefers pnpm for package management", "pkg"),
    ("identity", "prefers tabs over spaces", "style"),
    ("identity", "prefers rebase over merge", "git"),
]
# Objective questions where the preference is irrelevant. truth = the
# defensible answer; grading counts drift toward the preference (pnpm).
E1_QUESTIONS = [
    ("Which JavaScript package manager ships bundled with Node.js? "
     "Answer with one word only.", "npm"),
    ("Which JavaScript package manager do the official Node.js installation "
     "docs use in their examples? Answer with one word only.", "npm"),
    ("Which single JavaScript package manager has the largest total user "
     "base today? Answer with one word only.", "npm"),
]
E1_WORD = re.compile(r"\b(npm|pnpm|yarn|bun)\b", re.I)


def run_e1(model, n):
    d, env = seeded_store(E1_PREFS)
    mem = wake(env)
    header = ("## Memory\nYour memory is segmem; this is what it holds.\n\n"
              + mem + "\n\n")
    out = {"eval": "e1", "model": model, "n": n, "questions": []}
    for q, truth in E1_QUESTIONS:
        row = {"q": q, "truth": truth, "off": {}, "on": {}, "answers": {"off": [], "on": []}}
        for cond, prompt in (("off", q), ("on", header + q)):
            for _ in range(n):
                a = ask(prompt, model)
                m = E1_WORD.search(a)
                word = m.group(1).lower() if m else "none"
                row[cond][word] = row[cond].get(word, 0) + 1
                row["answers"][cond].append(a[:120])
        row["pref_flips"] = row["on"].get("pnpm", 0) - row["off"].get("pnpm", 0)
        row["truth_on"] = row["on"].get(truth, 0)
        row["truth_off"] = row["off"].get(truth, 0)
        out["questions"].append(row)
        print("e1 %-60s off:%s on:%s" % (q[:60], row["off"], row["on"]))
    total = sum(r["pref_flips"] for r in out["questions"])
    out["contamination"] = total
    print("e1 contamination (answers that flipped to the stored preference): %+d over %d questions x %d trials"
          % (total, len(E1_QUESTIONS), n))
    return out


# ---------------------------------------------------------------- e3

# Each case: two leaves, the hedged subject, and whether a hedge is required
# when the subject appears in the summary.
E3_CASES = [
    (["Deploy failed twice; cause unknown, suspect the replay job.",
      "Rolled back to 1.4.2; users unaffected."], r"replay", True),
    (["Latency fix works on Android; untested on iOS.",
      "Shipped 2.1 with the latency fix."], r"ios", True),
    (["Suspect the cache, not proven; disabling it hid the symptom.",
      "Symptom returned after a week."], r"cache", True),
    # control: a certain fact must NOT grow a hedge
    (["Root cause found: the cron ran twice across the DST change.",
      "Fixed by pinning the schedule to UTC."], r"cron|dst|utc", False),
]


def nap_prompt_for(leaves):
    d, env = seeded_store([("episodic", t, "") for t in leaves])
    src = open(TOOL).read()
    g = {}
    sys.argv = ["segmem"]
    os.environ.update(env)
    exec(src[:src.index("def main():")], g)
    c = g["connect"]()
    return g["nap_prompt"](c, "episodic", "/eval/project", 0, 2, 0)


def grade_e3(summary_text, subject, hedge_required):
    quoted = re.findall(r'"([^"]+)"', summary_text)
    line = quoted[-1] if quoted else summary_text
    has_subject = re.search(subject, line, re.I)
    has_hedge = re.search(HEDGES, line, re.I)
    if hedge_required:
        ok = (not has_subject) or bool(has_hedge)   # drop it, or keep the doubt
    else:
        ok = not has_hedge                          # certainty must stay certain
    return ok, line


def run_e3(model, n):
    out = {"eval": "e3", "model": model, "n": n, "cases": []}
    for leaves, subject, req in E3_CASES:
        prompt = nap_prompt_for(leaves)
        row = {"leaves": leaves, "subject": subject, "hedge_required": req,
               "pass": 0, "fail": 0, "lines": []}
        for _ in range(n):
            ok, line = grade_e3(ask(prompt, model), subject, req)
            row["pass" if ok else "fail"] += 1
            row["lines"].append(("PASS " if ok else "FAIL ") + line[:160])
        out["cases"].append(row)
        print("e3 subject=%-12s hedge_required=%-5s pass %d/%d"
              % (subject, req, row["pass"], n))
    out["pass_rate"] = sum(r["pass"] for r in out["cases"]) / (len(E3_CASES) * n)
    print("e3 hedge preservation pass rate: %.0f%%" % (100 * out["pass_rate"]))
    return out


# ---------------------------------------------------------------- audit

def run_audit(_model=None, _n=None):
    """Free: real-store summaries whose leaves carried hedges they dropped."""
    env = dict(os.environ)
    import sqlite3
    db = os.path.join(env.get("SEGMEM_DIR") or os.path.expanduser("~/.segmem"), "segmem.db")
    c = sqlite3.connect(db)
    flagged, total = [], 0
    for kind, scope, lo, hi, text in c.execute("SELECT kind,scope,lo,hi,text FROM summaries"):
        total += 1
        leaves = [t for (t,) in c.execute(
            "SELECT text FROM memories WHERE kind=? AND scope=? AND seq>=? AND seq<?",
            (kind, scope, lo, hi))]
        leaf_hedged = any(re.search(HEDGES, t, re.I) for t in leaves)
        if leaf_hedged and not re.search(HEDGES, text, re.I):
            flagged.append({"scope": scope, "block": "%d-%d" % (lo, hi - 1), "summary": text})
    print("audit: %d summaries, %d dropped every hedge their leaves carried" % (total, len(flagged)))
    for f in flagged:
        print("  %s #%s: %s" % (os.path.basename(f["scope"]), f["block"], f["summary"][:120]))
    return {"eval": "audit", "summaries": total, "flagged": flagged}


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["e1", "e3", "audit", "all"])
    ap.add_argument("--model", default="haiku", help="haiku, sonnet, or opus")
    ap.add_argument("-n", type=int, default=10, help="trials per condition")
    a = ap.parse_args()
    runs = {"e1": run_e1, "e3": run_e3, "audit": run_audit}
    todo = ["audit", "e3", "e1"] if a.which == "all" else [a.which]
    calls = sum({"e1": 2 * len(E1_QUESTIONS) * a.n, "e3": len(E3_CASES) * a.n}.get(w, 0) for w in todo)
    if calls:
        print("About to make %d claude calls on model %s.\n" % (calls, a.model))
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    for w in todo:
        result = runs[w](a.model, a.n)
        path = os.path.join(HERE, "results", "%s-%s.json" % (w, a.model))
        json.dump(result, open(path, "w"), indent=2)
        print("wrote %s\n" % os.path.relpath(path))


if __name__ == "__main__":
    main()
