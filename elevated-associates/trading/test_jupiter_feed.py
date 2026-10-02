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
