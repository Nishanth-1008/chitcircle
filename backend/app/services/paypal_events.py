"""Translate PayPal webhook events into the provider-event shape the ingest pipeline applies.

Only events we can tie to an obligation or a settlement through our own idempotency keys are translated:
  - invoices carry `detail.reference` = `collection:{cycle_id}:{member_id}`, `mandate:{id}` (catch-up invoice)
    or `payout:{settlement_id}` (payout modelled as an invoice to the winner);
  - payout items carry `sender_item_id` = `payout:{settlement_id}` or `mandate:{id}`.
Anything else returns None and is acknowledged without effect.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from financial_engine.money import Money, MoneyError

from ..models import AgentMandate, SettlementRow

PAYOUT_ITEM_STATUS = {
    "PAYMENT.PAYOUTS-ITEM.SUCCEEDED": "COMPLETED",
    "PAYMENT.PAYOUTS-ITEM.FAILED": "FAILED",
    "PAYMENT.PAYOUTS-ITEM.DENIED": "FAILED",
    "PAYMENT.PAYOUTS-ITEM.RETURNED": "FAILED",
    "PAYMENT.PAYOUTS-ITEM.BLOCKED": "FAILED",
    "PAYMENT.PAYOUTS-ITEM.CANCELED": "FAILED",
    "PAYMENT.PAYOUTS-ITEM.UNCLAIMED": "PENDING",
    "PAYMENT.PAYOUTS-ITEM.HELD": "PENDING",
}


def is_paypal_event(payload: dict) -> bool:
    return isinstance(payload, dict) and "event_type" in payload and "resource" in payload


def _minor(amount: Optional[dict]) -> Optional[tuple[int, str]]:
    if not amount:
        return None
    cur = amount.get("currency_code") or amount.get("currency")
    try:
        return Money.from_major(str(amount["value"]), cur).minor, cur
    except (KeyError, MoneyError):
        return None


def _resolve_reference(session: Session, ref: str) -> Optional[dict]:
    """Map one of our idempotency keys to what it pays for."""
    if ref.startswith("collection:"):
        parts = ref.split(":")
        if len(parts) == 3:
            return {"kind": "PAYMENT", "cycle_id": parts[1], "member_id": parts[2]}
    elif ref.startswith("payout:"):
        row = session.get(SettlementRow, ref.split(":", 1)[1])
        if row is not None:
            return {"kind": "PAYOUT", "payout_reference": row.payout_idempotency_key}
    elif ref.startswith("mandate:"):
        m = session.get(AgentMandate, ref.split(":", 1)[1])
        if m is None:
            return None
        if m.kind == "invoice":
            return {"kind": "PAYMENT", "cycle_id": m.params.get("cycle_id"), "member_id": m.params.get("member_id")}
        if m.kind == "payout" and m.params.get("settlement_id"):
            row = session.get(SettlementRow, m.params["settlement_id"])
            if row is not None:
                return {"kind": "PAYOUT", "payout_reference": row.payout_idempotency_key}
    return None


def normalize(session: Session, event: dict) -> Optional[dict]:
    et = event.get("event_type", "")
    res = event.get("resource") or {}
    base = {"event_id": event.get("id"), "paypal_event_type": et}

    if et == "INVOICING.INVOICE.PAID":
        inv = res.get("invoice") or res
        ref = ((inv.get("detail") or {}).get("reference")) or ""
        target = _resolve_reference(session, ref)
        payments = (inv.get("payments") or {})
        txns = payments.get("transactions") or []
        money = _minor(payments.get("paid_amount")) or _minor(inv.get("amount"))
        if target is None or money is None:
            return None
        txn_id = (txns[-1].get("payment_id") if txns else None) or inv.get("id")
        return {**base, **target, "provider_txn_id": txn_id, "status": "COMPLETED",
                "amount": money[0], "currency": money[1]}

    if et in PAYOUT_ITEM_STATUS:
        item = res.get("payout_item") or {}
        target = _resolve_reference(session, item.get("sender_item_id") or "")
        money = _minor(item.get("amount"))
        if target is None or target["kind"] != "PAYOUT" or money is None:
            return None
        txn_id = res.get("transaction_id") or res.get("payout_item_id")
        return {**base, **target, "provider_txn_id": txn_id, "status": PAYOUT_ITEM_STATUS[et],
                "amount": money[0], "currency": money[1]}

    return None
