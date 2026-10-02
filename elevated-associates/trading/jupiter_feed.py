"""Solana DEX prices for the PAPER engine, from Jupiter's public quote API.

PAPER ONLY. This module only asks Jupiter what a swap *would* return. It has no
wallet, never builds or sends a transaction, and reads no keys.

Each poll asks two quotes per token, sized like a real paper trade:
    buy:  NOTIONAL USDC -> token   gives the ask (USDC paid per token)
    sell: those tokens  -> USDC    gives the bid (USDC received per token)
Both quotes already include the pools' swap fees and price impact, so the gap
between bid and ask is the real round-trip cost at that size. The broker adds only
the Solana network fee on top (Config.dex_fee).

Products are named "JUP:<SYMBOL>" (for example JUP:SOL). Use a known symbol, or
"JUP:<mint>@<decimals>" for any other token.
"""

import json
import sys
import time
import urllib.parse
import urllib.request

from paperbot import Tick

PAPER_ONLY = True

JUPITER_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDC_DECIMALS = 6

# symbol -> (mint, decimals)
TOKENS = {
    "SOL": ("So11111111111111111111111111111111111111112", 9),
    "JUP": ("JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", 6),
    "BONK": ("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", 5),
    "WIF": ("EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", 6),
}


def resolve(product):
    """'JUP:SOL' or 'JUP:<mint>@<decimals>' -> (product name, mint, decimals)."""
    name = product if product.upper().startswith("JUP:") else f"JUP:{product}"
    token = name[4:]
    if "@" in token:
        mint, decimals = token.split("@", 1)
        return f"JUP:{mint}", mint, int(decimals)
    symbol = token.upper()
    if symbol not in TOKENS:
        raise ValueError(f"unknown token {token!r}: use one of {sorted(TOKENS)} or <mint>@<decimals>")
    mint, decimals = TOKENS[symbol]
    return f"JUP:{symbol}", mint, decimals


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ea-paperbot/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def quote_url(input_mint, output_mint, amount, slippage_bps):
    query = urllib.parse.urlencode({
        "inputMint": input_mint, "outputMint": output_mint,
        "amount": int(amount), "slippageBps": int(slippage_bps),
    })
    return f"{JUPITER_QUOTE}?{query}"


def quote_tick(product, notional_usd=50.0, slippage_bps=50, fetch=_get_json, now=time.time):
    """One bid/ask tick for `product` from a buy quote and a sell quote of `notional_usd`."""
    name, mint, decimals = resolve(product)
    usdc_in = round(notional_usd * 10 ** USDC_DECIMALS)
    buy = fetch(quote_url(USDC_MINT, mint, usdc_in, slippage_bps))
    token_units = int(buy["outAmount"])
    if token_units <= 0:
        raise ValueError(f"{name}: buy quote returned no tokens")
    sell = fetch(quote_url(mint, USDC_MINT, token_units, slippage_bps))
    tokens = token_units / 10 ** decimals
    ask = notional_usd / tokens
    bid = int(sell["outAmount"]) / 10 ** USDC_DECIMALS / tokens
    return Tick(now(), name, bid, ask)


def jupiter_feed(products, notional_usd=50.0, interval=5.0, max_ticks=None, slippage_bps=50,
                 fetch=_get_json, sleep=time.sleep, now=time.time):
    """Poll Jupiter quotes every `interval` seconds. Two requests per token per poll:
    keep tokens x 2 / interval under the free tier's limit (about 1 request per second)."""
    n = 0
    while max_ticks is None or n < max_ticks:
        started = now()
        for product in products:
            try:
                yield quote_tick(product, notional_usd, slippage_bps, fetch, now)
            except Exception as e:  # network hiccup or thin pool: skip this tick, keep running
                print(f"jupiter feed error {product}: {e}", file=sys.stderr)
        n += 1
        if max_ticks is None or n < max_ticks:
            sleep(max(0.0, interval - (now() - started)))
