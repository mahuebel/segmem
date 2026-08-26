"""Run: python3 test_segmem.py"""
import os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "segmem")


def run(*args, project="/p/alpha", check=True, stdin=None):
    env = dict(os.environ, SEGMEM_DIR=run.dir, SEGMEM_PROJECT=project)
    r = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True,
                       env=env, input=stdin)
    if check and r.returncode:
        raise AssertionError(r.stderr + r.stdout)
    return r.stdout + r.stderr


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
        for i in range(66):
            run("note", "episodic", "e%d" % i)
        out = run("wake", check=False)
        self.assertIn("Cannot wake", out)
        self.assertIn("#0-1", out)           # smallest needed block first
        self.assertIn("Keep doubts as doubts", out)
        run("nap", "0-1", "e0 e1")
        out = run("wake", check=False)
        # the cover for 66 lines over budget 64 needs only a few old blocks
        self.assertTrue("You are awake" in out or "Cannot wake" in out)
        while "Cannot wake" in out:
            import re
            lo, hi = re.search(r"nap (\d+)-(\d+)", out).groups()
            run("nap", "%s-%s" % (lo, hi), "sum %s-%s" % (lo, hi))
            out = run("wake", check=False)
        self.assertIn("You are awake", out)
        self.assertNotIn("Compress", out)    # nothing premature after wake

    def test_people_listed_by_name(self):
        run("note", "people", "Alice owns deploys", "--entities=alice")
        w = run("wake")
        self.assertIn("People known: alice", w)
        self.assertIn("Alice owns deploys", run("recall", "alice"))

    def test_wake_refuses_when_cover_needs_missing_summary(self):
        # Force a cover that needs a summary: budget is 64, so exceed it.
        env_budget = 70
        for i in range(env_budget):
            run("note", "episodic", "e%d" % i)
        out = run("wake", check=False)
        self.assertIn("Cannot wake", out)

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
        # 64 near-max episodic notes fit the budget with no summaries needed;
        # the whole wake must stay under the smallest harness cutoff (30k chars)
        filler = "x" * 200
        for i in range(64):
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

    def test_note_warns_on_scope_mismatch(self):
        run("note", "episodic", "vp sync notes", "--entities=hr-hub", project="/p/hr-hub")
        out = run("note", "episodic", "more vp sync", "--entities=hr-hub", project="/p/armory")
        self.assertIn("prior notes about hr-hub live in hr-hub, not armory", out)
        self.assertIn("forget 2", out)
        # a tag already at home in this project draws no warning
        out = run("note", "episodic", "follow-up", "--entities=hr-hub", project="/p/hr-hub")
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

    def test_plugin_hooks_match_cli(self):
        import json
        cfg = json.load(open(os.path.join(HERE, "hooks", "hooks.json")))
        cmds = [h["command"] for evt in cfg["hooks"].values()
                for m in evt for h in m["hooks"]]
        for want in ("segmem\" prompt", "segmem\" wake", "segmem\" hook", "segmem\" stale --hook"):
            self.assertTrue(any(c.endswith(want) for c in cmds), want)
        for c in cmds:
            self.assertIn("${CLAUDE_PLUGIN_ROOT}", c)

    def test_hook_caps_facts(self):
        import json
        for i in range(12):
            run("note", "episodic", "widget incident %d" % i, "--entities=widget-core")
        out = run("hook", stdin=json.dumps({"prompt": "what about widget-core?"}))
        lines = [l for l in out.splitlines() if l.startswith("#")]
        self.assertLessEqual(len(lines), 8)


if __name__ == "__main__":
    unittest.main()
