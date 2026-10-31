from datetime import date, datetime

from src.backup import BackupService
from src.database import Database
from src.models import FinancialAccount, Transaction


def _db(path, with_data=True):
    db = Database(str(path))
    db.initialize()
    if with_data:
        db.add_transaction(Transaction(None, "u1", "Ayah", "chat-1", "expense", 125000, "Belanja", "Makanan & Minuman", date(2026, 11, 1), datetime(2026, 11, 1, 8)))
        db.create_account(FinancialAccount(None, "chat-1", "Mandiri", "bank", "Mandiri", "Keluarga", "123", "IDR", 1000000, date(2026, 11, 1)), idempotency_key="acct-1")
    return db


def test_merge_restore_is_idempotent(tmp_path):
    source = _db(tmp_path / "source.db")
    target = _db(tmp_path / "target.db", with_data=False)
    service = BackupService(source)
    payload = service.export_snapshot("chat-1", "zip")

    first = BackupService(target).restore(payload, "backup.zip", "chat-1", "merge", "test")
    second = BackupService(target).restore(payload, "backup.zip", "chat-1", "merge", "test")

    assert first.inserted > 0
    assert second.inserted == 0
    assert second.conflicts > 0
    assert len(target.list_transactions(__import__("src.models", fromlist=["TransactionFilters"]).TransactionFilters("chat-1"))) == 1
    assert len(target.list_accounts("chat-1")) == 1


def test_replace_creates_safety_backup_and_reconstructs_snapshot(tmp_path):
    source = _db(tmp_path / "source.db")
    target = _db(tmp_path / "target.db", with_data=False)
    target.add_transaction(Transaction(None, "u2", "Ibu", "chat-1", "income", 900000, "Lain", "Pemasukan", date(2026, 11, 1), datetime(2026, 11, 1, 9)))
    payload = BackupService(source).export_snapshot("chat-1", "zip")

    result = BackupService(target).restore(payload, "backup.zip", "chat-1", "replace", "test", confirm_replace=True)

    assert result.mode == "replace"
    assert result.safety_backup_path
    assert len(target.list_accounts("chat-1")) == 1
    assert target.get_transaction(2) is None
