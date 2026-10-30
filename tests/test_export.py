from datetime import date, datetime
import io
import openpyxl
from passenger_wsgi import application
from src.database import Database
from src.export_report import generate_excel, generate_pdf
from src.models import Transaction


def _dummy_transactions():
    return [
        Transaction(
            id=101,
            user_id="u1",
            username="Ayah",
            chat_id="-1001",
            type="income",
            amount=15000000,
            description="Gaji Bulanan",
            category="Pemasukan",
            transaction_date=date(2026, 10, 1),
            created_at=datetime(2026, 10, 1, 9, 0, 0),
        ),
        Transaction(
            id=102,
            user_id="u2",
            username="Bunda",
            chat_id="-1001",
            type="expense",
            amount=350000,
            description="Belanja Mingguan Supermarket",
            category="Makanan & Minuman",
            transaction_date=date(2026, 10, 5),
            created_at=datetime(2026, 10, 5, 14, 30, 0),
        ),
    ]


def test_generate_excel():
    txs = _dummy_transactions()
    summary = {"income": 15000000, "expense": 350000, "savings_rate": 97.7}
    excel_bytes = generate_excel(txs, summary, "month")
    assert len(excel_bytes) > 2000

    # Verify openpyxl can load the bytes
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    assert "Rekap Keuangan" in wb.sheetnames
    ws = wb["Rekap Keuangan"]
    # Check title row
    assert "FINANCE FAMILY" in str(ws["A1"].value)
    # Check transactions
    found_desc = False
    for row in ws.iter_rows(values_only=True):
        if "Belanja Mingguan Supermarket" in [str(c) for c in row if c is not None]:
            found_desc = True
            break
    assert found_desc


def test_generate_pdf():
    txs = _dummy_transactions()
    summary = {"income": 15000000, "expense": 350000, "savings_rate": 97.7}
    pdf_bytes = generate_pdf(txs, summary, "month")
    assert len(pdf_bytes) > 2000
    # PDF signature %PDF-
    assert pdf_bytes.startswith(b"%PDF-")


def test_wsgi_export_routes(tmp_path, monkeypatch):
    db_path = str(tmp_path / "wsgi_test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("BOT_TOKEN", "mock-token")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "-1001")
    monkeypatch.setenv("WEB_PASSWORD", "testpass")

    db = Database(db_path)
    db.initialize()
    for tx in _dummy_transactions():
        db.add_transaction(tx)

    # Helper to call WSGI
    def call_app(path, cookie=""):
        status_box = []
        headers_box = []

        def start_response(status, headers):
            status_box.append(status)
            headers_box.extend(headers)

        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": path,
            "QUERY_STRING": "period=all",
            "HTTP_COOKIE": cookie,
            "wsgi.input": io.BytesIO(),
        }
        body = b"".join(application(environ, start_response))
        return status_box[0], dict(headers_box), body

    # Test without auth (should return login page)
    status, headers, body = call_app("/keuangan/export.xlsx")
    assert status.startswith("200")
    assert "text/html" in headers.get("Content-Type", "")
    assert b"password" in body.lower()

    # Generate valid session cookie
    import hashlib
    session_val = hashlib.sha256("testpass".encode("utf-8")).hexdigest()
    cookie = f"ff_session={session_val}"

    # Export Excel
    status, headers, body = call_app("/keuangan/export.xlsx", cookie)
    assert status.startswith("200")
    assert "spreadsheetml" in headers.get("Content-Type", "")
    assert len(body) > 2000

    # Export PDF
    status, headers, body = call_app("/keuangan/export.pdf", cookie)
    assert status.startswith("200")
    assert headers.get("Content-Type") == "application/pdf"
    assert body.startswith(b"%PDF-")
