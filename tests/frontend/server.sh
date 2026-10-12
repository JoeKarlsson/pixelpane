#!/bin/bash
# Starts the real controller with a fake panel and a throwaway state dir for the browser tests.
set -euo pipefail
cd "$(dirname "$0")/../.."
STATE=$(mktemp -d)
export PIXELPANE_PLUGINS="$STATE/plugins" PIXELPANE_FAKE=1 PIXELPANE_HOME="$PWD/tests/frontend/fixtures/library" PIXELPANE_STATE="$STATE" PIXELPANE_CACHE="$STATE/cache"
exec "${PYTHON:-python3}" -m pixelpane.app --port "${PORT:-18765}"
