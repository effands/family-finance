from datetime import datetime

import pytest

from src.parser import ParseError, parse_message


NOW = datetime(2025, 10, 30, 12, 0)


@pytest.mark.parametrize(
    "text,amount",
    [
        ("belanja buah habis 15000", 15000), ("belanja buah 15.000", 15000),
        ("bensin 15rb", 15000), ("bensin 15k", 15000), ("bensin 15ribu", 15000),
        ("gaji masuk 1,5jt", 1500000), ("gaji masuk 1.5jt", 1500000),
        ("gaji 8juta", 8000000), ("bonus 500k", 500000),
        ("bayar listrik 1.250.000", 1250000), ("jajan anak 25 k", 25000),
        ("50.000 bensin", 50000),
    ],
)
def test_parses_rupiah_variants(text, amount):
    result = parse_message(text, NOW, "Asia/Jakarta")
    assert result.amount == amount


def test_income_keywords_are_detected():
    assert parse_message("gaji masuk 8jt", NOW, "Asia/Jakarta").type == "income"
    assert parse_message("dapat cashback 20rb", NOW, "Asia/Jakarta").type == "income"


def test_expense_is_default():
    result = parse_message("belanja buah 15rb", NOW, "Asia/Jakarta")
    assert result.type == "expense"
    assert result.description == "belanja buah"


def test_relative_and_explicit_dates():
    assert parse_message("bensin 50rb kemarin", NOW, "Asia/Jakarta").transaction_date.isoformat() == "2025-10-29"
    assert parse_message("tgl 5 bayar listrik 350rb", NOW, "Asia/Jakarta").transaction_date.isoformat() == "2025-10-05"
    assert parse_message("5/12 belanja 20rb", NOW, "Asia/Jakarta").transaction_date.isoformat() == "2025-12-05"
    assert parse_message("05-12-2025 belanja 20rb", NOW, "Asia/Jakarta").transaction_date.isoformat() == "2025-12-05"


def test_missing_or_zero_amount_is_clarification():
    with pytest.raises(ParseError):
        parse_message("belanja buah", NOW, "Asia/Jakarta")
    with pytest.raises(ParseError):
        parse_message("belanja buah 0", NOW, "Asia/Jakarta")


def test_income_wins_when_explicit_income_and_expense_words_mix():
    assert parse_message("gaji masuk lalu bayar 8jt", NOW, "Asia/Jakarta").type == "income"
