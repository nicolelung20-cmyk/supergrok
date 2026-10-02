"""Second-by-second PAPER trading engine for Elevated Associates LLC.

PAPER ONLY. This module contains no order-placement code and never reads API keys.
It polls free public market data, runs strategies against a simulated broker that
charges realistic fees and spread, and writes a ledger so edges can be measured
honestly before any real capital is considered (see ../CHARTER.md, section 2).

Usage:
    python paperbot.py --live --products BTC-USD,ETH-USD,SOL-USD   # poll Coinbase every second
    python paperbot.py --synthetic --ticks 20000                   # offline random-walk run
    python paperbot.py --replay prices.csv                         # CSV rows: ts,product,bid,ask
    python paperbot.py --history 90 --strategies trend_breakout    # 90 days of hourly candles in seconds
    python paperbot.py --history 30 --granularity 60 --strategies liquidity_sweep   # one-minute sweeps
    python paperbot.py --jupiter --products JUP:SOL,JUP:JUP         # Solana DEX quotes (Jupiter), simulated swaps

Outputs (in --out, default ./paper_runs/<timestamp>/):
    ledger.jsonl   every fill, stop and kill-switch event
    summary.json   equity, P&L, fees, win rate, max drawdown, per-strategy stats, gate status

Manual kill-switch: create a file named STOP in the run folder. The bot closes every
position at the last quote, logs it, and exits.

To mirror these paper trades into an Alpaca paper account, run alpaca_paper.py instead.
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
COINBASE_CANDLES = "https://api.exchange.coinbase.com/products/{}/candles?granularity={}&start={}&end={}"


@dataclass
class Tick:
    ts: float
    product: str
    bid: float
    ask: float
    high: float = None   # candle high/low when the tick is a whole candle (history replay); None for quotes
    low: float = None

    @property
    def mid(self):
        return (self.bid + self.ask) / 2


@dataclass
class Config:
    starting_cash: float = 1000.0
    taker_fee: float = 0.006          # crypto taker fee; Coinbase Advanced entry tier is 0.60%
    stock_fee: float = 0.0            # US stocks/ETFs (commission-free brokers)
    dex_fee: float = 0.0003           # Solana network + priority fee on a ~$50 swap; pool fees are already in Jupiter quotes
    slippage_bps: float = 2.0         # extra cost beyond the quoted bid/ask
    # Risk policy (Linear ELE-39): <=5% per position, 3% daily loss halt, <=5 positions, no leverage.
    risk_per_trade: float = 0.05      # fraction of equity allocated per position
    stop_loss: float = 0.02
    take_profit: float = 0.04
    daily_kill_switch: float = 0.03   # pause new entries after -3% on the UTC day
    max_positions: int = 5
    # Paper-to-live gate (CHARTER.md section 2 + Linear ELE-40). Human steps are tracked separately.
    gate_min_days: float = 90.0
    gate_min_trades: int = 30
    gate_max_drawdown: float = 0.10

    def fee(self, product):
        """JUP:<token> is a Solana DEX swap; BTC-USD or BTC/USD is a crypto pair; anything else is a stock/ETF."""
        if product.upper().startswith("JUP:"):
            return self.dex_fee
        return self.taker_fee if ("-" in product or "/" in product) else self.stock_fee


@dataclass
class Position:
    product: str
    strategy: str
    qty: float
    entry: float
    opened: float
    fee_rate: float = 0.0


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


class TrendBreakout(Strategy):
    """Fee-aware trend breakout on bars built from ticks (one strategy, long timeframe).

    Enter long when a bar closes above the highest high of the prior `channel` bars while the
    close is above the slow EMA (trend regime) and the channel's average range is wide enough to
    clear `edge_multiple` round-trip costs. Exit when a bar closes below the lowest low of the
    prior `exit_channel` bars. Fewer, larger-conviction trades, so fees do not eat the edge.
    """
    name = "trend_breakout"

    def __init__(self, bar_ticks=3600, channel=20, exit_channel=10, trend=50,
                 edge_multiple=3.0, round_trip_cost=0.0125):
        super().__init__()
        self.bar_ticks, self.channel, self.exit_channel = bar_ticks, channel, exit_channel
        self.trend_a = 2 / (trend + 1)
        self.edge_multiple, self.round_trip_cost = edge_multiple, round_trip_cost
        self.state = {}

    def signal(self, tick):
        st = self.state.setdefault(tick.product, {
            "n": 0, "hi": tick.mid, "lo": tick.mid, "ema": None,
            "bars": deque(maxlen=max(self.channel, self.exit_channel)), "long": False})
        st["n"] += 1
        st["hi"], st["lo"] = max(st["hi"], tick.mid), min(st["lo"], tick.mid)
        if st["n"] < self.bar_ticks:
            return None
        close, hi, lo = tick.mid, st["hi"], st["lo"]
        st["n"], st["hi"], st["lo"] = 0, close, close
        st["ema"] = close if st["ema"] is None else st["ema"] + self.trend_a * (close - st["ema"])
        bars = list(st["bars"])
        st["bars"].append((hi, lo))
        if len(bars) < self.channel:
            return None
        window = bars[-self.channel:]
        high_n = max(b[0] for b in window)
        avg_range = sum(b[0] - b[1] for b in window) / len(window) / close
        if st["long"]:
            if close < min(b[1] for b in bars[-self.exit_channel:]):
                st["long"] = False
                return "sell"
            return None
        if close > high_n and close > st["ema"] and avg_range * self.channel ** 0.5 >= self.edge_multiple * self.round_trip_cost:
            st["long"] = True
            return "buy"
        return None


class LiquiditySweep(Strategy):
    """Liquidity sweep reversal on short bars (built for one-minute candles).

    A sweep is a bar whose low trades below the lowest low of the prior `lookback` bars (where
    resting sell stops sit) and then closes back above that level. Enter long on the close of the
    sweep bar. Exit when a later bar trades back below the sweep's wick (invalidated), reaches the
    highest high of the lookback (the opposite pool of liquidity), or after `max_hold` bars.

    Long only (spot). Setups are skipped unless the target is at least `edge_multiple` round-trip
    costs away and at least `min_rr` times the distance to the wick, so fees cannot eat the edge.
    Ticks that carry candle high/low are one bar each; plain quotes are grouped `bar_ticks` at a time.
    """
    name = "liquidity_sweep"

    def __init__(self, bar_ticks=60, lookback=30, max_hold=30, edge_multiple=2.0,
                 round_trip_cost=0.0125, min_rr=1.5):
        super().__init__()
        self.bar_ticks, self.lookback, self.max_hold = bar_ticks, lookback, max_hold
        self.edge_multiple, self.round_trip_cost, self.min_rr = edge_multiple, round_trip_cost, min_rr
        self.state = {}

    def _bar(self, st, tick):
        """Return (high, low, close) when a bar completes, else None."""
        if tick.high is not None and tick.low is not None:
            return tick.high, tick.low, tick.mid
        st["n"] += 1
        st["hi"] = tick.mid if st["hi"] is None else max(st["hi"], tick.mid)
        st["lo"] = tick.mid if st["lo"] is None else min(st["lo"], tick.mid)
        if st["n"] < self.bar_ticks:
            return None
        bar = (st["hi"], st["lo"], tick.mid)
        st["n"], st["hi"], st["lo"] = 0, None, None
        return bar

    def signal(self, tick):
        st = self.state.setdefault(tick.product, {
            "n": 0, "hi": None, "lo": None, "bars": deque(maxlen=self.lookback), "trade": None})
        bar = self._bar(st, tick)
        if bar is None:
            return None
        high, low, close = bar
        bars = list(st["bars"])
        st["bars"].append((high, low))
        trade = st["trade"]
        if trade is not None:
            trade["held"] += 1
            if low <= trade["stop"] or high >= trade["target"] or trade["held"] >= self.max_hold:
                st["trade"] = None
                return "sell"
            return None
        if len(bars) < self.lookback:
            return None
        pool_low = min(b[1] for b in bars)
        pool_high = max(b[0] for b in bars)
        if not (low < pool_low < close):
            return None
        reward, risk = (pool_high - close) / close, (close - low) / close
        if reward < self.edge_multiple * self.round_trip_cost or risk <= 0 or reward < self.min_rr * risk:
            return None
        st["trade"] = {"stop": low, "target": pool_high, "held": 0}
        return "buy"


STRATEGIES = {cls.name: cls for cls in (EmaCross, ZScoreReversion, TrendBreakout, LiquiditySweep)}


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
        self.halted = False
        self.first_ts = None
        self.last_ts = None
        self.last_tick = {}
        self.ledger_path = ledger_path

    def log(self, **event):
        if self.ledger_path:
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")

    def equity(self):
        return self.cash + sum(p.qty * self.last_mid.get(p.product, p.entry) for p in self.positions.values())

    def mark(self, tick):
        self.last_mid[tick.product] = tick.mid
        self.last_tick[tick.product] = tick
        self.first_ts = tick.ts if self.first_ts is None else self.first_ts
        self.last_ts = tick.ts
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
        if self.paused or self.halted or key in self.positions or len(self.positions) >= self.cfg.max_positions:
            return None
        notional = self.equity() * self.cfg.risk_per_trade
        if notional > self.cash or notional <= 0:
            return None
        rate = self.cfg.fee(tick.product)
        price = tick.ask * (1 + self._slip())
        fee = notional * rate
        qty = (notional - fee) / price
        self.cash -= notional
        self.fees += fee
        pos = self.positions[key] = Position(tick.product, strategy, qty, price, tick.ts, rate)
        self.log(ts=tick.ts, event="buy", product=tick.product, strategy=strategy,
                 price=round(price, 6), qty=qty, notional=round(notional, 2), fee=round(fee, 4))
        return pos

    def sell(self, tick, strategy, reason="signal"):
        pos = self.positions.pop((tick.product, strategy), None)
        if not pos:
            return None
        price = tick.bid * (1 - self._slip())
        gross = pos.qty * price
        fee = gross * pos.fee_rate
        self.cash += gross - fee
        self.fees += fee
        cost = pos.qty * pos.entry / (1 - pos.fee_rate)
        pnl = gross - fee - cost
        self.closed.append({"strategy": strategy, "pnl": pnl, "held_s": tick.ts - pos.opened})
        self.log(ts=tick.ts, event="sell", reason=reason, product=tick.product, strategy=strategy,
                 price=round(price, 6), fee=round(fee, 4), pnl=round(pnl, 4))
        return pos

    def halt(self, reason="manual_kill"):
        """Close every position at its last quote and stop trading for the rest of the run."""
        for product, strategy in list(self.positions):
            last = self.last_tick.get(product)
            if last is not None:
                self.sell(last, strategy, reason)
        self.halted = True
        self.log(ts=self.last_ts, event="halt", reason=reason, equity=round(self.equity(), 2))

    def check_exits(self, tick):
        for (product, strategy), pos in list(self.positions.items()):
            if product != tick.product:
                continue
            move = tick.bid / pos.entry - 1
            if move <= -self.cfg.stop_loss:
                self.sell(tick, strategy, "stop_loss")
            elif move >= self.cfg.take_profit:
                self.sell(tick, strategy, "take_profit")

    def gate(self):
        """Measured part of the paper-to-live gate. Thesis, LLC account and Nicole's yes are human steps."""
        days = (self.last_ts - self.first_ts) / 86_400 if self.first_ts is not None else 0.0
        net = sum(t["pnl"] for t in self.closed)
        checks = {
            "days_running": round(days, 2) >= self.cfg.gate_min_days,
            "closed_trades": len(self.closed) >= self.cfg.gate_min_trades,
            "net_positive_after_fees": net > 0,
            "max_drawdown": self.max_dd < self.cfg.gate_max_drawdown,
        }
        return {"days_running": round(days, 2), "net_pnl": round(net, 2), "checks": checks,
                "measured_checks_passed": all(checks.values())}

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
            "expectancy": round(sum(t["pnl"] for t in self.closed) / len(self.closed), 4) if self.closed else None,
            "max_drawdown_pct": round(self.max_dd * 100, 3),
            "open_positions": len(self.positions),
            "kill_switch_active": self.paused,
            "halted": self.halted,
            "per_strategy": per,
            "gate": self.gate(),
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


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ea-paperbot/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def coinbase_history_feed(products, days, granularity=3600, end=None, fetch=_get_json, pause=0.0):
    """Replay `days` of public Coinbase candles as ticks at each candle's close.

    The gate measures time from tick timestamps, so 90 days of history replays in seconds.
    Coinbase returns at most 300 candles per request, newest first; rows are merged by time.
    Candles are [time, low, high, open, close, volume]; each tick carries the candle's high and low.
    `pause` seconds between requests keeps long one-minute pulls under the public rate limit.
    """
    end = int(end if end is not None else time.time()) // granularity * granularity
    start = end - int(days * 86_400) - granularity  # one extra candle so first-to-last spans `days`
    rows = []
    for product in products:
        seen = set()
        hi = end
        while hi > start:
            lo = max(start, hi - 300 * granularity)
            iso = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            for c in fetch(COINBASE_CANDLES.format(product, granularity, iso(lo), iso(hi))):
                ts, close = int(c[0]), float(c[4])
                if start <= ts < end and ts not in seen:
                    seen.add(ts)
                    rows.append((ts, product, close, float(c[2]), float(c[1])))
            hi = lo
            if pause:
                time.sleep(pause)
    for ts, product, close, high, low in sorted(rows):
        yield Tick(float(ts), product, close, close, high, low)


def replay_feed(path):
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[0] == "ts":
                continue
            yield Tick(float(row[0]), row[1], float(row[2]), float(row[3]))


# ---------------------------------------------------------------- runner

def run(feed, strategies, broker, summary_path=None, summary_every=60, stop_file=None):
    for i, tick in enumerate(feed, 1):
        broker.mark(tick)
        if stop_file is not None and Path(stop_file).exists():
            broker.halt("manual_kill")
            break
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
    src.add_argument("--jupiter", action="store_true",
                     help="poll Jupiter (Solana DEX) quotes; products like JUP:SOL, JUP:JUP, JUP:<mint>@<decimals>")
    src.add_argument("--history", type=float, metavar="DAYS", help="replay DAYS of public Coinbase candles")
    ap.add_argument("--granularity", type=int, default=3600, choices=(60, 300, 900, 3600, 21600, 86400),
                    help="candle seconds for --history")
    ap.add_argument("--bar-ticks", type=int, default=None,
                    help="ticks per trend_breakout bar (default: one hour of ticks for the chosen feed)")
    ap.add_argument("--gate-min-days", type=float, default=Config.gate_min_days,
                    help="days of paper data the gate requires (measured from tick timestamps)")
    ap.add_argument("--products", default="BTC-USD,ETH-USD,SOL-USD")
    ap.add_argument("--strategies", default=",".join(STRATEGIES))
    ap.add_argument("--interval", type=float, default=None,
                    help="seconds between live polls (default 1; 5 for --jupiter to stay under its free rate limit)")
    ap.add_argument("--ticks", type=int, default=None, help="stop after N polls (live) or N steps (synthetic)")
    ap.add_argument("--fee", type=float, default=Config.taker_fee)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    products = [p.strip() for p in args.products.split(",") if p.strip()]
    if args.interval is None:
        args.interval = 5.0 if args.jupiter else 1.0
    if args.jupiter and args.products == ap.get_default("products"):
        products = ["JUP:SOL"]
    out = Path(args.out or f"paper_runs/{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    out.mkdir(parents=True, exist_ok=True)
    broker = PaperBroker(Config(taker_fee=args.fee, gate_min_days=args.gate_min_days),
                         ledger_path=out / "ledger.jsonl")
    tick_seconds = args.granularity if args.history else args.interval
    bar_ticks = args.bar_ticks or max(1, round(3600 / tick_seconds))
    cfg = broker.cfg
    round_trip = 2 * (cfg.fee(products[0]) + cfg.slippage_bps / 10_000)
    minute_ticks = max(1, round(60 / tick_seconds))
    strategies = []
    for s in (s.strip() for s in args.strategies.split(",")):
        if s == "trend_breakout":
            strategies.append(STRATEGIES[s](bar_ticks=bar_ticks))
        elif s == "liquidity_sweep":
            strategies.append(STRATEGIES[s](bar_ticks=minute_ticks, round_trip_cost=round_trip))
        else:
            strategies.append(STRATEGIES[s]())

    if args.live:
        feed = coinbase_feed(products, args.interval, args.ticks)
    elif args.synthetic:
        feed = synthetic_feed(products, args.ticks or 20_000)
    elif args.history:
        feed = coinbase_history_feed(products, args.history, args.granularity,
                                     pause=0.15 if args.granularity < 900 else 0.0)
    elif args.jupiter:
        from jupiter_feed import jupiter_feed  # imported here: jupiter_feed imports Tick from this module
        notional = broker.cfg.starting_cash * broker.cfg.risk_per_trade
        feed = jupiter_feed(products, notional_usd=notional, interval=args.interval, max_ticks=args.ticks)
    else:
        feed = replay_feed(args.replay)

    try:
        result = run(feed, strategies, broker, summary_path=out / "summary.json", stop_file=out / "STOP")
    except KeyboardInterrupt:
        result = broker.summary()
        (out / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"ledger: {out / 'ledger.jsonl'}")


if __name__ == "__main__":
    main()
