from financial_engine.money import Money
from financial_engine.reconciliation import (HmacVerifier, ProviderTxn, TxnKind, reconcile_payments,
                                             reconcile_payout)

INR = lambda n: Money(n, "INR")  # noqa: E731


def pay(i, m, amt, status="COMPLETED", kind=TxnKind.PAYMENT):
    return ProviderTxn(i, kind, status, INR(amt), m)


def test_clean_reconciliation_with_refund():
    rep = reconcile_payments({"m1": INR(450)}, [pay("t1", "m1", 500), pay("t2", "m1", 50, kind=TxnKind.REFUND)],
                             {"m1": INR(450)})
    assert rep.is_clean


def test_discrepancies():
    rep = reconcile_payments({"m1": INR(500)}, [pay("t1", "m1", 400)], {"m1": INR(500)})
    codes = {d.code for d in rep.discrepancies}
    assert {"INTERNAL_PROVIDER_MISMATCH", "UNDERPAID"} <= codes
    rep = reconcile_payments({"m1": INR(500)}, [pay("t1", "m1", 500), pay("t1", "m1", 500)], {"m1": INR(450)})
    assert {"DUPLICATE_PROVIDER_TXN", "OVERPAID"} <= {d.code for d in rep.discrepancies}


def test_pending_is_unresolved_not_clean():
    assert reconcile_payments({"m1": INR(0)}, [pay("t1", "m1", 10, status="PENDING")]).unresolved


def test_payout_reconciliation():
    ok = ProviderTxn("p1", TxnKind.PAYOUT, "COMPLETED", INR(100))
    assert reconcile_payout(INR(100), ok).is_clean
    assert not reconcile_payout(INR(101), ok).is_clean
    assert reconcile_payout(INR(100), None).unresolved          # timeout: never assumed success or failure


def test_hmac_verifier_fails_safe():
    v = HmacVerifier("s3cret")
    sig = v.sign(b"body")
    assert v.verify(b"body", sig) and not v.verify(b"body2", sig) and not v.verify(b"body", None)
    assert not HmacVerifier(None).verify(b"body", sig)
