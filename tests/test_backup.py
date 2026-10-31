import io
import json
import zipfile
from datetime import date, datetime

from src.backup import BackupService
from src.database import Database
from src.models import FinancialAccount, Transaction


def _db(tmp_path):
    db = Database(str(tmp_path / "money.db"))
    db.initialize()
    db.add_transaction(Transaction(None, "u1", "Ayah", "chat-1", "expense", 125000, "Belanja", "Makanan & Minuman", date(2026, 11, 1), datetime(2026, 11, 1, 8, 0)))
    db.create_account(FinancialAccount(None, "chat-1", "Mandiri", "bank", "Bank Mandiri", "Keluarga", "123", "IDR", 1000000, date(2026, 11, 1)), idempotency_key="acct-1")
    return db


def test_export_zip_contains_complete_snapshot_and_checksums(tmp_path):
    db = _db(tmp_path)
    payload = BackupService(db).export_snapshot("chat-1", "zip")

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert {"manifest.json", "snapshot.json", "transactions.csv", "financial_accounts.csv"} <= names
        manifest = json.loads(archive.read("manifest.json"))
        snapshot = archive.read("snapshot.json")
        assert manifest["schema_version"] == 1
        assert manifest["chat_id"] == "chat-1"
        assert manifest["checksums"]["snapshot.json"]
        assert json.loads(snapshot)["transactions"][0]["amount"] == 125000


def test_export_json_does_not_include_secrets(tmp_path):
    db = _db(tmp_path)
    payload = BackupService(db).export_snapshot("chat-1", "json")
    snapshot = json.loads(payload)
    assert "password" not in json.dumps(snapshot).lower()
    assert snapshot["financial_accounts"][0]["account_identifier"] == "123"


def test_preview_rejects_tampered_snapshot_before_restore(tmp_path):
    db = _db(tmp_path)
    payload = BackupService(db).export_snapshot("chat-1", "zip")
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(payload)) as source, zipfile.ZipFile(stream, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            if name == "snapshot.json":
                data += b" "
            target.writestr(name, data)
    try:
        BackupService(db).preview(stream.getvalue(), "backup.zip", "chat-1")
    except ValueError as exc:
        assert "checksum" in str(exc).lower()
    else:
        raise AssertionError("tampered backup must be rejected")


def test_json_snapshot_can_be_previewed(tmp_path):
    db = _db(tmp_path)
    payload = BackupService(db).export_snapshot("chat-1", "json")
    preview = BackupService(db).preview(payload, "backup.json", "chat-1")
    assert preview.format == "json"
    assert preview.counts["transactions"] == 1
