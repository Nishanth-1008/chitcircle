# ADR 0003: Transactional outbox now, Kafka only on triggers

**Status:** Accepted

## Context
Several consumers need reliable reactions to ledger events: projections, notifications, agents, analytics. Event volume at 100k users is low (see `01`). Kafka is powerful but adds infrastructure, schemas, operations and cost.

## Decision
Write an `outbox` row in the same transaction as each ledger event. A relay publishes to the job queue (Celery on Redis). Consumers are idempotent. Event payloads are versioned from the start. Adopt Kafka only when triggers are met.

## Triggers for Kafka
- Sustained event rate above about 5,000 per second, or
- Multiple independent consumers that need replay (analytics, fraud, search), or
- A service split that requires durable cross-service event contracts.

## Consequences
- No dual-write problem; no lost events if a worker crashes.
- Less infrastructure now; migration path is to change the relay's destination and move consumers one at a time.
- Replay is limited to re-reading the outbox or ledger until Kafka arrives; keep ledger events as the replay source.

## Alternatives considered
- **Kafka now:** overkill for the load; higher operational risk for a small team.
- **Publish directly from request handlers:** risks lost or duplicate events on failure.
- **Database triggers only:** hard to evolve and test.
