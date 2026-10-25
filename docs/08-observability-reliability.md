# 08. Observability and Reliability

## 1. Principles

- **Money correctness is a first-class SLO**, tracked next to latency and availability.
- Every request and job carries a **correlation id**; payments also carry their idempotency key, so one search shows the full story.
- Alert on **symptoms users or money feel**, not on every internal blip.

## 2. Telemetry stack

- **OpenTelemetry** in API, workers and scheduler for traces, metrics and logs; export to a managed backend (Grafana Cloud, Datadog or similar) so a small team does not run its own.
- **Structured JSON logs** with PII redaction.
- **Error tracking** (Sentry or similar) for backend, web and mobile.
- **Synthetic checks** from outside: login, load a circle, and a sandbox payment round-trip every few minutes.
- Product analytics events are separate from operational telemetry and exclude financial amounts unless aggregated.

## 3. Service-level objectives

| SLO | Target | Measured by |
|---|---|---|
| Read availability | 99.9% monthly | Synthetic and real traffic success ratio |
| Payment-path availability | 99.5% monthly | Webhook acceptance and payout submission success |
| Read latency | p95 under 300 ms | API traces on cached endpoints |
| Write latency | p95 under 800 ms | API traces excluding provider calls |
| Webhook-to-ledger lag | p99 under 60 s | `received_at` to `processed_at` |
| **Unbalanced journals** | **0** | Nightly invariant query |
| **Double payouts** | **0** | Unique idempotency plus nightly check |
| Reconciliation drift age | Under 24 h | Oldest open discrepancy |

## 4. Money-specific monitoring

| Signal | Alert |
|---|---|
| Journal debits not equal to credits | Page immediately |
| Circle pool does not net to zero after finalize | Page immediately |
| Payout in `PAYOUT_PENDING` more than 30 minutes | Warn; 2 hours page |
| Provider events unprocessed more than 5 minutes | Warn |
| Webhook signature failures above baseline | Security alert |
| Reconciliation discrepancy open more than 24 h | Ticket to operations |
| Duplicate provider event rate spike | Investigate provider or retries |
| Settlement calculated but not approved after N days | Notify organizer; operational dashboard |
| Overpayment unrefunded more than 3 days | Ticket |

A nightly **invariant job** re-checks the engine's 12 financial invariants against stored data and fails loudly on any violation.

## 5. System metrics

- API: request rate, error rate, latency histograms per route group, DB time per request.
- DB: connections, CPU, locks and lock waits, replication lag, slow queries, bloat on outbox.
- Cache: hit rate by key family, latency, evictions, stampede waits.
- Queues: depth, age of oldest job, retry rate, dead-letter count, per-queue throughput.
- Scheduler: late jobs, missed fires.
- Realtime: open connections, fan-out latency.
- LLM: cost per day, latency, fallback rate, refusals.
- Notifications: sent, delivered, failed, opt-out rate by channel.

## 6. Dashboards

1. **Executive and product:** active circles, cycles settled, on-time payment rate, time saved for organizers.
2. **Operations:** queue health, webhook lag, reconciliation board, open cases.
3. **Money integrity:** invariants, journal balance, pending payouts, provider mismatch.
4. **Performance:** latency, cache, DB.
5. **Cost:** infra, provider fees, LLM, messaging.

## 7. Reliability design

| Failure | Behaviour |
|---|---|
| PayPal slow or down | Circuit breaker; payouts queue; organizer sees a clear status; no false failures |
| Redis down | Fall through to the database; lower rate limits; no money impact |
| Worker crash mid-job | Job redelivered; idempotency keys make it safe |
| API instance crash | Load balancer drains; stateless instances replace it |
| DB failover | Multi-AZ automatic failover; app retries with backoff; short transactions limit blast radius |
| Duplicate delivery anywhere | Idempotent by design |
| LLM provider down | Agents fall back to templates; no money path depends on LLM |
| Region outage | Phase 6: warm standby region with replicated database and runbook |

Deploy practices: rolling or blue-green, health and readiness probes, graceful shutdown that finishes in-flight jobs, feature flags to disable agents, lottery mode, and new payout paths instantly.

## 8. Backup and disaster recovery

- PITR with 5-minute RPO target, multi-AZ database, cross-region snapshot copies.
- Quarterly **restore drill** that restores to a scratch environment and runs the invariant and reconciliation jobs.
- Object storage versioned; secrets and IaC state backed up.
- RTO target 1 hour for the primary region; documented step-by-step runbook.

## 9. Incident management

- Severity levels (SEV1 money at risk or data exposure, SEV2 major feature down, SEV3 degraded).
- On-call rotation once there are real users; start with a single owner plus clear escalation.
- Blameless post-incident reviews with tracked action items.
- Runbooks for: stuck payout, webhook backlog, provider outage, reconciliation mismatch, suspected fraud, data-subject request.
- Status page for members and organizers.

## 10. Operations tooling

A small internal console (role-gated, fully audited): search by circle or member, view ledger and journals, replay a provider event, re-run reconciliation, resolve an operations case, pause a circle, and export a statement. Build it before launch; support quality depends on it.
