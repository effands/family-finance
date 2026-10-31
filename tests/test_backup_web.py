from passenger_wsgi import _render_backup_page, _wealth_csrf
from src.database import Database


def test_backup_center_exposes_exports_import_and_reports(tmp_path):
    db = Database(str(tmp_path / "money.db"))
    db.initialize()
    body = _render_backup_page(db, "family", _wealth_csrf(db))
    assert "Unduh ZIP Lengkap" in body
    assert "/keuangan/backup/preview" in body
    assert "Posisi Kekayaan" in body
    assert "Preview Replace" in body
