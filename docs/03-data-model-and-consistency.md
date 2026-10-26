# 03. Data Model and Consistency

PostgreSQL 16 is the system of record. This document lists what exists in the prototype, what to add, and the rules that keep money correct.

## 1. What the prototype already does well

- Integer minor-unit money; floats rejected; explicit rounding with recorded remainders.
- Versioned, immutable rulesets with a fingerprint stored on every settlement.
- Append-only ledger events with unique idempotency keys; balanced double-entry journals.
- Row locks (`SELECT ... FOR UPDATE`) on cycles and settlements.
- One settlement per cycle enforced by a unique constraint.
- Payout idempotency key `payout:{settlement_id}`; `UNKNOWN` outcomes handled.

These are written for PostgreSQL but tested on SQLite. **Phase 2 must run the whole suite on real PostgreSQL, including a true concurrent-request test.**

## 2. Tables to add

```sql
-- Raw provider events: persist first, process later.
CREATE TABLE provider_events (
  id               uuid PRIMARY KEY,
  provider         text NOT NULL,
  provider_event_id text NOT NULL,
  event_type       text NOT NULL,
  payload          jsonb NOT NULL,
  signature_ok     boolean NOT NULL,
  received_at      timestamptz NOT NULL DEFAULT now(),
  processed_at     timestamptz,
  attempts         int NOT NULL DEFAULT 0,
  last_error       text,
  UNIQUE (provider, provider_event_id)
);

-- Transactional outbox: written in the same transaction as the ledger event.
CREATE TABLE outbox (
  id            bigserial PRIMARY KEY,
  aggregate_type text NOT NULL,
  aggregate_id   uuid NOT NULL,
  event_type     text NOT NULL,
  payload        jsonb NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  published_at   timestamptz
);
CREATE INDEX outbox_unpublished ON outbox (id) WHERE published_at IS NULL;

-- API idempotency (authoritative copy; Redis is only a fast path).
CREATE TABLE api_idempotency (
  key          text NOT NULL,
  actor_id     uuid NOT NULL,
  request_hash text NOT NULL,
  response     jsonb,
  status_code  int,
  created_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (actor_id, key)
);

-- Per-circle monotonic sequence used for cache versioning and ETags.
ALTER TABLE circles ADD COLUMN ledger_seq bigint NOT NULL DEFAULT 0;

-- Proposed actions from agents; humans approve before anything executes.
CREATE TABLE proposed_actions (
  id uuid PRIMARY KEY, circle_id uuid NOT NULL, kind text NOT NULL,
  params jsonb NOT NULL, rationale text, state text NOT NULL DEFAULT 'PROPOSED',
  proposed_by text NOT NULL, decided_by uuid, decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

Also add: `users`, `user_contacts` (PII, encrypted), `consents`, `notification_prefs`, `notification_log`, `jobs` (scheduler), `read_model_*` tables (Phase 3), `circle_invites`, `organizer_payment_accounts` (the non-custodial link, see `06`).

## 3. PII separation

The ledger and engine reference **member ids only**. Names, phones, emails, documents and addresses live in `users` / `user_contacts` / object storage, encrypted. This lets you honour deletion requests by erasing or pseudonymizing PII without touching the append-only financial record.

## 4. Locking and isolation rules

1. Default isolation: `READ COMMITTED` with **explicit row locks** on the aggregate being changed. Avoid `SERIALIZABLE` retries on hot paths.
2. Lock order is fixed: **circle (if needed) then cycle then settlement**. Never the reverse.
3. Lock scope is one cycle. Contention is bounded by circle size (tens of members), so there are no global hot rows.
4. **No network calls inside a transaction.** PayPal, LLM, notification and cache calls happen before or after, never during.
5. Set `lock_timeout` (for example 3 s) and `statement_timeout` (for example 15 s) and `idle_in_transaction_session_timeout` on the app role.
6. Every external effect uses an idempotency key derived from a stable business identity (`payout:{settlement_id}`, `provider:{txn_id}`).

## 5. Idempotency layers

| Layer | Mechanism |
|---|---|
| HTTP | `Idempotency-Key` header, `api_idempotency` table, same request hash returns the stored response, different hash returns 422 |
| Ledger | Unique `idempotency_key` per event (exists) |
| Provider ingress | Unique `(provider, provider_event_id)` |
| Provider egress | Provider request id header set to the business idempotency key (**VERIFY** supported header per endpoint) |
| Consumers | Outbox consumers record processed event ids; re-delivery is a no-op |

## 6. Indexes to review first

- `ledger_events (circle_id, created_at)` and `(cycle_id, created_at)`
- `obligations (cycle_id, member_id)` unique
- `bids (cycle_id, member_id)` unique
- Partial indexes for active states, for example cycles not yet `FINALIZED`
- `notification_log (user_id, created_at DESC)`

## 7. Migrations

- Replace `create_all` on startup with **Alembic**. Startup must never mutate schema in production.
- Use **expand and contract**: add nullable column, deploy code that writes both, backfill, switch reads, drop later. Every migration must be safe to run while the old code is still serving.
- Append-only trigger and constraints are part of migrations and covered by tests.
- A migration that locks a large table is split or run with `CONCURRENTLY` options.

## 8. Connection management

- Put **PgBouncer** in transaction pooling mode in front of PostgreSQL once there is more than one API instance.
- Size pools so that `API instances x workers x pool_size` stays below the PgBouncer server limit.
- Avoid session-level features (advisory locks held across transactions, temp tables) with transaction pooling; use transaction-level advisory locks instead.

## 9. Read replicas and read-your-writes

- Replica serves **read models and history views** where seconds of staleness is acceptable. Show an "as of" timestamp.
- After a write, the client receives the new `ledger_seq`; a read that carries a `min_seq` is routed to the primary if the replica is behind. Simple alternative: send reads in the 5 seconds after a write to the primary.
- **Anything that feeds a money decision reads the primary under lock**, never a replica or a cache.

## 10. Growth and retention

- Expected ledger growth is about 10 million rows per year at 100k users (see `01`), which is small. Do not partition early.
- Partition `ledger_events` and `provider_events` by time (monthly) when a table passes about 100 million rows or backups become slow.
- Outbox: delete or archive published rows older than 7 days; partition by day if churn causes bloat.
- Financial records are retained per the strictest applicable rule (**VERIFY** per jurisdiction); PII retention is separate and shorter.

## 11. Backup and recovery

Managed PostgreSQL with point-in-time recovery, multi-AZ, daily snapshots, and a **quarterly restore drill** into a scratch environment, verified by running reconciliation against the restored data.
