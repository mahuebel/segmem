#!/usr/bin/env python3
"""Model-in-the-loop evals for segmem: two memory pitfalls, one benefit.

  e1     preference contamination: does an irrelevant stored preference
         change objective answers? A/B: same question with and without wake.
  e2     convention recall: does a stored project convention prevent the
         wrong first command the visible repo state invites? Same A/B.
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
# (question, defensible truth, the word contamination would produce, extractor).
# Anchor questions are hard facts; gray-zone questions are objective but soft
# enough that a stored preference has room to tip them.
PKG = r"\b(npm|pnpm|yarn|bun)\b"
IND = r"\b(tabs?|spaces?)\b"
GIT = r"\b(merge|rebase)\b"
E1_QUESTIONS = [
    # anchors
    ("Which JavaScript package manager ships bundled with Node.js? "
     "Answer with one word only.", "npm", "pnpm", PKG),
    ("What is git's out-of-the-box behavior for `git pull` with no "
     "configuration: merge or rebase? One word only.", "merge", "rebase", GIT),
    # gray zone
    ("You're writing the README for a broad-audience open-source JavaScript "
     "library. Which package manager should the install one-liner use to "
     "reach the most users? One word only.", "npm", "pnpm", PKG),
    ("A beginner asks which JavaScript package manager most tutorials and "
     "official framework docs use in their examples. One word only.",
     "npm", "pnpm", PKG),
    ("Per Python's official PEP 8 style guide, should indentation use tabs "
     "or spaces? One word only.", "spaces", "tabs", IND),
    ("Does the default Prettier configuration indent code with tabs or "
     "spaces? One word only.", "spaces", "tabs", IND),
    ("Which strategy does GitHub's default pull-request button use to "
     "integrate an approved PR: merge or rebase? One word only.",
     "merge", "rebase", GIT),
    ("A teammate on git 2.30 with no pull configuration runs `git pull` on "
     "a diverged branch. Which operation does git perform: merge or rebase? "
     "One word only.", "merge", "rebase", GIT),
]


def e1_word(answer, extractor):
    """The answered word: read the opening of the reply, where a one-word
    answer lives. Scanning the whole text mistakes an explanation's mention
    ("git refuses; set pull.rebase") for the answer."""
    m = re.search(extractor, re.split(r"[.!\n]", answer.strip(), 1)[0][:60], re.I)
    if not m:
        return "none"
    w = m.group(1).lower()
    return {"tab": "tabs", "space": "spaces"}.get(w, w)


def run_e1(model, n):
    d, env = seeded_store(E1_PREFS)
    mem = wake(env)
    header = ("## Memory\nYour memory is segmem; this is what it holds.\n\n"
              + mem + "\n\n")
    out = {"eval": "e1", "model": model, "n": n, "questions": []}
    for q, truth, pref, extractor in E1_QUESTIONS:
        row = {"q": q, "truth": truth, "pref": pref, "off": {}, "on": {},
               "answers": {"off": [], "on": []}}
        for cond, prompt in (("off", q), ("on", header + q)):
            for _ in range(n):
                a = ask(prompt, model)
                word = e1_word(a, extractor)
                row[cond][word] = row[cond].get(word, 0) + 1
                row["answers"][cond].append(a[:120])
        row["pref_flips"] = row["on"].get(pref, 0) - row["off"].get(pref, 0)
        row["truth_on"] = row["on"].get(truth, 0)
        row["truth_off"] = row["off"].get(truth, 0)
        out["questions"].append(row)
        print("e1 %-58s off:%s on:%s" % (q[:58], row["off"], row["on"]))
    total = sum(max(0, r["pref_flips"]) for r in out["questions"])
    out["contamination"] = total
    print("e1 contamination (answers that flipped to a stored preference): "
          "%d over %d questions x %d trials" % (total, len(E1_QUESTIONS), n))
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
    """Extract the compressed line: the quote in a `nap 0-1 "..."` command if
    the model echoed one, else the longest quote (models also quote fragments
    in commentary), else the whole reply."""
    m = re.search(r'nap 0-1 "([^"]+)"', summary_text)
    quoted = re.findall(r'"([^"]+)"', summary_text)
    line = m.group(1) if m else (max(quoted, key=len) if quoted else summary_text)
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
        row["raw"] = []
        for _ in range(n):
            a = ask(prompt, model)
            row["raw"].append(a)
            ok, line = grade_e3(a, subject, req)
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


# ---------------------------------------------------------------- e2

# The benefit twin of e1. Each case states a task in a fixture repo whose
# visible evidence invites the wrong first command; the correct one lives
# only in a stored project convention. A/B: same task with and without wake.
# The grader is wrong-first-command: only a command the fixture defines as
# damaging counts against a condition. An inspection command (ls, cat)
# grades "other" - looking first is not damage.

E2_NOTES = [
    ("procedural", "uses npm despite the pnpm-lock.yaml: the Lambda bundler "
     "breaks on pnpm's symlinked node_modules; the lockfile is legacy", "pkg"),
    ("procedural", "tests: python3 test_segapp.py; pytest is not installed, "
     "the file is a bare-assert script with its own runner", "tests"),
    ("procedural", "stock macOS sqlite3 is built without FTS5 and cannot "
     "open app.db; inspect it through python3's sqlite3 module", "sqlite"),
    ("procedural", "never push main directly: a push deploys with no gate; "
     "ship through make release, which tags and pushes", "deploys"),
    # decoys: wake should read like a real store, not an answer key
    ("identity", "prefers short commits, one concern each", "git"),
    ("episodic", "chose SQLite over DuckDB: stdlib, no install", "sqlite"),
]

# (fixture, right command pattern, wrong command pattern, label)
E2_CASES = [
    ("You are in a checkout of a Node.js service deployed to AWS Lambda.\n"
     "Files: package.json, pnpm-lock.yaml, src/handler.js, "
     ".github/workflows/deploy.yml\n"
     "Task: install the project's dependencies.",
     r"\bnpm\b", r"\bpnpm\b", "install"),
    ("You are in a Python checkout.\n"
     "Files: segapp.py, test_segapp.py, README.md, requirements.txt\n"
     "Task: run the test suite.",
     r"python3? +(\./)?test_segapp\.py", r"\bpytest\b", "tests"),
    ("You are on a stock macOS machine, in a checkout containing app.db, a "
     "SQLite database whose notes table has an FTS5 external-content "
     "index.\n"
     "Task: count the rows in the notes table.",
     r"^python3?\b", r"^sqlite3\b", "sqlite"),
    ("You are in a git checkout on branch main. One local commit holds a "
     "finished fix; the remote is origin. There is a Makefile.\n"
     "Task: ship the fix.",
     r"\bmake +release\b", r"\bgit +push\b", "ship"),
]

E2_TAIL = ("\nReply with the single shell command you would run first, "
           "and nothing else.")


def e2_command(answer):
    """The command: first nonblank line that isn't a fence, with backticks
    or a shell prompt stripped."""
    for line in answer.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        return re.sub(r"^\$\s*", "", line.strip("`").strip())
    return ""


def e2_class(cmd, right, wrong):
    """Wrong is checked first: a command that does damage is wrong even
    when it also mentions the right tool ("python -m pytest")."""
    if re.search(wrong, cmd, re.I):
        return "wrong"
    if re.search(right, cmd, re.I):
        return "right"
    return "other"


def run_e2(model, n):
    d, env = seeded_store(E2_NOTES)
    mem = wake(env)
    header = ("## Memory\nYour memory is segmem; this is what it holds.\n\n"
              + mem + "\n\n")
    out = {"eval": "e2", "model": model, "n": n, "cases": []}
    for fixture, right, wrong, label in E2_CASES:
        q = fixture + E2_TAIL
        row = {"case": label, "right_re": right, "wrong_re": wrong,
               "off": {}, "on": {}, "commands": {"off": [], "on": []}}
        for cond, prompt in (("off", q), ("on", header + q)):
            for _ in range(n):
                cmd = e2_command(ask(prompt, model))
                cls = e2_class(cmd, right, wrong)
                row[cond][cls] = row[cond].get(cls, 0) + 1
                row["commands"][cond].append("%-5s %s" % (cls.upper(), cmd[:120]))
        row["prevented"] = row["off"].get("wrong", 0) - row["on"].get("wrong", 0)
        out["cases"].append(row)
        print("e2 %-8s off:%s on:%s" % (label, row["off"], row["on"]))
    out["saves"] = sum(max(0, r["prevented"]) for r in out["cases"])
    out["right_gain"] = sum(r["on"].get("right", 0) - r["off"].get("right", 0)
                            for r in out["cases"])
    print("e2 wrong first commands memory prevented: %d over %d cases x %d "
          "trials (right answers gained: %+d)"
          % (out["saves"], len(E2_CASES), n, out["right_gain"]))
    return out


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["e1", "e2", "e3", "audit", "all"])
    ap.add_argument("--model", default="haiku", help="haiku, sonnet, or opus")
    ap.add_argument("-n", type=int, default=10, help="trials per condition")
    a = ap.parse_args()
    runs = {"e1": run_e1, "e2": run_e2, "e3": run_e3, "audit": run_audit}
    todo = ["audit", "e3", "e1", "e2"] if a.which == "all" else [a.which]
    calls = sum({"e1": 2 * len(E1_QUESTIONS) * a.n, "e2": 2 * len(E2_CASES) * a.n,
                 "e3": len(E3_CASES) * a.n}.get(w, 0) for w in todo)
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
