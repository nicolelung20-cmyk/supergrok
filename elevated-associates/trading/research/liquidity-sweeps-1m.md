# Liquidity sweeps on one-minute charts

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
| 90 days | 0.6% | pending | | | | | |
| 90 days | 0.1% | pending | | | | | |

What it says:

- **At Coinbase's fee the cost filter does its job.** Only 9 setups qualified in 30 days, so losses stayed small, but there were too few trades to judge.
- **At the low fee it trades constantly and loses.** Before fees the 1,277 trades were still slightly negative (about −$21), so there is no raw edge yet; fees then made it −14%.
- **The stop is the problem.** A 13% win rate means price almost always comes back to the wick. With the stop exactly at the wick, ordinary one-minute noise takes it out before the move to the opposite pool.

### Round 2: follow the liquidity (running)

Four variants on seven liquid coins (BTC, ETH, SOL, XRP, DOGE, AVAX, LINK), 30 and 90 days, both fees:

| Variant | Change | Why |
|---|---|---|
| baseline | as round 1 | control |
| buffer | stop 0.5 average bar ranges below the wick | survive retests of the wick |
| big-pools | 4-hour pools (240 bars), buffered stop | bigger targets, fewer but stronger levels |
| follow | big pools, then trail the stop under the last 15 bars' lows after the target | let winners run to the next pool |

More coins means more setups ("more trades"); the pool size and trailing aim at larger gains per trade. The broker's 4% take-profit and 2% stop (ELE-39) still cap every trade; changing those is Nicole's call.

## Next ideas (one at a time, after round 2)

1. Keep only a variant that holds up in **both** the 30-day and 90-day windows at the low fee.
2. Volume filter: real stop runs print above-average volume on the sweep bar.
3. Prior-day high/low as the pool instead of a rolling window.
4. Forward paper test on the Jupiter feed for the survivor.
