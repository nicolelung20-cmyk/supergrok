# Liquidity sweeps and magnets on one-minute charts

Paper research for Elevated Associates LLC. Nothing here places real orders; results come from the paper broker in `paperbot.py`.

## The idea

Stop-loss orders cluster just below obvious lows (and above obvious highs). When price trades through such a level, those stops fire as market sells, which briefly adds selling and then often runs out of sellers. A **liquidity sweep** is that move: a wick below a pool of lows that closes back above it. The thesis is that the close back above shows the sell-side liquidity was absorbed, so price tends to travel toward the opposite pool, the recent highs where buy stops sit.

## Rules as coded (`LiquiditySweep`, long only, spot)

| Step | Rule (defaults) |
|---|---|
| Liquidity pool | Lowest low and highest high of the prior `lookback` = 30 one-minute bars (`--sweep-lookback`) |
| Sweep | Current bar's low is below the pool low **and** it closes back above the pool low |
| Entry | Buy at the close of the sweep bar |
| Invalidation | Sell when a later bar trades back down to the stop: the wick low, minus `--sweep-stop-buffer` average bar ranges |
| Target | Sell when a later bar reaches the pool high (the opposite liquidity); with `--sweep-trail N`, keep holding and trail the stop under the last N bars' lows instead |
| Time stop | Sell after `max_hold` = 30 bars |
| Cost filter | Skip unless target distance ≥ `edge_multiple` (2) × round-trip cost |
| Shape filter | Skip unless target distance ≥ `min_rr` (1.5) × distance to the wick |

The broker's ELE-39 limits still sit on top: 5% per position, at most 5 open, 2% stop, 4% take-profit, 3% daily loss halt. On one-minute bars, the strategy's own exits normally fire well before the 2% and 4% bands.

## Why fees decide this

One-minute moves are small. A typical sweep's target is a few tenths of a percent away. The round-trip cost the filter uses is 2 × (fee + slippage):

| Venue | Fee per side | Round trip | Minimum target with `edge_multiple` 2 |
|---|---|---|---|
| Coinbase (entry tier) | 0.60% | ≈ 1.24% | ≈ 2.5% |
| Low-cost what-if (e.g. a Solana DEX via Jupiter) | 0.10% | ≈ 0.24% | ≈ 0.5% |

At Coinbase's fee, most one-minute sweeps are filtered out, and the ones that pass are rare, volatile moments. That is deliberate: without the filter, fees alone made both earlier strategies lose about what they paid in fees. The low-fee run shows whether the pattern has an edge before costs. If it loses even there, it has no edge to protect.

## Using replay ("time is not linear")

Waiting for 90 days of live one-minute data takes 90 days. Replaying 90 days of real Coinbase one-minute candles through the same paper broker takes a few minutes on a GitHub runner. The `sweep_1m` job in `.github/workflows/paper-backtest.yml` does this daily for 30 and 90 days at both fee levels.

Replay limits to keep in mind:

- **Fills happen at the bar close.** A stop or target touched inside a bar is filled at that bar's close, not at the exact level. This can flatter or hurt results.
- **No order book.** Size is small ($50) and slippage is a flat 2 bps; real fills in fast sweeps can be worse.
- **One sample per window.** Compare 30 vs 90 days and the two fee levels. A result that only appears in one window is overfitting, not an edge.
- **The gate still applies.** Passing in replay is only a reason to run it forward on paper (Mac or Jupiter feed) for 90+ days. Going live is Nicole's separate decision.

## How to run it

```bash
cd elevated-associates/trading
python3 paperbot.py --history 30 --granularity 60 --strategies liquidity_sweep                 # Coinbase fee
python3 paperbot.py --history 30 --granularity 60 --strategies liquidity_sweep --fee 0.001     # low-fee what-if
python3 paperbot.py --jupiter --products JUP:SOL --strategies liquidity_sweep                  # forward, Solana DEX quotes
```

Cloud sessions can't reach Coinbase or Jupiter; run these on a Mac or let the workflow run them.

## Results

### Round 1: baseline (BTC, ETH, SOL), run 2026-10-02

| Window | Fee | Trades | Win rate | Return | Fees paid | Max DD | Gate |
|---|---|---|---|---|---|---|---|
| 30 days | 0.6% | 9 | 11.1% | −0.60% | $5.37 | 0.61% | not passed |
| 30 days | 0.1% | 1,277 | 13.1% | −14.00% | $118.66 | 14.01% | not passed |
| 90 days | 0.6% | 15 | 26.7% | −0.55% | $8.98 | 0.67% | not passed (15 trades, net negative) |
| 90 days | 0.1% | 3,139 | 13.5% | −30.80% | $262.29 | 30.80% | not passed |

What it says:

- **At Coinbase's fee the cost filter does its job.** Only 9 setups qualified in 30 days, so losses stayed small, but there were too few trades to judge.
- **At the low fee it trades constantly and loses.** Before fees the trades were still negative (about −$21 over 30 days, −$46 over 90), so there is no raw edge yet; fees then made it −14% and −31%.
- **The few Coinbase-fee trades were slightly positive before fees** (+$3.44 on 15 trades over 90 days), but 15 trades is far too few to mean anything.
- **The stop is the problem.** A 13% win rate means price almost always comes back to the wick. With the stop exactly at the wick, ordinary one-minute noise takes it out before the move to the opposite pool.

### Round 2: follow the liquidity (run 36961525434, 2026-10-02)

Four variants on seven liquid coins (BTC, ETH, SOL, XRP, DOGE, AVAX, LINK), 30 and 90 days, both fees:

| Variant | Change | Why |
|---|---|---|
| baseline | as round 1 | control |
| buffer | stop 0.5 average bar ranges below the wick | survive retests of the wick |
| big-pools | 4-hour pools (240 bars), buffered stop | bigger targets, fewer but stronger levels |
| follow | big pools, then trail the stop under the last 15 bars' lows after the target | let winners run to the next pool |

More coins means more setups ("more trades"); the pool size and trailing aim at larger gains per trade. The broker's 4% take-profit and 2% stop (ELE-39) still cap every trade; changing those is Nicole's call.

Results on $1,000 of paper money each. Pre-fee P&L is net P&L plus fees paid: the edge before costs.

| Variant | Window | Fee | Trades | Win rate | Return | Fees paid | Pre-fee P&L | Max DD |
|---|---|---|---|---|---|---|---|---|
| baseline | 30 d | 0.6% | 86 | 10.5% | −5.18% | $50.11 | −$1.71 | 5.18% |
| baseline | 30 d | 0.1% | 4,045 | 15.1% | −37.62% | $322.68 | −$53.60 | 37.63% |
| baseline | 90 d | 0.1% | 8,334 | 14.7% | −62.35% | $530.35 | −$93.23 | 62.36% |
| buffer | 30 d | 0.6% | 72 | 13.9% | −4.11% | $42.20 | +$1.14 | 4.11% |
| buffer | 30 d | 0.1% | 3,466 | 20.6% | −32.18% | $286.65 | −$35.29 | 32.26% |
| buffer | 90 d | 0.6% | 121 | 17.4% | −5.84% | $70.53 | +$12.14 | 5.85% |
| buffer | 90 d | 0.1% | 7,256 | 19.7% | −56.59% | $487.78 | −$78.23 | 56.64% |
| big-pools | 30 d | 0.6% | 340 | 7.4% | −19.14% | $183.60 | −$8.03 | 19.25% |
| big-pools | 30 d | 0.1% | 1,437 | 13.2% | −15.69% | $131.80 | −$25.58 | 15.96% |
| big-pools | 90 d | 0.6% | 654 | 10.4% | −31.73% | $328.67 | +$11.15 | 31.82% |
| big-pools | 90 d | 0.1% | 3,825 | 13.5% | −34.99% | $309.30 | −$41.00 | 35.24% |
| follow | 30 d | 0.6% | 340 | 7.4% | −19.09% | $183.67 | −$7.48 | 19.18% |
| follow | 30 d | 0.1% | 1,436 | 13.2% | −15.26% | $131.95 | −$21.14 | 15.46% |
| follow | 90 d | 0.6% | 654 | 10.4% | −31.68% | $328.92 | +$11.90 | 31.78% |
| follow | 90 d | 0.1% | 3,824 | 13.5% | −34.45% | $310.18 | −$34.71 | 34.64% |
| magnet | 30 d | 0.6% | 140 | 7.1% | −8.71% | $79.96 | −$7.16 | 8.74% |
| magnet | 30 d | 0.1% | 2,001 | 28.9% | −21.54% | $177.82 | −$37.57 | 21.57% |
| magnet | 90 d | 0.6% | 261 | 9.2% | −14.96% | $144.48 | −$5.09 | 15.04% |
| magnet | 90 d | 0.1% | 5,092 | 28.1% | −45.17% | $384.88 | −$66.81 | 45.21% |
| magnet-follow | 30 d | 0.6% | 140 | 7.1% | −8.72% | $79.95 | −$7.30 | 8.76% |
| magnet-follow | 30 d | 0.1% | 1,952 | 26.6% | −20.46% | $174.84 | −$29.79 | 20.54% |
| magnet-follow | 90 d | 0.6% | 261 | 9.2% | −15.09% | $144.31 | −$6.61 | 15.20% |
| magnet-follow | 90 d | 0.1% | 4,977 | 25.8% | −43.75% | $379.72 | −$57.82 | 43.78% |
| baseline | 90 d | 0.6% | 137 | 13.1% | −7.27% | $79.22 | +$6.55 | 7.27% |

The 90-day baseline at 0.6% first died on a Coinbase read timeout partway through the download. It was fixed in c6ab845; the row above is the re-run (run 36963056297).

**Verdict: no variant made money after fees in either window, let alone both.** What the numbers say:

- **Only `buffer` was positive before fees in both windows, and only barely.** At 0.6% it earned $1.14 (30 d) and $12.14 (90 d) before fees, then paid $42 and $71 in fees. `big-pools`/`follow` at 0.6% were +$11 before fees over 90 days, but −$8 over 30 days and $329 in fees.
- **Cheaper fees made results worse, not better.** At 0.1% the cost filter lets far smaller targets through: 10–50 × more trades, and pre-fee P&L turns clearly negative (−$21 to −$93). The small setups are noise, not liquidity.
- **Trailing (`follow`) changed almost nothing** versus `big-pools`: the 4% take-profit closes winners before the trail takes over.
- **Magnets lost before fees** in every window (−$5 to −$67). The higher win rate at 0.1% (28%) came from small targets that do not cover the stop losses.

### Liquidity magnet (`liquidity_magnet`)

The sweep trades the *reversal* after liquidity is taken. The magnet trades the *pull* toward liquidity that has not been taken yet:

| Step | Rule (defaults) |
|---|---|
| Magnet | Nearest level above price where at least 3 one-minute highs in the last 240 bars line up within 0.1% (equal highs, where buy stops rest) and no bar has traded through it since |
| Minimum distance | Only magnets at least 2 × round-trip cost above price count (closer equal highs can't pay for the trade) |
| Entry | A bar closes above the previous bar's high (momentum toward the magnet) and above the 60-bar EMA |
| Stop | Lowest low of the last 5 bars, minus the stop buffer |
| Exit | At the magnet, or with `--sweep-trail`, keep holding past it and trail under recent lows |
| Filters | Same as the sweep: reward ≥ 2 × round-trip cost and ≥ 1.5 × risk |

Two magnet variants (`magnet`, `magnet-follow`) run in the same round-2 replay as the sweep variants.

### Aggressive profile (opt-in, Nicole's choice 2026-10-02)

`--aggressive` raises only the open-position cap from 5 to 10. Position size (5%), stop (2%), take-profit (4%) and the 3% daily halt stay at the ELE-39 limits, and the defaults are unchanged. The engine holds one position per coin per strategy, so the cap only matters with more than 5 coins: the `follow-aggressive` and `magnet-aggressive` variants trade 12 Coinbase coins (adding ADA, LTC, DOT, BCH, UNI). More open trades also means more fees and more correlated losses on market-wide drops, so compare drawdown, not just return.

Results (run 36961997983, 12 coins, max 10 open) against the same variant at the normal profile (7 coins, max 5 open):

| Variant | Window | Fee | Trades | Win rate | Return | Fees paid | Pre-fee P&L | Max DD | Normal-profile return |
|---|---|---|---|---|---|---|---|---|---|
| follow-aggressive | 30 d | 0.6% | 778 | 10.0% | −37.17% | $374.73 | +$2.82 | 37.22% | −19.09% |
| follow-aggressive | 30 d | 0.1% | 2,525 | 14.2% | −23.02% | $221.41 | −$10.24 | 23.25% | −15.26% |
| follow-aggressive | 90 d | 0.6% | 1,521 | 10.7% | −58.81% | $612.52 | +$24.29 | 58.86% | −31.68% |
| follow-aggressive | 90 d | 0.1% | 6,475 | 13.9% | −49.44% | $463.39 | −$31.89 | 49.61% | −34.45% |
| magnet-aggressive | 30 d | 0.6% | 400 | 9.8% | −22.62% | $210.64 | −$15.52 | 22.64% | −8.71% |
| magnet-aggressive | 30 d | 0.1% | 4,084 | 28.9% | −40.71% | $319.48 | −$87.38 | 40.77% | −21.54% |
| magnet-aggressive | 90 d | 0.6% | 768 | 10.8% | −37.83% | $367.79 | −$10.53 | 37.85% | −14.96% |
| magnet-aggressive | 90 d | 0.1% | 10,501 | 28.5% | −72.36% | $599.12 | −$124.43 | 72.39% | −45.17% |

**Verdict: the aggressive profile roughly doubled trades and doubled losses.** With no edge per trade, more open positions only multiply fees: on $1,000, the 30-day follow variant at 0.6% went from −$191 to −$372. It is not worth using until a strategy is positive at the normal profile.

## Decentralized: Solana DEX replay

The same strategies also replay on **one-minute candles from Solana DEX pools**, built from on-chain swaps and published free by GeckoTerminal. Each token uses its highest-volume pool.

```bash
python3 paperbot.py --dex-history 30 --dex-fee 0.003 --products JUP:SOL,JUP:JUP,JUP:BONK,JUP:WIF \
  --strategies liquidity_magnet --sweep-stop-buffer 0.5
```

- **Costs.** Candles carry only prices, not the spread, so each swap is charged `--dex-fee` 0.3% (a typical 0.25% pool fee plus network fee and margin). Live paper runs on the Jupiter feed use real quotes instead, where the pool fee is already in the price.
- **History depth.** GeckoTerminal's free minute history may be shorter than 90 days for some pools; the job summary prints the days actually replayed.
- **Rate limit.** The free API allows about 30 requests a minute, so each page waits 2.1 s (about 6 minutes for 30 days of four tokens).

The `dex_1m` job in `paper-backtest.yml` runs baseline, follow, magnet and magnet-follow on SOL, JUP, BONK and WIF for 30 and 90 days.

Results (run 36962894214, SOL/JUP/BONK/WIF, swap cost 0.3%, $1,000 each). The 90-day jobs run two at a time behind the rate limit and are still going:

| Variant | Window | History replayed | Trades | Win rate | Return | Fees paid | Pre-fee P&L | Max DD |
|---|---|---|---|---|---|---|---|---|
| baseline | 30 d | 30.0 d | 1,198 | 12.1% | −33.32% | $295.20 | −$37.99 | 33.32% |
| follow | 30 d | 30.0 d | 479 | 17.1% | −12.87% | $133.16 | +$4.44 | 13.04% |
| magnet | 30 d | running | | | | | | |
| magnet-follow | 30 d | running | | | | | | |
| baseline / follow / magnet / magnet-follow | 90 d | queued | | | | | | |

So far the DEX picture matches Coinbase. The 0.3% swap cost is low enough to let thousands of small setups through, and those setups are not an edge. `follow` was barely positive before fees (+$4.44) and paid $133 in fees.

## Next ideas (one at a time, after round 2)

1. Keep only a variant that holds up in **both** the 30-day and 90-day windows at the low fee.
2. Volume filter: real stop runs print above-average volume on the sweep bar.
3. Prior-day high/low as the pool instead of a rolling window.
4. Forward paper test on the Jupiter feed for the survivor.

## Round 3: tournament and top-trader copies (2026-10-02)

The single-strategy runs above test one idea at a time. `tournament.py` now replays one download through 44 candidates in parallel. Those candidates cover sweep, magnet, trend, EMA, z-score, RSI and momentum, with several settings each. It picks settings on the first two-thirds of the history and scores them on the last third, which they never saw. That is the defence against fooling ourselves with 44 tries: a candidate only counts if it is **robust** (positive in both parts), and then needs confirming on other windows.

`hl_copy.py` tests a different source of edge: real Hyperliquid traders with three straight profitable months. The replay copies only their fresh longs, one candle late, unleveraged at 5% per position. So it measures what a follower actually gets, not what the traders made.

Results (run 36962586763) are below. **Verdict so far: none of the 44 rule-based candidates has an edge on Coinbase, at either fee level or timeframe.** The only consistent signal is that 1-minute z-score reversion is slightly positive before fees, and only a venue far cheaper than 0.1% per side could turn that into profit.

| Run | Robust candidates | Best robust (test return) | Notes |
|---|---|---|---|
| Coinbase 1m, 30 d, fee 0.6% (BTC/ETH/SOL, Sep 2 – Oct 2) | 0 of 44 | none | Every candidate lost on train. Best train: momentum lb240 th0.02 (−0.59%), then −1.05% on test |
| Coinbase 1m, 30 d, fee 0.1% | 0 of 44 | none | Top of train (trend_breakout c20, +1.57%) lost on test (−0.80%). The z-score family earned $1–3 before fees on test, but fees took it all |
| Coinbase 1h, 365 d, fee 0.6% (Oct 2025 – Oct 2026) | 0 of 44 | none | No candidate made money in the 8-month train part. Several made money on the 4-month test (ema_cross f60 s240 +0.56%, z-score w300 +0.55%), but that is the luck the split exists to catch |
| Solana DEX 1m, 30 d, fee 0.3% | | | |

Copy replay of the five chosen Hyperliquid traders (run 36962968316). The fee is 0.045% per side. Each copy enters one candle after the trader's fill, unleveraged, at 5% per position:

| Copy replay | Return on $1,000 | Trades | Win | Max DD | Fees |
|---|---|---|---|---|---|
| 30 d, 5m candles | −1.09% (−$10.90) | 71 | 29.6% | 1.60% | $3.19 |
| 30 d, 5m, aggressive | −1.53% (−$15.30) | 79 | 29.1% | 2.34% | $3.54 |
| 7 d, 1m candles | −0.28% (−$2.80) | 26 | 46.2% | 0.78% | $1.19 |

Per trader (30 d, 5m):

| Trader | History covered | Fresh-long signals | Copied entries | P&L |
|---|---|---|---|---|
| 0x0ad9e656… | 29.1 d | 2,135 | 4 | −$0.36 |
| 0xe09726ff… | 29.6 d | 6,122 | 23 | −$1.84 |
| 0x88532735… | 29.2 d | 4,067 | 21 | −$1.86 |
| 0xb69eec8f… | 25.1 d | 2,247 | 10 | −$10.96 |
| 0xec4a6f59… | 12.9 d (10,000-fill limit) | 16,254 | 14 | +$3.85 |

**Verdict: copying these winners did not carry their profit over.** The traders made millions over these months. A long-only, unleveraged copy one candle late lost $10.90 per $1,000 in 30 days. Fees were small ($3.19), so the loss is in the trades themselves, not the costs. Their edge comes from things the copy leaves out: shorts, sizing, leverage, and exits faster than one candle. Only 0xec4a6f59 was positive in both the 30-day and 7-day replays (+$3.85 and +$0.23). It is the fastest trader, so it is also the hardest to copy live. One small positive window is not an edge.

Fewer than 1% of signals became entries: the 5-position cap was usually full. That is why the aggressive profile added only 8 trades.
