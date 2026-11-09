"""Payout gateway abstraction. The engine never moves money itself."""
from __future__ import annotations

import base64
import hashlib
import json
import time
import zlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

import httpx
from jose import jwt
from jose.utils import base64url_decode
from sqlalchemy import select
from sqlalchemy.orm import Session

from financial_engine.money import Money

from ..config import (
    paypal_client_id,
    paypal_client_secret,
    paypal_base_url,
    paypal_webhook_id,
    webhook_secret,
    redis_url,
)
from ..models import UserContact


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


@dataclass(frozen=True)
class CollectionResult:
    """Result of creating a collection request (invoice/order)."""
    status: str                 # "CREATED" | "FAILED"
    provider_ref: Optional[str] = None   # PayPal invoice ID or order ID
    approval_url: Optional[str] = None   # URL for buyer to approve payment
    detail: str = ""


class PayoutGateway(Protocol):
    def submit_payout(self, *, idempotency_key: str, member_id: str, amount: Money) -> PayoutResult: ...

    def lookup_payout(self, idempotency_key: str) -> PayoutResult: ...


class CollectionGateway(Protocol):
    def create_collection(
        self,
        *,
        idempotency_key: str,
        member_id: str,
        amount: Money,
        description: str,
        return_url: str,
        cancel_url: str,
    ) -> CollectionResult: ...


def resolve_contact_email(session: Session, member_id: str) -> Optional[str]:
    """Resolve a member's verified contact email from ``user_contacts``.

    PII stays out of the engine; the payments adapter resolves the verified
    contact at the edge (§10.10, gap #10). Returns None when no verified
    email contact exists for the member, so callers can fall back.
    """
    from ..models import Member
    member = session.get(Member, member_id)
    user_id = member.user_id if member is not None and member.user_id else member_id
    contact = session.scalar(
        select(UserContact).where(
            UserContact.user_id == user_id,
            UserContact.kind == "email",
            UserContact.verified.is_(True),
        )
    )
    return contact.value if contact else None


class MockGateway:
    """Deterministic gateway for dev/tests. Dedupes by idempotency key like a real provider should."""

    def __init__(self, mode: str = "ok"):
        self.mode = mode                      # ok | fail | timeout
        self.submissions: dict = {}
        self.collections: dict = {}
        self.calls = 0

    def submit_payout(self, *, idempotency_key, member_id, amount, session=None):
        self.calls += 1
        if idempotency_key in self.submissions:
            return self.submissions[idempotency_key]
        if self.mode == "timeout":
            return PayoutResult(PayoutStatus.UNKNOWN, None, "provider timeout")
        if self.mode == "fail":
            return PayoutResult(PayoutStatus.FAILED, None, "rejected")   # a rejected request creates nothing
        res = PayoutResult(PayoutStatus.SUBMITTED, f"mock-{len(self.submissions) + 1}")
        self.submissions[idempotency_key] = res
        return res

    def lookup_payout(self, idempotency_key):
        return self.submissions.get(idempotency_key, PayoutResult(PayoutStatus.UNKNOWN, None, "not found"))

    def create_collection(self, *, idempotency_key, member_id, amount, description, return_url, cancel_url, session=None):
        if idempotency_key in self.collections:
            return self.collections[idempotency_key]
        if self.mode == "fail":
            return CollectionResult("FAILED", None, None, "mock failure")
        res = CollectionResult(
            "CREATED",
            f"mock-inv-{len(self.collections) + 1}",
            f"{return_url}?mock=1",
        )
        self.collections[idempotency_key] = res
        return res


# --- PayPal Implementation ---

class _TokenCache:
    """Thread-safe token cache using Redis with local fallback."""

    def __init__(self):
        self._local_cache: dict[str, tuple[str, float]] = {}  # key -> (token, expiry)
        self._redis = None
        self._init_redis()

    def _init_redis(self):
        try:
            import redis
            self._redis = redis.from_url(redis_url(), decode_responses=True)
            self._redis.ping()
        except Exception:
            self._redis = None

    def get(self, key: str) -> Optional[str]:
        # Try Redis first
        if self._redis:
            try:
                val = self._redis.get(f"paypal:token:{key}")
                if val:
                    return val
            except Exception:
                pass
        # Fallback to local cache
        if key in self._local_cache:
            token, expiry = self._local_cache[key]
            if time.time() < expiry:
                return token
            del self._local_cache[key]
        return None

    def set(self, key: str, token: str, ttl_seconds: int):
        expiry = time.time() + ttl_seconds - 60  # 60s buffer
        if self._redis:
            try:
                self._redis.setex(f"paypal:token:{key}", ttl_seconds, token)
            except Exception:
                pass
        self._local_cache[key] = (token, expiry)


_token_cache = _TokenCache()


def _paypal_error(body: str) -> str:
    """Short, human-readable reason from a PayPal error body (never the raw payload)."""
    try:
        data = json.loads(body)
    except Exception:  # noqa: BLE001 - non-JSON error bodies
        return "unexpected response"
    details = data.get("details") or []
    first = details[0] if details and isinstance(details[0], dict) else {}
    reason = first.get("description") or first.get("issue") or data.get("message") or data.get("name") \
        or data.get("error") or "unknown error"
    if "Currency Code is not valid" in reason:
        reason += " PayPal does not support this currency here (INR invoicing is unavailable); use e.g. USD"
    return reason[:300]


class PayPalGateway:
    """Real PayPal Sandbox gateway for collections and payouts."""

    def __init__(self):
        self.client_id = paypal_client_id()
        self.client_secret = paypal_client_secret()
        self.base_url = paypal_base_url()

        if not self.client_id or not self.client_secret:
            raise RuntimeError("PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET must be set")

    def _get_access_token(self) -> str:
        """Get OAuth2 access token with caching."""
        cache_key = f"{self.client_id}:{self.base_url}"
        cached = _token_cache.get(cache_key)
        if cached:
            return cached

        # Fetch new token
        auth = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = "grant_type=client_credentials"

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{self.base_url}/v1/oauth2/token", headers=headers, data=data)
            resp.raise_for_status()
            token_data = resp.json()

        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 32000)  # default ~9 hours
        _token_cache.set(cache_key, access_token, expires_in)
        return access_token

    def _headers(self, idempotency_key: str | None = None) -> dict:
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            **({"PayPal-Request-Id": idempotency_key} if idempotency_key else {}),
        }

    # --- Collection (Invoice) ---

    def create_collection(self, **kwargs) -> CollectionResult:
        """Create a PayPal invoice for a contribution; provider errors come back as a FAILED result."""
        try:
            return self._create_invoice(**kwargs)
        except httpx.HTTPStatusError as e:
            return CollectionResult("FAILED", None, None,
                                    f"PayPal rejected the invoice ({e.response.status_code}: {_paypal_error(e.response.text)})")
        except httpx.HTTPError:
            return CollectionResult("FAILED", None, None, "PayPal did not respond; try again")

    def _create_invoice(
        self,
        *,
        idempotency_key: str,
        member_id: str,
        amount: Money,
        description: str,
        return_url: str,
        cancel_url: str,
        session: Optional[Session] = None,
    ) -> CollectionResult:
        """Create and send a PayPal invoice for member contribution collection."""
        # PayPal Invoicing API v2
        # https://developer.paypal.com/docs/api/invoicing/v2/

        amount_str = amount.to_major_string()      # exact, exponent-aware (gap #9)
        currency = amount.currency

        # Resolve the member's verified contact at the edge (gap #10).
        # Only enforced when a DB session is provided (API path); direct calls skip it.
        payer_email = None
        if session is not None:
            payer_email = resolve_contact_email(session, member_id)
            if not payer_email:
                return CollectionResult("FAILED", None, None, "no verified email contact for member")

        invoice_id, payer_url = self._send_invoice(idempotency_key, payer_email, amount,
                                                   "ChitCircle contribution", description)
        return CollectionResult(status="CREATED", provider_ref=invoice_id, approval_url=payer_url,
                                detail="Invoice sent to payer")

    def _send_invoice(self, idempotency_key: str, recipient_email: Optional[str], amount: Money,
                      item_name: str, note: str) -> tuple[str, str]:
        """Create and send a PayPal v2 invoice. `detail.reference` carries our key so the PAID webhook maps back.

        The invoicer is the PayPal account behind the API credentials, so no `invoicer` block is sent.
        PayPal-Request-Id makes both calls safe to retry.
        """
        currency = amount.currency
        invoice = {
            "detail": {"currency_code": currency, "reference": idempotency_key, "note": note[:4000],
                       "payment_term": {"term_type": "DUE_ON_RECEIPT"}},
            "primary_recipients": [{"billing_info": {"email_address": recipient_email}}] if recipient_email else [],
            "items": [{"name": item_name, "description": note[:1000], "quantity": "1",
                       "unit_amount": {"currency_code": currency, "value": amount.to_major_string()}}],
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{self.base_url}/v2/invoicing/invoices",
                               headers={**self._headers(idempotency_key), "Prefer": "return=representation"},
                               json=invoice)
            resp.raise_for_status()
            data = resp.json()
            invoice_id = data.get("id") or data.get("href", "").rstrip("/").rsplit("/", 1)[-1]
            resp = client.post(f"{self.base_url}/v2/invoicing/invoices/{invoice_id}/send",
                               headers=self._headers(f"{idempotency_key}:send"),
                               json={"send_to_invoicer": False, "send_to_recipient": bool(recipient_email)})
            resp.raise_for_status()
            try:
                sent = resp.json()      # PayPal may answer 202 with an empty body
            except ValueError:
                sent = {}
        payer_url = sent.get("href") or ((data.get("detail") or {}).get("metadata") or {}).get("recipient_view_url") \
            or f"https://www.sandbox.paypal.com/invoice/p/#{invoice_id}"
        return invoice_id, payer_url

    # --- Payout ---

    def submit_payout(self, *, idempotency_key: str, member_id: str, amount: Money,
                      session: Optional[Session] = None) -> PayoutResult:
        """
        Submit a payout to the winner.
        Uses PayPal Payouts API if available, otherwise falls back to invoice to winner.
        """
        try:
            return self._submit_payouts_api(idempotency_key, member_id, amount, session=session)
        except httpx.HTTPStatusError as e:
            code, body = e.response.status_code, e.response.text
            if code in (401, 403) or "PAYOUTS_NOT_ENABLED" in body:
                # Payouts isn't enabled for this PayPal app: use the disclosed demo fallback.
                try:
                    return self._fallback_invoice_to_winner(idempotency_key, member_id, amount, session=session)
                except httpx.HTTPStatusError as fe:
                    return PayoutResult(PayoutStatus.FAILED, None,
                                        f"PayPal Payouts is not enabled for this app and the invoice fallback was "
                                        f"rejected ({fe.response.status_code}: {_paypal_error(fe.response.text)})")
                except httpx.HTTPError:
                    return PayoutResult(PayoutStatus.UNKNOWN, None, "payout fallback did not respond")
            if 400 <= code < 500:
                return PayoutResult(PayoutStatus.FAILED, None, f"PayPal rejected the payout ({code}: {_paypal_error(body)})")
            return PayoutResult(PayoutStatus.UNKNOWN, None, f"PayPal error {code}; status unknown")
        except Exception:
            # timeouts and transport errors: neither success nor failure, resolved by the status check
            return PayoutResult(PayoutStatus.UNKNOWN, None, "payout submission failed")

    def _submit_payouts_api(self, idempotency_key: str, member_id: str, amount: Money,
                            session: Optional[Session] = None) -> PayoutResult:
        """Submit via PayPal Payouts API."""
        amount_str = amount.to_major_string()
        currency = amount.currency

        # Resolve the winner's verified contact at the edge (gap #10).
        # Only enforced when a DB session is provided (API path); direct calls skip it.
        receiver_email = None
        if session is not None:
            receiver_email = resolve_contact_email(session, member_id)
            if not receiver_email:
                return PayoutResult(PayoutStatus.FAILED, None, "no verified email contact for member")

        payout = {
            "sender_batch_header": {
                "sender_batch_id": idempotency_key,
                "email_subject": "Your Chit Circle Payout",
                "email_message": "Congratulations! You've received a payout from your chit circle.",
            },
            "items": [
                {
                    "recipient_type": "EMAIL",
                    "amount": {"value": amount_str, "currency": currency},
                    "receiver": receiver_email,
                    "note": "Chit Circle winnings",
                    "sender_item_id": idempotency_key,
                }
            ],
        }

        headers = self._headers()

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{self.base_url}/v1/payments/payouts", headers=headers, json=payout)
            resp.raise_for_status()
            data = resp.json()

            payout_batch_id = data["batch_header"]["payout_batch_id"]
            return PayoutResult(
                status=PayoutStatus.SUBMITTED,
                provider_ref=payout_batch_id,
                detail="Payout submitted via Payouts API",
            )

    def _fallback_invoice_to_winner(self, idempotency_key: str, member_id: str, amount: Money,
                                    session: Optional[Session] = None) -> PayoutResult:
        """
        Fallback: Create an invoice from organizer to winner.
        The winner "pays" the invoice which transfers money from organizer to winner.
        This is a workaround when Payouts API is not enabled.
        """
        # Resolve the winner's verified contact at the edge (gap #10).
        # Only enforced when a DB session is provided (API path); direct calls skip it.
        recipient_email = None
        if session is not None:
            recipient_email = resolve_contact_email(session, member_id)
            if not recipient_email:
                return PayoutResult(PayoutStatus.FAILED, None, "no verified email contact for member")

        invoice_id, _ = self._send_invoice(idempotency_key, recipient_email, amount, "ChitCircle payout",
                                           "Circle payout record (sandbox fallback: PayPal Payouts is not enabled)")
        return PayoutResult(
            status=PayoutStatus.SUBMITTED,
            provider_ref=invoice_id,
            detail="Payout modeled as an invoice record because PayPal Payouts is not enabled; no money moved",
        )

    def lookup_payout(self, idempotency_key: str) -> PayoutResult:
        """Check payout status."""
        headers = self._headers()

        with httpx.Client(timeout=30.0) as client:
            # Try Payouts API first
            try:
                resp = client.get(f"{self.base_url}/v1/payments/payouts/{idempotency_key}", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    batch_status = data["batch_header"]["batch_status"]
                    status_map = {
                        "SUCCESS": PayoutStatus.CONFIRMED,
                        "FAILED": PayoutStatus.FAILED,
                        "PENDING": PayoutStatus.SUBMITTED,
                        "PROCESSING": PayoutStatus.SUBMITTED,
                        "CANCELED": PayoutStatus.FAILED,
                    }
                    return PayoutResult(
                        status=status_map.get(batch_status, PayoutStatus.UNKNOWN),
                        provider_ref=idempotency_key,
                        detail=f"Payouts API: {batch_status}",
                    )
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 404:
                    raise

            # Try invoice lookup (fallback path)
            try:
                resp = client.get(f"{self.base_url}/v2/invoicing/invoices/{idempotency_key}", headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    inv_status = data.get("status", "UNKNOWN")
                    status_map = {
                        "PAID": PayoutStatus.CONFIRMED,
                        "SENT": PayoutStatus.SUBMITTED,
                        "DRAFT": PayoutStatus.SUBMITTED,
                        "CANCELLED": PayoutStatus.FAILED,
                        "REFUNDED": PayoutStatus.FAILED,
                    }
                    return PayoutResult(
                        status=status_map.get(inv_status, PayoutStatus.UNKNOWN),
                        provider_ref=idempotency_key,
                        detail=f"Invoice fallback: {inv_status}",
                    )
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 404:
                    raise

            return PayoutResult(PayoutStatus.UNKNOWN, None, "not found")


# --- PayPal Webhook Verification ---

class PayPalWebhookVerifier:
    """
    Verify PayPal webhook signatures using certificate-based verification.
    PayPal sends the webhook with headers:
    - PAYPAL-TRANSMISSION-ID
    - PAYPAL-TRANSMISSION-TIME
    - PAYPAL-TRANSMISSION-SIG
    - PAYPAL-CERT-URL
    - PAYPAL-AUTH-ALGO (typically SHA256withRSA)
    """

    def __init__(self, webhook_id: str):
        self.webhook_id = webhook_id
        self._cert_cache: dict[str, tuple] = {}

    def verify(self, body: bytes, headers: dict) -> bool:
        """Verify the webhook signature."""
        try:
            h = {k.lower(): v for k, v in headers.items()}      # ASGI header names arrive lower-cased
            transmission_id = h.get("paypal-transmission-id")
            transmission_time = h.get("paypal-transmission-time")
            transmission_sig = h.get("paypal-transmission-sig")
            cert_url = h.get("paypal-cert-url")
            auth_algo = h.get("paypal-auth-algo", "SHA256withRSA")

            if not all([transmission_id, transmission_time, transmission_sig, cert_url]):
                return False
            if not cert_url.startswith(("https://api.paypal.com/", "https://api.sandbox.paypal.com/",
                                        "https://api-m.paypal.com/", "https://api-m.sandbox.paypal.com/")):
                return False

            # PayPal signs transmission_id|time|webhook_id|crc32(body) (decimal CRC32 of the raw body).
            message = f"{transmission_id}|{transmission_time}|{self.webhook_id}|{zlib.crc32(body)}"

            # Get certificate
            cert = self._get_certificate(cert_url)
            if not cert:
                return False

            # Verify signature
            public_key = cert.public_key()
            signature = base64.b64decode(transmission_sig)

            # Use the appropriate algorithm
            if auth_algo == "SHA256withRSA":
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.asymmetric import padding

                public_key.verify(
                    signature,
                    message.encode(),
                    padding.PKCS1v15(),
                    hashes.SHA256(),
                )
                return True

            return False

        except Exception:
            return False

    def _get_certificate(self, cert_url: str):
        """Fetch and cache PayPal's public certificate."""
        if cert_url in self._cert_cache:
            cert, expiry = self._cert_cache[cert_url]
            if time.time() < expiry:
                return cert

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(cert_url)
                resp.raise_for_status()
                cert_pem = resp.text

            from cryptography.hazmat.primitives import serialization
            cert = serialization.load_pem_x509_certificate(cert_pem.encode())

            # Cache for 24 hours
            self._cert_cache[cert_url] = (cert, time.time() + 86400)
            return cert
        except Exception:
            return None


_gateway: PayoutGateway | None = None
_collection_gateway: CollectionGateway | None = None
_webhook_verifier: PayPalWebhookVerifier | None = None


def _paypal_enabled() -> bool:
    """PAYMENT_GATEWAY=mock forces the mock even when PayPal credentials are present."""
    from ..config import get_env
    if (get_env("PAYMENT_GATEWAY") or "").strip().lower() == "mock":
        return False
    return bool(paypal_client_id())


def gateway_name() -> str:
    return "paypal" if isinstance(get_gateway(), PayPalGateway) else "mock"


def get_gateway() -> PayoutGateway:
    global _gateway
    if _gateway is None:
        if _paypal_enabled():
            try:
                _gateway = PayPalGateway()
            except Exception:
                _gateway = MockGateway()
        else:
            _gateway = MockGateway()
    return _gateway


def get_collection_gateway() -> CollectionGateway:
    global _collection_gateway
    if _collection_gateway is None:
        if _paypal_enabled():
            try:
                _collection_gateway = PayPalGateway()
            except Exception:
                _collection_gateway = MockGateway()
        else:
            _collection_gateway = MockGateway()
    return _collection_gateway


def get_webhook_verifier() -> PayPalWebhookVerifier:
    global _webhook_verifier
    if _webhook_verifier is None:
        webhook_id = paypal_webhook_id()
        if webhook_id:
            _webhook_verifier = PayPalWebhookVerifier(webhook_id)
        else:
            # Fallback to HMAC for dev (not secure for production)
            from financial_engine.reconciliation import HmacVerifier
            secret = webhook_secret() or "dev-secret"
            _webhook_verifier = _HmacWrapper(HmacVerifier(secret))
    return _webhook_verifier


class _HmacWrapper:
    """Wrapper to make HMAC verifier compatible with PayPalWebhookVerifier interface."""
    def __init__(self, hmac_verifier):
        self._verifier = hmac_verifier

    def verify(self, body: bytes, headers: dict) -> bool:
        sig = headers.get("X-Signature") or headers.get("x-signature")
        if not sig:
            return False
        return self._verifier.verify(body, sig)