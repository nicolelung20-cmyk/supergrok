import unittest

import paperbot
from paperbot import STRATEGIES, LiquiditySweep, Tick


def candle(close, high, low, ts=0.0, product="BTC-USD"):
    return Tick(ts, product, close, close, high, low)


def flat(n, base=100.0, width=0.5):
    """n quiet candles: lows at base - width, highs at base + width."""
    return [candle(base, base + width, base - width, ts=i) for i in range(n)]


class LiquiditySweepTest(unittest.TestCase):
    def strat(self, **kw):
        kw.setdefault("lookback", 10)
        kw.setdefault("round_trip_cost", 0.001)
        return LiquiditySweep(**kw)

    def signals(self, s, ticks):
        return [s.signal(t) for t in ticks]

    def test_registered(self):
        self.assertIs(STRATEGIES["liquidity_sweep"], LiquiditySweep)

    def test_buys_wick_below_lows_that_closes_back_above(self):
        s = self.strat()
        sig = self.signals(s, flat(10) + [candle(99.8, 100.0, 99.4)])
        self.assertEqual(sig[-1], "buy")

    def test_no_buy_when_close_stays_below_the_lows(self):
        s = self.strat()
        sig = self.signals(s, flat(10) + [candle(99.2, 100.0, 99.0)])
        self.assertNotIn("buy", sig)

    def test_no_buy_before_lookback_is_full(self):
        s = self.strat()
        sig = self.signals(s, flat(5) + [candle(99.8, 100.0, 99.4)])
        self.assertNotIn("buy", sig)

    def test_skips_sweep_whose_target_cannot_clear_fees(self):
        s = self.strat(round_trip_cost=0.0125)  # Coinbase-sized costs (2.5% needed) vs a 0.7% target
        sig = self.signals(s, flat(10) + [candle(99.8, 100.0, 99.4)])
        self.assertNotIn("buy", sig)

    def test_skips_sweep_with_poor_reward_to_risk(self):
        s = self.strat(min_rr=1.5)
        # deep wick: risk 99.8 -> 97.0 (2.8%) vs reward to 100.5 (0.7%)
        sig = self.signals(s, flat(10) + [candle(99.8, 100.0, 97.0)])
        self.assertNotIn("buy", sig)

    def test_sells_at_target_liquidity(self):
        s = self.strat()
        sig = self.signals(s, flat(10) + [candle(99.8, 100.0, 99.4), candle(100.3, 100.4, 99.9),
                                         candle(100.6, 100.7, 100.2)])
        self.assertEqual(sig[-3:], ["buy", None, "sell"])

    def test_sells_when_sweep_wick_is_lost(self):
        s = self.strat()
        sig = self.signals(s, flat(10) + [candle(99.8, 100.0, 99.4), candle(99.3, 99.6, 99.2)])
        self.assertEqual(sig[-2:], ["buy", "sell"])

    def test_sells_after_max_hold(self):
        s = self.strat(max_hold=3)
        hold = [candle(100.0, 100.2, 99.7, ts=20 + i) for i in range(3)]
        sig = self.signals(s, flat(10) + [candle(99.8, 100.0, 99.4)] + hold)
        self.assertEqual(sig[-4:], ["buy", None, None, "sell"])

    def test_builds_bars_from_quotes_without_candles(self):
        s = self.strat(bar_ticks=3)
        quotes = []
        for i in range(10):  # each bar: 99.5, 100.5, 100.0 -> low 99.5, high 100.5
            quotes += [Tick(i, "X", p, p) for p in (99.5, 100.5, 100.0)]
        quotes += [Tick(99, "X", p, p) for p in (100.0, 99.4, 99.8)]  # wick to 99.4, close 99.8
        self.assertEqual(self.signals(s, quotes)[-1], "buy")
        self.assertEqual(self.signals(s, quotes[:3])[:2], [None, None])  # only bar closes signal


class CandleTickTest(unittest.TestCase):
    def test_history_ticks_carry_candle_high_and_low(self):
        end = 1_700_000_000 // 60 * 60

        def fetch(url):  # [time, low, high, open, close, volume], newest first
            return [[end - 60, 95.0, 105.0, 100.0, 101.0, 1.0]]

        ticks = list(paperbot.coinbase_history_feed(["BTC-USD"], 0.0007, 60, end=end, fetch=fetch))
        self.assertTrue(ticks)
        t = ticks[0]
        self.assertEqual((t.bid, t.ask, t.high, t.low), (101.0, 101.0, 105.0, 95.0))

    def test_quotes_have_no_candle_fields(self):
        t = Tick(0, "BTC-USD", 1.0, 1.1)
        self.assertIsNone(t.high)
        self.assertIsNone(t.low)


if __name__ == "__main__":
    unittest.main()
