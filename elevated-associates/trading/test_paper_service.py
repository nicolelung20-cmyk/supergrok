import inspect
import json
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import paper_service
import paperbot


class PaperServiceTest(unittest.TestCase):
    def test_paper_only_no_credentials_or_orders(self):
        src = inspect.getsource(paper_service).lower()
        for banned in ("api_key", "api_secret", "/orders", "private", "hmac", "signature", "alpaca"):
            self.assertNotIn(banned, src)

    def test_recent_events_reads_fills_newest_first(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            (out / "ledger.jsonl").write_text(
                json.dumps({"ts": 1, "event": "buy", "product": "BTC-USD", "price": 10}) + "\n" +
                json.dumps({"ts": 2, "event": "kill_switch"}) + "\n" +
                json.dumps({"ts": 3, "event": "sell", "product": "BTC-USD", "price": 11, "pnl": 0.5}) + "\n")
            ev = paper_service.recent_events(out)
            self.assertEqual([e["ts"] for e in ev], [3, 1])

    def test_trades_synthetic_feed_and_serves_summary(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            paper_service.trade_forever(lambda: paperbot.synthetic_feed(["BTC-USD"], 3000), out=out)
            body = paper_service.summary_payload(out)
            self.assertTrue(body["paper_only"])
            self.assertIn("gate", body)

            orig = paper_service.OUT
            paper_service.OUT = out
            paper_service.state["thread"] = threading.Thread(target=lambda: None)
            server = ThreadingHTTPServer(("127.0.0.1", 0), paper_service.Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                port = server.server_address[1]
                got = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/summary.json").read())
                self.assertTrue(got["paper_only"])
                page = urllib.request.urlopen(f"http://127.0.0.1:{port}/").read().decode()
                self.assertIn("SuperGrok Desk", page)
                live = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/live").read())
                self.assertEqual([p["product"] for p in live["prices"]], ["BTC-USD"])
                self.assertGreater(live["prices"][0]["mid"], 0)
                self.assertTrue(live["summary"]["paper_only"])
                self.assertIsInstance(live["recent_events"], list)
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz")
                self.assertEqual(e.exception.code, 503)  # thread not alive -> unhealthy
            finally:
                server.shutdown()
                paper_service.OUT = orig


if __name__ == "__main__":
    unittest.main()
