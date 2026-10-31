from datetime import date

import pytest

from src.database import Database
from src.models import FinancialAccount


def test_create_and_list_bank_account_with_effective_opening_balance(tmp_path):
    db = Database(str(tmp_path / "wealth.db"))
    db.initialize()

    account = db.create_account(
        FinancialAccount(
            id=None,
            chat_id="family",
            name="Mandiri Utama",
            account_type="bank",
            provider="Bank Mandiri",
            holder_name="Keluarga",
            account_identifier="1234567890",
            currency="IDR",
            opening_balance=100_000_000,
            opening_balance_date=date(2026, 11, 1),
            is_active=True,
            notes="Rekening utama",
        )
    )

    loaded = db.list_accounts("family")
    assert account.id is not None
    assert len(loaded) == 1
    assert loaded[0].name == "Mandiri Utama"
    assert loaded[0].opening_balance == 100_000_000
    assert loaded[0].opening_balance_date == date(2026, 11, 1)


def test_account_rejects_non_idr_and_negative_opening_balance(tmp_path):
    db = Database(str(tmp_path / "wealth.db"))
    db.initialize()
    base = dict(
        id=None,
        chat_id="family",
        name="Crypto",
        account_type="investment",
        provider="Exchange",
        holder_name="Keluarga",
        account_identifier="wallet",
        currency="USD",
        opening_balance=0,
        opening_balance_date=date(2026, 11, 1),
        is_active=True,
        notes="",
    )
    with pytest.raises(ValueError, match="IDR"):
        db.create_account(FinancialAccount(**base))

    base["currency"] = "IDR"
    base["opening_balance"] = -1
    with pytest.raises(ValueError, match="positif"):
        db.create_account(FinancialAccount(**base))


def test_schema_migration_is_idempotent(tmp_path):
    db = Database(str(tmp_path / "wealth.db"))
    db.initialize()
    db.initialize()
    assert db.list_accounts("family") == []


def test_account_creation_idempotency_returns_existing_account(tmp_path):
    db = Database(str(tmp_path / "wealth.db"))
    db.initialize()
    account = FinancialAccount(None, "family", "Mandiri", "bank", "Mandiri", "Keluarga", "1234", "IDR", 100, date(2026, 11, 1))
    first = db.create_account(account, idempotency_key="account-submit-1")
    retry = db.create_account(account, idempotency_key="account-submit-1")
    assert retry.id == first.id
    assert len(db.list_accounts("family")) == 1
