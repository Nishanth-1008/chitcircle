# Phase 5: Global Expansion, Payment Rails and Compliance

**Timing:** about 6+ weeks, partly parallel to Phase 4
**Goal:** Serve many communities in many countries, legally and with the right payment rails.

## Why this phase matters

The hackathon framing is global, but real operation depends on local law and local rails. PayPal does not cover India-domestic payments (see `06`), and rules on rotating savings, interest and lotteries differ everywhere.

## Workstreams

### A. Jurisdiction profiles (data, versioned)
- [ ] Schema: discount and bid caps, commission rules, security requirements, enabled payout modes, required disclosures, minimum organizer verification
- [ ] Profiles for the first target markets (for example India registered-chit style, US and UK tanda/susu style, Kenya chama, South Africa stokvel)
- [ ] Each profile reviewed by a local professional before it is marked "supported"
- [ ] The UI refuses combinations the profile forbids; profiles never grant legal permission

### B. Payment rails behind the gateway interfaces
- [ ] Adapter for a licensed **domestic India rail** (UPI via a payment aggregator) for India-domestic circles
- [ ] Evaluate mobile-money rails where the community uses them (for example M-Pesa in Kenya)
- [ ] Card and bank-transfer options per market
- [ ] Per-circle rail selection; the engine and ledger remain unchanged
- [ ] Reconciliation adapters per rail

### C. Multi-currency
- [ ] One currency per circle, many circles in many currencies
- [ ] Provider-quoted conversion shown before payment; no internal FX math
- [ ] Reporting in the circle currency; optional display conversion

### D. Compliance and legal
- [ ] Counsel opinion on the operating model per market (software provider versus regulated activity)
- [ ] Organizer verification and KYC level per market
- [ ] AML screening approach with the payment partner
- [ ] Terms, privacy notices, and disclosures localised
- [ ] Decision on lottery mode: disabled unless a jurisdiction and the partner both permit it
- [ ] Decision on interest-bearing advances: gated by profile and counsel
- [ ] Registered-foreman path for India: partner with licensed foremen as customers who run chits on the platform

### E. Privacy and data residency
- [ ] Data-subject request tooling (export, delete) tested end to end
- [ ] Region pinning if a market requires it
- [ ] Retention schedules per data class

### F. Localisation
- [ ] Translation workflow with reviewers; locale-aware formatting
- [ ] Cultural vocabulary per community (names such as chit, tanda, susu shown natively)
- [ ] Support content in local languages

### G. Go-to-market foundations
- [ ] Community partnerships (organizations that already convene circles)
- [ ] Pricing model: SaaS subscription per circle or per organizer, with no fee on member funds in the first version
- [ ] Support model and hours per region

## Exit criteria

- At least two payment rails live behind the same interfaces
- At least three jurisdiction profiles supported with legal review
- A non-USD circle and an INR domestic circle each settle a full cycle in staging
- Counsel sign-off on the operating model for launch markets
- Data-subject request workflow verified

## Risks

| Risk | Mitigation |
|---|---|
| Regulatory change or misread | Counsel per market; profiles versioned; feature flags per jurisdiction |
| Rail partner onboarding takes months | Start conversations in Phase 2; keep the gateway abstraction clean |
| Translation errors in financial text | Native reviewers; plain-language review; screenshots in context |
| Over-expansion | Launch one market at a time with success metrics |
