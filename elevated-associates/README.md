# Elevated Associates LLC — Operating Workspace

One place for every revenue stream, AI agent, automation, and open decision run under **Elevated Associates LLC**.

Start with **[STATUS.md](STATUS.md)**: the one-page board of what's live, what's automated, what failed, and what needs you.

## Layout

| Path | What's in it |
|---|---|
| [`registry.json`](registry.json) | Single source of truth: streams, agents, blockers. Every agent updates this, nothing else. |
| [`STATUS.md`](STATUS.md) | Generated board. Rebuild with `python elevated-associates/ops/ea_status.py`. |
| [`CHARTER.md`](CHARTER.md) | Operating rules: legal, capital policy, how agents coordinate. |
| [`streams/`](streams/) | One page per revenue stream: model, state, next moves, metrics. |
| [`ledger/2026-09-interactions.md`](ledger/2026-09-interactions.md) | Consolidated log of AI-agent sessions, Routines and artifacts, Aug 28 – Sep 28. |
| [`compliance/`](compliance/) | LLC hygiene, tax, trading/securities and marketing rules. |
| [`ops/`](ops/) | The status tool and the agent coordination protocol. |

## Priority order (by expected revenue per hour of effort)

1. **Elevated AI services.** $5k–$15k packages. One signed pilot outweighs months of SaaS subscriptions. The lead-gen Routine already runs weekly, so the bottleneck is follow-up and fit calls.
2. **Elevat.** Live freemium SaaS at $29/mo Pro. This is a distribution problem now, not a build problem.
3. **Riskline.** Free audience-builder feeding a Pro waitlist. It also feeds leads into 1 and 2.
4. **High-Yield Extensions / MoneyPrinter.** Built. They need a key or a push, then distribution.
5. **Trading and Web3.** Research and paper-trading only until a strategy shows a real, fee-adjusted edge. See [streams/trading-and-web3.md](streams/trading-and-web3.md).

## Quick commands

```bash
python elevated-associates/ops/ea_status.py          # rebuild STATUS.md
python elevated-associates/ops/ea_status.py --check  # validate registry (CI-friendly)
```
