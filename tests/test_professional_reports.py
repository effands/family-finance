from datetime import date, datetime

from src.database import Database
from src.models import FinancialAccount, Transaction
from src.professional_reports import build_professional_report, render_report_html


def test_wealth_report_uses_account_balances_and_is_printable(tmp_path):
    db = Database(str(tmp_path / "money.db"))
    db.initialize()
    db.create_account(FinancialAccount(None, "chat-1", "Mandiri", "bank", "Mandiri", "Keluarga", "123", "IDR", 1000000, date(2026, 11, 1)), idempotency_key="a")
    report = build_professional_report(db, "chat-1", "wealth", None, None)
    html = render_report_html(report, print_mode=True)
    assert report.title == "Posisi Kekayaan"
    assert "Rp 1.000.000" in html
    assert "@media print" in html
    assert "Print" not in html


def test_cashflow_report_respects_date_range(tmp_path):
    db = Database(str(tmp_path / "money.db"))
    db.initialize()
    db.add_transaction(Transaction(None, "u", "A", "chat-1", "income", 500000, "Gaji", "Pemasukan", date(2026, 10, 1), datetime(2026, 10, 1, 8)))
    db.add_transaction(Transaction(None, "u", "A", "chat-1", "expense", 100000, "Makan", "Makanan & Minuman", date(2026, 11, 1), datetime(2026, 11, 1, 8)))
    report = build_professional_report(db, "chat-1", "cashflow", date(2026, 11, 1), date(2026, 11, 30))
    assert report.totals["income"] == 0
    assert report.totals["expense"] == 100000
