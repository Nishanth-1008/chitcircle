"""Payout gateway abstraction. The engine never moves money itself."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

from financial_engine.money import Money


class PayoutStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"          # timeout / no answer: neither success nor failure


@dataclass(frozen=True)
class PayoutResult:
    status: PayoutStatus
    provider_ref: Optional[str] = None
    detail: str = ""


class PayoutGateway(Protocol):
    def submit_payout(self, *, idempotency_key: str, member_id: str, amount: Money) -> PayoutResult: ...

    def lookup_payout(self, idempotency_key: str) -> PayoutResult: ...


class MockGateway:
    """Deterministic gateway for dev/tests. Dedupes by idempotency key like a real provider should."""

    def __init__(self, mode: str = "ok"):
        self.mode = mode                      # ok | fail | timeout
        self.submissions: dict = {}
        self.calls = 0

    def submit_payout(self, *, idempotency_key, member_id, amount):
        self.calls += 1
        if idempotency_key in self.submissions:
            return self.submissions[idempotency_key]
        if self.mode == "timeout":
            return PayoutResult(PayoutStatus.UNKNOWN, None, "provider timeout")
        res = (PayoutResult(PayoutStatus.FAILED, None, "rejected") if self.mode == "fail"
               else PayoutResult(PayoutStatus.SUBMITTED, f"mock-{len(self.submissions) + 1}"))
        self.submissions[idempotency_key] = res
        return res

    def lookup_payout(self, idempotency_key):
        return self.submissions.get(idempotency_key, PayoutResult(PayoutStatus.UNKNOWN, None, "not found"))


class PayPalPayoutsGateway:
    """Placeholder. Actual PayPal sandbox payout capability is a reserved decision in the spec."""

    def submit_payout(self, **kwargs):
        raise NotImplementedError("PayPal payouts integration is not implemented")

    def lookup_payout(self, idempotency_key):
        raise NotImplementedError("PayPal payouts integration is not implemented")


_gateway: PayoutGateway = MockGateway()


def get_gateway() -> PayoutGateway:
    return _gateway
