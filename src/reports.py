"""Financial report generators for Telegram bot and exports.

Finance Family — Dibuat oleh effands ~ ziqva.com team with love family @2026.
"""
from datetime import date, datetime, timedelta
from .database import Database
from .formatting import format_rupiah, format_date_id
from .models import TransactionFilters

MONTHS = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
CREDIT_NOTE = "✨ Dibuat oleh effands ~ ziqva.com team with love family @2026"


def period(kind: str, now: datetime):
    kind = (kind or "bulan").strip().lower()
    if " " in kind:
        a, b = kind.split(" ", 1)
        return date.fromisoformat(a), date.fromisoformat(b), f"{a} s/d {b}"
    if kind in ("hari", "day", "today"):
        return now.date(), now.date(), f"Hari ini ({format_date_id(now.date())})"
    if kind in ("minggu", "week", "pekan"):
        start = now.date() - timedelta(days=now.weekday())
        end = start + timedelta(days=6)
        return start, end, f"Pekan Ini ({format_date_id(start)} - {format_date_id(end)})"
    if kind in ("bulan", "month"):
        start = now.date().replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        return start, end, f"{MONTHS[now.month - 1]} {now.year}"
    if kind in ("tahun", "year"):
        start = now.date().replace(month=1, day=1)
        end = now.date().replace(month=12, day=31)
        return start, end, f"Tahun {now.year}"
    if kind in ("all", "semua"):
        return None, None, "Semua Catatan Transaksi"
    if len(kind) == 7 and kind[4] == "-":
        y, m = map(int, kind.split("-"))
        start = date(y, m, 1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        return start, end, f"{MONTHS[m - 1]} {y}"
    raise ValueError("Format periode tidak dikenali. Gunakan: hari, minggu, bulan, tahun, all, atau YYYY-MM")


def build_income_summary(db: Database, chat_id: str, now: datetime, kind: str = "bulan") -> str:
    start, end, title = period(kind, now)
    fetch = getattr(db, "list_transactions_with_ledger", db.list_transactions)
    rows = fetch(TransactionFilters(chat_id, start, end, transaction_type="income", sort_by="transaction_date", sort_dir="desc"))
    total_income = sum(x.amount for x in rows)

    out = [
        "📈 *IKHTISAR PEMASUKAN KELUARGA*",
        f"📅 *Periode:* {title}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"💵 *Total Pemasukan :* *{format_rupiah(total_income)}*",
        f"🔢 *Banyak Mutasi   :* {len(rows)} transaksi",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if rows:
        out.append("*Riwayat Pemasukan Terakhir:*")
        for x in rows[:7]:
            user_label = f"@{x.username.lstrip('@')}" if x.username else "User"
            out.append(f"• `{format_date_id(x.transaction_date)}`: {x.description} — *{format_rupiah(x.amount)}* ({user_label})")
        if len(rows) > 7:
            out.append(f"_... dan {len(rows) - 7} transaksi lainnya di dasbor web._")
    else:
        out.append("Belum ada catatan pemasukan pada periode ini.")

    out.append("━━━━━━━━━━━━━━━━━━━━━━")
    out.append(CREDIT_NOTE)
    return "\n".join(out)


def build_expense_summary(db: Database, chat_id: str, now: datetime, kind: str = "bulan") -> str:
    start, end, title = period(kind, now)
    fetch = getattr(db, "list_transactions_with_ledger", db.list_transactions)
    rows = fetch(TransactionFilters(chat_id, start, end, transaction_type="expense", sort_by="transaction_date", sort_dir="desc"))
    total_expense = sum(x.amount for x in rows)

    cats = {}
    users = {}
    for x in rows:
        cats[x.category] = cats.get(x.category, 0) + x.amount
        uname = (x.username or x.user_id or "User").lstrip("@")
        users[uname] = users.get(uname, 0) + x.amount

    out = [
        "📉 *IKHTISAR PENGELUARAN KELUARGA*",
        f"📅 *Periode:* {title}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"💸 *Total Pengeluaran :* *{format_rupiah(total_expense)}*",
        f"🔢 *Banyak Transaksi   :* {len(rows)} transaksi",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if rows:
        out.append("*Riwayat Pengeluaran Terakhir:*")
        for x in rows[:7]:
            user_label = f"@{x.username.lstrip('@')}" if x.username else "User"
            out.append(f"• `{format_date_id(x.transaction_date)}`: {x.description} — *{format_rupiah(x.amount)}* ({user_label})")
        if len(rows) > 7:
            out.append(f"_... dan {len(rows) - 7} transaksi lainnya di dasbor web._")
        out.append("━━━━━━━━━━━━━━━━━━━━━━")

    if cats and total_expense > 0:
        out.append("*Distribusi Alokasi Belanja:*")
        for cat_name, amt in sorted(cats.items(), key=lambda z: -z[1]):
            pct = round((amt / total_expense) * 100, 1)
            out.append(f"• *{cat_name}*: {format_rupiah(amt)} ({pct}%)")
        out.append("━━━━━━━━━━━━━━━━━━━━━━")

    if users and total_expense > 0:
        out.append("*Kontribusi Anggota Keluarga:*")
        for uname, amt in sorted(users.items(), key=lambda z: -z[1]):
            pct = round((amt / total_expense) * 100, 1)
            out.append(f"• @{uname}: {format_rupiah(amt)} ({pct}%)")
        out.append("━━━━━━━━━━━━━━━━━━━━━━")

    if not rows:
        out.append("Belum ada catatan pengeluaran pada periode ini.")
        out.append("━━━━━━━━━━━━━━━━━━━━━━")

    out.append(CREDIT_NOTE)
    return "\n".join(out)


def build_report(db: Database, kind: str, chat_id: str, now: datetime, user_id=None) -> str:
    start, end, title = period(kind, now)
    fetch = getattr(db, "list_transactions_with_ledger", db.list_transactions)
    rows = fetch(TransactionFilters(chat_id, start, end, user_id))
    income = sum(x.amount for x in rows if x.type == "income")
    expense = sum(x.amount for x in rows if x.type == "expense")
    balance = income - expense
    savings_rate = round(((income - expense) / income) * 100, 1) if income > 0 else (0.0 if expense > 0 else 100.0)

    bal_status = "🟢 Surplus" if balance > 0 else ("🔴 Defisit" if balance < 0 else "⚪ Seimbang")

    out = [
        f"🏛️ *LAPORAN KEUANGAN KELUARGA*",
        f"📅 *Periode:* {title}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"🟢 *Total Pemasukan   :* *{format_rupiah(income)}*",
        f"🔴 *Total Pengeluaran :* *{format_rupiah(expense)}*",
        "──────────────────────",
        f"💎 *Arus Kas Bersih   :* *{format_rupiah(balance)}* ({bal_status})",
        f"📊 *Rasio Tabungan    :* {savings_rate}%",
        f"🧾 *Total Transaksi   :* {len(rows)} catatan",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]

    cats = {}
    for x in rows:
        if x.type == "expense":
            cats[x.category] = cats.get(x.category, 0) + x.amount

    if cats and expense > 0:
        out.append("*Distribusi Pengeluaran:*")
        for k, v in sorted(cats.items(), key=lambda z: -z[1]):
            pct = round((v * 100) / expense, 1)
            out.append(f"• {k}: {format_rupiah(v)} ({pct}%)")
        out.append("━━━━━━━━━━━━━━━━━━━━━━")

    users = {}
    for x in rows:
        if x.type == "expense":
            uname = (x.username or x.user_id or "user").lstrip("@")
            users[uname] = users.get(uname, 0) + x.amount

    if users and expense > 0:
        out.append("*Kontribusi Anggota:*")
        for k, v in sorted(users.items(), key=lambda z: -z[1]):
            pct = round((v * 100) / expense, 1)
            out.append(f"• @{k}: {format_rupiah(v)} ({pct}%)")
        out.append("━━━━━━━━━━━━━━━━━━━━━━")

    out.append(CREDIT_NOTE)
    return "\n".join(out)


def build_recap(db, kind, chat_id, now, user_id=None):
    return build_report(db, kind, chat_id, now, user_id)
