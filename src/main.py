"""Telegram Bot for Family Finance Management.

Finance Family — Dibuat oleh effands ~ ziqva.com team with love family @2026.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from .categorizer import categorize
from .config import load_settings
from .database import Database
from .formatting import format_rupiah, render_confirmation
from .models import Category, FinancialAccount, Transaction
from .parser import ParseError, parse_message
from .rate_limit import RateLimiter
from .receipt_ai import GeminiKeyPool, extract_receipt, interpret_text, transcribe_audio
from .reports import build_expense_summary, build_income_summary, build_report
from .wealth import WealthLedger, WealthError, InsufficientFundsError, parse_idr_amount
from .telegram_wealth import WealthTelegramMenu
from .intent import classify_finance_intent, account_request_summary, extract_account_fields

MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📊 Rekap Bulan Ini", "💰 Saldo Kas"],
        ["📈 Total Pemasukan", "📉 Total Pengeluaran"],
        ["📅 Rekap Pekan Ini", "🏷️ Kategori"],
        ["↩️ Undo Terakhir", "❓ Panduan & Menu"],
    ],
    resize_keyboard=True,
)

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
  _(Contoh: `/edit 42 nominal 30000`)_
• `/tambahkategori <Nama> <kata1,kata2>`
• `/hapuskategori <Nama>`

📸 *Analisa Struk Belanja:*
Kirimkan foto nota/struk belanja langsung ke grup ini untuk dianalisa otomatis oleh Gemini Vision AI.
━━━━━━━━━━━━━━━━━━━━━━
✨ _Dibuat oleh effands ~ ziqva.com team with love family @2026_"""


def allowed(update: Update, settings) -> bool:
    return str(update.effective_chat.id) in settings.allowed_chat_ids


def get_command_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Rekap Bulan Ini", callback_data="cb:rekap:bulan"),
            InlineKeyboardButton("💰 Saldo Kas", callback_data="cb:rekap:bulan"),
        ],
        [
            InlineKeyboardButton("📈 Total Pemasukan", callback_data="cb:income:bulan"),
            InlineKeyboardButton("📉 Total Pengeluaran", callback_data="cb:expense:bulan"),
        ],
        [
            InlineKeyboardButton("📅 Rekap Pekan Ini", callback_data="cb:rekap:minggu"),
            InlineKeyboardButton("🏷️ Daftar Kategori", callback_data="cb:kategori"),
        ],
        [
            InlineKeyboardButton("↩️ Undo Catatan Terakhir", callback_data="cb:undo:last"),
            InlineKeyboardButton("❓ Panduan Bantuan", callback_data="cb:bantuan"),
        ],
    ])


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    user = update.effective_user
    name = f"@{user.username}" if user.username else (user.first_name or "Keluarga")
    reply = context.application.bot_data["wealth_menu"].main_menu(str(update.effective_chat.id), str(user.id), f"👋 *Halo, {name}!*")
    await update.message.reply_text(reply.text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(reply.keyboard["inline_keyboard"]))


async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if context.user_data.get("receipt_editing"):
        pending = context.user_data.get("pending_receipt")
        if pending:
            try:
                corrected = parse_message(text, datetime.now(), context.application.bot_data["settings"].timezone)
                pending.update({"amount": corrected.amount, "description": corrected.description, "date": corrected.transaction_date.isoformat()})
                pending["category"] = categorize(corrected.description, context.application.bot_data["db"].list_categories()).name
                context.user_data.pop("receipt_editing", None)
                keys = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Simpan Mutasi", callback_data="receipt:save"), InlineKeyboardButton("✏️ Koreksi", callback_data="receipt:edit")], [InlineKeyboardButton("❌ Batalkan", callback_data="receipt:cancel")]])
                return await update.message.reply_text(f"✏️ *Struk diperbarui*\nTotal: *{format_rupiah(pending['amount'])}*\nDeskripsi: {pending['description']}\nKategori: {pending['category']}\n\nPeriksa lalu simpan.", parse_mode="Markdown", reply_markup=keys)
            except ParseError as exc:
                return await update.message.reply_text(f"❓ Koreksi belum terbaca: {exc}\nContoh: `45000 belanja rumah`", parse_mode="Markdown")
        context.user_data.pop("receipt_editing", None)
    guided = context.application.bot_data["wealth_menu"].handle_text(str(update.effective_chat.id), str(update.effective_user.id), text, str(update.update_id))
    if guided:
        return await update.message.reply_text(guided.text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(guided.keyboard["inline_keyboard"]))
    intent = classify_finance_intent(text)
    if intent == "account_add":
        menu = context.application.bot_data["wealth_menu"]
        reply = menu.begin_account_request(
            str(update.effective_chat.id),
            str(update.effective_user.id),
            extract_account_fields(text),
        )
        return await update.message.reply_text(
            f"🤖 Saya pahami Anda ingin menambahkan {account_request_summary(text)} sebagai akun keuangan baru.\n\n"
            "Kita isi datanya lewat tombol dan konfirmasi agar tidak salah mencatat sebagai pengeluaran.\n\n" + reply.text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(reply.keyboard["inline_keyboard"]),
        )
    if text in ("📊 Rekap Bulan Ini", "💰 Saldo Kas"):
        return await report_cmd(update, context, "bulan")
    if text == "📈 Total Pemasukan":
        return await income_cmd(update, context)
    if text == "📉 Total Pengeluaran":
        return await expense_cmd(update, context)
    if text == "📅 Rekap Pekan Ini":
        return await report_cmd(update, context, "minggu")
    if text == "🏷️ Kategori":
        return await categories_cmd(update, context)
    if text == "↩️ Undo Terakhir":
        return await undo_cmd(update, context)
    if text == "❓ Panduan & Menu":
        return await start_cmd(update, context)
    return await message_handler(update, context)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, text_override=None, reply_message=None):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    user = update.effective_user
    reply = reply_message or update.message
    chat_id = str(update.effective_chat.id)
    now = datetime.now()

    if not context.application.bot_data["limiter"].allow(str(user.id), now):
        return await reply.reply_text("⏳ Terlalu banyak pesan dalam waktu singkat. Mohon tunggu sebentar.")

    text = text_override if text_override is not None else update.message.text
    db: Database = context.application.bot_data["db"]
    ai_category = None
    should_use_ai = bool(s.gemini_api_keys and len(text or "") >= 80)
    try:
        if should_use_ai:
            raise ParseError("Pesan panjang akan dipahami oleh Gemini")
        parsed = parse_message(text, now, s.timezone)
    except ParseError as e:
        # Natural-language fallback/preferred path for longer messages.
        if (len(text or "") < 45 and not should_use_ai) or not s.gemini_api_keys:
            try:
                parsed = parse_message(text, now, s.timezone)
            except ParseError:
                return await reply.reply_text(f"❓ {e}")
        else:
            try:
                ai = await asyncio.to_thread(
                    interpret_text, text, [c.name for c in db.list_categories()],
                    s.gemini_api_keys, s.gemini_model, context.application.bot_data["gemini_pool"]
                )
                parsed = type("AIParsed", (), {
                    "type": ai["type"], "amount": ai["amount"], "description": ai["description"],
                    "transaction_date": date.fromisoformat(ai["date"]),
                })()
                ai_category = ai
            except Exception:
                if should_use_ai:
                    # A valid short-format interpretation is safer than rejecting a transaction.
                    try:
                        parsed = parse_message(text, now, s.timezone)
                    except ParseError:
                        return await reply.reply_text(f"❓ {e}\nCoba tulis nominal dengan format seperti `makan 25rb`, atau pastikan Gemini aktif.", parse_mode="Markdown")
                else:
                    return await reply.reply_text(f"❓ {e}\nCoba tulis nominal dengan format seperti `makan 25rb`, atau pastikan Gemini aktif.", parse_mode="Markdown")
    if ai_category:
        existing = {c.name.casefold(): c for c in db.list_categories()}
        safe_name = " ".join(ai_category["category"].split())[:80]
        safe_keywords = [" ".join(k.split())[:40] for k in ai_category.get("keywords", []) if k.strip()][:5]
        category = existing.get(safe_name.casefold())
        if category is None and safe_name.casefold() != "lain-lain" and safe_name:
            category = Category(safe_name, safe_keywords, "📁", ai_category["type"])
            db.upsert_category(category)
    else:
        category = categorize(parsed.description, db.list_categories())
    uname = user.username or user.first_name or "user"
    wealth_ledger = WealthLedger(db)
    wealth_account = wealth_ledger.get_default_account(chat_id, parsed.type, str(user.id))
    if wealth_account:
        try:
            if parsed.type == "income":
                op = wealth_ledger.create_income(chat_id, wealth_account.id, parsed.amount, parsed.description, category.name, parsed.transaction_date, str(user.id), uname, idempotency_key=f"tg:{update.update_id}")
            else:
                op = wealth_ledger.create_expense(chat_id, wealth_account.id, parsed.amount, parsed.description, category.name, parsed.transaction_date, str(user.id), uname, idempotency_key=f"tg:{update.update_id}")
            summary = wealth_ledger.get_wealth_summary(chat_id)
            return await reply.reply_text(
                f"✅ *Mutasi tercatat dari {wealth_account.name}*\n{parsed.description}: *{format_rupiah(parsed.amount)}*\n"
                f"Saldo total tercatat: *{format_rupiah(summary.total_wealth)}*\nRef: `{op.id[:10]}`",
                parse_mode="Markdown",
            )
        except (WealthError, InsufficientFundsError) as exc:
            return await reply.reply_text(f"❌ Mutasi ditolak: {exc}. Sumber dana default: {wealth_account.name}.")
    tx = db.add_transaction(
        Transaction(
            None,
            str(user.id),
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

    # Calculate month balance summary note
    m_start = now.date().replace(day=1)
    m_end = (m_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    from .models import TransactionFilters
    m_rows = db.list_transactions(TransactionFilters(chat_id, m_start, m_end))
    m_inc = sum(r.amount for r in m_rows if r.type == "income")
    m_exp = sum(r.amount for r in m_rows if r.type == "expense")
    m_bal = m_inc - m_exp
    bal_str = f"Saldo Bulan Ini: *{format_rupiah(m_bal)}*" + (" (Surplus)" if m_bal > 0 else (" (Defisit)" if m_bal < 0 else ""))

    card_text = render_confirmation(tx, uname, bal_str)
    action_keys = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("↩️ Batalkan / Undo", callback_data=f"cb:undo:{tx.id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"cb:edit:{tx.id}"),
            InlineKeyboardButton("🗑️ Hapus", callback_data=f"cb:delete:{tx.id}"),
            InlineKeyboardButton("📊 Rekap Saldo", callback_data="cb:rekap:bulan"),
        ]
    ])
    await reply.reply_text(card_text, parse_mode="Markdown", reply_markup=action_keys)


async def income_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    db = context.application.bot_data["db"]
    chat_id = str(update.effective_chat.id)
    text = build_income_summary(db, chat_id, datetime.now(), "bulan")
    await update.message.reply_text(text, parse_mode="Markdown")


async def expense_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    db = context.application.bot_data["db"]
    chat_id = str(update.effective_chat.id)
    text = build_expense_summary(db, chat_id, datetime.now(), "bulan")
    await update.message.reply_text(text, parse_mode="Markdown")


async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE, forced: str | None = None):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    kind = forced or " ".join(context.args or ["bulan"])
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id) if "saya" in (context.args or []) else None
    kind = kind.replace(" saya", "").strip()
    if kind == "saya":
        kind = "bulan"
    try:
        text = build_report(context.application.bot_data["db"], kind, chat_id, datetime.now(), user_id)
    except ValueError as e:
        text = f"❓ {e}"
    await update.message.reply_text(text, parse_mode="Markdown")


async def undo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    db: Database = context.application.bot_data["db"]
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    tx = db.find_latest_transaction(user_id, chat_id, datetime.now())
    if tx and db.delete_transaction(tx.id, user_id, chat_id):
        await update.message.reply_text(
            f"✅ *Catatan Terakhir Dibatalkan*\nTransaksi #{tx.id} ({tx.description} — {format_rupiah(tx.amount)}) telah dihapus dari pembukuan.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("❓ Tidak ditemukan catatan mutasi milik Anda dalam 24 jam terakhir untuk dibatalkan.")


async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    if not context.args:
        return await update.message.reply_text("Format: `/hapus <ID_TRANSAKSI>`\nContoh: `/hapus 42`", parse_mode="Markdown")
    try:
        tx_id = int(context.args[0].replace("#", ""))
    except ValueError:
        return await update.message.reply_text("ID transaksi harus berupa angka, contoh: `/hapus 42`", parse_mode="Markdown")

    db: Database = context.application.bot_data["db"]
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    tx = db.get_transaction(tx_id)
    if tx and tx.user_id == user_id and str(tx.chat_id) == chat_id:
        if not db.delete_transaction(tx_id, user_id, chat_id):
            return await update.message.reply_text("❓ Transaksi sudah dihapus atau tidak ditemukan.")
        await update.message.reply_text(
            f"✅ *Catatan Mutasi Dihapus*\nTransaksi #{tx_id} ({tx.description} — {format_rupiah(tx.amount)}) berhasil dihapus dari sistem.",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("❓ Catatan transaksi tidak ditemukan atau bukan bagian dari pembukuan grup ini.")


async def edit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    if len(context.args) < 3:
        return await update.message.reply_text(
            "Format: `/edit <ID> nominal|deskripsi|kategori <nilai>`\nContoh:\n• `/edit 42 nominal 35000`\n• `/edit 42 deskripsi Nasi Goreng Telur`\n• `/edit 42 kategori Makanan & Minuman`",
            parse_mode="Markdown",
        )
    tx_id_str, field = context.args[0].replace("#", ""), context.args[1].lower()
    value = " ".join(context.args[2:])
    try:
        tx_id = int(tx_id_str)
    except ValueError:
        return await update.message.reply_text("ID transaksi harus berupa angka.")

    changes = {}
    if field in ("nominal", "amount"):
        try:
            changes["amount"] = int(value.replace(".", "").replace(",", "").replace("Rp", "").strip())
        except ValueError:
            return await update.message.reply_text("Nominal harus berupa angka yang valid.")
    elif field in ("deskripsi", "desc", "description"):
        changes["description"] = value
    elif field in ("kategori", "cat", "category"):
        changes["category"] = value
    else:
        return await update.message.reply_text("Kolom yang dapat diubah hanya: `nominal`, `deskripsi`, atau `kategori`.", parse_mode="Markdown")

    db: Database = context.application.bot_data["db"]
    user_id = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)
    ok = db.update_transaction(tx_id, user_id, chat_id, **changes)
    if ok:
        await update.message.reply_text(f"✅ *Catatan #{tx_id} Berhasil Diperbarui.*", parse_mode="Markdown")
    else:
        await update.message.reply_text("❓ Catatan transaksi tidak ditemukan atau bukan milik Anda.")


async def categories_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    db: Database = context.application.bot_data["db"]
    cats = db.list_categories()
    lines = ["🏷️ *DAFTAR KATEGORI TRANSAKSI AKTIF*", "━━━━━━━━━━━━━━━━━━━━━━"]
    for c in cats:
        kw = ", ".join(c.keywords[:4])
        kw_str = f" _({kw})_" if kw else ""
        lines.append(f"• {c.emoji} *{c.name}*{kw_str}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("Gunakan `/tambahkategori <Nama> <kata1,kata2>` untuk menambah.")
    lines.append("✨ _ziqva.com team with love family @2026_")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def accounts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    db = context.application.bot_data["db"]
    accounts = db.list_accounts(str(update.effective_chat.id))
    if not accounts:
        return await update.message.reply_text("🏦 Belum ada akun keuangan. Tambahkan rekening/e-wallet/cash melalui menu Kekayaan di dasbor web.")
    ledger = WealthLedger(db)
    balances = {x.account_id: x for x in ledger.get_account_balances(str(update.effective_chat.id))}
    lines = ["🏦 *AKUN KEUANGAN AKTIF*", "━━━━━━━━━━━━━━━━━━━━━━"]
    for account in accounts:
        balance = balances[account.id].balance
        ident = ("•••• " + account.account_identifier[-4:]) if len(account.account_identifier) > 4 else "—"
        provider = account.provider or account.account_type
        provider_line = f"  Provider: {provider} ·" if provider.casefold() != account.name.casefold() else " "
        owner = f" - {account.holder_name}" if account.holder_name and account.holder_name.casefold() != account.name.casefold() else ""
        lines.append(f"• *{account.name}{owner}*\n{provider_line} ID {account.id} · {ident} · {format_rupiah(balance)}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def wealth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    summary = WealthLedger(context.application.bot_data["db"]).get_wealth_summary(str(update.effective_chat.id))
    text = ("💎 *TOTAL KEKAYAAN KELUARGA*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• Total aset: *{format_rupiah(summary.total_wealth)}*\n"
            f"• Aset likuid: *{format_rupiah(summary.liquid_assets)}*\n"
            f"• Investasi: *{format_rupiah(summary.investments)}*\n"
            f"• Cash di tangan: *{format_rupiah(summary.cash)}*\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "Saldo dihitung dari ledger akun; transfer internal tidak dihitung sebagai pemasukan.")
    await update.message.reply_text(text, parse_mode="Markdown")

async def set_account_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set a personal default account; it overrides the family default for this user."""
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    if len(context.args) != 2 or context.args[0].casefold() not in {"masuk", "keluar", "income", "expense"}:
        return await update.message.reply_text("Format: `/setakun masuk|keluar <ID akun>`\nContoh: `/setakun masuk 2` (khusus Anda)", parse_mode="Markdown")
    kind = "income" if context.args[0].casefold() in {"masuk", "income"} else "expense"
    try:
        account_id = int(context.args[1])
        account = context.application.bot_data["db"].get_account(account_id, str(update.effective_chat.id))
        if not account:
            raise ValueError
        WealthLedger(context.application.bot_data["db"]).set_default_account(str(update.effective_chat.id), kind, account_id, str(update.effective_user.id))
        await update.message.reply_text(f"✅ Default pribadi untuk transaksi {('masuk' if kind == 'income' else 'keluar')} diset ke *{account.name}*.", parse_mode="Markdown")
    except (ValueError, WealthError):
        await update.message.reply_text("❌ ID akun tidak ditemukan di grup ini. Lihat daftar dengan `/akun`.", parse_mode="Markdown")


async def transfer_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    if len(context.args) < 4:
        return await update.message.reply_text("Format: `/transfer <dari_id> <ke_id> <nominal> <keterangan>`\nGunakan `/akun` untuk melihat akun aktif.", parse_mode="Markdown")
    try:
        source_id, destination_id = int(context.args[0]), int(context.args[1])
        amount = int(context.args[2].replace(".", "").replace(",", "").replace("Rp", ""))
        description = " ".join(context.args[3:])
        WealthLedger(context.application.bot_data["db"]).create_transfer(str(update.effective_chat.id), source_id, destination_id, amount, description, datetime.now().date(), str(update.effective_user.id), update.effective_user.username or update.effective_user.first_name or "user", idempotency_key=f"tg:{update.update_id}")
        await update.message.reply_text(f"✅ Transfer {format_rupiah(amount)} berhasil dicatat. Gunakan `/saldoaset` untuk melihat saldo terbaru.", parse_mode="Markdown")
    except (ValueError, WealthError, InsufficientFundsError) as exc:
        await update.message.reply_text(f"❌ Transfer ditolak: {exc}")


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    db: Database = context.application.bot_data["db"]
    chat_id = str(update.effective_chat.id)
    tx_count = len(db.list_transactions(TransactionFilters(chat_id)))
    acc_count = len(db.list_accounts(chat_id))
    summary = WealthLedger(db).get_wealth_summary(chat_id)
    text = (
        "📦 *STATUS BACKUP & KEAMANAN DATA*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• Total Transaksi : *{tx_count} catatan*\n"
        f"• Total Rekening  : *{acc_count} akun*\n"
        f"• Total Kekayaan  : *{format_rupiah(summary.total_wealth)}*\n"
        "• Integritas Data : ✅ Terverifikasi\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 *Pusat Unduh & Pulihkan Cadangan:*\n"
        "Buka menu Backup di dasbor web: `/keuangan/backup`\n"
        "Tersedia ekspor ZIP lengkap, JSON, dan CSV bundle."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def add_category_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    if len(context.args) < 2:
        return await update.message.reply_text("Format: `/tambahkategori <Nama Kategori> <kata1,kata2>`\nContoh: `/tambahkategori Investasi saham,bibit,reksa`", parse_mode="Markdown")
    name = context.args[0]
    keywords = [k.strip() for k in " ".join(context.args[1:]).split(",") if k.strip()]
    db: Database = context.application.bot_data["db"]
    from .models import Category
    db.upsert_category(Category(name, keywords, "📁", "expense"))
    await update.message.reply_text(f"✅ Kategori *{name}* berhasil disimpan dengan kata kunci: `{', '.join(keywords)}`.", parse_mode="Markdown")


async def remove_category_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    if not context.args:
        return await update.message.reply_text("Format: `/hapuskategori <Nama Kategori>`", parse_mode="Markdown")
    name = " ".join(context.args)
    db: Database = context.application.bot_data["db"]
    if name == "Lain-lain":
        return await update.message.reply_text("⚠️ Kategori 'Lain-lain' merupakan kategori bawaan dan tidak dapat dihapus.")
    db.rename_category_transactions(name, "Lain-lain")
    ok = db.delete_category(name)
    if ok:
        await update.message.reply_text(f"✅ Kategori *{name}* dihapus dan seluruh transaksi terkait dialihkan ke 'Lain-lain'.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❓ Kategori tidak ditemukan.")


async def receipt_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    if not s.gemini_api_keys:
        return await update.message.reply_text("🧾 Foto struk diterima. Tambahkan Gemini API Key melalui dasbor web (Menu Pengaturan) untuk analisa otomatis.")
    status_msg = await update.message.reply_text("🔎 *Sedang menganalisa foto struk belanja dengan Gemini AI...*", parse_mode="Markdown")
    stage = "mengunduh foto dari Telegram"
    try:
        for attempt in range(3):
            try:
                photo = await update.message.photo[-1].get_file(read_timeout=60, connect_timeout=30)
                image = await photo.download_as_bytearray(read_timeout=120, connect_timeout=30)
                break
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(1)
        stage = "menganalisis foto melalui Gemini"
        current = load_settings(context.application.bot_data["db"].path)
        pool = context.application.bot_data["gemini_pool"]
        pool.update(current.gemini_api_keys, current.gemini_model)
        data = await asyncio.to_thread(extract_receipt, bytes(image), current.gemini_api_keys, current.gemini_model, pool)
        context.user_data["pending_receipt"] = {
            **data,
            "pending_at": datetime.now().isoformat(),
            "user_id": str(update.effective_user.id),
            "username": update.effective_user.username or update.effective_user.first_name or "user",
            "chat_id": str(update.effective_chat.id),
        }
        detail_lines = [f"• {i['name']} x{i['quantity']:g} — {format_rupiah(i['subtotal'] or i['unit_price'])}" for i in data.get("items", [])]
        detail_text = ("\n🧺 *Rincian Barang:*\n" + "\n".join(detail_lines)) if detail_lines else ""
        preview = (
            f"🧾 *HASIL ANALISA STRUK BELANJA*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💸 *Nominal Total :* *{format_rupiah(data['amount'])}*\n"
            f"📝 *Deskripsi     :* {data['description']}\n"
            f"🏷️ *Pos Kategori  :* {data['category']}\n"
            f"📅 *Tanggal Struk :* {data['date']}\n"
            f"🕒 *Jam           :* {data.get('time') or '-'}\n"
            f"📍 *Lokasi        :* {data.get('location') or '-'}\n"
            f"🏦 *Bank          :* {data.get('bank') or data.get('source_bank') or data.get('destination_bank') or '-'}\n"
            f"🔁 *Jenis         :* {data.get('transaction_kind') or '-'}\n"
            f"{detail_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Apakah Anda ingin menyimpan transaksi ini?"
        )
        keys = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Simpan Mutasi", callback_data="receipt:save"),
                InlineKeyboardButton("✏️ Koreksi", callback_data="receipt:edit"),
            ],
            [
                InlineKeyboardButton("❌ Batalkan", callback_data="receipt:cancel"),
            ],
        ])
        stage = "mengirim hasil ke Telegram"
        await status_msg.edit_text(preview, parse_mode="Markdown", reply_markup=keys, read_timeout=60, connect_timeout=30)
    except Exception as exc:
        logging.getLogger(__name__).exception("Receipt failed at %s: %s", stage, exc)
        detail = str(exc).replace("\n", " ").strip()[:240] or type(exc).__name__
        await status_msg.edit_text(f"⚠️ Gagal saat {stage}: {detail}. Silakan coba lagi.", read_timeout=60)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    if not s.gemini_api_keys:
        return await update.message.reply_text("🎙️ Tambahkan Gemini API Key terlebih dahulu di Pengaturan.")
    status = await update.message.reply_text("🎙️ Mendengarkan suara Anda...")
    try:
        audio_file = await update.message.voice.get_file(read_timeout=60, connect_timeout=30)
        audio = await audio_file.download_as_bytearray(read_timeout=60, connect_timeout=30)
        current = load_settings(context.application.bot_data["db"].path)
        transcript = await asyncio.to_thread(
            transcribe_audio, bytes(audio), current.gemini_api_keys, current.gemini_model,
            context.application.bot_data["gemini_pool"],
        )
        context.user_data["pending_voice"] = {"transcript": transcript, "created_at": datetime.now().isoformat(), "user_id": str(update.effective_user.id), "chat_id": str(update.effective_chat.id)}
        keys = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Konfirmasi & Simpan", callback_data="voice:save"), InlineKeyboardButton("❌ Batalkan", callback_data="voice:cancel")]])
        await status.edit_text(f"🎙️ *Hasil transkrip:*\n{transcript}\n\nPeriksa dulu sebelum dicatat.", parse_mode="Markdown", reply_markup=keys)
    except Exception as exc:
        logging.getLogger(__name__).exception("Voice failed: %s", exc)
        await status.edit_text(f"⚠️ Gagal membaca voice: {str(exc)[:180]}")


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    db: Database = context.application.bot_data["db"]
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)
    now = datetime.now()

    if data.startswith("wealth:"):
        if data == "wealth:duplicate:update":
            pending = context.user_data.pop("pending_account_update", None)
            if not pending:
                return await query.message.reply_text("❌ Data update sudah kedaluwarsa.")
            try:
                existing = db.get_account(int(pending["existing_id"]), chat_id)
                if not existing:
                    raise WealthError("Akun duplikat tidak ditemukan")
                db.update_account_metadata(existing.id, chat_id, name=pending["name"], provider=pending["provider"], holder_name=pending["holder_name"], account_identifier=pending["account_identifier"])
                WealthLedger(db).reconcile_account(chat_id, existing.id, parse_idr_amount(pending["opening_balance"], allow_zero=True), "Update akun duplikat", date.today(), user_id, update.effective_user.username or "user")
                return await query.message.reply_text(f"✅ Akun {existing.name} berhasil diperbarui.\nID akun: {existing.id}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data="wealth:home")]]))
            except (KeyError, ValueError, WealthError) as exc:
                return await query.message.reply_text(f"❌ Update akun gagal: {exc}")
        reply = context.application.bot_data["wealth_menu"].handle_callback(chat_id, user_id, data, str(update.update_id))
        if reply.action == "account_create":
            try:
                values = reply.payload
                account = FinancialAccount(None, chat_id, values["name"], values["account_type"], values["provider"], values["holder_name"], values["account_identifier"], "IDR", int(values["opening_balance"].replace(".", "").replace(",", "")), date.today())
                normalized = lambda value: " ".join(str(value).casefold().split())
                duplicate = next((item for item in db.list_accounts(chat_id) if (values.get("account_identifier") and normalized(item.account_identifier) == normalized(values["account_identifier"])) or (normalized(item.name) == normalized(values["name"]) and normalized(item.provider) == normalized(values["provider"]))), None)
                if duplicate:
                    context.user_data["pending_account_update"] = {**values, "existing_id": duplicate.id}
                    return await query.message.reply_text(
                        f"⚠️ Akun duplikat terdeteksi\n\nAkun {duplicate.name} ({duplicate.provider}) dengan ID {duplicate.id} sudah ada.\n\nApakah ingin memperbarui data dan saldo akun tersebut?",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Update Akun", callback_data="wealth:duplicate:update"), InlineKeyboardButton("❌ Batalkan", callback_data="wealth:cancel")]]),
                    )
                account = db.create_account(account, idempotency_key=f"telegram-account:{update.update_id}")
                reply.text = f"✅ *Akun berhasil ditambahkan*\n{account.name}\nID akun: `{account.id}`"
            except (KeyError, ValueError, WealthError) as exc:
                reply.text = f"❌ Akun tidak disimpan: {exc}"
        elif reply.action == "default_account":
            try:
                values = reply.payload
                kind = str(values["operation_kind"]).casefold()
                kind = "income" if kind in {"income", "masuk"} else "expense" if kind in {"expense", "keluar"} else kind
                account_id = int(values["account_id"])
                account = db.get_account(account_id, chat_id)
                if kind not in {"income", "expense"} or not account:
                    raise WealthError("Jenis atau akun default tidak valid")
                WealthLedger(db).set_default_account(chat_id, kind, account_id, user_id)
                reply.text = f"✅ Default pribadi {kind} diset ke *{account.name}*."
            except (KeyError, ValueError, WealthError) as exc:
                reply.text = f"❌ Default akun tidak disimpan: {exc}"
        elif reply.action == "operation_create":
            try:
                values = reply.payload
                ledger = WealthLedger(db)
                amount = parse_idr_amount(values["amount"])
                tx_date = date.today()
                operation = ledger.create_transfer(chat_id, int(values["source_account_id"]), int(values["destination_account_id"]), amount, values.get("description", "Transfer"), tx_date, user_id, update.effective_user.username or "user", operation_type=values.get("operation_type", "transfer"), idempotency_key=f"telegram-operation:{update.update_id}")
                reply.text = f"✅ Mutasi berhasil disimpan. Ref: `{operation.id[:10]}`"
            except (KeyError, ValueError, WealthError) as exc:
                reply.text = f"❌ Mutasi tidak disimpan: {exc}"
        elif reply.action == "archive":
            try:
                WealthLedger(db).archive_account(chat_id, int(reply.payload["account_id"]), user_id)
                reply.text = "✅ Akun berhasil diarsipkan."
            except (KeyError, ValueError, WealthError) as exc:
                reply.text = f"❌ Akun tidak diarsipkan: {exc}"
        elif reply.action == "reconcile":
            try:
                values = reply.payload
                WealthLedger(db).reconcile_account(chat_id, int(values["account_id"]), parse_idr_amount(values["actual_balance"], allow_zero=True), values.get("reason", "Rekonsiliasi"), date.today(), user_id, update.effective_user.username or "user")
                reply.text = "✅ Saldo akun berhasil direkonsiliasi."
            except (KeyError, ValueError, WealthError) as exc:
                reply.text = f"❌ Rekonsiliasi gagal: {exc}"
        elif reply.action == "summary":
            summary = WealthLedger(db).get_wealth_summary(chat_id)
            reply.text = f"📊 *RINGKASAN KEUANGAN*\n\n• Total kekayaan: *{format_rupiah(summary.total_wealth)}*\n• Aset likuid: *{format_rupiah(summary.liquid_assets)}*\n• Investasi: *{format_rupiah(summary.investments)}*\n• Cash: *{format_rupiah(summary.cash)}*"
        elif reply.action in {"account_list", "investment_list"}:
            balances = {item.account_id: item for item in WealthLedger(db).get_account_balances(chat_id, include_archived=False)}
            accounts = [a for a in db.list_accounts(chat_id) if a.id in balances]
            if reply.action == "investment_list":
                accounts = [a for a in accounts if a.account_type == "investment"]
                title = "📈 *PORTOFOLIO INVESTASI*"
            else:
                title = "🏦 *SALDO SEMUA AKUN*"
            if not accounts:
                reply.text = title + "\n\nBelum ada akun yang tercatat."
            else:
                lines = [title, ""]
                for account in accounts:
                    balance = balances[account.id].balance
                    provider = account.provider or account.account_type
                    provider_line = f"  Provider: {provider} ·" if provider.casefold() != account.name.casefold() else " "
                    owner = f" - {account.holder_name}" if account.holder_name and account.holder_name.casefold() != account.name.casefold() else ""
                    lines.append(f"• *{account.name}{owner}*\n{provider_line} ID {account.id} · *{format_rupiah(balance)}*")
                reply.text = "\n".join(lines)
        elif reply.action == "reports":
            rows = WealthLedger(db).list_operations(chat_id, limit=10)
            reply.text = "📋 *MUTASI TERAKHIR*\n\n" + ("\n".join(f"• {row['description']} — {row['operation_type']} ({row['transaction_date']})" for row in rows) if rows else "Belum ada mutasi.")
        return await query.message.reply_text(reply.text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(reply.keyboard["inline_keyboard"]))

    # Receipt callbacks
    if data.startswith("receipt:"):
        pending = context.user_data.get("pending_receipt")
        if not pending:
            return await query.edit_message_text("❓ Pratinjau struk telah kedaluwarsa.")
        try:
            if datetime.now() - datetime.fromisoformat(pending.get("pending_at", datetime.now().isoformat())) > timedelta(hours=24):
                context.user_data.pop("pending_receipt", None)
                context.user_data.pop("receipt_editing", None)
                return await query.edit_message_text("⌛ Pratinjau struk kedaluwarsa setelah 24 jam.")
        except ValueError:
            context.user_data.pop("pending_receipt", None)
            return await query.edit_message_text("❓ Pratinjau struk tidak valid, silakan kirim ulang.")
        if data == "receipt:cancel":
            context.user_data.pop("pending_receipt", None)
            return await query.edit_message_text("❌ Pencatatan struk belanja dibatalkan.")
        if data == "receipt:edit":
            context.user_data["receipt_editing"] = True
            return await query.edit_message_text("✏️ Silakan ketik koreksi transaksi, contoh: `45000 belanja perlengkapan rumah`", parse_mode="Markdown")
        if data == "receipt:save":
            if int(pending.get("amount") or 0) <= 0:
                return await query.edit_message_text("❓ Nominal struk belum terbaca. Gunakan Koreksi dan masukkan nominal yang benar.")
            if str(pending.get("chat_id")) != chat_id or str(pending.get("user_id")) != user_id:
                context.user_data.pop("pending_receipt", None)
                return await query.edit_message_text("❌ Pratinjau ini bukan milik Anda atau bukan dari grup ini.")
            tx_type = "income" if pending.get("direction") == "in" or (pending.get("direction") is None and pending.get("category") == "Pemasukan") else "expense"
            saved = db.add_transaction_with_details(
                Transaction(
                    None,
                    pending["user_id"],
                    pending["username"],
                    pending["chat_id"],
                    tx_type,
                    pending["amount"],
                    pending["description"],
                    pending["category"],
                    date.fromisoformat(pending["date"]),
                    now,
                )
            )
            context.user_data.pop("pending_receipt", None)
            await query.edit_message_text(render_confirmation(saved, pending["username"]), parse_mode="Markdown")
            return

    if data.startswith("voice:"):
        pending = context.user_data.get("pending_voice")
        if not pending or pending.get("user_id") != user_id or pending.get("chat_id") != chat_id:
            return await query.edit_message_text("❓ Konfirmasi voice sudah kedaluwarsa.")
        if data == "voice:cancel":
            context.user_data.pop("pending_voice", None)
            return await query.edit_message_text("❌ Pencatatan voice dibatalkan.")
        try:
            if datetime.now() - datetime.fromisoformat(pending["created_at"]) > timedelta(hours=24):
                context.user_data.pop("pending_voice", None)
                return await query.edit_message_text("⌛ Konfirmasi voice kedaluwarsa setelah 24 jam.")
            context.user_data.pop("pending_voice", None)
            return await message_handler(update, context, pending["transcript"], reply_message=query.message)
        except (ValueError, ParseError) as exc:
            return await query.edit_message_text(f"❌ Voice tidak dapat dicatat: {exc}")

    # Undo specific transaction ID callback
    if data.startswith("cb:undo:"):
        target_id = data.split("cb:undo:")[-1]
        if target_id == "last":
            tx = db.find_latest_transaction(user_id, chat_id, now)
            if tx and db.delete_transaction(tx.id, user_id, chat_id):
                await query.edit_message_text(f"🗑️ *Catatan mutasi terakhir (#{tx.id} — {tx.description}) berhasil dibatalkan.*", parse_mode="Markdown")
            else:
                await query.edit_message_text("❓ Tidak ada mutasi milik Anda dalam 24 jam terakhir untuk dibatalkan.")
        else:
            try:
                tx_id = int(target_id)
                tx = db.get_transaction(tx_id)
                if tx and tx.user_id == user_id and datetime.now() - tx.created_at <= timedelta(hours=24) and db.delete_transaction(tx_id, user_id, chat_id):
                    await query.edit_message_text(f"🗑️ *Catatan mutasi #{tx_id} ({tx.description} — {format_rupiah(tx.amount)}) berhasil dibatalkan.*", parse_mode="Markdown")
                elif tx and datetime.now() - tx.created_at > timedelta(hours=24):
                    await query.edit_message_text("⌛ Tombol undo sudah kedaluwarsa setelah 24 jam.", reply_markup=None)
                else:
                    await query.edit_message_text("❓ Catatan transaksi telah dihapus sebelumnya.")
            except ValueError:
                pass
        return

    if data.startswith("cb:delete:") or data.startswith("cb:edit:"):
        try:
            tx_id = int(data.rsplit(":", 1)[1])
            tx = db.get_transaction(tx_id)
        except (ValueError, TypeError):
            tx = None
        if not tx or str(tx.chat_id) != chat_id or str(tx.user_id) != user_id:
            return await query.edit_message_text("❌ Anda hanya dapat mengelola transaksi yang Anda buat sendiri.")
        if data.startswith("cb:delete:"):
            if datetime.now() - tx.created_at > timedelta(hours=24):
                return await query.edit_message_text("⌛ Penghapusan dari tombol hanya tersedia selama 24 jam.")
            db.delete_transaction(tx_id, user_id, chat_id)
            return await query.edit_message_text(f"✅ Transaksi #{tx_id} dihapus. Saldo dan rekap akan diperbarui.")
        return await query.message.reply_text(
            f"✏️ Untuk mengubah transaksi #{tx_id}, kirim salah satu:\n"
            f"`/edit {tx_id} nominal 50000`\n`/edit {tx_id} deskripsi Keterangan baru`\n`/edit {tx_id} kategori Nama Kategori`",
            parse_mode="Markdown",
        )

    # Reports callbacks
    if data == "cb:rekap:bulan":
        text = build_report(db, "bulan", chat_id, now)
        return await query.message.reply_text(text, parse_mode="Markdown")
    if data == "cb:rekap:minggu":
        text = build_report(db, "minggu", chat_id, now)
        return await query.message.reply_text(text, parse_mode="Markdown")
    if data == "cb:income:bulan":
        text = build_income_summary(db, chat_id, now, "bulan")
        return await query.message.reply_text(text, parse_mode="Markdown")
    if data == "cb:expense:bulan":
        text = build_expense_summary(db, chat_id, now, "bulan")
        return await query.message.reply_text(text, parse_mode="Markdown")
    if data == "cb:kategori":
        cats = db.list_categories()
        lines = ["🏷️ *KATEGORI TRANSAKSI KELUARGA*", "━━━━━━━━━━━━━━━━━━━━━━"]
        for c in cats:
            lines.append(f"• {c.emoji} *{c.name}*")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━\n✨ _ziqva.com team @2026_")
        return await query.message.reply_text("\n".join(lines), parse_mode="Markdown")
    if data == "cb:bantuan":
        return await query.message.reply_text(HELP_TEXT, parse_mode="Markdown")


def build_app():
    s = load_settings()
    db = Database(s.database_path)
    db.initialize()
    async def clear_webhook(application):
        # Bot keluarga berjalan dengan long polling; webhook web harus dilepas
        # agar Telegram tidak mengirim update ke dua jalur sekaligus.
        await application.bot.delete_webhook(drop_pending_updates=False)
        await application.bot.set_my_commands([
            ("start", "Buka menu Finance Family"),
            ("rekap", "Ringkasan bulan berjalan"),
            ("saldo", "Lihat saldo kas"),
            ("pemasukan", "Lihat total pemasukan"),
            ("pengeluaran", "Lihat total pengeluaran"),
            ("hari", "Laporan hari ini"),
            ("minggu", "Laporan minggu ini"),
            ("bulan", "Laporan bulan ini"),
            ("kategori", "Daftar kategori"),
            ("akun", "Daftar akun bank dan e-wallet"),
            ("saldoaset", "Total kekayaan dan saldo aset"),
            ("transfer", "Transfer antar akun"),
            ("setakun", "Atur rekening pribadi"),
            ("undo", "Batalkan catatan terakhir"),
            ("bantuan", "Panduan penggunaan bot"),
        ])

    telegram_request = HTTPXRequest(connect_timeout=30, read_timeout=60, write_timeout=60, pool_timeout=30)
    updates_request = HTTPXRequest(connect_timeout=30, read_timeout=75, write_timeout=60, pool_timeout=30)
    app = (
        Application.builder()
        .token(s.bot_token)
        .request(telegram_request)
        .get_updates_request(updates_request)
        .post_init(clear_webhook)
        .build()
    )
    app.bot_data.update(settings=s, db=db, limiter=RateLimiter(s.rate_limit), gemini_pool=GeminiKeyPool(s.gemini_api_keys, s.gemini_model), wealth_menu=WealthTelegramMenu())

    app.add_handler(CommandHandler(["start", "menu", "bantuan"], start_cmd))
    app.add_handler(CommandHandler(["pemasukan", "masuk"], income_cmd))
    app.add_handler(CommandHandler(["pengeluaran", "keluar"], expense_cmd))
    app.add_handler(CommandHandler(["rekap", "saldo"], lambda u, c: report_cmd(u, c, "bulan")))
    app.add_handler(CommandHandler(["laporan", "hari", "minggu", "bulan", "tahun", "all"], report_cmd))
    app.add_handler(CommandHandler("undo", undo_cmd))
    app.add_handler(CommandHandler("hapus", delete_cmd))
    app.add_handler(CommandHandler("edit", edit_cmd))
    app.add_handler(CommandHandler("kategori", categories_cmd))
    app.add_handler(CommandHandler(["akun", "rekening"], accounts_cmd))
    app.add_handler(CommandHandler(["saldoaset", "wealth", "kekayaan"], wealth_cmd))
    app.add_handler(CommandHandler("transfer", transfer_cmd))
    app.add_handler(CommandHandler("setakun", set_account_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
    app.add_handler(CommandHandler("tambahkategori", add_category_cmd))
    app.add_handler(CommandHandler("hapuskategori", remove_category_cmd))

    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO, receipt_photo_handler))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    return app


if __name__ == "__main__":
    build_app().run_polling()
