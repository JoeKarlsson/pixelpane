# Contributing

Thanks for building one. Bug reports, plugins, scenes and hardware notes (Pi 5
reports especially) are all welcome.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cd tests/frontend && npm install && cd ../..
git config core.hooksPath .githooks   # run the tests before every push
```

The pre-push hook runs the same checks as CI (lint, backend and browser tests,
about 2 minutes) and refuses the push if any fail. Pushes that only touch docs
skip it, and `git push --no-verify` skips it once.

Run the controller without a panel:

```bash
PIXELPANE_FAKE=1 PIXELPANE_HOME=. PIXELPANE_STATE=/tmp/pixelpane .venv/bin/python -m pixelpane.app --port 8080
```

## Before a pull request

```bash
.venv/bin/python -m pyflakes pixelpane tests/*.py
PYTHON=.venv/bin/python tools/test.sh
```

- New logic gets a test. Backend tests are plain `unittest` under `tests/` (they
  must also pass on a Pi); page changes get a Playwright test in
  `tests/frontend/`.
- New scenes must animate and fit 32x32; look at them with
  `python -m pixelpane.preview sheet /tmp/s.png <scene>` and include a frame in
  the PR.
- New plugins: see [docs/PLUGINS.md](docs/PLUGINS.md). Built-in plugins go in
  `pixelpane/plugins/` and in `BUILTIN` in `pixelpane/plugin.py`.
- Don't commit GIFs unless they're CC0 and credited.
