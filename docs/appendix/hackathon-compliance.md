# Hackathon Compliance and Judging Checklist

Companion to `../README.md` and the phase plans. This file tracks how ChitCircle maps to the PayPal AI
Hackathon judging requirements and what still must be checked against the competition's Official Rules.

> **VERIFY — everything in section 4.** We have **not** read the Official Rules text. Section 4 is a
> placeholder to be filled from the **Official Rules** tab on Devpost before submission. Nothing below may
> be treated as confirmed until then. Likewise, the exact judging wording in section 1 must be checked
> against Devpost (**VERIFY**).

## 1. Judging requirements — status map

The five requirements as we understand them (**VERIFY** exact wording on Devpost):

| # | Requirement | Current status | Covered by |
|---|---|---|---|
| 1 | Meaningful PayPal integration | In progress: real `PayPalGateway` behind the gateway interfaces (invoice-based collection, payout with documented fallback), verified webhook receiver, `provider_events` → ledger, reconciliation; sandbox-first (Phase 0 spikes S1–S4 decide payout availability) | `06`, `10` §3.1, `adr/0007`, `phases/phase-1` |
| 2 | Meaningful AI | Designed and in build: collections agent proposes and, after human approval, executes through a single-use mandate; explainer; bid advisor; proposed-actions queue. Numbers always come from the engine | `10`, `adr/0007`, `phases/phase-1` |
| 3 | Working prototype | Phased: API + worker + Postgres on Render, seeded circles, 20-cycle simulator driving the real API, Next.js dashboard with Bryntum timeline, end-to-end sandbox payment | `02`, `12`, `phases/phase-1` |
| 4 | Sufficient documentation | This `docs/` corpus (architecture, data model, ADRs, phases, testing, ops) plus the judge-facing README checklist in section 2 | this file, `README.md` |
| 5 | Compliance with Official Rules | **Unverified.** See the placeholder checklist in section 4 — must be completed from the Official Rules tab | section 4 |

## 2. Judge-facing checklist for the repo README

The README should contain, in this order:

- [ ] **What the project does** — one paragraph: run a community savings circle (chit / tanda / susu /
      stokvel / chama) end to end without the manual hassle; PayPal-powered, designed for 100k+ users.
- [ ] **Architecture diagram** — modular monolith plus workers (from `02`).
- [ ] **"How we use PayPal"** — collection via invoice/order, verified webhooks into the ledger,
      settlement and payout, reconciliation; non-custodial (organizer's own account); sandbox only.
- [ ] **"How we use AI"** — the agent proposes, a human approves, the engine computes, execution happens
      through a single-use mandate (`adr/0007`). Include one concrete end-to-end example.
- [ ] **Run instructions** — clone, env vars, `docker compose up`, seed, run the simulator, start the API.
- [ ] **Demo link and video** — public URL and the short demo video.
- [ ] **Sponsor tools used and where** — see `sponsor-tools-plan.md`; state plainly which tools and where
      in the code they are used.
- [ ] **Honest limitations** — sandbox only / no real funds; India-domestic settlement is not possible
      through PayPal (see `06`); lottery mode disabled; legal posture not reviewed; mandate expiry and caps
      are v1 defaults pending tuning.

## 3. Pre-existing work

**Disclosure: the financial engine and its test suite predate the hackathon.** `financial_engine/`
(money, ledger, rules, settlement, auction, obligations, reconciliation, risk, states) and its tests were
written before the competition period; everything else in this plan is new work.

Plan:

- **Tag the pre-hackathon commit** (for example `pre-hackathon-v0`) so the baseline is identifiable.
- **Keep full commit history** — do **not** squash; reviewers must be able to see what predates the entry.
- **Include a pre-existing vs new work table in the README**, for example:

  | Area | Pre-existing | New (hackathon) |
  |---|---|---|
  | Pure financial engine + its tests | ✔ | |
  | PayPal gateway, verified webhooks, `provider_events` pipeline | | ✔ |
  | Agent + mandate system (`proposed_actions`, `agent_mandates`, `execute_mandate`) | | ✔ |
  | Web UI (Next.js dashboard, Bryntum timeline) | | ✔ |
  | Simulator driving the real API, seed presets | | ✔ |
  | Deployment, docs corpus | | partly ✔ (extend and document) |

- **Make the new work substantial**: PayPal integration, the agent and mandate system, the web UI and the
  simulator are the bulk of the submission.

**(VERIFY)** whether the Official Rules require a specific disclosure format for AI-generated code or for
pre-existing components — see section 4.

## 4. Official Rules placeholder checklist — MUST BE COMPLETED

Fill every row from the **Official Rules tab on Devpost**. We have **not** verified the rules text; do not
invent answers, and do not submit until this table is complete.

| # | Item | Our answer | VERIFY against the Official Rules |
|---|---|---|---|
| 4.1 | Pre-existing code policy (allowed? window? disclosure required?) | _TBD_ | VERIFY against the Official Rules |
| 4.2 | AI-generated code disclosure requirements | _TBD_ | VERIFY against the Official Rules |
| 4.3 | Eligibility: countries, age, team size, student status | _TBD_ | VERIFY against the Official Rules |
| 4.4 | Submission requirements: repo, write-up length, media, forms | _TBD_ | VERIFY against the Official Rules |
| 4.5 | Sponsor-tool requirements (which tools, minimum usage, prizes) | _TBD_ | VERIFY against the Official Rules |
| 4.6 | IP and licensing: licence for submitted code, sponsor IP terms | _TBD_ | VERIFY against the Official Rules |
| 4.7 | Deadline and time zone (currently assumed Nov 12 2026, 12:00pm PST) | _TBD_ | VERIFY against the Official Rules |

## 5. Related open questions

See `open-questions.md` for the technical, payments, legal and go-to-market questions, including the new
"Agents and mandates" section (caps, mandate expiry, second-approver thresholds, which PayPal calls the
agent may use in the sandbox).
