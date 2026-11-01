# ADR 0007: Approval-gated agent execution via single-use mandates

**Status:** Accepted

## Context

The original plan (`10-ai-agents.md`) said agents observe, explain, draft and propose only, and never
execute a money-moving action or call a provider. That was more conservative than this project needs: the
PayPal AI Hackathon requires meaningful AI **and** meaningful PayPal integration, and its "AI Agents or
Automation" theme asks for agents that actually transact (**VERIFY** exact wording against the Official
Rules tab on Devpost).

The two obvious swings are both wrong: an agent that may execute freely is an unaudited money-moving bot,
and an agent that may never execute leaves the AI and PayPal requirements shallow. The need is a design
where the model's judgement is used for *what* to do, while a machine enforces *whether* and *how* it runs.

## Decision

**The LLM decides what to propose. Deterministic code decides what executes. An agent may execute a
payment-related action only after explicit human approval, through a single-use mandate that locks the
exact parameters.**

The mandate flow:

1. The agent writes a `proposed_actions` row with exact structured parameters: kind, recipient member id,
   amount (integer minor units), currency, circle id, cycle or settlement id, rationale, expiry.
2. A human approves with step-up auth (biometric or OTP). The approval screen shows the exact amount and
   recipient in plain language.
3. Approval creates a **mandate**: hash of canonical parameters, single use, short expiry, hard amount cap,
   bound to circle, cycle, recipient and action kind (`agent_mandates`, see `03`).
4. The agent calls `execute_mandate(mandate_id)`. The tool takes **only** the id; the LLM never supplies
   amount or recipient. The tool re-reads parameters from the database, verifies hash, expiry, unused
   status and proposal state, recomputes the amount with the engine and aborts on any mismatch, takes the
   cycle lock, then calls the gateway with idempotency key `mandate:{id}`. Provider calls stay outside DB
   transactions; `UNKNOWN` outcomes use the existing checker flow.
5. The agent reports the outcome and follows up.

Guardrails are layered (detail in `10`): an action allow-list (winner payout of an approved settlement,
catch-up invoice, refund of a verified overpayment — no generic "pay X"); recipient rules (verified payout
destination only, cooldown plus step-up after a destination change); per-action, per-circle daily and
velocity caps; global and per-agent kill switches; risk tiers (Tier 0 messages, Tier 1 invoices and
refunds, Tier 2 payouts requiring approval + step-up + second approver, with the recipient never approving
their own payout); isolation (the LLM process holds no provider credentials, execution runs in a restricted
worker, member-written text never reaches the execution path); and, if PayPal MCP tools are exposed, a proxy
that permits only mandated calls.

Agents still never calculate money: proposal and execution amounts come from the engine.

Relationship to `adr/0002`: non-custodial concerns whose money sits where, not who triggers the API call
(see the clarification added to `adr/0002`). PayPal's acceptable use policy applies equally to agent- and
human-initiated calls (**VERIFY** current wording).

## Consequences

- A human authorises every payment-related execution, with the exact amount and recipient visible — no
  silent or ambiguous agent spending.
- Replay, tampering and stale-execution attempts fail closed: unique `execution_idempotency_key`, single-use
  `state`, `params_hash` verification and engine recomputation.
- The AI does real work (it decides what to propose and drives execution), so the hackathon AI and PayPal
  themes are met without handing the model a payment button.
- New surface area to secure and test: the mandate table, the `execute_mandate` tool, step-up approval, caps
  and the kill switch (covered by the tests in `11`).
- New operational signals: mismatch aborts, expired-mandate attempts, cap breaches, kill-switch activations
  (alerts and dashboard in `08`).
- A compromised or coerced approver can still authorise a capped, allow-listed, audited action — mitigated
  by step-up, short expiry, caps, second approver for payouts and the kill switch.

## Alternatives considered

- **Agent never executes (the original rule):** safest, but leaves the hackathon's AI-plus-PayPal
  requirement shallow and pushes every action to a human click with no automation value.
- **Standing auto-approval for everything:** no meaningful human control; rejected for money movement. In v1
  standing policies cover Tier 0 messages only, with small Tier 1 invoices possible later; Tier 2 payouts
  never.
- **Raw provider tools exposed to the LLM:** the model could pick its own amount, recipient and timing,
  breaking parameter control and auditability. Rejected; only `execute_mandate(id)` exists, and any MCP
  tools sit behind a mandate-only proxy.

## Revisit when

Regulators, the payment partner or counsel say agent-triggered calls need a different control (for example
a per-transaction challenge beyond step-up), or the action allow-list grows past payout, invoice and refund
— at which point add a new ADR rather than widening this one.
