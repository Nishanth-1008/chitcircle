# Phase 2: Production Hardening of the Core

**Timing:** about 4 to 6 weeks after the hackathon
**Goal:** Make the money core safe enough for a real, small pilot.

## Workstreams

### A. Correctness on PostgreSQL
- [ ] Full test suite in CI on PostgreSQL 16; drop SQLite for integration tests
- [ ] Concurrency tests from `11` section 4 passing
- [ ] Verify the append-only trigger, unique constraints and row-lock order
- [ ] Alembic for all schema; startup never mutates schema
- [ ] Nightly invariant job (12 invariants plus journal balance plus pool net zero)

### B. Identity and authorization
- [ ] Managed OIDC provider with phone OTP and email
- [ ] Remove `X-Actor-Id` and `X-Actor-Role` stub; circle roles from the database
- [ ] Postgres row-level security as a second barrier
- [ ] Step-up verification for payout approval and payout-detail changes
- [ ] Admin and support roles with audit trail

### C. Idempotency and webhooks
- [ ] `Idempotency-Key` middleware with `api_idempotency` table
- [ ] Provider webhook pipeline: raw store, verify, ack, process, retry, dead-letter view
- [ ] Out-of-order handling (refund before payment)
- [ ] Nightly provider reconciliation with operations cases

### D. Payments readiness
- [ ] Non-custodial onboarding for organizers (`organizer_payment_accounts`) per `06`
- [ ] Provider fee account in the chart of accounts and ruleset fee policy
- [ ] Written confirmation of permitted use from the payment partner; lottery mode flag off
- [ ] Go-live checklist for the partner (credentials, webhooks, business verification)

### E. Operations and observability
- [ ] OpenTelemetry, structured logs, error tracking, synthetic checks
- [ ] Money-specific alerts from `08`
- [ ] Ops console v0: search, ledger view, replay event, rerun reconciliation, pause circle
- [ ] Backups, PITR, first restore drill
- [ ] Runbooks: stuck payout, webhook backlog, mismatch

### F. Security and compliance baseline
- [ ] Threat model review and external penetration test scope
- [ ] PII separation and field encryption in place
- [ ] Consent records; data export and deletion workflow
- [ ] Legal review of terms, disclosures, and jurisdiction profile defaults

### G. Pilot
- [ ] Recruit 3 to 5 friendly circles (sandbox first, then small live amounts where the partner and law permit)
- [ ] Weekly feedback sessions; log every confusion point
- [ ] Track: time saved, on-time rate, support requests, disputes

## Exit criteria

- All tests green on PostgreSQL with concurrency scenarios
- Authentication and authorization production-grade; no stub left
- Reconciliation and invariant jobs running with alerts
- One full pilot cycle settled with zero unresolved discrepancies
- Security review findings of high severity closed
- Runbooks written and one drill completed

## Risks

| Risk | Mitigation |
|---|---|
| Partner will not approve the use case | Choose a different rail or a different positioning early; keep gateway abstraction |
| Pilot circles uncomfortable with digital collection | Start with parallel run (ledger only) before moving money |
| Scope creep from feature requests | Hold features to Phase 4; Phase 2 is hardening |
