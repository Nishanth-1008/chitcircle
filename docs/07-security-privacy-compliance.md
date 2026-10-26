# 07. Security, Privacy and Compliance

This is engineering guidance, not legal advice. Have counsel review before any live launch.

## 1. Authentication and authorization

- **Authentication:** use a managed identity provider (OIDC) rather than building it. Support **phone-number OTP** (many community members have no email), email, and optionally social login. Short-lived access tokens (about 15 minutes), rotating refresh tokens, device binding on mobile.
- **Authorization is resolved from the database, not trusted from the token.** Circle roles (`organizer`, `member`, `approver`) come from `circle_members` and are cached for 60 seconds. The prototype's `X-Actor-Id` / `X-Actor-Role` stub is removed in Phase 2.
- Existing service-level rules stay: organizer-only actions, recipient cannot approve their own payout, members can bid only for themselves.
- **Defense in depth:** PostgreSQL row-level security keyed on circle membership as a second barrier against a missing filter.
- Step-up verification (biometric or OTP) for approving payouts and changing payout details.
- Separate admin and support access, with just-in-time elevation and a full audit trail.

## 2. Data protection

| Data | Handling |
|---|---|
| Ledger and engine data | Member ids only, no PII |
| Phone, email, name, address | Separate tables; field-level encryption with envelope keys (KMS) |
| Guarantor documents, IDs | Object storage, encrypted, private, short-lived signed URLs, malware scan on upload |
| Card or bank data | **Never touches our systems.** Use PayPal-hosted flows |
| Secrets | Secrets manager; no secrets in code, logs or client bundles |
| Logs | Structured, with PII redaction at the logger |
| LLM inputs | Redact personal data; send only what the task needs |

TLS everywhere; HSTS; encryption at rest on database, cache snapshots and object storage.

## 3. Application security

- Input validation with Pydantic; reject unknown fields.
- Rate limits: per user and per IP on login, OTP, bidding and invite endpoints; stricter on OTP to resist SMS pumping.
- CSRF protection for cookie sessions; strict CORS allow-list; secure, HttpOnly, SameSite cookies on web.
- Webhook endpoint accepts only signed events; optional IP allow-listing if the provider publishes ranges.
- Dependency scanning, SAST and container scanning in CI; pinned versions; SBOM.
- Content security policy on the web app; no inline scripts; subresource integrity for third-party scripts.
- Threat model reviewed each phase (see below).

## 4. Threat model highlights

| Threat | Mitigation |
|---|---|
| Duplicate or replayed webhook | Unique provider event id, idempotent processing |
| Forged webhook | Signature verification; reject and alarm |
| Organizer abuse (fake circle, disappearing with funds) | Non-custodial flow, organizer verification, visible ledger, dispute log |
| Member default after winning | Security workflow, guarantor, risk-linked required security |
| Bid manipulation or shill bidding | Eligibility rules, sealed-bid default, audit of bid history |
| Account takeover | OTP, device binding, step-up on sensitive actions |
| Insider misuse | Role separation, audit logs, access reviews |
| Prompt injection into agents | Agents have read tools and `propose` only; no direct execution; inputs treated as untrusted (see `10`) |
| SMS pumping and abuse | Rate limits, country allow-lists, provider fraud guards |

## 5. Privacy and data-protection law

Likely relevant regimes (**VERIFY** current rules with counsel): India's Digital Personal Data Protection Act, 2023; EU and UK GDPR for diaspora members; US state privacy laws.

Engineering consequences:
- Consent records and purpose limitation in `consents`.
- Data export and deletion workflows. Because the ledger holds no PII, deletion erases or pseudonymizes the `users` and contact rows while the financial record stays intact and explainable.
- Data residency options if a regime requires it (region-pinned databases per market in Phase 5/6).
- Breach response runbook and notification timelines.

## 6. Financial and regulatory posture

- Position as **software for organizers**, not as the operator of the chit and not as a custodian.
- **India:** the Chit Funds Act, 1982 and state rules apply to registered chits (discount ceiling, foreman commission ceiling, security from prized subscribers, filings). Confirm the current commission ceiling, because a 2018 amendment bill proposed raising it. Informal circles are not regulated as chits but may attract other rules.
- **Elsewhere:** informal rotating savings groups are often unregulated, while lending, interest and deposit-taking can be regulated.
- **Jurisdiction profile** (data, versioned): caps, commission rules, required security, enabled payout modes, required disclosures, whether lottery and interest-bearing modes are allowed. A profile never grants legal permission; it only restricts what the product allows.
- **KYC and AML:** organizer verification at minimum; screening and thresholds depend on the payment partner and the market.
- Disclosures to members: effective annualized rate of any early payout, fees, who holds the funds, and how disputes are handled.
- Terms of service must state the platform is software, the organizer is responsible for the circle, and members should read their circle agreement.

## 7. Security operations

- Quarterly access review; annual penetration test before scale-up; bug-report channel.
- Secrets rotation schedule, including provider credentials and webhook secrets.
- Immutable audit log (append-only table plus export to write-once storage).
- Incident severity levels and an on-call rotation (see `08`).
