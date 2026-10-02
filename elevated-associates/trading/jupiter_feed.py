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
import urllib.error
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


# ---------------------------------------------------------------- DEX history (GeckoTerminal)

GECKO = "https://api.geckoterminal.com/api/v2"
GECKO_TOKEN_POOLS = GECKO + "/networks/solana/tokens/{}/pools?page=1"
GECKO_OHLCV = GECKO + "/networks/solana/pools/{}/ohlcv/minute?aggregate={}&limit=1000&currency=usd&token={}"


def polite_get_json(url, retries=6, base_wait=10.0, sleep=time.sleep, get=_get_json):
    """GET JSON, waiting and retrying when the free API answers 429 Too Many Requests.

    Waits base_wait, 2x, 4x... seconds, or longer if a Retry-After header asks for more.
    GeckoTerminal sends "Retry-After: 0", so the header alone would retry with no pause.
    """
    for attempt in range(retries + 1):
        try:
            return get(url)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == retries:
                raise
            retry_after = (e.headers or {}).get("Retry-After")
            hinted = float(retry_after) if retry_after and str(retry_after).isdigit() else 0.0
            wait = max(hinted, base_wait * 2 ** attempt)
            print(f"rate limited, waiting {wait:.0f}s", file=sys.stderr)
            sleep(wait)


def top_pool(mint, fetch=polite_get_json):
    """Address of the highest-volume Solana pool for `mint` (GeckoTerminal lists pools by volume)."""
    pools = fetch(GECKO_TOKEN_POOLS.format(mint)).get("data") or []
    if not pools:
        raise ValueError(f"no DEX pools found for {mint}")
    return pools[0]["attributes"]["address"]


def dex_history_feed(products, days, aggregate=1, end=None, fetch=polite_get_json, pause=2.1, sleep=time.sleep):
    """Replay `days` of one-minute DEX candles (from on-chain swaps) for each `JUP:` product.

    Uses each token's highest-volume Solana pool on GeckoTerminal. Candles are
    [time, open, high, low, close, volume], newest first, at most 1000 per request; the free
    API allows about 30 requests a minute, hence `pause`. Each tick is the candle's close with
    its high and low; bid equals ask, so pool fees must come from Config.dex_fee.
    """
    end = int(end if end is not None else time.time())
    start = end - int(days * 86_400)
    rows = []
    for product in products:
        name, mint, _ = resolve(product)
        pool = top_pool(mint, fetch)
        before, seen = end, set()
        while before > start:
            url = GECKO_OHLCV.format(pool, aggregate, mint) + f"&before_timestamp={before}"
            candles = fetch(url).get("data", {}).get("attributes", {}).get("ohlcv_list") or []
            if pause:
                sleep(pause)
            older = [c for c in candles if int(c[0]) < before]
            if not older:
                break  # no more history for this pool
            for c in older:
                ts = int(c[0])
                if start <= ts < end and ts not in seen:
                    seen.add(ts)
                    rows.append((ts, name, float(c[4]), float(c[2]), float(c[3])))
            before = min(int(c[0]) for c in older)
    for ts, name, close, high, low in sorted(rows):
        yield Tick(float(ts), name, close, close, high, low)
