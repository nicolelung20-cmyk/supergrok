# Paper Trading Engine

A second-by-second **paper** trading bot for Elevated Associates LLC. It polls free public Coinbase prices every second, runs strategies against a simulated broker, and logs every fill. It charges the **real** taker fee (0.60%), crosses the bid/ask spread, and adds slippage, so results aren't flattered.

**It cannot trade real money.** The code has no order-placement path and never reads API keys, and a unit test fails if either is ever added.

## Run it

```bash
cd elevated-associates/trading
python3 -m unittest discover -p "test_*.py"                    # 112 tests, no network needed
python3 paperbot.py --live --products BTC-USD,ETH-USD,SOL-USD   # Coinbase prices, simulated fills
python3 paperbot.py --synthetic --ticks 20000                   # offline sanity check
python3 alpaca_paper.py --check                                 # verify Alpaca paper keys
python3 alpaca_paper.py --products BTC/USD,ETH/USD,SPY          # Alpaca quotes, mirrored paper orders
```

It needs only Python 3.9+ and no packages. Each run writes `paper_runs/<time>/ledger.jsonl` and `summary.json`, where the summary refreshes every minute and includes the gate status.

**Kill-switch:** create a file named `STOP` in the run folder (`touch paper_runs/<run>/STOP`). The bot closes every position, including in Alpaca paper, logs a `halt` event, and exits.

**Where to run it around the clock (all $0):** Nicole's Mac, with `caffeinate -i python3 alpaca_paper.py`, or any always-on machine she owns. Claude's cloud sessions are temporary and their network policy currently blocks Alpaca and Coinbase, so they are for building and testing only.

## Strategy tournament: many strategies at once, judged out of sample

`tournament.py` downloads price history once, then replays it through 44 candidates (every strategy family below, several settings each) in parallel on all CPU cores.

```bash
python3 tournament.py --history 30 --granularity 60 --fee 0.001 --products BTC-USD,ETH-USD,SOL-USD
python3 tournament.py --dex-history 30 --dex-fee 0.003 --products JUP:SOL,JUP:BONK
python3 tournament.py --replay paper_runs/<run>/ticks.csv      # reuse a download
```

- The first two-thirds of the history picks the best settings; the last third is the **out-of-sample test** those settings never saw. Candidates are ranked by their train score (return minus half the max drawdown, with at least 10 trades).
- **Read the test columns.** With 44 candidates, some look good on the train part by luck. "Robust" marks candidates that made money in both parts; even then, one window is not proof.
- Output: `leaderboard.md`, `leaderboard.json`, and `ticks.csv` (the download). The "Paper backtest" workflow's `tournament` job runs it on Coinbase 1-minute (30 days, at 0.6% and 0.1% fees), Coinbase hourly (365 days) and Solana DEX 1-minute (30 days).

## Hyperliquid top traders: paper copy-trading

`hl_copy.py` follows chosen Hyperliquid wallets and mirrors their **fresh long entries** into the paper broker. It exits when the trader starts closing, or earlier at the ELE-39 stop or take-profit.

```bash
python3 hl_copy.py --replay 30                  # what copying the default traders would have earned
python3 hl_copy.py --replay 7 --interval 1m     # finer candles, shorter window
python3 hl_copy.py --live --poll 30             # follow forward
```

- **Default traders** (in `TOP_TRADERS`) are 5 wallets chosen on 2026-10-02 from Coinversa's persistent winners:
  - profitable in each of the last 3 months;
  - their best month was no more than 55% of their 90-day profit, so one lucky month can't carry them;
  - their 30-day trend is not declining;
  - they don't trade like high-frequency bots, which a follower can't keep up with.
  
  Override the list with `--traders` or `--traders-file`.
- **Replay is honest about delay:** each copy fills at the close of the first candle after the trader's fill, not at the trader's price.
- **Different from the traders' own results:** they use leverage, shorts and position sizing; the copy is unleveraged, long-only, 5% per position. A trader's profit does not carry over one-for-one.
- **Coverage limit:** Hyperliquid keeps only each wallet's last 10,000 fills here, so a very active trader's replay may cover fewer days than requested. `report.md` shows the days actually covered.
- **Read-only:** it calls only `userFillsByTime`, `allMids` and `candleSnapshot` on the public info API. It has no wallet or keys, and a test fails if order or signing code appears. The fee is Hyperliquid's base taker rate (`Config.hl_fee`, 0.045%).
- Cloud sessions can't reach Hyperliquid. Run it on your Mac, or through the "Paper backtest" workflow's `hl_copy` job.

## Moon bot: paper copy-trading of Solana wallets

`moonbot.py` follows wallets you choose and mirrors their token buys and sells into the paper broker at live Jupiter quotes.

```bash
python3 moonbot.py --wallets <addr1>,<addr2>          # or --wallets-file wallets.txt
python3 moonbot.py --wallets-file wallets.txt --min-sol 1 --aggressive
```

- **Reads only.** It calls two public Solana methods (`getSignaturesForAddress`, `getTransaction`) and Jupiter quotes. It has no wallet and never signs or sends anything; a test fails if that changes.
- **No chasing old moves.** History that existed when the bot started is skipped; only new trades are copied.
- **What counts.** A buy is a transaction where the wallet's token balance rises while its SOL, wrapped SOL or stablecoins fall. Buys under `--min-sol` (default 0.5 SOL) are ignored.
- **Exits.** The paper position closes when the copied wallet sells, or earlier at the ELE-39 stop (2%) or take-profit (4%). Memecoins move far more than 4%, so the take-profit caps big wins; changing it is Nicole's call.
- **Where to run it.** Your Mac, or the "Moon bot (paper)" GitHub workflow (Actions tab → Run workflow, paste wallet addresses), which runs up to 5.5 hours and posts a scorecard. The public Solana RPC is rate-limited, so keep it to a handful of wallets at a 15-second interval.
- **Output.** `copied.jsonl` lists every wallet trade seen; `ledger.jsonl` and `summary.json` work like the other bots.

## Aggressive profile (opt-in)

`--aggressive` allows up to 10 open positions instead of 5. Every other ELE-39 limit stays the same, and `summary.json` records `risk_profile` so results are never mixed up. It only has an effect with more than 5 products, since each strategy holds one position per product.

## Solana DEX (Jupiter), paper only

```bash
python3 paperbot.py --jupiter                                   # JUP:SOL, quotes every 5 s
python3 paperbot.py --jupiter --products JUP:SOL,JUP:JUP --strategies trend_breakout
python3 paperbot.py --jupiter --products "JUP:<mint>@<decimals>" # any other token
```

Prices come from Jupiter's free public quote API (`lite-api.jup.ag/swap/v1/quote`). Each poll asks what a buy and a sell of one paper trade ($50, the 5% position size) would return, so the gap between bid and ask is the real round-trip cost, including pool fees and price impact. The broker then adds only the Solana network fee (`Config.dex_fee`, 0.03%), not the 0.6% exchange fee.

`jupiter_feed.py` only reads quotes. It has no wallet, never builds or sends a transaction, and reads no keys; a unit test fails if swap, signing or key code is ever added. Known tokens: SOL, JUP, BONK, WIF. Keep tokens × 2 ÷ interval under about 1 request a second (the free tier's limit). Jupiter has no price history, so DEX strategies can only be scored by running forward; `--history` backtests stay on Coinbase. Cloud sessions can't reach Jupiter; run it on your Mac or a GitHub Actions runner.

To replay past DEX prices, `--dex-history DAYS` uses free one-minute candles from Solana DEX pools (GeckoTerminal, built from on-chain swaps). Pass `--dex-fee 0.003` so each swap pays a typical pool fee; candles have no spread.

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
| `liquidity_sweep` | Buy a reclaim after price wicks under a pool of resting lows; target the pool above (see `research/liquidity-sweeps-1m.md`) |
| `liquidity_magnet` | Ride momentum toward untouched equal highs; exit at the magnet |
| `rsi_reversion` | Buy when the bar RSI is oversold (default under 25), sell when it recovers (above 55) |
| `momentum` | Buy when the close is up at least `threshold` over `lookback` bars; sell when momentum turns negative or after `max_hold` bars |

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

## Fast answers: replay history instead of waiting

The gate counts days from the price data's timestamps, not the wall clock, so 90 days of
public Coinbase candles replay in under a second:

```bash
python3 paperbot.py --history 90 --strategies trend_breakout            # hourly candles, 1 bar = 1 candle
python3 paperbot.py --history 90 --granularity 300 --strategies trend_breakout   # 5-minute candles, 12 per bar
```

**Timeframe check:** on the live feed `trend_breakout` builds one-hour bars from one-second
ticks and needs 20 bars before its first signal, so a live run shorter than about 21 hours
cannot trade at all. `--bar-ticks` sets ticks per bar; `--gate-min-days` sets the gate window.
A history replay is a backtest on past prices with fills at each candle's close, so it is
evidence for or against a strategy, not a substitute for the live paper record the charter asks for.

## The gate to real money (from [CHARTER.md](../CHARTER.md))

All four are required, and none can be waived by an agent:
1. At least **90 days** and **30+ closed trades** of live paper results that are **net positive after fees**, with max drawdown under 10%. `summary.json` → `gate` reports these measured checks.
2. A written thesis explaining why the edge exists, plus a **max-loss number**.
3. A business exchange account in the LLC's name with completed KYB, opened by Nicole.
4. Nicole's explicit yes for that specific strategy and amount.

Until then this bot produces **information, not income**.
