# 06. PayPal Integration

## 1. Funds flow: non-custodial by design

The platform **calculates, validates, approves and records**. It should not hold the pot. Preferred model:

- Each circle's organizer connects **their own PayPal business account** (onboarding through PayPal's partner or platform program; **VERIFY** the exact program and eligibility).
- Members pay into that account. The organizer's account pays the winner. The platform may take a SaaS fee or platform fee where the program allows.
- ChitCircle's ledger mirrors and checks these movements; it is not the bank.

Why: holding client funds or acting as an escrow or money-transmission service can require licences and, per PayPal's own acceptable use policy, requires **pre-approval** for money-service and escrow-type activity (**VERIFY** current policy text). See `adr/0002`.

The prototype already respects this shape: the engine never moves money, and the `PayoutGateway` interface keeps providers swappable.

## 2. The India caveat (important)

Public sources report that PayPal ended **domestic** payments in India in April 2021 and supports **cross-border** flows only; PayPal reportedly holds in-principle RBI approval for cross-border export payments, which does not cover domestic transfers (**VERIFY** current status).

Implications:

- **PayPal fits diaspora and cross-border circles** (for example an Indian chit group with members in the US, UK and Gulf, or a Nigerian-American esusu). This matches the global positioning.
- **An India-domestic chit cannot be settled through PayPal** as far as we can tell. A production India launch needs a licensed domestic rail (UPI via a payment aggregator, or bank transfer) behind the same gateway interfaces. This is a Phase 5 item.
- For the hackathon, demo scenarios should use cross-border or non-India circles and currencies (USD, GBP, EUR, CAD) or label INR scenarios clearly as simulated.
- In the Chit Funds Act context, an Indian registered foreman collecting online would also fall under Indian payment regulation. That is a legal question, not an engineering one.

## 3. Gateway interfaces

```python
class CollectionGateway(Protocol):
    def create_payment_request(self, *, idem: str, obligation_id: str, payer_ref: str,
                               amount: Money, due: date, return_url: str) -> PaymentRequest: ...
    def lookup_payment(self, idem: str) -> PaymentStatus: ...
    def refund(self, *, idem: str, provider_txn_id: str, amount: Money) -> RefundResult: ...

class PayoutGateway(Protocol):          # exists in the prototype
    def submit_payout(self, *, idempotency_key, member_id, amount) -> PayoutResult: ...
    def lookup_payout(self, idempotency_key) -> PayoutResult: ...
```

Adapters: `PayPalGateway`, `MockGateway` (tests and simulator), and later a domestic-rail adapter. The service layer depends only on the protocols.

## 4. PayPal capability mapping (sandbox first)

The PayPal AI Toolkit exposes a sandbox MCP server with tools for orders and payments, invoices, subscriptions, disputes, catalog, shipments and reporting. A dedicated payout tool was not visible in the tool list.

| Need | Candidate | Notes |
|---|---|---|
| Recurring contribution | Subscriptions and billing plans | Good for fixed monthly installments; net installment varies with dividends, so prefer invoices or orders per cycle |
| Per-cycle installment with a variable net amount | Invoices (partial payments, QR codes) or Orders | Preferred: one invoice per obligation, amount = net contribution |
| Late payment catch-up | Invoice reminders | Agent-driven escalation |
| Winner payout | Payouts API if available in sandbox, otherwise an order or invoice from the organizer's account to the winner | **Phase 0 spike decides** |
| Refunds | Refund on a captured payment | Overpayments surface as `OVERPAID` and block finalization until refunded (existing behaviour) |
| Disputes | Disputes APIs and webhooks | Moves the cycle to `DISPUTED` (existing behaviour) |
| History and statements | Reporting and transaction search | Feeds reconciliation |

Webhook event families to subscribe to (**VERIFY** names in the sandbox): payment captured and refunded, invoice paid, subscription lifecycle, payout item succeeded or failed, dispute created and resolved.

## 5. Authentication and tokens

- OAuth client credentials kept in a secrets manager, never in the repository.
- Cache the access token in Redis with TTL below its lifetime and **single-flight refresh** so a burst does not trigger many refreshes. Sandbox tokens can expire within hours, so refresh is a Phase 1 requirement.
- Separate credentials and webhook ids per environment.

## 6. Reconciliation

Daily job, plus on-demand per settlement:

1. Pull provider transactions for the window.
2. Match to ledger `PAYMENT`, `REFUND`, `PAYOUT` events by provider transaction id and idempotency key.
3. Classify: matched, missing in ledger, missing at provider, amount mismatch, duplicate, overpaid.
4. Auto-resolve the safe classes (late webhook arrived); open an **operations case** for the rest.
5. A settlement cannot finalize while its discrepancies are open (existing behaviour).

Add to the chart of accounts: a **provider fees** account so PayPal fees are explicit and the circle pool still nets to zero. Decide who bears fees (organizer, member, platform) in the ruleset, and record it.

## 7. Multi-currency

- One currency per circle; the engine already carries currency on every `Money`.
- Cross-border diaspora circles pay in the circle currency; PayPal handles member-side conversion. Show the member the converted amount before they pay (use the provider quote, not our own rate).
- Never add currencies in the ledger. Convert only at the edges.

## 8. Sandbox versus live

Treat these as different systems: payout availability, webhook delivery, fraud checks, and rate limits differ. Keep a **go-live checklist** (business verification, policy approval for the use case, webhook endpoints, credentials rotation, reconciliation run on small real amounts) in Phase 2.

## 9. Policy checks before any live launch

| Area | Action |
|---|---|
| Lottery or prize-draw mode | PayPal restricts entry-fee-and-prize activity unless approved (**VERIFY**). Ship **disabled by default**, enabled only per jurisdiction and with approval |
| Pooled funds or escrow-like behaviour | Keep non-custodial; get written confirmation from PayPal for the use case |
| Chit-style savings groups | Ask PayPal's compliance team directly; do not assume permitted |
| Interest-bearing advances | Treat as lending; jurisdiction profile must gate it |
