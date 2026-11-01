"""Gap #9: provider payloads must carry an exact, exponent-aware amount string.

`f"{amount.minor / 100:.2f}"` is float division with a hard-coded exponent: it turns 500 JPY into
"5.00", truncates KWD, and loses precision past 2**53. These tests drive the real PayPal adapter
against a capturing transport (no network) and assert the exact strings that leave the process.
"""
import pytest

from financial_engine.money import Money
from app.services import gateway as G


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class _CapturingClient:
    """Stands in for httpx.Client; records every request body and answers from a queue."""

    last_requests: list = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, headers=None, json=None, data=None):
        _CapturingClient.last_requests.append(("POST", url, json))
        if url.endswith("/v2/invoicing/invoices"):
            return _Resp({"id": "INV-1"})
        if url.endswith("/send"):
            return _Resp({"status": "SENT"})
        if url.endswith("/v1/payments/payouts"):
            return _Resp({"batch_header": {"payout_batch_id": "BATCH-1"}})
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url, headers=None):
        _CapturingClient.last_requests.append(("GET", url, None))
        return _Resp({"id": "INV-1"})


@pytest.fixture(autouse=True)
def capturing_transport(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("PAYPAL_BASE_URL", "https://api-m.sandbox.paypal.com")
    _CapturingClient.last_requests = []
    monkeypatch.setattr(G.httpx, "Client", _CapturingClient)
    # preload the token so no OAuth request is attempted
    G._token_cache._local_cache.clear()
    G._token_cache.set("test-client-id:https://api-m.sandbox.paypal.com", "test-token", 3600)
    yield
    G._token_cache._local_cache.clear()


def _bodies():
    return [body for _, _, body in _CapturingClient.last_requests if body]


@pytest.mark.parametrize("minor,currency,expected", [
    (12345, "USD", "123.45"),
    (5, "USD", "0.05"),
    (0, "USD", "0.00"),
    (500, "JPY", "500"),        # exponent 0: the old code sent "5.00"
    (1, "JPY", "1"),
    (1234, "KWD", "1.234"),     # exponent 3: the old code sent "12.34"
    (-999, "USD", "-9.99"),
    (10**15 + 1, "USD", "10000000000000.01"),   # beyond float precision
])
def test_to_major_string_is_exact(minor, currency, expected):
    assert Money(minor, currency).to_major_string() == expected


@pytest.mark.parametrize("minor,currency", [(12345, "USD"), (500, "JPY"), (1234, "KWD"), (0, "EUR")])
def test_to_major_string_round_trips(minor, currency):
    m = Money(minor, currency)
    assert Money.from_major(m.to_major_string(), currency).minor == minor


def test_collection_invoice_carries_exact_jpy_amount():
    gw = G.PayPalGateway()
    res = gw.create_collection(idempotency_key="collection:c1:m1", member_id="m1",
                               amount=Money(500, "JPY"), description="cycle 1",
                               return_url="https://x/ok", cancel_url="https://x/cancel")
    assert res.status == "CREATED"
    create = next(b for b in _bodies() if "items" in b)
    assert create["items"][0]["unit_amount"] == {"currency_code": "JPY", "value": "500"}


def test_payout_carries_exact_kwd_amount():
    gw = G.PayPalGateway()
    res = gw._submit_payouts_api("payout:s1", "m1", Money(1234, "KWD"))
    assert res.provider_ref == "BATCH-1"
    payout = next(b for b in _bodies() if "sender_batch_header" in b)
    assert payout["items"][0]["amount"] == {"value": "1.234", "currency": "KWD"}


def test_invoice_fallback_carries_exact_amount():
    gw = G.PayPalGateway()
    res = gw._fallback_invoice_to_winner("payout:s2", "m1", Money(10_000_001, "USD"))
    assert res.status.value == "SUBMITTED"
    create = next(b for b in _bodies() if "items" in b)
    assert create["items"][0]["unit_amount"]["value"] == "100000.01"
