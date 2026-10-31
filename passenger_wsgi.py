"""Passenger WSGI entrypoint for Telegram webhook and family finance dashboard.

Finance Family — Dibuat oleh effands ~ ziqva.com team with love family @2026.
"""
import csv
import hashlib
import html
import io
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, quote_plus, unquote_plus, urlencode
from urllib.request import Request, urlopen

from src.categorizer import categorize
from src.bot_control import BotController
from src.config import load_settings
from src.database import Database
from src.export_report import generate_excel, generate_pdf
from src.formatting import format_date_id, format_rupiah, render_confirmation
from src.models import Category, Transaction, TransactionFilters
from src.models import FinancialAccount
from src.wealth import WealthLedger, WealthError, InsufficientFundsError, parse_idr_amount
from src.parser import ParseError, parse_message
from src.reports import build_expense_summary, build_income_summary, build_report

TITLE = "Finance Family — Sistem Manajemen Keuangan Keluarga"
CREDIT_HTML = '<footer class="app-footer"><div class="footer-container"><div class="footer-brand">Finance Family · Sistem Manajemen Keuangan Personal & Keluarga</div><div class="footer-credit">Dibuat oleh <strong>effands</strong> ~ <a href="https://ziqva.com" target="_blank" rel="noopener">ziqva.com</a> team with love family @2026 ❤️</div></div></footer>'

HELP_TEXT = """🏛️ *FINANCE FAMILY — COMMAND CENTER*
*Sistem Pembukuan & Tata Kelola Keuangan Keluarga*
━━━━━━━━━━━━━━━━━━━━━━
Kirim pesan teks transaksi atau unggah foto struk belanja untuk pencatatan otomatis.

💡 *Contoh Format Teks Cepat:*
• `bensin 50rb`
• `belanja sayur 45rb kemarin`
• `makan malam nas got 26700`
• `gaji bulanan masuk 10jt`
• `bayar listrik pln 350.000`

📊 *Perintah Laporan & Informasi:*
• `/rekap` atau `/saldo` — Ringkasan kas bulan berjalan
• `/pemasukan` — Rincian mutasi uang masuk
• `/pengeluaran` — Rincian belanja per pos kategori
• `/hari`, `/minggu`, `/bulan`, `/tahun`, `/semua` — Laporan berkala
• `/kategori` — Daftar kategori & kata kunci aktif

🛠️ *Perintah Koreksi Transaksi (CRUD):*
• `/undo` — Batalkan catatan terakhir Anda
• `/hapus <ID>` — Hapus transaksi (Contoh: `/hapus 42`)
• `/edit <ID> nominal|deskripsi|kategori <nilai>`
• `/tambahkategori <Nama> <kata1,kata2>`
• `/hapuskategori <Nama>`
━━━━━━━━━━━━━━━━━━━━━━
✨ _Dibuat oleh effands ~ ziqva.com team with love family @2026_"""


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
        "settings": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
        "layout-dashboard": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>',
        "sparkles": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>',
        "shield": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
        "edit": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/></svg>',
        "key": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4"/><path d="m21 2-9.6 9.6"/><circle cx="7.5" cy="15.5" r="5.5"/></svg>',
        "file-pdf": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M10 12h1a1.5 1.5 0 0 1 1.5 1.5v0a1.5 1.5 0 0 1-1.5 1.5H10v-3z"/><path d="M15 12h2a1.5 1.5 0 0 1 1.5 1.5v0a1.5 1.5 0 0 1-1.5 1.5h-1"/><path d="M6 12v3"/></svg>',
        "git-pull": '<svg class="btn-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M13 6h3a2 2 0 0 1 2 2v7"/><line x1="6" x2="6" y1="9" y2="21"/></svg>',
    }
    return icons.get(name, "")


def _send_telegram(chat_id: str, text: str, reply_markup: dict | None = None, parse_mode: str = "Markdown"):
    token = os.environ.get("BOT_TOKEN")
    if not token or not chat_id:
        return
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    req = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=urlencode(payload).encode("utf-8"),
        method="POST",
    )
    try:
        with urlopen(req, timeout=15):
            pass
    except Exception:
        pass


def _answer_callback_query(callback_query_id: str, text: str = ""):
    token = os.environ.get("BOT_TOKEN")
    if not token or not callback_query_id:
        return
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    req = Request(
        f"https://api.telegram.org/bot{token}/answerCallbackQuery",
        data=urlencode(payload).encode("utf-8"),
        method="POST",
    )
    try:
        with urlopen(req, timeout=15):
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


def _get_active_password(db: Database) -> str:
    db_pw = db.get_setting("web_password", "")
    if db_pw:
        return db_pw
    return os.environ.get("WEB_PASSWORD", "")


def _authorized(environ, db: Database) -> bool:
    password = _get_active_password(db)
    if not password:
        return False
    cookie = SimpleCookie(environ.get("HTTP_COOKIE", ""))
    expected = hashlib.sha256(password.encode()).hexdigest()
    return bool(cookie.get("ff_session") and cookie["ff_session"].value == expected)


def _update_env_file(key: str, value: str, env_path: str = ".env"):
    try:
        if not os.path.exists(env_path):
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(f"{key}={value}\n")
            return
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        found = False
        new_lines = []
        for line in lines:
            if line.strip().startswith(f"{key}=") or line.strip().startswith(f"export {key}="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}\n")
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
    except Exception:
        pass


def _test_gemini_connection(api_key: str, model: str) -> tuple[bool, str]:
    raw_keys = [k.strip() for k in api_key.replace("\r", "\n").replace(",", "\n").split("\n") if k.strip()]
    if not raw_keys:
        return False, "Kunci API Gemini belum diisi."
    try:
        from src.receipt_ai import GeminiKeyPool
        pool = GeminiKeyPool(tuple(raw_keys), model or "gemini-3.8-flash")
        ok, msg = pool.test()
        if ok:
            return True, f"Koneksi berhasil terhubung menggunakan model {model or 'gemini-3.8-flash'} ({len(pool.keys)} Kunci API aktif)."
        return False, msg
    except Exception as exc:
        return False, str(exc)


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
          <div class="auth-feature-item"><span class="auth-feature-check">✓</span><span>Laporan arus kas berkala, ekspor PDF & berkas Excel</span></div>
        </div>
      </div>
      <div style="font-size: 12px; color: #94a3b8; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 16px;">
        Finance Family · Dibuat oleh effands ~ ziqva.com team with love family @2026
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
                    row["deskripsi"] or "Impor Data",
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
        desc_js = desc_escaped.replace("'", "\\'")

        output.append(f"""<tr class="tx-row" data-id="{x.id}">
          <td class="tabular-nums" style="color: var(--ink-muted); font-size: 12px; font-weight: 600;">#{x.id}</td>
          <td class="tabular-nums" style="white-space: nowrap; font-weight: 500;">{format_date_id(x.transaction_date)}</td>
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
            <button class="btn btn-ghost btn-sm" type="button" title="Hapus transaksi ini" onclick="confirmDelete({x.id}, '{desc_js}', '{format_rupiah(x.amount)}')">
              {_svg_icon("trash")}
            </button>
          </td>
        </tr>""")
    return "".join(output)


def _render_settings_page(db: Database, settings, active_tab: str, toast_html: str):
    categories = db.list_categories()

    gemini_keys_val = db.get_setting("gemini_api_keys", "") or os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))
    gemini_model_val = db.get_setting("gemini_model", "") or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    gemini_active = bool(gemini_keys_val.strip())

    tab_cat_active = "active" if active_tab == "categories" else ""
    tab_gemini_active = "active" if active_tab == "gemini" else ""
    tab_sec_active = "active" if active_tab == "security" else ""
    tab_sys_active = "active" if active_tab == "system" else ""

    # Git & Deployment Information
    git_branch = "main"
    git_commit = "-"
    git_remote = "-"
    try:
        git_branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.STDOUT, text=True, timeout=5).strip()
        git_commit = subprocess.check_output(["git", "log", "-1", "--format=%h - %s (%cd)", "--date=short"], stderr=subprocess.STDOUT, text=True, timeout=5).strip()
        git_remote = subprocess.check_output(["git", "config", "--get", "remote.origin.url"], stderr=subprocess.STDOUT, text=True, timeout=5).strip()
    except Exception:
        pass
    last_git_update = db.get_setting("last_git_update", "") or "Belum pernah dilakukan pembaruan dari dasbor web."
    bot_controller = BotController(os.path.dirname(os.path.abspath(__file__)))
    bot_status = bot_controller.status()
    bot_status_label = "Aktif / Online" if bot_status.running else "Mati / Offline"
    bot_status_class = "active" if bot_status.running else "inactive"
    bot_status_detail = f"PID {bot_status.pid}" if bot_status.pid else "Worker Telegram belum berjalan"

    cat_rows = []
    for c in categories:
        tx_count = db.count_category_transactions(c.name)
        type_label = "Pengeluaran" if c.type == "expense" else ("Pemasukan" if c.type == "income" else "Pemasukan & Pengeluaran")
        type_cls = "expense" if c.type == "expense" else ("income" if c.type == "income" else "neutral")
        kw_badges = "".join(f'<span class="keyword-badge">{html.escape(k)}</span>' for k in c.keywords) or '<span style="color:var(--ink-faint); font-size:12px;">(Tanpa kata kunci)</span>'

        is_default = c.name == "Lain-lain"
        category_js = html.escape(c.name).replace("'", "\\'")
        keywords_js = html.escape(",".join(c.keywords)).replace("'", "\\'")
        delete_btn = f"""<button class="btn btn-ghost btn-sm" type="button" style="color: var(--expense-main);" title="Hapus Kategori" onclick="confirmDeleteCategory('{category_js}')">{_svg_icon("trash")}</button>""" if not is_default else '<span style="font-size:11px; color:var(--ink-faint); font-style:italic;">Bawaan sistem</span>'

        cat_rows.append(f"""<tr>
          <td style="font-size: 20px; width: 50px; text-align: center;">{c.emoji}</td>
          <td style="font-weight: 700; color: var(--ink-primary);">{html.escape(c.name)}</td>
          <td><span class="badge-type {type_cls}">{type_label}</span></td>
          <td><div class="category-keywords-wrap">{kw_badges}</div></td>
          <td class="tabular-nums" style="font-weight: 600; color: var(--ink-muted);">{tx_count} transaksi</td>
          <td class="action-cell">
            <button class="btn btn-ghost btn-sm" type="button" title="Sunting Kategori" onclick="openEditCategoryModal('{category_js}', '{c.emoji}', '{c.type}', '{keywords_js}')">
              {_svg_icon("edit")}
            </button>
            {delete_btn}
          </td>
        </tr>""")

    categories_table_html = "".join(cat_rows)

    if gemini_active:
        gemini_status_html = f"""<div class="status-callout active">
          {_svg_icon("check")}
          <div>
            <strong>Layanan Gemini Vision AI Siap Digunakan</strong>
            <div style="font-size: 12px; margin-top: 2px;">Kunci API telah tersimpan dan aktif untuk ekstraksi otomatis struk belanja dari bot Telegram.</div>
          </div>
        </div>"""
    else:
        gemini_status_html = f"""<div class="status-callout inactive">
          {_svg_icon("key")}
          <div>
            <strong>Integrasi Gemini Vision AI Belum Dikonfigurasi</strong>
            <div style="font-size: 12px; margin-top: 2px;">Tambahkan Kunci API Gemini agar foto struk belanja yang dikirim ke bot Telegram dapat dianalisa secara otomatis.</div>
          </div>
        </div>"""

    emoji_quick_buttons = "".join(f'<button type="button" class="btn btn-secondary btn-sm" onclick="setEmojiQuick(&quot;{em}&quot;)">{em}</button>' for em in ['🍔','⛽','🏠','💊','📱','👶','👕','💰','📈','🎓','🚗','✈️','🎁','🐾','🛒','💳'])
    body = f"""<div class="toast-container">{toast_html}</div>

<main class="page-shell">
  <header class="topbar">
    <a class="brand-lockup" href="/keuangan/dashboard" title="Kembali ke Beranda (Home)">
      <div class="brand-mark">FF</div>
      <div class="brand-info">
        <span class="brand-badge"><span class="status-dot"></span>Panel Pengaturan</span>
        <h1 class="brand-title">Pengaturan Sistem</h1>
        <span class="brand-desc">Konfigurasi Kategori, Layanan AI Gemini, Keamanan & Parameter Sistem</span>
      </div>
    </a>
    <div class="actions">
      <nav class="header-nav-menu">
        <a class="header-nav-link" href="/keuangan/dashboard">
          {_svg_icon("layout-dashboard")} Dasbor
        </a>
        <a class="header-nav-link active" href="/keuangan/settings">
          {_svg_icon("settings")} Pengaturan
        </a>
      </nav>
      <a class="btn btn-ghost" href="/keuangan/logout" title="Keluar dari sesi ini" onclick="return confirm('Keluar dari sesi dasbor keuangan?')">
        {_svg_icon("logout")}
      </a>
    </div>
  </header>

  <nav class="settings-nav-tabs">
    <a class="settings-tab-btn {tab_cat_active}" href="/keuangan/settings?tab=categories">
      🏷️ Kategori Transaksi
    </a>
    <a class="settings-tab-btn {tab_gemini_active}" href="/keuangan/settings?tab=gemini">
      {_svg_icon("sparkles")} Integrasi Gemini AI
    </a>
    <a class="settings-tab-btn {tab_sec_active}" href="/keuangan/settings?tab=security">
      {_svg_icon("shield")} Kata Sandi & Keamanan
    </a>
    <a class="settings-tab-btn {tab_sys_active}" href="/keuangan/settings?tab=system">
      ⚙️ Info Sistem & Telegram
    </a>
  </nav>

  <!-- TAB 1: KATEGORI TRANSAKSI (CRUD) -->
  <div id="tab-content-categories" style="display: {'block' if active_tab == 'categories' else 'none'};">
    <section class="settings-section-card">
      <div class="settings-section-header">
        <div>
          <h2 class="settings-section-title">Manajemen Kategori Transaksi</h2>
          <p class="settings-section-desc">
            Kelola klasifikasi pos pengeluaran dan pemasukan. Kata kunci digunakan oleh parser otomatis untuk mengkategorikan transaksi teks dari pesan Telegram.
          </p>
        </div>
        <button class="btn btn-primary" type="button" onclick="openNewCategoryModal()">
          {_svg_icon("plus")} Tambah Kategori Baru
        </button>
      </div>

      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 60px; text-align: center;">Ikon</th>
              <th style="width: 180px;">Nama Kategori</th>
              <th style="width: 150px;">Tipe Pos</th>
              <th>Kata Kunci Deteksi Otomatis (Keywords)</th>
              <th style="width: 130px;">Penggunaan</th>
              <th style="width: 100px; text-align: center;">Aksi</th>
            </tr>
          </thead>
          <tbody>
            {categories_table_html}
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <!-- TAB 2: INTEGRASI GEMINI VISION AI -->
  <div id="tab-content-gemini" style="display: {'block' if active_tab == 'gemini' else 'none'};">
    <section class="settings-section-card">
      <div class="settings-section-header">
        <div>
          <h2 class="settings-section-title">Konfigurasi Google Gemini Vision AI</h2>
          <p class="settings-section-desc">
            Membaca foto struk dan nota belanja secara instan via Telegram, mengekstraksi tanggal, nominal total, nama toko, dan menetapkan kategori secara cerdas.
          </p>
        </div>
      </div>

      {gemini_status_html}

      <form method="post" action="/keuangan/settings/gemini/save" style="max-width: 680px; display: flex; flex-direction: column; gap: 18px;">
        <div class="form-group">
          <label for="gemini-key">Google Gemini API Keys (Multi-Key Input)</label>
          <div class="api-input-wrap" style="align-items: flex-start;">
            <textarea class="form-control" id="gemini-key" name="gemini_api_keys" rows="4" style="font-family: monospace; font-size: 13px; line-height: 1.5; resize: vertical;" placeholder="AIzaSy...&#10;AIzaSy...&#10;(Satu API key per baris atau pisahkan dengan koma)">{html.escape(gemini_keys_val)}</textarea>
          </div>
          <div class="setting-help-text">
            Dapatkan Kunci API gratis via portal <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener">Google AI Studio</a>. Masukkan satu atau beberapa key (satu per baris atau pisahkan dengan koma). Sistem otomatis melakukan rotasi multi-key (*round-robin*) dan *failover* saat kuota suatu key habis.
          </div>
        </div>

        <div class="form-group">
          <label for="gemini-model">Pilihan Model Gemini Generasi Terbaru</label>
          <select class="form-control" id="gemini-model" name="gemini_model">
            <option value="gemini-3.8-flash" {'selected' if gemini_model_val == 'gemini-3.8-flash' else ''}>gemini-3.8-flash (Terbaru: Sangat Cepat, Kuota Hemat & Super Akurat)</option>
            <option value="gemini-3.7-flash" {'selected' if gemini_model_val == 'gemini-3.7-flash' else ''}>gemini-3.7-flash (Generasi 3.7 Cepat)</option>
            <option value="gemini-3.6-flash" {'selected' if gemini_model_val == 'gemini-3.6-flash' else ''}>gemini-3.6-flash (Generasi 3.6 Cepat)</option>
            <option value="gemini-2.0-flash" {'selected' if gemini_model_val == 'gemini-2.0-flash' else ''}>gemini-2.0-flash (Flash Generasi 2.0)</option>
            <option value="gemini-2.0-flash-lite" {'selected' if gemini_model_val == 'gemini-2.0-flash-lite' else ''}>gemini-2.0-flash-lite (Model lama — ketersediaan tergantung Google)</option>
            <option value="gemini-2.5-flash" {'selected' if gemini_model_val == 'gemini-2.5-flash' else ''}>gemini-2.5-flash (Flash Generasi 2.5)</option>
          </select>
          <div class="setting-help-text">
            Pilih model untuk membaca struk, lalu simpan konfigurasi. Opsi generasi baru dan lama tersedia untuk pengujian; model lama yang sudah dihentikan Google akan ditolak API.
          </div>
        </div>

        <div style="display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap;">
          <button class="btn btn-primary" type="submit">
            {_svg_icon("check")} Simpan Konfigurasi AI
          </button>
          <button class="btn btn-secondary" type="submit" formaction="/keuangan/settings/gemini/test">
            {_svg_icon("sparkles")} Uji Koneksi Gemini
          </button>
        </div>
      </form>
    </section>
  </div>

  <!-- TAB 3: KATA SANDI & KEAMANAN -->
  <div id="tab-content-security" style="display: {'block' if active_tab == 'security' else 'none'};">
    <section class="settings-section-card" style="max-width: 680px;">
      <div class="settings-section-header">
        <div>
          <h2 class="settings-section-title">Perbarui Kata Sandi Akses</h2>
          <p class="settings-section-desc">
            Ubah kata sandi otorisasi yang digunakan untuk masuk ke dasbor keuangan keluarga.
          </p>
        </div>
      </div>

      <form method="post" action="/keuangan/settings/password/save" style="display: flex; flex-direction: column; gap: 18px;">
        <div class="form-group">
          <label for="current-pwd">Kata Sandi Saat Ini</label>
          <input class="form-control" type="password" id="current-pwd" name="current_password" placeholder="••••••••••••" required>
        </div>

        <div class="form-group">
          <label for="new-pwd">Kata Sandi Baru</label>
          <input class="form-control" type="password" id="new-pwd" name="new_password" minlength="6" placeholder="Minimal 6 karakter" required>
        </div>

        <div class="form-group">
          <label for="confirm-pwd">Konfirmasi Kata Sandi Baru</label>
          <input class="form-control" type="password" id="confirm-pwd" name="confirm_password" minlength="6" placeholder="Ulangi kata sandi baru" required>
        </div>

        <div style="background-color: var(--bg-surface-soft); padding: 12px 16px; border-radius: 8px; font-size: 12.5px; color: var(--ink-secondary); border: 1px solid var(--border-subtle);">
          🔒 Kata sandi dienkripsi menggunakan cryptographic hashing SHA-256 dan disimpan secara terlindung di basis data lokal.
        </div>

        <div>
          <button class="btn btn-primary" type="submit">
            Perbarui Kata Sandi
          </button>
        </div>
      </form>
    </section>
  </div>

  <!-- TAB 4: INFO SISTEM & TELEGRAM -->
  <div id="tab-content-system" style="display: {'block' if active_tab == 'system' else 'none'};">
    <section class="settings-section-card" style="margin-bottom: 24px;">
      <div class="settings-section-header">
        <div>
          <h2 class="settings-section-title">Kontrol Bot Telegram</h2>
          <p class="settings-section-desc">Nyalakan, matikan, atau restart bot langsung dari sini tanpa membuka Terminal hosting.</p>
        </div>
        <div class="status-callout {bot_status_class}" style="margin:0; min-width:210px;">
          <span class="status-dot"></span>
          <div><strong>{bot_status_label}</strong><div style="font-size:12px; margin-top:2px;">{bot_status_detail}</div></div>
        </div>
      </div>
      <div style="display:flex; gap:10px; flex-wrap:wrap; align-items:center;">
        <form method="post" action="/keuangan/settings/bot/start"><button class="btn btn-primary" type="submit">▶️ Nyalakan Bot</button></form>
        <form method="post" action="/keuangan/settings/bot/restart"><button class="btn btn-secondary" type="submit">🔄 Restart Bot</button></form>
        <form method="post" action="/keuangan/settings/bot/stop" onsubmit="return confirm('Matikan bot Telegram sekarang?')"><button class="btn btn-danger" type="submit">⏹️ Matikan Bot</button></form>
        <a class="btn btn-ghost" href="/keuangan/settings?tab=system">↻ Cek Status</a>
      </div>
      <p class="setting-help-text" style="margin-top:12px;">Bot yang dimatikan tidak akan membaca pesan atau foto baru di Telegram. Auto-start setelah restart server tetap aktif.</p>
    </section>

    <section class="settings-section-card" style="margin-bottom: 24px;">
      <div class="settings-section-header">
        <div>
          <h2 class="settings-section-title">Pembaruan Sistem & Sinkronisasi Git</h2>
          <p class="settings-section-desc">
            Tarik pembaruan kode sumber langsung dari repositori GitHub ke VPS / server hosting tanpa harus masuk ke terminal SSH atau cPanel admin.
          </p>
        </div>
        <form method="post" action="/keuangan/settings/system/update" onsubmit="return confirmSystemUpdate(this);">
          <button class="btn btn-primary" type="submit" id="btn-git-update">
            {_svg_icon("refresh")} Perbarui dari GitHub (Git Pull)
          </button>
        </form>
      </div>

      <table class="info-table">
        <tbody>
          <tr>
            <th>Status Git & Branch</th>
            <td><span class="keyword-badge" style="background:#e0f2fe; color:#0369a1; font-weight:700;">Branch: {html.escape(git_branch)}</span></td>
          </tr>
          <tr>
            <th>Commit Aktif Saat Ini</th>
            <td><code>{html.escape(git_commit)}</code></td>
          </tr>
          <tr>
            <th>Repositori GitHub (Remote)</th>
            <td><a href="{html.escape(git_remote)}" target="_blank" rel="noopener" style="color:var(--brand-primary); font-weight:600;">{html.escape(git_remote)}</a></td>
          </tr>
          <tr>
            <th>Mekanisme Muat Ulang Hosting</th>
            <td>Passenger WSGI Auto-Reload (<code>tmp/restart.txt</code>) & Re-kompilasi Otomatis</td>
          </tr>
          <tr>
            <th>Riwayat Pembaruan Terakhir</th>
            <td><code>{html.escape(last_git_update)}</code></td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="settings-section-card">
      <div class="settings-section-header">
        <div>
          <h2 class="settings-section-title">Parameter & Lingkungan Sistem</h2>
          <p class="settings-section-desc">
            Informasi status infrastruktur, perizinan Telegram, dan pengaturan lingkungan aktif.
          </p>
        </div>
      </div>

      <table class="info-table">
        <tbody>
          <tr>
            <th>ID Chat Telegram Terdaftar</th>
            <td><code>{html.escape(", ".join(sorted(settings.allowed_chat_ids)) or "(Belum diisi)")}</code></td>
          </tr>
          <tr>
            <th>Zona Waktu Operasional</th>
            <td>{html.escape(settings.timezone)}</td>
          </tr>
          <tr>
            <th>Lokasi Berkas Basis Data</th>
            <td><code>{html.escape(settings.database_path)}</code></td>
          </tr>
          <tr>
            <th>Batas Laju Pesan (*Rate Limit*)</th>
            <td>{settings.rate_limit} pesan / menit / pengguna</td>
          </tr>
          <tr>
            <th>Runtime Python</th>
            <td>Python {sys.version.split()[0]} ({sys.platform})</td>
          </tr>
          <tr>
            <th>Mode Basis Data SQLite</th>
            <td>WAL (*Write-Ahead Logging*) Enabled</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
  {CREDIT_HTML}
</main>

<!-- Modal: Tambah / Sunting Kategori -->
<div class="modal-overlay" id="modal-category-edit">
  <div class="modal-dialog">
    <div class="modal-header">
      <h3 id="cat-modal-title">Tambah Kategori Baru</h3>
      <button class="modal-close-btn" type="button" onclick="closeModal('modal-category-edit')">&times;</button>
    </div>
    <form method="post" action="/keuangan/settings/category/save">
      <input type="hidden" id="cat-old-name" name="old_name" value="">
      <div class="modal-body">
        <div style="display: grid; grid-template-columns: 80px 1fr; gap: 12px;">
          <div class="form-group">
            <label for="cat-emoji">Emoji</label>
            <input class="form-control" style="text-align: center; font-size: 20px;" id="cat-emoji" name="emoji" value="📁" maxlength="4" required>
          </div>
          <div class="form-group">
            <label for="cat-name">Nama Kategori</label>
            <input class="form-control" id="cat-name" name="name" placeholder="Contoh: Investasi & Saham" required>
          </div>
        </div>

        <div class="form-group">
          <label style="font-size: 11.5px; color: var(--ink-muted); margin-bottom: 4px;">Pilihan Emoji Cepat:</label>
          <div style="display: flex; gap: 6px; flex-wrap: wrap;">
            {emoji_quick_buttons}
          </div>
        </div>

        <div class="form-group">
          <label for="cat-type">Jenis Alokasi Pos</label>
          <select class="form-control" id="cat-type" name="type">
            <option value="expense">Pengeluaran (Beban Kas Keluar)</option>
            <option value="income">Pemasukan (Kas Masuk)</option>
            <option value="both">Keduanya (Pemasukan & Pengeluaran)</option>
          </select>
        </div>

        <div class="form-group">
          <label for="cat-keywords">Kata Kunci Deteksi Otomatis (Pisahkan dengan koma)</label>
          <textarea class="form-control" id="cat-keywords" name="keywords" rows="3" placeholder="Contoh: bibit, saham, reksa, crypto, dividen"></textarea>
          <div class="setting-help-text">
            Bot Telegram akan otomatis mengenali kata-kata ini saat mencatat transaksi dari pesan teks.
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-ghost" type="button" onclick="closeModal('modal-category-edit')">Batalkan</button>
        <button class="btn btn-primary" type="submit">Simpan Kategori</button>
      </div>
    </form>
  </div>
</div>

<!-- Modal: Konfirmasi Hapus Kategori -->
<div class="modal-overlay" id="modal-category-delete">
  <div class="modal-dialog" style="max-width: 440px;">
    <div class="modal-header">
      <h3 style="color: var(--expense-main);">Konfirmasi Hapus Kategori</h3>
      <button class="modal-close-btn" type="button" onclick="closeModal('modal-category-delete')">&times;</button>
    </div>
    <form method="post" action="/keuangan/settings/category/delete">
      <input type="hidden" id="delete-cat-name" name="name" value="">
      <div class="modal-body">
        <p style="font-size: 13.5px; color: var(--ink-secondary); line-height: 1.5;">
          Hapus kategori <strong id="delete-cat-label">-</strong>?
        </p>
        <div style="font-size: 12px; color: var(--ink-muted); background: var(--bg-surface-soft); padding: 10px; border-radius: 8px; border: 1px solid var(--border-subtle); margin-top: 8px;">
          Catatan: Seluruh riwayat transaksi yang terhubung ke kategori ini akan otomatis dialihkan ke kategori <strong>Lain-lain</strong> agar riwayat pembukuan Anda tetap aman.
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-ghost" type="button" onclick="closeModal('modal-category-delete')">Batalkan</button>
        <button class="btn btn-danger" type="submit">Ya, Hapus Kategori</button>
      </div>
    </form>
  </div>
</div>

<script>
function dismissToast(id) {{
  const el = document.getElementById(id);
  if (el) {{
    el.style.opacity = '0';
    el.style.transform = 'translateX(100%)';
    setTimeout(() => el.remove(), 300);
  }}
}}
setTimeout(() => dismissToast('main-toast'), 6000);

function openModal(id) {{
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}}

function closeModal(id) {{
  const el = document.getElementById(id);
  if (el) el.classList.remove('active');
}}

function openNewCategoryModal() {{
  document.getElementById('cat-modal-title').innerText = 'Tambah Kategori Baru';
  document.getElementById('cat-old-name').value = '';
  document.getElementById('cat-name').value = '';
  document.getElementById('cat-emoji').value = '📁';
  document.getElementById('cat-type').value = 'expense';
  document.getElementById('cat-keywords').value = '';
  openModal('modal-category-edit');
}}

function openEditCategoryModal(name, emoji, type, keywords) {{
  document.getElementById('cat-modal-title').innerText = 'Sunting Kategori: ' + name;
  document.getElementById('cat-old-name').value = name;
  document.getElementById('cat-name').value = name;
  document.getElementById('cat-emoji').value = emoji || '📁';
  document.getElementById('cat-type').value = type || 'expense';
  document.getElementById('cat-keywords').value = keywords || '';
  openModal('modal-category-edit');
}}

function confirmDeleteCategory(name) {{
  document.getElementById('delete-cat-name').value = name;
  document.getElementById('delete-cat-label').innerText = name;
  openModal('modal-category-delete');
}}

function setEmojiQuick(em) {{
  document.getElementById('cat-emoji').value = em;
}}

function toggleApiKeyReveal(inputId, btn) {{
  const inp = document.getElementById(inputId);
  if (inp.type === 'password') {{
    inp.type = 'text';
    btn.innerText = 'Sembunyikan';
  }} else {{
    inp.type = 'password';
    btn.innerText = 'Tampilkan';
  }}
}}
function confirmSystemUpdate(form) {{
  if (confirm('Tarik pembaruan kode terbaru dari repositori GitHub (git pull) dan muat ulang aplikasi server sekarang?')) {{
    const btn = document.getElementById('btn-git-update');
    if (btn) {{
      btn.disabled = true;
      btn.innerHTML = 'Memproses Git Pull & Reload...';
    }}
    return true;
  }}
  return false;
}}
</script>"""

    return body


def _wealth_csrf(db: Database) -> str:
    secret = _get_active_password(db) or "finance-family"
    return hashlib.sha256((secret + ":wealth-ledger").encode("utf-8")).hexdigest()


def _mask_identifier(value: str) -> str:
    value = value or ""
    if len(value) <= 4:
        return "••••" if value else "—"
    return "•••• " + value[-4:]


def _render_wealth_page(db: Database, chat_id: str, csrf_token: str, toast_html: str = "") -> str:
    ledger = WealthLedger(db)
    summary = ledger.get_wealth_summary(chat_id)
    balances = {x.account_id: x for x in ledger.get_account_balances(chat_id)}
    accounts = db.list_accounts(chat_id, include_archived=True)
    account_rows = "".join(
        f"""<tr><td><strong>{html.escape(a.name)}</strong><div class='setting-help-text'>{html.escape(a.provider or a.account_type.title())}</div></td>
        <td>{html.escape(a.account_type.title())}</td><td>{html.escape(_mask_identifier(a.account_identifier))}</td>
        <td class='tx-amount'>{format_rupiah(balances[a.id].balance if a.id in balances else a.opening_balance)}</td>
        <td>{'Aktif' if a.is_active else 'Diarsipkan'}{' <form method="post" action="/keuangan/wealth/account/archive" style="display:inline"><input type="hidden" name="csrf_token" value="' + csrf_token + '"><input type="hidden" name="account_id" value="' + str(a.id) + '"><button class="btn btn-ghost" type="submit">Arsipkan</button></form>' if a.is_active else ''}</td></tr>"""
        for a in accounts
    ) or "<tr><td colspan='5'><div class='empty-state-box'><div class='empty-state-title'>Belum ada akun keuangan</div><div class='empty-state-desc'>Tambahkan rekening bank, e-wallet, cash, atau investasi untuk mulai menghitung total kekayaan.</div></div></td></tr>"
    active_options = "".join(f"<option value='{a.id}'>{html.escape(a.name)} — {html.escape(a.provider)}</option>" for a in accounts if a.is_active)
    operation_rows = "".join(
        f"<tr><td>{html.escape(r['transaction_date'])}</td><td><strong>{html.escape(r['operation_type'])}</strong></td><td>{html.escape(r['description'])}</td><td>{format_rupiah(r['debits'])}</td><td>{'Dibatalkan' if r['reversed_operation_id'] else ('<form method=\"post\" action=\"/keuangan/wealth/operation/reverse\"><input type=\"hidden\" name=\"csrf_token\" value=\"' + csrf_token + '\"><input type=\"hidden\" name=\"operation_id\" value=\"' + html.escape(r['id']) + '\"><input class=\"form-control\" name=\"reason\" placeholder=\"Alasan\" required><button class=\"btn btn-ghost\" type=\"submit\">Batalkan</button></form>')}</td></tr>"
        for r in ledger.list_operations(chat_id)
    ) or "<tr><td colspan='5'><div class='empty-state-box'>Belum ada mutasi wealth.</div></td></tr>"
    return f"""<main class='page-shell'>
      <header class='topbar'><a class='brand-lockup' href='/keuangan/dashboard'><div class='brand-mark'>FF</div><div class='brand-info'><span class='brand-badge'><span class='status-dot'></span>Wealth Center</span><h1 class='brand-title'>Total Kekayaan</h1><span class='brand-desc'>Saldo tercatat lintas bank, e-wallet, cash, dan investasi</span></div></a>
      <div class='actions'><nav class='header-nav-menu'><a class='header-nav-link' href='/keuangan/dashboard'>{_svg_icon('layout-dashboard')} Dasbor</a><a class='header-nav-link active' href='/keuangan/wealth'>{_svg_icon('wallet')} Kekayaan</a><a class='header-nav-link' href='/keuangan/settings'>{_svg_icon('settings')} Pengaturan</a></nav><a class='btn btn-ghost' href='/logout'>{_svg_icon('logout')} Keluar</a></div></header>
      {toast_html}
      <section class='metric-grid'>
        <article class='metric-card'><div class='metric-label'>Total Kekayaan</div><div class='metric-value val-balance'>{format_rupiah(summary.total_wealth)}</div><div class='metric-footer'><span>Semua akun aktif</span><span class='metric-tag tag-neutral'>IDR</span></div></article>
        <article class='metric-card'><div class='metric-label'>Aset Likuid</div><div class='metric-value val-income'>{format_rupiah(summary.liquid_assets)}</div><div class='metric-footer'><span>Bank + e-wallet + cash</span></div></article>
        <article class='metric-card'><div class='metric-label'>Investasi</div><div class='metric-value val-stats'>{format_rupiah(summary.investments)}</div><div class='metric-footer'><span>SBN, crypto, saham, aset</span></div></article>
        <article class='metric-card'><div class='metric-label'>Cash di Tangan</div><div class='metric-value val-balance'>{format_rupiah(summary.cash)}</div><div class='metric-footer'><span>Belum dilaporkan penggunaannya</span></div></article>
      </section>
      <section class='panel settings-section-card'><div class='settings-section-header'><div><h2 class='settings-section-title'>Akun Keuangan</h2><p class='settings-section-desc'>Saldo dihitung dari saldo awal dan ledger. Transfer antar akun tidak menggandakan kekayaan.</p></div><a class='btn btn-primary' href='#akun-baru'>{_svg_icon('plus')} Tambah Akun</a></div>
        <div class='table-responsive'><table class='data-table'><thead><tr><th>Nama Akun</th><th>Jenis</th><th>Identitas</th><th>Saldo Tercatat</th><th>Status</th></tr></thead><tbody>{account_rows}</tbody></table></div>
      </section>
      <section class='breakdown-grid'><div class='panel settings-section-card' id='akun-baru'><div class='settings-section-header'><div><h2 class='settings-section-title'>Tambah Akun</h2><p class='settings-section-desc'>Nomor rekening/ID hanya digunakan untuk identifikasi dan ditampilkan tersamarkan.</p></div></div>
        <form method='post' action='/keuangan/wealth/account/save' class='form-stack'><input type='hidden' name='csrf_token' value='{csrf_token}'><div class='form-group'><label>Nama panggilan</label><input class='form-control' name='name' required placeholder='Mandiri Utama'></div><div class='form-group'><label>Jenis akun</label><select class='form-control' name='account_type'><option value='bank'>Bank</option><option value='ewallet'>E-wallet</option><option value='cash'>Cash</option><option value='investment'>Investasi</option></select></div><div class='form-group'><label>Bank / provider</label><input class='form-control' name='provider' placeholder='Bank Mandiri / DANA / SBN'></div><div class='form-group'><label>Nama pemilik</label><input class='form-control' name='holder_name' placeholder='Keluarga'></div><div class='form-group'><label>Nomor rekening / ID / nomor HP</label><input class='form-control' name='account_identifier'></div><div class='form-group'><label>Saldo awal (IDR)</label><input class='form-control' name='opening_balance' inputmode='numeric' required value='0'></div><div class='form-group'><label>Tanggal saldo awal</label><input class='form-control' type='date' name='opening_balance_date' required value='{date.today().isoformat()}'></div><button class='btn btn-primary' type='submit'>Simpan Akun</button></form>
      </div><div class='panel settings-section-card'><div class='settings-section-header'><div><h2 class='settings-section-title'>Catat Mutasi</h2><p class='settings-section-desc'>Pilih sumber dana untuk pengeluaran, transfer, dan tarik ATM.</p></div></div><form method='post' action='/keuangan/wealth/operation/create' class='form-stack'><input type='hidden' name='csrf_token' value='{csrf_token}'><div class='form-group'><label>Jenis</label><select class='form-control' name='operation_type'><option value='expense'>Pengeluaran</option><option value='cash_withdrawal'>Tarik tunai ATM</option><option value='transfer'>Transfer antar akun</option></select></div><div class='form-group'><label>Dari akun</label><select class='form-control' name='source_account_id' required>{active_options}</select></div><div class='form-group'><label>Ke akun (untuk transfer/ATM)</label><select class='form-control' name='destination_account_id'><option value=''>— pilih bila diperlukan —</option>{active_options}</select></div><div class='form-group'><label>Nominal (IDR)</label><input class='form-control' name='amount' inputmode='numeric' required></div><div class='form-group'><label>Keterangan</label><input class='form-control' name='description' required placeholder='Belanja / tarik tunai / transfer'></div><button class='btn btn-primary' type='submit'>Catat Mutasi</button></form></div></section>
      <section class='panel settings-section-card'><div class='settings-section-header'><div><h2 class='settings-section-title'>Rekonsiliasi Saldo</h2><p class='settings-section-desc'>Jika saldo aplikasi berbeda dari saldo nyata, masukkan saldo aktual. Sistem membuat adjustment yang dapat diaudit.</p></div></div><form method='post' action='/keuangan/wealth/reconcile' class='form-stack'><input type='hidden' name='csrf_token' value='{csrf_token}'><div class='form-group'><label>Akun</label><select class='form-control' name='account_id' required>{active_options}</select></div><div class='form-group'><label>Saldo aktual (IDR)</label><input class='form-control' name='actual_balance' inputmode='numeric' required></div><div class='form-group'><label>Alasan</label><input class='form-control' name='reason' required placeholder='Cocokkan mutasi bank'></div><button class='btn btn-secondary' type='submit'>Simpan Rekonsiliasi</button></form></section>
      <section class='panel settings-section-card'><div class='settings-section-header'><div><h2 class='settings-section-title'>Sumber Dana Default</h2><p class='settings-section-desc'>Dipakai oleh input cepat Telegram bila transaksi tidak menyebut sumber secara eksplisit.</p></div></div><form method='post' action='/keuangan/wealth/default/save' class='form-stack'><input type='hidden' name='csrf_token' value='{csrf_token}'><div class='form-group'><label>Jenis transaksi</label><select class='form-control' name='operation_kind'><option value='expense'>Pengeluaran</option><option value='income'>Pemasukan</option></select></div><div class='form-group'><label>Akun default</label><select class='form-control' name='account_id' required>{active_options}</select></div><button class='btn btn-secondary' type='submit'>Simpan Default</button></form></section>
      <section class='panel settings-section-card'><div class='settings-section-header'><div><h2 class='settings-section-title'>Riwayat Ledger & Koreksi</h2><p class='settings-section-desc'>Setiap operasi dapat ditelusuri dan dibatalkan dengan reversal; histori asli tidak dihapus.</p></div></div><div class='table-responsive'><table class='data-table'><thead><tr><th>Tanggal</th><th>Jenis</th><th>Keterangan</th><th>Debit</th><th>Aksi</th></tr></thead><tbody>{operation_rows}</tbody></table></div></section>
      {CREDIT_HTML}</main>"""


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

    # Initialize Database for Authentication and Settings
    settings = load_settings()
    db = Database(settings.database_path)
    db.initialize()
    chat_id = next(iter(settings.allowed_chat_ids), "default")

    # Authentication Handling
    if not _authorized(environ, db):
        error = ""
        if environ.get("REQUEST_METHOD") == "POST":
            length = int(environ.get("CONTENT_LENGTH") or 0)
            form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
            password = form.get("password", [""])[0]
            expected = _get_active_password(db)
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

    # Parse Queries & Body
    query = parse_qs(environ.get("QUERY_STRING", ""))

    # WEALTH: account and double-entry ledger operations
    if path.endswith("/wealth/account/save") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        if form.get("csrf_token", [""])[0] != _wealth_csrf(db):
            start_response("403 Forbidden", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"CSRF token tidak valid"]
        try:
            opening_date = date.fromisoformat(form.get("opening_balance_date", [date.today().isoformat()])[0])
            name = form.get("name", [""])[0].strip()
            if not name:
                raise WealthError("Nama akun wajib diisi")
            opening = parse_idr_amount(form.get("opening_balance", ["0"])[0]) if form.get("opening_balance", ["0"])[0].strip() else 0
            db.create_account(FinancialAccount(None, chat_id, name, form.get("account_type", ["bank"])[0], form.get("provider", [""])[0], form.get("holder_name", [""])[0], form.get("account_identifier", [""])[0], "IDR", opening, opening_date))
            start_response("303 See Other", [("Location", "/keuangan/wealth?toast=account_saved")])
        except (ValueError, WealthError) as exc:
            start_response("303 See Other", [("Location", f"/keuangan/wealth?toast=wealth_error&detail={quote_plus(str(exc)[:140])}")])
        return [b""]

    if path.endswith("/wealth/operation/create") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        if form.get("csrf_token", [""])[0] != _wealth_csrf(db):
            start_response("403 Forbidden", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"CSRF token tidak valid"]
        try:
            amount = parse_idr_amount(form.get("amount", ["0"])[0])
            kind = form.get("operation_type", ["expense"])[0]
            source = int(form.get("source_account_id", ["0"])[0])
            destination_raw = form.get("destination_account_id", [""])[0]
            destination = int(destination_raw) if destination_raw.isdigit() else None
            description = form.get("description", ["Mutasi manual"])[0].strip()
            ledger = WealthLedger(db)
            actor = "web"
            if kind == "expense":
                ledger.create_expense(chat_id, source, amount, description, "Lain-lain", date.today(), actor, "Admin", idempotency_key=hashlib.sha256((str(form) + str(environ.get("HTTP_COOKIE", ""))).encode()).hexdigest())
            else:
                if not destination:
                    raise WealthError("Akun tujuan wajib dipilih")
                ledger.create_transfer(chat_id, source, destination, amount, description, date.today(), actor, "Admin", operation_type=kind, idempotency_key=hashlib.sha256((str(form) + str(environ.get("HTTP_COOKIE", ""))).encode()).hexdigest())
            start_response("303 See Other", [("Location", "/keuangan/wealth?toast=operation_saved")])
        except (ValueError, WealthError, InsufficientFundsError) as exc:
            start_response("303 See Other", [("Location", f"/keuangan/wealth?toast=wealth_error&detail={quote_plus(str(exc)[:140])}")])
        return [b""]

    if path.endswith("/wealth/account/archive") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        if form.get("csrf_token", [""])[0] != _wealth_csrf(db):
            start_response("403 Forbidden", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"CSRF token tidak valid"]
        try:
            WealthLedger(db).archive_account(chat_id, int(form.get("account_id", ["0"])[0]), "web")
            start_response("303 See Other", [("Location", "/keuangan/wealth?toast=account_archived")])
        except (ValueError, WealthError) as exc:
            start_response("303 See Other", [("Location", f"/keuangan/wealth?toast=wealth_error&detail={quote_plus(str(exc)[:140])}")])
        return [b""]

    if path.endswith("/wealth/reconcile") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        if form.get("csrf_token", [""])[0] != _wealth_csrf(db):
            start_response("403 Forbidden", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"CSRF token tidak valid"]
        try:
            actual = parse_idr_amount(form.get("actual_balance", ["0"])[0], allow_zero=True)
            WealthLedger(db).reconcile_account(chat_id, int(form.get("account_id", ["0"])[0]), actual, form.get("reason", ["Rekonsiliasi saldo"])[0], date.today(), "web", "Admin")
            start_response("303 See Other", [("Location", "/keuangan/wealth?toast=reconciled")])
        except (ValueError, WealthError) as exc:
            start_response("303 See Other", [("Location", f"/keuangan/wealth?toast=wealth_error&detail={quote_plus(str(exc)[:140])}")])
        return [b""]

    if path.endswith("/wealth/operation/reverse") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        if form.get("csrf_token", [""])[0] != _wealth_csrf(db):
            start_response("403 Forbidden", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"CSRF token tidak valid"]
        try:
            WealthLedger(db).reverse_operation(chat_id, form.get("operation_id", [""])[0], "web", form.get("reason", ["Koreksi manual"])[0])
            start_response("303 See Other", [("Location", "/keuangan/wealth?toast=reversed")])
        except (ValueError, WealthError) as exc:
            start_response("303 See Other", [("Location", f"/keuangan/wealth?toast=wealth_error&detail={quote_plus(str(exc)[:140])}")])
        return [b""]

    if path.endswith("/wealth/default/save") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        if form.get("csrf_token", [""])[0] != _wealth_csrf(db):
            start_response("403 Forbidden", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"CSRF token tidak valid"]
        try:
            WealthLedger(db).set_default_account(chat_id, form.get("operation_kind", ["expense"])[0], int(form.get("account_id", ["0"])[0]))
            start_response("303 See Other", [("Location", "/keuangan/wealth?toast=default_saved")])
        except (ValueError, WealthError) as exc:
            start_response("303 See Other", [("Location", f"/keuangan/wealth?toast=wealth_error&detail={quote_plus(str(exc)[:140])}")])
        return [b""]

    # SETTINGS: Category Save (Create / Update)
    if path.endswith("/settings/category/save") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        name = form.get("name", [""])[0].strip()
        old_name = form.get("old_name", [""])[0].strip()
        emoji = form.get("emoji", ["📁"])[0].strip() or "📁"
        keywords_raw = form.get("keywords", [""])[0]
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        tx_type = form.get("type", ["expense"])[0]
        if name:
            if old_name and old_name != name and old_name != "Lain-lain":
                db.rename_category_transactions(old_name, name)
                db.delete_category(old_name)
            db.upsert_category(Category(name, keywords, emoji, tx_type))
            start_response("303 See Other", [("Location", "/keuangan/settings?tab=categories&toast=cat_saved")])
            return [b""]
        start_response("303 See Other", [("Location", "/keuangan/settings?tab=categories&toast=cat_err")])
        return [b""]

    # SETTINGS: Category Delete
    if path.endswith("/settings/category/delete") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        name = form.get("name", [""])[0].strip()
        if name == "Lain-lain":
            start_response("303 See Other", [("Location", "/keuangan/settings?tab=categories&toast=cat_err_protected")])
            return [b""]
        if name:
            db.rename_category_transactions(name, "Lain-lain")
            db.delete_category(name)
            start_response("303 See Other", [("Location", "/keuangan/settings?tab=categories&toast=cat_deleted")])
            return [b""]

    # SETTINGS: Gemini Save
    if path.endswith("/settings/gemini/save") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        raw_keys_input = form.get("gemini_api_keys", [""])[0].strip()
        # Clean multi-input (support newline and comma separated)
        parsed_keys = [k.strip() for k in raw_keys_input.replace("\r", "\n").replace(",", "\n").split("\n") if k.strip()]
        keys = ",".join(dict.fromkeys(parsed_keys))
        model = form.get("gemini_model", ["gemini-3.8-flash"])[0].strip() or "gemini-3.8-flash"
        db.set_setting("gemini_api_keys", keys)
        db.set_setting("gemini_model", model)
        os.environ["GEMINI_API_KEYS"] = keys
        os.environ["GEMINI_MODEL"] = model
        _update_env_file("GEMINI_API_KEYS", keys)
        _update_env_file("GEMINI_MODEL", model)
        start_response("303 See Other", [("Location", "/keuangan/settings?tab=gemini&toast=gemini_saved")])
        return [b""]

    # SETTINGS: Gemini Test Connection
    if path.endswith("/settings/gemini/test") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        raw_keys_input = form.get("gemini_api_keys", [""])[0].strip()
        parsed_keys = [k.strip() for k in raw_keys_input.replace("\r", "\n").replace(",", "\n").split("\n") if k.strip()]
        keys = ",".join(dict.fromkeys(parsed_keys))
        model = form.get("gemini_model", ["gemini-3.8-flash"])[0].strip() or "gemini-3.8-flash"
        if not keys:
            start_response("303 See Other", [("Location", "/keuangan/settings?tab=gemini&toast=gemini_err_empty")])
            return [b""]
        ok, msg = _test_gemini_connection(keys, model)
        if ok:
            start_response("303 See Other", [("Location", "/keuangan/settings?tab=gemini&toast=gemini_test_ok")])
            return [b""]
        start_response("303 See Other", [("Location", f"/keuangan/settings?tab=gemini&toast=gemini_test_fail&err_msg={quote_plus(msg[:120])}")])
        return [b""]

    # SETTINGS: Password Change
    if path.endswith("/settings/password/save") and environ.get("REQUEST_METHOD") == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        form = parse_qs(environ["wsgi.input"].read(length).decode("utf-8", "replace"))
        cur_pwd = form.get("current_password", [""])[0]
        new_pwd = form.get("new_password", [""])[0]
        conf_pwd = form.get("confirm_password", [""])[0]
        active_pwd = _get_active_password(db)
        if cur_pwd != active_pwd:
            start_response("303 See Other", [("Location", "/keuangan/settings?tab=security&toast=pwd_err_current")])
            return [b""]
        if len(new_pwd) < 6 or new_pwd != conf_pwd:
            start_response("303 See Other", [("Location", "/keuangan/settings?tab=security&toast=pwd_err_match")])
            return [b""]
        db.set_setting("web_password", new_pwd)
        os.environ["WEB_PASSWORD"] = new_pwd
        _update_env_file("WEB_PASSWORD", new_pwd)
        new_cookie = hashlib.sha256(new_pwd.encode()).hexdigest()
        is_https = environ.get("wsgi.url_scheme") == "https" or environ.get("HTTP_X_FORWARDED_PROTO") == "https"
        sec_flag = " Secure;" if is_https else ""
        start_response(
            "303 See Other",
            [
                ("Location", "/keuangan/settings?tab=security&toast=pwd_saved"),
                ("Set-Cookie", f"ff_session={new_cookie}; Path=/; HttpOnly;{sec_flag} SameSite=Lax"),
            ],
        )
        return [b""]

    # SETTINGS: Telegram bot process controls
    if path.endswith("/settings/bot/start") and environ.get("REQUEST_METHOD") == "POST":
        status = BotController(os.path.dirname(os.path.abspath(__file__))).start()
        toast = "bot_started" if status.running else "bot_error"
        start_response("303 See Other", [("Location", f"/keuangan/settings?tab=system&toast={toast}")])
        return [b""]

    if path.endswith("/settings/bot/stop") and environ.get("REQUEST_METHOD") == "POST":
        status = BotController(os.path.dirname(os.path.abspath(__file__))).stop()
        toast = "bot_stopped" if not status.running else "bot_error"
        start_response("303 See Other", [("Location", f"/keuangan/settings?tab=system&toast={toast}")])
        return [b""]

    if path.endswith("/settings/bot/restart") and environ.get("REQUEST_METHOD") == "POST":
        status = BotController(os.path.dirname(os.path.abspath(__file__))).restart()
        toast = "bot_started" if status.running else "bot_error"
        start_response("303 See Other", [("Location", f"/keuangan/settings?tab=system&toast={toast}")])
        return [b""]

    # SETTINGS: System Update via Git Pull (VPS / Server Auto-Update)
    if path.endswith("/settings/system/update") and environ.get("REQUEST_METHOD") == "POST":
        output_lines = []
        is_success = False
        try:
            pull_res = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True, timeout=30)
            out = (pull_res.stdout or "").strip() or (pull_res.stderr or "").strip()
            output_lines.append(out)
            if pull_res.returncode == 0:
                is_success = True
            else:
                fallback_res = subprocess.run(["git", "pull"], capture_output=True, text=True, timeout=30)
                fb_out = (fallback_res.stdout or "").strip() or (fallback_res.stderr or "").strip()
                if fallback_res.returncode == 0:
                    is_success = True
                    output_lines.append(fb_out)
                else:
                    output_lines.append(f"Exit code: {pull_res.returncode}")

            # Touch tmp/restart.txt to reload Passenger WSGI on VPS/hosting
            try:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                tmp_dir = os.path.join(base_dir, "tmp")
                os.makedirs(tmp_dir, exist_ok=True)
                with open(os.path.join(tmp_dir, "restart.txt"), "w") as rf:
                    rf.write(str(time.time()))
            except Exception:
                pass

            # Recompile python bytecode
            try:
                import compileall
                compileall.compile_dir(os.path.dirname(os.path.abspath(__file__)), force=False, quiet=1)
            except Exception:
                pass

        except Exception as exc:
            output_lines.append(f"Error: {exc}")

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"{now_str} — {' '.join(output_lines)}"
        db.set_setting("last_git_update", log_entry)

        toast_val = "git_success" if is_success else "git_error"
        msg = quote_plus(" ".join(output_lines)[:160])
        start_response("303 See Other", [("Location", f"/keuangan/settings?tab=system&toast={toast_val}&detail={msg}")])
        return [b""]

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

    # Parse Toast Notifications
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
    elif toast_type == "cat_saved":
        toast_html = f"""<div class="toast toast-success" id="main-toast">
          <div style="color: var(--income-main);">{_svg_icon("check")}</div>
          <div style="flex: 1;">
            <div class="toast-title">Kategori Berhasil Disimpan</div>
            <div class="toast-msg">Pos kategori dan kata kunci parser otomatis berhasil diperbarui.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "cat_deleted":
        toast_html = f"""<div class="toast toast-success" id="main-toast">
          <div style="color: var(--income-main);">{_svg_icon("check")}</div>
          <div style="flex: 1;">
            <div class="toast-title">Kategori Berhasil Dihapus</div>
            <div class="toast-msg">Kategori telah dihapus dan seluruh transaksi terkait telah dialihkan ke 'Lain-lain'.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "cat_err_protected":
        toast_html = f"""<div class="toast toast-error" id="main-toast">
          <div style="flex: 1;">
            <div class="toast-title">Penghapusan Ditolak</div>
            <div class="toast-msg">Kategori 'Lain-lain' merupakan kategori bawaan sistem dan tidak dapat dihapus.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "gemini_saved":
        toast_html = f"""<div class="toast toast-success" id="main-toast">
          <div style="color: var(--income-main);">{_svg_icon("check")}</div>
          <div style="flex: 1;">
            <div class="toast-title">Konfigurasi Gemini Disimpan</div>
            <div class="toast-msg">Kunci API dan model Google Gemini AI berhasil diperbarui.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "gemini_test_ok":
        toast_html = f"""<div class="toast toast-success" id="main-toast">
          <div style="color: var(--income-main);">{_svg_icon("check")}</div>
          <div style="flex: 1;">
            <div class="toast-title">Pengujian Gemini AI Berhasil!</div>
            <div class="toast-msg">Koneksi ke Google Gemini AI aktif dan respons valid diterima.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "gemini_test_fail":
        err_detail = unquote_plus(query.get("err_msg", [""])[0])
        toast_html = f"""<div class="toast toast-error" id="main-toast">
          <div style="flex: 1;">
            <div class="toast-title">Pengujian Gemini AI Gagal</div>
            <div class="toast-msg">{html.escape(err_detail or 'Koneksi gagal. Periksa Kunci API Anda.')}</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "gemini_err_empty":
        toast_html = f"""<div class="toast toast-error" id="main-toast">
          <div style="flex: 1;">
            <div class="toast-title">Kunci API Belum Diisi</div>
            <div class="toast-msg">Silakan masukkan minimal satu Google Gemini API Key sebelum menguji.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "pwd_saved":
        toast_html = f"""<div class="toast toast-success" id="main-toast">
          <div style="color: var(--income-main);">{_svg_icon("check")}</div>
          <div style="flex: 1;">
            <div class="toast-title">Kata Sandi Berhasil Diperbarui</div>
            <div class="toast-msg">Kata sandi akses dasbor telah berhasil diganti dan sesi aktif diperbarui.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "pwd_err_current":
        toast_html = f"""<div class="toast toast-error" id="main-toast">
          <div style="flex: 1;">
            <div class="toast-title">Gagal Mengubah Kata Sandi</div>
            <div class="toast-msg">Kata sandi saat ini yang Anda masukkan tidak cocok.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "pwd_err_match":
        toast_html = f"""<div class="toast toast-error" id="main-toast">
          <div style="flex: 1;">
            <div class="toast-title">Konfirmasi Kata Sandi Tidak Sesuai</div>
            <div class="toast-msg">Kata sandi baru dan konfirmasi harus cocok, serta minimal 6 karakter.</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "git_success":
        detail = unquote_plus(query.get("detail", [""])[0])
        toast_html = f"""<div class="toast toast-success" id="main-toast">
          <div style="color: var(--income-main);">{_svg_icon("check")}</div>
          <div style="flex: 1;">
            <div class="toast-title">Pembaruan Kode Sumber Berhasil</div>
            <div class="toast-msg">{html.escape(detail or 'Sistem telah ditarik dari GitHub dan server dimuat ulang.')}</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "git_error":
        detail = unquote_plus(query.get("detail", [""])[0])
        toast_html = f"""<div class="toast toast-error" id="main-toast">
          <div style="flex: 1;">
            <div class="toast-title">Pembaruan Sistem Gagal</div>
            <div class="toast-msg">{html.escape(detail or 'Terjadi kendala saat menjalankan perintah git pull.')}</div>
          </div>
          <button class="toast-close" onclick="dismissToast('main-toast')">&times;</button>
        </div>"""
    elif toast_type == "bot_started":
        toast_html = '<div class="toast toast-success" id="main-toast"><div class="toast-title">Bot Telegram Aktif</div><div class="toast-msg">Bot sudah dinyalakan dan siap membaca pesan grup.</div><button class="toast-close" onclick="dismissToast(\'main-toast\')">&times;</button></div>'
    elif toast_type == "bot_stopped":
        toast_html = '<div class="toast toast-success" id="main-toast"><div class="toast-title">Bot Telegram Dimatikan</div><div class="toast-msg">Bot tidak akan memproses pesan baru sampai dinyalakan kembali.</div><button class="toast-close" onclick="dismissToast(\'main-toast\')">&times;</button></div>'
    elif toast_type == "bot_error":
        toast_html = '<div class="toast toast-error" id="main-toast"><div class="toast-title">Kontrol Bot Gagal</div><div class="toast-msg">Proses bot belum berhasil dikendalikan. Buka tab Info Sistem untuk melihat statusnya.</div><button class="toast-close" onclick="dismissToast(\'main-toast\')">&times;</button></div>'

    # ROUTE: SETTINGS PAGE
    if path.endswith("/wealth"):
        toast_type = query.get("toast", [""])[0]
        if toast_type == "account_saved":
            toast_html = '<div class="toast toast-success" id="main-toast"><div class="toast-title">Akun Berhasil Disimpan</div><div class="toast-msg">Saldo awal dan identitas akun telah masuk ke Wealth Center.</div></div>'
        elif toast_type == "operation_saved":
            toast_html = '<div class="toast toast-success" id="main-toast"><div class="toast-title">Mutasi Berhasil Dicatat</div><div class="toast-msg">Saldo akun dan total kekayaan telah diperbarui.</div></div>'
        elif toast_type == "account_archived":
            toast_html = '<div class="toast toast-success" id="main-toast"><div class="toast-title">Akun Diarsipkan</div><div class="toast-msg">Akun tidak muncul sebagai sumber baru, tetapi histori tetap tersimpan.</div></div>'
        elif toast_type == "reconciled":
            toast_html = '<div class="toast toast-success" id="main-toast"><div class="toast-title">Rekonsiliasi Tersimpan</div><div class="toast-msg">Selisih saldo dicatat sebagai adjustment yang dapat diaudit.</div></div>'
        elif toast_type == "reversed":
            toast_html = '<div class="toast toast-success" id="main-toast"><div class="toast-title">Operasi Dibatalkan</div><div class="toast-msg">Reversal tercatat tanpa menghapus histori asli.</div></div>'
        elif toast_type == "default_saved":
            toast_html = '<div class="toast toast-success" id="main-toast"><div class="toast-title">Sumber Default Disimpan</div><div class="toast-msg">Input cepat Telegram sekarang memakai akun default tersebut.</div></div>'
        elif toast_type == "wealth_error":
            toast_html = f'<div class="toast toast-error" id="main-toast"><div class="toast-title">Mutasi Ditolak</div><div class="toast-msg">{html.escape(query.get("detail", ["Periksa data input."])[0])}</div></div>'
        body = _render_wealth_page(db, chat_id, _wealth_csrf(db), toast_html)
        status, headers, payload = _html_page("Total Kekayaan — Finance Family", body)
        start_response(status, headers)
        return payload

    if path.endswith("/settings"):
        active_tab = query.get("tab", ["categories"])[0]
        if active_tab not in ("categories", "gemini", "security", "system"):
            active_tab = "categories"
        body = _render_settings_page(db, settings, active_tab, toast_html)
        status, headers, payload = _html_page("Pengaturan Sistem — Finance Family", body)
        start_response(status, headers)
        return payload

    # ROUTE: DASHBOARD PAGE & FILTERS
    try:
        filters, period = _filters(query, chat_id)
    except ValueError as exc:
        filters, period = TransactionFilters(chat_id), "month"

    rows = db.list_transactions(filters)
    income, expense, categories, users, cat_counts, user_counts = _summary(rows)
    balance = income - expense
    savings_rate = round(((income - expense) / income) * 100, 1) if income > 0 else (0.0 if expense > 0 else 100.0)
    summary_data = {"income": income, "expense": expense, "savings_rate": savings_rate}

    # EXPORT: EXCEL (.xlsx)
    if path.endswith(("/export.xlsx", "/export.excel")):
        xlsx_bytes = generate_excel(rows, summary_data, period)
        start_response(
            "200 OK",
            [
                ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                ("Content-Disposition", f'attachment; filename="laporan_keuangan_family_{period}_{date.today().isoformat()}.xlsx"'),
                ("Content-Length", str(len(xlsx_bytes))),
            ],
        )
        return [xlsx_bytes]

    # EXPORT: PDF STANDALONE LAPORAN
    if path.endswith("/export.pdf"):
        pdf_bytes = generate_pdf(rows, summary_data, period)
        start_response(
            "200 OK",
            [
                ("Content-Type", "application/pdf"),
                ("Content-Disposition", f'attachment; filename="laporan_keuangan_family_{period}_{date.today().isoformat()}.pdf"'),
                ("Content-Length", str(len(pdf_bytes))),
            ],
        )
        return [pdf_bytes]

    # Legacy CSV Export Route
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
    clean_params = {k: v[0] for k, v in query.items() if v and k not in ("toast", "imported", "import_err", "err_msg")}
    export_q = urlencode(clean_params)

    # Fullscreen Table View (Excel/Audit view)
    if path.endswith(("/excel", "/fullscreen")):
        body = f"""<main class="page-shell">
  <header class="topbar">
    <a class="brand-lockup" href="/keuangan/dashboard" title="Kembali ke Beranda (Home)">
      <div class="brand-mark">FF</div>
      <div class="brand-info">
        <span class="brand-badge"><span class="status-dot"></span>Buku Besar Lengkap</span>
        <h1 class="brand-title">Daftar Audit Transaksi Keuangan</h1>
        <span class="brand-desc">Total {len(rows)} mutasi catatan transaksi terverifikasi</span>
      </div>
    </a>
    <div class="actions">
      <nav class="header-nav-menu">
        <a class="header-nav-link active" href="/keuangan/dashboard">{_svg_icon("layout-dashboard")} Dasbor</a>
        <a class="header-nav-link" href="/keuangan/wealth">{_svg_icon("wallet")} Kekayaan</a>
        <a class="header-nav-link" href="/keuangan/settings">{_svg_icon("settings")} Pengaturan</a>
      </nav>
      <a class="btn btn-primary" href="/keuangan/export.pdf?{export_q}">{_svg_icon("file-pdf")} Unduh PDF</a>
      <a class="btn btn-secondary" href="/keuangan/export.xlsx?{export_q}">{_svg_icon("download")} Unduh Excel (.xlsx)</a>
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
  {CREDIT_HTML}
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
        "hasData": bool(income > 0 or expense > 0),
    })

    # Main Dashboard Body
    body = f"""<div class="toast-container">{toast_html}</div>

<main class="page-shell">
  <!-- Top Navigation Bar -->
  <header class="topbar">
    <a class="brand-lockup" href="/keuangan/dashboard" title="Kembali ke Beranda (Home)">
      <div class="brand-mark">FF</div>
      <div class="brand-info">
        <span class="brand-badge"><span class="status-dot"></span>Sistem Manajemen Aktif</span>
        <h1 class="brand-title">Finance Family</h1>
        <span class="brand-desc">Sistem Manajemen & Pembukuan Finansial Keluarga Terpadu</span>
      </div>
    </a>
    <div class="actions">
      <nav class="header-nav-menu">
        <a class="header-nav-link active" href="/keuangan/dashboard">
          {_svg_icon("layout-dashboard")} Dasbor
        </a>
        <a class="header-nav-link" href="/keuangan/wealth">
          {_svg_icon("wallet")} Kekayaan
        </a>
        <a class="header-nav-link" href="/keuangan/settings">
          {_svg_icon("settings")} Pengaturan
        </a>
      </nav>
      <button class="btn btn-primary" type="button" onclick="openAddModal()">
        {_svg_icon("plus")} Catat Transaksi
      </button>
      <a class="btn btn-ghost" href="/keuangan/logout" title="Keluar dari sesi ini" onclick="return confirm('Keluar dari sesi dasbor keuangan?')">
        {_svg_icon("logout")}
      </a>
    </div>
  </header>

  <!-- Period Tabs & Action Toolbar -->
  <div class="period-nav-wrapper">
    <div style="display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
      <nav class="period-tabs">
        {period_tabs_html}
      </nav>
      {custom_date_form}
    </div>
    <div class="period-toolbar-actions">
      <button class="btn btn-secondary" type="button" onclick="openImportModal()">
        {_svg_icon("upload")} Impor Berkas
      </button>
      <a class="btn btn-primary" href="/keuangan/export.pdf?{export_q}">
        {_svg_icon("file-pdf")} Ekspor PDF
      </a>
      <a class="btn btn-secondary" href="/keuangan/export.xlsx?{export_q}">
        {_svg_icon("download")} Ekspor Excel
      </a>
    </div>
  </div>

  <!-- Advanced Filters Panel -->
  {filter_form_html}

  <!-- Executive Financial KPI Metric Cards -->
  <section class="metric-grid">
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

  <!-- Transaction Data Ledger Panel (Moved directly below summary metrics for quick access) -->
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

  {CREDIT_HTML}
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

<!-- Modal: Impor Berkas -->
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

<script id="chart-data" type="application/json">{chart_json_data}</script>

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

window.addEventListener('DOMContentLoaded', () => {{
  try {{
    const rawData = JSON.parse(document.getElementById('chart-data').textContent);
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
        "/wealth",
        "/wealth/account/save",
        "/wealth/account/archive",
        "/wealth/operation/create",
        "/wealth/operation/reverse",
        "/wealth/default/save",
        "/wealth/reconcile",
        "/settings",
        "/settings/category/save",
        "/settings/category/delete",
        "/settings/gemini/save",
        "/settings/gemini/test",
        "/settings/password/save",
        "/settings/system/update",
        "/settings/bot/start",
        "/settings/bot/stop",
        "/settings/bot/restart",
        "/excel",
        "/fullscreen",
        "/export.xlsx",
        "/export.excel",
        "/export.pdf",
        "/export.csv",
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
        payload = b"family-finance bot is online"
        start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(payload)))])
        return [payload]

    # Process Telegram Webhook Updates
    chat_id = ""
    try:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        raw_body = environ["wsgi.input"].read(length) or b"{}"
        update = json.loads(raw_body)
        settings = load_settings()
        db = Database(settings.database_path)
        db.initialize()

        # 1. Handle Callback Query (Inline Buttons: Undo, Rekap, dll)
        if "callback_query" in update:
            cq = update["callback_query"]
            cq_id = str(cq.get("id", ""))
            _answer_callback_query(cq_id)
            cq_data = cq.get("data", "")
            msg = cq.get("message") or {}
            chat_id = str(msg.get("chat", {}).get("id", ""))
            sender = cq.get("from") or {}
            user_id = str(sender.get("id", ""))
            now = datetime.now()

            if chat_id in settings.allowed_chat_ids:
                if cq_data.startswith("cb:undo:"):
                    target_id = cq_data.split("cb:undo:")[-1]
                    if target_id == "last":
                        tx = db.find_latest_transaction(user_id, chat_id, now)
                        if tx and db.delete_transaction(tx.id, user_id, chat_id):
                            _send_telegram(chat_id, f"🗑️ *Catatan mutasi #{tx.id} ({tx.description}) berhasil dibatalkan.*")
                        else:
                            _send_telegram(chat_id, "❓ Tidak ada catatan mutasi milik Anda dalam 5 menit terakhir untuk dibatalkan.")
                    else:
                        try:
                            tx_id = int(target_id)
                            tx = db.get_transaction(tx_id)
                            if tx and db.delete_transaction_web(tx_id, chat_id):
                                _send_telegram(chat_id, f"🗑️ *Catatan mutasi #{tx_id} ({tx.description} — {format_rupiah(tx.amount)}) berhasil dibatalkan.*")
                            else:
                                _send_telegram(chat_id, "❓ Catatan transaksi telah dihapus sebelumnya.")
                        except ValueError:
                            pass
                elif cq_data == "cb:rekap:bulan":
                    _send_telegram(chat_id, build_report(db, "bulan", chat_id, now))
                elif cq_data == "cb:rekap:minggu":
                    _send_telegram(chat_id, build_report(db, "minggu", chat_id, now))
                elif cq_data == "cb:income:bulan":
                    _send_telegram(chat_id, build_income_summary(db, chat_id, now, "bulan"))
                elif cq_data == "cb:expense:bulan":
                    _send_telegram(chat_id, build_expense_summary(db, chat_id, now, "bulan"))
                elif cq_data == "cb:kategori":
                    cats = db.list_categories()
                    lines = ["🏷️ *KATEGORI TRANSAKSI KELUARGA*", "━━━━━━━━━━━━━━━━━━━━━━"] + [f"• {c.emoji} *{c.name}*" for c in cats] + ["━━━━━━━━━━━━━━━━━━━━━━", "✨ _ziqva.com team @2026_"]
                    _send_telegram(chat_id, "\n".join(lines))
                elif cq_data == "cb:bantuan":
                    _send_telegram(chat_id, HELP_TEXT)

            start_response("200 OK", [("Content-Type", "application/json")])
            return [b'{"ok":true}']

        # 2. Handle Text & Photo Messages
        message = update.get("message") or {}
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        text = (message.get("text") or "").strip()
        chat_id = str(chat.get("id", ""))
        user_id = str(sender.get("id", ""))
        uname = sender.get("username") or sender.get("first_name") or "user"
        now = datetime.now()

        if chat_id in settings.allowed_chat_ids:
            # Menu / Start Command
            if text.startswith(("/start", "/menu", "/bantuan")):
                inline_keys = {
                    "inline_keyboard": [
                        [{"text": "📊 Rekap Bulan Ini", "callback_data": "cb:rekap:bulan"}, {"text": "💰 Saldo Kas", "callback_data": "cb:rekap:bulan"}],
                        [{"text": "📈 Total Pemasukan", "callback_data": "cb:income:bulan"}, {"text": "📉 Total Pengeluaran", "callback_data": "cb:expense:bulan"}],
                        [{"text": "📅 Rekap Pekan Ini", "callback_data": "cb:rekap:minggu"}, {"text": "🏷️ Daftar Kategori", "callback_data": "cb:kategori"}],
                        [{"text": "↩️ Undo Terakhir", "callback_data": "cb:undo:last"}, {"text": "❓ Panduan Bantuan", "callback_data": "cb:bantuan"}],
                    ]
                }
                welcome = f"👋 *Halo, @{uname.lstrip('@')}!*\nSelamat datang di *Finance Family*.\n\n" + HELP_TEXT
                _send_telegram(chat_id, welcome, reply_markup=inline_keys)

            # Income Summary Command
            elif text.startswith(("/pemasukan", "/masuk")):
                _send_telegram(chat_id, build_income_summary(db, chat_id, now, "bulan"))

            # Expense Summary Command
            elif text.startswith(("/pengeluaran", "/keluar")):
                _send_telegram(chat_id, build_expense_summary(db, chat_id, now, "bulan"))

            # Recap & Balance Command
            elif text and text.split()[0].split("@")[0] == "/akun":
                accounts = db.list_accounts(chat_id)
                if not accounts:
                    _send_telegram(chat_id, "🏦 Belum ada akun. Tambahkan melalui `/keuangan/wealth` di dasbor web.")
                else:
                    ledger = WealthLedger(db)
                    balances = {x.account_id: x for x in ledger.get_account_balances(chat_id, include_archived=False)}
                    lines = ["🏦 *AKUN KEUANGAN AKTIF*", "━━━━━━━━━━━━━━━━━━━━━━"]
                    for account in accounts:
                        ident = ("•••• " + account.account_identifier[-4:]) if len(account.account_identifier) > 4 else "—"
                        lines.append(f"• *{account.name}* (ID `{account.id}`)\n  {ident} · {format_rupiah(balances[account.id].balance)}")
                    _send_telegram(chat_id, "\n".join(lines))

            # Wealth summary command must be matched before /saldo legacy prefix.
            elif text and text.split()[0].split("@")[0] == "/saldoaset":
                summary = WealthLedger(db).get_wealth_summary(chat_id)
                _send_telegram(chat_id, f"💎 *TOTAL KEKAYAAN*\n━━━━━━━━━━━━━━━━━━━━━━\n• Total aset: *{format_rupiah(summary.total_wealth)}*\n• Aset likuid: *{format_rupiah(summary.liquid_assets)}*\n• Investasi: *{format_rupiah(summary.investments)}*\n• Cash: *{format_rupiah(summary.cash)}*")

            elif text and text.split()[0].split("@")[0] == "/transfer":
                parts = text.split()
                try:
                    if len(parts) < 4:
                        raise ValueError("Format: /transfer <dari_id> <ke_id> <nominal> <keterangan>")
                    amount = int(parts[3].replace(".", "").replace(",", "").replace("Rp", ""))
                    WealthLedger(db).create_transfer(chat_id, int(parts[1]), int(parts[2]), amount, " ".join(parts[4:]) or "Transfer", now.date(), user_id, uname, idempotency_key=f"webhook:{update.get('update_id')}")
                    _send_telegram(chat_id, f"✅ Transfer {format_rupiah(amount)} berhasil dicatat.")
                except (ValueError, WealthError, InsufficientFundsError) as exc:
                    _send_telegram(chat_id, f"❌ Transfer ditolak: {exc}")

            elif text.startswith(("/rekap", "/saldo")):
                _send_telegram(chat_id, build_report(db, "bulan", chat_id, now))

            # Periodic Report Command
            elif text.startswith(("/laporan", "/hari", "/minggu", "/bulan", "/tahun", "/all", "/semua")):
                parts = text.split()
                cmd = parts[0].lstrip("/")
                kind = parts[1] if len(parts) > 1 else (cmd if cmd in ("hari", "minggu", "bulan", "tahun", "all") else "bulan")
                _send_telegram(chat_id, build_report(db, kind, chat_id, now))

            # Undo Command
            elif text.startswith("/undo"):
                tx = db.find_latest_transaction(user_id, chat_id, now)
                if tx and db.delete_transaction(tx.id, user_id, chat_id):
                    _send_telegram(chat_id, f"✅ *Catatan Terakhir Dibatalkan*\nTransaksi #{tx.id} ({tx.description} — {format_rupiah(tx.amount)}) telah dihapus dari pembukuan.")
                else:
                    _send_telegram(chat_id, "❓ Tidak ditemukan catatan mutasi milik Anda dalam 5 menit terakhir untuk dibatalkan.")

            # Delete Command
            elif text.startswith("/hapus"):
                parts = text.split()
                if len(parts) > 1 and parts[1].replace("#", "").isdigit():
                    tx_id = int(parts[1].replace("#", ""))
                    tx = db.get_transaction(tx_id)
                    if tx and (tx.user_id == user_id or str(tx.chat_id) == chat_id):
                        db.delete_transaction_web(tx_id, chat_id)
                        _send_telegram(chat_id, f"✅ *Catatan Mutasi Dihapus*\nTransaksi #{tx_id} ({tx.description} — {format_rupiah(tx.amount)}) berhasil dihapus dari sistem.")
                    else:
                        _send_telegram(chat_id, "❓ Catatan transaksi tidak ditemukan atau bukan bagian dari grup ini.")
                else:
                    _send_telegram(chat_id, "Format: `/hapus <ID_TRANSAKSI>`\nContoh: `/hapus 42`")

            # Edit Command
            elif text.startswith("/edit"):
                parts = text.split()
                if len(parts) >= 4 and parts[1].replace("#", "").isdigit():
                    tx_id = int(parts[1].replace("#", ""))
                    field = parts[2].lower()
                    val = " ".join(parts[3:])
                    changes = {}
                    if field in ("nominal", "amount"):
                        try:
                            changes["amount"] = int(val.replace(".", "").replace(",", "").replace("Rp", "").strip())
                        except ValueError:
                            _send_telegram(chat_id, "Nominal harus berupa angka valid.")
                            parts = []
                    elif field in ("deskripsi", "description"):
                        changes["description"] = val
                    elif field in ("kategori", "category"):
                        changes["category"] = val
                    if changes:
                        ok = db.update_transaction(tx_id, user_id, chat_id, **changes) or db.update_transaction(tx_id, "web", chat_id, **changes)
                        if ok:
                            _send_telegram(chat_id, f"✅ *Catatan #{tx_id} Berhasil Diperbarui.*")
                        else:
                            _send_telegram(chat_id, "❓ Catatan transaksi tidak ditemukan atau bukan milik Anda.")
                else:
                    _send_telegram(chat_id, "Format: `/edit <ID> nominal|deskripsi|kategori <nilai>`")

            # Categories Command
            elif text.startswith("/kategori"):
                cats = db.list_categories()
                lines = ["🏷️ *DAFTAR KATEGORI TRANSAKSI AKTIF*", "━━━━━━━━━━━━━━━━━━━━━━"]
                for c in cats:
                    lines.append(f"• {c.emoji} *{c.name}*")
                lines.append("━━━━━━━━━━━━━━━━━━━━━━\n✨ _ziqva.com team with love family @2026_")
                _send_telegram(chat_id, "\n".join(lines))

            # Natural Language Transaction
            elif text and not text.startswith("/"):
                parsed = parse_message(text, now, settings.timezone)
                category = categorize(parsed.description, db.list_categories())
                wealth_ledger = WealthLedger(db)
                wealth_account = wealth_ledger.get_default_account(chat_id, parsed.type)
                if wealth_account:
                    try:
                        if parsed.type == "income":
                            op = wealth_ledger.create_income(chat_id, wealth_account.id, parsed.amount, parsed.description, category.name, parsed.transaction_date, user_id, uname, idempotency_key=f"webhook:{update.get('update_id')}")
                        else:
                            op = wealth_ledger.create_expense(chat_id, wealth_account.id, parsed.amount, parsed.description, category.name, parsed.transaction_date, user_id, uname, idempotency_key=f"webhook:{update.get('update_id')}")
                        summary = wealth_ledger.get_wealth_summary(chat_id)
                        _send_telegram(chat_id, f"✅ *Mutasi tercatat dari {wealth_account.name}*\n{parsed.description}: *{format_rupiah(parsed.amount)}*\nSaldo total tercatat: *{format_rupiah(summary.total_wealth)}*\nRef: `{op.id[:10]}`")
                        start_response("200 OK", [("Content-Type", "application/json")])
                        return [b'{"ok":true}']
                    except (WealthError, InsufficientFundsError) as exc:
                        _send_telegram(chat_id, f"❌ Mutasi ditolak: {exc}. Sumber dana default: {wealth_account.name}.")
                        start_response("200 OK", [("Content-Type", "application/json")])
                        return [b'{"ok":true}']
                tx = db.add_transaction(
                    Transaction(
                        None,
                        user_id,
                        uname,
                        chat_id,
                        parsed.type,
                        parsed.amount,
                        parsed.description,
                        category.name,
                        parsed.transaction_date,
                        now,
                    )
                )

                # Month balance calculation
                m_start = now.date().replace(day=1)
                m_end = (m_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                m_rows = db.list_transactions(TransactionFilters(chat_id, m_start, m_end))
                m_inc = sum(r.amount for r in m_rows if r.type == "income")
                m_exp = sum(r.amount for r in m_rows if r.type == "expense")
                m_bal = m_inc - m_exp
                bal_note = f"Saldo Bulan Ini: *{format_rupiah(m_bal)}*" + (" (Surplus)" if m_bal > 0 else (" (Defisit)" if m_bal < 0 else ""))

                card = render_confirmation(tx, uname, bal_note)
                action_markup = {
                    "inline_keyboard": [
                        [
                            {"text": "↩️ Batalkan / Undo", "callback_data": f"cb:undo:{tx.id}"},
                            {"text": "📊 Rekap Saldo", "callback_data": "cb:rekap:bulan"},
                        ]
                    ]
                }
                _send_telegram(chat_id, card, reply_markup=action_markup)

        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"ok":true}']
    except ParseError as exc:
        if chat_id:
            _send_telegram(chat_id, f"❓ {exc}")
        start_response("200 OK", [("Content-Type", "application/json")])
        return [b'{"ok":true}']
    except Exception:
        start_response("500 Internal Server Error", [("Content-Type", "text/plain")])
        return [b"internal error"]
