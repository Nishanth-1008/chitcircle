# ADR 0006: PostgreSQL as the only system of record, including the ledger

**Status:** Accepted

## Context
The prototype implements an append-only event ledger with balanced double-entry journals, unique idempotency keys and row locks. Expected volume is about 10 million ledger rows per year at 100k users.

## Decision
Keep the ledger in PostgreSQL with constraints and an append-only trigger. Do not introduce a separate ledger database or event store. Use Redis only for ephemeral data.

## Consequences
- Transactions span ledger, outbox and state changes, which makes consistency straightforward.
- Strong tooling: PITR backups, replicas, constraints, SQL for invariants and reconciliation.
- Partitioning and replicas cover growth well past the target; sharding by circle id is the later path.

## Alternatives considered
- **Dedicated ledger database or event store:** extra operational surface for no need at this scale.
- **NoSQL for events:** loses relational constraints and transactional guarantees that money needs.
- **Blockchain ledger:** adds cost and complexity without solving custody or fiat rails.

## Revisit when
Write throughput on the primary saturates after partitioning and replicas (Phase 6 triggers).
