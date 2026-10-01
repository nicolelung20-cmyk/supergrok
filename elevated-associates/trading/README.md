# Paper Trading Engine

A second-by-second **paper** trading bot for Elevated Associates LLC. It polls free public Coinbase prices every second, runs strategies against a simulated broker, and logs every fill. It charges the **real** taker fee (0.60%), crosses the bid/ask spread, and adds slippage, so results aren't flattered.

**It cannot trade real money.** The code has no order-placement path and never reads API keys, and a unit test fails if either is ever added.

## Run it

```bash
cd elevated-associates/trading
python3 -m unittest discover -p "test_*.py"                    # 30 tests, no network needed
python3 paperbot.py --live --products BTC-USD,ETH-USD,SOL-USD   # Coinbase prices, simulated fills
python3 paperbot.py --synthetic --ticks 20000                   # offline sanity check
python3 alpaca_paper.py --check                                 # verify Alpaca paper keys
python3 alpaca_paper.py --products BTC/USD,ETH/USD,SPY          # Alpaca quotes, mirrored paper orders
```

It needs only Python 3.9+ and no packages. Each run writes `paper_runs/<time>/ledger.jsonl` and `summary.json`, where the summary refreshes every minute and includes the gate status.

**Kill-switch:** create a file named `STOP` in the run folder (`touch paper_runs/<run>/STOP`). The bot closes every position, including in Alpaca paper, logs a `halt` event, and exits.

**Where to run it around the clock (all $0):** Nicole's Mac, with `caffeinate -i python3 alpaca_paper.py`, or any always-on machine she owns. Claude's cloud sessions are temporary and their network policy currently blocks Alpaca and Coinbase, so they are for building and testing only.

## Deploy: run the paper bot around the clock

Run it on a machine you own (your Mac is free). One-time setup:

1. Nothing else is required: with no keys it runs the keyless simulation (public Coinbase prices, simulated fills at the real fee, spread and slippage). It produces the same scorecard and gate status as the Alpaca mode.
2. `./run_paper.sh` runs `trend_breakout` on BTC/USD (override with `PAPER_PRODUCTS` / `PAPER_STRATEGY`). On a Mac it uses `caffeinate` so the machine stays awake.
3. `./run_paper.sh status` prints the latest scorecard, and `./run_paper.sh stop` is the kill-switch: it closes every position and exits.
4. Optional, only if you want orders mirrored into a broker's paper account: set `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` (paper keys) in your shell, never in chat or git. The script then uses Alpaca automatically.

Notes:
- Leave it running. The gate's "days running" counts from process start, so a restart resets that clock (the ledger still appends).
- `trend_breakout` builds hourly bars and needs about 20 bars of history before its first trade, so expect the first trade after roughly a day. This is also why a scheduled GitHub Actions run (short, fresh each time) can't run this strategy.
- Paper only: the Alpaca client refuses any host except `paper-api.alpaca.markets`, and the keyless mode has no order path at all. Going live is a separate decision after the gate below.

## Alpaca paper (Linear ELE-40)

`alpaca_paper.py` runs the same strategies on Alpaca quotes and mirrors each simulated entry and exit as a market order in Alpaca's **paper** account. That gives one broker for stocks, ETFs and crypto with a free paper account (Robinhood has no paper API). Trading runs in Nicole's personal name; going live later only means swapping in live keys for a personal account.

- **Paper only.** The client refuses any host except `paper-api.alpaca.markets`, and a test checks that the live host appears nowhere in the module.
- **Keys** come from the environment variables `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` (paper keys). Never commit them or paste them into chat.
- **Fees:** stocks and ETFs are commission-free (`stock_fee=0`); crypto uses 0.25% taker (check Alpaca's current fee page).
- Stocks only get quotes while the US market is open. Options are not wired in yet.
- `paperbot.py` stays simulation-only with no credentials; `PaperBroker` remains the scorecard and the Alpaca order ids go in the ledger for reconciliation.

## Strategies

| Name | Idea |
|---|---|
| `ema_cross` | Trend following: buy when the 30-tick EMA crosses above the 120-tick EMA, sell on the cross back |
| `zscore_reversion` | Mean reversion: buy when price is 2.5σ below its 5-minute mean, exit when it reverts |
| `trend_breakout` | Long-timeframe, fee-aware: buy a bar close above the prior 20-bar high when above the 50-bar EMA and the channel range is at least 3x round-trip cost; exit below the prior 10-bar low. Bars are 3600 ticks (about 1 hour at 1 tick/s). One strategy at a time, no parallel runs |

Run **one strategy at a time** on Alpaca (ELE-39); `alpaca_paper.py` defaults to `ema_cross`.

Risk policy (ELE-39), enforced in `Config` and tested:
- 5% of equity per position, at most 5 positions open, cash only (no leverage).
- 2% stop-loss and 4% take-profit.
- A daily kill-switch that stops new entries after a 3% loss on the day.

## What the numbers say so far

| Run | Result |
|---|---|
| Synthetic random walk, 20k ticks | −4.9%, $49 in fees on 42 trades. Fees were essentially the entire loss |
| Live Coinbase feed check (Sep 28) | 285 real ticks in 95 s for BTC/ETH/SOL at about 1 per second; BTC spread about $0.01. This only confirms the data path: 95 s is shorter than the strategies' warm-up, so there are no trades to judge |
| Synthetic, 20k ticks, one strategy each (Sep 28) | At 0.60% fees: ema_cross −3.1%, zscore −3.0%. At 0.25% fees: ema_cross −2.8%, zscore −1.1% (49% wins). A random walk has no edge, so a loss is expected. What this shows is that cheaper fees cut the loss, and that the 3% daily kill-switch capped every run near −3% |

**The math that matters:** a round trip pays about 1.2% in fees plus the spread. A strategy trading every few minutes needs each trade to average **more than 1.2%** just to break even. Most second-by-second retail strategies can't clear that bar, which is the same finding as the earlier "Fees Ate the Edge" analysis. The ways to improve the odds:
1. **Lower fees**: maker orders (0.40%) or higher-volume fee tiers.
2. **Fewer, larger-conviction trades**: longer timeframes where moves beat the fees.
3. **Measure before believing**: run live paper for weeks, not minutes.

## The gate to real money (from [CHARTER.md](../CHARTER.md))

All four are required, and none can be waived by an agent:
1. At least **90 days** and **30+ closed trades** of live paper results that are **net positive after fees**, with max drawdown under 10%. `summary.json` → `gate` reports these measured checks.
2. A written thesis explaining why the edge exists, plus a **max-loss number**.
3. A business exchange account in the LLC's name with completed KYB, opened by Nicole.
4. Nicole's explicit yes for that specific strategy and amount.

Until then this bot produces **information, not income**.
