"""Provider reconciliation. A request is never proof of a completed movement."""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Optional

from .money import Money


class HmacVerifier:
    """Default callback verifier. Swap for the provider's own scheme (e.g. PayPal webhook verification)."""

    def __init__(self, secret: Optional[str]):
        self._secret = secret

    def verify(self, body: bytes, signature: Optional[str]) -> bool:
        if not self._secret or not signature:
            return False                                  # fail safe
        expected = hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def sign(self, body: bytes) -> str:
        return hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()


class TxnKind(str, Enum):
    PAYMENT = "PAYMENT"
    REFUND = "REFUND"
    PAYOUT = "PAYOUT"


@dataclass(frozen=True)
class ProviderTxn:
    provider_txn_id: str
    kind: TxnKind
    status: str                     # COMPLETED | FAILED | PENDING | ...
    amount: Money
    member_id: Optional[str] = None


@dataclass(frozen=True)
class Discrepancy:
    code: str
    detail: str
    member_id: Optional[str] = None


@dataclass
class ReconciliationReport:
    discrepancies: list = field(default_factory=list)
    unresolved: bool = False

    @property
    def is_clean(self) -> bool:
        return not self.discrepancies and not self.unresolved

    def to_dict(self) -> dict:
        return {"is_clean": self.is_clean, "unresolved": self.unresolved,
                "discrepancies": [d.__dict__ for d in self.discrepancies]}


def reconcile_payments(internal_paid: Mapping[str, Money], provider_txns: Iterable[ProviderTxn],
                       expected_net: Optional[Mapping[str, Money]] = None) -> ReconciliationReport:
    """Compare internal confirmed cash (and optionally the expected net obligation) with provider records."""
    rep = ReconciliationReport()
    seen: set = set()
    totals: dict = {}
    for t in provider_txns:
        if t.kind == TxnKind.PAYOUT:
            continue
        if t.provider_txn_id in seen:
            rep.discrepancies.append(Discrepancy("DUPLICATE_PROVIDER_TXN", t.provider_txn_id, t.member_id))
            continue
        seen.add(t.provider_txn_id)
        if t.status == "PENDING":
            rep.unresolved = True
            continue
        if t.status != "COMPLETED" or t.member_id is None:
            continue
        sign = 1 if t.kind == TxnKind.PAYMENT else -1
        totals[t.member_id] = totals.get(t.member_id, 0) + sign * t.amount.minor
        cur = t.amount.currency
        internal = internal_paid.get(t.member_id)
        if internal is not None and internal.currency != cur:
            rep.discrepancies.append(Discrepancy("CURRENCY_MISMATCH", f"{internal.currency} vs {cur}", t.member_id))
    for m, internal in internal_paid.items():
        got = totals.get(m, 0)
        if got != internal.minor:
            rep.discrepancies.append(Discrepancy(
                "INTERNAL_PROVIDER_MISMATCH", f"internal {internal.minor} vs provider {got}", m))
        if expected_net is not None and m in expected_net and got != expected_net[m].minor:
            code = "UNDERPAID" if got < expected_net[m].minor else "OVERPAID"
            rep.discrepancies.append(Discrepancy(code, f"net due {expected_net[m].minor} vs cash {got}", m))
    return rep


def reconcile_payout(expected: Money, provider: Optional[ProviderTxn]) -> ReconciliationReport:
    rep = ReconciliationReport()
    if provider is None or provider.status == "PENDING":
        rep.unresolved = True                      # unknown outcome stays unresolved
        return rep
    if provider.status != "COMPLETED":
        rep.discrepancies.append(Discrepancy("PAYOUT_NOT_COMPLETED", provider.status))
    if provider.amount != expected:
        rep.discrepancies.append(Discrepancy(
            "PAYOUT_AMOUNT_MISMATCH", f"expected {expected.minor} {expected.currency}, "
                                      f"provider {provider.amount.minor} {provider.amount.currency}"))
    return rep
