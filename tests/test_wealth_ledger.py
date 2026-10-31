from datetime import date
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.database import Database
from src.models import FinancialAccount
from src.wealth import WealthLedger, InsufficientFundsError, WealthError, parse_idr_amount


def setup_accounts(tmp_path):
    db = Database(str(tmp_path / "wealth.db"))
    db.initialize()
    mandiri = db.create_account(FinancialAccount(None, "family", "Mandiri", "bank", "Mandiri", "Keluarga", "111", "IDR", 100_000_000, date(2026, 11, 1)))
    cash = db.create_account(FinancialAccount(None, "family", "Cash", "cash", "Cash", "Keluarga", "", "IDR", 0, date(2026, 11, 1)))
    investment = db.create_account(FinancialAccount(None, "family", "SBN", "investment", "SBN", "Keluarga", "ORI", "IDR", 0, date(2026, 11, 1)))
    return db, mandiri, cash, investment


def test_atm_withdrawal_moves_money_to_cash_without_changing_wealth(tmp_path):
    db, mandiri, cash, _ = setup_accounts(tmp_path)
    ledger = WealthLedger(db)
    before = ledger.get_wealth_summary("family")

    ledger.create_transfer("family", mandiri.id, cash.id, 3_000_000, "Tarik ATM", date(2026, 11, 1), "u", "Ayah", operation_type="cash_withdrawal", idempotency_key="atm-1")
    balances = {x.account_id: x.balance for x in ledger.get_account_balances("family")}
    after = ledger.get_wealth_summary("family")
    assert balances[mandiri.id] == 97_000_000
    assert balances[cash.id] == 3_000_000
    assert after.total_wealth == before.total_wealth

    ledger.create_expense("family", cash.id, 500_000, "Belanja cash", "Makanan", date(2026, 11, 1), "u", "Ayah", idempotency_key="cash-expense-1")
    balances = {x.account_id: x.balance for x in ledger.get_account_balances("family")}
    assert balances[cash.id] == 2_500_000
    assert ledger.get_wealth_summary("family").total_wealth == before.total_wealth - 500_000


def test_investment_purchase_moves_money_without_income(tmp_path):
    db, mandiri, _, investment = setup_accounts(tmp_path)
    ledger = WealthLedger(db)
    ledger.create_transfer("family", mandiri.id, investment.id, 10_000_000, "Beli SBN", date(2026, 11, 1), "u", "Ayah", operation_type="transfer", idempotency_key="sbn-1")
    balances = {x.account_id: x.balance for x in ledger.get_account_balances("family")}
    assert balances[mandiri.id] == 90_000_000
    assert balances[investment.id] == 10_000_000
    summary = ledger.get_wealth_summary("family")
    assert summary.total_wealth == 100_000_000
    assert summary.investments == 10_000_000
    assert summary.income == 0


def test_insufficient_funds_rolls_back_both_transfer_entries(tmp_path):
    db, mandiri, cash, _ = setup_accounts(tmp_path)
    ledger = WealthLedger(db)
    with pytest.raises(InsufficientFundsError):
        ledger.create_transfer("family", mandiri.id, cash.id, 101_000_000, "Terlalu besar", date(2026, 11, 1), "u", "Ayah", idempotency_key="too-much")
    balances = {x.account_id: x.balance for x in ledger.get_account_balances("family")}
    assert balances[mandiri.id] == 100_000_000
    assert balances[cash.id] == 0


def test_idempotency_returns_same_operation_and_reversal_restores_balances(tmp_path):
    db, mandiri, cash, _ = setup_accounts(tmp_path)
    ledger = WealthLedger(db)
    first = ledger.create_transfer("family", mandiri.id, cash.id, 3_000_000, "Tarik ATM", date(2026, 11, 1), "u", "Ayah", operation_type="cash_withdrawal", idempotency_key="retry")
    second = ledger.create_transfer("family", mandiri.id, cash.id, 3_000_000, "Tarik ATM", date(2026, 11, 1), "u", "Ayah", operation_type="cash_withdrawal", idempotency_key="retry")
    assert first.id == second.id
    ledger.reverse_operation("family", first.id, "u", "Salah input")
    balances = {x.account_id: x.balance for x in ledger.get_account_balances("family")}
    assert balances[mandiri.id] == 100_000_000
    assert balances[cash.id] == 0


def test_expense_retry_returns_original_even_after_balance_changes(tmp_path):
    db, mandiri, _, _ = setup_accounts(tmp_path)
    ledger = WealthLedger(db)
    first = ledger.create_expense("family", mandiri.id, 90_000_000, "Belanja besar", "Belanja", date(2026, 11, 1), "u", "Ayah", idempotency_key="expense-retry")
    ledger.create_expense("family", mandiri.id, 10_000_000, "Belanja lain", "Belanja", date(2026, 11, 1), "u", "Ayah", idempotency_key="expense-other")
    retry = ledger.create_expense("family", mandiri.id, 90_000_000, "Belanja besar", "Belanja", date(2026, 11, 1), "u", "Ayah", idempotency_key="expense-retry")
    assert retry.id == first.id


def test_concurrent_expenses_cannot_overspend_account(tmp_path):
    db, mandiri, _, _ = setup_accounts(tmp_path)
    ledger = WealthLedger(db)

    def spend(key):
        try:
            ledger.create_expense("family", mandiri.id, 80_000_000, "Concurrent", "Belanja", date(2026, 11, 1), "u", "Ayah", idempotency_key=key)
            return True
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(spend, ["concurrent-a", "concurrent-b"]))
    assert sum(results) == 1
    assert ledger.get_account_balances("family")[0].balance >= 0


def test_atm_requires_cash_destination_and_transfer_fee_is_expense(tmp_path):
    db, mandiri, _, investment = setup_accounts(tmp_path)
    ledger = WealthLedger(db)
    with pytest.raises(Exception, match="Cash"):
        ledger.create_transfer("family", mandiri.id, investment.id, 1_000_000, "ATM salah", date(2026, 11, 1), "u", "Ayah", operation_type="cash_withdrawal", idempotency_key="atm-wrong")
    ledger.create_transfer("family", mandiri.id, investment.id, 1_000_000, "Beli SBN", date(2026, 11, 1), "u", "Ayah", fee_amount=5_000, idempotency_key="fee")
    summary = ledger.get_wealth_summary("family")
    assert summary.expense == 5_000
    assert summary.total_wealth == 99_995_000


def test_idr_parser_rejects_fractional_or_ambiguous_amounts():
    assert parse_idr_amount("Rp 1.000.000") == 1_000_000
    with pytest.raises(WealthError):
        parse_idr_amount("1.000,00")
    with pytest.raises(WealthError):
        parse_idr_amount("abc")
