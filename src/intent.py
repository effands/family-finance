"""Lightweight intent detection before transaction parsing."""
import re


def classify_finance_intent(text: str) -> str:
    value = " ".join((text or "").casefold().split())
    account_words = ("bank baru", "tambah bank", "input bank", "rekening baru", "akun bank",
                     "e-wallet baru", "tambah ewallet", "tambah e-wallet", "akun baru")
    balance_words = ("saldo awal", "saldo bank", "saldo rekening", "saldo ")
    if any(word in value for word in account_words) and any(word in value for word in balance_words):
        return "account_add"
    if any(word in value for word in ("tarik tunai", "tarik atm", "tarik saldo", "ambil uang di atm")):
        return "cash_withdrawal"
    if any(word in value for word in ("transfer", "pindah saldo", "kirim uang")):
        return "transfer"
    return "transaction"


def account_request_summary(text: str) -> str:
    value = " ".join((text or "").split())
    match = re.search(r"(?:bank|rekening|akun)\s+(?:baru\s+)?([A-Za-z0-9][A-Za-z0-9 ._-]{1,40}?)(?=\s+(?:atas nama|nama|saldo|rp|$))", value, re.I)
    account_name = match.group(1).strip() if match else "akun baru"
    return account_name
