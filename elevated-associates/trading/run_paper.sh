#!/usr/bin/env bash
# Runs the Alpaca PAPER bot (trend_breakout) on this machine until you create the STOP file.
# Needs NO keys: with none set it runs the keyless simulation (public Coinbase prices, simulated fills).
# Optional: export ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY (paper keys) to also mirror orders to Alpaca paper.
# This script never prints or stores keys.
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

if [ -n "${ALPACA_API_KEY_ID:-}" ] && [ -n "${ALPACA_API_SECRET_KEY:-}" ]; then
  MODE=alpaca
  echo "Alpaca paper keys found. Checking the paper account..."
  python3 alpaca_paper.py --check
else
  MODE=simulated
  echo "No Alpaca keys set. Running keyless: public Coinbase prices, simulated fills, same scorecard."
fi

mkdir -p "$OUT"
rm -f "$OUT/STOP"
echo "Starting $STRATEGY on $PRODUCTS ($MODE). Output: $OUT (stop with: $0 stop)"
if [ "$MODE" = alpaca ]; then
  CMD=(python3 alpaca_paper.py --products "$PRODUCTS" --strategies "$STRATEGY" --out "$OUT")
else
  CMD=(python3 paperbot.py --live --products "${PRODUCTS//\//-}" --strategies "$STRATEGY" --out "$OUT")
fi
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -i "${CMD[@]}"
fi
exec "${CMD[@]}"
