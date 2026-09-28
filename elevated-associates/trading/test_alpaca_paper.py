import json
import unittest

import alpaca_paper
from alpaca_paper import PAPER_BASE, AlpacaPaper, MirroredBroker, _to_ticks
from paperbot import Config, Tick


class FakeOpener:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    def __call__(self, req):
        body = json.loads(req.data) if req.data else None
        self.calls.append((req.get_method(), req.full_url, body, dict(req.header_items())))
        for key, resp in self.responses.items():
            if key in req.full_url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return {"id": "ord-1", "status": "accepted"}


def client(opener=None):
    return AlpacaPaper("k", "s", opener=opener or FakeOpener())


class ClientTest(unittest.TestCase):
    def test_refuses_any_host_but_paper(self):
        with self.assertRaises(ValueError):
            AlpacaPaper("k", "s", base="https://api.alpaca.markets")

    def test_requires_keys(self):
        import os
        saved = {k: os.environ.pop(k, None) for k in ("ALPACA_API_KEY_ID", "ALPACA_API_SECRET_KEY")}
        try:
            with self.assertRaises(RuntimeError):
                AlpacaPaper()
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_crypto_buy_is_notional_gtc_on_paper_host(self):
        o = FakeOpener()
        client(o).buy("BTC/USD", 50)
        method, url, body, headers = o.calls[0]
        self.assertEqual((method, url), ("POST", PAPER_BASE + "/v2/orders"))
        self.assertEqual(body, {"symbol": "BTC/USD", "notional": "50.00", "side": "buy",
                                "type": "market", "time_in_force": "gtc"})
        self.assertEqual(headers["Apca-api-key-id"], "k")

    def test_stock_buy_is_day_order_and_close_strips_slash(self):
        o = FakeOpener()
        c = client(o)
        c.buy("SPY", 25)
        c.close("BTC/USD")
        self.assertEqual(o.calls[0][2]["time_in_force"], "day")
        self.assertEqual(o.calls[1][:2], ("DELETE", PAPER_BASE + "/v2/positions/BTCUSD"))

    def test_quotes_skip_stocks_when_market_closed_and_drop_bad_quotes(self):
        o = FakeOpener({
            "/v2/clock": {"is_open": False},
            "crypto/us/latest/quotes": {"quotes": {"BTC/USD": {"bp": 100, "ap": 101},
                                                   "ETH/USD": {"bp": 0, "ap": 5}}},
        })
        ticks = client(o).latest_quotes(["BTC/USD", "ETH/USD", "SPY"])
        self.assertEqual([t.product for t in ticks], ["BTC/USD"])
        self.assertFalse(any("stocks/quotes" in c[1] for c in o.calls))

    def test_to_ticks_rejects_crossed_quotes(self):
        self.assertEqual(_to_ticks({"X": {"bp": 10, "ap": 9}}), [])


class MirrorTest(unittest.TestCase):
    def test_entry_and_exit_are_mirrored_with_order_ids(self):
        o = FakeOpener()
        b = MirroredBroker(Config(slippage_bps=0, taker_fee=0.0025), client(o))
        events = []
        b.log = lambda **e: events.append(e)
        t = Tick(0, "BTC/USD", 100, 100)
        b.mark(t)
        b.buy(t, "ema_cross")
        b.sell(t, "ema_cross")
        self.assertEqual([c[0] for c in o.calls], ["POST", "DELETE"])
        self.assertAlmostEqual(float(o.calls[0][2]["notional"]), 50.0, places=2)
        self.assertIn("alpaca_buy", [e["event"] for e in events])
        self.assertIn("alpaca_close", [e["event"] for e in events])

    def test_broker_error_is_logged_and_simulation_continues(self):
        o = FakeOpener({"/v2/orders": RuntimeError("boom")})
        b = MirroredBroker(Config(slippage_bps=0), client(o))
        events = []
        b.log = lambda **e: events.append(e)
        t = Tick(0, "BTC/USD", 100, 100)
        b.mark(t)
        self.assertIsNotNone(b.buy(t, "s"))
        self.assertEqual(events[-1]["event"], "alpaca_error")

    def test_halt_closes_alpaca_positions(self):
        o = FakeOpener()
        b = MirroredBroker(Config(slippage_bps=0), client(o))
        t = Tick(0, "BTC/USD", 100, 100)
        b.mark(t)
        b.buy(t, "s")
        b.halt()
        self.assertEqual(o.calls[-1][0], "DELETE")


class SafetyTest(unittest.TestCase):
    def test_no_live_host_anywhere(self):
        import inspect
        src = inspect.getsource(alpaca_paper)
        self.assertNotIn("://api.alpaca.markets", src)
        self.assertEqual(alpaca_paper.PAPER_BASE, "https://paper-api.alpaca.markets")


if __name__ == "__main__":
    unittest.main()
