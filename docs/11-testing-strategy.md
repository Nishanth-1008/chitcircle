# 11. Testing Strategy

## 1. Starting point

The prototype has 86 tests: unit tests, Hypothesis property-based tests, and API integration tests on in-memory SQLite, plus a test that keeps the engine free of framework and provider imports. Keep all of it. The gaps are real PostgreSQL, true concurrency, provider contracts and load.

## 2. Test pyramid

| Level | Scope | Tooling |
|---|---|---|
| Unit and property | Engine math, rounding, settlement invariants, state machine | pytest, Hypothesis |
| Stateful property | Random sequences of lifecycle actions never break invariants | Hypothesis state machines |
| Integration (real Postgres) | Services, constraints, triggers, row locks | pytest with a Postgres container in CI |
| Concurrency | Races on bids, payouts, webhooks, settlements | Threaded tests against Postgres |
| Contract | API matches OpenAPI; clients stay in sync | Schemathesis, generated-client check |
| Provider | PayPal sandbox end to end | Scheduled job with sandbox credentials |
| Load | Surge and soak at 10x targets | k6 or Locust |
| End to end | Critical user journeys | Playwright (web), Maestro or Detox (mobile) |
| Security | Dependencies, secrets, authz matrix | SAST, dependency scan, authorization tests |

## 3. Postgres in CI (Phase 2, first task)

- Run the full suite against PostgreSQL 16 in CI (service container). Keep SQLite only for fast local unit runs, or drop it.
- Add tests that exercise Postgres-only behaviour: `SELECT ... FOR UPDATE`, the append-only trigger, unique constraints, partial indexes, and `SKIP LOCKED` queues.
- Migration tests: apply all migrations to an empty database and to a snapshot of the previous release; run the suite after each.

## 4. Concurrency scenarios (must pass)

1. Two simultaneous payout requests for one settlement result in exactly one provider submission.
2. Two identical webhooks processed in parallel create one ledger event.
3. A bid and an auction close at the same instant: either the bid lands before close or is rejected; never lost silently.
4. Two organizers or approvers acting on one settlement: approvals counted once each, finalize only once.
5. Payout times out (`UNKNOWN`), then the checker and a late webhook both arrive: single final state.
6. Worker killed between provider call and ledger write: redelivery produces no duplicate.
7. Idempotent API retries return the original response.

## 5. Provider tests

- A **fake PayPal server** (recorded and parameterized) for deterministic CI: success, failure, timeout, duplicate webhook, out-of-order events, refund before payment.
- A nightly **real sandbox** run: create an invoice or order, pay it with a sandbox buyer, receive the webhook, reconcile, attempt a payout.
- Postman collection (sponsor tool) runs in CI against a deployed preview, with monitors in production for health and key flows.

## 6. Simulator as a test asset

The 20-month circle simulator (Phase 1) doubles as a **golden-run regression**: given a seed, it must produce identical ledgers, settlements and balances. Variants: normal circle, repeated late payer, default after winning, tie in an auction, no-bid month, rounding-heavy amounts, multi-currency presets, dispute mid-cycle.

## 7. Load and soak (Phase 3)

| Scenario | Target |
|---|---|
| Due-date surge | 30,000 payment webhooks in 30 minutes with no loss and under 60 s lag |
| Auction close storm | 500 simultaneous closes with correct results |
| Dashboard reads | 500 requests per second with cache, p95 under 300 ms |
| Reminder fan-out | 100,000 notifications in 2 hours without starving payments |
| Soak | 24 hours at 3x average load, memory and connection stability |
| Cache failure | Kill Redis mid-test; error rate stays flat, latency rises within limits |
| Provider failure | 50% 5xx from fake provider; breakers open, no duplicates |

## 8. Chaos and failure drills

Scheduled game days: kill a worker mid-payout, partition the database briefly, expire provider tokens, flood webhooks, restore a backup and reconcile. Each drill ends with the invariants job and a written finding.

## 9. Quality gates

- CI blocks merge on: unit, integration, concurrency, contract tests, lint, type checks, security scans.
- Coverage is tracked, but **invariant and concurrency tests are the gate that matters**.
- Release checklist for money-touching changes: migration reviewed, rollback plan, feature flag, reconciliation run on staging, two reviewers.

## 10. Test data and environments

- Seed presets for several communities and currencies.
- Synthetic members only; no production data in lower environments.
- Preview environment per pull request with its own database.
