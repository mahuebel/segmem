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


if __name__ == "__main__":
    unittest.main()
