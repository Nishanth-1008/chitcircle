# 05. Async Processing, Events, Scheduling and Real-Time

## 1. Why asynchronous

Payments, notifications, projections and agent runs must not run inside an HTTP request or a database transaction. They are driven by durable records (outbox rows, scheduled jobs, raw provider events) so that a crash at any moment loses nothing.

## 2. Transactional outbox

1. The service layer writes the ledger event and an `outbox` row in the **same transaction**.
2. A relay worker claims unpublished rows with `SELECT ... FOR UPDATE SKIP LOCKED`, publishes them to the job queue, and marks them published.
3. Consumers are **idempotent**: they record processed event ids and ignore duplicates.
4. Ordering is guaranteed per circle by routing all events of one circle to the same queue partition or by taking the circle lock in consumers that need order.

```python
# Relay loop (simplified)
while True:
    with session.begin():
        rows = session.execute(text("""
            SELECT id, event_type, aggregate_id, payload FROM outbox
            WHERE published_at IS NULL ORDER BY id
            LIMIT 200 FOR UPDATE SKIP LOCKED""")).all()
        for r in rows:
            queue.enqueue(r.event_type, r.aggregate_id, r.payload, dedupe_id=r.id)
        session.execute(text("UPDATE outbox SET published_at = now() WHERE id = ANY(:ids)"),
                        {"ids": [r.id for r in rows]})
    if not rows:
        time.sleep(0.2)
```

## 3. Queue technology

| Phase | Choice | Reason |
|---|---|---|
| 1 (hackathon) | Outbox plus a simple worker process polling Postgres; Render cron or Workflows for scheduled work | No extra infrastructure, fewest moving parts |
| 3+ | **Celery with a Redis broker** (dedicated `queue` instance) | Mature, works with the existing synchronous code, retries, rate limits, routing |
| Later | Kafka only if triggers in `adr/0003` are hit | Replay, many independent consumers, very high volume |

Queues by priority: `payments` (highest), `webhooks`, `projections`, `notifications`, `agents` (lowest). A slow LLM call must never delay a payout.

## 4. Webhook ingestion

1. Receiver reads the **raw body**, verifies the provider signature (use PayPal's verification method, not the prototype's HMAC stand-in; **VERIFY** exact method), and writes to `provider_events` with a unique `(provider, provider_event_id)`.
2. Returns `200` immediately. Verification failures return `4xx` and are alarmed if frequent.
3. A worker processes the event: maps it to an obligation or payout, applies it under the cycle lock, appends ledger events and outbox rows.
4. Failures retry with exponential backoff and jitter; after N attempts the event goes to a **dead-letter view** for manual handling.
5. **Out-of-order tolerance:** a refund arriving before the payment it refunds is parked and retried.
6. **Missed-webhook safety net:** a nightly job lists provider transactions for the day and reconciles against the ledger (see `06`).

## 5. Scheduler

Scheduled work lives in a `jobs` table (`run_at`, `type`, `circle_id`, `payload`, `status`, `attempts`), not in memory.

- A **dispatcher** claims due jobs with `SKIP LOCKED` and enqueues them. Leader election is a transaction-level advisory lock, so two dispatchers never double-fire.
- Jobs: open cycle, send reminder, close auction, escalate collection, run reconciliation, expire invites.
- Times are stored in UTC and computed from the **circle's time zone**.
- **Jitter** reminders across a window (for example 08:00 to 10:00 local) to avoid a thundering herd and to respect provider rate limits.
- Auction close is exact (deadline) and idempotent: closing an already closed auction is a no-op.

## 6. Provider rate limits and resilience

- A **token bucket** per provider limits outbound calls; workers back off on `429` or `5xx` with jitter.
- A **circuit breaker** opens after repeated failures; payouts queue up and the organizer sees "provider unavailable, will retry", never a false failure.
- Outbound calls always carry the idempotency key so a retry after a timeout cannot double-pay.
- Timeouts are explicit (connect 3 s, read 10 s). A timeout yields `UNKNOWN`, never `FAILED`.

## 7. Real-time for live auctions

| Phase | Approach |
|---|---|
| 1 | Client polls every 3 seconds with `ETag` revalidation (cheap with caching) |
| 4 | **Server-Sent Events** from the realtime gateway; Redis pub/sub broadcasts "circle X changed" |
| Later | WebSockets only if bidirectional features need them |

SSE is enough: bids go in via normal `POST`, updates flow out via SSE. Behind a load balancer, no sticky sessions are needed because Redis pub/sub fans out to every gateway instance. Anti-sniping (auto-extend the deadline on a late bid) is a ruleset option, not a default.

## 8. Notification pipeline

1. Consumer receives an outbox event and resolves recipients and **preferences** (channel, language, quiet hours).
2. Renders from versioned templates (per language).
3. De-duplicates by `(user, event, channel)`.
4. Sends via a channel adapter (push, email, SMS, messaging app) and logs delivery status.
5. Failures fall back to the next channel according to preference.

Message-app channels often need pre-approved templates and have per-message cost, so treat them as a premium channel with explicit opt-in.

## 9. When to move to Kafka

Not before: sustained event rate above about 5,000 per second, several independent consumers that need replay (analytics, fraud, search), or cross-service event contracts after a service split. Migration path: the outbox relay publishes to Kafka instead of the queue; event schemas are already versioned; consumers move one at a time. See `adr/0003`.
