from datetime import date

import pytest

from src.database import Database
from src.models import FinancialAccount
from src.wealth import WealthLedger, InsufficientFundsError


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
