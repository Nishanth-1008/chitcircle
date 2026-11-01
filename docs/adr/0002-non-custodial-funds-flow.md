# ADR 0002: Non-custodial funds flow

**Status:** Accepted (pending partner and legal confirmation)

## Context
Circles pool money. Holding that money, or acting as an escrow, can be a regulated money-transmission activity and PayPal's acceptable use policy requires pre-approval for money-service and escrow-type activity (**VERIFY** current text). The platform's value is calculation, orchestration, visibility and automation, not custody.

## Decision
Funds move between members and the organizer's own payment account. ChitCircle computes, validates, approves, records and reconciles. The platform does not hold a pooled balance. Revenue is a software fee, not a spread on funds.

## Consequences
- Lower regulatory burden and clearer positioning as software for organizers.
- Requires organizer onboarding to the payment partner (verification, linked account).
- The organizer carries custody risk; mitigated by visible ledger, security workflow, and dispute log.
- The ledger mirrors and checks provider movements; reconciliation is mandatory.
- Some conveniences (instant pot guarantees, platform-funded advances) are off the table.

## Alternatives considered
- **Custodial pooled account:** best experience, but needs licences and a heavy compliance stack.
- **Smart-contract escrow:** removes custody but excludes most target users and conflicts with fiat rails.

## Revisit when
A licensed partner offers pooled accounts as a service, or the company obtains the required licences.

## Clarification: custody is about funds, not about who calls the API

Non-custodial refers to **where money sits and whose account it is in**, not to *what triggers* an
integration call. ChitCircle holds no pooled balance either way: funds still move between members and the
organizer's own payment account.

An agent that executes an **approval-gated, mandate-bound** call against the organizer's own account (see
`adr/0007`) does not create custody. Nothing is held by the platform; no new account is opened; the ledger
still mirrors and reconciles provider movements rather than being the bank.

PayPal's acceptable use policy applies **equally** to agent-initiated and human-initiated calls
(**VERIFY** current wording). The distinction that matters for policy is the use case (chit-style savings
groups, pooled or escrow-like behaviour, prize draws), not whether a human or an approved agent pressed the
button.
