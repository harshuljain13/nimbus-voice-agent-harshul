#!/usr/bin/env bash
# Start the backend API (:8100) and the static site (:8092) together.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x "backend/.venv/bin/python" ]; then
  echo "backend venv missing — run 'make install' first." >&2
  exit 1
fi

# Invoke via `python -m` (not the ./.venv/bin/uvicorn shebang) so a moved/renamed repo dir
# doesn't break the run — the venv's python survives moves; the console-script shebangs don't.
( cd backend && exec ./.venv/bin/python -m uvicorn app.main:app --reload --port 8100 ) &
BACK=$!
( exec python3 scripts/serve.py 8092 ) &   # no-cache static server (avoids stale JS/CSS)
WEB=$!

echo ""
echo "  Backend    : http://localhost:8100/health"
echo "  Playground : http://localhost:8092/playground/playground.html"
echo "  Nimbus site: http://localhost:8092/frontend/index.html"
echo "  Ctrl-C to stop both."
echo ""

trap 'kill "$BACK" "$WEB" 2>/dev/null || true' EXIT INT TERM
wait
