"""Telegram Bot for Family Finance Management.

Finance Family — Dibuat oleh effands ~ ziqva.com team with love family @2026.
"""
import asyncio
from datetime import date, datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .categorizer import categorize
from .config import load_settings
from .database import Database
from .formatting import format_rupiah, render_confirmation
from .models import Transaction
from .rate_limit import RateLimiter
from .receipt_ai import GeminiKeyPool, extract_receipt
from .reports import build_expense_summary, build_income_summary, build_report

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
    welcome = f"👋 *Halo, {name}!*\nSelamat datang di *Finance Family*.\n\n" + HELP_TEXT
    await update.message.reply_text(welcome, parse_mode="Markdown", reply_markup=get_command_inline_keyboard())


async def menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
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


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = context.application.bot_data["settings"]
    if not allowed(update, s):
        return
    user = update.effective_user
    chat_id = str(update.effective_chat.id)
    now = datetime.now()

    if not context.application.bot_data["limiter"].allow(str(user.id), now):
        return await update.message.reply_text("⏳ Terlalu banyak pesan dalam waktu singkat. Mohon tunggu sebentar.")

    text = update.message.text
    try:
        parsed = parse_message(text, now, s.timezone)
    except ParseError as e:
        return await update.message.reply_text(f"❓ {e}")

    db: Database = context.application.bot_data["db"]
    category = categorize(parsed.description, db.list_categories())
    uname = user.username or user.first_name or "user"
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
            InlineKeyboardButton("📊 Rekap Saldo", callback_data="cb:rekap:bulan"),
        ]
    ])
    await update.message.reply_text(card_text, parse_mode="Markdown", reply_markup=action_keys)


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
        await update.message.reply_text("❓ Tidak ditemukan catatan mutasi milik Anda dalam 5 menit terakhir untuk dibatalkan.")


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
    if tx and (tx.user_id == user_id or str(tx.chat_id) == chat_id):
        db.delete_transaction_web(tx_id, chat_id)
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
    ok = db.update_transaction(tx_id, user_id, chat_id, **changes) or db.update_transaction(tx_id, "web", chat_id, **changes)
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
    try:
        photo = await update.message.photo[-1].get_file()
        image = await photo.download_as_bytearray()
        current = load_settings(context.application.bot_data["db"].path)
        pool = context.application.bot_data["gemini_pool"]
        pool.update(current.gemini_api_keys, current.gemini_model)
        data = await asyncio.to_thread(extract_receipt, bytes(image), current.gemini_api_keys, current.gemini_model, pool)
        context.user_data["pending_receipt"] = {
            **data,
            "user_id": str(update.effective_user.id),
            "username": update.effective_user.username or update.effective_user.first_name or "user",
            "chat_id": str(update.effective_chat.id),
        }
        preview = (
            f"🧾 *HASIL ANALISA STRUK BELANJA*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💸 *Nominal Total :* *{format_rupiah(data['amount'])}*\n"
            f"📝 *Deskripsi     :* {data['description']}\n"
            f"🏷️ *Pos Kategori  :* {data['category']}\n"
            f"📅 *Tanggal Struk :* {data['date']}\n"
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
        await status_msg.edit_text(preview, parse_mode="Markdown", reply_markup=keys)
    except Exception as exc:
        await status_msg.edit_text(f"⚠️ Gagal membaca struk belanja: {exc}\nSilakan ketik manual, contoh: `belanja supermarket 75rb`.")


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    db: Database = context.application.bot_data["db"]
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)
    now = datetime.now()

    # Receipt callbacks
    if data.startswith("receipt:"):
        pending = context.user_data.get("pending_receipt")
        if not pending:
            return await query.edit_message_text("❓ Pratinjau struk telah kedaluwarsa.")
        if data == "receipt:cancel":
            context.user_data.pop("pending_receipt", None)
            return await query.edit_message_text("❌ Pencatatan struk belanja dibatalkan.")
        if data == "receipt:edit":
            return await query.edit_message_text("✏️ Silakan ketik koreksi transaksi, contoh: `45000 belanja perlengkapan rumah`", parse_mode="Markdown")
        if data == "receipt:save":
            tx_type = "income" if pending.get("category") == "Pemasukan" else "expense"
            saved = db.add_transaction(
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

    # Undo specific transaction ID callback
    if data.startswith("cb:undo:"):
        target_id = data.split("cb:undo:")[-1]
        if target_id == "last":
            tx = db.find_latest_transaction(user_id, chat_id, now)
            if tx and db.delete_transaction(tx.id, user_id, chat_id):
                await query.edit_message_text(f"🗑️ *Catatan mutasi terakhir (#{tx.id} — {tx.description}) berhasil dibatalkan.*", parse_mode="Markdown")
            else:
                await query.edit_message_text("❓ Tidak ada mutasi milik Anda dalam 5 menit terakhir untuk dibatalkan.")
        else:
            try:
                tx_id = int(target_id)
                tx = db.get_transaction(tx_id)
                if tx and db.delete_transaction_web(tx_id, chat_id):
                    await query.edit_message_text(f"🗑️ *Catatan mutasi #{tx_id} ({tx.description} — {format_rupiah(tx.amount)}) berhasil dibatalkan.*", parse_mode="Markdown")
                else:
                    await query.edit_message_text("❓ Catatan transaksi telah dihapus sebelumnya.")
            except ValueError:
                pass
        return

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
    app = Application.builder().token(s.bot_token).build()
    app.bot_data.update(settings=s, db=db, limiter=RateLimiter(s.rate_limit), gemini_pool=GeminiKeyPool(s.gemini_api_keys, s.gemini_model))

    app.add_handler(CommandHandler(["start", "menu", "bantuan"], start_cmd))
    app.add_handler(CommandHandler(["pemasukan", "masuk"], income_cmd))
    app.add_handler(CommandHandler(["pengeluaran", "keluar"], expense_cmd))
    app.add_handler(CommandHandler(["rekap", "saldo"], lambda u, c: report_cmd(u, c, "bulan")))
    app.add_handler(CommandHandler(["laporan", "hari", "minggu", "bulan", "tahun", "all"], report_cmd))
    app.add_handler(CommandHandler("undo", undo_cmd))
    app.add_handler(CommandHandler("hapus", delete_cmd))
    app.add_handler(CommandHandler("edit", edit_cmd))
    app.add_handler(CommandHandler("kategori", categories_cmd))
    app.add_handler(CommandHandler("tambahkategori", add_category_cmd))
    app.add_handler(CommandHandler("hapuskategori", remove_category_cmd))

    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO, receipt_photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_text))
    return app


if __name__ == "__main__":
    build_app().run_polling()
