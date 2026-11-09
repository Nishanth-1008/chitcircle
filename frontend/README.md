# ChitCircle Web

Next.js 15 (App Router) + TypeScript, plain CSS with design tokens. Responsive: sidebar on desktop, bottom
navigation on mobile, light/dark/system theme. Talks only to the FastAPI backend through the same-origin
`/api/backend/*` proxy (`next.config.mjs`).

## Run

```bash
cp .env.example .env.local     # CHITCIRCLE_API_URL=http://localhost:8000
npm install
npm run dev                    # http://localhost:3000 (needs the backend running)
npm test                       # vitest + testing-library
npm run typecheck && npm run build
```

Create an account on `/register`. To join someone's circle, register with the email the organizer invited:
the seat links to your account automatically.

## Screens

| Route | What it does |
|---|---|
| `/welcome`, `/sign-in`, `/register` | JWT sign-in and sign-up (`POST /auth/login`, `/auth/register`) |
| `/app/home` | Everything that needs you across circles, dues per currency, your circles |
| `/app/circles`, `/app/circles/new` | Your circles; create a circle (tradition template, invites by email, rules, live plain-language summary) |
| `/app/circles/[id]` | Overview, rounds, members (security status, risk), member × round timeline, rules and versions |
| `/app/circles/[id]/cycles/[cycleId]` | Round workspace: role-aware next step, sealed/open bidding with the bid advisor, contributions, “why is my installment X?”, ledger, history, disputes |
| `/app/settlements/[id]` (+ `/reconciliation`) | Breakdown, approvals, payout release/check/confirm, three-way reconciliation, finalize |
| `/app/circles/[id]/agents` | Approvals inbox: run the collections agent, approve with step-up (issues a single-use mandate), run or revoke |
| `/app/activity` | Circle-wide shared ledger with filters and cursor paging |
| `/app/profile`, `/app/help` | PayPal email, theme, connection status, sign out; FAQ |

## Rules the client follows

- **No money math in the browser.** Amounts are server integers (minor units) formatted by `lib/money.ts`; typed
  amounts are parsed to minor units with string arithmetic. Bid previews, explanations and settlements come from
  the engine.
- **The server decides permissions.** Role-specific UI uses `my_role` / `my_member_id` from the API; every command
  is re-checked server-side.
- **Money status is never overstated.** A contribution counts only once the provider confirms it; approved ≠ paid;
  a submitted payout is not confirmed. Auction installments are payable only after settlement (the dividend lowers them).
- **Every command is single-flight** (`useAction`) and sends a fresh `Idempotency-Key`.
- **Sandbox tools are labelled.** When the backend reports `sandbox_tools`, “Simulate confirmed payment” and
  “Simulate provider confirmation” send sandbox provider events through the real ingest pipeline.
