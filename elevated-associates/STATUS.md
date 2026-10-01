# Elevated Associates LLC — Status

_Generated 2026-10-01 from `registry.json` by `ops/ea_status.py`. Edit the registry, not this file._

## Revenue streams

| Stream | Status | Potential | Automation | Blocked on |
|---|---|---|---|---|
| [Elevated AI — implementation services](streams/elevated-ai-services.md) | active | high | Weekly free lead list + content (Routine, Mon) | quickbooks-reauth |
| [Elevat — AI LinkedIn post writer](streams/elevat.md) | live | medium | Daily sales pulse, social content M/W/F, weekly contest scout (Routines). Pro checkout OFF until a live Stripe key is set; Upgrade button shows the Pro waitlist meanwhile. | stripe-live-key |
| [Riskline — position-size / risk calculator](streams/riskline.md) | live | medium | Hourly markets/waitlist refresh + daily ops (Routines) | routine-usage-limit |
| [High-Yield Extensions](streams/high-yield-extensions.md) | backend-live | medium | Covered by venture ops scans | — |
| [MoneyPrinter — automated Shorts](streams/moneyprinter.md) | blocked | low-medium | Pipeline built and tested end to end | pexels-key, youtube-connection |
| [Algorithmic / "quantum" trading research](trading/README.md) | paper-only | unproven | Second-by-second paper engine (elevated-associates/trading/paperbot.py): Coinbase public feed, EMA-cross + z-score strategies, real 0.6% fees, daily kill-switch. Runs on an always-on machine; the cloud blocks exchange APIs | — |
| [Web3 tooling & content](streams/trading-and-web3.md) | exploring | unproven | None yet | coinbase-business-setup |
| [Kraken funding-capture bot](streams/trading-and-web3.md) | retired | n/a | None — retired 2026-09-09 at owner's request; do not resume | — |
| [Agency Roni](streams/agency-roni.md) | exploring | unknown | None yet | — |

## Agents & automations

| Agent | Kind | Schedule | Last status | Last run |
|---|---|---|---|---|
| Daily: sales pulse + Grok list + PRs | routine | daily 14:00 UTC | succeeded | 2026-09-27 |
| Elevated AI LinkedIn prospects (Mon, free) | routine | Mon 12:52 UTC | succeeded | 2026-09-28 |
| Elevat social content (Mon/Wed/Fri) | routine | M/W/F 14:47 UTC | not-yet-run | — |
| Elevat contest scout (Mon) | routine | Mon 15:46 UTC | not-yet-run | — |
| Riskline — hourly markets & waitlist refresh | routine | hourly :46 | failed | 2026-09-28 |
| Riskline daily ops | routine | daily 12:48 UTC | failed | 2026-09-28 |
| Weekly status update (Fri) | routine | Fri 15:46 UTC | succeeded | 2026-09-26 |
| Daybook dashboard | artifact | — | live | 2026-09-12 |
| Venture Growth & Optimization Plan | artifact | — | live | 2026-09-16 |
| SuperGrok Bridge (this repo) | tool | — | local-only | — |

## Needs attention

- **Riskline — hourly markets & waitlist refresh** failed on its last run (2026-09-28)
- **Riskline daily ops** failed on its last run (2026-09-28)

## Needs Nicole (one-time checkpoints)

- **stripe-live-key** — Elevat cannot take real money: production STRIPE_SECRET_KEY is invalid (Stripe returns 'Invalid API Key'), and the fallback Payment Link was TEST mode. On Sep 28 the test link was removed from the live app so Upgrade shows the Pro waitlist instead of a checkout that declines real cards. _Action:_ Stripe Dashboard (LIVE mode) → Developers → API keys → copy the secret key → Floot project 'Elevat' → Environment variables → STRIPE_SECRET_KEY. Then tell Claude: it runs /_api/stripe/setup_pro (creates the $29/mo price + webhook), and you paste the webhook signing secret into STRIPE_WEBHOOK_SECRET. In-app checkout then turns on automatically (cost: $0 (Stripe charges only a fee per successful payment))
- **quickbooks-reauth** — QuickBooks connector signed out, so invoices and payment links for the $5k–$15k service packages can't be created. _Action:_ Reconnect QuickBooks under claude.ai → Settings → Connectors (cost: $0)
- **routine-usage-limit** — Riskline hourly + daily Routines failed today within ~15s of firing; several sessions this month stopped on the weekly usage limit (next reset shown as Sep 30, 01:00 UTC). _Action:_ Check plan usage at claude.ai/settings/usage; if limits keep tripping, pause the hourly Riskline refresh (the most frequent job) so higher-value runs finish (cost: $0 to pause)
- **coinbase-business-setup** — Coinbase Business / trust account checklist is waiting on EIN and entity documents. _Action:_ Work through the Coinbase Business Trust Account Checklist artifact (cost: $0)
- **pexels-key** — MoneyPrinter needs a free Pexels API key for stock footage. _Action:_ Create a free key at pexels.com/api under the LLC's email (cost: $0)
- **youtube-connection** — MoneyPrinter auto-upload needs a YouTube channel owned by the LLC. _Action:_ Create/choose the channel, then connect it (cost: $0)
