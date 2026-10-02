import inspect
import unittest
from urllib.parse import parse_qs, urlparse

import jupiter_feed
from jupiter_feed import JUPITER_QUOTE, USDC_MINT, jupiter_feed as feed, quote_tick, resolve
from paperbot import Config, EmaCross, PaperBroker, run

SOL_MINT = jupiter_feed.TOKENS["SOL"][0]


class FakeJupiter:
    """Answers quote URLs like Jupiter: SOL priced at `price` USDC, losing `cost` of value per swap."""

    def __init__(self, prices, cost=0.001):
        self.prices = list(prices)
        self.cost = cost
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        price = self.prices[0]
        amount = int(q["amount"])
        if q["inputMint"] == USDC_MINT:  # buy SOL with USDC
            sol = amount / 1e6 / price * (1 - self.cost)
            return {"outAmount": str(int(sol * 1e9))}
        if len(self.prices) > 1:  # advance the price after each buy/sell pair
            self.prices.pop(0)
        usdc = amount / 1e9 * price * (1 - self.cost)
        return {"outAmount": str(int(usdc * 1e6))}


class QuoteTest(unittest.TestCase):
    def test_resolve_known_symbol_and_custom_mint(self):
        self.assertEqual(resolve("JUP:sol"), ("JUP:SOL", SOL_MINT, 9))
        self.assertEqual(resolve("SOL")[0], "JUP:SOL")
        self.assertEqual(resolve("JUP:Mint111@4"), ("JUP:Mint111", "Mint111", 4))
        with self.assertRaises(ValueError):
            resolve("JUP:NOPE")

    def test_tick_brackets_price_by_round_trip_cost(self):
        fake = FakeJupiter([150.0], cost=0.001)
        t = quote_tick("JUP:SOL", notional_usd=50, fetch=fake, now=lambda: 1.0)
        self.assertEqual(t.product, "JUP:SOL")
        self.assertAlmostEqual(t.ask, 150 / 0.999, places=3)
        self.assertAlmostEqual(t.bid, 150 * 0.999, places=3)
        self.assertLess(t.bid, t.ask)

    def test_quotes_are_sized_like_a_paper_trade(self):
        fake = FakeJupiter([150.0])
        quote_tick("JUP:SOL", notional_usd=50, slippage_bps=50, fetch=fake)
        buy = parse_qs(urlparse(fake.urls[0]).query)
        self.assertTrue(fake.urls[0].startswith(JUPITER_QUOTE))
        self.assertEqual(buy["amount"], ["50000000"])  # 50 USDC in base units
        self.assertEqual(buy["slippageBps"], ["50"])
        sell = parse_qs(urlparse(fake.urls[1]).query)
        self.assertEqual(sell["inputMint"], [SOL_MINT])

    def test_feed_skips_errors_and_stops_after_max_ticks(self):
        def broken(url):
            raise OSError("blocked")
        ticks = list(feed(["JUP:SOL"], max_ticks=3, fetch=broken, sleep=lambda s: None))
        self.assertEqual(ticks, [])


class PaperRunTest(unittest.TestCase):
    def test_dex_products_pay_network_fee_not_exchange_fee(self):
        cfg = Config()
        self.assertEqual(cfg.fee("JUP:SOL"), cfg.dex_fee)
        self.assertLess(cfg.dex_fee, cfg.taker_fee)
        self.assertEqual(cfg.fee("BTC-USD"), cfg.taker_fee)

    def test_uptrend_then_drop_trades_on_jupiter_quotes(self):
        prices = [120 - i * 0.2 for i in range(100)] + [100 + i * 0.5 for i in range(200)] + [200 - i * 0.8 for i in range(150)]
        fake = FakeJupiter(prices, cost=0.001)
        broker = PaperBroker(Config(gate_min_days=0, gate_min_trades=1))
        ticks = feed(["JUP:SOL"], max_ticks=len(prices), fetch=fake, sleep=lambda s: None)
        result = run(ticks, [EmaCross(fast=5, slow=20)], broker)
        self.assertTrue(result["paper_only"])
        self.assertGreaterEqual(result["closed_trades"], 1)
        self.assertGreater(result["fees_paid"], 0)


class SafetyTest(unittest.TestCase):
    def test_quote_only_no_wallet_or_transactions(self):
        src = inspect.getsource(jupiter_feed).lower()
        self.assertTrue(jupiter_feed.PAPER_ONLY)
        self.assertIn("/swap/v1/quote", src)
        for banned in ("/swap/v1/swap", "swap-instructions", "/execute", "/order", "sendtransaction",
                       "keypair", "private_key", "secret", "api_key", "signature"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()


class FakeGecko:
    """GeckoTerminal-shaped answers: one pool list, minute candles newest first, 1000 a page."""

    def __init__(self, first_ts, last_ts):
        self.first_ts, self.last_ts, self.urls = first_ts, last_ts, []

    def __call__(self, url):
        self.urls.append(url)
        if "/tokens/" in url:
            return {"data": [{"attributes": {"address": "PoolAAA"}}, {"attributes": {"address": "PoolBBB"}}]}
        before = int(parse_qs(urlparse(url).query)["before_timestamp"][0])
        newest = min(before - 60, self.last_ts) // 60 * 60
        rows = [[t, 100.0, 101.0 + t % 7, 99.0, 100.5, 5.0]
                for t in range(newest, max(self.first_ts, newest - 1000 * 60) - 1, -60)]
        return {"data": {"attributes": {"ohlcv_list": rows}}}


class DexHistoryTest(unittest.TestCase):
    def test_pages_minute_candles_from_top_pool_in_time_order(self):
        end = 1_700_000_000 // 60 * 60
        fake = FakeGecko(first_ts=end - 5 * 86_400, last_ts=end)
        ticks = list(jupiter_feed.dex_history_feed(["JUP:SOL"], 2, end=end, fetch=fake, pause=0))
        self.assertTrue(all("/pools/PoolAAA/ohlcv/minute" in u for u in fake.urls[1:]))
        self.assertTrue(any(f"token={SOL_MINT}" in u for u in fake.urls[1:]))
        self.assertEqual(len(ticks), 2 * 1440)  # two days of minutes, no duplicates at page edges
        self.assertEqual([t.ts for t in ticks], sorted(t.ts for t in ticks))
        t = ticks[0]
        self.assertEqual((t.product, t.bid, t.ask, t.low), ("JUP:SOL", 100.5, 100.5, 99.0))
        self.assertGreater(t.high, t.low)

    def test_stops_when_pool_history_runs_out(self):
        end = 1_700_000_000 // 60 * 60
        fake = FakeGecko(first_ts=end - 3_600, last_ts=end)  # only one hour of history
        ticks = list(jupiter_feed.dex_history_feed(["JUP:SOL"], 30, end=end, fetch=fake, pause=0))
        self.assertEqual(len(ticks), 60)

    def test_replay_charges_the_dex_fee(self):
        cfg = Config(dex_fee=0.003)
        self.assertEqual(cfg.fee("JUP:SOL"), 0.003)


class PoliteGetTest(unittest.TestCase):
    def _http_error(self, code, retry_after=None):
        import urllib.error
        headers = {"Retry-After": retry_after} if retry_after else {}
        return urllib.error.HTTPError("u", code, "x", headers, None)

    def test_retries_429_then_succeeds(self):
        calls, waits = [], []

        def get(url):
            calls.append(url)
            if len(calls) < 3:
                raise self._http_error(429)
            return {"ok": True}

        out = jupiter_feed.polite_get_json("u", base_wait=1, sleep=waits.append, get=get)
        self.assertEqual(out, {"ok": True})
        self.assertEqual(waits, [1, 2])

    def test_honors_retry_after(self):
        waits = []
        responses = [self._http_error(429, "7"), {"ok": 1}]

        def get(url):
            r = responses.pop(0)
            if isinstance(r, Exception):
                raise r
            return r

        jupiter_feed.polite_get_json("u", sleep=waits.append, get=get)
        self.assertEqual(waits, [7.0])

    def test_other_errors_and_exhausted_retries_raise(self):
        import urllib.error

        def boom(url):
            raise self._http_error(500)

        with self.assertRaises(urllib.error.HTTPError):
            jupiter_feed.polite_get_json("u", sleep=lambda s: None, get=boom)

        def always_429(url):
            raise self._http_error(429)

        with self.assertRaises(urllib.error.HTTPError):
            jupiter_feed.polite_get_json("u", retries=2, sleep=lambda s: None, get=always_429)
