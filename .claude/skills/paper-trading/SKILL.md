---
name: paper-trading
description: Work on the paper-only trading engine in elevated-associates/trading (paperbot.py, alpaca_paper.py). Use when changing strategies, the risk policy, the simulated broker, or when asked to run or test the trading bot.
---

# Paper trading engine

Everything here is **paper only**. `paperbot.py` has no order path and reads no keys; `alpaca_paper.py` refuses any host but `paper-api.alpaca.markets`. Tests enforce both. Never add a live endpoint, live keys, or a way around those tests.

## Test (always, before committing)

```bash
cd elevated-associates/trading && python3 -m unittest discover -p "test_*.py"
```

No network or packages needed. Add a test for every behaviour change.

## Run

- Offline check: `python3 paperbot.py --synthetic --ticks 20000`
- Live prices (simulated fills): `python3 paperbot.py --live --products BTC-USD,ETH-USD`
- Alpaca paper: `python3 alpaca_paper.py --check`, keys from `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY`

Cloud sessions can't reach Coinbase or Alpaca, so use `--synthetic` there. Output goes to `paper_runs/` (gitignored). To stop a run, create a `STOP` file in its run folder.

## Risk policy (ELE-39), enforced in `Config`

5% of equity per position, at most 5 open, no leverage, 2% stop-loss, 4% take-profit, and no new entries after a 3% daily loss. One strategy at a time on Alpaca. Changing these limits is Nicole's call, so ask first.

## Reporting results

Quote fee-adjusted P&L, win rate and max drawdown from `summary.json`, and include the gate status. Don't call a strategy profitable from one short run.
