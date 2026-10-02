"""Strategy tournament: many strategies and settings, replayed in parallel, judged out of sample.

PAPER ONLY. Uses paperbot's simulated broker; nothing here can place an order.

"Time is not linear": price history is downloaded once and replayed as many times as
needed, so months of market time are tested in minutes, for every candidate at once.

Honest scoring (walk-forward):
  * The history is split by time: the first `--train` share (default 2/3) is used to
    pick settings, the rest is the out-of-sample test the winner never saw.
  * Each candidate runs on both parts with a fresh $1,000 paper account.
  * Candidates are ranked by their TRAIN score (return minus half the max drawdown,
    needing --min-trades trades). The leaderboard then shows each one's TEST result.
    With many candidates, the best train score is partly luck; the test column is the
    number to believe, and "robust" marks candidates positive in both parts.

Usage:
    python tournament.py --history 30 --granularity 60 --products BTC-USD,ETH-USD --fee 0.001
    python tournament.py --dex-history 30 --products JUP:SOL,JUP:BONK --dex-fee 0.003
    python tournament.py --replay ticks.csv            # reuse a saved download
Outputs leaderboard.json and leaderboard.md in --out, plus ticks.csv (the download).
"""

import argparse
import itertools
import json
import os
from datetime import datetime, timezone
from multiprocessing import Pool
from pathlib import Path

import paperbot
from paperbot import AGGRESSIVE, STRATEGIES, Config, PaperBroker, run

PAPER_ONLY = True

_TICKS = []  # shared with worker processes (fork)


def grid(minute_ticks, round_trip, hour_ticks=None):
    """Candidate (label, strategy name, kwargs). Each family covers a small, sensible range."""
    hour_ticks = hour_ticks or minute_ticks * 60
    c = []
    for fast, slow in ((10, 40), (20, 80), (30, 120), (60, 240)):
        c.append((f"ema_cross f{fast} s{slow}", "ema_cross", {"fast": fast, "slow": slow}))
    for window, z in itertools.product((120, 300, 600), (-2.0, -2.5, -3.0)):
        c.append((f"zscore w{window} z{z}", "zscore_reversion", {"window": window, "entry_z": z}))
    for channel in (10, 20, 40):
        c.append((f"trend_breakout c{channel}", "trend_breakout",
                  {"bar_ticks": hour_ticks, "channel": channel, "exit_channel": max(5, channel // 2),
                   "round_trip_cost": round_trip}))
    for period, lo, hi in ((14, 25, 55), (14, 20, 50), (7, 20, 60)):
        c.append((f"rsi p{period} {lo}/{hi}", "rsi_reversion",
                  {"period": period, "buy_below": lo, "sell_above": hi, "bar_ticks": minute_ticks}))
    for lookback, th in itertools.product((30, 60, 240), (0.005, 0.01, 0.02)):
        c.append((f"momentum lb{lookback} th{th}", "momentum",
                  {"lookback": lookback, "threshold": th, "max_hold": lookback * 2, "bar_ticks": minute_ticks}))
    base = {"bar_ticks": minute_ticks, "round_trip_cost": round_trip}
    for lookback, buf, trail in itertools.product((30, 240), (0.0, 0.5), (0, 15)):
        c.append((f"sweep lb{lookback} buf{buf} trail{trail}", "liquidity_sweep",
                  dict(base, lookback=lookback, max_hold=max(30, lookback), stop_buffer=buf, trail=trail)))
    for lookback, touches, trail in itertools.product((120, 240), (2, 3), (0, 15)):
        c.append((f"magnet lb{lookback} t{touches} trail{trail}", "liquidity_magnet",
                  dict(base, lookback=lookback, touches=touches, stop_buffer=0.5, trail=trail)))
    return c


def score(summary):
    return summary["return_pct"] - 0.5 * summary["max_drawdown_pct"]


def _run_one(job):
    label, name, kwargs, lo, hi, cfg_kwargs = job
    broker = PaperBroker(Config(**cfg_kwargs))
    s = run(iter(_TICKS[lo:hi]), [STRATEGIES[name](**kwargs)], broker)
    return {"label": label, "strategy": name, "return_pct": s["return_pct"], "max_dd_pct": s["max_drawdown_pct"],
            "trades": s["closed_trades"], "win_rate_pct": s["win_rate_pct"], "fees": s["fees_paid"],
            "pre_fee_pnl": round(s["gate"]["net_pnl"] + s["fees_paid"], 2), "score": round(score(s), 3)}


def tournament(ticks, candidates, cfg_kwargs, train=2 / 3, min_trades=10, processes=None):
    """Run every candidate on the train and test parts. Returns rows sorted by train score."""
    global _TICKS
    _TICKS = ticks
    split = int(len(ticks) * train)
    jobs = []
    for label, name, kwargs in candidates:
        jobs.append((label, name, kwargs, 0, split, cfg_kwargs))
        jobs.append((label, name, kwargs, split, len(ticks), cfg_kwargs))
    if processes == 1:
        results = [_run_one(j) for j in jobs]
    else:
        with Pool(processes or os.cpu_count()) as pool:
            results = pool.map(_run_one, jobs, chunksize=1)
    rows = []
    for i in range(0, len(results), 2):
        tr, te = results[i], results[i + 1]
        rows.append({"label": tr["label"], "strategy": tr["strategy"],
                     "train": {k: tr[k] for k in tr if k not in ("label", "strategy")},
                     "test": {k: te[k] for k in te if k not in ("label", "strategy")},
                     "eligible": tr["trades"] >= min_trades,
                     "robust": tr["return_pct"] > 0 and te["return_pct"] > 0 and tr["trades"] >= min_trades})
    rows.sort(key=lambda r: (r["eligible"], r["train"]["score"]), reverse=True)
    return rows, split


def markdown(rows, meta, top=15):
    lines = [f"# Strategy tournament ({meta['source']})", "",
             f"{meta['ticks']} ticks · train {meta['train_span']} · test {meta['test_span']} · fee {meta['fee']} · "
             f"profile {meta['profile']} · {len(rows)} candidates", "",
             "Ranked by train score (return − ½ max drawdown). **The test columns are out of sample.**", "",
             "| # | Candidate | Train return | Train trades | Test return | Test DD | Test trades | Test pre-fee P&L | Robust |",
             "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows[:top], 1):
        tr, te = r["train"], r["test"]
        lines.append(f"| {i} | {r['label']} | {tr['return_pct']:+.2f}% | {tr['trades']} | {te['return_pct']:+.2f}% | "
                     f"{te['max_dd_pct']:.2f}% | {te['trades']} | ${te['pre_fee_pnl']:+.2f} | "
                     f"{'yes' if r['robust'] else 'no'} |")
    robust = [r for r in rows if r["robust"]]
    lines += ["", f"Robust candidates (positive in train and test): {len(robust)} of {len(rows)}."]
    if robust:
        best = max(robust, key=lambda r: r["test"]["return_pct"])
        lines.append(f"Best robust by test return: **{best['label']}** ({best['test']['return_pct']:+.2f}% test, "
                     f"{best['test']['trades']} trades). One window is not proof; confirm on other periods "
                     "before any forward paper run.")
    else:
        lines.append("No candidate made money in both parts. Nothing here has an edge yet.")
    return "\n".join(lines) + "\n"


def span(ticks):
    if not ticks:
        return "empty"
    f = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    return f"{f(ticks[0].ts)} → {f(ticks[-1].ts)}"


def main():
    ap = argparse.ArgumentParser(description="Paper strategy tournament with out-of-sample scoring.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--history", type=float, metavar="DAYS", help="Coinbase candles")
    src.add_argument("--dex-history", type=float, metavar="DAYS", help="Solana DEX one-minute candles")
    src.add_argument("--replay", metavar="CSV", help="saved ticks (from an earlier --out)")
    src.add_argument("--synthetic", type=int, metavar="TICKS", help="offline random walk (for checks)")
    ap.add_argument("--granularity", type=int, default=60, choices=(60, 300, 900, 3600))
    ap.add_argument("--products", default="BTC-USD,ETH-USD,SOL-USD")
    ap.add_argument("--fee", type=float, default=Config.taker_fee)
    ap.add_argument("--dex-fee", type=float, default=Config.dex_fee)
    ap.add_argument("--aggressive", action="store_true")
    ap.add_argument("--train", type=float, default=2 / 3, help="share of history used to pick settings")
    ap.add_argument("--min-trades", type=int, default=10)
    ap.add_argument("--processes", type=int, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    products = [p.strip() for p in args.products.split(",") if p.strip()]
    out = Path(args.out or f"paper_runs/tournament-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    out.mkdir(parents=True, exist_ok=True)
    if args.history:
        feed, source = paperbot.coinbase_history_feed(products, args.history, args.granularity,
                                                      pause=0.15 if args.granularity < 900 else 0.0), "Coinbase"
        tick_seconds = args.granularity
    elif args.dex_history:
        from jupiter_feed import dex_history_feed
        feed, source, tick_seconds = dex_history_feed(products, args.dex_history), "Solana DEX", 60
    elif args.replay:
        feed, source, tick_seconds = paperbot.replay_feed(args.replay), f"replay {args.replay}", args.granularity
    else:
        feed, source, tick_seconds = paperbot.synthetic_feed(products, args.synthetic), "synthetic", 1
    ticks = list(feed)
    if not args.replay:
        paperbot.write_ticks(ticks, out / "ticks.csv")

    cfg_kwargs = dict(taker_fee=args.fee, dex_fee=args.dex_fee, **(AGGRESSIVE if args.aggressive else {}))
    cfg = Config(**cfg_kwargs)
    round_trip = 2 * (cfg.fee(products[0]) + cfg.slippage_bps / 10_000)
    minute_ticks = max(1, round(60 / tick_seconds))
    hour_ticks = max(1, round(3600 / tick_seconds))
    rows, split = tournament(ticks, grid(minute_ticks, round_trip, hour_ticks), cfg_kwargs, args.train, args.min_trades,
                             args.processes)
    meta = {"source": source, "products": products, "ticks": len(ticks), "train_span": span(ticks[:split]),
            "test_span": span(ticks[split:]), "fee": cfg.fee(products[0]), "profile": cfg.profile,
            "paper_only": PAPER_ONLY}
    (out / "leaderboard.json").write_text(json.dumps({"meta": meta, "rows": rows}, indent=2))
    md = markdown(rows, meta)
    (out / "leaderboard.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
