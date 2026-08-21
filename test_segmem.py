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
        # naps come due smallest block first
        out = run("nap", "0-1", "alpha 0 and 1")
        self.assertIn("#2-3", out)
        out = run("nap", "2-3", "alpha 2 and 3")
        self.assertIn("#0-3", out)
        self.assertIn("All compressed", run("nap", "0-3", "alpha 0 to 3"))

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
        run("note", "episodic", "chose Node over Bun for the Lambda runtime")
        run("note", "episodic", "beta secret", project="/p/beta")
        out = run("hook", stdin=json.dumps({"prompt": "ask Alice about the Lambda deploy"}))
        self.assertIn("<segmem-recall>", out)
        self.assertIn("Alice owns", out)
        self.assertIn("Lambda", out)
        self.assertNotIn("beta secret", out)
        self.assertEqual("", run("hook", stdin=json.dumps({"prompt": "fix it please"})))
        self.assertEqual("", run("hook", stdin="not json"))


if __name__ == "__main__":
    unittest.main()
