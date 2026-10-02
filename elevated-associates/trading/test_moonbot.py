import inspect
import unittest

import moonbot
from moonbot import WSOL, MoonBot, WalletWatcher, parse_trades
from paperbot import Config, PaperBroker, Tick

WALLET = "Wa11et1111111111111111111111111111111111111"
MEME = "MemeMint111111111111111111111111111111111111"


def tx(sol_change, token_change, mint=MEME, err=None, decimals=6, other_owner=False):
    """A minimal jsonParsed transaction: the wallet's SOL and token balance change."""
    owner = "Someone" if other_owner else WALLET
    pre, post = 1_000_000_000, 1_000_000_000 + int(sol_change * 1e9)

    def bal(amt):
        return {"accountIndex": 1, "mint": mint, "owner": owner,
                "uiTokenAmount": {"amount": str(amt), "decimals": decimals}}

    return {
        "meta": {"err": err, "preBalances": [pre, 0], "postBalances": [post, 0],
                 "preTokenBalances": [bal(5_000)], "postTokenBalances": [bal(5_000 + token_change)]},
        "transaction": {"message": {"accountKeys": [{"pubkey": WALLET}, {"pubkey": "TokenAcct"}]}},
    }


class ParseTest(unittest.TestCase):
    def test_buy_spends_sol_for_tokens(self):
        [t] = parse_trades(WALLET, tx(-2.0, 1_000_000))
        self.assertEqual((t["mint"], t["side"], t["amount"], t["decimals"]), (MEME, "buy", 1_000_000, 6))
        self.assertAlmostEqual(t["sol"], 2.0)

    def test_sell_receives_sol(self):
        [t] = parse_trades(WALLET, tx(1.5, -4_000))
        self.assertEqual(t["side"], "sell")
        self.assertAlmostEqual(t["sol"], 1.5)

    def test_ignores_failed_transactions_and_other_owners(self):
        self.assertEqual(parse_trades(WALLET, tx(-2.0, 1_000_000, err={"x": 1})), [])
        self.assertEqual(parse_trades(WALLET, tx(-2.0, 1_000_000, other_owner=True)), [])

    def test_token_received_without_paying_is_not_a_buy(self):
        self.assertEqual(parse_trades(WALLET, tx(0.0, 1_000_000)), [])  # airdrop or transfer in

    def test_wrapped_sol_counts_as_the_quote_side(self):
        t = tx(0.0, 1_000_000)
        t["meta"]["preTokenBalances"].append({"accountIndex": 2, "mint": WSOL, "owner": WALLET,
                                              "uiTokenAmount": {"amount": "3000000000", "decimals": 9}})
        t["meta"]["postTokenBalances"].append({"accountIndex": 2, "mint": WSOL, "owner": WALLET,
                                               "uiTokenAmount": {"amount": "0", "decimals": 9}})
        [trade] = parse_trades(WALLET, t)
        self.assertEqual(trade["side"], "buy")
        self.assertAlmostEqual(trade["sol"], 3.0)


class FakeChain:
    """Serves getSignaturesForAddress / getTransaction from a script of transactions."""

    def __init__(self):
        self.txs = {}       # signature -> tx
        self.order = []     # newest first
        self.calls = []

    def add(self, sig, transaction):
        self.txs[sig] = transaction
        self.order.insert(0, sig)

    def __call__(self, url, body):
        self.calls.append(body["method"])
        if body["method"] == "getSignaturesForAddress":
            until = body["params"][1].get("until")
            sigs = self.order[:self.order.index(until)] if until in self.order else list(self.order)
            return {"result": [{"signature": s, "err": None, "blockTime": 1_700_000_000} for s in sigs]}
        return {"result": self.txs[body["params"][0]]}


class WatcherTest(unittest.TestCase):
    def test_wallet_with_no_history_still_gets_its_first_trade_copied(self):
        chain = FakeChain()
        w = WalletWatcher([WALLET], post=chain)
        self.assertEqual(w.poll(), [])
        chain.add("first", tx(-2.0, 1_000_000))
        self.assertEqual([e["signature"] for e in w.poll()], ["first"])

    def test_skips_history_then_reports_new_trades_once(self):
        chain = FakeChain()
        chain.add("old", tx(-5.0, 1_000_000))
        w = WalletWatcher([WALLET], post=chain)
        self.assertEqual(w.poll(), [])                      # baseline: old buy is not copied
        chain.add("new", tx(-2.0, 1_000_000))
        [e] = w.poll()
        self.assertEqual((e["signature"], e["side"], e["wallet"]), ("new", "buy", WALLET))
        self.assertEqual(w.poll(), [])                      # not reported twice

    def test_only_read_methods(self):
        with self.assertRaises(ValueError):
            moonbot.rpc("x", "sendTransaction", [], post=lambda u, b: {})


def fake_quote(prices):
    def quote(product, notional_usd=50.0):
        p = prices[product]
        return Tick(0.0, product, p * 0.998, p * 1.002)
    return quote


class MoonBotTest(unittest.TestCase):
    def setUp(self):
        self.chain = FakeChain()
        self.prices = {f"JUP:{MEME}@6": 1.0}
        self.broker = PaperBroker(Config(dex_fee=0.0003))
        self.bot = MoonBot(WalletWatcher([WALLET], post=self.chain), self.broker,
                           min_sol=0.5, quote=fake_quote(self.prices))
        self.bot.step()  # baseline

    def test_copies_buy_then_wallet_sell(self):
        self.chain.add("b", tx(-2.0, 1_000_000))
        self.bot.step()
        self.assertIn((f"JUP:{MEME}@6", "moon_copy"), self.broker.positions)
        self.chain.add("s", tx(2.1, -1_000_000))
        self.bot.step()
        self.assertEqual(self.broker.positions, {})
        self.assertEqual(len(self.broker.closed), 1)

    def test_ignores_small_buys(self):
        self.chain.add("b", tx(-0.1, 1_000_000))
        self.bot.step()
        self.assertEqual(self.broker.positions, {})

    def test_stop_loss_still_applies(self):
        self.chain.add("b", tx(-2.0, 1_000_000))
        self.bot.step()
        self.assertEqual(len(self.broker.positions), 1)
        self.prices[f"JUP:{MEME}@6"] = 0.9  # -10%, beyond the 2% stop
        self.bot.step()
        self.assertEqual(self.broker.positions, {})
        self.assertEqual(self.bot.held, {})

    def test_quote_failure_skips_trade(self):
        def broken(product, notional_usd=50.0):
            raise OSError("no route")
        self.bot.quote = broken
        self.chain.add("b", tx(-2.0, 1_000_000))
        self.bot.step()
        self.assertEqual(self.broker.positions, {})


class SafetyTest(unittest.TestCase):
    def test_read_only_no_wallet_or_transactions(self):
        src = inspect.getsource(moonbot).lower()
        self.assertTrue(moonbot.PAPER_ONLY)
        self.assertEqual(moonbot.READ_METHODS, {"getSignaturesForAddress", "getTransaction"})
        for banned in ("sendtransaction(", "sendrawtransaction", "signtransaction", "keypair",
                       "private_key", "secret", "api_key", "/swap/v1/swap", "/execute"):
            self.assertNotIn(banned, src)


if __name__ == "__main__":
    unittest.main()
