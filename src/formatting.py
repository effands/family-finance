"""Message formatting utilities for Telegram and web displays.

Finance Family — Dibuat oleh effands ~ ziqva.com team with love family @2026.
"""
from datetime import date
from .models import Transaction

BULAN_ID = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def format_rupiah(n: int) -> str:
    return f"Rp {n:,.0f}".replace(",", ".")


def format_date_id(d: date) -> str:
    if not d:
        return "-"
    return f"{d.day:02d} {BULAN_ID[d.month]} {d.year}"


def render_confirmation(x: Transaction, actor: str, balance_note: str = "") -> str:
    is_inc = x.type == "income"
    type_badge = "🟢 Pemasukan" if is_inc else "🔴 Pengeluaran"
    clean_actor = actor.lstrip("@")
    date_str = format_date_id(x.transaction_date)

    msg = [
        "✨ *MUTASI TRANSAKSI TERCATAT*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📌 *Jenis*     : {type_badge}",
        f"💰 *Nominal*   : *{format_rupiah(x.amount)}*",
        f"📝 *Deskripsi* : {x.description}",
        f"🏷️ *Kategori*  : {x.category}",
        f"📅 *Tanggal*   : {date_str}",
        f"👤 *Pencatat*  : @{clean_actor}",
        f"🆔 *ID Ref*    : `#{x.id}`",
        "━━━━━━━━━━━━━━━━━━━━━━",
    ]
    if balance_note:
        msg.append(f"📊 {balance_note}")
        msg.append("━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(msg)
