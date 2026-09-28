# Paper Trading Engine

A second-by-second **paper** trading bot for Elevated Associates LLC. It polls free public Coinbase prices every second, runs strategies against a simulated broker, and logs every fill. It charges the **real** taker fee (0.60%), crosses the bid/ask spread, and adds slippage, so results aren't flattered.

**It cannot trade real money.** The code has no order-placement path and never reads API keys, and a unit test fails if either is ever added.

## Run it

```bash
cd elevated-associates/trading
python3 -m unittest test_paperbot                               # 8 tests
python3 paperbot.py --live --products BTC-USD,ETH-USD,SOL-USD   # runs until Ctrl-C
python3 paperbot.py --synthetic --ticks 20000                   # offline sanity check
python3 paperbot.py --replay prices.csv                         # rows: ts,product,bid,ask
```

It needs only Python 3.9+ and no packages. Each run writes `paper_runs/<time>/ledger.jsonl` and `summary.json`, where the summary refreshes every minute.

**Where to run it around the clock (all $0):** Nicole's Mac, with `caffeinate -i python3 paperbot.py --live`, or any always-on machine she owns. Claude's cloud sessions are temporary and this environment blocks exchange APIs, so they are for building and testing only.

## Strategies

| Name | Idea |
|---|---|
| `ema_cross` | Trend following: buy when the 30-tick EMA crosses above the 120-tick EMA, sell on the cross back |
| `zscore_reversion` | Mean reversion: buy when price is 2.5σ below its 5-minute mean, exit when it reverts |

Risk controls on every strategy:
- 10% of equity per position, at most 3 positions open.
- 2% stop-loss and 4% take-profit.
- A daily kill-switch that stops new entries after a 5% loss on the day.

## What the numbers say so far

| Run | Result |
|---|---|
| Synthetic random walk, 20k ticks | −4.9%, $49 in fees on 42 trades. Fees were essentially the entire loss |
| Live Coinbase feed check (Sep 28) | 285 real ticks in 95 s for BTC/ETH/SOL at about 1 per second; BTC spread about $0.01. This only confirms the data path: 95 s is shorter than the strategies' warm-up, so there are no trades to judge |

**The math that matters:** a round trip pays about 1.2% in fees plus the spread. A strategy trading every few minutes needs each trade to average **more than 1.2%** just to break even. Most second-by-second retail strategies can't clear that bar, which is the same finding as the earlier "Fees Ate the Edge" analysis. The ways to improve the odds:
1. **Lower fees**: maker orders (0.40%) or higher-volume fee tiers.
2. **Fewer, larger-conviction trades**: longer timeframes where moves beat the fees.
3. **Measure before believing**: run live paper for weeks, not minutes.

## The gate to real money (from [CHARTER.md](../CHARTER.md))

All four are required, and none can be waived by an agent:
1. At least **90 days** of live paper results that are **net positive after fees**, with max drawdown under 15%.
2. A written thesis explaining why the edge exists, plus a **max-loss number**.
3. A business exchange account in the LLC's name with completed KYB, opened by Nicole.
4. Nicole's explicit yes for that specific strategy and amount.

Until then this bot produces **information, not income**.
