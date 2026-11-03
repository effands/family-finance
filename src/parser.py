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
_REF_PATTERN = re.compile(
    r"\b(?:nomer|nomor|no\.?|id|rek(?:ening)?|va|token|ref(?:erensi)?|pln|meter(?:an)?|telepon|telp|hp)\s*(?:pelanggan|tagihan|transaksi|tujuan|rekening)?\s*[:#-]?\s*(\d+)\b",
    re.I,
)
_DATE_PATTERN = re.compile(
    r"\b(?:kemarin|tgl\s+\d{1,2}|tanggal\s+\d{1,2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{4})?)\b",
    re.I,
)
_AMOUNT_PREFIX = re.compile(
    r"\b(?:sebesar|sejumlah|senilai|total|biaya|harga|rp\.?|nominal)\s*[:=]?\s*$",
    re.I,
)


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

    date_spans = [m.span(0) for m in _DATE_PATTERN.finditer(text)]
    ref_spans = [m.span(1) for m in _REF_PATTERN.finditer(text)]

    candidates = []
    for m in _AMOUNT.finditer(text):
        m_span = m.span()
        if any(ds[0] <= m_span[0] and m_span[1] <= ds[1] for ds in date_spans):
            continue

        raw_num, suffix = m.group(1), m.group(2)
        score = 0

        # Substantial penalty if inside reference/ID pattern (e.g. nomer pelanggan 152702245514)
        if any(rs[0] <= m_span[0] and m_span[1] <= rs[1] for rs in ref_spans):
            score -= 100

        prefix_text = text[:m.start()].rstrip()
        prefix_match = _AMOUNT_PREFIX.search(prefix_text)
        if prefix_match:
            score += 100

        if suffix:
            score += 50
        if "." in raw_num or "," in raw_num:
            score += 20
        # If number is very long plain digits without dots/commas/suffix, likely an ID or phone
        if len(raw_num) >= 9 and not suffix and "." not in raw_num and "," not in raw_num:
            score -= 60

        candidates.append((score, m, prefix_match))

    if not candidates:
        raise ParseError("Nominal belum terbaca. Contoh: belanja buah 15rb")

    candidates.sort(key=lambda c: c[0], reverse=True)
    best_score, best_match, best_prefix = candidates[0]

    amount = _number(best_match.group(1), best_match.group(2))
    if amount <= 0:
        raise ParseError("Nominal harus lebih dari Rp 0")

    lowered = text.casefold()
    tx_type = "income" if any(word in lowered for word in _INCOME) else "expense"

    start_cut = best_prefix.start() if best_prefix else best_match.start()
    end_cut = best_match.end()
    description = text[:start_cut] + " " + text[end_cut:]
    description = _DATE_PATTERN.sub(" ", description)
    description = re.sub(r"\s+", " ", description).strip(" -,.\t")

    return ParsedTransaction(tx_type, amount, description or "Tanpa deskripsi", _date(text, now), [])
