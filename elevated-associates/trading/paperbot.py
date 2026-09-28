"""Second-by-second PAPER trading engine for Elevated Associates LLC.

PAPER ONLY. This module contains no order-placement code and never reads API keys.
It polls free public market data, runs strategies against a simulated broker that
charges realistic fees and spread, and writes a ledger so edges can be measured
honestly before any real capital is considered (see ../CHARTER.md, section 2).

Usage:
    python paperbot.py --live --products BTC-USD,ETH-USD,SOL-USD   # poll Coinbase every second
    python paperbot.py --synthetic --ticks 20000                   # offline random-walk run
    python paperbot.py --replay prices.csv                         # CSV rows: ts,product,bid,ask

Outputs (in --out, default ./paper_runs/<timestamp>/):
    ledger.jsonl   every fill, stop and kill-switch event
    summary.json   equity, P&L, fees, win rate, max drawdown, per-strategy stats
"""

import argparse
import csv
import json
import math
import random
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PAPER_ONLY = True

COINBASE_TICKER = "https://api.exchange.coinbase.com/products/{}/ticker"


@dataclass
class Tick:
    ts: float
    product: str
    bid: float
    ask: float

    @property
    def mid(self):
        return (self.bid + self.ask) / 2


@dataclass
class Config:
    starting_cash: float = 1000.0
    taker_fee: float = 0.006          # Coinbase Advanced entry tier taker fee (0.60%)
    slippage_bps: float = 2.0         # extra cost beyond the quoted bid/ask
    risk_per_trade: float = 0.10      # fraction of equity allocated per position
    stop_loss: float = 0.02
    take_profit: float = 0.04
    daily_kill_switch: float = 0.05   # pause new entries after -5% on the UTC day
    max_positions: int = 3


@dataclass
class Position:
    product: str
    strategy: str
    qty: float
    entry: float
    opened: float


# ---------------------------------------------------------------- strategies

class Strategy:
    name = "base"

    def __init__(self):
        self.history = {}

    def prices(self, product, maxlen):
        return self.history.setdefault(product, deque(maxlen=maxlen))

    def signal(self, tick):
        """Return 'buy', 'sell' or None."""
        raise NotImplementedError


class EmaCross(Strategy):
    """Fast/slow EMA crossover on mid price (trend following)."""
    name = "ema_cross"

    def __init__(self, fast=30, slow=120):
        super().__init__()
        self.fast_a, self.slow_a = 2 / (fast + 1), 2 / (slow + 1)
        self.state = {}
        self.warmup = slow

    def signal(self, tick):
        st = self.state.setdefault(tick.product, {"f": tick.mid, "s": tick.mid, "n": 0, "above": None})
        st["f"] += self.fast_a * (tick.mid - st["f"])
        st["s"] += self.slow_a * (tick.mid - st["s"])
        st["n"] += 1
        if st["n"] < self.warmup:
            return None
        above = st["f"] > st["s"]
        prev, st["above"] = st["above"], above
        if prev is None or prev == above:
            return None
        return "buy" if above else "sell"


class ZScoreReversion(Strategy):
    """Buy when price is stretched far below its rolling mean; exit on reversion."""
    name = "zscore_reversion"

    def __init__(self, window=300, entry_z=-2.5, exit_z=0.0):
        super().__init__()
        self.window, self.entry_z, self.exit_z = window, entry_z, exit_z

    def signal(self, tick):
        h = self.prices(tick.product, self.window)
        h.append(tick.mid)
        if len(h) < self.window:
            return None
        mean = sum(h) / len(h)
        sd = math.sqrt(sum((p - mean) ** 2 for p in h) / len(h))
        if sd == 0:
            return None
        z = (tick.mid - mean) / sd
        if z <= self.entry_z:
            return "buy"
        if z >= self.exit_z:
            return "sell"
        return None


STRATEGIES = {cls.name: cls for cls in (EmaCross, ZScoreReversion)}


# ---------------------------------------------------------------- broker

class PaperBroker:
    """Simulated spot broker: buys at ask, sells at bid, plus slippage and taker fee."""

    def __init__(self, cfg, ledger_path=None):
        self.cfg = cfg
        self.cash = cfg.starting_cash
        self.positions = {}
        self.last_mid = {}
        self.fees = 0.0
        self.closed = []
        self.peak = cfg.starting_cash
        self.max_dd = 0.0
        self.day = None
        self.day_start_equity = cfg.starting_cash
        self.paused = False
        self.ledger_path = ledger_path

    def log(self, **event):
        if self.ledger_path:
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")

    def equity(self):
        return self.cash + sum(p.qty * self.last_mid.get(p.product, p.entry) for p in self.positions.values())

    def mark(self, tick):
        self.last_mid[tick.product] = tick.mid
        day = datetime.fromtimestamp(tick.ts, timezone.utc).date()
        eq = self.equity()
        if day != self.day:
            self.day, self.day_start_equity, self.paused = day, eq, False
        if not self.paused and eq <= self.day_start_equity * (1 - self.cfg.daily_kill_switch):
            self.paused = True
            self.log(ts=tick.ts, event="kill_switch", equity=round(eq, 2))
        self.peak = max(self.peak, eq)
        self.max_dd = max(self.max_dd, (self.peak - eq) / self.peak)

    def _slip(self):
        return self.cfg.slippage_bps / 10_000

    def buy(self, tick, strategy):
        key = (tick.product, strategy)
        if self.paused or key in self.positions or len(self.positions) >= self.cfg.max_positions:
            return
        notional = self.equity() * self.cfg.risk_per_trade
        if notional > self.cash or notional <= 0:
            return
        price = tick.ask * (1 + self._slip())
        fee = notional * self.cfg.taker_fee
        qty = (notional - fee) / price
        self.cash -= notional
        self.fees += fee
        self.positions[key] = Position(tick.product, strategy, qty, price, tick.ts)
        self.log(ts=tick.ts, event="buy", product=tick.product, strategy=strategy,
                 price=round(price, 6), qty=qty, fee=round(fee, 4))

    def sell(self, tick, strategy, reason="signal"):
        pos = self.positions.pop((tick.product, strategy), None)
        if not pos:
            return
        price = tick.bid * (1 - self._slip())
        gross = pos.qty * price
        fee = gross * self.cfg.taker_fee
        self.cash += gross - fee
        self.fees += fee
        cost = pos.qty * pos.entry / (1 - self.cfg.taker_fee)
        pnl = gross - fee - cost
        self.closed.append({"strategy": strategy, "pnl": pnl, "held_s": tick.ts - pos.opened})
        self.log(ts=tick.ts, event="sell", reason=reason, product=tick.product, strategy=strategy,
                 price=round(price, 6), fee=round(fee, 4), pnl=round(pnl, 4))

    def check_exits(self, tick):
        for (product, strategy), pos in list(self.positions.items()):
            if product != tick.product:
                continue
            move = tick.bid / pos.entry - 1
            if move <= -self.cfg.stop_loss:
                self.sell(tick, strategy, "stop_loss")
            elif move >= self.cfg.take_profit:
                self.sell(tick, strategy, "take_profit")

    def summary(self):
        wins = [t for t in self.closed if t["pnl"] > 0]
        per = {}
        for t in self.closed:
            s = per.setdefault(t["strategy"], {"trades": 0, "pnl": 0.0, "wins": 0})
            s["trades"] += 1
            s["pnl"] = round(s["pnl"] + t["pnl"], 4)
            s["wins"] += t["pnl"] > 0
        eq = self.equity()
        return {
            "paper_only": PAPER_ONLY,
            "starting_cash": self.cfg.starting_cash,
            "equity": round(eq, 2),
            "return_pct": round((eq / self.cfg.starting_cash - 1) * 100, 3),
            "fees_paid": round(self.fees, 2),
            "closed_trades": len(self.closed),
            "win_rate_pct": round(100 * len(wins) / len(self.closed), 1) if self.closed else None,
            "max_drawdown_pct": round(self.max_dd * 100, 3),
            "open_positions": len(self.positions),
            "kill_switch_active": self.paused,
            "per_strategy": per,
        }


# ---------------------------------------------------------------- feeds

def coinbase_feed(products, interval=1.0, max_ticks=None):
    n = 0
    while max_ticks is None or n < max_ticks:
        started = time.time()
        for product in products:
            try:
                req = urllib.request.Request(COINBASE_TICKER.format(product), headers={"User-Agent": "ea-paperbot/1.0"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    d = json.load(r)
                yield Tick(time.time(), product, float(d["bid"]), float(d["ask"]))
            except Exception as e:  # network hiccup: skip this tick, keep running
                print(f"feed error {product}: {e}")
        n += 1
        time.sleep(max(0.0, interval - (time.time() - started)))


def synthetic_feed(products, ticks, seed=7, vol=0.0008, spread_bps=1.0):
    rng = random.Random(seed)
    prices = {p: 100.0 * (i + 1) for i, p in enumerate(products)}
    t0 = time.time()
    for i in range(ticks):
        for p in products:
            prices[p] *= math.exp(rng.gauss(0, vol))
            half = prices[p] * spread_bps / 20_000
            yield Tick(t0 + i, p, prices[p] - half, prices[p] + half)


def replay_feed(path):
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0] == "ts":
                continue
            yield Tick(float(row[0]), row[1], float(row[2]), float(row[3]))


# ---------------------------------------------------------------- runner

def run(feed, strategies, broker, summary_path=None, summary_every=60):
    for i, tick in enumerate(feed, 1):
        broker.mark(tick)
        broker.check_exits(tick)
        for strat in strategies:
            sig = strat.signal(tick)
            if sig == "buy":
                broker.buy(tick, strat.name)
            elif sig == "sell":
                broker.sell(tick, strat.name)
        if summary_path and i % summary_every == 0:
            summary_path.write_text(json.dumps(broker.summary(), indent=2))
    if summary_path:
        summary_path.write_text(json.dumps(broker.summary(), indent=2))
    return broker.summary()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--live", action="store_true", help="poll Coinbase public tickers")
    src.add_argument("--synthetic", action="store_true", help="offline random walk")
    src.add_argument("--replay", metavar="CSV", help="replay ts,product,bid,ask rows")
    ap.add_argument("--products", default="BTC-USD,ETH-USD,SOL-USD")
    ap.add_argument("--strategies", default=",".join(STRATEGIES))
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between live polls")
    ap.add_argument("--ticks", type=int, default=None, help="stop after N polls (live) or N steps (synthetic)")
    ap.add_argument("--fee", type=float, default=Config.taker_fee)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    products = [p.strip() for p in args.products.split(",") if p.strip()]
    out = Path(args.out or f"paper_runs/{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    out.mkdir(parents=True, exist_ok=True)
    broker = PaperBroker(Config(taker_fee=args.fee), ledger_path=out / "ledger.jsonl")
    strategies = [STRATEGIES[s.strip()]() for s in args.strategies.split(",")]

    if args.live:
        feed = coinbase_feed(products, args.interval, args.ticks)
    elif args.synthetic:
        feed = synthetic_feed(products, args.ticks or 20_000)
    else:
        feed = replay_feed(args.replay)

    try:
        result = run(feed, strategies, broker, summary_path=out / "summary.json")
    except KeyboardInterrupt:
        result = broker.summary()
        (out / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"ledger: {out / 'ledger.jsonl'}")


if __name__ == "__main__":
    main()
