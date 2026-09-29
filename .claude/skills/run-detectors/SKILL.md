---
name: run-detectors
description: Run the vendored static-analysis detectors (swallowed exceptions, raw SQL, monkey patches, recursion, threads, lifecycle bypass, etc.) over the SuperGrok code. Use after editing start.py, app.py or login_bridge.py, or when asked to audit or certify code quality.
---

# SuperGrok detectors

The detectors live in `vendor/claude/` and are report-only. They run through `start.py` without launching Qt, so they work even when PySide6 isn't installed.

## Commands

```bash
python3 start.py --claude-detectors all                    # full suite
python3 start.py --claude-detectors swallowed-exceptions   # one detector
python3 start.py --swallowed | --raw-sql | --recursion | --monkeypatch | --nonconform | --lifecycle-bypass
python3 start.py --detector-selftest                       # check the detector routes
python3 start.py --manual                                  # every flag
```

Reference: `vendor/claude/README.md` and `vendor/claude/DETECTORS_MANUAL.md`.

## Workflow

1. Run the detectors relevant to the files you changed.
2. Fix new HIGH findings in code you touched. Leave pre-existing findings in untouched code alone unless asked.
3. Runs rewrite `logs/*.txt` and `reports/claude_detectors_report_latest.txt`. Don't commit that churn unless the user asked for fresh reports: `git checkout -- logs reports`.
4. Use `# noqa: <detector>` only when the finding is a real false positive, and say why in the same comment.
