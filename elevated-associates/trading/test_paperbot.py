import inspect
import unittest

import paperbot
from paperbot import Config, EmaCross, PaperBroker, Tick, ZScoreReversion, run, synthetic_feed


def tick(price, ts=0.0, product="BTC-USD", spread=0.0):
    return Tick(ts, product, price - spread / 2, price + spread / 2)


class BrokerTest(unittest.TestCase):
    def test_round_trip_at_flat_price_loses_exactly_two_fees(self):
        b = PaperBroker(Config(taker_fee=0.006, slippage_bps=0))
        b.mark(tick(100))
        b.buy(tick(100), "s")
        b.sell(tick(100), "s")
        # 5% of $1000 in (risk policy), fee on entry and on exit
        self.assertAlmostEqual(b.cash, 1000 - 50 * 0.006 - 50 * 0.994 * 0.006, places=6)
        self.assertAlmostEqual(b.closed[0]["pnl"], b.cash - 1000, places=6)

    def test_stop_loss_and_take_profit(self):
        b = PaperBroker(Config(slippage_bps=0, stop_loss=0.02, take_profit=0.04))
        b.mark(tick(100))
        b.buy(tick(100), "s")
        b.check_exits(tick(97.9))
        self.assertEqual(b.closed[-1]["strategy"], "s")
        self.assertFalse(b.positions)
        b.buy(tick(100), "s")
        b.check_exits(tick(104.1))
        self.assertGreater(b.closed[-1]["pnl"], 0)

    def test_kill_switch_blocks_new_entries(self):
        b = PaperBroker(Config(slippage_bps=0, risk_per_trade=1.0, stop_loss=1.0, taker_fee=0))
        b.mark(tick(100))
        b.buy(tick(100), "a")
        b.mark(tick(94))  # -6% on the day
        self.assertTrue(b.paused)
        b.sell(tick(94), "a")
        b.buy(tick(94), "b")
        self.assertFalse(b.positions)

    def test_stocks_use_stock_fee(self):
        b = PaperBroker(Config(taker_fee=0.006, stock_fee=0.0, slippage_bps=0))
        b.mark(tick(100, product="SPY"))
        b.buy(tick(100, product="SPY"), "s")
        b.sell(tick(100, product="SPY"), "s")
        self.assertEqual(b.fees, 0)
        self.assertAlmostEqual(b.cash, 1000, places=6)

    def test_default_config_matches_risk_policy(self):
        c = Config()
        self.assertEqual((c.risk_per_trade, c.daily_kill_switch, c.max_positions), (0.05, 0.03, 5))

    def test_halt_closes_everything_and_blocks_entries(self):
        b = PaperBroker(Config(slippage_bps=0))
        for p in ("BTC-USD", "SPY"):
            b.mark(tick(100, product=p))
            b.buy(tick(100, product=p), "s")
        b.halt()
        self.assertFalse(b.positions)
        self.assertTrue(b.halted)
        b.buy(tick(100), "s")
        self.assertFalse(b.positions)

    def test_gate_needs_days_trades_profit_and_low_drawdown(self):
        b = PaperBroker(Config(slippage_bps=0, taker_fee=0, gate_min_days=1, gate_min_trades=2))
        g = b.gate()
        self.assertFalse(g["measured_checks_passed"])
        for i, ts in enumerate((0, 50_000)):
            b.mark(tick(100, ts=ts))
            b.buy(tick(100, ts=ts), "s")
            b.sell(tick(101, ts=ts + 1), "s")
        b.mark(tick(101, ts=90_000))
        g = b.gate()
        self.assertTrue(all(g["checks"].values()), g)

    def test_max_positions(self):
        b = PaperBroker(Config(max_positions=1))
        b.mark(tick(100))
        b.buy(tick(100), "a")
        b.buy(tick(100), "b")
        self.assertEqual(len(b.positions), 1)


class StrategyTest(unittest.TestCase):
    def test_ema_cross_buys_on_uptrend_and_sells_on_downtrend(self):
        s = EmaCross(fast=3, slow=10)
        sigs = [s.signal(tick(100 - i * 0.1)) for i in range(30)]
        sigs += [s.signal(tick(97 + i)) for i in range(30)]
        sigs += [s.signal(tick(127 - i)) for i in range(30)]
        fired = [x for x in sigs if x]
        self.assertIn("buy", fired)
        self.assertEqual(fired[-1], "sell")

    def test_zscore_buys_on_sharp_drop(self):
        s = ZScoreReversion(window=50, entry_z=-2.0)
        for i in range(49):
            s.signal(tick(100 + (i % 2) * 0.1))
        self.assertEqual(s.signal(tick(95)), "buy")


class SafetyTest(unittest.TestCase):
    def test_no_order_placement_or_credentials(self):
        src = inspect.getsource(paperbot).lower()
        self.assertTrue(paperbot.PAPER_ONLY)
        for banned in ("api_key", "api_secret", "/orders", "private", "hmac", "signature"):
            self.assertNotIn(banned, src)


class StopFileTest(unittest.TestCase):
    def test_stop_file_halts_run(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            stop = Path(d) / "STOP"
            stop.write_text("")
            b = PaperBroker(Config())
            out = run(synthetic_feed(["BTC-USD"], 100), [EmaCross()], b, stop_file=stop)
            self.assertTrue(out["halted"])


class EndToEndTest(unittest.TestCase):
    def test_synthetic_run_produces_consistent_summary(self):
        b = PaperBroker(Config())
        out = run(synthetic_feed(["BTC-USD", "ETH-USD"], 3000), [EmaCross(), ZScoreReversion()], b)
        self.assertTrue(out["paper_only"])
        self.assertGreater(out["closed_trades"], 0)
        self.assertGreater(out["fees_paid"], 0)
        self.assertGreaterEqual(out["max_drawdown_pct"], 0)


if __name__ == "__main__":
    unittest.main()
