# Phase 1: Hackathon MVP

**Dates:** Oct 27 to Nov 11, 2026
**Deadline:** Nov 12, 2026, 12:00pm PST (about 1:30am IST Nov 13). **VERIFY**, and aim to submit by the evening of Nov 11 IST.
**Goal:** A convincing, working demo with PayPal at the center: an organizer runs a circle end to end and the system removes their hassles.

## Scope

**Must have**
- Real `PayPalGateway` behind the existing interfaces (or the documented fallback for payout)
- Verified webhook receiver; `provider_events` table; processing into ledger events
- Preset rulesets (for example Indian-style auction chit, tanda rotation, agreed-discount) as data
- Simulator that drives a 20-cycle circle through the real API
- Auth (simple JWT), read endpoints for timeline and dashboard
- Next.js organizer dashboard with the Bryntum timeline
- Auction flow in the UI (polling), settlement view, approve and payout
- Collections agent with escalation and one-tap proposed actions
- Deployed on Render; Postman collection; demo video; write-up

**Should have**
- Explainer agent ("why is my installment X?") and bid advisor with effective-rate preview
- Agreed-discount early payout in the UI
- Zapier-driven reminders to a messaging or email channel
- Tiered visibility (group, private, organizer)

**Stretch**
- Organizer copilot daily summary; live SSE auction; second language; AG Grid ledger view

## Plan

### Week 1: Oct 27 to Nov 2 (engine to PayPal to API)
- [ ] `PayPalGateway` (collection plus payout or fallback); token cache and refresh
- [ ] Webhook receiver with real verification; `provider_events`; worker processing; `ledger_seq`
- [ ] Outbox table and simple relay loop
- [ ] Presets, seed script, and simulator (golden-run seeds)
- [ ] Minimal JWT auth replacing header stub for the demo path
- [ ] `GET /circles/{id}/timeline` and `/dashboard` read models (direct SQL is fine for now, cache later)
- [ ] Alembic baseline migration
- [ ] Render deploy of API, worker, database; Postman collection

### Week 2: Nov 3 to Nov 8 (product and agents)
- [ ] Next.js app: login, circle list, organizer dashboard, Bryntum timeline
- [ ] Member view: my payments, bid screen, settlement breakdown
- [ ] Auction open, bid, close in the UI; polling every 3 s
- [ ] Proposed-actions table and approval queue UI
- [ ] Collections agent: deterministic schedule, templated message with model-personalized line, reminder through Zapier
- [ ] Explainer and bid advisor if time allows
- [ ] Early-payout screen with effective annualized rate

### Nov 9 to 11: Freeze and submit
- [ ] Feature freeze on Nov 9 evening
- [ ] Demo script rehearsed; record video (short, with a clear story)
- [ ] README with architecture diagram and run instructions
- [ ] Devpost write-up: problem, global framing, PayPal usage, sponsor tools used and how, honest limitations
- [ ] Submit with at least 12 hours of buffer

## Demo story (about 3 minutes)

1. A circle is created from a preset; members join.
2. The simulator fast-forwards; the Bryntum timeline fills with paid, late and pending cells.
3. An auction runs; the settlement shows exact dividend math.
4. A member misses a payment; the agent reminds, proposes a catch-up invoice; the organizer approves in one tap.
5. An agreed-discount early payout shows the effective rate.
6. Payout executes through PayPal sandbox; ledger and reconciliation show clean.
7. Close: "From about 40 manual tasks to 3 approvals."

## Cut list (drop in this order if behind)

1. Second language, SSE, AG Grid
2. Organizer copilot
3. Bid advisor
4. Zapier channel (show a simulated message log)
5. Tiered visibility variants (keep organizer and group views)

Never cut: real PayPal sandbox collection, verified webhook, ledger integrity, and the timeline.

## Exit criteria

- Public URL with a working end-to-end demo on seeded data
- A real sandbox payment flows through webhook to ledger to timeline
- Payout executes (real or documented fallback)
- Demo video, repository, and write-up submitted

## Honest limitations to state

Sandbox only; no real funds; India-domestic settlement is not possible through PayPal (see `06`); lottery mode disabled; legal posture not reviewed.
