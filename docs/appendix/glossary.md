# Glossary

| Term | Meaning |
|---|---|
| **ROSCA** | Rotating savings and credit association: a group pays in each cycle and one member takes the pot |
| **Chit fund / kuri / chitty** | South Asian ROSCA, often with auctions and a foreman |
| **Tanda, susu, stokvel, chama, equb, hui, arisan, paluwagan, tontine** | Names for similar circles across communities |
| **Organizer / foreman / banker** | The person who runs the circle |
| **Chit value (V)** | Total pot per cycle |
| **Installment / contribution (C)** | What each member owes per cycle, V divided by members |
| **Discount (D)** | Amount the winner gives up in a discount-funded payout |
| **Winner payout (W)** | Amount the winner receives |
| **Commission (F)** | Organizer's fee |
| **Dividend pool (P)** | Discount minus commission, shared among members |
| **Net contribution** | Installment minus the member's dividend |
| **Prized / non-prized** | Has already won, or has not yet won |
| **Agreed discount** | Early payout at pre-agreed terms with no competing bids |
| **Ruleset** | Versioned, immutable set of rules for a circle, identified by a fingerprint |
| **Jurisdiction profile** | Data that restricts which options a circle may use in a place |
| **Ledger event** | Append-only record of something that happened to money |
| **Journal** | Balanced double-entry postings derived from events |
| **Reconciliation** | Matching provider records with the ledger |
| **Idempotency key** | Stable identifier that makes retries safe |
| **Outbox** | Table written in the same transaction as state changes, relayed to workers |
| **Read model** | Precomputed view built from events for fast reads |
| **ledger_seq** | Per-circle counter that versions cache keys and ETags |
| **Non-custodial** | The platform does not hold member funds |
| **PgBouncer** | Connection pooler for PostgreSQL |
| **SSE** | Server-Sent Events: one-way real-time stream from server to client |
| **SLO** | Service-level objective |
| **ADR** | Architecture decision record |
