# ChitCircle Financial Engine (v1.0 implementation)

Python + FastAPI + PostgreSQL + Pytest implementation of the *ChitCircle Financial Engine – Financial Rules and
Technical Specification*. Principle: **calculate → validate → approve → execute payment → reconcile → finalize.**

```
backend/
├── financial_engine/   PURE calculation code (no FastAPI / DB / PayPal / UI imports; enforced by a test)
│   money.py            exact integer minor-unit money, explicit rounding, rounding-adjustment records
│   rules.py            versioned, immutable rulesets (+ fingerprint hash)
│   contributions.py    C = V/N, net contribution (an obligation, never cash)
│   auction.py          bid validation, grace-period eligibility, winner + tie-break + no-bid fallback
│   payout_modes.py     fixed rotation, auditable lottery, agreed-discount early payout
│   settlement.py       W, F, P, dividends, remainder, balance equation
│   validation.py       the 12 financial invariants (section 15)
│   states.py           cycle state machine (+ ON_HOLD / FAILED / DISPUTED)
│   ledger.py           append-only events, balanced double-entry journals (proposed chart of accounts)
│   reconciliation.py   payment/payout reconciliation, HMAC callback verifier
│   risk.py             transparent rule-based risk indicators (advisory only)
├── app/                FastAPI layer: routes, SQLAlchemy models, service layer, payout gateway abstraction
└── tests/              unit, property-based (Hypothesis), and API/DB integration tests
```

## Run

```bash
cd backend
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
pytest                                   # 86 tests; integration tests use in-memory SQLite
docker compose -f ../docker-compose.yml up -d
cp .env.example .env && export $(cat .env | xargs)
uvicorn app.main:app --reload            # tables are created on startup; docs at /docs
```

## Lifecycle through the API

1. `POST /circles` (ruleset + members) → `POST /circles/{id}/cycles` → `POST /cycles/{id}/open` (creates obligations + `CONTRIBUTION_DUE`)
2. Recipient: `auction/open` → `auction/bids` → `auction/close`, or `POST /cycles/{id}/recipient` (rotation / lottery), or `POST /cycles/{id}/early-payout`
3. `POST /cycles/{id}/settlement` (idempotent; one settlement per cycle, enforced by a unique constraint)
4. `POST /settlements/{id}/approvals` → `POST /settlements/{id}/payout` (idempotency key `payout:{settlement_id}`)
5. Signed provider callbacks: `POST /webhooks/provider` (`X-Signature` = HMAC-SHA256 of raw body) for `PAYMENT`, `REFUND`, `PAYOUT`
6. `POST /settlements/{id}/finalize` – only succeeds when approvals, security checks, provider reconciliation and the
   ledger (all journals balanced, circle pool nets to zero) are clean. Otherwise it returns 409 with the discrepancies.

Auth is a stub (`X-Actor-Id`, `X-Actor-Role` headers); replace it with real authentication. Services still enforce
that organizer-only actions come from the circle's organizer, the recipient cannot approve their own payout, and
members can only bid for themselves.

## Settlement model

- Discount-funded (auction, agreed discount): `W = V − D`, `P = D − F`, `Σ net = W + F + R`
- No-discount (rotation, lottery): `W = V − F`, `P = 0`, `Σ net = W + F`
- `R` is the explicit rounding remainder of the dividend split. It is recorded as a `RoundingAdjustment` and posted
  to the configured destination; if a remainder arises and no destination is configured, the settlement is rejected.
- The ₹1,00,000 / 20 members / ₹12,000 discount example is a permanent regression test
  (`tests/test_settlement.py::test_worked_example_regression`, and end-to-end in `test_api_integration.py`).

## Spec section 20 – reserved decisions (NOT guessed)

| Open item | How the code treats it |
|---|---|
| Default commission base/rate | No default: `commission.base` and `rounding` are required ruleset fields |
| Rounding method / remainder destination | Method required per commission; destination optional and **required at runtime** if a remainder occurs |
| Default grace period | No default: `grace_period_days` is required |
| Tie-break / lottery audit | Configurable tie-break (`EARLIEST_BID`, `LOWEST_POSITION`, `SEEDED_RANDOM`). Lottery = committed SHA-256 seed + deterministic draw, verifiable via `verify_lottery`; this is a placeholder for the final audit method |
| Dividend eligibility | `ELIGIBLE_MEMBERS` is implemented as "not in arrears past the grace period at calculation time" – confirm with product |
| Approval policy per mode | One `required_approvals` count per ruleset (≥ 1, cannot be bypassed) |
| Chart of accounts | A minimal **proposed** chart is in `ledger.py` |
| Jurisdiction rules | `jurisdiction_profile` is stored but does not grant legal permission |
| PayPal sandbox payouts | `PayPalPayoutsGateway` is a stub; `MockGateway` is used. Callback verification is HMAC – swap in the provider's own verifier |
| Disputes / chargebacks / failed transfers | Disputes move the cycle to `DISPUTED`; failed payouts to `FAILED`; resume only to the recorded prior state. Chargeback handling is not modelled beyond `REFUND` events |

## Known limitations

- Tested against SQLite only in this environment. Row locks (`SELECT … FOR UPDATE`), the Postgres append-only trigger
  and the unique constraints are written for PostgreSQL but should be exercised in your own Postgres CI, including a
  true concurrent-request test.
- No Alembic migrations yet (`create_all` on startup).
- A payout whose provider outcome is unknown stays `PAYOUT_PENDING`; retrying `POST …/payout` re-sends with the same
  idempotency key, and `POST …/payout/check` looks it up.
- Overpayments are not auto-refunded: they surface as `OVERPAID` and block finalization until a `REFUND` is recorded.
