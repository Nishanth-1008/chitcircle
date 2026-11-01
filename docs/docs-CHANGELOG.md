# docs/ CHANGELOG

One line per file changed (or created) in this documentation update, which moves the plan from "agents
never execute" to **approval-gated execution through single-use mandates** (`adr/0007`).

| File | Why it changed |
|---|---|
| `README.md` | Rewrote headline decision 8 to the new rule (LLM proposes, deterministic code executes); added decision 9 (mandate-gated execution) and a mandate convention bullet; added a "Hackathon requirements" row to the reading table pointing at `appendix/hackathon-compliance.md`. |
| `02-system-architecture.md` | Agents module now owns mandates and reaches `cycles` via approvals *and* mandates. |
| `03-data-model-and-consistency.md` | Added the `agent_mandates` table (hash-locked, single-use, capped, step-up approval) and a mandate row in the idempotency layers table noting the unique `execution_idempotency_key` (`mandate:{id}`). |
| `06-paypal-integration.md` | Added §3.1 "Mandate-bound gateway calls (agent execution)" — re-read, verify, recompute, cycle lock, provider call outside the transaction; kept the India and acceptable-use caveats. |
| `07-security-privacy-compliance.md` | Updated the agent prompt-injection row and added threats: mandate replay, mandate parameter tampering, prompt injection into proposals, compromised approver device. |
| `08-observability-reliability.md` | Added alerts (amount/parameter mismatch abort, expired/revoked/consumed mandate use, execution above caps, kill-switch activation) and a "Agent execution" dashboard panel. |
| `09-clients-web-and-mobile.md` | Approvals row now says step-up on approve issues the execution mandate. |
| `10-ai-agents.md` | Core rewrite: new role/boundary rule, Allowed/Not-allowed table, mandate design (§3.1), lifecycle `PROPOSED -> APPROVED -> MANDATE_ISSUED -> EXECUTED | FAILED | EXPIRED | REVOKED`, execution agents (collections invoice, payout executor), layered guardrails with risk tiers, roadmap; kept "agents never calculate money". |
| `11-testing-strategy.md` | Added mandate concurrency tests (single-use, recipient cannot approve own payout) and a "Mandate and agent-execution tests" block (tamper, expiry, recompute mismatch, injection fixtures, kill switch). |
| `12-infrastructure-and-deployment.md` | Feature flags now explicitly include the global and per-agent kill switches. |
| `adr/0002-non-custodial-funds-flow.md` | Added a clarification section: custody is about funds and accounts, not about who triggers an API call; AUP applies equally to agent- and human-initiated calls (VERIFY). |
| `adr/0007-approval-gated-agent-execution.md` | **New** — Context, Decision, Consequences, Alternatives (never executes / standing auto-approval / raw tool access), Revisit when. |
| `phases/phase-1-hackathon-mvp.md` | Mandate-gated execution is a MUST HAVE and in the never-cut list; added tasks (mandate table, `execute_mandate`, approval UI with step-up, caps, kill switch, tests); demo story now runs propose -> approve -> agent executes -> webhook -> ledger. |
| `phases/phase-2-production-hardening.md` | Added mandate hardening: second-approver rule, step-up enforcement, destination-change cooldown, cap tuning, mandate audit export. |
| `appendix/open-questions.md` | New "Agents and mandates" section (Q29-Q34): cap values, mandate expiry, second-approver thresholds, PayPal calls the agent may use, default step-up method, MCP exposure. |
| `appendix/glossary.md` | Added Mandate, Proposed action, Execution agent, Step-up auth, Risk tier. |
| `appendix/hackathon-compliance.md` | **New** — judging-requirement status map, judge-facing README checklist, pre-existing-work disclosure plan, and a Official Rules placeholder checklist (every row marked VERIFY, nothing invented). |
| `backend-implementation.md` | Brought in line with the new rule: ground rule 10, module map, `agent_mandates` in the schema plan, idempotency layers, threat model, §13 rewrite (mandate model, lifecycle, layered guardrails), planned endpoints, Phase 1 roadmap and never-cut list, `mandate:{id}` idempotency key, mandate tests, extra VERIFY rows. |
| `docs-CHANGELOG.md` | **New** — this file. |
