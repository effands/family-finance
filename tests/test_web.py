from datetime import date

from passenger_wsgi import _import_csv, _period_bounds, _safe_csv_value
from src.database import Database


def test_period_bounds_supports_week_and_custom():
    start, end, period = _period_bounds({"period": ["week"]})
    assert period == "week"
    assert start.weekday() == 0
    assert (end - start).days == 6

    start, end, period = _period_bounds({"period": ["custom"], "start": ["2026-10-01"], "end": ["2026-10-07"]})
    assert (start, end, period) == (date(2026, 10, 1), date(2026, 10, 7), "custom")


def test_csv_import_adds_rows_without_replacing_existing_data(tmp_path):
    db = Database(str(tmp_path / "money.db"))
    db.initialize()
    csv_text = "tanggal,tipe,nominal,deskripsi,kategori,user\n2026-10-30,pengeluaran,15.000,belanja buah,Makanan & Minuman,suami\n"
    inserted, errors = _import_csv(db, csv_text, "-123")
    assert inserted == 1
    assert errors == []
    assert db.get_transaction(1).amount == 15000


def test_csv_value_is_safe_for_spreadsheets():
    assert _safe_csv_value("=SUM(A1)") == "'=SUM(A1)"
    assert _safe_csv_value("belanja") == "belanja"
