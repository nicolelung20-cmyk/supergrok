"""Hyperliquid top-trader follower: paper copies of chosen wallets' long entries.

PAPER ONLY. This module calls Hyperliquid's public read-only info API
(api.hyperliquid.xyz/info: userFillsByTime, allMids, candleSnapshot). It has no wallet
and no keys, and it never calls the order endpoint, so it cannot place an order.

Rules (simple on purpose, so the result is easy to judge):
  * Copy only fresh longs on perps: a fill marked "Open Long" that starts from a flat
    position. Adds to an existing position and shorts are ignored (the paper broker is
    long-only and unleveraged, per ELE-39).
  * Exit when that trader starts closing ("Close Long" or "Long > Short"), or earlier at
    the ELE-39 stop (2%) or take-profit (4%).
  * Each trader gets its own strategy name (hl:<first 8 of address>), so summary.json
    shows results per trader. Position size, max open positions and the daily kill switch
    are shared, exactly as for every other paper bot.

"Time is not linear": --replay DAYS downloads the traders' real fills and candles and
replays what copying them would have done, acting on the close of the candle after each
fill (the delay a real follower would have). --live follows them forward in real time.

Usage:
    python hl_copy.py --replay 30                     # default trader list, 5-minute candles
    python hl_copy.py --replay 14 --interval 1m --traders 0xabc...,0xdef...
    python hl_copy.py --live --poll 30
"""

import argparse
import json
import sys
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from paperbot import AGGRESSIVE, Config, PaperBroker, Tick

PAPER_ONLY = True

INFO_URL = "https://api.hyperliquid.xyz/info"
READ_TYPES = {"userFillsByTime", "allMids", "candleSnapshot"}
FILLS_PAGE = 2000          # userFillsByTime returns at most this many fills per call
CANDLES_PAGE = 5000        # candleSnapshot returns at most this many candles per call
INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000}

# Chosen 2026-10-02 from Coinversa Pulse "persistent winners" (profitable in each of the last
# 3 months), keeping wallets whose best month was <= 55% of their 90-day PnL, whose 30-day trend
# was not "declining", and that trade at a pace a follower can copy (< ~120k fills a month).
TOP_TRADERS = [
    "0x0ad9e656d9e6211d0ea1c5462342e1fc94cc4cbf",  # $6.3M / 90d, best month 41%, 42.6% win (30d)
    "0xe09726ff25f5001f37b15049f54116cb83d7d0fe",  # $3.6M / 90d, best month 53%, 34.1% win
    "0x885327357a8d005c9dfb670583899df6e21f8249",  # $1.5M / 90d, best month 43%, 52.6% win
    "0xb69eec8fea0081343c3b09e652ba1fa7dcf7033a",  # $1.3M / 90d, best month 40%, 36.7% win, improving
    "0xec4a6f59960fb55a7fa49262e2628687b322cf62",  # $12.1M / 90d, best month 41%, improving; fast (~114k fills/30d)
]


def info(body, post=None):
    """One read-only call to Hyperliquid's info API."""
    if body.get("type") not in READ_TYPES:
        raise ValueError(f"{body.get('type')} is not a read request this follower may make")
    if post is not None:
        return post(INFO_URL, body)
    import urllib.request
    req = urllib.request.Request(INFO_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "ea-hl-copy/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def fetch_fills(user, start_ms, end_ms, post=None, pause=0.5, sleep=time.sleep):
    """All of `user`'s fills in [start_ms, end_ms], oldest first. Hyperliquid only keeps the
    most recent 10,000 fills per wallet here, so very active wallets cover a shorter span."""
    out, t = [], start_ms
    while t <= end_ms:
        batch = info({"type": "userFillsByTime", "user": user, "startTime": t, "endTime": end_ms}, post) or []
        out += batch
        if len(batch) < FILLS_PAGE:
            break
        t = max(f["time"] for f in batch) + 1
        sleep(pause)
    seen, unique = set(), []
    for f in sorted(out, key=lambda f: f["time"]):
        key = (f.get("hash"), f.get("tid"), f["time"], f["coin"], f.get("sz"))
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def strategy_name(user):
    return f"hl:{user[:10]}"


def signals(user, fills):
    """Copy signals from one trader's fills: list of (ts_seconds, 'buy'|'sell', coin, user)."""
    out = []
    for f in sorted(fills, key=lambda f: f["time"]):
        coin, direction = f["coin"], f.get("dir", "")
        if coin.startswith("@") or "/" in coin:
            continue  # spot pairs: perps only
        flat = abs(float(f.get("startPosition") or 0)) < 1e-12
        if direction == "Open Long" and flat:
            out.append((f["time"] / 1000, "buy", coin, user))
        elif direction in ("Close Long", "Long > Short"):
            out.append((f["time"] / 1000, "sell", coin, user))
    return out


def candles(coin, start_ms, end_ms, interval="5m", post=None, pause=0.5, sleep=time.sleep):
    """Candles for one perp as Ticks stamped at each candle's close (bid = ask = close)."""
    step = INTERVAL_MS[interval]
    ticks, t = [], start_ms
    while t < end_ms:
        hi = min(end_ms, t + step * CANDLES_PAGE)
        rows = info({"type": "candleSnapshot",
                     "req": {"coin": coin, "interval": interval, "startTime": t, "endTime": hi}}, post) or []
        for c in rows:
            close = float(c["c"])
            ticks.append(Tick(int(c["T"]) / 1000, f"HL:{coin}", close, close, float(c["h"]), float(c["l"])))
        t = hi
        sleep(pause)
    dedup = {(k.ts, k.product): k for k in ticks}
    return sorted(dedup.values(), key=lambda k: k.ts)


class Copier:
    """Applies copy signals to a PaperBroker."""

    def __init__(self, broker, log_path=None):
        self.broker, self.log_path = broker, log_path
        self.copied = defaultdict(lambda: {"signals": 0, "entries": 0})

    def _log(self, event):
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")

    def apply(self, signal, tick):
        ts, side, coin, user = signal
        name = strategy_name(user)
        self.copied[user]["signals"] += 1
        self._log({"ts": ts, "acted_ts": tick.ts, "side": side, "coin": coin, "trader": user})
        if side == "buy":
            if self.broker.buy(tick, name):
                self.copied[user]["entries"] += 1
        else:
            self.broker.sell(tick, name, "trader_closed")


def replay(sigs, ticks, broker, copier):
    """Run signals against candle ticks. Each signal acts on the first candle of its coin that
    closes after the fill, so the copy always trades later than the trader did."""
    pending = defaultdict(deque)
    for s in sorted(sigs):
        pending[f"HL:{s[2]}"].append(s)
    for tick in ticks:
        broker.mark(tick)
        broker.check_exits(tick)
        queue = pending.get(tick.product)
        while queue and queue[0][0] < tick.ts:
            copier.apply(queue.popleft(), tick)
    return broker.summary()


def report(summary, copier, coverage):
    lines = ["| Trader | Fills read | History covered | Copy signals | Entries | Closed trades | P&L |",
             "|---|---|---|---|---|---|---|"]
    per = summary["per_strategy"]
    for user, cov in coverage.items():
        s = per.get(strategy_name(user), {"trades": 0, "pnl": 0.0})
        c = copier.copied.get(user, {"signals": 0, "entries": 0})
        lines.append(f"| {user[:10]}… | {cov['fills']} | {cov['days']:.1f} days | {c['signals']} | {c['entries']} | "
                     f"{s['trades']} | ${s['pnl']:+.2f} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Paper copy-trading of Hyperliquid top traders (long entries only).")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replay", type=float, metavar="DAYS", help="replay what copying would have done")
    mode.add_argument("--live", action="store_true", help="follow forward in real time")
    ap.add_argument("--traders", default="", help="comma-separated 0x addresses (default: the chosen top traders)")
    ap.add_argument("--traders-file", help="one address per line (# comments allowed)")
    ap.add_argument("--interval", default="5m", choices=sorted(INTERVAL_MS), help="replay candle size")
    ap.add_argument("--poll", type=float, default=30.0, help="seconds between polls in --live")
    ap.add_argument("--polls", type=int, default=None, help="stop --live after N polls")
    ap.add_argument("--fee", type=float, default=Config.hl_fee, help="fee per trade for HL: copies")
    ap.add_argument("--aggressive", action="store_true", help="opt-in profile: up to 10 open positions")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    traders = [t.strip().lower() for t in args.traders.split(",") if t.strip()]
    if args.traders_file:
        for line in Path(args.traders_file).read_text().splitlines():
            line = line.split("#", 1)[0].strip().lower()
            if line:
                traders.append(line)
    traders = traders or list(TOP_TRADERS)

    out = Path(args.out or f"paper_runs/hl-copy-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    out.mkdir(parents=True, exist_ok=True)
    cfg = Config(hl_fee=args.fee, **(AGGRESSIVE if args.aggressive else {}))
    broker = PaperBroker(cfg, ledger_path=out / "ledger.jsonl")
    copier = Copier(broker, log_path=out / "copied.jsonl")

    if args.replay:
        end_ms = int(time.time() * 1000)
        start_ms = end_ms - int(args.replay * 86_400_000)
        sigs, coverage = [], {}
        for user in traders:
            fills = fetch_fills(user, start_ms, end_ms)
            span = (fills[-1]["time"] - fills[0]["time"]) / 86_400_000 if fills else 0.0
            coverage[user] = {"fills": len(fills), "days": span}
            sigs += signals(user, fills)
            print(f"{user}: {len(fills)} fills over {span:.1f} days", file=sys.stderr)
        coins = sorted({s[2] for s in sigs if s[1] == "buy"})
        ticks = []
        for coin in coins:
            ticks += candles(coin, start_ms, end_ms, args.interval)
        ticks.sort(key=lambda k: k.ts)
        summary = replay(sigs, ticks, broker, copier)
        summary["traders"] = coverage
        md = (f"# Hyperliquid copy replay · {args.replay:g} days · {args.interval} candles · profile {cfg.profile}\n\n"
              f"Return {summary['return_pct']:+.2f}% on ${cfg.starting_cash:,.0f} · {summary['closed_trades']} trades · "
              f"win {summary['win_rate_pct']}% · max DD {summary['max_drawdown_pct']}% · fees ${summary['fees_paid']}\n\n"
              + report(summary, copier, coverage) + "\n")
        (out / "report.md").write_text(md)
        (out / "summary.json").write_text(json.dumps(summary, indent=2))
        print(md)
        return

    print(f"hl_copy: following {len(traders)} trader(s), paper only. Output: {out} (stop: touch {out / 'STOP'})")
    last_ms = {u: int(time.time() * 1000) for u in traders}
    n = 0
    try:
        while args.polls is None or n < args.polls:
            started = time.time()
            if (out / "STOP").exists():
                broker.halt("manual_kill")
                break
            try:
                now_ms = int(time.time() * 1000)
                sigs = []
                for user in traders:
                    fills = fetch_fills(user, last_ms[user], now_ms)
                    if fills:
                        last_ms[user] = fills[-1]["time"] + 1
                    sigs += signals(user, fills)
                mids = info({"type": "allMids"})
                now = time.time()
                coins = {p.split(":", 1)[1] for p, _ in broker.positions} | {s[2] for s in sigs}
                ticks = {c: Tick(now, f"HL:{c}", float(mids[c]), float(mids[c])) for c in coins if c in mids}
                for t in ticks.values():
                    broker.mark(t)
                    broker.check_exits(t)
                for s in sorted(sigs):
                    if s[2] in ticks:
                        copier.apply(s, ticks[s[2]])
            except Exception as err:  # API hiccup: keep running
                print(f"hl_copy poll error: {err}", file=sys.stderr)
            (out / "summary.json").write_text(json.dumps(broker.summary(), indent=2))
            n += 1
            time.sleep(max(0.0, args.poll - (time.time() - started)))
    except KeyboardInterrupt:
        pass
    (out / "summary.json").write_text(json.dumps(broker.summary(), indent=2))
    print(json.dumps(broker.summary(), indent=2))


if __name__ == "__main__":
    main()
