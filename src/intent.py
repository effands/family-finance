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


def extract_account_fields(text: str) -> dict:
    value = " ".join((text or "").split())
    fields = {"account_type": "bank"}
    provider = re.search(r"(?:bank|rekening|akun)\s+(?:baru\s+)?([A-Za-z][A-Za-z0-9 ._-]{1,40}?)(?=\s+(?:atas nama|nama|saldo|no|nomor|norek|rekening|$))", value, re.I)
    holder = re.search(r"(?:atas nama|nama pemilik)\s+([A-Za-z][A-Za-z .'-]{1,60}?)(?=\s+(?:saldo|rp|no|nomor|norek|rekening|$))", value, re.I)
    balance = re.search(r"(?:saldo(?: awal)?|rp)\s*[:=]?\s*([\d.,]+)\s*(?:jt|juta|rb|ribu)?", value, re.I)
    identifier = re.search(r"(?:no(?:mor)?|norek|rekening|id)\s*(?:rekening)?\s*[:=]?\s*([0-9][0-9 -]{2,30})", value, re.I)
    if provider:
        fields["provider"] = provider.group(1).strip()
        fields["name"] = fields["provider"]
    if holder:
        fields["holder_name"] = holder.group(1).strip()
    if balance:
        raw = balance.group(1).replace(".", "").replace(",", "")
        multiplier = balance.group(0).casefold()
        fields["opening_balance"] = str(int(raw) * (1_000_000 if "jt" in multiplier or "juta" in multiplier else 1_000 if "rb" in multiplier or "ribu" in multiplier else 1))
    if identifier:
        fields["account_identifier"] = identifier.group(1).replace(" ", "-")
    return fields
