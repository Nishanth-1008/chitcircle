# ChitCircle Backend

> **Backend for ChitCircle** — an organizer-first platform for community savings circles (Chit Funds, ROSCAs, Tandas, Susus, Committees). Built with FastAPI, SQLAlchemy 2.0, PostgreSQL 16, and a pure-Python financial engine.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Quickstart](#quickstart)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Running the Server](#running-the-server)
- [Running Tests](#running-tests)
- [Running the Worker](#running-the-worker)
- [Running the Scheduler](#running-the-scheduler)
- [Alembic Migrations](#alembic-migrations)
- [API Endpoints](#api-endpoints)
- [Key Design Decisions](#key-design-decisions)
- [Configuration Reference](#configuration-reference)

---

## Architecture Overview

The backend is a modular monolith with strict layering:

```
HTTP Layer (FastAPI)          →  app/main.py, app/api/routes.py
Service Orchestration         →  app/services/financial_service.py
Pure Financial Engine         →  financial_engine/ (zero external deps)
Persistence                   →  app/models.py (SQLAlchemy ORM), app/db.py
External Integrations         →  app/services/gateway.py (PayPal / Mock)
Async Job Queue               →  app/services/jobs.py, scripts/worker.py, scripts/scheduler.py
Caching / Rate Limiting       →  Redis (token bucket, read-model cache, PayPal token cache)
```

### Layer Responsibilities

| Layer | Responsibility | Files |
|-------|---------------|-------|
| **HTTP** | Request parsing, auth, idempotency, rate limiting, ETags | `app/main.py`, `app/api/routes.py` |
| **Service** | Financial orchestration, two-phase webhook ingest, settlement lifecycle | `app/services/financial_service.py` |
| **Engine** | Deterministic money math, rules, settlement, auction, validation | `financial_engine/` |
| **ORM** | SQLAlchemy models, append-only ledger triggers, RLS-ready | `app/models.py` |
| **DB** | Engine factory, session management, migration assertions | `app/db.py` |
| **Gateway** | PayPal sandbox abstraction, contact resolution, webhook verification | `app/services/gateway.py` |
| **Jobs** | Durable Postgres job queue, outbox relay, claim/complete/fail | `app/services/jobs.py` |
| **Worker** | Drains provider events, outbox relay, due jobs | `scripts/worker.py` |
| **Scheduler** | Advisory-lock leadership, scheduled job enqueuing | `scripts/scheduler.py` |

### Core Guarantees

- **No lost events**: Two-phase provider webhook ingest (phase A persists raw body, phase B applies under cycle lock).
- **Append-only ledger**: Ledger events can never be updated or deleted — corrections create linked reversal records.
- **Deterministic money**: All amounts stored in minor units (integer); `Money.to_major_string()` for currency-exponent-safe serialization.
- **Idempotency**: `Idempotency-Key` required on all state-changing requests; same key + same body replays stored response.
- **Human-in-the-loop**: AI agents can only propose; humans approve with step-up auth; mandates are hash-locked and single-use.
- **Row-Level Security**: Postgres RLS keyed by `app.current_user_id`, enforced with `FORCE ROW LEVEL SECURITY`.

---

## Project Structure

```
backend/
├── alembic/                    # Database migrations (PostgreSQL only)
│   ├── versions/
│   │   ├── 0001_baseline_schema.py
│   │   ├── 0002_user_contacts.py
│   │   └── 0003_rls_policies.py
│   └── alembic.ini
├── app/                        # FastAPI application layer
│   ├── __init__.py
│   ├── auth.py                 # JWT auth, actor resolution, RLS session variable
│   ├── config.py               # Environment configuration, secure-config assertions
│   ├── db.py                   # Engine factory, session management, RLS guard SQL
│   ├── errors.py               # ServiceError, Conflict, Forbidden, NotFound, Unprocessable
│   ├── main.py                 # FastAPI app factory, middleware, exception handlers
│   ├── models.py               # SQLAlchemy ORM models, EncryptedString TypeDecorator
│   ├── presets.py              # Default ruleset presets
│   ├── schemas.py              # Pydantic request/response schemas
│   └── services/               # Business logic orchestration
│       ├── __init__.py
│       ├── celery_app.py       # Celery application (Redis broker/backend)
│       ├── celery_tasks.py     # Celery task definitions
│       ├── financial_service.py # Service layer: settlement, webhooks, payouts, mandates
│       ├── gateway.py          # PayPal gateway abstraction, contact resolution
│       ├── jobs.py             # Durable job queue, outbox relay
│       ├── jobs_tasks.py       # Celery job dispatch tasks
│       ├── money_alerts.py     # Money-specific operational alerts
│       └── read_models.py      # Read models with Redis cache + ETags
├── financial_engine/           # PURE mathematical calculations (no DB, no FastAPI)
│   ├── __init__.py
│   ├── money.py                # Integer minor-unit money, rounding
│   ├── rules.py                # Versioned rulesets & SHA-256 fingerprints
│   ├── contributions.py        # Contribution obligation calculations
│   ├── auction.py              # Bid validation, eligibility, tie-breakers
│   ├── payout_modes.py         # Auction, rotation, lottery, early payout modes
│   ├── settlement.py           # Settlement math (winner payout, commission, dividends)
│   ├── validation.py           # The 12 financial invariants
│   ├── states.py               # Cycle state machine
│   ├── ledger.py               # Balanced double-entry journals & chart of accounts
│   ├── reconciliation.py       # Provider reconciliation & HMAC verifier
│   └── risk.py                 # Rule-based risk indicators
├── scripts/                    # Long-running processes
│   ├── __init__.py
│   ├── worker.py               # Worker: provider events, outbox relay, due jobs
│   ├── scheduler.py            # Scheduler: advisory lock, scheduled job enqueuing
│   ├── seed_demo.py            # Demo data seeding
│   └── simulator.py            # Cycle simulation for testing
├── tests/                      # Pytest suite (unit, property-based, integration)
├── financial_engine/           # (see above)
├── .env                        # Local environment variables (NOT committed)
├── .env.example                # Environment variable template
├── chitcircle.db               # Local SQLite database (NOT committed)
├── pytest.ini                  # Pytest configuration
└── requirements.txt            # Python dependencies
```

---

## Prerequisites

- **Python 3.11+**
- **pip** or **uv**
- **Docker & Docker Compose** (for PostgreSQL 16 — optional for local dev/tests which use SQLite)
- **Redis** (optional for local dev — rate limiting, caching, and PayPal token cache fail open if unavailable)

---

## Quickstart

### 1. Create and activate a virtual environment

```bash
cd backend

python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# or: .venv\Scripts\activate     # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your values (see Environment Variables below)
```

### 4. Start PostgreSQL (optional — for production-like local dev)

```bash
cd ..
docker compose up -d
cd backend
```

### 5. Run the test suite

```bash
pytest
```

Tests run on an in-memory SQLite database by default, so Docker is not required.

### 6. Start the development server

```bash
uvicorn app.main:app --reload --port 8000
```

Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

---

## Environment Variables

Copy `.env.example` to `.env` and fill in real values. All variables:

| Variable | Description | Default | Required in Production |
|----------|-------------|---------|----------------------|
| `DATABASE_URL` | SQLAlchemy database URL (PostgreSQL 16 or SQLite) | `postgresql+psycopg://chitcircle:chitcircle@localhost:5432/chitcircle` | Yes |
| `WEBHOOK_SECRET` | Shared secret for verifying signed provider callbacks (HMAC-SHA256) | *(none)* | **Yes** |
| `PAYPAL_CLIENT_ID` | PayPal Sandbox client ID | *(none)* | For PayPal integration |
| `PAYPAL_CLIENT_SECRET` | PayPal Sandbox client secret | *(none)* | For PayPal integration |
| `PAYPAL_BASE_URL` | PayPal API base URL | `https://api-m.sandbox.paypal.com` | Use `api-m.paypal.com` in prod |
| `PAYPAL_WEBHOOK_ID` | PayPal webhook ID for certificate-based verification | *(none)* | For PayPal webhooks |
| `JWT_SECRET_KEY` | Secret for signing/verifying JWT tokens | *(none — insecure default rejected)* | **Yes** |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` | No |
| `JWT_EXPIRATION_MINUTES` | JWT token expiry in minutes | `15` | No |
| `REDIS_URL` | Redis URL for caching, rate limiting, token cache | `redis://localhost:6379/0` | No |
| `APP_ENV` | Deployment environment: `development`, `test`, `staging`, `production` | `development` | Yes |
| `ALLOW_ACTOR_HEADERS` | Enable `X-Actor-Id`/`X-Actor-Role` dev stub (off in production) | `true` | No |
| `AGENT_PROPOSAL_ENABLED` | Feature flag for agent proposals | `true` | No |
| `AGENT_EXECUTION_ENABLED` | Feature flag for agent mandate execution | `true` | No |
| `ENCRYPTION_KEY` | Base64-encoded 32-byte key for `UserContact.value` field encryption | *(none)* | For PII encryption |
| `READ_REPLICA_DATABASE_URL` | Read-replica database URL (empty = use primary for all reads) | *(empty)* | No |

### Secure Configuration

When `APP_ENV=production`, the application refuses to boot if:

- `JWT_SECRET_KEY` is unset or still the insecure development default
- `WEBHOOK_SECRET` is unset

The `X-Actor-Id`/`X-Actor-Role` development stub is automatically disabled in production regardless of `ALLOW_ACTOR_HEADERS`.

### Generating a Secure JWT Secret

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Generating an Encryption Key

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## Database Setup

### Option A: SQLite (default for tests and local dev)

No setup required. SQLAlchemy `create_all()` creates the schema on first connection. Alembic migrations are skipped for SQLite.

### Option B: PostgreSQL 16 (production-like)

1. Start PostgreSQL:

```bash
cd ..  # repo root
docker compose up -d
cd backend
```

2. Ensure `DATABASE_URL` in `.env` points to the running PostgreSQL instance.

3. Run Alembic migrations:

```bash
alembic upgrade head
```

4. Start the application. On startup, `assert_migrations_applied()` verifies the schema is at `alembic upgrade head` and refuses to boot if behind.

---

## Running the Server

```bash
# Development (auto-reload)
uvicorn app.main:app --reload --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

The app exposes:

- **REST API**: `http://localhost:8000/v1/...`
- **OpenAPI docs**: `http://localhost:8000/docs`
- **Health check**: `GET /v1/health`

### Startup Checks

On startup the application:

1. Calls `config.assert_secure_config()` — refuses to boot with insecure production config
2. Calls `db.init_db()` — creates schema on SQLite; no-op on PostgreSQL
3. Calls `db.assert_migrations_applied()` — refuses to boot if PostgreSQL schema is behind Alembic head

---

## Running Tests

```bash
# Full test suite
pytest

# Specific test file
pytest tests/test_api_integration.py

# With verbose output
pytest -v

# Stop on first failure
pytest -x
```

Tests run on an in-memory SQLite database. PostgreSQL CI uses per-test truncation isolation (see `tests/conftest.py`).

The test suite covers:

- Settlement lifecycle and the 12 financial invariants
- Two-phase webhook ingest (persist-then-apply, crash safety)
- Outbox relay with `SKIP LOCKED` and `published_at`
- HTTP idempotency (428 when missing key, replay, conflict on different body)
- JWT authentication and actor resolution
- PayPal gateway serialization (exact JPY/KWD amounts)
- Agent proposal → approval → mandate execution flow
- Ops console endpoints (ledger search, job replay, circle pause/resume)
- Read models with Redis cache + ETags / 304 responses
- Rate limiting (token bucket, 60 req/min)

---

## Running the Worker

The worker drains provider events, relays the outbox, and processes due jobs:

```bash
# Single pass (cron-friendly)
python -m scripts.worker --once

# Continuous loop (2-second interval)
python -m scripts.worker
```

### What the Worker Does

1. **`process_pending_provider_events()`** — Applies RECEIVED/PARKED provider events under cycle lock with exponential backoff and dead-lettering after 5 attempts.
2. **`relay_outbox()`** — Publishes unpublished outbox rows into the job queue with `SELECT ... FOR UPDATE SKIP LOCKED` and marks them `published_at`.
3. **`run_once()`** — Claims due jobs from the Postgres Job table and dispatches them.

### Celery (Optional, Phase 3)

Celery is configured (`requirements.txt` includes `celery>=5.3`) and can be used instead of or alongside the standalone worker:

```bash
# Process due jobs via Celery worker
celery -A app.services.celery_app worker

# Also run the periodic dispatcher (Celery Beat)
celery -A app.services.celery_app worker --beat
```

Celery uses Redis as broker and result backend. The Postgres `Job` table remains the durable source of truth; Celery only executes and retries job dispatch.

---

## Running the Scheduler

The scheduler acquires a PostgreSQL advisory lock (single leader) and enqueues recurring jobs:

```bash
# Single pass
python -m scripts.scheduler --once

# Continuous loop (30-second interval)
python -m scripts.scheduler
```

### Registered Scheduled Tasks

| Task | Interval | Purpose |
|------|----------|---------|
| `invariant_check` | Nightly (86400s) | Enqueue a job to verify ledger/obligation consistency |
| `provider_reconciliation` | Nightly (86400s) | Enqueue a job to sync with PayPal |
| `dead_letter_reaper` | Hourly (3600s) | Enqueue a job when DEAD jobs exist |
| `ledger_imbalance` | Every 5 min (300s) | Alert when a cycle's ledger amounts don't sum to zero |
| `dead_letter_spike` | Every 5 min (300s) | Alert when dead-lettered jobs exceed threshold |

---

## Alembic Migrations

Migrations manage schema changes for PostgreSQL. SQLite is exempt (schema created by `create_all`).

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply all pending migrations
alembic upgrade head

# Check current migration status
alembic current

# Roll back one migration
alembic downgrade -1
```

### Migration Files

| File | Description |
|------|-------------|
| `0001_baseline_schema.py` | Initial schema: users, circles, members, cycles, obligations, settlements, ledger events, bids, lottery, approvals, provider events, outbox, jobs, feature flags, agent mandates, proposed actions, API idempotency |
| `0002_user_contacts.py` | `user_contacts` table with encrypted `value` column |
| `0003_rls_policies.py` | Row-level security policies on circles, members, cycles, settlements |

---

## API Endpoints

All endpoints are prefixed with `/v1`.

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/login` | OAuth2 password login, returns JWT |
| `POST` | `/auth/register` | Register a new user (demo) |

### Circles

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/circles` | Create a circle with versioned ruleset and members |
| `GET` | `/circles/{circle_id}` | Get circle details |
| `POST` | `/circles/{circle_id}/rulesets` | Add a new ruleset version |
| `PUT` | `/circles/{circle_id}/members/{member_id}/security` | Set member security status |
| `GET` | `/circles/{circle_id}/members/{member_id}/risk` | Get member risk indicator |

### Cycles

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/circles/{circle_id}/cycles` | Create a cycle |
| `GET` | `/cycles/{cycle_id}` | Get cycle details |
| `POST` | `/cycles/{cycle_id}/open` | Open a cycle (issues contribution obligations) |
| `POST` | `/cycles/{cycle_id}/auction/open` | Open auction for bidding |
| `POST` | `/cycles/{cycle_id}/auction/bids` | Submit a bid |
| `GET` | `/cycles/{cycle_id}/auction/bids` | List bids |
| `POST` | `/cycles/{cycle_id}/auction/close` | Close auction, select winner |
| `POST` | `/cycles/{cycle_id}/recipient` | Select recipient (fixed rotation or lottery) |
| `POST` | `/cycles/{cycle_id}/early-payout` | Request early payout with agreed discount |
| `POST` | `/cycles/{cycle_id}/settlement` | Calculate cycle settlement |
| `GET` | `/cycles/{cycle_id}/ledger` | Cursor-paginated ledger |
| `POST` | `/cycles/{cycle_id}/resume` | Resume cycle from ON_HOLD |
| `POST` | `/cycles/{circle_id}/disputes` | Open a dispute |
| `POST` | `/cycles/{circle_id}/disputes/resolve` | Resolve a dispute |

### Settlements

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/settlements/{settlement_id}` | Get settlement |
| `POST` | `/settlements/{settlement_id}/approvals` | Approve/reject settlement |
| `POST` | `/settlements/{settlement_id}/payout` | Execute payout |
| `POST` | `/settlements/{settlement_id}/payout/check` | Check payout status |
| `GET` | `/settlements/{settlement_id}/reconciliation` | Reconciliation report |
| `POST` | `/settlements/{settlement_id}/finalize` | Finalize settlement |

### Provider Webhooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/webhooks/provider` | Signed provider callbacks (phase A: persist only) |

### Collections

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/collections/create` | Create PayPal invoice for member contribution |

### Read Models (with ETag caching)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/circles/{circle_id}/timeline` | Member × cycle timeline grid |
| `GET` | `/circles/{circle_id}/dashboard` | Organizer dashboard summary |
| `GET` | `/circles/{circle_id}/members/{member_id}/view` | Member-specific view |

### Agent Mandates

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/circles/{circle_id}/proposed-actions` | Propose a mandate-gated action |
| `POST` | `/proposed-actions/{proposal_id}/approve` | Human approves proposal, issues mandate |
| `POST` | `/mandates/{mandate_id}/execute` | Execute an approved mandate |
| `POST` | `/mandates/{mandate_id}/revoke` | Revoke an unused mandate |
| `GET` | `/circles/{circle_id}/proposed-actions` | List proposals |
| `GET` | `/circles/{circle_id}/mandates` | List mandates (audit trail) |

### Ops Console (organizer only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/ops/ledger/search` | Search ledger events |
| `POST` | `/ops/jobs/{job_id}/replay` | Replay a dead-lettered job |
| `POST` | `/ops/reconciliation/rerun` | Enqueue provider reconciliation job |
| `POST` | `/ops/circles/{circle_id}/pause` | Pause a circle (kill switch) |
| `POST` | `/ops/circles/{circle_id}/resume` | Resume a paused circle |

---

## Key Design Decisions

### Two-Phase Webhook Ingest

Provider callbacks are handled in two phases:

1. **Phase A** (webhook handler): Verifies signature, persists the raw body to `provider_events` as `RECEIVED`, returns `200` immediately. No business logic, no locks.
2. **Phase B** (worker): Applies the durable row under cycle lock, marks it `PROCESSED`. Failures park the row for retry with exponential backoff; permanent validation errors mark it `REJECTED`.

This guarantees no lost events even if the process crashes between callback receipt and durable processing.

### Append-Only Ledger

`LedgerEventRow` has SQLAlchemy event listeners that raise `LedgerImmutableError` on any `UPDATE` or `DELETE`. Corrections create linked reversal events rather than mutating history. A PostgreSQL trigger enforces the same at the database level.

### Row-Level Security

Postgres RLS policies on `circles`, `members`, `cycles`, and `settlements` are keyed by `current_setting('app.current_user_id', true)`. The `get_current_actor()` dependency sets this session variable after authenticating the caller. `FORCE ROW LEVEL SECURITY` ensures policies apply even to the table owner.

### Idempotency

All state-changing methods (`POST`/`PUT`/`PATCH`/`DELETE`) require an `Idempotency-Key` header. The middleware stores `(key, actor_id, request_hash, response, status_code)` in `api_idempotency`. Replays return the stored response with `X-Idempotency-Replayed: true`; same key with a different body returns `422`.

### Encrypted PII

`UserContact.value` uses `EncryptedString`, a SQLAlchemy `TypeDecorator` backed by Fernet (AES-256). Plaintext never hits disk — encryption/decryption happens entirely in the application layer, keyed by `ENCRYPTION_KEY`.

### Rate Limiting

Redis token-bucket per `(user_id, path)` at 60 req/min. Fails open (allows the request) if Redis is unavailable.

### Read Models

Read models query write tables directly and cache results in Redis with a 60s TTL. ETags are SHA-256 of the serialized payload; clients can use `If-None-Match` to receive `304 Not Modified`.

---

## Configuration Reference

### `.env.example`

The `.env.example` file at the repo root documents every environment variable with development defaults and production annotations. Copy it to `.env` and adjust for your deployment.

### Production Checklist

- [ ] `APP_ENV=production`
- [ ] `JWT_SECRET_KEY` set to a strong random value (not the dev default)
- [ ] `WEBHOOK_SECRET` set to a shared secret for provider callback verification
- [ ] `DATABASE_URL` points to PostgreSQL 16
- [ ] `ENCRYPTION_KEY` set to a base64-encoded 32-byte Fernet key
- [ ] `ALLOW_ACTOR_HEADERS` effectively disabled (enforced automatically in production)
- [ ] Alembic migrations applied (`alembic upgrade head`)
- [ ] Redis running for rate limiting and caching (optional — fails open)
- [ ] Worker process running (`python -m scripts.worker`)
- [ ] Scheduler process running (`python -m scripts.scheduler`)

---

## License

This project was built for the PayPal AI Hackathon. See repository license details for terms.