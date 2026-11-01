from src.main import _explicit_payment_hint


def test_explicit_cash_payment_is_detected():
    assert _explicit_payment_hint("Beli sembako cash 141500") == "cash"


def test_explicit_wallet_payment_is_detected():
    assert _explicit_payment_hint("bayar via GoPay 25000") == "gopay"


def test_payment_hint_is_optional_for_ambiguous_text():
    assert _explicit_payment_hint("beli sembako 141500") is None
