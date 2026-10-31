from datetime import date

from src.database import Database
from src.models import FinancialAccount
from src.wealth import WealthLedger


def test_default_account_and_reconciliation_create_auditable_adjustment(tmp_path):
    db = Database(str(tmp_path / "wealth.db"))
    db.initialize()
    account = db.create_account(FinancialAccount(None, "family", "Mandiri", "bank", "Mandiri", "Keluarga", "1234", "IDR", 100_000_000, date(2026, 11, 1)))
    ledger = WealthLedger(db)

    ledger.set_default_account("family", "expense", account.id)
    assert ledger.get_default_account("family", "expense").id == account.id
    operation = ledger.reconcile_account("family", account.id, 99_500_000, "Selisih biaya admin", date(2026, 11, 1), "u", "Ayah")
    assert operation.operation_type == "adjustment"
    assert ledger.get_account_balances("family")[0].balance == 99_500_000


def test_archived_account_stays_in_history_but_cannot_be_used(tmp_path):
    db = Database(str(tmp_path / "wealth.db"))
    db.initialize()
    account = db.create_account(FinancialAccount(None, "family", "GoPay Lama", "ewallet", "GoPay", "Keluarga", "0812", "IDR", 0, date(2026, 11, 1)))
    ledger = WealthLedger(db)
    ledger.create_income("family", account.id, 80_000, "Isi saldo", "", date(2026, 11, 1), "u", "Ayah", idempotency_key="seed")
    ledger.archive_account("family", account.id, "u")
    assert db.list_accounts("family") == []
    assert db.list_accounts("family", include_archived=True)[0].is_active is False
    assert ledger.get_wealth_summary("family").total_wealth == 80_000
