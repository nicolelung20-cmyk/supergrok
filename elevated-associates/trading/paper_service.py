"""Always-on host for the paper bot: runs paperbot on live public Coinbase prices and serves its scorecard.

Paper only. It reuses paperbot's simulated broker, so there is no order path and no keys.

    python3 paper_service.py            # serves on $PORT (default 8080)

GET /         the latest summary.json (scorecard, gate status)
GET /healthz  "ok" while the trading thread is alive

On free hosts that sleep without traffic (Render), set KEEPALIVE_URL (Render sets
RENDER_EXTERNAL_URL automatically) and the service pings its own public URL every 10 minutes.
"""
import json
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import paperbot

PRODUCTS = [p.strip() for p in os.environ.get("PAPER_PRODUCTS", "BTC-USD,ETH-USD,SOL-USD").split(",") if p.strip()]
STRATEGY_NAMES = [s.strip() for s in os.environ.get("PAPER_STRATEGIES", ",".join(paperbot.STRATEGIES)).split(",") if s.strip()]
OUT = Path(os.environ.get("PAPER_OUT", "paper_runs/service"))
KEEPALIVE_SECONDS = 600

state = {"started": time.time(), "thread": None, "error": None}


def build(out=OUT, interval=1.0):
    out.mkdir(parents=True, exist_ok=True)
    broker = paperbot.PaperBroker(paperbot.Config(), ledger_path=out / "ledger.jsonl")
    bar_ticks = max(1, round(3600 / interval))
    strategies = [paperbot.STRATEGIES[n](bar_ticks=bar_ticks) if n == "trend_breakout" else paperbot.STRATEGIES[n]()
                  for n in STRATEGY_NAMES]
    return broker, strategies


def trade_forever(feed_factory=None, out=OUT):
    broker, strategies = build(out)
    feed = feed_factory() if feed_factory else paperbot.coinbase_feed(PRODUCTS, 1.0)
    try:
        paperbot.run(feed, strategies, broker, summary_path=out / "summary.json", stop_file=out / "STOP")
    except Exception as e:  # keep the web side up and report the failure on /healthz
        state["error"] = repr(e)
        raise


def summary_payload(out=OUT):
    path = out / "summary.json"
    body = json.loads(path.read_text()) if path.exists() else {"paper_only": True, "status": "warming up"}
    body["uptime_hours"] = round((time.time() - state["started"]) / 3600, 2)
    body["products"] = PRODUCTS
    return body


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/healthz"):
            alive = state["thread"] is not None and state["thread"].is_alive()
            self._send(200 if alive else 503, "text/plain", b"ok" if alive else f"down: {state['error']}".encode())
        elif self.path in ("/", "/status", "/summary.json"):
            self._send(200, "application/json", json.dumps(summary_payload(), indent=2).encode())
        else:
            self._send(404, "text/plain", b"not found")

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def keepalive(url):
    while True:
        time.sleep(KEEPALIVE_SECONDS)
        try:
            urllib.request.urlopen(url.rstrip("/") + "/healthz", timeout=10).read()
        except Exception as e:  # a missed ping only risks one sleep; the next one retries
            print(f"keepalive failed: {e}")


def main():
    state["thread"] = threading.Thread(target=trade_forever, daemon=True)
    state["thread"].start()
    url = os.environ.get("KEEPALIVE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    if url:
        threading.Thread(target=keepalive, args=(url,), daemon=True).start()
    port = int(os.environ.get("PORT", "8080"))
    print(f"paper service on :{port}, products {PRODUCTS}, strategies {STRATEGY_NAMES}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
