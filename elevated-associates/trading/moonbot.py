"""Moon bot: paper copy-trading of Solana wallets you choose.

PAPER ONLY. This module reads public Solana data (getSignaturesForAddress and
getTransaction over JSON-RPC) and Jupiter quotes. It has no wallet and never builds,
signs or sends a transaction.

How it works:
  1. Every --interval seconds, each watched wallet's new transactions are read.
     History that existed when the bot started is skipped, so it never copies old moves.
  2. A transaction where the wallet's balance of a token goes up while its SOL or
     stablecoins go down is a buy; the reverse is a sell. Buys smaller than
     --min-sol are ignored (dust, airdrops, tests).
  3. On a buy, the bot paper-buys the same token at a live Jupiter quote. On the
     wallet's sell, it paper-sells. Open positions are re-quoted every poll so the
     broker's stop-loss and take-profit (ELE-39) still apply.

Usage:
    python moonbot.py --wallets <addr1>,<addr2> --interval 15
    python moonbot.py --wallets-file wallets.txt --aggressive

Outputs ledger.jsonl and summary.json in --out (default paper_runs/moonbot-<time>/),
plus copied.jsonl with every wallet trade seen. Create a STOP file there to close all
paper positions and exit.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import jupiter_feed
from paperbot import AGGRESSIVE, Config, PaperBroker

PAPER_ONLY = True

SOLANA_RPC = "https://api.mainnet-beta.solana.com"
WSOL = "So11111111111111111111111111111111111111112"
QUOTE_MINTS = {
    WSOL,
    jupiter_feed.USDC_MINT,
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
}
READ_METHODS = {"getSignaturesForAddress", "getTransaction"}


def rpc(url, method, params, post=None):
    """One read-only JSON-RPC call."""
    if method not in READ_METHODS:
        raise ValueError(f"{method} is not a read method this bot may call")
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    if post is None:
        import urllib.request
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": "ea-moonbot/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            reply = json.load(r)
    else:
        reply = post(url, body)
    if reply.get("error"):
        raise RuntimeError(f"{method}: {reply['error']}")
    return reply.get("result")


def parse_trades(wallet, tx):
    """Token buys and sells by `wallet` in one jsonParsed transaction.

    Returns a list of {mint, decimals, side, amount, sol}. `sol` is the SOL (native plus
    wrapped) the wallet spent on a buy or received on a sell; trades paid in USDC or USDT
    are detected too, but report sol 0, so --min-sol filters them out.
    """
    if not tx or (tx.get("meta") or {}).get("err") is not None:
        return []
    meta = tx["meta"]
    deltas, decimals = {}, {}
    for sign, key in ((-1, "preTokenBalances"), (1, "postTokenBalances")):
        for b in meta.get(key) or []:
            if b.get("owner") != wallet:
                continue
            amt = b["uiTokenAmount"]
            deltas[b["mint"]] = deltas.get(b["mint"], 0) + sign * int(amt["amount"])
            decimals[b["mint"]] = int(amt["decimals"])
    keys = [k["pubkey"] if isinstance(k, dict) else k
            for k in tx["transaction"]["message"]["accountKeys"]]
    sol = 0.0
    if wallet in keys:
        i = keys.index(wallet)
        sol = (meta["postBalances"][i] - meta["preBalances"][i]) / 1e9
    sol += deltas.get(WSOL, 0) / 1e9
    quote_out = sol < 0 or any(deltas.get(m, 0) < 0 for m in QUOTE_MINTS - {WSOL})
    quote_in = sol > 0 or any(deltas.get(m, 0) > 0 for m in QUOTE_MINTS - {WSOL})
    trades = []
    for mint, delta in deltas.items():
        if mint in QUOTE_MINTS or delta == 0:
            continue
        if delta > 0 and quote_out:
            trades.append({"mint": mint, "decimals": decimals[mint], "side": "buy", "amount": delta, "sol": -sol})
        elif delta < 0 and quote_in:
            trades.append({"mint": mint, "decimals": decimals[mint], "side": "sell", "amount": -delta, "sol": sol})
    return trades


class WalletWatcher:
    """Reports each wallet's new trades since the previous poll (never its old history)."""

    def __init__(self, wallets, rpc_url=SOLANA_RPC, post=None):
        self.wallets, self.rpc_url, self.post = list(wallets), rpc_url, post
        self.last_sig = {}      # wallet -> newest signature already seen
        self.started = set()    # wallets whose existing history has been skipped

    def _call(self, method, params):
        return rpc(self.rpc_url, method, params, self.post)

    def poll(self):
        events = []
        for w in self.wallets:
            opts = {"limit": 25}
            if self.last_sig.get(w):
                opts["until"] = self.last_sig[w]
            sigs = self._call("getSignaturesForAddress", [w, opts]) or []
            first_poll = w not in self.started
            self.started.add(w)
            if sigs:
                self.last_sig[w] = sigs[0]["signature"]
            if first_poll or not sigs:
                continue  # baseline: skip history that existed before the bot started
            for s in reversed(sigs):  # oldest first
                if s.get("err") is not None:
                    continue
                tx = self._call("getTransaction", [s["signature"], {
                    "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
                for t in parse_trades(w, tx):
                    t.update(wallet=w, signature=s["signature"], ts=s.get("blockTime") or time.time())
                    events.append(t)
        return events


class MoonBot:
    """Mirrors watched wallets' buys and sells into a PaperBroker at Jupiter quotes."""

    name = "moon_copy"

    def __init__(self, watcher, broker, min_sol=0.5, quote=jupiter_feed.quote_tick, log_path=None):
        self.watcher, self.broker, self.min_sol, self.quote = watcher, broker, min_sol, quote
        self.log_path = log_path
        self.held = {}  # product -> wallet that we copied

    def _log(self, event):
        if self.log_path:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")

    def _tick(self, product):
        notional = self.broker.equity() * self.broker.cfg.risk_per_trade
        return self.quote(product, notional_usd=max(notional, 1.0))

    def step(self):
        for e in self.watcher.poll():
            product = f"JUP:{e['mint']}@{e['decimals']}"
            self._log(e)
            try:
                if e["side"] == "buy" and e["sol"] >= self.min_sol and product not in self.held:
                    t = self._tick(product)
                    self.broker.mark(t)
                    if self.broker.buy(t, self.name):
                        self.held[product] = e["wallet"]
                elif e["side"] == "sell" and self.held.get(product) == e["wallet"]:
                    t = self._tick(product)
                    self.broker.mark(t)
                    self.broker.sell(t, self.name, "wallet_sold")
                    self.held.pop(product, None)
            except Exception as err:  # no route or thin pool: skip, keep running
                print(f"moonbot {product}: {err}", file=sys.stderr)
        for product in list(self.held):
            try:
                t = self._tick(product)
            except Exception as err:
                print(f"moonbot quote {product}: {err}", file=sys.stderr)
                continue
            self.broker.mark(t)
            self.broker.check_exits(t)
            if (product, self.name) not in self.broker.positions:
                self.held.pop(product, None)  # stop or take-profit closed it


def main():
    ap = argparse.ArgumentParser(description="Paper copy-trading of Solana wallets (moon bot).")
    ap.add_argument("--wallets", default="", help="comma-separated Solana wallet addresses to follow")
    ap.add_argument("--wallets-file", help="file with one wallet address per line (# comments allowed)")
    ap.add_argument("--rpc", default=SOLANA_RPC, help="Solana JSON-RPC URL (public endpoint by default)")
    ap.add_argument("--interval", type=float, default=15.0, help="seconds between polls")
    ap.add_argument("--min-sol", type=float, default=0.5, help="ignore wallet buys smaller than this many SOL")
    ap.add_argument("--aggressive", action="store_true", help="opt-in profile: up to 10 open positions")
    ap.add_argument("--polls", type=int, default=None, help="stop after N polls")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    wallets = [w.strip() for w in args.wallets.split(",") if w.strip()]
    if args.wallets_file:
        for line in Path(args.wallets_file).read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                wallets.append(line)
    if not wallets:
        ap.error("give at least one wallet with --wallets or --wallets-file")

    out = Path(args.out or f"paper_runs/moonbot-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
    out.mkdir(parents=True, exist_ok=True)
    profile = AGGRESSIVE if args.aggressive else {}
    broker = PaperBroker(Config(**profile), ledger_path=out / "ledger.jsonl")
    bot = MoonBot(WalletWatcher(wallets, args.rpc), broker, args.min_sol, log_path=out / "copied.jsonl")
    print(f"moonbot: following {len(wallets)} wallet(s), paper only. Output: {out} (stop: touch {out / 'STOP'})")
    n = 0
    try:
        while args.polls is None or n < args.polls:
            started = time.time()
            if (out / "STOP").exists():
                broker.halt("manual_kill")
                break
            try:
                bot.step()
            except Exception as err:  # RPC hiccup: keep running
                print(f"moonbot poll error: {err}", file=sys.stderr)
            (out / "summary.json").write_text(json.dumps(broker.summary(), indent=2))
            n += 1
            time.sleep(max(0.0, args.interval - (time.time() - started)))
    except KeyboardInterrupt:
        pass
    (out / "summary.json").write_text(json.dumps(broker.summary(), indent=2))
    print(json.dumps(broker.summary(), indent=2))


if __name__ == "__main__":
    main()
