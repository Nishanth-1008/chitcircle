# Phase 0: Foundation and Spikes

**Dates:** Oct 24 to 26, 2026 (3 days)
**Goal:** Remove the biggest unknowns before committing to the hackathon build.

## Why this phase exists

Three things can sink the project if discovered late: PayPal payout feasibility, the front-end timeline component, and the prototype's behaviour on real PostgreSQL. Each gets a time-boxed spike.

## Spikes

| # | Spike | Time box | Question answered | Output |
|---|---|---|---|---|
| S1 | **PayPal sandbox collection** | 4 h | Can we create an invoice or order, pay it with a sandbox buyer and receive a webhook that maps to an obligation? | Working script, list of event types and payload shapes |
| S2 | **PayPal payout feasibility** | 3 h | Is a payout path available in the sandbox? If not, what is the best fallback (order or invoice from the organizer account to the winner)? | Decision note in `appendix/open-questions.md` |
| S3 | **Webhook verification** | 2 h | How does PayPal's signature verification work for our receiver? | Replacement for the prototype's HMAC verifier |
| S4 | **Token lifecycle** | 1 h | Expiry, refresh, concurrency | Token cache design validated |
| S5 | **Prototype on real PostgreSQL** | 3 h | Do all 86 tests pass on Postgres 16? Does the append-only trigger work? Do row locks behave under concurrent requests? | CI-ready test run, list of fixes |
| S6 | **Bryntum Scheduler** | 2 h | Can we render a member x month grid from fake data and style cells (paid, late, pending, auction month, winner)? | Prototype page, licence trial activated |
| S7 | **Render skeleton** | 2 h | Deploy API, worker, Postgres from the repository | Public health endpoint |
| S8 | **Postman and APIMatic setup** | 1 h | Collection imports the PayPal sandbox collection; Context Plugin installed in the coding agent | Working environment |

## Tasks

- [ ] Create sandbox business and buyer accounts; store credentials in environment, not code.
- [ ] Run S1 to S4 in one scratch script; record raw payloads as fixtures for the fake provider.
- [ ] Run the test suite against PostgreSQL (`docker compose up -d`, set `DATABASE_URL`); fix SQLite-only assumptions.
- [ ] Add a concurrency test for double payout and double webhook on Postgres.
- [ ] Decide currency for the demo (USD or GBP; INR only as a clearly labelled simulation, see `06`).
- [ ] Confirm hackathon rules: deadline in your time zone, required submission artefacts, sponsor requirements.
- [ ] Create the monorepo layout (`apps/api`, `apps/web`, `packages/api-client`) without moving working code yet.

## Exit criteria

- A sandbox payment produces a verified webhook that your code can map to an obligation.
- Payout decision made: real payout path, or documented fallback.
- Test suite green on PostgreSQL.
- Bryntum grid renders fake data.
- API deployed on Render with a public health check.

## Risks and fallbacks

| Risk | Fallback |
|---|---|
| No payout API in sandbox | Model payout as an order or invoice to the winner and state it plainly in the submission |
| Webhook delivery unreliable on localhost | Use a tunnel or the Render deployment as the webhook target |
| Bryntum styling takes too long | Use a simpler timeline grid for the demo and keep Bryntum for the organizer view only |
| Tests fail on Postgres | Fix incrementally; do not start new features until green |
