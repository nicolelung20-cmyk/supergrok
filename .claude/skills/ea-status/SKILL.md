---
name: ea-status
description: Validate and rebuild the Elevated Associates LLC status board. Use when updating registry.json (streams, agents, blockers), recording an agent run, or when asked "what's the status" of the venture.
---

# Elevated Associates status board

`elevated-associates/registry.json` is the single source of truth. `STATUS.md` is generated from it, so never hand-edit `STATUS.md`.

## Steps

1. Read `elevated-associates/registry.json` and `elevated-associates/ops/agent-protocol.md`.
2. Make the scoped change to `registry.json` only (agent `last_status` / `last_run`, stream state, or a `blockers` entry).
3. Validate: `python3 elevated-associates/ops/ea_status.py --check`. It must exit 0.
4. Rebuild the board: `python3 elevated-associates/ops/ea_status.py`.
5. Commit `registry.json` and `STATUS.md` together.

## Rules

- Follow `elevated-associates/CHARTER.md`. Legal-only work; no real-money trading.
- Blockers are for things only Nicole can do. Include the exact URL or env var name needed.
- Never put API keys, tokens or account numbers in the registry.
