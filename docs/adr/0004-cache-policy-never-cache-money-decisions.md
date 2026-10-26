# ADR 0004: Cache policy: views yes, money decisions never

**Status:** Accepted

## Context
Dashboards and timelines are read far more than they change, and caching is needed for latency and cost. But a stale cached balance used in a payout or bid decision would be a financial bug.

## Decision
- Cache read models keyed by `{circle_id}:{ledger_seq}`; new writes change the sequence so stale keys become unreachable.
- Cache immutable data (rulesets by version) without expiry.
- **Never** read caches for eligibility, balances, settlement amounts, approvals, payout state, or reconciliation. Those read the primary database under lock.
- Redis failure must degrade performance only, never correctness.
- Use separate Redis instances for cache and queue because eviction policies conflict.

## Consequences
- Simple mental model and easy audits: any number that moves money has a database source.
- Slightly more database reads on decision paths; acceptable given the load.
- Needs a projection worker and a per-circle sequence.

## Alternatives considered
- **TTL-only caching:** stale windows with no way to prove freshness.
- **Write-through caching of balances:** couples correctness to cache health.
