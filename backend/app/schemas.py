from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, StrictInt


class CreateCircle(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    ruleset: dict
    members: list[str]


class NewRuleset(BaseModel):
    ruleset: dict
    reason: str


class NewCycle(BaseModel):
    due_date: datetime
    ruleset_version: Optional[int] = None


class BidIn(BaseModel):
    member_id: str
    discount: StrictInt = Field(description="discount in minor units")


class EarlyPayoutIn(BaseModel):
    requester_id: str
    discount: StrictInt
    consenting_member_ids: list[str]


class ApprovalIn(BaseModel):
    decision: str
    reason: Optional[str] = None


class ReasonIn(BaseModel):
    reason: str


class SecurityIn(BaseModel):
    status: str


class ProviderCallback(BaseModel):
    provider_txn_id: str
    kind: str                                   # PAYMENT | REFUND | PAYOUT
    status: str                                 # COMPLETED | FAILED | PENDING
    amount: StrictInt                           # minor units
    currency: str
    cycle_id: Optional[str] = None
    member_id: Optional[str] = None
    payout_reference: Optional[str] = None      # our payout idempotency key (PAYOUT only)
