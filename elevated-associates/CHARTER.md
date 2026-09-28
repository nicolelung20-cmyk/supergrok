# Operating Charter

These rules apply to every person, agent, Routine, and tool that works under Elevated Associates LLC. When an old prompt, repo, or doc conflicts with them, these rules win.

## 1. Legal, always

- **Only legal methods.** "Find the best way past a blocker" means switching to another legitimate route, such as a free tier, a different vendor, a manual step, or a partner. It never means evading terms of service, law, or access controls.
- **Not allowed, whatever the upside:** fake or bulk accounts; bypassing paywalls, CAPTCHAs or rate limits; jailbreak or "godmode" agents; scraping behind logins; stolen or borrowed credentials; unregistered investment offerings; pump-and-dump or wash trading; spam.
- **When in doubt, ask a professional.** Trading, securities, tax and money-transmission questions go to a licensed CPA or attorney before real money moves. The [compliance](compliance/) docs are checklists, not legal advice.

## 2. Capital policy: default spend is $0

| Tier | Rule |
|---|---|
| **Free** (free tiers, open source, owned tools) | Agents may use freely. |
| **Paid but reversible** (a subscription or credits under $50/mo) | Needs Nicole's explicit yes, a written reason, and a success metric reviewed at 30 days. |
| **Capital at risk** (trading, ads, inventory, anything > $50) | Needs Nicole's explicit yes plus a written thesis with a max-loss number. Real-money trading also needs a strategy that beat fees in at least 90 days of paper trading. |

**Strategic moves only.** Money moves only toward a stream with measured traction, such as paying users, booked calls or waitlist growth, and never toward one that is merely promising.

**Agents never** buy credits, upgrade plans, provision paid infrastructure, or place real trades on their own, even under a blanket go-ahead.

## 3. Identity and accounts

- Every account (Stripe, Coinbase, YouTube, API keys) is opened by Nicole in the LLC's name with the LLC's EIN and a business email. Agents prepare everything and hand her a single step.
- Keep business and personal money separate: one business bank account and one business card. Mixing them puts the LLC's liability shield at risk.

## 4. How agents coordinate

See [ops/agent-protocol.md](ops/agent-protocol.md). In short:

1. **One registry.** Every agent reads `registry.json` at start and writes its result back.
2. **One board.** `STATUS.md` is generated from it; the Daybook artifact mirrors it for mobile.
3. **Fail loudly, never silently.** A failed run records `last_status: failed` and a one-line reason.
4. **One blocker list.** Anything only Nicole can do goes into `blockers` once and is batched, never drip-fed.

## 5. Honesty in reporting

"Live" means real users can reach it. "Revenue" means money received. Projections, paper profits and waitlist counts are labeled as such.
