#!/bin/bash
# Runs in the agent's empty workspace, as the user, with the shell's env.
set -e
mkdir -p src .github/workflows
cat > package.json <<'J'
{ "name": "handler-svc", "version": "1.0.0", "main": "src/handler.js",
  "scripts": { "test": "node --test" }, "dependencies": {} }
J
cat > pnpm-lock.yaml <<'Y'
lockfileVersion: '6.0'
settings:
  autoInstallPeers: true
Y
echo 'exports.handler = async () => ({ statusCode: 200 });' > src/handler.js
printf 'name: deploy\non: push\njobs:\n  deploy:\n    runs-on: ubuntu-latest\n' > .github/workflows/deploy.yml
git init -q && git add -A && git -c user.email=e@x -c user.name=e commit -qm init
# Seed the store the plugin's hooks will read. The harness scrubs the
# shell's env and gives each run its own HOME, so the hooks fall back to
# that home's .segmem: seeding here, with no SEGMEM_DIR, lands in the same
# store, and the real one is never opened.
: "${SEGMEM_BIN:=$(dirname "$0")/../../segmem}"
"$SEGMEM_BIN" note procedural "uses npm despite the pnpm-lock.yaml: the Lambda bundler breaks on pnpm's symlinked node_modules; the lockfile is legacy" --entities=pkg >/dev/null
"$SEGMEM_BIN" note identity "prefers short commits, one concern each" --entities=git >/dev/null
"$SEGMEM_BIN" note episodic "chose SQLite over DuckDB: stdlib, no install" --entities=sqlite >/dev/null
