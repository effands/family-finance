from types import SimpleNamespace

from src.main import _accounts_for_payment_hint, _explicit_payment_hint


def test_explicit_cash_payment_is_detected():
    assert _explicit_payment_hint("Beli sembako cash 141500") == "cash"


def test_explicit_wallet_payment_is_detected():
    assert _explicit_payment_hint("bayar via GoPay 25000") == "gopay"


def test_payment_hint_is_optional_for_ambiguous_text():
    assert _explicit_payment_hint("beli sembako 141500") is None


def test_cash_hint_never_offers_bank_accounts():
    accounts = [
        SimpleNamespace(account_type="bank", name="BANK MANDIRI", provider="BANK MANDIRI"),
        SimpleNamespace(account_type="ewallet", name="DANA", provider="DANA"),
        SimpleNamespace(account_type="cash", name="CASH", provider="CASH"),
    ]
    assert [a.name for a in _accounts_for_payment_hint(accounts, "cash")] == ["CASH"]
