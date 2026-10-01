#!/bin/bash
# Run the repo's fast checks at session start so breakage shows up immediately.
# The checks are stdlib-only; cloud sessions also install requirements.txt.
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0

fail=()

# Cloud sessions only: install the bridge's dependencies (PySide6, SQLAlchemy)
# so it can be imported and run. Cached with the container after the first run.
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  python3 -m pip install --quiet --disable-pip-version-check -r requirements.txt >/dev/null 2>&1 || fail+=("dependency install")
fi

(cd elevated-associates/trading 2>/dev/null && python3 -m unittest discover -q -p "test_*.py" >/dev/null 2>&1) || fail+=("trading tests")
python3 elevated-associates/ops/ea_status.py --check >/dev/null 2>&1 || fail+=("registry check")
python3 -m py_compile start.py app.py login_bridge.py >/dev/null 2>&1 || fail+=("bridge compile")

if [ ${#fail[@]} -eq 0 ]; then
  msg="Session checks passed: trading tests, registry, bridge compile."
else
  joined=$(printf '%s, ' "${fail[@]}")
  msg="Session checks FAILED: ${joined%, }. Run the commands in CLAUDE.md to see details."
fi
printf '{"systemMessage": "%s", "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "%s"}}\n' "$msg" "$msg"
