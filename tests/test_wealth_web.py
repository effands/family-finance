from datetime import date

from passenger_wsgi import _mask_identifier, _render_wealth_page, _wealth_csrf
from src.database import Database
from src.models import FinancialAccount


def test_wealth_page_renders_summary_and_masks_account_identifier(tmp_path):
    db = Database(str(tmp_path / "wealth.db"))
    db.initialize()
    db.set_setting("web_password", "secret")
    db.create_account(FinancialAccount(None, "family", "Mandiri Utama", "bank", "Bank Mandiri", "Keluarga", "1234567890", "IDR", 100_000_000, date(2026, 11, 1)))
    body = _render_wealth_page(db, "family", _wealth_csrf(db))
    assert "Total Kekayaan" in body
    assert "Rp 100.000.000" in body
    assert "•••• 7890" in body
    assert "1234567890" not in body
    assert _mask_identifier("1234567890") == "•••• 7890"


def test_wealth_page_has_source_and_destination_operation_controls(tmp_path):
    db = Database(str(tmp_path / "wealth.db"))
    db.initialize()
    body = _render_wealth_page(db, "family", _wealth_csrf(db))
    assert "source_account_id" in body
    assert "destination_account_id" in body
    assert "Tarik tunai ATM" in body
