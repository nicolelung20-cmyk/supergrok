#!/bin/bash
# Run the repo's fast checks at session start so breakage shows up immediately.
# Stdlib-only; no installs, no network.
cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}" || exit 0

fail=()
(cd elevated-associates/trading 2>/dev/null && python3 -m unittest -q test_paperbot test_alpaca_paper >/dev/null 2>&1) || fail+=("trading tests")
python3 elevated-associates/ops/ea_status.py --check >/dev/null 2>&1 || fail+=("registry check")
python3 -m py_compile start.py app.py login_bridge.py >/dev/null 2>&1 || fail+=("bridge compile")

if [ ${#fail[@]} -eq 0 ]; then
  msg="Session checks passed: trading tests, registry, bridge compile."
else
  joined=$(printf '%s, ' "${fail[@]}")
  msg="Session checks FAILED: ${joined%, }. Run the commands in CLAUDE.md to see details."
fi
printf '{"systemMessage": "%s", "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "%s"}}\n' "$msg" "$msg"
