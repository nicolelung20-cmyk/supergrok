# Trading ("Quantum") & Web3

**Status:** paper-only research. **Real capital deployed:** $0. **Kraken bot:** retired Sep 9, do not resume.

## The honest picture on "quantum trading"

- No retail-accessible quantum computer gives a trading edge today. Current quantum hardware is too small and noisy to beat classical methods on portfolio optimization or pricing at useful scale.
- **"Quantum AI" trading platforms are a well-known scam pattern.** Regulators including the FCA, CFTC and state securities boards have issued repeated warnings about apps sold under that name. Treat anything promising automatic returns from "quantum" as fraud until proven otherwise.
- What *is* real and legal: **quantum-inspired** optimization, such as simulated annealing or tensor-network methods, running on normal hardware. It can be applied to position sizing and portfolio construction, which is exactly Riskline's niche.

**Recommendation:** use "quantum" as a research and content angle (for example a "quantum-inspired portfolio optimizer" feature or explainer for Riskline Pro), not as a trading strategy.

## What the paper trading showed

- "Fees Ate the Edge" (Sep 7): after realistic fees and slippage, the simulated edge disappeared. This is the most common outcome for retail algo strategies.
- The meme-coin paper bot runs hourly on a simulated $1,000 portfolio with a 5% daily kill-switch.

**Gate before any real money** (from the [charter](../CHARTER.md)): at least 90 days of paper results that beat fees, a written thesis, a max-loss number, and Nicole's explicit yes. Trading only with the LLC's own money is generally fine. Trading for other people, pooling funds or selling signals can require registration (RIA, CTA or CPO), so get counsel first.

## Web3: sell the shovels, not the speculation

Lower-risk, legal revenue routes that fit the current stack:

| Idea | Why it fits | Cost |
|---|---|---|
| **Riskline for crypto:** position sizing with funding rates and liquidation price | Riskline already exists and the audience overlaps | $0 |
| **On-chain data explainers / dashboards** (read-only RPC via QuickNode free tier) | Content drives traffic to Riskline and Elevat | $0 |
| **Web3 AI-implementation packages** under Elevated AI services (wallet UX audits, agent workflows) | Reuses the $5k–$15k service model | $0 |
| **Token scanner** (BSC new-token scanner already built) as a *research* tool | Built; needs an Etherscan key | $0 (free key) |

**Avoid:** issuing a token, running a presale, custodying customer funds (money-transmitter risk), and paid "alpha" groups (investment-adviser risk).

## Next moves

1. Add a crypto mode to Riskline (liquidation price, funding-rate drag). No blockers.
2. Draft a "Quantum-inspired position sizing, explained" post as Riskline and Elevat content.
3. Finish the Coinbase Business onboarding checklist, so the LLC has a compliant on-ramp *if* a strategy ever passes the gate.
