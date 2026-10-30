"""Passenger WSGI entrypoint for Telegram webhook and family finance dashboard.

Sistem Manajemen Keuangan Personal & Pembukuan Keluarga Terpadu.
"""
import csv
import hashlib
import html
import io
import json
import os
from datetime import date, datetime, timedelta
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlencode
from urllib.request import Request, urlopen

from src.categorizer import categorize
from src.config import load_settings
from src.database import Database
from src.formatting import format_rupiah, render_confirmation
from src.models import Transaction, TransactionFilters
from src.parser import ParseError, parse_message

TITLE = "Finance Family — Sistem Manajemen Keuangan Keluarga"

BULAN_ID = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def _format_date_id(d: date) -> str:
    if not d:
        return "-"
    return f"{d.day:02d} {BULAN_ID[d.month]} {d.year}"


def _monogram(name: str) -> str:
    clean = "".join(ch for ch in (name or "U") if ch.isalnum() or ch.isspace()).strip()
    parts = clean.split()
    if len(parts) >= 2:
        return (parts[0][:1] + parts[1][:1]).upper()
    return clean[:2].upper() if clean else "FF"


def _svg_icon(name: str) -> str:
    icons = {
        "wallet": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2a1 1 0 0 0-1-1"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/></svg>',
        "trending-up": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>',
        "trending-down": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/></svg>',
        "scale": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/></svg>',
        "percent": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="19" x2="5" y1="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/></svg>',
        "plus": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/><path d="M12 5v14"/></svg>',
        "download": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>',
        "upload": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>',
        "printer": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect width="12" height="8" x="6" y="14"/></svg>',
        "filter": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>',
        "refresh": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>',
        "search": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>',
        "trash": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>',
        "logout": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/></svg>',
        "table": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/></svg>',
        "check": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
        "file-text": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><line x1="10" x2="8" y1="9" y2="9"/></svg>',
    }
    return icons.get(name, "")


def _send_message(chat_id, text):
    token = os.environ.get("BOT_TOKEN")
    if not token or not chat_id:
        return
    body = urlencode({"chat_id": chat_id, "text": text}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    try:
        with urlopen(req, timeout=20):
            pass
    except Exception:
        pass


def _set_webhook():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return
    body = urlencode({"url": "https://asistenq.com/keuangan/"}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/setWebhook", data=body, method="POST")
    try:
        with urlopen(req, timeout=20):
            pass
    except Exception:
        pass


def _authorized(environ):
    password = os.environ.get("WEB_PASSWORD")
    if not password:
        return False
    cookie = SimpleCookie(environ.get("HTTP_COOKIE", ""))
    expected = hashlib.sha256(password.encode()).hexdigest()
    return bool(cookie.get("ff_session") and cookie["ff_session"].value == expected)


def _html_page(title, body, status="200 OK", headers=None):
    markup = f"""<!doctype html>
<html lang="id">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <meta name="description" content="Sistem Informasi & Manajemen Keuangan Keluarga Terpadu">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/keuangan/static/app.css">
</head>
<body>
  {body}
  <script src="/keuangan/static/chart.umd.min.js"></script>
</body>
</html>"""
    payload = markup.encode("utf-8")
    resp_headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(payload))),
    ] + (headers or [])
    return status, resp_headers, [payload]


def _auth_page(error=""):
    alert = f'<div class="toast toast-error" style="margin-bottom: 20px;"><div class="toast-title">Akses Ditolak</div><div class="toast-msg">{html.escape(error)}</div></div>' if error else ""
    return f"""<main class="auth-page">
  <div class="auth-wrapper">
    <section class="auth-hero">
      <div>
        <div class="brand-lockup">
          <div class="brand-mark">FF</div>
          <div class="brand-info">
            <span class="brand-badge" style="color: #93c5fd;"><span class="status-dot"></span>Sistem Terenkripsi</span>
            <span class="brand-title" style="color: #ffffff;">Finance Family</span>
          </div>
        </div>
        <h1 class="auth-hero-title">Tata Kelola Finansial Rumah Tangga yang Akuntabel & Presisi.</h1>
        <p class="auth-hero-desc">Pencatatan mutasi harian secara instan via Telegram, dilengkapi dasbor analisis visual, pemisahan pos anggaran, dan laporan terpadu.</p>
        <div class="auth-features-list">
          <div class="auth-feature-item"><span class="auth-feature-check">✓</span><span>Pencatatan multi-pengguna dengan integrasi bot Telegram</span></div>
          <div class="auth-feature-item"><span class="auth-feature-check">✓</span><span>Alokasi pengeluaran per kategori & kontribusi anggota</span></div>
          <div class="auth-feature-item"><span class="auth-feature-check">✓</span><span>Laporan arus kas berkala, ekspor CSV & berkas cetak PDF</span></div>
        </div>
      </div>
      <div style="font-size: 12px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 16px;">
        Finance Family Private Infrastructure · Keamanan & Privasi Terjamin
      </div>
    </section>
    <section class="auth-form-card">
      <div class="auth-badge">Portal Otorisasi Sistem</div>
      <h2 class="auth-form-title">Selamat Datang</h2>
      <p class="auth-form-subtitle">Silakan masukkan kata sandi keamanan untuk mengakses dasbor keuangan keluarga.</p>
      {alert}
      <form class="auth-form" method="post">
        <div class="form-group">
          <label for="password">Kata Sandi Akses</label>
          <input class="form-control" id="password" name="password" type="password" autocomplete="current-password" placeholder="••••••••••••" autofocus required>
        </div>
        <button class="btn btn-primary" type="submit" style="padding: 12px; font-size: 14px; margin-top: 8px;">
          Masuk ke Sistem Dasbor
        </button>
      </form>
    </section>
  </div>
</main>"""


def _period_bounds(query):
    today = date.today()
    period = query.get("period", ["month"])[0]
    if period == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    elif period == "year":
        start = today.replace(month=1, day=1)
        end = today.replace(month=12, day=31)
    elif period == "all":
        start = end = None
    elif period == "custom":
        try:
            start = date.fromisoformat(query.get("start", [today.isoformat()])[0])
            end = date.fromisoformat(query.get("end", [today.isoformat()])[0])
        except ValueError:
            raise ValueError("Tanggal custom tidak valid.")
    else:
        start = today.replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        period = "month"
    if start and end and start > end:
        raise ValueError("Tanggal mulai tidak boleh melewati tanggal akhir.")
    return start, end, period


def _filters(query, chat_id):
    start, end, period = _period_bounds(query)
    tx_type = query.get("type", [""])[0] or None
    category = query.get("category", [""])[0] or None
    search = query.get("q", [""])[0].strip() or None
    user_id = query.get("user", [""])[0].strip() or None
    sort_by = query.get("sort", ["transaction_date"])[0]
    sort_dir = query.get("dir", ["desc"])[0]
    return TransactionFilters(chat_id, start, end, user_id, tx_type, category, search, sort_by, sort_dir), period


def _safe_csv_value(value):
    value = "" if value is None else str(value)
    return "'" + value if value[:1] in "=-+@" else value


def _summary(rows):
    income = sum(x.amount for x in rows if x.type == "income")
    expense = sum(x.amount for x in rows if x.type == "expense")
    categories = {}
    users = {}
    cat_counts = {}
    user_counts = {}
    for x in rows:
        uname = (x.username or x.user_id or "user").strip()
        if x.type == "expense":
            categories[x.category] = categories.get(x.category, 0) + x.amount
            cat_counts[x.category] = cat_counts.get(x.category, 0) + 1
            users[uname] = users.get(uname, 0) + x.amount
            user_counts[uname] = user_counts.get(uname, 0) + 1
        elif x.type == "income":
            if uname not in users:
                users[uname] = 0
            user_counts[uname] = user_counts.get(uname, 0) + 1
    return income, expense, categories, users, cat_counts, user_counts


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
        raise ValueError("Header CSV wajib memuat: tanggal, tipe, nominal, deskripsi, kategori, user")
    inserted = 0
    errors = []
    for line_no, raw in enumerate(reader, start=2):
        row = {str(k).strip().lower(): (v or "").strip() for k, v in raw.items() if k is not None}
        try:
            tx_type = row["tipe"].lower()
            if tx_type in ("pemasukan", "income", "masuk"):
                tx_type = "income"
            elif tx_type in ("pengeluaran", "expense", "keluar"):
                tx_type = "expense"
            else:
                raise ValueError("tipe harus 'pemasukan' atau 'pengeluaran'")
            amount = int(row["nominal"].replace(".", "").replace(",", "").replace("Rp", "").strip())
            if amount <= 0:
                raise ValueError("nominal harus lebih besar dari 0")
            tx_date = date.fromisoformat(row["tanggal"])
            username = row["user"] or "impor"
            db.add_transaction(
                Transaction(
                    None,
                    "import",
                    username,
                    chat_id,
                    tx_type,
                    amount,
                    row["deskripsi"] or "Impor CSV",
                    row["kategori"] or "Lain-lain",
                    tx_date,
                    datetime.now(),
                )
            )
            inserted += 1
        except (KeyError, ValueError) as exc:
            errors.append(f"baris {line_no}: {exc}")
    return inserted, errors


def _rows_html(rows, active_chat_id=""):
    if not rows:
        return """<tr>
          <td colspan="8">
            <div class="empty-state-box">
              <div class="empty-state-icon">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M9 21V9"/></svg>
              </div>
              <div class="empty-state-title">Belum Ada Catatan Transaksi</div>
              <div class="empty-state-desc">Tidak terdapat data mutasi keuangan yang sesuai dengan parameter filter atau rentang tanggal yang dipilih.</div>
              <button class="btn btn-primary btn-sm" type="button" onclick="openAddModal()">
                + Catat Transaksi Baru
              </button>
            </div>
          </td>
        </tr>"""

    output = []
    for x in rows:
        is_inc = x.type == "income"
        type_badge = f'<span class="badge-type {"income" if is_inc else "expense"}">{"Pemasukan" if is_inc else "Pengeluaran"}</span>'
        sign = "+" if is_inc else "-"
        amt_class = "income" if is_inc else "expense"
        user_name = html.escape(x.username or x.user_id or "User")
        user_initials = _monogram(user_name)
        desc_escaped = html.escape(x.description)
        cat_escaped = html.escape(x.category)

        output.append(f"""<tr class="tx-row" data-id="{x.id}">
          <td class="tabular-nums" style="color: var(--ink-muted); font-size: 12px; font-weight: 600;">#{x.id}</td>
          <td class="tabular-nums" style="white-space: nowrap; font-weight: 500;">{_format_date_id(x.transaction_date)}</td>
          <td>{type_badge}</td>
          <td><span class="category-chip">{cat_escaped}</span></td>
          <td style="font-weight: 600; color: var(--ink-primary); max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{desc_escaped}">{desc_escaped}</td>
          <td class="tabular-nums"><span class="tx-amount {amt_class}">{sign} {format_rupiah(x.amount)}</span></td>
          <td>
            <div class="tx-user-cell">
              <div class="user-avatar">{user_initials}</div>
              <span style="font-weight: 500; font-size: 13px;">{user_name}</span>
            </div>
          </td>
          <td class="action-cell">
            <button class="btn btn-ghost btn-sm" type="button" title="Hapus transaksi ini" onclick="confirmDelete({x.id}, '{desc_escaped.replace("'", "\\'")}', '{format_rupiah(x.amount)}')">
              {_svg_icon("trash")}
            </button>
          </td>
        </tr>""")
    return "".join(output)


def _dashboard_response(environ, start_response):
    path = environ.get("PATH_INFO", "")

    # Static CSS
    if path.endswith("/static/app.css"):
        css_path = os.path.join(os.path.dirname(__file__), "static", "app.css")
        with open(css_path, "rb") as f:
            payload = f.read()
        start_response("200 OK", [("Content-Type", "text/css; charset=utf-8"), ("Content-Length", str(len(payload)))])
        return [payload]

    # Static Chart.js
    if path.endswith("/static/chart.umd.min.js"):
        chart_path = os.path.join(os.path.dirname(__file__), "static", "chart.umd.min.js")
        if os.path.exists(chart_path):
            with open(chart_path, "rb") as f:
                payload = f.read()
            start_response("200 OK", [("Content-Type", "application/javascript; charset=utf-8"), ("Content-Length", str(len(payload)))])
            return [payload]

    # Logout Action
    if path.endswith("/logout"):
        start_response(
            "303 See Other",
            [
                ("Location", "/keuangan/dashboard"),
                ("Set-Cookie", "ff_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; SameSite=Lax"),
            ],
        )
        return [b""]

    # Authentication Handling
    if not _authorized(environ):
        error = ""
        if environ.get("REQUEST_METHOD") == "POST":
            length = int(environ.get("CONTENT_LENGTH") or 0)
            form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
            password = form.get("password", [""])[0]
            expected = os.environ.get("WEB_PASSWORD", "")
            if password and password == expected:
                cookie = hashlib.sha256(expected.encode()).hexdigest()
                is_https = environ.get("wsgi.url_scheme") == "https" or environ.get("HTTP_X_FORWARDED_PROTO") == "https"
                sec_flag = " Secure;" if is_https else ""
                start_response(
                    "303 See Other",
                    [
                        ("Location", "/keuangan/dashboard"),
                        ("Set-Cookie", f"ff_session={cookie}; Path=/; HttpOnly;{sec_flag} SameSite=Lax"),
                    ],
                )
                return [b""]
            error = "Kata sandi otorisasi tidak valid. Silakan coba kembali."
        status, headers, body = _html_page(TITLE, _auth_page(error))
        start_response(status, headers)
        return body

    # Authorized Session - Initialize Resources
    settings = load_settings()
    db = Database(settings.database_path)
    db.initialize()
    chat_id = next(iter(settings.allowed_chat_ids), "default")

    # CSV Template Download
    if path.endswith("/template.csv"):
        template_csv = (
            "tanggal,tipe,nominal,deskripsi,kategori,user\r\n"
            f"{date.today().isoformat()},pengeluaran,50000,Bensin Kendaraan,Transportasi,Ayah\r\n"
            f"{date.today().isoformat()},pengeluaran,125000,Belanja Bahan Makanan Pokok,Makanan & Minuman,Ibu\r\n"
            f"{date.today().isoformat()},pemasukan,10000000,Gaji Bulanan,Pemasukan,Ayah\r\n"
        ).encode("utf-8-sig")
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/csv; charset=utf-8"),
                ("Content-Disposition", 'attachment; filename="template_transaksi_finance_family.csv"'),
                ("Content-Length", str(len(template_csv))),
            ],
        )
        return [template_csv]

    # Create Transaction Manually via Web
    if path.endswith("/transaction/create") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        tx_type = form.get("type", ["expense"])[0].lower()
        if tx_type not in ("income", "expense"):
            tx_type = "expense"
        amt_str = form.get("amount", ["0"])[0].replace(".", "").replace(",", "").replace("Rp", "").strip()
        amount = int(amt_str) if amt_str.isdigit() else 0
        desc = form.get("description", [""])[0].strip() or "Transaksi Manual"
        cat = form.get("category", ["Lain-lain"])[0].strip() or "Lain-lain"
        dt_str = form.get("transaction_date", [""])[0].strip()
        try:
            tx_date = date.fromisoformat(dt_str) if dt_str else date.today()
        except ValueError:
            tx_date = date.today()
        user_name = form.get("username", [""])[0].strip() or "Admin"
        ret_period = form.get("period", ["month"])[0]

        if amount > 0:
            db.add_transaction(
                Transaction(
                    id=None,
                    user_id="web",
                    username=user_name,
                    chat_id=chat_id,
                    type=tx_type,
                    amount=amount,
                    description=desc,
                    category=cat,
                    transaction_date=tx_date,
                    created_at=datetime.now(),
                )
            )
            start_response("303 See Other", [("Location", f"/keuangan/dashboard?period={ret_period}&toast=created")])
            return [b""]
        else:
            start_response("303 See Other", [("Location", f"/keuangan/dashboard?period={ret_period}&toast=err_amount")])
            return [b""]

    # Delete Transaction via Web
    if path.endswith("/transaction/delete") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        tx_id_str = form.get("id", ["0"])[0].strip()
        ret_period = form.get("period", ["month"])[0]
        if tx_id_str.isdigit():
            db.delete_transaction_web(int(tx_id_str), chat_id)
            start_response("303 See Other", [("Location", f"/keuangan/dashboard?period={ret_period}&toast=deleted")])
            return [b""]

    # Import CSV
    if path.endswith("/import") and environ.get("REQUEST_METHOD") == "POST":
        try:
            inserted, errors = _import_csv(db, _extract_csv_upload(environ), chat_id)
            redirect_url = f"/keuangan/dashboard?imported={inserted}&toast=imported"
            if errors:
                redirect_url += f"&import_err={len(errors)}"
            start_response("303 See Other", [("Location", redirect_url)])
            return [b""]
        except ValueError as exc:
            start_response("400 Bad Request", [("Content-Type", "text/plain; charset=utf-8")])
            return [str(exc).encode("utf-8")]

    # Parse Filters & Queries
    query = parse_qs(environ.get("QUERY_STRING", ""))
    error = ""
    try:
        filters, period = _filters(query, chat_id)
    except ValueError as exc:
        filters, period, error = TransactionFilters(chat_id), "month", str(exc)

    rows = db.list_transactions(filters)
    income, expense, categories, users, cat_counts, user_counts = _summary(rows)
    balance = income - expense
    savings_rate = round(((income - expense) / income) * 100, 1) if income > 0 else (0.0 if expense > 0 else 100.0)

    # Export CSV
    if path.endswith("/export.csv"):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["ID Transaksi", "Tanggal", "Jenis Transaksi", "Nominal (IDR)", "Deskripsi", "Kategori", "Pencatat"])
        for x in rows:
            type_label = "Pemasukan" if x.type == "income" else "Pengeluaran"
            writer.writerow([
                x.id,
                x.transaction_date.isoformat(),
                type_label,
                x.amount,
                _safe_csv_value(x.description),
                _safe_csv_value(x.category),
                _safe_csv_value(x.username or x.user_id or ""),
            ])
        payload = stream.getvalue().encode("utf-8-sig")
        start_response(
            "200 OK",
            [
                ("Content-Type", "text/csv; charset=utf-8"),
                ("Content-Disposition", f'attachment; filename="laporan_keuangan_family_{period}_{date.today().isoformat()}.csv"'),
                ("Content-Length", str(len(payload))),
            ],
        )
        return [payload]

    # Base URL query builder
    clean_params = {k: v[0] for k, v in query.items() if v and k not in ("toast", "imported", "import_err")}
    export_q = urlencode(clean_params)

    # Toast Notifications Detection
    toast_type = query.get("toast", [""])[0]
    toast_html = ""
    if toast_type == "created":
        toast_html = f"""<div class="toast toast-success" id="main-toast">
          <div style="color: var(--income-main);">{_svg_icon("check")}</div>
          <div style="flex: 1;">
            <div class="toast-title">Transaksi Berhasil Dicatat</div>
            <div class="toast-msg">Data transaksi baru telah tersimpan ke dalam pembukuan keluarga.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "deleted":
        toast_html = f"""<div class="toast toast-success" id="main-toast">
          <div style="color: var(--income-main);">{_svg_icon("check")}</div>
          <div style="flex: 1;">
            <div class="toast-title">Transaksi Berhasil Dihapus</div>
            <div class="toast-msg">Catatan transaksi telah dihapus dari sistem pembukuan.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "imported":
        cnt = query.get("imported", ["0"])[0]
        toast_html = f"""<div class="toast toast-success" id="main-toast">
          <div style="color: var(--income-main);">{_svg_icon("check")}</div>
          <div style="flex: 1;">
            <div class="toast-title">Impor Data CSV Selesai</div>
            <div class="toast-msg">Sebanyak {cnt} data transaksi berhasil diimpor ke sistem.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "err_amount":
        toast_html = f"""<div class="toast toast-error" id="main-toast">
          <div style="flex: 1;">
            <div class="toast-title">Gagal Menyimpan Transaksi</div>
            <div class="toast-msg">Nominal transaksi harus lebih besar dari Rp 0.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""

    # Fullscreen Table View (Excel/Audit view)
    if path.endswith(("/excel", "/fullscreen")):
        body = f"""<main class="page-shell">
  <header class="topbar">
    <div class="brand-lockup">
      <div class="brand-mark">FF</div>
      <div class="brand-info">
        <span class="brand-badge"><span class="status-dot"></span>Buku Besar Lengkap</span>
        <h1 class="brand-title">Daftar Audit Transaksi Keuangan</h1>
        <span class="brand-desc">Total {len(rows)} mutasi catatan transaksi terverifikasi</span>
      </div>
    </div>
    <div class="actions">
      <a class="btn btn-primary" href="/keuangan/export.csv?{export_q}">{_svg_icon("download")} Unduh CSV</a>
      <button class="btn btn-secondary" onclick="window.print()">{_svg_icon("printer")} Cetak Laporan</button>
      <a class="btn btn-ghost" href="/keuangan/dashboard?{export_q}">Kembali ke Dasbor</a>
    </div>
  </header>
  <section class="panel ledger-panel">
    <div class="table-responsive">
      <table class="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Tanggal</th>
            <th>Jenis Transaksi</th>
            <th>Kategori</th>
            <th>Deskripsi Transaksi</th>
            <th>Nominal</th>
            <th>Pencatat</th>
            <th>Aksi</th>
          </tr>
        </thead>
        <tbody>{_rows_html(rows, chat_id)}</tbody>
      </table>
    </div>
  </section>
</main>"""
        status, headers, payload = _html_page("Daftar Lengkap Transaksi — Finance Family", body)
        start_response(status, headers)
        return payload

    # Build Categories Dropdown Options
    all_categories = db.list_categories()
    categories_options = "".join(
        f"<option value='{html.escape(c.name)}' {'selected' if filters.category == c.name else ''}>{c.emoji} {html.escape(c.name)}</option>"
        for c in all_categories
    )

    # Build Period Tab Links
    period_defs = [
        ("week", "Pekan Ini"),
        ("month", "Bulan Ini"),
        ("year", "Tahun Ini"),
        ("all", "Semua Periode"),
    ]
    period_tabs_html = "".join(
        f"<a class='period-tab {'active' if period == p else ''}' href='/keuangan/dashboard?period={p}'>{label}</a>"
        for p, label in period_defs
    )
    custom_active = "active" if period == "custom" else ""
    period_tabs_html += f"<a class='period-tab {custom_active}' href='javascript:void(0)' onclick='toggleCustomDate()'>Rentang Kustom</a>"

    # Custom Date Range Form (Inline Collapsible)
    start_val = filters.start.isoformat() if filters.start else date.today().replace(day=1).isoformat()
    end_val = filters.end.isoformat() if filters.end else date.today().isoformat()
    custom_display = "flex" if period == "custom" else "none"
    custom_date_form = f"""<form id="custom-date-panel" class="custom-date-box" method="get" style="display:{custom_display};">
      <input type="hidden" name="period" value="custom">
      <label style="font-weight:600; color:var(--ink-secondary);">Mulai:</label>
      <input type="date" name="start" value="{start_val}" required>
      <label style="font-weight:600; color:var(--ink-secondary);">Sampai:</label>
      <input type="date" name="end" value="{end_val}" required>
      <button class="btn btn-primary btn-sm" type="submit">Terapkan Rentang</button>
    </form>"""

    # Category Breakdown List HTML
    if categories and expense > 0:
        sorted_cats = sorted(categories.items(), key=lambda z: -z[1])
        cat_items = []
        for cat_name, cat_amt in sorted_cats:
            cat_pct = round((cat_amt / expense) * 100, 1)
            cat_count = cat_counts.get(cat_name, 0)
            c_emoji = next((c.emoji for c in all_categories if c.name == cat_name), "📁")
            cat_items.append(f"""<div class="breakdown-item">
              <div class="breakdown-header">
                <div class="breakdown-title-info">
                  <div class="category-emoji">{c_emoji}</div>
                  <div>
                    <div class="breakdown-name">{html.escape(cat_name)}</div>
                    <div class="breakdown-count">{cat_count} catatan</div>
                  </div>
                </div>
                <div class="breakdown-figures">
                  <div class="breakdown-amount">{format_rupiah(cat_amt)}</div>
                  <div class="breakdown-pct">{cat_pct}%</div>
                </div>
              </div>
              <div class="progress-track">
                <div class="progress-fill fill-expense" style="width: {cat_pct}%;"></div>
              </div>
            </div>""")
        cat_html = "".join(cat_items)
    else:
        cat_html = """<div class="empty-state-box" style="padding: 32px 16px;">
          <div class="empty-state-title" style="font-size: 14px;">Belum Ada Pengeluaran</div>
          <div class="empty-state-desc">Belum terdapat catatan transaksi pengeluaran pada rentang waktu ini.</div>
        </div>"""

    # User Contribution List HTML
    if users and expense > 0:
        sorted_users = sorted(users.items(), key=lambda z: -z[1])
        user_items = []
        for uname, u_amt in sorted_users:
            u_pct = round((u_amt / expense) * 100, 1)
            u_count = user_counts.get(uname, 0)
            u_init = _monogram(uname)
            user_items.append(f"""<div class="breakdown-item">
              <div class="breakdown-header">
                <div class="breakdown-title-info">
                  <div class="user-avatar">{u_init}</div>
                  <div>
                    <div class="breakdown-name">{html.escape(uname)}</div>
                    <div class="breakdown-count">{u_count} aktivitas</div>
                  </div>
                </div>
                <div class="breakdown-figures">
                  <div class="breakdown-amount">{format_rupiah(u_amt)}</div>
                  <div class="breakdown-pct">{u_pct}%</div>
                </div>
              </div>
              <div class="progress-track">
                <div class="progress-fill fill-user" style="width: {u_pct}%;"></div>
              </div>
            </div>""")
        user_html = "".join(user_items)
    else:
        user_html = """<div class="empty-state-box" style="padding: 32px 16px;">
          <div class="empty-state-title" style="font-size: 14px;">Belum Ada Data Pengguna</div>
          <div class="empty-state-desc">Belum terdapat aktivitas pencatatan anggota keluarga pada periode ini.</div>
        </div>"""

    # Balance Badge Logic
    if balance > 0:
        balance_tag = '<span class="metric-tag tag-income">Surplus Finansial</span>'
        balance_class = "val-income"
    elif balance < 0:
        balance_tag = '<span class="metric-tag tag-expense">Defisit Anggaran</span>'
        balance_class = "val-expense"
    else:
        balance_tag = '<span class="metric-tag tag-neutral">Seimbang (Nol)</span>'
        balance_class = "val-balance"

    # Filter Form HTML
    filter_form_html = f"""<section class="panel filter-card">
  <form class="filters-form" method="get">
    <input type="hidden" name="period" value="{period}">
    {f'<input type="hidden" name="start" value="{filters.start.isoformat()}">' if filters.start and period == "custom" else ''}
    {f'<input type="hidden" name="end" value="{filters.end.isoformat()}">' if filters.end and period == "custom" else ''}
    
    <div class="form-group">
      <label for="f-type">Jenis Transaksi</label>
      <select class="form-control" id="f-type" name="type">
        <option value="">Semua Jenis</option>
        <option value="income" {'selected' if filters.transaction_type == 'income' else ''}>Pemasukan (Masuk)</option>
        <option value="expense" {'selected' if filters.transaction_type == 'expense' else ''}>Pengeluaran (Keluar)</option>
      </select>
    </div>

    <div class="form-group">
      <label for="f-cat">Kategori</label>
      <select class="form-control" id="f-cat" name="category">
        <option value="">Semua Kategori</option>
        {categories_options}
      </select>
    </div>

    <div class="form-group">
      <label for="f-sort">Urutkan Berdasarkan</label>
      <select class="form-control" id="f-sort" name="sort">
        <option value="transaction_date" {'selected' if filters.sort_by == 'transaction_date' else ''}>Tanggal Transaksi</option>
        <option value="amount" {'selected' if filters.sort_by == 'amount' else ''}>Nominal (IDR)</option>
        <option value="description" {'selected' if filters.sort_by == 'description' else ''}>Deskripsi</option>
        <option value="category" {'selected' if filters.sort_by == 'category' else ''}>Kategori</option>
      </select>
    </div>

    <div class="form-group">
      <label for="f-dir">Tata Urutan</label>
      <select class="form-control" id="f-dir" name="dir">
        <option value="desc" {'selected' if filters.sort_dir == 'desc' else ''}>Terbaru / Terbesar</option>
        <option value="asc" {'selected' if filters.sort_dir == 'asc' else ''}>Terlama / Terkecil</option>
      </select>
    </div>

    <div class="form-group">
      <label for="f-q">Pencarian Kata Kunci</label>
      <input class="form-control" id="f-q" name="q" value="{html.escape(filters.search or '')}" placeholder="Cari deskripsi, kategori, nama...">
    </div>

    <div class="filter-btn-group">
      <button class="btn btn-primary" type="submit">
        {_svg_icon("filter")} Terapkan
      </button>
      <a class="btn btn-secondary" href="/keuangan/dashboard?period={period}" title="Atur Ulang Filter">
        {_svg_icon("refresh")}
      </a>
    </div>
  </form>
</section>"""

    # Prepare Data for Chart.js
    chart_cat_labels = list(categories.keys())
    chart_cat_data = list(categories.values())
    chart_json_data = json.dumps({
        "income": income,
        "expense": expense,
        "balance": max(0, balance),
        "catLabels": chart_cat_labels,
        "catData": chart_cat_data,
        "hasData": bool(income > 0 or expense > 0)
    })

    # Main Dashboard Body
    body = f"""<div class="toast-container">{toast_html}</div>

<main class="page-shell">
  <!-- Top Navigation Bar -->
  <header class="topbar">
    <div class="brand-lockup">
      <div class="brand-mark">FF</div>
      <div class="brand-info">
        <span class="brand-badge"><span class="status-dot"></span>Sistem Manajemen Aktif</span>
        <h1 class="brand-title">Finance Family</h1>
        <span class="brand-desc">Sistem Manajemen & Pembukuan Finansial Keluarga Terpadu</span>
      </div>
    </div>
    <div class="actions">
      <button class="btn btn-primary" type="button" onclick="openAddModal()">
        {_svg_icon("plus")} Catat Transaksi
      </button>
      <button class="btn btn-secondary" type="button" onclick="openImportModal()">
        {_svg_icon("upload")} Impor CSV
      </button>
      <a class="btn btn-secondary" href="/keuangan/export.csv?{export_q}">
        {_svg_icon("download")} Ekspor CSV
      </a>
      <button class="btn btn-ghost" type="button" onclick="window.print()">
        {_svg_icon("printer")} Cetak
      </button>
      <a class="btn btn-ghost" href="/keuangan/logout" title="Keluar dari sesi ini" onclick="return confirm('Keluar dari sesi dasbor keuangan?')">
        {_svg_icon("logout")}
      </a>
    </div>
  </header>

  <!-- Period Tabs & Custom Date Selector -->
  <div class="period-nav-wrapper">
    <nav class="period-tabs">
      {period_tabs_html}
    </nav>
    {custom_date_form}
  </div>

  <!-- Advanced Filters Panel -->
  {filter_form_html}

  <!-- Executive Financial KPI Metric Cards -->
  <section class="metric-grid">
    <!-- Card 1: Pemasukan -->
    <div class="metric-card card-income">
      <div class="metric-header">
        <div class="metric-meta">
          <span class="metric-label">Total Pemasukan</span>
        </div>
        <div class="metric-icon-wrap">
          {_svg_icon("trending-up")}
        </div>
      </div>
      <div class="metric-value val-income">{format_rupiah(income)}</div>
      <div class="metric-footer">
        <span class="metric-tag tag-income">+ Kas Masuk</span>
        <span class="tabular-nums">{sum(1 for x in rows if x.type == "income")} transaksi</span>
      </div>
    </div>

    <!-- Card 2: Pengeluaran -->
    <div class="metric-card card-expense">
      <div class="metric-header">
        <div class="metric-meta">
          <span class="metric-label">Total Pengeluaran</span>
        </div>
        <div class="metric-icon-wrap">
          {_svg_icon("trending-down")}
        </div>
      </div>
      <div class="metric-value val-expense">{format_rupiah(expense)}</div>
      <div class="metric-footer">
        <span class="metric-tag tag-expense">- Beban Kas</span>
        <span class="tabular-nums">{sum(1 for x in rows if x.type == "expense")} transaksi</span>
      </div>
    </div>

    <!-- Card 3: Saldo Bersih -->
    <div class="metric-card card-balance">
      <div class="metric-header">
        <div class="metric-meta">
          <span class="metric-label">Arus Kas Bersih (Net)</span>
        </div>
        <div class="metric-icon-wrap">
          {_svg_icon("scale")}
        </div>
      </div>
      <div class="metric-value {balance_class}">{format_rupiah(balance)}</div>
      <div class="metric-footer">
        {balance_tag}
        <span>Selisih Masuk - Keluar</span>
      </div>
    </div>

    <!-- Card 4: Rasio Tabungan -->
    <div class="metric-card card-stats">
      <div class="metric-header">
        <div class="metric-meta">
          <span class="metric-label">Rasio Retensi Tabungan</span>
        </div>
        <div class="metric-icon-wrap">
          {_svg_icon("percent")}
        </div>
      </div>
      <div class="metric-value val-stats">{savings_rate}%</div>
      <div class="metric-footer">
        <span class="metric-tag tag-neutral">Total {len(rows)} Catatan</span>
        <span>Efisiensi Arus Kas</span>
      </div>
    </div>
  </section>

  <!-- Interactive Charts Section -->
  <section class="charts-grid">
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-group">
          <h3>Komparasi Arus Kas Finansial</h3>
          <div class="panel-subtitle">Perbandingan proporsional antara pemasukan, pengeluaran, dan sisa saldo</div>
        </div>
      </div>
      <div class="chart-box">
        <canvas id="cashflowBarChart"></canvas>
      </div>
    </div>

    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-group">
          <h3>Distribusi Pos Belanja</h3>
          <div class="panel-subtitle">Komposisi pengeluaran keluarga berdasarkan pos kategori</div>
        </div>
      </div>
      <div class="chart-box">
        <canvas id="categoryDonutChart"></canvas>
      </div>
    </div>
  </section>

  <!-- Detailed Categorical & User Breakdown Panels -->
  <section class="breakdown-grid">
    <!-- Category Breakdown Panel -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-group">
          <h3>Alokasi Pengeluaran per Kategori</h3>
          <div class="panel-subtitle">Urutan pos pengeluaran dari nominal terbesar</div>
        </div>
      </div>
      <div class="breakdown-list">
        {cat_html}
      </div>
    </div>

    <!-- User Contribution Panel -->
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title-group">
          <h3>Rekapitulasi Anggota Keluarga</h3>
          <div class="panel-subtitle">Distribusi belanja dan pencatatan per anggota</div>
        </div>
      </div>
      <div class="breakdown-list">
        {user_html}
      </div>
    </div>
  </section>

  <!-- Transaction Data Ledger Panel -->
  <section class="panel ledger-panel">
    <div class="panel-header">
      <div class="panel-title-group">
        <h3>Buku Besar Mutasi Transaksi</h3>
        <div class="panel-subtitle">Menampilkan {len(rows)} mutasi catatan transaksi terverifikasi</div>
      </div>
      <div class="ledger-toolbar">
        <div class="ledger-search-box">
          <span class="search-icon">{_svg_icon("search")}</span>
          <input class="form-control" type="text" id="tableQuickSearch" placeholder="Pencarian cepat di tabel..." onkeyup="filterTableLive()">
        </div>
        <a class="btn btn-secondary btn-sm" href="/keuangan/excel?{export_q}">
          {_svg_icon("table")} Tampilan Penuh
        </a>
      </div>
    </div>

    <div class="table-responsive">
      <table class="data-table" id="transactionTable">
        <thead>
          <tr>
            <th style="width: 70px;">ID</th>
            <th style="width: 120px;">Tanggal</th>
            <th style="width: 130px;">Jenis</th>
            <th style="width: 150px;">Kategori</th>
            <th>Deskripsi Transaksi</th>
            <th style="width: 160px;">Nominal (IDR)</th>
            <th style="width: 150px;">Pencatat</th>
            <th style="width: 60px; text-align: center;">Aksi</th>
          </tr>
        </thead>
        <tbody>
          {_rows_html(rows, chat_id)}
        </tbody>
      </table>
    </div>
  </section>
</main>

<!-- Modal: Tambah Transaksi Manual -->
<div class="modal-overlay" id="modal-add-tx">
  <div class="modal-dialog">
    <div class="modal-header">
      <h3>Catat Transaksi Finansial Baru</h3>
      <button class="modal-close-btn" type="button" onclick="closeModal('modal-add-tx')">&times;</button>
    </div>
    <form method="post" action="/keuangan/transaction/create">
      <input type="hidden" name="period" value="{period}">
      <input type="hidden" id="modal-tx-type" name="type" value="expense">
      <div class="modal-body">
        <div class="form-group">
          <label>Jenis Transaksi</label>
          <div class="type-toggle-group">
            <button type="button" id="btn-toggle-expense" class="type-toggle-btn active expense" onclick="setTypeToggle('expense')">
              Pengeluaran (Kas Keluar)
            </button>
            <button type="button" id="btn-toggle-income" class="type-toggle-btn income" onclick="setTypeToggle('income')">
              Pemasukan (Kas Masuk)
            </button>
          </div>
        </div>

        <div class="form-group">
          <label for="modal-amount">Nominal Transaksi (IDR)</label>
          <input class="form-control tabular-nums" id="modal-amount" name="amount" type="number" step="1000" min="1" placeholder="Contoh: 150000" required oninput="previewRupiah(this.value)">
          <span id="amount-preview" style="font-size: 12px; font-weight: 700; color: var(--brand-primary); margin-top: 2px;"></span>
        </div>

        <div class="form-group">
          <label for="modal-desc">Deskripsi Transaksi</label>
          <input class="form-control" id="modal-desc" name="description" type="text" placeholder="Contoh: Belanja kebutuhan dapur mingguan" required>
        </div>

        <div class="form-group">
          <label for="modal-cat">Kategori</label>
          <select class="form-control" id="modal-cat" name="category" required>
            {categories_options}
          </select>
        </div>

        <div class="form-group">
          <label for="modal-date">Tanggal Transaksi</label>
          <input class="form-control" id="modal-date" name="transaction_date" type="date" value="{date.today().isoformat()}" required>
        </div>

        <div class="form-group">
          <label for="modal-user">Nama Pencatat / Anggota Keluarga</label>
          <input class="form-control" id="modal-user" name="username" type="text" placeholder="Contoh: Ayah, Ibu, Admin..." value="Admin" required>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-ghost" type="button" onclick="closeModal('modal-add-tx')">Batal</button>
        <button class="btn btn-primary" type="submit">Simpan Transaksi</button>
      </div>
    </form>
  </div>
</div>

<!-- Modal: Impor CSV -->
<div class="modal-overlay" id="modal-import-csv">
  <div class="modal-dialog">
    <div class="modal-header">
      <h3>Impor Berkas Transaksi CSV</h3>
      <button class="modal-close-btn" type="button" onclick="closeModal('modal-import-csv')">&times;</button>
    </div>
    <form method="post" action="/keuangan/import" enctype="multipart/form-data">
      <div class="modal-body">
        <p style="font-size: 13px; color: var(--ink-secondary); line-height: 1.6;">
          Unggah berkas CSV pembukuan. Data baru akan ditambahkan secara aman tanpa menghapus catatan yang sudah ada di sistem.
        </p>
        <div class="dropzone" onclick="document.getElementById('file-input-csv').click()">
          <div style="color: var(--brand-primary); margin-bottom: 8px;">{_svg_icon("file-text")}</div>
          <div style="font-weight: 700; font-size: 13.5px;">Klik untuk memilih berkas CSV</div>
          <div id="file-chosen-label" style="font-size: 12px; color: var(--ink-muted); margin-top: 4px;">Format: .csv (UTF-8)</div>
          <input type="file" id="file-input-csv" name="file" accept=".csv,text/csv" style="display:none;" onchange="updateFileLabel(this)" required>
        </div>
        <div style="background: var(--bg-surface-soft); padding: 12px; border-radius: 8px; font-size: 12px; color: var(--ink-secondary);">
          <strong>Format Header Wajib:</strong><br>
          <code>tanggal, tipe, nominal, deskripsi, kategori, user</code>
        </div>
        <div>
          <a class="btn btn-ghost btn-sm" href="/keuangan/template.csv" style="font-size: 12px;">
            {_svg_icon("download")} Unduh Contoh Templat CSV
          </a>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-ghost" type="button" onclick="closeModal('modal-import-csv')">Batal</button>
        <button class="btn btn-primary" type="submit">Mulai Impor Data</button>
      </div>
    </form>
  </div>
</div>

<!-- Modal: Konfirmasi Hapus Transaksi -->
<div class="modal-overlay" id="modal-delete-tx">
  <div class="modal-dialog" style="max-width: 440px;">
    <div class="modal-header">
      <h3 style="color: var(--expense-main);">Konfirmasi Hapus Transaksi</h3>
      <button class="modal-close-btn" type="button" onclick="closeModal('modal-delete-tx')">&times;</button>
    </div>
    <form method="post" action="/keuangan/transaction/delete">
      <input type="hidden" name="period" value="{period}">
      <input type="hidden" id="delete-tx-id" name="id" value="">
      <div class="modal-body">
        <p style="font-size: 13.5px; color: var(--ink-secondary); line-height: 1.5;">
          Apakah Anda yakin ingin menghapus catatan transaksi <strong id="delete-tx-desc">-</strong> senilai <strong id="delete-tx-amt" style="color: var(--expense-main);">-</strong>?
        </p>
        <div style="font-size: 12px; color: var(--ink-muted); background: var(--expense-surface); padding: 10px; border-radius: 8px; border: 1px solid var(--expense-border);">
          ⚠️ Tindakan ini bersifat permanen dan data yang dihapus tidak dapat dipulihkan.
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-ghost" type="button" onclick="closeModal('modal-delete-tx')">Batalkan</button>
        <button class="btn btn-danger" type="submit">Ya, Hapus Transaksi</button>
      </div>
    </form>
  </div>
</div>

<!-- Embedded JSON Data for Chart.js -->
<script id="chart-data" type="application/json">{chart_json_data}</script>

<!-- Interactive Dashboard Client Scripts -->
<script>
function dismissToast(id) {{
  const el = document.getElementById(id);
  if (el) {{
    el.style.opacity = '0';
    el.style.transform = 'translateX(100%)';
    setTimeout(() => el.remove(), 300);
  }}
}}
setTimeout(() => dismissToast('main-toast'), 5000);

function toggleCustomDate() {{
  const panel = document.getElementById('custom-date-panel');
  if (panel) {{
    panel.style.display = (panel.style.display === 'none' || panel.style.display === '') ? 'flex' : 'none';
  }}
}}

function openModal(id) {{
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}}

function closeModal(id) {{
  const el = document.getElementById(id);
  if (el) el.classList.remove('active');
}}

function openAddModal() {{ openModal('modal-add-tx'); }}
function openImportModal() {{ openModal('modal-import-csv'); }}

function confirmDelete(id, desc, amount) {{
  document.getElementById('delete-tx-id').value = id;
  document.getElementById('delete-tx-desc').innerText = '#' + id + ' (' + desc + ')';
  document.getElementById('delete-tx-amt').innerText = amount;
  openModal('modal-delete-tx');
}}

function setTypeToggle(type) {{
  document.getElementById('modal-tx-type').value = type;
  const btnExp = document.getElementById('btn-toggle-expense');
  const btnInc = document.getElementById('btn-toggle-income');
  if (type === 'income') {{
    btnInc.classList.add('active');
    btnExp.classList.remove('active');
  }} else {{
    btnExp.classList.add('active');
    btnInc.classList.remove('active');
  }}
}}

function previewRupiah(val) {{
  const num = parseInt(val, 10);
  const prev = document.getElementById('amount-preview');
  if (!isNaN(num) && num > 0) {{
    prev.innerText = 'Terbaca: Rp ' + num.toLocaleString('id-ID');
  }} else {{
    prev.innerText = '';
  }}
}}

function updateFileLabel(input) {{
  const lbl = document.getElementById('file-chosen-label');
  if (input.files && input.files[0]) {{
    lbl.innerText = 'Berkas dipilih: ' + input.files[0].name;
    lbl.style.color = 'var(--brand-primary)';
    lbl.style.fontWeight = '700';
  }}
}}

function filterTableLive() {{
  const input = document.getElementById('tableQuickSearch');
  const filter = input.value.toLowerCase();
  const table = document.getElementById('transactionTable');
  const tr = table.getElementsByClassName('tx-row');
  for (let i = 0; i < tr.length; i++) {{
    const text = tr[i].textContent || tr[i].innerText;
    tr[i].style.display = text.toLowerCase().indexOf(filter) > -1 ? '' : 'none';
  }}
}}

// Initialize Charts
window.addEventListener('DOMContentLoaded', () => {{
  try {{
    const rawData = JSON.parse(document.getElementById('chart-data').textContent);
    
    // Bar Chart: Pemasukan vs Pengeluaran
    const ctxBar = document.getElementById('cashflowBarChart');
    if (ctxBar && window.Chart) {{
      new Chart(ctxBar, {{
        type: 'bar',
        data: {{
          labels: ['Total Pemasukan', 'Total Pengeluaran', 'Saldo Kas Bersih'],
          datasets: [{{
            label: 'Nominal (IDR)',
            data: [rawData.income, rawData.expense, rawData.balance],
            backgroundColor: ['#10b981', '#f43f5e', '#6366f1'],
            borderRadius: 8,
            maxBarThickness: 50
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              callbacks: {{
                label: (ctx) => ' Rp ' + Number(ctx.raw).toLocaleString('id-ID')
              }}
            }}
          }},
          scales: {{
            y: {{
              beginAtZero: true,
              ticks: {{
                callback: (val) => 'Rp ' + (val >= 1000000 ? (val/1000000).toFixed(1) + 'jt' : (val/1000).toFixed(0) + 'rb')
              }},
              grid: {{ color: '#f1f5f9' }}
            }},
            x: {{ grid: {{ display: false }} }}
          }}
        }}
      }});
    }}

    // Doughnut Chart: Categories Breakdown
    const ctxDonut = document.getElementById('categoryDonutChart');
    if (ctxDonut && window.Chart) {{
      const donutColors = [
        '#ef4444', '#f97316', '#f59e0b', '#10b981', '#06b6d4',
        '#3b82f6', '#6366f1', '#8b5cf6', '#ec4899', '#64748b'
      ];
      
      const labels = rawData.catLabels.length ? rawData.catLabels : ['Belum Ada Pengeluaran'];
      const dataValues = rawData.catData.length ? rawData.catData : [1];
      const bgColors = rawData.catData.length ? donutColors.slice(0, labels.length) : ['#e2e8f0'];

      new Chart(ctxDonut, {{
        type: 'doughnut',
        data: {{
          labels: labels,
          datasets: [{{
            data: dataValues,
            backgroundColor: bgColors,
            borderWidth: 2,
            borderColor: '#ffffff',
            hoverOffset: 6
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          cutout: '68%',
          plugins: {{
            legend: {{
              position: 'bottom',
              labels: {{
                boxWidth: 12,
                font: {{ size: 11, family: 'Plus Jakarta Sans' }}
              }}
            }},
            tooltip: {{
              callbacks: {{
                label: (ctx) => {{
                  if (!rawData.catData.length) return ' Tidak ada data';
                  return ' ' + ctx.label + ': Rp ' + Number(ctx.raw).toLocaleString('id-ID');
                }}
              }}
            }}
          }}
        }}
      }});
    }}
  }} catch(e) {{
    console.error('Chart init exception:', e);
  }}
}});
</script>"""

    status, headers, payload = _html_page(TITLE, body)
    start_response(status, headers)
    return payload


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")
    valid_subpaths = (
        "/dashboard",
        "/excel",
        "/fullscreen",
        "/export.csv",
        "/export",
        "/export.xlsx",
        "/import",
        "/template.csv",
        "/transaction/create",
        "/transaction/delete",
        "/logout",
        "/static/app.css",
        "/static/chart.umd.min.js",
    )
    if any(path.endswith(x) for x in valid_subpaths):
        return _dashboard_response(environ, start_response)

    if environ.get("REQUEST_METHOD") == "GET":
        try:
            _set_webhook()
        except Exception:
            pass
        payload = b"family-finance bot is online"
        start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(payload)))])
        return [payload]

    chat_id = ""
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        update = json.loads(environ["wsgi.input"].read(length) or b"{}")
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        text = message.get("text") or ""
        settings = load_settings()
        chat_id = str(chat.get("id", ""))
        if chat_id in settings.allowed_chat_ids and text and not text.startswith("/"):
            db = Database(settings.database_path)
            db.initialize()
            parsed = parse_message(text, datetime.now(), settings.timezone)
            category = categorize(parsed.description, db.list_categories())
            item = db.add_transaction(
                Transaction(
                    None,
                    str(sender.get("id", "")),
                    sender.get("username") or sender.get("first_name") or "user",
                    chat_id,
                    parsed.type,
                    parsed.amount,
                    parsed.description,
                    category.name,
                    parsed.transaction_date,
                    datetime.now(),
                )
            )
            _send_message(chat_id, render_confirmation(item, sender.get("username") or sender.get("first_name") or "user"))
        elif chat_id in settings.allowed_chat_ids and text.startswith("/start"):
            _send_message(chat_id, "👋 Halo! Kirim contoh transaksi seperti: bensin 50rb atau gaji masuk 8jt")
        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"ok":true}']
    except ParseError as exc:
        if chat_id:
            _send_message(chat_id, f"❓ {exc}")
        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"ok":true}']
    except Exception:
        start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
        return [b"internal error"]
