# SuperGrok / Elevated Associates

Two things live in this repo:

- **SuperGrok Bridge** (`start.py`, `app.py`, `login_bridge.py`): a PySide6 desktop shell that drives logged-in web chat sessions. Architecture is in `docs/ARCHITECTURE.md`.
- **Elevated Associates LLC workspace** (`elevated-associates/`): the venture registry, status board, compliance notes and the paper-trading engine.

## Project skills (`.claude/skills/`)

| Skill | Use for |
|---|---|
| `ea-status` | Editing `registry.json` and rebuilding `STATUS.md` |
| `paper-trading` | Anything in `elevated-associates/trading/` |
| `run-detectors` | Static checks after editing the bridge code |
| `add-bridge-provider` | Adding a new chat target to the bridge |

## Checks CI runs (`.github/workflows/ci.yml`)

```bash
(cd elevated-associates/trading && python3 -m unittest test_paperbot test_alpaca_paper)
python3 elevated-associates/ops/ea_status.py --check
python3 -m py_compile start.py app.py login_bridge.py
```

## Hard rules

- Trading is paper only. Never add live endpoints or keys.
- Never commit secrets. `config.ini` is gitignored; use `config.ini.example`.
- Follow `elevated-associates/CHARTER.md` for anything venture-related.
