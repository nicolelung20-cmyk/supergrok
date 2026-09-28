# Elevat — AI LinkedIn Post Writer

**Status:** live at https://eai-workspace.floot.app (Floot free tier). **Model:** 3 free posts/day with no signup; Pro $29/month for up to 100/day.

## Automation in place

- Daily sales pulse (generations, visitors, waitlist, active subscriptions)
- Social content Routine (Mon/Wed/Fri)
- Weekly contest/launch-directory scout (Mon)

## Blocker: can't take real money yet

Found Sep 28:
- The production `STRIPE_SECRET_KEY` is **invalid** (Stripe replies "Invalid API Key"), so `/checkout` can't create sessions.
- The fallback Payment Link was in **test mode**, where real cards are declined. It has been removed from the live app, so Upgrade now shows the Pro waitlist and captures interested buyers instead.

**Fastest way to turn on real checkout (Nicole, about 2 minutes, $0, no keys):**
1. Stripe Dashboard → switch on **Live mode** → Payment Links → New.
2. Product "Elevat Pro", **$29.00 / month**, recurring → Create link → copy the `https://buy.stripe.com/...` URL.
3. Paste it to Claude. It goes into `helpers/proPaymentLink.tsx` in the Floot project, the app is republished, and Upgrade takes real subscriptions. The app already passes `prefilled_email` and `client_reference_id`, so each payment maps to a user.

Until the webhook below is set up, turn on Pro for each payer by hand, using the Stripe customer's email.

**Full in-app checkout, with automatic Pro activation (about 5 minutes, $0):**
1. Stripe Dashboard → switch to **Live mode** → Developers → API keys → copy the secret key.
2. Floot project "Elevat" → Environment variables → set `STRIPE_SECRET_KEY`.
3. Tell Claude. It calls `/_api/stripe/setup_pro`, which creates the $29/mo price and the webhook.
4. Paste the webhook's signing secret into `STRIPE_WEBHOOK_SECRET`.

The Upgrade button then switches to real checkout on its own, with no code change.

## Next moves

1. Submit to free launch directories found by the contest scout.
2. Add a Riskline → Elevat cross-link: traders who post about markets are a natural audience.
3. After Stripe is back: re-enable Pro auto-activation and confirm no paid user is missing Pro.
