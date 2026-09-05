"""Run: python3 test_segmem.py"""
import os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "segmem")


def run(*args, project="/p/alpha", check=True, stdin=None, org=None):
    env = dict(os.environ, SEGMEM_DIR=run.dir, SEGMEM_PROJECT=project)
    if org:
        env["SEGMEM_ORG_DIR"] = org
    r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True,
                       env=env, input=stdin)
    if check and r.returncode:
        raise AssertionError(r.stderr + r.stdout)
    return r.stdout + r.stderr


def org_repo(facts=(), candidates=()):
    """A real knowledge repo in a tmpdir: fact files, git init, one commit."""
    d = tempfile.mkdtemp()
    for sub in ("facts", "candidates"):
        os.makedirs(os.path.join(d, sub))
    for sub, items in (("facts", facts), ("candidates", candidates)):
        for slug, entities, text in items:
            open(os.path.join(d, sub, slug + ".md"), "w").write(
                "---\nkind: procedural\nscope: org\nentities: %s\n"
                "witnesses: alice 2026-08-01 kerf\n---\n%s\n" % (entities, text))
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], cwd=d, check=True, capture_output=True)
    return d


def org_commit(d, msg="more"):
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", msg], cwd=d, check=True, capture_output=True)


class Segmem(unittest.TestCase):
    def setUp(self):
        run.dir = tempfile.mkdtemp()

    def test_scope_defaults(self):
        self.assertIn("(global)", run("note", "identity", "prefers pnpm", "--entities=pkg"))
        self.assertIn("(alpha)", run("note", "procedural", "uses npm, legacy", "--entities=pkg"))
        self.assertIn("(global)", run("note", "people", "Alice reviews infra", "--entities=alice"))

    def test_override_shown_at_wake(self):
        run("note", "procedural", "prefers pnpm", "--scope=global", "--entities=pkg")
        run("note", "procedural", "uses npm for the Lambda runtime", "--entities=pkg")
        w = run("wake")
        self.assertIn("OVERRIDDEN", w)
        self.assertIn("Lambda", w)
        # Other project sees only the global fact, no override.
        w2 = run("wake", project="/p/beta")
        self.assertNotIn("OVERRIDDEN", w2)
        self.assertIn("prefers pnpm", w2)

    def test_supersedes_hides_old(self):
        run("note", "identity", "lives in Berlin")
        run("note", "identity", "lives in Lisbon", "--supersedes=1")
        w = run("wake")
        self.assertIn("Lisbon", w)
        self.assertNotIn("Berlin", w)
        r = run("recall", "Berlin")
        self.assertIn("[superseded]", r)

    def test_episodic_scoped_and_tree(self):
        for i in range(4):
            run("note", "episodic", "alpha event %d" % i)
        run("note", "episodic", "beta event", project="/p/beta")
        self.assertNotIn("beta event", run("wake"))
        self.assertNotIn("alpha event", run("wake", project="/p/beta"))
        # four memories fit the wake budget, so nothing comes due
        self.assertIn("Nothing to compress", run("nap", "0-1", "x", check=False))

    def test_nap_only_when_cover_needs_it(self):
        for i in range(18):
            run("note", "episodic", "e%d" % i)
        out = run("wake")
        # wake never blocks: a block with no summary prints raw, then asks
        self.assertIn("You are awake", out)
        self.assertIn("not compressed yet", out)
        self.assertIn("nap 0-1", out)             # smallest needed block first
        self.assertIn("Keep doubts as doubts", out)
        run("nap", "0-1", "e0 e1")
        out = run("wake")
        while "Compress episodic" in out:
            import re
            lo, hi = re.search(r"nap (\d+)-(\d+)", out).groups()
            run("nap", "%s-%s" % (lo, hi), "sum %s-%s" % (lo, hi))
            out = run("wake")
        self.assertIn("You are awake", out)
        self.assertNotIn("not compressed yet", out)
        self.assertNotIn("Compress", out)    # nothing premature after wake

    def test_wake_once_per_session(self):
        run("note", "procedural", "sky is blue")
        hook = '{"session_id": "s1", "source": "startup"}'
        # function-hook path claims first; the command hook then stays silent
        self.assertIn("sky is blue", run("wake", "--once", "--session=s1", "--served=function"))
        self.assertEqual("", run("wake", "--once", stdin=hook))
        # a compaction is a new source: it wakes again; so does another session
        self.assertIn("sky is blue", run("wake", "--once", stdin=hook.replace("startup", "compact")))
        self.assertIn("sky is blue", run("wake", "--once", stdin=hook.replace("s1", "s2")))
        # no session id known: --once is a no-op, plain wake is untouched
        self.assertIn("sky is blue", run("wake", "--once", stdin=""))
        self.assertIn("sky is blue", run("wake"))

    def test_hook_once_owner_serves_every_prompt(self):
        import json
        run("note", "procedural", "the deploy runs from make-release",
            "--entities=make-release")
        ask = json.dumps({"prompt": "how does `make-release` work?", "session_id": "s1"})
        # the function path claims s1 first, so it owns recall for s1
        self.assertIn("make-release",
                      run("hook", "--once", "--session=s1", "--served=function", stdin=ask))
        self.assertEqual("", run("hook", "--once", stdin=ask))
        # and it keeps owning it on later prompts, not just the first
        self.assertIn("make-release",
                      run("hook", "--once", "--session=s1", "--served=function", stdin=ask))
        self.assertEqual("", run("hook", "--once", stdin=ask))
        # another session is arbitrated on its own; here the command path wins
        s2 = ask.replace("s1", "s2")
        self.assertIn("make-release", run("hook", "--once", stdin=s2))
        self.assertEqual("", run("hook", "--once", "--session=s2", "--served=function", stdin=s2))
        # no --once, or no session id: never silent
        self.assertIn("make-release", run("hook", stdin=ask))
        self.assertIn("make-release", run("hook", "--once", stdin=ask.replace(
            '"session_id": "s1"', '"session_id": ""')))

    def test_people_listed_by_name(self):
        run("note", "people", "Alice owns deploys", "--entities=alice")
        w = run("wake")
        self.assertIn("People known: alice", w)
        self.assertIn("Alice owns deploys", run("recall", "alice"))

    def test_wake_prints_raw_when_summary_missing(self):
        # budget is 16 per project, so exceed it: the oldest block prints raw
        for i in range(20):
            run("note", "episodic", "e%d" % i)
        out = run("wake")
        self.assertIn("You are awake", out)
        self.assertIn("#0-1", out)
        self.assertIn("  #0 ", out)

    def test_wake_caps_procedural(self):
        for i in range(40):
            run("note", "procedural", "rule %d" % i)
        out = run("wake")
        self.assertIn("rule 39", out)
        self.assertNotIn("rule 0 ", out)
        self.assertIn("8 older procedural notes", out)
        self.assertIn("rule 0 ", run("wake", "--all"))

    def test_scope_name_is_not_a_tag(self):
        out = run("note", "procedural", "x", "--entities=alpha,widget")
        self.assertIn("alpha is the scope itself", out)
        self.assertIn("[widget]", run("recall", "x"))
        self.assertNotIn("[alpha", run("recall", "x"))

    def test_recall_hides_superseded_and_caps(self):
        run("note", "procedural", "old fact about zed")
        run("note", "procedural", "new fact about zed", "--supersedes=1")
        out = run("recall", "zed")
        self.assertNotIn("old fact", out)
        self.assertIn("old fact", run("recall", "zed", "--all"))
        for i in range(15):
            run("note", "episodic", "zed thing %d" % i)
        out = run("recall", "zed")
        self.assertEqual(out.count("zed"), 12 + 1)  # 12 rows plus the "more" line
        self.assertIn("more;", out)

    def test_promote_needs_three_agreeing_projects(self):
        run("note", "procedural", "uses pnpm", "--entities=pkg", project="/p/a")
        run("note", "procedural", "uses pnpm.", "--entities=pkg", project="/p/b")
        run("note", "procedural", "uses yarn", "--entities=pkg", project="/p/c")
        self.assertIn("Not promoted", run("promote", "1", project="/p/a"))
        run("note", "procedural", "Uses PNPM", "--entities=pkg", project="/p/d")
        self.assertIn("Promoted #1", run("promote", "1", project="/p/a"))
        self.assertIn("(global)", run("wake", project="/p/zzz"))

    def test_hook_recalls_identifiers(self):
        import json
        run("note", "people", "Alice owns deploys", "--entities=alice")
        run("note", "episodic", "chose Node over Bun for the Lambda runtime", "--entities=lambda")
        run("note", "episodic", "Claude said the Gateway was slow")
        run("note", "episodic", "beta secret", project="/p/beta")
        out = run("hook", stdin=json.dumps({"prompt": "ask Alice about the Lambda deploy"}))
        self.assertIn("<segmem-recall>", out)
        self.assertIn("Alice owns", out)
        self.assertIn("Lambda", out)
        self.assertNotIn("beta secret", out)
        # a capitalised word that is not a tag is prose, not an identifier
        self.assertEqual("", run("hook", stdin=json.dumps({"prompt": "Claude, is the Gateway slow?"})))
        self.assertEqual("", run("hook", stdin=json.dumps({"prompt": "fix it please"})))
        self.assertEqual("", run("hook", stdin="not json"))

    def test_mcp_roundtrip(self):
        import json
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "segmem_note",
                "arguments": {"kind": "people", "text": "Alice owns deploys", "entities": "alice"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "segmem_recall",
                "arguments": {"query": "alice"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "segmem_wake", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 6, "method": "nope"},
        ]
        out = run("mcp", stdin="\n".join(json.dumps(m) for m in msgs) + "\n")
        replies = {r["id"]: r for r in (json.loads(l) for l in out.splitlines() if l.strip())}
        self.assertEqual(replies[1]["result"]["serverInfo"]["name"], "segmem")
        self.assertEqual({t["name"] for t in replies[2]["result"]["tools"]},
                         {"segmem_wake", "segmem_note", "segmem_recall", "segmem_nap"})
        self.assertIn("#1 people", replies[3]["result"]["content"][0]["text"])
        self.assertIn("Alice owns", replies[4]["result"]["content"][0]["text"])
        self.assertIn("You are awake", replies[5]["result"]["content"][0]["text"])
        self.assertEqual(replies[6]["error"]["code"], -32601)
        self.assertEqual(len(replies), 6)  # the notification got no reply

    def test_wake_keeps_episodic_when_a_dossier_has_pressure(self):
        # Regression: the people-pressure loop used to rebind the project
        # variable, and the episodic section vanished for any store where a
        # known person had been touched.
        run("note", "people", "Alice owns deploys", "--entities=alice")
        run("note", "episodic", "chose SQLite over DuckDB", "--entities=sqlite")
        run("note", "episodic", "alice asked for a rollback plan", "--entities=alice")
        w = run("wake")
        self.assertIn("### Episodic (alpha)", w)
        self.assertIn("chose SQLite", w)

    def test_serve_is_live_and_read_only(self):
        import json, socket, time, urllib.request
        run("note", "procedural", "prefers pnpm", "--scope=global", "--entities=pkg")
        run("note", "procedural", "uses npm for the Lambda runtime", "--entities=pkg")
        run("note", "episodic", "chose SQLite over DuckDB", "--entities=sqlite")
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        env = dict(os.environ, SEGMEM_DIR=run.dir, SEGMEM_PROJECT="/p/alpha")
        srv = subprocess.Popen([sys.executable, TOOL, "serve", "--no-open", "--port=%d" % port],
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        base = "http://127.0.0.1:%d" % port
        get = lambda path: urllib.request.urlopen(base + path, timeout=5).read().decode()
        try:
            for _ in range(50):
                try:
                    get("/api/state"); break
                except OSError:
                    time.sleep(0.1)
            st = json.loads(get("/api/state"))
            self.assertIn("OVERRIDDEN", st["wake"])          # byte-identical wake
            self.assertEqual(st["seq"]["alpha"]["0"], 3)       # seq -> id map for episodic
            self.assertEqual(st["scope"], "/p/alpha")
            f = json.loads(get("/api/fact?id=1"))
            self.assertEqual([c["id"] for c in f["conflicts"]], [2])
            self.assertIn("OVERRIDDEN by #2", f["why"])
            self.assertEqual(f["threshold"], 12)
            hits = json.loads(get("/api/search?q=npm"))
            self.assertEqual([r["id"] for r in hits["rows"]], [2])
            self.assertEqual(hits["facets"]["entity"], {"pkg": 1})
            self.assertEqual(json.loads(get("/api/search?q=&kind=procedural"))["total"], 2)
            self.assertEqual(json.loads(get("/api/search?q=mem-op"))["total"], 0)  # no FTS crash
            spine = json.loads(get("/api/spine"))
            self.assertEqual([r[0] for r in spine], [1, 2, 3])
            self.assertEqual(spine[0][1:3], ["procedural", "global"])
            ov = json.loads(get("/api/overview"))
            self.assertEqual((ov["live"], ov["superseded"], ov["overrides"]), (3, 0, 1))
            self.assertEqual(ov["due"]["/p/alpha"]["pending"], 0)   # nothing due under budget
            self.assertGreater(ov["wake"]["/p/alpha"]["tokens"], 0)
            hk = json.loads(get("/api/hook?" + urllib.parse.urlencode(
                {"prompt": "why npm for the `Lambda` runtime, see #2 and Alice", "scope": "/p/alpha"})))
            self.assertEqual(hk["identifiers"], ["Lambda"])
            # "#2" is three bytes with the hash, so it falls under the min length; Alice is prose: no tag
            self.assertEqual([(d["word"], d["why"]) for d in hk["dropped"]],
                             [("#2", "too short"), ("Alice", "capitalized but not a tag: prose")])
            self.assertIn("#2 ", hk["output"])
            self.assertNotIn("#1 ", hk["output"])                          # project + global, ranked; Lambda hits #2 only
            tr = json.loads(get("/api/tree?scope=/p/alpha&budget=1&T=4"))
            self.assertEqual((tr["real_T"], tr["T"], len(tr["cover"])), (1, 4, 1))
            self.assertEqual(tr["pending"], [[0, 2], [2, 4], [0, 4]])       # smallest first
            en = json.loads(get("/api/entities"))
            self.assertEqual(en["nodes"][0]["id"], "pkg")
            self.assertEqual(en["nodes"][0]["n"], 2)
            run("note", "procedural", "uses npm; the Lambda runtime needs it", "--entities=pkg", "--supersedes=2")
            ch = json.loads(get("/api/chains"))["chains"]
            self.assertEqual([v["id"] for v in ch[0]["versions"]], [2, 4])
            self.assertIn(["+", "needs it"], [[op, t] for op, t in ch[0]["versions"][1]["diff"] if op == "+"])
            # Browsing presses on nothing: no recall touches were written.
            self.assertNotIn("recall", run("stale", "--min=1"))
            page = get("/")
            self.assertIn("<title>segmem</title>", page)
            self.assertNotIn("<script src=", page)
            # A commit from another connection reaches the event stream.
            es = urllib.request.urlopen(base + "/api/events", timeout=5)
            self.assertEqual(es.readline().strip(), b": open")
            run("note", "episodic", "second note")
            line = b""
            for _ in range(20):
                line = es.readline().strip()
                if line.startswith(b"data:"):
                    break
            self.assertTrue(line.startswith(b'data: {"v":'), line)
        finally:
            srv.terminate(); srv.wait(timeout=5)

    def test_html_is_self_contained(self):
        run("note", "identity", "prefers pnpm", "--entities=pkg")
        run("note", "procedural", "uses npm", "--entities=pkg")
        run("note", "episodic", "an event")
        out = os.path.join(run.dir, "v.html")
        self.assertIn(out, run("html", out, "--no-open"))
        page = open(out, encoding="utf-8").read()
        self.assertIn("prefers pnpm", page)
        self.assertIn("uses npm", page)
        self.assertNotIn("<script src=", page)      # no external libraries
        self.assertNotIn("https://", page.split("<script>")[0])  # no remote assets

    def test_tags_canonical_and_hinted(self):
        run("note", "procedural", "uses actions", "--entities=github-actions")
        out = run("note", "episodic", "ci broke", "--entities=GitHub-Actions,github_actions")
        self.assertIn("new tag: github_actions (similar: github-actions)", out)
        page = run("recall", "broke")
        self.assertIn("[github-actions,github_actions]", page)  # case-matched to the stored spelling

    def test_people_hint(self):
        out = run("note", "episodic", "Alice fixed the deploy", "--entities=Alice,PrayerPair,useGuard")
        self.assertIn("no people record for Alice", out)
        self.assertNotIn("PrayerPair;", out)
        self.assertNotIn("useGuard;", out)
        run("note", "people", "Alice owns deploys", "--entities=alice")
        out = run("note", "episodic", "Alice again", "--entities=Alice")
        self.assertNotIn("no people record", out)
        self.assertIn("People known: Alice", run("wake"))  # first stored spelling wins

    def test_wake_shows_dates(self):
        run("note", "episodic", "an event")
        out = run("wake")
        self.assertRegex(out, r"#0 \d{4}-\d{2}-\d{2} an event")

    def test_wake_stays_under_transport_limits(self):
        # 16 near-max episodic notes fit the budget with no summaries needed;
        # the whole wake must stay under the smallest harness cutoff (30k chars)
        filler = "x" * 200
        for i in range(16):
            run("note", "episodic", "event %d %s" % (i, filler))
        for i in range(4):
            run("note", "procedural", "rule %d %s" % (i, filler))
        out = run("wake")
        self.assertIn("You are awake", out)
        self.assertLess(len(out.encode()), 30000)

    def test_note_too_long_shows_trim_mark(self):
        out = run("note", "episodic", "word " * 60, check=False)
        self.assertIn("Too long", out)
        self.assertIn("▮", out)
        before = out.split("▮")[0].split("\n")[-1]
        self.assertLessEqual(len(before.encode()), 280)

    def test_pressure_builds_and_resets(self):
        run("note", "people", "Alice owns deploys", "--entities=alice")
        self.assertIn("No dossier under pressure", run("stale"))
        run("note", "episodic", "alice conceded the rollout in writing", "--entities=alice")
        run("note", "episodic", "alice rebranded the standup", "--entities=alice")
        out = run("stale")     # two notes at weight 3 meet the threshold of 6
        self.assertIn("alice", out)
        self.assertIn("2 notes", out)
        run("touch", "alice")
        self.assertIn("No dossier under pressure", run("stale"))
        # the next note about her starts the cycle again
        run("note", "episodic", "alice hired a deputy", "--entities=alice")
        self.assertIn("1 note", run("stale", "--min=3"))
        # an entity nobody has a dossier for builds no pressure
        self.assertIn("No people note", run("touch", "widget", check=False))

    def test_recall_and_prompt_mentions_press_lighter_than_notes(self):
        import json
        run("note", "people", "Alice owns deploys", "--entities=alice")
        run("recall", "alice")
        run("hook", stdin=json.dumps({"prompt": "ask Alice about deploys", "session_id": "s1"}))
        out = run("stale", "--min=1")
        self.assertIn("1 recall, 1 prompt", out)
        self.assertIn("pressure 3", out)

    def test_supersede_resets_pressure(self):
        run("note", "people", "Alice owns deploys", "--entities=alice")
        run("note", "episodic", "alice event a", "--entities=alice")
        run("note", "episodic", "alice event b", "--entities=alice")
        self.assertIn("alice", run("stale"))
        run("note", "people", "Alice owns deploys and the rollout", "--entities=alice",
            "--supersedes=1")
        self.assertIn("No dossier under pressure", run("stale"))

    def test_stop_hook_nags_once_per_session(self):
        import json
        run("note", "people", "Alice owns deploys", "--entities=alice")
        for i in range(2):
            run("note", "episodic", "alice event %d" % i, "--entities=alice")
        out = run("stale", "--hook", stdin=json.dumps({"session_id": "s1"}))
        self.assertIn('"decision": "block"', out)
        self.assertIn("alice", out)
        # once per entity and session
        self.assertEqual("", run("stale", "--hook", stdin=json.dumps({"session_id": "s1"})))
        # never blocks the stop its own block caused
        self.assertEqual("", run("stale", "--hook",
                                 stdin=json.dumps({"session_id": "s2", "stop_hook_active": True})))
        # a new session nags again; a review then quiets every session
        self.assertIn("block", run("stale", "--hook", stdin=json.dumps({"session_id": "s3"})))
        run("touch", "alice")
        self.assertEqual("", run("stale", "--hook", stdin=json.dumps({"session_id": "s4"})))

    def test_wake_flags_stale_dossier(self):
        run("note", "people", "Alice owns deploys", "--entities=alice")
        w = run("wake")
        self.assertNotIn("dossier from", w)
        run("note", "episodic", "alice event a", "--entities=alice")
        run("note", "episodic", "alice event b", "--entities=alice")
        w = run("wake")
        self.assertIn("dossier from", w)
        self.assertIn("touch alice", w)

    def test_procedural_pressure_and_touch_by_id(self):
        run("note", "procedural", "uses npm, the Lambda runtime needs it", "--entities=pkg")
        self.assertNotIn("#1", run("stale"))
        # own tag 3 + three notes at 3 = 12 meets the procedural threshold
        for i in range(3):
            run("note", "episodic", "bundler event %d" % i, "--entities=pkg")
        out = run("stale")
        self.assertIn("#1 procedural", out)
        self.assertIn("Verify against the repo", out)
        self.assertIn("touch 1", out)
        # soft cost: touch echoes the exact claim being confirmed
        out = run("touch", "1")
        self.assertIn("uses npm, the Lambda runtime needs it", out)
        self.assertNotIn("#1", run("stale"))

    def test_export_on_second_cycle_and_keep(self):
        run("note", "procedural", "uses npm, the Lambda runtime needs it", "--entities=pkg")
        for i in range(3):
            run("note", "episodic", "bundler event %d" % i, "--entities=pkg")
        run("touch", "1")
        # a confirmed fact under pressure again is stable and hot: export
        for i in range(4):
            run("note", "episodic", "more bundler %d" % i, "--entities=pkg")
        out = run("stale")
        self.assertIn("stable and hot", out)
        self.assertIn("touch 1 --keep", out)
        out = run("touch", "1", "--keep")
        self.assertIn("kept in memory", out)
        # after keep: pressure returns as verify, never as export
        for i in range(4):
            run("note", "episodic", "later bundler %d" % i, "--entities=pkg")
        out = run("stale")
        self.assertIn("#1", out)
        self.assertNotIn("stable and hot", out)

    def test_touch_id_rejects_non_procedural(self):
        run("note", "episodic", "an event")
        self.assertIn("No live procedural note", run("touch", "1", check=False))
        self.assertIn("--keep applies", run("touch", "alice", "--keep", check=False))

    def test_stop_hook_covers_procedural_once(self):
        import json
        run("note", "procedural", "uses npm, the Lambda runtime needs it", "--entities=pkg")
        for i in range(3):
            run("note", "episodic", "bundler event %d" % i, "--entities=pkg")
        out = run("stale", "--hook", stdin=json.dumps({"session_id": "s1"}))
        self.assertIn('"decision": "block"', out)
        self.assertIn("#1", out)
        self.assertEqual("", run("stale", "--hook", stdin=json.dumps({"session_id": "s1"})))
        run("touch", "1")
        self.assertEqual("", run("stale", "--hook", stdin=json.dumps({"session_id": "s2"})))

    def test_wake_flags_hot_procedural(self):
        run("note", "procedural", "uses npm, the Lambda runtime needs it", "--entities=pkg")
        self.assertNotIn("under pressure", run("wake"))
        for i in range(3):
            run("note", "episodic", "bundler event %d" % i, "--entities=pkg")
        w = run("wake")
        self.assertIn("under pressure", w)
        self.assertIn("touch 1", w)

    def test_other_project_procedural_stays_quiet(self):
        run("note", "procedural", "uses npm here", "--entities=pkg", project="/p/beta")
        for i in range(3):
            run("note", "episodic", "beta event %d" % i, "--entities=pkg", project="/p/beta")
        self.assertIn("#1", run("stale", project="/p/beta"))
        self.assertNotIn("#1", run("stale", project="/p/alpha"))

    def test_org_recall_and_hook(self):
        import json
        d = org_repo(facts=[("aws-lambda-bundler", "lambda-runtime",
                             "The lambda-runtime bundler breaks on symlinked node_modules")])
        run("note", "procedural", "unrelated local fact", "--entities=misc")
        out = run("recall", "bundler", org=d)
        self.assertIn("org:aws-lambda-bundler", out)
        self.assertIn("(org)", out)
        out = run("hook", org=d,
                  stdin=json.dumps({"prompt": "why does lambda-runtime fail?"}))
        self.assertIn("<segmem-recall>", out)
        self.assertIn("org:aws-lambda-bundler", out)
        # unset org dir: the same query finds nothing
        self.assertIn("No match", run("recall", "bundler"))

    def test_org_reindex_on_head_change(self):
        d = org_repo(facts=[("first-fact", "alpha-comp", "alpha-comp uses X")])
        self.assertIn("first-fact", run("recall", "alpha-comp", org=d))
        open(os.path.join(d, "facts", "second-fact.md"), "w").write(
            "---\nkind: procedural\nscope: org\nentities: beta-comp\n---\nbeta-comp uses Y\n")
        org_commit(d)
        self.assertIn("second-fact", run("recall", "beta-comp", org=d))

    def test_wake_org_summary_conflict_and_cosign(self):
        d = org_repo(facts=[("pkg-standard", "pkg", "org standard is pnpm everywhere")],
                     candidates=[("npm-lambda", "bundler",
                                  "uses npm, the Lambda runtime needs it")])
        run("note", "procedural", "uses npm, the Lambda runtime needs it", "--entities=pkg")
        w = run("wake", org=d)
        self.assertIn("Org layer: 1 facts (1 candidates)", w)
        self.assertIn("org:pkg-standard", w)
        self.assertIn("open an issue", w)
        self.assertIn("matches candidate npm-lambda", w)
        self.assertIn("co-sign", w)
        # without the org dir, wake is silent about the layer
        self.assertNotIn("Org layer", run("wake"))

    def test_contribute_prints_file_and_gates(self):
        run("note", "procedural", "uses npm, the Lambda runtime needs it", "--entities=pkg")
        out = run("contribute", "1")
        self.assertIn("candidates/pkg-uses-npm", out)
        self.assertIn("kind: procedural", out)
        self.assertIn("gh pr create", out)
        self.assertIn("uses npm, the Lambda runtime needs it", out)
        run("note", "people", "Alice owns deploys", "--entities=alice")
        run("note", "procedural", "ask alice before infra changes", "--entities=alice")
        out = run("contribute", "3", check=False)
        self.assertIn("names a person", out)
        out = run("contribute", "2", check=False)
        self.assertIn("No live procedural", out)

    def test_contribute_redirects_to_cosign(self):
        d = org_repo(candidates=[("npm-lambda", "pkg",
                                  "uses npm, the Lambda runtime needs it")])
        run("note", "procedural", "uses npm, the Lambda runtime needs it", "--entities=pkg")
        out = run("contribute", "1", org=d)
        self.assertIn("Co-sign", out)
        self.assertIn("npm-lambda", out)
        self.assertNotIn("gh pr create --title", out)

    def test_org_init_scaffold(self):
        base = tempfile.mkdtemp()
        kb = os.path.join(base, "kb")
        run("org-init", kb)
        for f in ("README.md", "CODEOWNERS", "facts/knowledge-repo.md", "candidates"):
            self.assertTrue(os.path.exists(os.path.join(kb, f)), f)
        self.assertIn("Not empty", run("org-init", kb, check=False))

    def test_note_warns_on_scope_mismatch(self):
        run("note", "episodic", "vp sync notes", "--entities=vp-sync", project="/p/hr-hub")
        out = run("note", "episodic", "more vp sync", "--entities=vp-sync", project="/p/armory")
        self.assertIn("prior notes about vp-sync live in hr-hub, not armory", out)
        self.assertIn("forget 2", out)
        # a tag already at home in this project draws no warning
        out = run("note", "episodic", "follow-up", "--entities=vp-sync", project="/p/hr-hub")
        self.assertNotIn("misfiled", out)

    def test_forget_note_by_id(self):
        run("note", "episodic", "first")
        run("note", "episodic", "misfiled")
        self.assertIn("not the newest", run("forget", "1", check=False))
        self.assertIn("Forgot #2", run("forget", "2"))
        w = run("wake")
        self.assertIn("first", w)
        self.assertNotIn("misfiled", w)
        self.assertIn("No match", run("recall", "misfiled"))
        # the freed seq is reused cleanly
        run("note", "episodic", "replacement")
        self.assertIn("replacement", run("wake"))

    def test_forget_and_supersede_chain(self):
        run("note", "identity", "lives in Berlin")
        run("note", "identity", "lives in Lisbon", "--supersedes=1")
        self.assertIn("superseded by #2", run("forget", "1", check=False))
        out = run("forget", "2")
        self.assertIn("#1 is live again", out)
        self.assertIn("Berlin", run("wake"))

    def test_recall_survives_fts_operators(self):
        run("note", "episodic", "mem-op refactor landed", "--entities=mem-op")
        out = run("recall", "mem-op OR atlas")     # hyphen is FTS5 syntax raw
        self.assertIn("mem-op refactor", out)
        self.assertIn("mem-op refactor", run("recall", "mem-op"))
        self.assertIn("No match", run("recall", "atlas"))
        # real FTS5 syntax still reaches the engine untouched
        self.assertIn("mem-op refactor", run("recall", "refactor OR nothingness"))
        self.assertIn("No match", run("recall", "refactor NOT landed"))

    def test_prompt_prints_doctrine(self):
        out = run("prompt")
        self.assertIn("30-day test", out)
        self.assertIn("touch <name>", out)
        self.assertNotIn("hooks", out)   # doctrine only; no install block

    def test_stale_count_is_one_number(self):
        self.assertEqual("0", run("stale", "--count").strip())
        run("note", "people", "Alice owns deploys", "--entities=alice")
        run("note", "episodic", "alice event a", "--entities=alice")
        run("note", "episodic", "alice event b", "--entities=alice")
        self.assertEqual("1", run("stale", "--count").strip())
        # counting never nags and never writes a nag touch
        self.assertEqual("1", run("stale", "--count").strip())

    def test_check_note_refuses_and_hints_without_writing(self):
        run("note", "procedural", "the release runs from make-release",
            "--entities=make-release")
        # too long: refused, with the mark where the limit falls
        long = run("check-note", check=False,
                   stdin='segmem note procedural "%s"' % ("x" * 300))
        self.assertIn("Too long: 300 bytes", long)
        self.assertIn("\u25ae", long)
        # a near tag: allowed, with the spelling named
        near = run("check-note",
                   stdin='segmem note procedural "another" --entities=make-relase')
        self.assertIn("similar: make-release", near)
        # not a note at all: silence
        self.assertEqual("", run("check-note", stdin="ls -la && git status"))
        self.assertEqual("", run("check-note", stdin="segmem recall make-release"))
        # a wrong kind is refused the way note refuses it
        self.assertIn("usage:", run("check-note", check=False,
                                    stdin='segmem note wrongkind "hi"'))
        # quoting this parser cannot read never blocks a command
        self.assertEqual("", run("check-note", stdin='segmem note procedural "unclosed'))
        # and none of it wrote anything
        self.assertIn("No match.", run("recall", "another"))

    def test_prompt_subagent_is_read_only(self):
        out = run("prompt", "--subagent")
        self.assertIn("wake", out)
        self.assertIn("recall", out)
        for w in ("note", "nap", "promote"):
            self.assertIn(w, out)
        self.assertNotIn("30-day test", out)   # the parent's doctrine, not this

    def test_plugin_hooks_match_cli(self):
        import json
        cfg = json.load(open(os.path.join(HERE, "hooks", "hooks.json")))
        cmds = [h["command"] for evt in cfg["hooks"].values()
                for m in evt for h in m["hooks"]]
        for want in ("segmem\" prompt", "segmem\" wake --once", "segmem\" hook --once",
                     "segmem\" stale --hook"):
            self.assertTrue(any(c.endswith(want) for c in cmds), want)
        for c in cmds:
            self.assertIn("${CLAUDE_PLUGIN_ROOT}", c)
        # the function-hook module beside it also wakes --once, or the two double up
        self.assertEqual(cfg["modules"], ["hooks.ts"])
        ts = open(os.path.join(HERE, "hooks", "hooks.ts")).read()
        self.assertIn('"wake", "--once"', ts)
        self.assertIn('"hook", "--once"', ts)
        self.assertIn("--served=function", ts)
        # the subagent rule lives in Python; the module only fetches it
        self.assertIn('"prompt", "--subagent"', ts)
        self.assertNotIn("never `note`", ts)
        # recall is the only registered tool: note stays a Bash command, which
        # is what keeps "subagents never note" true with no extra enforcement
        self.assertEqual(ts.count("$.tool.register"), 1)
        self.assertIn('name: "recall"', ts)
        self.assertNotIn('name: "note"', ts)
        # and the module never writes memory
        for w in ('"note"', '"nap"', '"promote"', '"forget"', '"touch"'):
            self.assertNotIn('/segmem", %s' % w, ts)

    def test_hook_caps_facts(self):
        import json
        for i in range(12):
            run("note", "episodic", "widget incident %d" % i, "--entities=widget-core")
        out = run("hook", stdin=json.dumps({"prompt": "what about widget-core?"}))
        lines = [l for l in out.splitlines() if l.startswith("#")]
        self.assertLessEqual(len(lines), 8)


if __name__ == "__main__":
    unittest.main()
