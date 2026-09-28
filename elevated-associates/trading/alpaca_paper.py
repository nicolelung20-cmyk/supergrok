"""Run paperbot's strategies on Alpaca's PAPER account (stocks, ETFs and crypto).

Alpaca PAPER ONLY. The only trading host this module can reach is
paper-api.alpaca.markets; any other base URL raises before a request is made, so
live orders are impossible from this file. Going live is a human decision
(CHARTER.md section 2, Linear ELE-40).

paperbot.PaperBroker stays the source of truth for the scorecard and the gate.
Every simulated entry and exit is mirrored as a market order in the Alpaca paper
account, and the order id is written to the ledger so the two can be reconciled.

Setup (Nicole, one time, free): create an Alpaca paper account, generate paper API
keys and store them as environment variables ALPACA_API_KEY_ID and
ALPACA_API_SECRET_KEY. Never paste keys into chat or commit them.

Usage:
    python3 alpaca_paper.py --products BTC/USD,ETH/USD,SPY --strategies ema_cross
    python3 alpaca_paper.py --check            # verify keys and print the paper account

Stocks and ETFs (e.g. SPY) only get quotes while the US market is open; crypto
trades around the clock. Options are not wired in yet.
"""

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from paperbot import STRATEGIES, Config, PaperBroker, Tick, run

PAPER_BASE = "https://paper-api.alpaca.markets"
DATA_BASE = "https://data.alpaca.markets"
ALPACA_CRYPTO_FEE = 0.0025  # Alpaca crypto taker fee, lowest volume tier; confirm on their fee page


def is_crypto(symbol):
    return "/" in symbol


def _urlopen(req, timeout=10):
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body else {}


class AlpacaPaper:
    """Minimal REST client that can only talk to the Alpaca paper trading host."""

    def __init__(self, key_id=None, secret=None, base=PAPER_BASE, opener=_urlopen):
        if base != PAPER_BASE:
            raise ValueError("alpaca_paper only trades on the paper host: " + PAPER_BASE)
        self.key_id = key_id or os.environ.get("ALPACA_API_KEY_ID")
        self.secret = secret or os.environ.get("ALPACA_API_SECRET_KEY")
        if not self.key_id or not self.secret:
            raise RuntimeError("Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY (paper keys).")
        self.base = base
        self.opener = opener
        self._clock = (0.0, False)

    def _request(self, method, url, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret,
            "Content-Type": "application/json",
            "User-Agent": "ea-paperbot/1.1",
        })
        return self.opener(req)

    def trading(self, method, path, body=None):
        return self._request(method, self.base + path, body)

    def data(self, path, params):
        return self._request("GET", DATA_BASE + path + "?" + urllib.parse.urlencode(params))

    # -- account and market state

    def account(self):
        return self.trading("GET", "/v2/account")

    def market_open(self, max_age=60.0):
        checked, is_open = self._clock
        if time.time() - checked > max_age:
            is_open = bool(self.trading("GET", "/v2/clock").get("is_open"))
            self._clock = (time.time(), is_open)
        return is_open

    # -- orders

    def buy(self, symbol, notional):
        return self.trading("POST", "/v2/orders", {
            "symbol": symbol,
            "notional": f"{notional:.2f}",
            "side": "buy",
            "type": "market",
            "time_in_force": "gtc" if is_crypto(symbol) else "day",
        })

    def close(self, symbol):
        return self.trading("DELETE", "/v2/positions/" + urllib.parse.quote(symbol.replace("/", ""), safe=""))

    # -- quotes

    def latest_quotes(self, symbols):
        ticks = []
        crypto = [s for s in symbols if is_crypto(s)]
        stocks = [s for s in symbols if not is_crypto(s)]
        if crypto:
            q = self.data("/v1beta3/crypto/us/latest/quotes", {"symbols": ",".join(crypto)}).get("quotes", {})
            ticks += _to_ticks(q)
        if stocks and self.market_open():
            q = self.data("/v2/stocks/quotes/latest", {"symbols": ",".join(stocks), "feed": "iex"}).get("quotes", {})
            ticks += _to_ticks(q)
        return ticks


def _to_ticks(quotes):
    now = time.time()
    out = []
    for symbol, q in quotes.items():
        bid, ask = float(q.get("bp") or 0), float(q.get("ap") or 0)
        if bid > 0 and ask >= bid:
            out.append(Tick(now, symbol, bid, ask))
    return out


def alpaca_feed(client, symbols, interval=1.0, max_ticks=None):
    n = 0
    while max_ticks is None or n < max_ticks:
        started = time.time()
        try:
            yield from client.latest_quotes(symbols)
        except Exception as e:  # network hiccup: skip this poll, keep running
            print(f"feed error: {e}")
        n += 1
        time.sleep(max(0.0, interval - (time.time() - started)))


class MirroredBroker(PaperBroker):
    """PaperBroker that also places each entry and exit in the Alpaca paper account."""

    def __init__(self, cfg, client, ledger_path=None):
        super().__init__(cfg, ledger_path)
        self.client = client

    def _mirror(self, tick, action, fn):
        try:
            order = fn()
            self.log(ts=tick.ts, event="alpaca_" + action, product=tick.product,
                     order_id=order.get("id"), status=order.get("status"))
        except Exception as e:  # the simulation keeps running; the gap shows up in the ledger
            self.log(ts=tick.ts, event="alpaca_error", action=action, product=tick.product, error=str(e))

    def buy(self, tick, strategy):
        pos = super().buy(tick, strategy)
        if pos is not None:
            notional = pos.qty * pos.entry / (1 - pos.fee_rate)
            self._mirror(tick, "buy", lambda: self.client.buy(tick.product, notional))
        return pos

    def sell(self, tick, strategy, reason="signal"):
        pos = super().sell(tick, strategy, reason)
        if pos is not None and not any(p == tick.product for p, _ in self.positions):
            self._mirror(tick, "close", lambda: self.client.close(tick.product))
        return pos


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--products", default="BTC/USD,ETH/USD,SOL/USD")
    ap.add_argument("--strategies", default="ema_cross", help="one strategy at a time (ELE-39)")
    ap.add_argument("--interval", type=float, default=1.0, help="seconds between polls")
    ap.add_argument("--ticks", type=int, default=None, help="stop after N polls")
    ap.add_argument("--out", default=None)
    ap.add_argument("--check", action="store_true", help="print the paper account and exit")
    args = ap.parse_args()

    client = AlpacaPaper()
    if args.check:
        acct = client.account()
        print(json.dumps({k: acct.get(k) for k in ("status", "cash", "equity", "buying_power", "crypto_status")}, indent=2))
        return

    symbols = [p.strip() for p in args.products.split(",") if p.strip()]
    out = Path(args.out or f"paper_runs/alpaca-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    out.mkdir(parents=True, exist_ok=True)
    broker = MirroredBroker(Config(taker_fee=ALPACA_CRYPTO_FEE, stock_fee=0.0), client, ledger_path=out / "ledger.jsonl")
    strategies = [STRATEGIES[s.strip()]() for s in args.strategies.split(",")]
    try:
        result = run(alpaca_feed(client, symbols, args.interval, args.ticks), strategies, broker,
                     summary_path=out / "summary.json", stop_file=out / "STOP")
    except KeyboardInterrupt:
        result = broker.summary()
        (out / "summary.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    print(f"ledger: {out / 'ledger.jsonl'}")


if __name__ == "__main__":
    main()
