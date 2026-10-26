# ADR 0001: Modular monolith with background workers

**Status:** Accepted

## Context
Target is 100k+ users. The capacity model in `01` shows modest throughput (single-digit to low double-digit writes per second at burst, about 125 reads per second at peak). The team is small. The existing prototype is a single FastAPI codebase with a pure engine.

## Decision
Build one codebase with enforced module boundaries, deployed as several process types (API, workers, scheduler, realtime gateway). Do not split into microservices.

## Consequences
- Simple deployments, local development, and transactions across modules where needed.
- One consistent data model and fewer distributed-systems failure modes around money.
- Boundaries are kept by import rules and tests so extraction stays possible.
- Independent scaling is by process type, not by service.

## Alternatives considered
- **Microservices from day one:** more operational cost and consistency problems for a load that does not need them.
- **Serverless functions:** awkward for long-lived workers, connection pooling and idempotent processing.

## Revisit when
A module needs independent scaling or a separate team (see Phase 6 triggers).
