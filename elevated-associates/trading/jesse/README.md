# Jesse research setup (paper and backtests only)

[Jesse](https://github.com/jesse-ai/jesse) is an open-source backtesting framework. Here it is a **research tool** for testing a strategy idea on historical candles before it goes into the paper engine one directory up. It does not replace `paperbot.py`, and the one-strategy-at-a-time rule (ELE-39) still applies to what runs on Alpaca paper.

## Rules

- Backtests and paper results only. `setup.sh` never installs the paid live-trade plugin (`jesse install-live`) and never reads or stores exchange keys, and `test_jesse_setup.py` fails if either is added.
- Free tier only: Jesse, Postgres and Redis are open source.
- A backtest is not evidence for the paper-to-live gate (90+ days, 30+ closed paper trades, positive after fees, max drawdown under 10%, kill-switch tested). Only the paper engine's scorecard counts.

## Use

```bash
./setup.sh setup    # once: venv, project template, Postgres user and database, local .env
./setup.sh start    # dashboard at http://localhost:9000 (password in bot/.env)
./setup.sh status
./setup.sh stop
```

State lives in `~/jesse-bot` (override with `JESSE_HOME`), outside this repo. The generated `.env` holds random passwords and is never committed.

## Known limits

- Importing candles needs outbound access to an exchange. Claude's cloud sessions block it, so run backtests on a machine you own.
- The dashboard's code editor autocomplete needs a GitHub download that the cloud sandbox blocks; `start` skips it with `--skip-lsp`.
