"""Passenger WSGI entrypoint for Telegram webhook and family dashboard."""
import csv, hashlib, html, io, json, os
from datetime import date, datetime, timedelta
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from src.categorizer import categorize
from src.config import load_settings
from src.database import Database
from src.formatting import format_rupiah, render_confirmation
from src.models import Transaction, TransactionFilters
from src.parser import ParseError, parse_message

TITLE = "Finance Family — Catatan Keuangan Keluarga"

def _send_message(chat_id, text):
    body = urlencode({"chat_id": chat_id, "text": text}).encode()
    req = Request(f"https://api.telegram.org/bot{os.environ['BOT_TOKEN']}/sendMessage", data=body, method="POST")
    with urlopen(req, timeout=20): pass

def _set_webhook():
    token = os.environ.get("BOT_TOKEN")
    if not token: return
    body = urlencode({"url": "https://asistenq.com/keuangan/"}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/setWebhook", data=body, method="POST")
    with urlopen(req, timeout=20): pass

def _authorized(environ):
    password = os.environ.get("WEB_PASSWORD")
    if not password: return False
    cookie = SimpleCookie(environ.get("HTTP_COOKIE", "")); expected = hashlib.sha256(password.encode()).hexdigest()
    return bool(cookie.get("ff_session") and cookie["ff_session"].value == expected)

def _html_page(title, body, status="200 OK", headers=None):
    markup = f"<!doctype html><html lang='id'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><meta name='description' content='Pembukuan keluarga yang sederhana dan rapi'><link rel='stylesheet' href='/keuangan/static/app.css'></head><body>{body}</body></html>"
    payload = markup.encode(); return status, [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(payload)))] + (headers or []), [payload]

def _auth_page(error=""):
    alert = f"<div class='alert'>{html.escape(error)}</div>" if error else ""
    return f"<main class='auth-page'><section class='auth-layout'><aside class='auth-aside'><div><div class='brand-lockup'><div class='brand-mark'>FF</div><strong>Finance Family</strong></div><h1 style='font-size:42px;line-height:1.05;margin:56px 0 12px'>Uang keluarga,<br>lebih mudah dipahami.</h1><p>Catat dari Telegram. Pantau ringkasannya dari mana saja.</p></div><div class='footer-note'>Ruang privat untuk pembukuan keluarga</div></aside><section class='auth-card'><div class='eyebrow'>Dashboard keluarga</div><h1>Selamat datang</h1><p class='muted'>Masuk untuk melihat ringkasan keuangan.</p>{alert}<form method='post'><label for='password'>Password dashboard</label><input id='password' name='password' type='password' autocomplete='current-password' autofocus required><button type='submit'>Masuk ke dashboard</button></form></section></section></main>"

def _period_bounds(query):
    today = date.today(); period = query.get("period", ["month"])[0]
    if period == "week": start = today - timedelta(days=today.weekday()); end = start + timedelta(days=6)
    elif period == "all": start = end = None
    elif period == "custom":
        try: start = date.fromisoformat(query.get("start", [today.isoformat()])[0]); end = date.fromisoformat(query.get("end", [today.isoformat()])[0])
        except ValueError: raise ValueError("Tanggal custom tidak valid.")
    else:
        start = today.replace(day=1); end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1); period = "month"
    if start and end and start > end: raise ValueError("Tanggal mulai tidak boleh melewati tanggal akhir.")
    return start, end, period

def _filters(query, chat_id):
    start, end, period = _period_bounds(query); tx_type = query.get("type", [""])[0] or None; category = query.get("category", [""])[0] or None; search = query.get("q", [""])[0].strip() or None
    return TransactionFilters(chat_id, start, end, None, tx_type, category, search, query.get("sort", ["transaction_date"])[0], query.get("dir", ["desc"])[0]), period

def _rows_html(rows):
    if not rows: return "<tr><td colspan='7'><div class='empty-state'>Belum ada transaksi pada filter ini.</div></td></tr>"
    return "".join(f"<tr><td>{x.id}</td><td>{x.transaction_date:%d/%m/%Y}</td><td><span class='badge {'income' if x.type == 'income' else 'expense'}'>{'Pemasukan' if x.type == 'income' else 'Pengeluaran'}</span></td><td>{html.escape(x.description)}</td><td>{html.escape(x.category)}</td><td class={'income' if x.type == 'income' else 'expense'}><strong>{format_rupiah(x.amount)}</strong></td><td>{html.escape(x.username or '')}</td></tr>" for x in rows)

def _summary(rows):
    income = sum(x.amount for x in rows if x.type == "income"); expense = sum(x.amount for x in rows if x.type == "expense"); categories = {}; users = {}
    for x in rows:
        if x.type == "expense": categories[x.category] = categories.get(x.category, 0) + x.amount
        users[x.username or x.user_id] = users.get(x.username or x.user_id, 0) + (x.amount if x.type == "expense" else 0)
    return income, expense, categories, users

def _safe_csv_value(value):
    value = "" if value is None else str(value)
    return "'" + value if value[:1] in "=-+@" else value

def _read_request_body(environ):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    return environ["wsgi.input"].read(length)

def _extract_csv_upload(environ):
    raw = _read_request_body(environ)
    content_type = environ.get("CONTENT_TYPE", "")
    if "multipart/form-data" not in content_type:
        return parse_qs(raw.decode("utf-8", "replace")).get("csv", [""])[0]
    boundary = content_type.split("boundary=", 1)[-1].strip().strip('"')
    marker = ("--" + boundary).encode()
    for part in raw.split(marker):
        if b'name="file"' not in part or b"\r\n\r\n" not in part:
            continue
        payload = part.split(b"\r\n\r\n", 1)[1]
        return payload.rsplit(b"\r\n", 1)[0].decode("utf-8-sig", "replace")
    return ""

def _import_csv(db, csv_text, chat_id):
    required = {"tanggal", "tipe", "nominal", "deskripsi", "kategori", "user"}
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames or not required.issubset({x.strip().lower() for x in reader.fieldnames}):
        raise ValueError("Header CSV wajib: tanggal, tipe, nominal, deskripsi, kategori, user")
    inserted = 0
    errors = []
    for line_no, raw in enumerate(reader, start=2):
        row = {str(k).strip().lower(): (v or "").strip() for k, v in raw.items() if k is not None}
        try:
            tx_type = row["tipe"].lower()
            if tx_type in ("pemasukan", "income", "masuk"): tx_type = "income"
            elif tx_type in ("pengeluaran", "expense", "keluar"): tx_type = "expense"
            else: raise ValueError("tipe harus pemasukan/pengeluaran")
            amount = int(row["nominal"].replace(".", "").replace(",", ""))
            if amount <= 0: raise ValueError("nominal harus lebih dari 0")
            tx_date = date.fromisoformat(row["tanggal"])
            username = row["user"] or "import"
            db.add_transaction(Transaction(None, "import", username, chat_id, tx_type, amount, row["deskripsi"], row["kategori"] or "Lain-lain", tx_date, datetime.now()))
            inserted += 1
        except (KeyError, ValueError) as exc:
            errors.append(f"baris {line_no}: {exc}")
    return inserted, errors

def _dashboard_response(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if path.endswith("/static/app.css"):
        with open(os.path.join(os.path.dirname(__file__), "static", "app.css"), "rb") as f: payload = f.read()
        start_response("200 OK", [("Content-Type", "text/css; charset=utf-8"), ("Content-Length", str(len(payload)))])
        return [payload]
    if not _authorized(environ):
        error = ""
        if environ.get("REQUEST_METHOD") == "POST":
            length = int(environ.get("CONTENT_LENGTH") or 0); form = parse_qs(environ["wsgi.input"].read(length).decode()); password = form.get("password", [""])[0]; expected = os.environ.get("WEB_PASSWORD", "")
            if password == expected:
                cookie = hashlib.sha256(expected.encode()).hexdigest(); start_response("303 See Other", [("Location", "/keuangan/dashboard"), ("Set-Cookie", f"ff_session={cookie}; HttpOnly; Secure; SameSite=Lax")]); return [b""]
            error = "Password tidak cocok. Coba lagi."
        status, headers, body = _html_page(TITLE, _auth_page(error)); start_response(status, headers); return body
    settings = load_settings(); db = Database(settings.database_path); db.initialize(); chat_id = next(iter(settings.allowed_chat_ids), "")
    if path.endswith("/import") and environ.get("REQUEST_METHOD") == "POST":
        try:
            inserted, errors = _import_csv(db, _extract_csv_upload(environ), chat_id)
            message = f"Import selesai: {inserted} transaksi ditambahkan."
            if errors: message += " " + " | ".join(errors[:3])
            start_response("303 See Other", [("Location", "/keuangan/dashboard?imported=" + str(inserted))])
            return [b""]
        except ValueError as exc:
            start_response("400 Bad Request", [("Content-Type", "text/plain; charset=utf-8")])
            return [str(exc).encode()]
    query = parse_qs(environ.get("QUERY_STRING", ""))
    try: filters, period = _filters(query, chat_id); error = ""
    except ValueError as exc: filters, period, error = TransactionFilters(chat_id), "month", str(exc)
    rows = db.list_transactions(filters); income, expense, categories, users = _summary(rows)
    if path.endswith("/export.csv"):
        stream = io.StringIO(); writer = csv.writer(stream); writer.writerow(["ID", "Tanggal", "Tipe", "Nominal", "Deskripsi", "Kategori", "User"])
        for x in rows: writer.writerow([x.id, x.transaction_date.isoformat(), x.type, x.amount, _safe_csv_value(x.description), _safe_csv_value(x.category), _safe_csv_value(x.username or "")])
        payload = stream.getvalue().encode("utf-8-sig"); start_response("200 OK", [("Content-Type", "text/csv; charset=utf-8"), ("Content-Disposition", "attachment; filename=finance-family.csv"), ("Content-Length", str(len(payload)))]); return [payload]
    categories_options = "".join(f"<option value='{html.escape(c.name)}' {'selected' if filters.category == c.name else ''}>{html.escape(c.name)}</option>" for c in db.list_categories())
    period_links = "".join(f"<a class={'active' if period == p else ''} href='/keuangan/dashboard?period={p}'>{label}</a>" for p, label in [("week", "Minggu ini"), ("month", "Bulan ini"), ("all", "Semua")])
    filter_form = f"<form class='panel filters' method='get'><input type='hidden' name='period' value='{period}'><div class='field'><label>Tipe</label><select name='type'><option value=''>Semua tipe</option><option value='income' {'selected' if filters.transaction_type == 'income' else ''}>Pemasukan</option><option value='expense' {'selected' if filters.transaction_type == 'expense' else ''}>Pengeluaran</option></select></div><div class='field'><label>Kategori</label><select name='category'><option value=''>Semua kategori</option>{categories_options}</select></div><div class='field'><label>Urutkan</label><select name='sort'><option value='transaction_date'>Tanggal</option><option value='amount'>Nominal</option><option value='description'>Deskripsi</option><option value='category'>Kategori</option></select></div><div class='field'><label>Arah</label><select name='dir'><option value='desc'>Terbaru / besar</option><option value='asc'>Terlama / kecil</option></select></div><div class='field'><label>Cari</label><input name='q' value='{html.escape(filters.search or '')}' placeholder='buah, bensin, suami...'></div><div class='filter-actions'><button type='submit'>Terapkan</button><a class='button ghost' href='/keuangan/dashboard?period={period}'>Reset</a></div></form>"
    cat_html = "".join(f"<div class='summary-row'><span>{html.escape(k)}</span><strong>{format_rupiah(v)}</strong></div>" for k, v in sorted(categories.items(), key=lambda z: -z[1])) or "<div class='empty-state'>Belum ada pengeluaran.</div>"; user_html = "".join(f"<div class='summary-row'><span>{html.escape(k)}</span><strong>{format_rupiah(v)}</strong></div>" for k, v in users.items()) or "<div class='empty-state'>Belum ada data user.</div>"
    query_keep = urlencode({k: v[0] for k, v in query.items() if v and k != "period"}); export_q = f"period={period}&{query_keep}" if query_keep else f"period={period}"
    if path.endswith("/excel"):
        body = f"<main class='page-shell'><header class='topbar'><div><div class='eyebrow'>Finance Family</div><h1 class='title'>Export transaksi</h1><p class='muted'>Download CSV untuk spreadsheet atau cetak halaman ini sebagai PDF.</p></div><div class='actions'><a class='button secondary' href='/keuangan/export.csv?{export_q}'>Download CSV</a><a class='button ghost' href='/keuangan/dashboard?{export_q}'>Kembali</a></div></header><section class='panel'><div class='table-wrap'><table class='data-table'><thead><tr><th>ID</th><th>Tanggal</th><th>Tipe</th><th>Nominal</th><th>Deskripsi</th><th>Kategori</th><th>User</th></tr></thead><tbody>{_rows_html(rows)}</tbody></table></div></section></main>"
    else:
        alert_html = {'<div class="alert">' + html.escape(error) + '</div>' if error else ''}
        body = f"<main class='page-shell'><header class='topbar'><div class='brand-lockup'><div class='brand-mark'>FF</div><div><div class='eyebrow'>Pembukuan keluarga</div><h1 class='title'>Finance Family</h1></div></div><div class='actions'><a class='button secondary' href='/keuangan/export.csv?{export_q}'>Download CSV</a><a class='button ghost' href='#' onclick='window.print();return false'>Cetak / PDF</a></div></header>{alert_html}<nav class='period-tabs'>{period_links}<a href='#custom'>Custom</a></nav>{filter_form}<section class='metric-grid' style='margin-top:18px'><div class='metric-card'><div class='metric-label'>Pemasukan</div><div class='metric-value income'>{format_rupiah(income)}</div></div><div class='metric-card'><div class='metric-label'>Pengeluaran</div><div class='metric-value expense'>{format_rupiah(expense)}</div></div><div class='metric-card'><div class='metric-label'>Saldo bersih</div><div class='metric-value balance'>{format_rupiah(income-expense)}</div></div></section><section class='summary-grid'><div class='panel'><div class='eyebrow'>Per kategori</div><h2>Pengeluaran</h2><div class='summary-list'>{cat_html}</div></div><div class='panel'><div class='eyebrow'>Kontribusi</div><h2>Per user</h2><div class='summary-list'>{user_html}</div></div></section><section class='panel' style='margin-top:18px'><div class='topbar' style='margin-bottom:12px'><div><div class='eyebrow'>Detail transaksi</div><h2 style='margin:3px 0'>Transaksi terpilih · {len(rows)}</h2></div><a class='button secondary' href='/keuangan/excel?{export_q}'>Buka tabel</a></div><div class='table-wrap'><table class='data-table'><thead><tr><th>ID</th><th>Tanggal</th><th>Tipe</th><th>Deskripsi</th><th>Kategori</th><th>Nominal</th><th>User</th></tr></thead><tbody>{_rows_html(rows[-50:])}</tbody></table></div></section><section class='panel' style='margin-top:18px'><div class='eyebrow'>Data</div><h2>Import transaksi CSV</h2><p class='muted'>Kolom: tanggal, tipe, nominal, deskripsi, kategori, user. Data baru ditambahkan tanpa menghapus catatan lama.</p><form class='import-box' method='post' enctype='text/csv' action='/keuangan/import'><input type='file' name='file' accept='.csv,text/csv' required><button type='submit'>Import CSV</button></form></section></main>"
    status, headers, payload = _html_page(TITLE, body); start_response(status, headers); return payload

def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if path.endswith(("/dashboard", "/excel", "/export.csv", "/export", "/export.xlsx", "/import", "/static/app.css")): return _dashboard_response(environ, start_response)
    if environ.get("REQUEST_METHOD") == "GET":
        try: _set_webhook()
        except Exception: pass
        payload = b"family-finance bot is online"; start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(payload)))]); return [payload]
    chat_id = ""
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0); update = json.loads(environ["wsgi.input"].read(length) or b"{}"); message = update.get("message") or {}; chat = message.get("chat") or {}; sender = message.get("from") or {}; text = message.get("text") or ""; settings = load_settings(); chat_id = str(chat.get("id", ""))
        if chat_id in settings.allowed_chat_ids and text and not text.startswith("/"):
            db = Database(settings.database_path); db.initialize(); parsed = parse_message(text, datetime.now(), settings.timezone); category = categorize(parsed.description, db.list_categories()); item = db.add_transaction(Transaction(None, str(sender.get("id", "")), sender.get("username") or sender.get("first_name") or "user", chat_id, parsed.type, parsed.amount, parsed.description, category.name, parsed.transaction_date, datetime.now())); _send_message(chat_id, render_confirmation(item, sender.get("username") or sender.get("first_name") or "user"))
        elif chat_id in settings.allowed_chat_ids and text.startswith("/start"): _send_message(chat_id, "👋 Halo! Kirim contoh seperti: bensin 50rb atau gaji masuk 8jt")
        start_response("200 OK", [("Content-Type", "application/json")]); return [b'{"ok":true}']
    except ParseError as exc:
        if chat_id: _send_message(chat_id, f"❓ {exc}")
        start_response("200 OK", [("Content-Type", "application/json")]); return [b'{"ok":true}']
    except Exception:
        start_response("500 Internal Server Error", [("Content-Type", "text/plain")]); return [b"internal error"]
