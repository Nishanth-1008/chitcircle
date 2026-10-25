# Open Questions and Decisions

Update this file as decisions are made. Each item lists an owner and when it must be resolved.

## Product and rules

| # | Question | Needed by |
|---|---|---|
| 1 | Interest model for advances: flat monthly rate on the outstanding pot, or reducing as installments are paid | Before Phase 1 early-payout UI |
| 2 | Default visibility tiers and whether circles can override them | Phase 1 |
| 3 | Default payout mode in the demo (agreed discount recommended) | Phase 1 |
| 4 | Dividend eligibility rule (the prototype uses "not in arrears past grace period"; confirm) | Phase 1 |
| 5 | Required approvals per payout mode (currently one count per ruleset) | Phase 2 |
| 6 | Remainder destination for rounding (organizer, pool, platform) | Phase 1 |
| 7 | Who bears provider fees (organizer, member, platform) | Phase 2 |
| 8 | Grace period and commission defaults per preset | Phase 1 |

## Payments

| # | Question | Needed by |
|---|---|---|
| 9 | Does the PayPal sandbox support a payout path? If not, is the order or invoice fallback acceptable for the demo? | Phase 0 (S2) |
| 10 | PayPal's exact webhook signature verification method for our receiver | Phase 0 (S3) |
| 11 | Which PayPal onboarding program supports organizer-owned accounts, and what are its eligibility rules? | Phase 2 |
| 12 | Is the chit-style savings group use case permitted under PayPal's acceptable use policy? | Phase 2 |
| 13 | Is PayPal still cross-border only in India? Confirm current status and any change | Phase 0 |
| 14 | Which domestic rail for India (UPI aggregator), and what onboarding does it need? | Phase 5 (start talks in Phase 2) |

## Legal and compliance

| # | Question | Needed by |
|---|---|---|
| 15 | Current foreman commission ceiling under the Chit Funds Act (a 2018 amendment bill proposed raising it) | Before any India claims |
| 16 | Operating model opinion: software provider versus regulated activity, per market | Phase 2 and 5 |
| 17 | Lottery mode: allowed anywhere? Default disabled until confirmed | Phase 2 |
| 18 | Interest-bearing advances: allowed where, under what disclosures? | Phase 5 |
| 19 | KYC and AML expectations of the payment partner | Phase 2 |
| 20 | Data-protection obligations by market (India, EU, UK, US states) | Phase 2 and 5 |

## Technical

| # | Question | Needed by |
|---|---|---|
| 21 | Managed identity provider choice and OTP vendor | Phase 2 |
| 22 | Cloud for production (keep application cloud-neutral) | Phase 3 |
| 23 | Messaging channels and vendors (push, email, SMS, message apps) and per-message budget | Phase 4 |
| 24 | LLM provider and model tiers; monthly budget | Phase 1 and 3 |
| 25 | Bryntum and AG Grid licence terms beyond the trial | Phase 2 |

## Go-to-market

| # | Question | Needed by |
|---|---|---|
| 26 | First launch community and country | Phase 2 pilot |
| 27 | Pricing: per circle or per organizer, free tier | Phase 5 |
| 28 | Partnership targets: registered foremen, community organizations | Phase 2 onward |
