"""Edge cases of the ELE-39 risk policy that test_paperbot.py does not pin down."""
import unittest

import paperbot
from paperbot import Config, PaperBroker, Tick

DAY = 86_400.0


def tick(price, ts=0.0, product="BTC-USD"):
    return Tick(ts, product, price, price)


def broker(**kw):
    return PaperBroker(Config(slippage_bps=0, taker_fee=0.0, **kw))


class RiskPolicyTest(unittest.TestCase):
    def test_position_size_follows_current_equity_not_starting_cash(self):
        b = broker()
        b.mark(tick(100))
        b.cash = 2000.0
        b.buy(tick(100), "s")
        self.assertAlmostEqual(b.cash, 1900.0)

    def test_cash_never_goes_negative_when_every_slot_is_filled(self):
        b = broker(max_positions=5)
        for i in range(5):
            b.mark(tick(100, product=f"P{i}-USD"))
            b.buy(tick(100, product=f"P{i}-USD"), "s")
        self.assertEqual(len(b.positions), 5)
        self.assertGreater(b.cash, 0)

    def test_daily_halt_triggers_at_three_percent_not_before(self):
        b = broker()
        b.mark(tick(100, ts=0))
        b.cash = 1000.0 * 0.971
        b.mark(tick(100, ts=1))
        self.assertFalse(b.paused)
        b.cash = 1000.0 * 0.97
        b.mark(tick(100, ts=2))
        self.assertTrue(b.paused)
        self.assertIsNone(b.buy(tick(100, ts=3), "s"))

    def test_daily_halt_resets_on_the_next_utc_day(self):
        b = broker()
        b.mark(tick(100, ts=0))
        b.cash = 900.0
        b.mark(tick(100, ts=1))
        self.assertTrue(b.paused)
        b.mark(tick(100, ts=DAY + 1))
        self.assertFalse(b.paused)


if __name__ == "__main__":
    unittest.main()


class AggressiveProfileTest(unittest.TestCase):
    def test_aggressive_only_raises_open_positions(self):
        base, aggr = Config(), Config(**paperbot.AGGRESSIVE)
        self.assertEqual((base.max_positions, aggr.max_positions), (5, 10))
        for field in ("risk_per_trade", "stop_loss", "take_profit", "daily_kill_switch", "taker_fee"):
            self.assertEqual(getattr(base, field), getattr(aggr, field), field)

    def test_summary_names_the_profile(self):
        self.assertEqual(PaperBroker(Config()).summary()["risk_profile"], "ele-39")
        s = PaperBroker(Config(**paperbot.AGGRESSIVE)).summary()
        self.assertEqual((s["risk_profile"], s["max_positions"]), ("aggressive", 10))
