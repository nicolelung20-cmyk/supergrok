import os
import tempfile
import unittest

import paperbot
import tournament
from paperbot import STRATEGIES, MomentumBreakout, RsiReversion, Tick


def candle(close, high=None, low=None, ts=0.0, product="BTC-USD"):
    return Tick(ts, product, close, close, high if high is not None else close, low if low is not None else close)


class NewStrategyTest(unittest.TestCase):
    def test_registered(self):
        self.assertIs(STRATEGIES["rsi_reversion"], RsiReversion)
        self.assertIs(STRATEGIES["momentum"], MomentumBreakout)

    def test_rsi_buys_oversold_and_sells_on_recovery(self):
        s = RsiReversion(period=5, buy_below=30, sell_above=55)
        closes = [100 - i for i in range(15)] + [86 + 2 * i for i in range(15)]
        sig = [s.signal(candle(c, ts=i)) for i, c in enumerate(closes)]
        self.assertIn("buy", sig)
        self.assertIn("sell", sig[sig.index("buy"):])

    def test_rsi_flat_market_does_nothing(self):
        s = RsiReversion(period=5)
        self.assertEqual({s.signal(candle(100.0, ts=i)) for i in range(50)}, {None})

    def test_momentum_buys_strong_move_and_sells_when_it_fades(self):
        s = MomentumBreakout(lookback=5, threshold=0.02, max_hold=50)
        closes = [100.0] * 6 + [101, 102, 103, 104] + [104, 103, 102, 101, 100, 99]
        sig = [s.signal(candle(c, ts=i)) for i, c in enumerate(closes)]
        self.assertIn("buy", sig)
        self.assertEqual(sig[-1] if "sell" not in sig else "sell", "sell")

    def test_momentum_time_stop(self):
        s = MomentumBreakout(lookback=3, threshold=0.01, max_hold=3)
        closes = [100, 100, 100, 100] + [102 + i for i in range(10)]
        sig = [s.signal(candle(c, ts=i)) for i, c in enumerate(closes)]
        first = sig.index("buy")
        self.assertEqual(sig[first + 3], "sell")

    def test_bar_strategy_groups_quotes(self):
        s = RsiReversion(bar_ticks=3)
        self.assertIsNone(s.bar(Tick(0, "X", 1.0, 1.0)))
        self.assertIsNone(s.bar(Tick(1, "X", 3.0, 3.0)))
        self.assertEqual(s.bar(Tick(2, "X", 2.0, 2.0)), (3.0, 1.0, 2.0))


class TickFileTest(unittest.TestCase):
    def test_write_and_replay_keep_high_and_low(self):
        ticks = [Tick(1.0, "A", 10.0, 10.0, 11.0, 9.0), Tick(2.0, "A", 10.5, 10.6)]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.csv")
            self.assertEqual(paperbot.write_ticks(ticks, path), 2)
            back = list(paperbot.replay_feed(path))
        self.assertEqual(back, ticks)


class TournamentTest(unittest.TestCase):
    def setUp(self):
        self.ticks = list(paperbot.synthetic_feed(["BTC-USD", "ETH-USD"], 6000))
        self.cands = tournament.grid(minute_ticks=60, round_trip=0.0024)

    def test_grid_covers_every_family(self):
        families = {name for _, name, _ in self.cands}
        self.assertEqual(families, set(STRATEGIES))
        self.assertEqual(len({label for label, _, _ in self.cands}), len(self.cands))  # unique labels

    def test_runs_train_and_test_and_ranks_by_train(self):
        rows, split = tournament.tournament(self.ticks, self.cands[:6], {"taker_fee": 0.001},
                                            min_trades=0, processes=1)
        self.assertEqual(split, int(len(self.ticks) * 2 / 3))
        self.assertEqual(len(rows), 6)
        scores = [r["train"]["score"] for r in rows]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for r in rows:
            self.assertEqual(r["robust"], r["train"]["return_pct"] > 0 and r["test"]["return_pct"] > 0)

    def test_parallel_matches_serial(self):
        serial, _ = tournament.tournament(self.ticks, self.cands[:4], {}, processes=1)
        parallel, _ = tournament.tournament(self.ticks, self.cands[:4], {}, processes=2)
        self.assertEqual(serial, parallel)

    def test_markdown_says_when_nothing_is_robust(self):
        rows = [{"label": "x", "strategy": "ema_cross", "robust": False, "eligible": True,
                 "train": {"return_pct": -1.0, "trades": 20}, "test": {"return_pct": -1.0, "max_dd_pct": 1.0,
                                                                      "trades": 9, "pre_fee_pnl": -3.0}}]
        meta = {"source": "s", "ticks": 1, "train_span": "a", "test_span": "b", "fee": 0.001, "profile": "ele-39"}
        self.assertIn("Nothing here has an edge yet", tournament.markdown(rows, meta))

    def test_paper_only(self):
        self.assertTrue(tournament.PAPER_ONLY)


if __name__ == "__main__":
    unittest.main()
