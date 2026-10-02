import inspect
import unittest

import hl_copy
from hl_copy import Copier, candles, fetch_fills, replay, signals, strategy_name
from paperbot import Config, PaperBroker

TRADER = "0x" + "a" * 40
OTHER = "0x" + "b" * 40


def fill(t_ms, direction, start=0.0, coin="BTC", sz="1", px="100"):
    return {"coin": coin, "dir": direction, "startPosition": str(start), "time": t_ms, "sz": sz, "px": px,
            "hash": f"h{t_ms}{coin}{direction}", "tid": t_ms}


class FakeHL:
    """Serves userFillsByTime and candleSnapshot from scripts."""

    def __init__(self, fills=None, prices=None):
        self.fills = fills or {}      # user -> fills
        self.prices = prices or {}    # coin -> list of (open_ms, close)
        self.calls = []

    def __call__(self, url, body):
        self.calls.append(body["type"])
        if body["type"] == "userFillsByTime":
            fs = [f for f in self.fills.get(body["user"], [])
                  if body["startTime"] <= f["time"] <= body["endTime"]]
            return fs[:hl_copy.FILLS_PAGE]
        if body["type"] == "candleSnapshot":
            r = body["req"]
            return [{"t": t, "T": t + 299_999, "o": c, "h": c * 1.001, "l": c * 0.999, "c": c}
                    for t, c in self.prices.get(r["coin"], []) if r["startTime"] <= t < r["endTime"]]
        return {}


class SignalTest(unittest.TestCase):
    def test_fresh_long_buys_and_close_sells(self):
        sig = signals(TRADER, [fill(1000, "Open Long"), fill(2000, "Open Long", start=1),
                               fill(3000, "Close Long", start=2)])
        self.assertEqual([(s[1], s[2]) for s in sig], [("buy", "BTC"), ("sell", "BTC")])
        self.assertEqual(sig[0][0], 1.0)

    def test_ignores_adds_shorts_and_spot(self):
        sig = signals(TRADER, [fill(1, "Open Long", start=5), fill(2, "Open Short"),
                               fill(3, "Close Short", start=-1), fill(4, "Buy", coin="@107"),
                               fill(5, "Open Long", coin="PURR/USDC")])
        self.assertEqual(sig, [])

    def test_flip_to_short_counts_as_exit(self):
        self.assertEqual(signals(TRADER, [fill(1, "Long > Short", start=3)])[0][1], "sell")


class FetchTest(unittest.TestCase):
    def test_pages_through_full_batches_and_dedups(self):
        fills = [fill(i, "Open Long", coin=f"C{i}") for i in range(hl_copy.FILLS_PAGE + 5)]
        fake = FakeHL({TRADER: fills})
        got = fetch_fills(TRADER, 0, 10**9, post=fake, sleep=lambda s: None)
        self.assertEqual(len(got), len(fills))
        self.assertEqual(fake.calls.count("userFillsByTime"), 2)

    def test_candles_are_stamped_at_close(self):
        fake = FakeHL(prices={"ETH": [(0, 10.0), (300_000, 11.0)]})
        ticks = candles("ETH", 0, 600_000, "5m", post=fake, sleep=lambda s: None)
        self.assertEqual([(t.product, t.ts, t.bid) for t in ticks],
                         [("HL:ETH", 299.999, 10.0), ("HL:ETH", 599.999, 11.0)])
        self.assertAlmostEqual(ticks[0].high, 10.01)


class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.broker = PaperBroker(Config())
        self.copier = Copier(self.broker)

    def ticks(self, closes, coin="BTC"):
        fake = FakeHL(prices={coin: [(i * 300_000, c) for i, c in enumerate(closes)]})
        return candles(coin, 0, len(closes) * 300_000, "5m", post=fake, sleep=lambda s: None)

    def test_copies_after_the_fill_and_exits_when_trader_closes(self):
        sigs = signals(TRADER, [fill(310_000, "Open Long"), fill(910_000, "Close Long", start=1)])
        s = replay(sigs, self.ticks([100, 100, 101, 101.5, 101.5]), self.broker, self.copier)
        self.assertEqual(s["closed_trades"], 1)
        name = strategy_name(TRADER)
        self.assertEqual(s["per_strategy"][name]["trades"], 1)
        # bought at the close of the candle after the fill (100), sold after the close fill (101.5)
        self.assertGreater(s["per_strategy"][name]["pnl"], 0)

    def test_stop_loss_applies_to_copies(self):
        sigs = signals(TRADER, [fill(10_000, "Open Long")])
        s = replay(sigs, self.ticks([100, 97, 96]), self.broker, self.copier)
        self.assertEqual(s["closed_trades"], 1)
        self.assertLess(s["per_strategy"][strategy_name(TRADER)]["pnl"], 0)

    def test_other_traders_close_does_not_exit_my_copy(self):
        sigs = signals(TRADER, [fill(10_000, "Open Long")]) + signals(OTHER, [fill(400_000, "Close Long", start=1)])
        s = replay(sigs, self.ticks([100, 100.5, 100.5]), self.broker, self.copier)
        self.assertEqual(s["open_positions"], 1)

    def test_hl_fee_applies(self):
        self.assertEqual(Config().fee("HL:BTC"), Config.hl_fee)


class SafetyTest(unittest.TestCase):
    def test_read_only_no_keys_or_exchange(self):
        self.assertTrue(hl_copy.PAPER_ONLY)
        self.assertEqual(hl_copy.READ_TYPES, {"userFillsByTime", "allMids", "candleSnapshot"})
        with self.assertRaises(ValueError):
            hl_copy.info({"type": "order"}, post=lambda u, b: {})
        src = inspect.getsource(hl_copy).lower()
        for banned in ("/exchange", "private_key", "secret", "api_key", "eth_account", "sign_l1", "signature"):
            self.assertNotIn(banned, src)

    def test_default_traders_are_addresses(self):
        for t in hl_copy.TOP_TRADERS:
            self.assertRegex(t, r"^0x[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
