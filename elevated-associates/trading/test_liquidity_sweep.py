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

    def test_stop_buffer_survives_a_retest_of_the_wick(self):
        # bars range 1.0 wide; buffer 0.5 puts the stop at 99.4 - 0.5 = 98.9
        retest = candle(99.6, 99.9, 99.3)  # dips below the wick (99.4) but not the buffered stop
        plain = self.signals(self.strat(min_rr=0.5), flat(10) + [candle(99.8, 100.0, 99.4), retest])
        buffered = self.signals(self.strat(min_rr=0.5, stop_buffer=0.5),
                                flat(10) + [candle(99.8, 100.0, 99.4), retest])
        self.assertEqual(plain[-2:], ["buy", "sell"])
        self.assertEqual(buffered[-2:], ["buy", None])

    def test_trail_holds_past_target_and_exits_on_trailed_stop(self):
        s = self.strat(trail=3, max_hold=50)
        run_up = [candle(100.6 + i, 101.0 + i, 100.2 + i, ts=30 + i) for i in range(5)]  # target 100.5 hit, keeps rising
        drop = [candle(102.0, 102.5, 101.5, ts=40)]  # below the lowest low of the last 3 bars (102.2)
        sig = self.signals(s, flat(10) + [candle(99.8, 100.0, 99.4)] + run_up + drop)
        self.assertEqual(sig[10], "buy")
        self.assertNotIn("sell", sig[11:16])  # no exit at the first target
        self.assertEqual(sig[-1], "sell")

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


class LiquidityMagnetTest(unittest.TestCase):
    def strat(self, **kw):
        kw.setdefault("lookback", 12)
        kw.setdefault("round_trip_cost", 0.001)
        kw.setdefault("trend", 3)
        kw.setdefault("min_rr", 1.0)
        return paperbot.LiquidityMagnet(**kw)

    def history(self):
        # three equal highs at 102.0 (buy stops rest above them), then a pullback to ~100
        bars = [candle(101.5, 102.0, 101.0, ts=i) for i in range(3)]
        bars += [candle(100.0 + 0.1 * i, 100.3 + 0.1 * i, 99.8 + 0.1 * i, ts=3 + i) for i in range(9)]
        return bars

    def test_finds_untouched_equal_highs(self):
        s = self.strat()
        bars = [(102.0, 101.0)] * 3 + [(100.5, 99.8)] * 5
        self.assertEqual(s.magnet(bars, 100.4), 100.5)  # the range just above price is a pool too
        self.assertEqual(s.magnet(bars, 100.4, floor=101.0), 102.0)

    def test_ignores_highs_already_run_through(self):
        s = self.strat()
        bars = [(102.0, 101.0)] * 3 + [(103.0, 101.5)] + [(100.5, 99.8)] * 5
        self.assertIsNone(s.magnet(bars, 100.4, floor=101.0))

    def test_needs_enough_touches(self):
        s = self.strat(touches=3)
        bars = [(102.0, 101.0)] * 2 + [(100.5, 99.8)] * 5
        self.assertIsNone(s.magnet(bars, 100.4, floor=101.0))

    def test_buys_momentum_toward_magnet_and_sells_at_it(self):
        s = self.strat(stop_bars=2)  # stop 100.5: risk 0.69% vs 0.79% to the magnet
        push = candle(101.2, 101.3, 100.8, ts=20)       # closes above the prior bar's high (101.1)
        arrive = candle(102.0, 102.1, 101.3, ts=21)     # reaches the magnet at 102.0
        sig = [s.signal(t) for t in self.history() + [push, arrive]]
        self.assertEqual(sig[-2:], ["buy", "sell"])

    def test_no_buy_without_momentum(self):
        s = self.strat(stop_bars=2)
        stall = candle(100.9, 101.0, 100.7, ts=20)      # does not close above the prior bar's high
        sig = [s.signal(t) for t in self.history() + [stall]]
        self.assertNotIn("buy", sig)

    def test_registered_and_cli_defaults_apply(self):
        self.assertIs(STRATEGIES["liquidity_magnet"], paperbot.LiquidityMagnet)
        m = paperbot.LiquidityMagnet()
        self.assertEqual((m.lookback, m.max_hold), (240, 120))

    def test_skips_magnet_when_risk_is_larger_than_reward(self):
        s = self.strat(stop_bars=5)  # stop 100.2: risk 0.99% vs 0.79% to the magnet
        sig = [s.signal(t) for t in self.history() + [candle(101.2, 101.3, 100.8, ts=20)]]
        self.assertNotIn("buy", sig)
