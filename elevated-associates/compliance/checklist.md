# Compliance Checklist — Elevated Associates LLC

A working checklist, not legal or tax advice. Confirm state-specific items with a CPA or attorney.

## Entity hygiene
- [ ] EIN on file (needed for Coinbase Business, Stripe and banking)
- [ ] State annual report / franchise tax calendar set
- [ ] Registered agent current
- [ ] Operating agreement signed (a single-member LLC still needs one)
- [ ] Dedicated business bank account and card, with no personal spending on them
- [ ] Every account (Stripe, Coinbase, YouTube, API keys) opened in the LLC's name with a business email

## Tax & books
- [ ] QuickBooks tracks every stream as its own class or category (Elevated AI, Elevat, Riskline, HYE, MoneyPrinter)
- [ ] Quarterly estimated taxes scheduled (by default a single-member LLC's profit flows to Form 1040 Schedule C)
- [ ] Sales tax on SaaS checked for each state where customers are (Stripe Tax can calculate it)
- [ ] Crypto: every transaction logged with cost basis (Form 8949). Paper trades are not taxable events.

## Trading & crypto
- [ ] Real-money trading only with the LLC's own capital, never client money
- [ ] No selling signals, managing others' money, or pooling funds without counsel (RIA/CTA/CPO rules)
- [ ] No token issuance or presales (securities risk)
- [ ] No custody of customer crypto (money-transmitter licensing)
- [ ] Exchange accounts are business accounts with completed KYB

## Marketing & product
- [ ] Privacy policy + terms on Elevat, Riskline and the extensions (they collect emails and waitlist data)
- [ ] CAN-SPAM for outreach: real sender, physical address, working opt-out
- [ ] LinkedIn automation stays within LinkedIn's terms: drafts for a human to send, no auto-DM bots
- [ ] FTC disclosures on affiliate links and testimonials; no income claims ("make $X/month")
- [ ] Riskline: "not financial advice" disclaimer (already present on the Daybook)
- [ ] AI-generated video labeled per platform rules

## Data & security
- [ ] Supabase RLS policies reviewed (last pass: zero advisor findings)
- [ ] Secrets only in env vars or `config.ini` (gitignored), never committed
- [ ] 2FA on every business account
