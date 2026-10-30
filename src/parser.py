from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedTransaction:
    type: str
    amount: int
    description: str
    transaction_date: date
    warnings: list[str]


_AMOUNT = re.compile(r"(?<!\w)(\d[\d.,]*)(?:\s*)(rb|ribu|k|jt|juta)?(?!\w)", re.I)
_INCOME = ("gaji", "masuk", "terima", "bonus", "jual", "untung", "cashback", "refund", "dapat", "thr")


def _number(raw: str, suffix: str | None) -> int:
    suffix = (suffix or "").casefold()
    if suffix in {"rb", "ribu", "k"}:
        normalized = raw.replace(".", "").replace(",", ".")
        return int(round(float(normalized) * 1000))
    if suffix in {"jt", "juta"}:
        normalized = raw.replace(",", ".")
        if normalized.count(".") > 1:
            normalized = normalized.replace(".", "")
        return int(round(float(normalized) * 1_000_000))
    if "," in raw:
        return int(float(raw.replace(".", "").replace(",", ".")))
    if raw.count(".") > 1 or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", raw):
        return int(raw.replace(".", ""))
    return int(raw)


def _date(text: str, now: datetime) -> date:
    lowered = text.casefold()
    if "kemarin" in lowered:
        return (now - timedelta(days=1)).date()
    match = re.search(r"\b(?:tgl|tanggal)\s+(\d{1,2})\b", lowered)
    if match:
        return date(now.year, now.month, int(match.group(1)))
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?\b", lowered)
    if match:
        return date(int(match.group(3) or now.year), int(match.group(2)), int(match.group(1)))
    return now.date()


def parse_message(text: str, now: datetime, timezone: str = "Asia/Jakarta") -> ParsedTransaction:
    if not text or not text.strip():
        raise ParseError("Tulis nominalnya, misalnya: bensin 50rb")
    match = _AMOUNT.search(text)
    if not match:
        raise ParseError("Nominal belum terbaca. Contoh: belanja buah 15rb")
    amount = _number(match.group(1), match.group(2))
    if amount <= 0:
        raise ParseError("Nominal harus lebih dari Rp 0")
    lowered = text.casefold()
    tx_type = "income" if any(word in lowered for word in _INCOME) else "expense"
    description = text[:match.start()] + " " + text[match.end():]
    description = re.sub(r"\b(?:kemarin|tgl\s+\d{1,2}|tanggal\s+\d{1,2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{4})?)\b", " ", description, flags=re.I)
    description = re.sub(r"\s+", " ", description).strip(" -,.\t")
    return ParsedTransaction(tx_type, amount, description or "Tanpa deskripsi", _date(text, now), [])
