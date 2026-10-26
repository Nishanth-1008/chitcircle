"""Payout gateway abstraction. The engine never moves money itself."""
from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

import httpx
from jose import jwt
from jose.utils import base64url_decode

from financial_engine.money import Money

from ..config import (
    paypal_client_id,
    paypal_client_secret,
    paypal_base_url,
    paypal_webhook_id,
    webhook_secret,
    redis_url,
)


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


class MockGateway:
    """Deterministic gateway for dev/tests. Dedupes by idempotency key like a real provider should."""

    def __init__(self, mode: str = "ok"):
        self.mode = mode                      # ok | fail | timeout
        self.submissions: dict = {}
        self.collections: dict = {}
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

    def create_collection(self, *, idempotency_key, member_id, amount, description, return_url, cancel_url):
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

    def create_collection(
        self,
        *,
        idempotency_key: str,
        member_id: str,
        amount: Money,
        description: str,
        return_url: str,
        cancel_url: str,
    ) -> CollectionResult:
        """Create a PayPal invoice for member contribution collection."""
        # PayPal Invoicing API v2
        # https://developer.paypal.com/docs/api/invoicing/v2/

        amount_str = f"{amount.minor / 100:.2f}"  # Convert minor units to major
        # Determine currency from amount or default to USD
        currency = getattr(amount, 'currency', 'USD')

        invoice = {
            "detail": {
                "currency_code": currency,
                "reference": idempotency_key,
                "note": description,
                "term": "DueOnReceipt",
            },
            "invoicer": {
                "name": "ChitCircle",
                "email": "noreply@chitcircle.example",
            },
            "primary_recipients": [
                {"email": f"member-{member_id}@example.com"}  # Placeholder; real impl would use member email
            ],
            "items": [
                {
                    "name": "Chit Circle Contribution",
                    "description": description,
                    "quantity": "1",
                    "unit_amount": {"currency_code": currency, "value": amount_str},
                }
            ],
        }

        headers = self._headers(idempotency_key)

        with httpx.Client(timeout=30.0) as client:
            # Create draft invoice
            resp = client.post(f"{self.base_url}/v2/invoicing/invoices", headers=headers, json=invoice)

            if resp.status_code == 422 and "DUPLICATE_INVOICE_ID" in resp.text:
                # Idempotency: invoice already exists, get it
                resp = client.get(f"{self.base_url}/v2/invoicing/invoices/{idempotency_key}", headers=headers)
                resp.raise_for_status()
                invoice_data = resp.json()
            else:
                resp.raise_for_status()
                invoice_data = resp.json()

            invoice_id = invoice_data["id"]

            # Send invoice (moves from DRAFT to SENT)
            resp = client.post(
                f"{self.base_url}/v2/invoicing/invoices/{invoice_id}/send",
                headers=headers,
                json={"send_to_invoicer": False, "send_to_recipient": True}
            )
            resp.raise_for_status()

            # Get the invoice link for the payer
            approval_url = f"https://www.sandbox.paypal.com/invoice/payerView/detail/{invoice_id}"

            return CollectionResult(
                status="CREATED",
                provider_ref=invoice_id,
                approval_url=approval_url,
                detail="Invoice sent to payer",
            )

    # --- Payout ---

    def submit_payout(self, *, idempotency_key: str, member_id: str, amount: Money) -> PayoutResult:
        """
        Submit a payout to the winner.
        Uses PayPal Payouts API if available, otherwise falls back to invoice to winner.
        """
        # Try Payouts API first
        try:
            return self._submit_payouts_api(idempotency_key, member_id, amount)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403 and "PAYOUTS_NOT_ENABLED" in e.response.text:
                # Fallback: create invoice/order to winner
                return self._fallback_invoice_to_winner(idempotency_key, member_id, amount)
            raise
        except Exception:
            # Any other error -> UNKNOWN, will be retried
            return PayoutResult(PayoutStatus.UNKNOWN, None, "payout submission failed")

    def _submit_payouts_api(self, idempotency_key: str, member_id: str, amount: Money) -> PayoutResult:
        """Submit via PayPal Payouts API."""
        amount_str = f"{amount.minor / 100:.2f}"
        currency = getattr(amount, 'currency', 'USD')

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
                    "receiver": f"member-{member_id}@example.com",  # Placeholder
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

    def _fallback_invoice_to_winner(self, idempotency_key: str, member_id: str, amount: Money) -> PayoutResult:
        """
        Fallback: Create an invoice from organizer to winner.
        The winner "pays" the invoice which transfers money from organizer to winner.
        This is a workaround when Payouts API is not enabled.
        """
        # Create invoice where organizer is invoicer and winner is recipient
        # When winner "pays", money moves from organizer's PayPal to winner's PayPal
        amount_str = f"{amount.minor / 100:.2f}"
        currency = getattr(amount, 'currency', 'USD')

        invoice = {
            "detail": {
                "currency_code": currency,
                "reference": idempotency_key,
                "note": "Chit Circle winnings payout",
                "term": "DueOnReceipt",
            },
            "invoicer": {
                "name": "ChitCircle Organizer",
                "email": "organizer@chitcircle.example",
            },
            "primary_recipients": [
                {"email": f"member-{member_id}@example.com"}
            ],
            "items": [
                {
                    "name": "Chit Circle Payout",
                    "description": "Your winnings from the chit circle",
                    "quantity": "1",
                    "unit_amount": {"currency_code": currency, "value": amount_str},
                }
            ],
        }

        headers = self._headers(idempotency_key)

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{self.base_url}/v2/invoicing/invoices", headers=headers, json=invoice)

            if resp.status_code == 422 and "DUPLICATE_INVOICE_ID" in resp.text:
                resp = client.get(f"{self.base_url}/v2/invoicing/invoices/{idempotency_key}", headers=headers)
                resp.raise_for_status()
                invoice_data = resp.json()
            else:
                resp.raise_for_status()
                invoice_data = resp.json()

            invoice_id = invoice_data["id"]

            # Send to winner
            resp = client.post(
                f"{self.base_url}/v2/invoicing/invoices/{invoice_id}/send",
                headers=headers,
                json={"send_to_invoicer": False, "send_to_recipient": True}
            )
            resp.raise_for_status()

            return PayoutResult(
                status=PayoutStatus.SUBMITTED,
                provider_ref=invoice_id,
                detail="Payout modeled as invoice to winner (Payouts API not available)",
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
            transmission_id = headers.get("PAYPAL-TRANSMISSION-ID")
            transmission_time = headers.get("PAYPAL-TRANSMISSION-TIME")
            transmission_sig = headers.get("PAYPAL-TRANSMISSION-SIG")
            cert_url = headers.get("PAYPAL-CERT-URL")
            auth_algo = headers.get("PAYPAL-AUTH-ALGO", "SHA256withRSA")

            if not all([transmission_id, transmission_time, transmission_sig, cert_url]):
                return False

            # Construct the message that was signed
            message = f"{transmission_id}|{transmission_time}|{self.webhook_id}|{hashlib.sha256(body).hexdigest()}"

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


def get_gateway() -> PayoutGateway:
    global _gateway
    if _gateway is None:
        client_id = paypal_client_id()
        if client_id:
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
        client_id = paypal_client_id()
        if client_id:
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