# Phase 6: Scale-Out and Maturity

**Timing:** ongoing; every item is **trigger-driven**, not calendar-driven
**Goal:** Grow past 100k users without a rewrite, and mature operations.

## Trigger-driven backlog

| Item | Trigger | Approach |
|---|---|---|
| Partition large tables | Ledger or provider events above about 100 million rows, or slow backups | Monthly time partitions (or hash of circle id); online migration with dual writes |
| Second read replica / replica per region | DB read CPU above 60% sustained, or latency for distant users | Route read models and history to replicas |
| Kafka | Sustained events above about 5,000 per second, several independent replaying consumers (analytics, fraud, search) | Outbox relay publishes to Kafka; migrate consumers one by one; schema registry |
| Extract a service | A module needs independent scaling or a separate team (candidates: notifications, realtime gateway, agents) | Module boundaries from `02` make this a mechanical change |
| Sharding by circle id | Above about 1 million users or primary write saturation | Circle-scoped queries already; routing layer maps circle to shard |
| Multi-region active-passive | Availability or latency requirements, or data residency | Warm standby with replicated database and rehearsed failover |
| Analytics warehouse | Product and finance need cross-circle analysis | CDC or outbox export to a warehouse; no PII, amounts aggregated |
| Dedicated fraud and risk models | Enough real behaviour data and measured default rates | Train and shadow-evaluate against the transparent rule-based score |

## Maturity workstreams

- [ ] SOC 2 style controls (access, change management, incident response, vendor review)
- [ ] Annual penetration tests and quarterly access reviews
- [ ] Chaos and game-day program; SLO review cadence
- [ ] Cost optimisation: right-sizing, reserved capacity, observability sampling, messaging mix
- [ ] Public API and webhooks for partners (accounting tools, community platforms)
- [ ] Organizer marketplace features (templates, verified organizer badges)
- [ ] Credit-history features (portable payment record, optional bureau reporting where lawful), inspired by credit-reporting lending circles
- [ ] Data-lifecycle automation (retention, archival, deletion)

## Principles for this phase

1. **Measure first.** No scaling step without a dashboard showing the bottleneck.
2. **One change at a time**, each with a rollback and a load test.
3. **Correctness before capacity.** Invariants stay at zero violations through every change.
4. **Prefer boring technology.** PostgreSQL and Redis go a long way; add exotic systems only when a trigger fires.

## Exit criteria (rolling)

- Every trigger above has a dashboard and an owner
- Every scale-out step has a rehearsed rollback
- Quarterly capacity review recorded
