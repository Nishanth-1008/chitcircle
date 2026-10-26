# Phase 3: Scale Architecture

**Timing:** about 6 to 8 weeks, after Phase 2 exit
**Goal:** Meet the 100k-user targets in `01` with headroom, and prove it with load tests.

## Workstreams

### A. Read models and caching (see `04`)
- [ ] `circles.ledger_seq` incremented in the same transaction as every ledger write
- [ ] Projection worker builds `read_model_timeline`, `read_model_dashboard`, `read_model_member_view` from outbox events
- [ ] Redis `cache` instance; versioned keys; single-flight and jittered TTLs
- [ ] `ETag` and `If-None-Match` on read-model endpoints
- [ ] Rate limiting in Redis (login, OTP, bids, invites, heavy reads)
- [ ] Cache metrics and a Redis-down drill

### B. Asynchronous backbone (see `05`)
- [ ] Outbox relay hardened (`SKIP LOCKED`, batching, lag metric)
- [ ] Celery with a Redis `queue` instance (`noeviction`, AOF); queues: payments, webhooks, projections, notifications, agents
- [ ] Idempotent consumers with processed-event tracking
- [ ] Retry policy with backoff and jitter; dead-letter view and replay tool
- [ ] Scheduler with `jobs` table, advisory-lock leadership, jittered reminders
- [ ] Provider token bucket and circuit breaker

### C. Database scaling (see `03`)
- [ ] PgBouncer in transaction mode; pool sizing documented
- [ ] Read replica with routing rules and read-your-writes handling
- [ ] Slow-query review; indexes tuned from real plans
- [ ] Outbox cleanup and bloat monitoring
- [ ] `lock_timeout`, `statement_timeout`, `idle_in_transaction_session_timeout` set

### D. API and runtime
- [ ] Horizontal scaling of API behind a load balancer; readiness and liveness probes; graceful shutdown
- [ ] Gunicorn and Uvicorn worker tuning; thread pool sizing validated
- [ ] Response compression; pagination everywhere; N+1 query audit
- [ ] Separate webhook receiver deployment if it needs independent scaling

### E. Agents at scale (see `10`)
- [ ] Agent runner on the lowest-priority queue
- [ ] Explanation cache and batching of daily summaries
- [ ] Budget alerts and template fallback

### F. Load and resilience testing (see `11`)
- [ ] Scenarios: due-date surge, auction close storm, dashboard read load, reminder fan-out, 24 h soak
- [ ] Failure drills: Redis down, provider 5xx, worker kill, replica lag
- [ ] Capacity report that replaces the assumptions in `01` with measurements

## Exit criteria

| Criterion | Target |
|---|---|
| Sustained reads | 500 requests per second, p95 under 300 ms |
| Webhook surge | 30,000 events in 30 minutes, no loss, p99 lag under 60 s |
| Cache hit rate | Above 90% on timeline and dashboard |
| Redis failure | No increase in money errors; latency within agreed limits |
| Invariants | Zero violations through every load and chaos run |
| Cost | Cost per active circle measured and acceptable |

## Risks

| Risk | Mitigation |
|---|---|
| Premature complexity | Add one component at a time, each behind a measured need |
| Cache bugs serving stale money | Money decisions never read cache; versioned keys; invariant job |
| Queue backlog during surge | Priority queues, autoscaling on depth, jittered reminders |
| Replica lag surprises | Route post-write reads to primary; show "as of" times |
