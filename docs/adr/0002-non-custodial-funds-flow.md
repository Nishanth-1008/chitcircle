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
