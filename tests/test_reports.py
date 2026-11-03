from datetime import date, datetime
from src.database import Database
from src.models import Transaction
from src.reports import build_expense_summary, build_income_summary, build_report


def test_monthly_report(tmp_path):
    db = Database(str(tmp_path / "x.db"))
    db.initialize()
    db.add_transaction(Transaction(None, "u", "suami", "c", "expense", 15000, "buah", "Makanan & Minuman", date(2025, 10, 30), datetime(2025, 10, 30, 12)))
    report = build_report(db, "bulan", "c", datetime(2025, 10, 30))
    assert "Rp 15.000" in report and "Makanan & Minuman" in report
    assert "ziqva.com" in report


def test_custom_range_report(tmp_path):
    db = Database(str(tmp_path / "x.db"))
    db.initialize()
    assert "Format periode" not in build_report(db, "2025-10", "c", datetime(2025, 10, 30))


def test_income_and_expense_summaries(tmp_path):
    db = Database(str(tmp_path / "summary.db"))
    db.initialize()
    now = datetime(2026, 10, 15, 10, 0, 0)
    db.add_transaction(Transaction(None, "u1", "Ayah", "c1", "income", 12000000, "Gaji Kantor", "Pemasukan", date(2026, 10, 1), now))
    db.add_transaction(Transaction(None, "u2", "Bunda", "c1", "expense", 450000, "Supermarket", "Makanan & Minuman", date(2026, 10, 2), now))

    inc_rep = build_income_summary(db, "c1", now, "bulan")
    assert "IKHTISAR PEMASUKAN KELUARGA" in inc_rep
    assert "Rp 12.000.000" in inc_rep
    assert "ziqva.com" in inc_rep

    exp_rep = build_expense_summary(db, "c1", now, "bulan")
    assert "IKHTISAR PENGELUARAN KELUARGA" in exp_rep
    assert "Rp 450.000" in exp_rep
    assert "Makanan & Minuman" in exp_rep
    assert "ziqva.com" in exp_rep


def test_reports_include_wealth_ledger_transactions(tmp_path):
    from src.models import FinancialAccount
    from src.wealth import WealthLedger

    db = Database(str(tmp_path / "wealth_rep.db"))
    db.initialize()
    wl = WealthLedger(db)
    acc = db.create_account(
        FinancialAccount(
            None, "c1", "Bank Jago", "bank", "Bank Jago", "Ayah", "12345", "IDR", 10000000, date(2026, 11, 1), True, ""
        )
    )
    now = datetime(2026, 11, 3, 12, 0, 0)
    wl.create_expense("c1", acc.id, 332642, "Bayar indihome Kantor", "Tagihan", date(2026, 11, 3), "u1", "effands")

    exp_rep = build_expense_summary(db, "c1", now, "bulan")
    assert "Rp 332.642" in exp_rep
    assert "1 transaksi" in exp_rep
    assert "Tagihan" in exp_rep
    assert "@effands" in exp_rep

    wl.create_income("c1", acc.id, 5000000, "Bonus Proyek", "Pemasukan", date(2026, 11, 3), "u1", "effands")
    inc_rep = build_income_summary(db, "c1", now, "bulan")
    assert "Rp 5.000.000" in inc_rep
    assert "Bonus Proyek" in inc_rep

    full_rep = build_report(db, "bulan", "c1", now)
    assert "Rp 332.642" in full_rep
    assert "Rp 5.000.000" in full_rep

