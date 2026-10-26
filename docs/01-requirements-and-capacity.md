# 01. Requirements and Capacity

## 1. Personas

| Persona | Needs |
|---|---|
| **Organizer** (foreman, banker, group leader) | Zero-chase collections, one dashboard, one-tap approvals, trustworthy records, early risk warnings |
| **Member** | See group status, pay easily, bid with understanding, know exactly what they will receive and pay |
| **Guarantor / approver** | Confirm security, approve a payout |
| **Platform operator** (you) | Reconciliation, support tooling, abuse handling, compliance reporting |

## 2. Functional scope (by phase)

- **Core (Phases 1 to 2):** circles, rulesets, cycles, contributions, auctions, agreed-discount early payout, settlement, approvals, payouts, ledger, reconciliation, disputes.
- **Experience (Phases 1 to 4):** organizer dashboard, member timeline, notifications, live auctions, mobile app.
- **Intelligence (Phases 1 and 3):** risk indicators, collections agent, bid advisor, explainer.
- **Global (Phase 5):** jurisdiction profiles, multiple currencies and payment rails, localisation.

## 3. Non-functional requirements

| Area | Target |
|---|---|
| Availability | 99.9% for read paths; 99.5% for payment-moving paths (degrade, never guess) |
| Latency | p95 under 300 ms for cached reads, under 800 ms for writes (excluding provider calls, which are async) |
| Correctness | **Zero** unbalanced journals; **zero** double payouts; reconciliation drift resolved within 24 h |
| Durability | RPO 5 minutes or better, RTO 1 hour or better |
| Auditability | Every money event traceable to an actor, a ruleset version, and an idempotency key |
| Security | No card data on our systems; PII separated from the ledger; least-privilege access |
| Accessibility | WCAG 2.1 AA target for web; screen-reader friendly |
| Localisation | Multiple languages and currencies, right-to-left support, circle-local time zones |

## 4. Capacity model

All figures are **assumptions to validate with load tests in Phase 3**.

| Assumption | Value |
|---|---|
| Registered members | 100,000 |
| Average circle size | 20 members, so about 5,000 circles |
| Cycle frequency | Monthly |
| Share of payments landing in the 3 busiest days | 50% |
| Peak hour share of a busy day | 15% |
| Burst factor on top of that | 10x |
| Daily active share | 30% |
| Sessions per active user per day | 3, with about 12 API calls each |

| Derived quantity | Calculation | Result |
|---|---|---|
| Contributions per month | 100,000 members x 1 | about 100,000 |
| Busy-day payments | 50,000 / 3 | about 16,700 per day |
| Peak-hour payments | 16,700 x 15% | about 2,500 per hour, 0.7 per second |
| Burst payment writes | 0.7 x 10 | about 7 per second |
| Webhook events | about 3 events per payment | about 20 to 30 per second at burst |
| Reads per day | 30,000 x 3 x 12 | about 1.1 million, 12 per second average |
| Peak reads | average x 10 | about 125 per second |
| Ledger rows per cycle | about 8 x 20 members | about 160 |
| Ledger rows per month | 160 x 5,000 cycles | about 800,000, roughly 10 million per year |
| Reminder notifications | 3 per member per cycle | about 300,000 per month |

**Conclusion.** One PostgreSQL primary, one read replica, Redis, 2 to 4 API instances and 2 workers comfortably carry 100k users with an order of magnitude of headroom. The design target is therefore **correctness under burst**, not raw throughput.

## 5. Where the real difficulty lies

1. **Correctness of money under retries and concurrency** (duplicate webhooks, double-clicks, worker crashes mid-payout).
2. **Due-date thundering herd:** thousands of reminders, payments and webhooks in a few hours.
3. **Provider dependency:** PayPal latency, rate limits and outages must never corrupt state.
4. **Read-heavy dashboards** that look at the same circle repeatedly.
5. **Notification fan-out** across channels with preferences and quiet hours.

## 6. Scaling triggers

| Signal | Threshold | Action |
|---|---|---|
| API p95 latency | above 500 ms for 1 week | Profile; add API instances; check cache hit rate |
| DB CPU | above 60% sustained | Add read replica routing; review slow queries; consider bigger instance |
| Cache hit rate on read models | below 85% | Review keys and TTLs; precompute projections |
| Ledger table size | above about 100 million rows | Partition by time or hash of circle id (Phase 6) |
| Queue depth | growing for 15+ minutes | Add workers; check provider throttling |
| Outbox lag | above 30 seconds | Add relay workers; check locks |
| Event volume | above about 5,000 per second sustained, or analytics consumers needing replay | Evaluate Kafka (`adr/0003`) |
| Users | above about 1 million | Plan sharding by circle id and multi-region |
