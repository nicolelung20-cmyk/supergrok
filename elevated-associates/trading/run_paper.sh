#!/usr/bin/env bash
# Runs the Alpaca PAPER bot (trend_breakout) on this machine until you create the STOP file.
# Keys come from your shell; this script never prints or stores them.
#   export ALPACA_API_KEY_ID=...   export ALPACA_API_SECRET_KEY=...   (paper keys only)
#   ./run_paper.sh            start (or restart)
#   ./run_paper.sh stop       closes every position and exits the bot (kill-switch)
#   ./run_paper.sh status     prints the latest summary.json
set -euo pipefail
cd "$(dirname "$0")"

OUT="${PAPER_OUT:-paper_runs/alpaca-trend_breakout}"
PRODUCTS="${PAPER_PRODUCTS:-BTC/USD}"
STRATEGY="${PAPER_STRATEGY:-trend_breakout}"   # one strategy at a time (ELE-39)

case "${1:-start}" in
  stop)
    mkdir -p "$OUT" && touch "$OUT/STOP"
    echo "STOP file created. The bot closes all positions and exits within a few seconds."
    exit 0 ;;
  status)
    cat "$OUT/summary.json" 2>/dev/null || echo "No summary yet at $OUT/summary.json"
    exit 0 ;;
  start) ;;
  *) echo "usage: $0 [start|stop|status]" >&2; exit 2 ;;
esac

for var in ALPACA_API_KEY_ID ALPACA_API_SECRET_KEY; do
  if [ -z "${!var:-}" ]; then
    echo "$var is not set. Create a free Alpaca PAPER account, generate paper keys, and export both." >&2
    exit 1
  fi
done

echo "Checking the paper account..."
python3 alpaca_paper.py --check

mkdir -p "$OUT"
rm -f "$OUT/STOP"
echo "Starting $STRATEGY on $PRODUCTS. Output: $OUT (stop with: $0 stop)"
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -i python3 alpaca_paper.py --products "$PRODUCTS" --strategies "$STRATEGY" --out "$OUT"
fi
exec python3 alpaca_paper.py --products "$PRODUCTS" --strategies "$STRATEGY" --out "$OUT"
