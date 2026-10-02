# Liquidity sweeps on one-minute charts

Paper research for Elevated Associates LLC. Nothing here places real orders; results come from the paper broker in `paperbot.py`.

## The idea

Stop-loss orders cluster just below obvious lows (and above obvious highs). When price trades through such a level, those stops fire as market sells, which briefly adds selling and then often runs out of sellers. A **liquidity sweep** is that move: a wick below a pool of lows that closes back above it. The thesis is that the close back above shows the sell-side liquidity was absorbed, so price tends to travel toward the opposite pool, the recent highs where buy stops sit.

## Rules as coded (`LiquiditySweep`, long only, spot)

| Step | Rule (defaults) |
|---|---|
| Liquidity pool | Lowest low and highest high of the prior `lookback` = 30 one-minute bars |
| Sweep | Current bar's low is below the pool low **and** it closes back above the pool low |
| Entry | Buy at the close of the sweep bar |
| Invalidation | Sell when a later bar trades back down to the sweep's wick low |
| Target | Sell when a later bar reaches the pool high (the opposite liquidity) |
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

Filled in from the `sweep_1m` workflow runs (fee-adjusted P&L, win rate, max drawdown, gate status).

| Window | Fee | Trades | Win rate | Return | Max DD | Gate |
|---|---|---|---|---|---|---|
| 30 days | 0.6% | pending | | | | |
| 30 days | 0.1% | pending | | | | |
| 90 days | 0.6% | pending | | | | |
| 90 days | 0.1% | pending | | | | |

## Next ideas (one at a time)

1. Mirror for shorts is not possible on spot; instead test the same rules on the sell side as an *exit* signal for longs.
2. Require the sweep to happen at a higher-timeframe level (for example the prior day's low) instead of any 30-bar low.
3. Add a volume condition: real stop runs print above-average volume on the sweep bar.
4. Vary `lookback` (15, 30, 60) and keep only settings that hold up in both windows.
