# Riskline — Position-Size / Risk Calculator

**Status:** live (Claude Artifact, https://claude.ai/artifact/GFwKMnSHVmWvYKFQUftBM5). Free, with a Pro waitlist offering founder pricing to the first 200 signups. Companion: Riskline Paper Desk.

## Automation in place

- Hourly markets + waitlist refresh into the Daybook
- Daily ops pass (one improvement per day)

**Both failed on Sep 28**, each within ~15s of firing. The most likely cause is the account usage limit (see [ledger](../ledger/2026-09-interactions.md)). If limits keep tripping, cut the hourly refresh to every 4 hours. It is the most frequent job and the least valuable per run.

## Next moves

1. Crypto mode: liquidation price and funding-rate drag.
2. A "quantum-inspired" optimal-f / Kelly sizing explainer as a Pro teaser.
3. Define what Pro contains before the waitlist hits 200.
