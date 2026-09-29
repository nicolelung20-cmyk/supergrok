#!/bin/bash
# SessionStart hook for Claude Code on the web: installs Python deps and
# dev tools so tests, lint and the Elevated Associates registry check work.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"

# App dependencies (PySide6, SQLAlchemy) plus test/lint tools.
python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt
python3 -m pip install --quiet --disable-pip-version-check pytest ruff

# Let tests import modules that live next to them (e.g. trading/paperbot.py).
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PYTHONPATH=\"$PWD/elevated-associates/trading:\${PYTHONPATH:-}\"" >> "$CLAUDE_ENV_FILE"
fi

# Fail fast if the venture registry is malformed.
python3 elevated-associates/ops/ea_status.py --check
