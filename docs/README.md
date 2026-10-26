# ChitCircle Documentation

Phase-wise implementation plan and system design for ChitCircle, a PayPal-powered platform that lets the organizer of a community savings circle (chit fund, tanda, susu, stokvel, chama, hui and similar) run it without the hassle. Designed for **100,000+ users** from day one of the architecture, even though the hackathon prototype is much smaller.

Status: planning documents, written Oct 24, 2026, against the `chitcircle-financial-engine` prototype (Python, FastAPI, SQLAlchemy, PostgreSQL, 86 passing tests). Anything marked **VERIFY** is an assumption or an external fact that must be confirmed before you rely on it.

## Headline decisions

1. **Modular monolith plus background workers, not microservices.** At 100k users the load is modest. The hard problems are correctness, webhook bursts, notification fan-out and due-date spikes, none of which need a service mesh. See `adr/0001`.
2. **PostgreSQL is the only system of record**, including the ledger. Redis is for caching, queues and rate limits only. **Never serve a money decision from cache.** See `04-caching-strategy.md` and `adr/0004`.
3. **Transactional outbox now, Kafka later.** Kafka is adopted only when stated triggers are hit. See `adr/0003`.
4. **Non-custodial funds flow.** The platform computes and orchestrates; money moves between members and the organizer's own payment account. This avoids holding client funds. See `adr/0002`.
5. **PayPal cannot serve India-domestic circles.** Public sources report PayPal stopped domestic payments in India in 2021 and supports cross-border only (**VERIFY** current status). PayPal fits diaspora and cross-border circles. India-domestic needs another rail behind the same gateway interface. See `06-paypal-integration.md`.
6. **Lottery mode is off by default.** PayPal's acceptable use policy restricts prize-draw style activity and money-transmission or escrow-like services without approval (**VERIFY** current wording). See `07-security-privacy-compliance.md`.
7. **Web first (Next.js), mobile second (Expo / React Native)**, sharing a typed client generated from FastAPI's OpenAPI spec. See `09-clients-web-and-mobile.md`.
8. **Agents propose, humans approve, the engine calculates.** An LLM never computes or moves money. See `10-ai-agents.md`.

## Reading order

| # | Document | Read it for |
|---|---|---|
| 01 | `01-requirements-and-capacity.md` | Targets, capacity math, scaling triggers |
| 02 | `02-system-architecture.md` | Components, flows, module boundaries |
| 03 | `03-data-model-and-consistency.md` | Schema, locking, idempotency, outbox, migrations |
| 04 | `04-caching-strategy.md` | What to cache, what never to cache, invalidation |
| 05 | `05-async-events-scheduling-realtime.md` | Workers, webhooks, scheduler, live auctions |
| 06 | `06-paypal-integration.md` | Funds flow, PayPal flows, reconciliation, India caveat |
| 07 | `07-security-privacy-compliance.md` | Auth, PII, regulatory posture |
| 08 | `08-observability-reliability.md` | SLOs, money-specific alerts, DR |
| 09 | `09-clients-web-and-mobile.md` | Next.js, Expo, shared client, notifications |
| 10 | `10-ai-agents.md` | Agent design and guardrails |
| 11 | `11-testing-strategy.md` | Test pyramid, concurrency, load tests |
| 12 | `12-infrastructure-and-deployment.md` | Render for the hackathon, production path |
| | `phases/` | Phase 0 to 6 with tasks and exit criteria |
| | `adr/` | Architecture decision records |
| | `appendix/` | Sponsor tool plan, open questions, glossary |

## Phase overview

| Phase | Goal | Timing |
|---|---|---|
| 0 | Foundation and spikes | Oct 24 to 26, 2026 |
| 1 | Hackathon MVP with real PayPal sandbox | Oct 27 to Nov 11, 2026 |
| 2 | Production hardening of the core | About 4 to 6 weeks after the hackathon |
| 3 | Scale architecture (cache, workers, read models) | About 6 to 8 weeks |
| 4 | Mobile app, notifications, live auctions | About 6 to 8 weeks |
| 5 | Global expansion, extra payment rails, compliance | About 6+ weeks |
| 6 | Scale-out and maturity | Ongoing, trigger-driven |

**Hackathon deadline:** Nov 12, 2026, 12:00pm PST per the Devpost page, which is about 1:30am IST on Nov 13. **VERIFY** on Devpost and plan to submit by the evening of Nov 11 IST.

## Conventions

- "Engine" means `financial_engine/` (pure calculation, no I/O). "Service layer" means `app/services/`.
- Money is always integer minor units plus a currency. Floats never appear in money code.
- Every state change that matters writes a ledger event with an idempotency key.
