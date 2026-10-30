"""WSGI entrypoint for cPanel Passenger.

This keeps the bot online through Telegram webhook requests instead of a
long-running polling process, which is the correct model for shared hosting.
"""
import json
import os
import hashlib
import html
from http.cookies import SimpleCookie
from datetime import datetime
from urllib.parse import urlencode, parse_qs
from urllib.request import Request, urlopen

from src.categorizer import categorize
from src.config import load_settings
from src.database import Database
from src.formatting import render_confirmation
from src.models import Transaction
from src.parser import ParseError, parse_message
from src.models import TransactionFilters
from src.formatting import format_rupiah


def _send_message(chat_id, text):
    token = os.environ["BOT_TOKEN"]
    body = urlencode({"chat_id": chat_id, "text": text}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/sendMessage", data=body, method="POST")
    with urlopen(req, timeout=20):
        pass


def _set_webhook():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return
    body = urlencode({"url": "https://asistenq.com/keuangan/"}).encode()
    req = Request(f"https://api.telegram.org/bot{token}/setWebhook", data=body, method="POST")
    with urlopen(req, timeout=20):
        pass


def _dashboard_rows(db, chat_id):
    rows = db.list_transactions(TransactionFilters(chat_id))
    income = sum(x.amount for x in rows if x.type == "income")
    expense = sum(x.amount for x in rows if x.type == "expense")
    return rows, income, expense


def _authorized(environ):
    password = os.environ.get("WEB_PASSWORD")
    if not password:
        return False
    cookie = SimpleCookie(environ.get("HTTP_COOKIE", ""))
    expected = hashlib.sha256(password.encode()).hexdigest()
    return cookie.get("ff_session") and cookie["ff_session"].value == expected


def _html_page(title, body):
    return f"""<!doctype html><html lang='id'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>
    :root{{--bg:#f4f7fb;--ink:#14213d;--muted:#718096;--card:#fff;--accent:#2563eb;--green:#0f9d70;--red:#dc4c64}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);font:14px system-ui,-apple-system,Segoe UI,sans-serif;color:var(--ink)}}main{{max-width:1120px;margin:0 auto;padding:32px 20px}}header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}}h1{{margin:0;font-size:28px}}.muted{{color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:18px}}.card{{background:var(--card);border-radius:16px;padding:20px;box-shadow:0 4px 18px #14213d0d}}.label{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}}.value{{font-size:24px;font-weight:750;margin-top:8px}}.green{{color:var(--green)}}.red{{color:var(--red)}}.blue{{color:var(--accent)}}.actions a,button{{display:inline-block;border:0;border-radius:10px;padding:10px 14px;background:var(--accent);color:#fff;text-decoration:none;cursor:pointer;font-weight:650}}table{{width:100%;border-collapse:collapse}}th,td{{padding:12px 8px;border-bottom:1px solid #e9eef5;text-align:left}}th{{color:var(--muted);font-size:12px;text-transform:uppercase}}.login{{max-width:420px;margin:100px auto}}input{{width:100%;padding:12px;border:1px solid #d8e0ec;border-radius:10px;margin:8px 0 14px}}@media(max-width:700px){{.grid{{grid-template-columns:1fr}}header{{display:block}}.actions{{margin-top:14px}}}}
    </style></head><body><main>{body}</main></body></html>"""


def _dashboard_response(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if not _authorized(environ):
        if environ.get("REQUEST_METHOD") == "POST":
            length = int(environ.get("CONTENT_LENGTH") or 0)
            form = environ["wsgi.input"].read(length).decode()
            password = parse_qs(form).get("password", [""])[0]
            expected = os.environ.get("WEB_PASSWORD", "")
            if password == expected:
                cookie = hashlib.sha256(expected.encode()).hexdigest()
                body = _html_page("Finance Family", "<main><h1>Login berhasil</h1><p>Silakan buka ulang dashboard.</p></main>")
                start_response("303 See Other", [("Location", "/keuangan/dashboard"), ("Set-Cookie", f"ff_session={cookie}; HttpOnly; Secure; SameSite=Lax")])
                return [body.encode()]
        body = _html_page("Login — Finance Family", "<section class='card login'><h1>Finance Family</h1><p class='muted'>Masuk untuk melihat pembukuan keluarga.</p><form method='post'><label>Password dashboard</label><input name='password' type='password' autofocus required><button>Masuk</button></form></section>")
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")]); return [body.encode()]
    settings = load_settings(); db = Database(settings.database_path); db.initialize(); rows, income, expense = _dashboard_rows(db, next(iter(settings.allowed_chat_ids), ""))
    if path.endswith("/export") or path.endswith("/export.xlsx"):
        lines = ["ID,Tanggal,Tipe,Nominal,Deskripsi,Kategori,User"]
        lines += [f'{x.id},{x.transaction_date},{x.type},{x.amount},"{x.description.replace(chr(34), chr(34)*2)}","{x.category}","{x.username}"' for x in rows]
        payload = ("\n".join(lines) + "\n").encode(); start_response("200 OK", [("Content-Type", "application/vnd.ms-excel"), ("Content-Disposition", "attachment; filename=finance-family.xls")]); return [payload]
    tr = "".join(f"<tr><td>{x.transaction_date:%d/%m/%Y}</td><td>{'💰' if x.type=='income' else '💸'}</td><td>{html.escape(x.description)}</td><td>{html.escape(x.category)}</td><td class={'green' if x.type=='income' else 'red'}>{format_rupiah(x.amount)}</td><td>{html.escape(x.username)}</td></tr>" for x in rows[-30:][::-1]) or "<tr><td colspan='6' class='muted'>Belum ada transaksi.</td></tr>"
    body = f"<header><div><h1>Finance Family</h1><div class='muted'>Ringkasan pembukuan keluarga</div></div><div class='actions'><a href='/keuangan/export.xlsx'>⬇ Export Excel</a> <a href='#' onclick='window.print();return false'>🖨 Cetak / PDF</a></div></header><section class='grid'><div class='card'><div class='label'>Pemasukan</div><div class='value green'>{format_rupiah(income)}</div></div><div class='card'><div class='label'>Pengeluaran</div><div class='value red'>{format_rupiah(expense)}</div></div><div class='card'><div class='label'>Saldo bersih</div><div class='value blue'>{format_rupiah(income-expense)}</div></div></section><section class='card'><h2>Transaksi terbaru</h2><table><thead><tr><th>Tanggal</th><th></th><th>Deskripsi</th><th>Kategori</th><th>Nominal</th><th>Dari</th></tr></thead><tbody>{tr}</tbody></table></section>"
    payload = _html_page("Finance Family — Dashboard", body).encode(); start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")]); return [payload]


def application(environ, start_response):
    if environ.get("PATH_INFO", "").endswith("/dashboard") or environ.get("PATH_INFO", "").endswith("/export.csv"):
        return _dashboard_response(environ, start_response)
    if environ.get("REQUEST_METHOD") == "GET":
        try:
            _set_webhook()
        except Exception:
            pass
        payload = b"family-finance bot is online"
        start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(payload)))])
        return [payload]

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
            item = db.add_transaction(Transaction(None, str(sender.get("id", "")), sender.get("username") or sender.get("first_name") or "user", chat_id, parsed.type, parsed.amount, parsed.description, category.name, parsed.transaction_date, datetime.now()))
            _send_message(chat_id, render_confirmation(item, sender.get("username") or sender.get("first_name") or "user"))
        elif chat_id in settings.allowed_chat_ids and text.startswith("/start"):
            _send_message(chat_id, "👋 Halo! Kirim contoh seperti: bensin 50rb atau gaji masuk 8jt")
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
