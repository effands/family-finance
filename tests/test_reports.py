from datetime import date, datetime
from src.database import Database
from src.models import Transaction
from src.reports import build_report

def test_monthly_report(tmp_path):
    db=Database(str(tmp_path/"x.db")); db.initialize(); db.add_transaction(Transaction(None,"u","suami","c","expense",15000,"buah","Makanan & Minuman",date(2025,10,30),datetime(2025,10,30,12)))
    report=build_report(db,"bulan","c",datetime(2025,10,30))
    assert "Rp 15.000" in report and "Makanan & Minuman" in report

def test_custom_range_report(tmp_path):
    db=Database(str(tmp_path/"x.db")); db.initialize()
    assert "Format periode" not in build_report(db,"2025-10","c",datetime(2025,10,30))
