# ChitCircle Web (Phases 1–2)

Next.js 15 (App Router) + TypeScript, plain CSS with design tokens. Mobile-first (360–430 px), light/dark/system theme.
Implements **Phase 1** (shell, theme, nav, components, typed API client) and **Phase 2** (read-only circles, rounds,
ledger/activity, settlement, reconciliation). No write paths, no payments.



## Run
```bash
npm install
npm run dev            # demo mode works with no backend
npm test               # 64 tests (vitest + testing-library)
npm run typecheck && npm run build
```
Live API (optional): copy `.env.example` to `.env.local`, start the FastAPI backend (`uvicorn app.main:app`), set
`CHITCIRCLE_API_URL`. The browser calls same-origin `/api/backend/*`, which Next proxies to the backend (the backend
has no CORS; `/webhooks/*` is deliberately **not** proxied). Use **Sign in (development)** with an actor ID.

## Routes
`/welcome`, `/sign-in` (dev only), `/app/home`, `/app/circles`, `/app/circles/[id]`,
`/app/circles/[id]/cycles/[cycleId]`, `/app/activity`, `/app/settlements/[id]`, `/app/settlements/[id]/reconciliation`,
`/app/profile`, `/app/help`.

## Honest boundaries (see also the in-app Help screen)
- **No list endpoints exist**, so Home/Circles/Activity are built from circle/round IDs the user opens, saved in this
  browser (`lib/saved.ts`), and loaded from the authoritative GET endpoints. The UI says so.
- **Auth is a stub.** `X-Actor-*` headers are sent for identification only; roles are derived from server data
  (`organizer_id`, member IDs), never from a client toggle (`lib/permissions.ts`).
- **No frontend financial maths.** Amounts are server integers formatted by one adapter (`lib/money.ts`).
  `GET /cycles` and `/circles` carry no currency, so it is taken from ledger/settlement when present, else the configured
  default and marked "assumed" (live mode).
- **Money status never overstated:** "Contribution due" ≠ payment; approved ≠ paid; payout "requested/submitted" ≠
  confirmed; a stub-gateway notice shows in live mode.
- Demo data is fictional and labelled. Create circle, bids, approvals, payouts, join/invite, notifications, and online
  payment are **not implemented** (Phases 3–5 / missing backend APIs). `useSingleFlight` (duplicate-submit guard) is
  ready and tested for those commands.

## Deviations from the design spec
- Secondary text `#666D68` and darker income/expense/warning *text* tokens, for 4.5:1 contrast. Fills keep spec colors.
- The Stitch mock's "funds held in escrow / RBI compliant" copy was intentionally **not** reproduced (unverified claim).
- Spec's "Create account" is replaced by "Explore the demo" until an auth API exists.
