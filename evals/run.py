#!/usr/bin/env python3
"""Model-in-the-loop evals for segmem: two memory pitfalls, one benefit.

  e1     preference contamination: does an irrelevant stored preference
         change objective answers? A/B: same question with and without wake.
  e2     convention recall: does a stored project convention prevent the
         wrong first command the visible repo state invites? Same A/B.
  e3     hedge preservation: does the nap prompt keep doubts as doubts?
  audit  free lint of the real store: summaries against their leaves, one
         flag per nap-gate check (hedge dropped, invented token, silent
         leaf), counted so a check earns its way to a refusal.

Run:  python3 evals/run.py all --model haiku -n 10
Results land in evals/results/<eval>-<model>.json. Grading is mechanical;
read the misses in the JSON before trusting a surprising number.
"""
import argparse
import importlib.machinery
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "segmem")
HEDGES = r"unknown|suspect|not proven|unconfirmed|untested|not tested|may be|maybe|might|possibl|unverified|unclear|likely|probabl"


# Child claude sessions run the user's hooks, the segmem plugin included:
# point them at a throwaway store so the real one neither leaks into the
# "off" condition nor collects touches from eval prompts.
ASK_ENV = dict(os.environ, SEGMEM_DIR=tempfile.mkdtemp(prefix="segmem-eval-ask-"))


def ask(prompt, model, timeout=120):
    r = subprocess.run(["claude", "-p", "--model", model, prompt],
                       capture_output=True, text=True, timeout=timeout, env=ASK_ENV)
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

def _segmem():
    """The tool as a module, for identifiers() and the store's own rules."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "segmem_mod", TOOL, loader=importlib.machinery.SourceFileLoader("segmem_mod", TOOL))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def audit_flags(summary, leaves, leaf_dates, identifiers):
    """The nap gate's content checks, as flags on one stored summary against
    its leaves (docs/design-nap-gate.md, S1). Counted here before any of
    them may refuse a nap.

    invented:  a digit run or identifier in the summary that no leaf holds.
               Digit runs compare as ints so 9/2, 09-02, and 16/8 all resolve
               to what the leaves carry; a leaf's own date counts as source.
    hedge:     leaves carried a doubt marker, the summary carries none.
    silent:    leaves whose identifiers and numbers the summary shares none
               of; dropping a leaf whole is allowed, this counts how often."""
    def nums(t):
        # 1,681 is one number; 9/2 and 09-02 are two that compare as ints
        return {int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", t)}
    def idents(t):
        # identifiers() also returns a sentence-ending word ("tags only." is
        # a path to the regex); here only code-shaped tokens count
        return {i.lower() for i in identifiers(t) if re.search(r"[_/.\-#]", i.strip(".,;:"))}
    src = " ".join(leaves) + " " + " ".join(leaf_dates)
    src_nums, src_idents, src_low = nums(src), idents(src), src.lower()
    def novel(i):
        # a summary joins what leaves held apart (s1-s3, e1/e3): invented
        # only if no part of it is in the sources
        parts = [p for p in re.split(r"[-/]", i) if len(p) > 1] or [i]
        return all(p not in src_low for p in parts)
    invented = sorted({str(n) for n in nums(summary) - src_nums}
                      | {i for i in idents(summary) if novel(i)})
    hedge = any(re.search(HEDGES, t, re.I) for t in leaves) and not re.search(HEDGES, summary, re.I)
    silent = []
    for i, leaf in enumerate(leaves):
        keys = idents(leaf) | {str(n) for n in nums(leaf) if n > 31}
        if keys and not (keys & (idents(summary) | {str(n) for n in nums(summary)})):
            silent.append(i)
    return {"invented": invented, "hedge": hedge, "silent": silent}


def run_audit(_model=None, _n=None):
    """Free: real-store summaries against their leaves, one flag per check.
    The hedge flag is the original audit; invented and silent are the nap
    gate's other checks, counted so their firing rate decides whether they
    ever become refusals."""
    env = dict(os.environ)
    import sqlite3
    db = os.path.join(env.get("SEGMEM_DIR") or os.path.expanduser("~/.segmem"), "segmem.db")
    c = sqlite3.connect(db)
    identifiers = _segmem().identifiers
    rows, total = [], 0
    for kind, scope, lo, hi, text in c.execute("SELECT kind,scope,lo,hi,text FROM summaries"):
        total += 1
        leaves = c.execute(
            "SELECT text, ts FROM memories WHERE kind=? AND scope=? AND seq>=? AND seq<? ORDER BY seq",
            (kind, scope, lo, hi)).fetchall()
        f = audit_flags(text, [t for t, _ in leaves], [ts[:10] for _, ts in leaves], identifiers)
        f.update({"scope": scope, "block": "%d-%d" % (lo, hi - 1), "summary": text,
                  "leaves": len(leaves)})
        rows.append(f)
    hedged = [r for r in rows if r["hedge"]]
    invented = [r for r in rows if r["invented"]]
    silent = [r for r in rows if r["silent"]]
    print("audit: %d summaries" % total)
    print("  hedge dropped: %d" % len(hedged))
    for r in hedged:
        print("    %s #%s: %s" % (os.path.basename(r["scope"]), r["block"], r["summary"][:100]))
    print("  invented tokens: %d summaries" % len(invented))
    for r in invented:
        print("    %s #%s: %s" % (os.path.basename(r["scope"]), r["block"], ", ".join(r["invented"])))
    print("  silent leaves: %d summaries, %d leaves of %d"
          % (len(silent), sum(len(r["silent"]) for r in silent), sum(r["leaves"] for r in rows)))
    return {"eval": "audit", "summaries": total, "flagged": hedged,
            "invented": invented, "silent": silent}


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

# which raw chunk holds each case's answer
E2_TRUE = {"install": "pkg", "tests": "tests", "sqlite": "sqlite", "ship": "deploys"}

E2_TAIL = ("\nReply with the single shell command you would run first, "
           "and nothing else.")

# The control arm, after MemDelta (arXiv 2606.29914): the same facts as
# verbatim past-session text, found by a word-overlap search over transcript
# chunks, written by nobody. Wake costs an LLM-written note per fact; this
# costs nothing to write. If it prevents as many wrong commands as wake, the
# curation is not what earns the keep. The chunks read like real sessions:
# the fact is in there, beside the noise it was learned in, and two decoys
# from another repo carry the words a search would also match.
E2_RAW = [
    ("pkg", """[session 2026-08-02, lambda-svc] Task: install deps and run the bundler
$ pnpm install
Lockfile is up to date, resolution step is skipped
Done in 4.1s
$ npm run bundle
> esbuild src/handler.js --bundle --platform=node --outfile=dist/handler.js
X [ERROR] Could not resolve "@aws-sdk/client-s3"
  node_modules/.pnpm/... is a symlink; the Lambda bundler config follows no symlinks
$ rm -rf node_modules && npm install
added 212 packages in 9s
$ npm run bundle
  dist/handler.js  1.2mb
> ok that works. the pnpm-lock.yaml is from before the Lambda move; leaving it for now"""),
    ("tests", """[session 2026-08-05, segapp] Task: run the tests after the parser change
$ pytest
zsh: command not found: pytest
$ python3 -m pytest
/usr/bin/python3: No module named pytest
$ head -5 test_segapp.py
'''Run: python3 test_segapp.py'''
import os, sys
$ python3 test_segapp.py
....
4 passed
> the file is a bare-assert script with its own runner, so that's the command"""),
    ("sqlite", """[session 2026-08-09, segapp] Task: check how many notes are in app.db
$ sqlite3 app.db "select count(*) from notes"
Error: no such module: fts5
$ sqlite3 --version
3.43.2 2023-10-10 (stock macOS build, no FTS5)
$ python3 -c "import sqlite3; c=sqlite3.connect('app.db'); print(c.execute('select count(*) from notes').fetchone())"
(412,)
> python's bundled sqlite has FTS5, the CLI on this Mac doesn't"""),
    ("deploys", """[session 2026-08-11, lambda-svc] Task: ship the retry fix
$ git push origin main
...
remote: deploy.yml triggered: production
> wait, that deployed straight to prod with no gate. Rolled back with the previous tag.
$ cat Makefile | grep -A3 release
release:
\tgit tag v$(shell date +%Y%m%d.%H%M)
\tgit push --tags
\t./scripts/gate.sh && git push origin main
> from now on: make release, never git push main"""),
]

# Decoys, three kinds. Same-repo sessions share the file names the task
# names and hold no answer; other-repo sessions used the wrong command and
# it was right there; the rest is the ordinary noise of a transcript store.
# Each is (label, date, repo, task, body). Dates spread so that a tie on
# word overlap breaks the way a real search breaks it: newest first.
E2_DECOYS = [
    # lambda-svc, no answer
    ("d-lam-1", "2026-07-20", "lambda-svc", "bump the aws sdk in package.json",
     "$ cat package.json | grep aws-sdk\n  \"@aws-sdk/client-s3\": \"^3.600.0\"\n"
     "$ sed -i '' 's/3.600.0/3.650.0/' package.json\n> bumped; the workflow in .github/workflows/deploy.yml runs the bundle on push"),
    ("d-lam-2", "2026-07-24", "lambda-svc", "add a lint step to deploy.yml",
     "$ cat .github/workflows/deploy.yml\nname: deploy\non: push\njobs: ...\n"
     "> added a lint job before bundle in .github/workflows/deploy.yml; src/handler.js has two unused imports"),
    ("d-lam-3", "2026-07-28", "lambda-svc", "raise the Lambda timeout",
     "$ grep -n timeout src/handler.js\n12:  timeout: 3000\n> the Node.js service times out on cold start; raised to 10000 in src/handler.js and the Lambda config"),
    ("d-lam-4", "2026-08-01", "lambda-svc", "why is the deployed bundle 4mb",
     "$ ls -la dist/\n  handler.js 4.1mb\n> the AWS Lambda bundle pulls the whole sdk; switched to per-client imports in src/handler.js"),
    ("d-lam-5", "2026-08-06", "lambda-svc", "write a README for the service",
     "$ ls\npackage.json pnpm-lock.yaml src .github Makefile\n> wrote README.md: a Node.js service deployed to AWS Lambda through .github/workflows/deploy.yml"),
    ("d-lam-6", "2026-08-14", "lambda-svc", "rotate the S3 credentials",
     "$ aws secretsmanager update-secret --secret-id lambda-svc/s3 ...\n> rotated; src/handler.js reads it at cold start, nothing to change in the checkout"),
    ("d-lam-7", "2026-08-19", "lambda-svc", "investigate the flaky deploy",
     "$ gh run list --workflow=deploy.yml | head\n  failure  deploy  main  2m\n  success  deploy  main  3m\n"
     "> the flaky step is the bundle on a cold runner; deploy.yml now caches node_modules"),
    ("d-lam-8", "2026-08-22", "lambda-svc", "check the project's dependencies for a CVE",
     "$ npm audit\nfound 0 vulnerabilities\n> clean; package.json has 14 dependencies, all current"),
    # segapp, no answer
    ("d-seg-1", "2026-07-22", "segapp", "add the export command",
     "$ grep -n 'def cmd_' segapp.py | tail -3\n> added cmd_export to segapp.py; README.md lists it; requirements.txt unchanged"),
    ("d-seg-2", "2026-07-26", "segapp", "why does the parser drop the last line",
     "$ python3 -c 'import segapp; print(segapp.parse(open(\"x\").read()))'\n> off by one in segapp.py parse(); added a case to test_segapp.py"),
    ("d-seg-3", "2026-07-30", "segapp", "pin the requirements",
     "$ cat requirements.txt\nrequests>=2\n$ pip freeze | grep -i requests\nrequests==2.32.3\n> pinned in requirements.txt; README.md says pip install -r requirements.txt"),
    ("d-seg-4", "2026-08-03", "segapp", "rebuild the notes index",
     "$ python3 -c \"import sqlite3; c=sqlite3.connect('app.db'); c.execute(\\\"insert into notes_fts(notes_fts) values('rebuild')\\\")\"\n"
     "> the FTS5 external-content index on the notes table is rebuilt; app.db went from 9mb to 7mb"),
    ("d-seg-5", "2026-08-07", "segapp", "what tables does app.db have",
     "$ python3 -c \"import sqlite3; print(sqlite3.connect('app.db').execute('select name from sqlite_master').fetchall())\"\n"
     "[('notes',), ('notes_fts',), ('tags',)]\n> three tables in the SQLite database; notes_fts is the FTS5 index over notes"),
    ("d-seg-6", "2026-08-13", "segapp", "write the README",
     "$ ls\napp.db segapp.py test_segapp.py README.md requirements.txt\n> README.md: a Python checkout, one file, SQLite database app.db beside it"),
    ("d-seg-7", "2026-08-17", "segapp", "count tags per note",
     "$ python3 -c \"import sqlite3; c=sqlite3.connect('app.db'); print(c.execute('select count(*) from tags').fetchone())\"\n(1290,)\n> 1290 rows in tags for 412 notes"),
    ("d-seg-8", "2026-08-21", "segapp", "the machine is a stock macOS install, set up python",
     "$ python3 --version\nPython 3.12.4\n$ pip3 install -r requirements.txt\n> stock macOS machine; the checkout runs on the system python3"),
    # other repos where the wrong command was right
    ("d-kerf-1", "2026-07-28", "kerf", "run the tests",
     "$ pytest -q\n.........\n9 passed in 0.8s\n> kerf uses pytest; conftest.py sets the fixtures"),
    ("d-kerf-2", "2026-08-08", "kerf", "run the test suite after the merge",
     "$ pytest\n== 41 passed in 3.1s ==\n> green; the Python checkout's suite runs under pytest from the repo root"),
    ("d-kweb-1", "2026-07-30", "kerf-web", "install and start the dev server",
     "$ pnpm install && pnpm dev\n  VITE ready in 412 ms\n> pnpm everywhere in kerf-web, the lockfile is pnpm's"),
    ("d-kweb-2", "2026-08-10", "kerf-web", "install the project's dependencies on the new machine",
     "$ pnpm install\nPackages: +812\nDone in 11s\n> pnpm-lock.yaml respected; package.json has the packageManager field"),
    ("d-linux-1", "2026-08-04", "ops-box", "count rows in the audit table",
     "$ sqlite3 audit.db 'select count(*) from events'\n88213\n> the Linux sqlite3 CLI has FTS5; the FTS5 index on events is fine"),
    ("d-linux-2", "2026-08-16", "ops-box", "inspect the SQLite database",
     "$ sqlite3 audit.db .tables\nevents events_fts\n> sqlite3 CLI works here, the notes and events tables both indexed"),
    ("d-api-1", "2026-08-01", "billing-api", "ship the fix",
     "$ git push origin main\n> pushed to main; the remote origin runs CI, deploy is a manual step later"),
    ("d-api-2", "2026-08-12", "billing-api", "ship the finished fix from the local commit",
     "$ git log --oneline -1\n  fix: retry on 429\n$ git push origin main\n> branch main pushed; there is a Makefile but it only builds docs"),
    ("d-api-3", "2026-08-20", "billing-api", "release the hotfix",
     "$ make\n> no release target in the Makefile here; git push origin main and CI takes it"),
    # ordinary noise
    ("d-n-1", "2026-07-19", "notes", "draft the on-call handover",
     "> wrote the handover in README.md of the notes repo; nothing to install"),
    ("d-n-2", "2026-07-23", "dotfiles", "set up the new machine",
     "$ brew install node python3\n> stock macOS machine; installed node and python3, checkout of dotfiles applied"),
    ("d-n-3", "2026-08-15", "infra", "rotate the deploy key",
     "$ gh secret set DEPLOY_KEY < key\n> the deploy workflow in .github/workflows reads DEPLOY_KEY; origin unchanged"),
    ("d-n-4", "2026-08-18", "kerf", "finish the branch",
     "$ git checkout main && git merge feature\n$ git push origin main\n> merged the finished branch and pushed main; kerf has no deploy on push"),
]


def raw_corpus():
    """The true chunks and the decoys, as (label, date, text)."""
    out = [(label, re.search(r"\d{4}-\d\d-\d\d", text).group(0), text)
           for label, text in E2_RAW]
    for label, date, repo, task, body in E2_DECOYS:
        out.append((label, date, "[session %s, %s] Task: %s\n%s" % (date, repo, task, body)))
    return out


E2_RAW_K = 3


def raw_context(fixture):
    """The chunks a word-overlap search over past sessions returns for this
    task: scored by distinct fixture words of four letters or more that the
    chunk contains, ties newest first, top E2_RAW_K. Returns (text, labels)
    so the result can say whether the true chunk made the cut."""
    words = {w for w in re.findall(r"[a-z][a-z0-9_.-]{3,}", fixture.lower())}
    scored = []
    for label, date, chunk in raw_corpus():
        hit = sum(1 for w in words if w in chunk.lower())
        if hit:
            scored.append((-hit, date, label, chunk))
    scored.sort(key=lambda t: t[1], reverse=True)   # newest first...
    scored.sort(key=lambda t: t[0])                 # ...within a score
    top = scored[:E2_RAW_K]
    return "\n\n".join(c for _, _, _, c in top), [l for _, _, l, _ in top]


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
    out = {"eval": "e2", "model": model, "n": n, "cases": [],
           "cost": {"on": {"llm_writes": len(E2_NOTES), "bytes": len(mem)},
                    "raw": {"llm_writes": 0, "bytes": 0}}}
    for fixture, right, wrong, label in E2_CASES:
        q = fixture + E2_TAIL
        raw, picked = raw_context(fixture)
        out["cost"]["raw"]["bytes"] += len(raw) // len(E2_CASES)
        rawhead = ("## Past sessions\nA search over your past session transcripts "
                   "for this task found:\n\n" + raw + "\n\n")
        row = {"case": label, "right_re": right, "wrong_re": wrong,
               "off": {}, "on": {}, "raw": {}, "commands": {"off": [], "on": [], "raw": []},
               "retrieved": picked, "retrieval_hit": E2_TRUE[label] in picked}
        for cond, prompt in (("off", q), ("on", header + q), ("raw", rawhead + q)):
            for _ in range(n):
                cmd = e2_command(ask(prompt, model))
                cls = e2_class(cmd, right, wrong)
                row[cond][cls] = row[cond].get(cls, 0) + 1
                row["commands"][cond].append("%-5s %s" % (cls.upper(), cmd[:120]))
        for cond in ("on", "raw"):
            row["prevented_" + cond] = row["off"].get("wrong", 0) - row[cond].get("wrong", 0)
        row["prevented"] = row["prevented_on"]
        out["cases"].append(row)
        print("e2 %-8s off:%s on:%s raw:%s  retrieved:%s%s"
              % (label, row["off"], row["on"], row["raw"], ",".join(picked),
                 "" if row["retrieval_hit"] else " (true chunk missed)"))
    for cond in ("on", "raw"):
        out["saves" if cond == "on" else "saves_raw"] = sum(
            max(0, r["prevented_" + cond]) for r in out["cases"])
        out["right_gain" if cond == "on" else "right_gain_raw"] = sum(
            r[cond].get("right", 0) - r["off"].get("right", 0) for r in out["cases"])
    print("e2 wrong first commands prevented over %d cases x %d trials: "
          "wake %d (right gained %+d, %d LLM-written notes, %d bytes); "
          "raw transcripts %d (right gained %+d, 0 writes, ~%d bytes)"
          % (len(E2_CASES), n, out["saves"], out["right_gain"],
             out["cost"]["on"]["llm_writes"], out["cost"]["on"]["bytes"],
             out["saves_raw"], out["right_gain_raw"], out["cost"]["raw"]["bytes"]))
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
    calls = sum({"e1": 2 * len(E1_QUESTIONS) * a.n, "e2": 3 * len(E2_CASES) * a.n,
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
