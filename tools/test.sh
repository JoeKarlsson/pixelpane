#!/bin/bash
# Run every test: backend (unittest) and the control page in a real browser (Playwright).
#   PYTHON=/path/to/python tools/test.sh      # PYTHON needs Flask, Pillow and numpy
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
echo "== backend"
"$PY" -m unittest discover -s tests -t .
echo "== frontend"
cd tests/frontend
[ -d node_modules ] || npm install --silent
PYTHON="$PY" npx playwright test
