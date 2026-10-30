from datetime import datetime
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, filters
from .config import load_settings
from .database import Database
from .parser import ParseError, parse_message
from .categorizer import categorize
from .formatting import render_confirmation
from .models import Transaction
from .reports import build_report
from .rate_limit import RateLimiter
from .receipt_ai import extract_receipt

MENU=ReplyKeyboardMarkup([["➕ Catat transaksi", "🧾 Upload struk"], ["📊 Laporan bulan", "📅 Laporan minggu"], ["💰 Rekap saldo", "↩️ Undo terakhir"], ["🏷️ Kategori", "❓ Bantuan"]], resize_keyboard=True)
HELP="""👋 Halo! Aku pencatat keuangan keluarga.
Ketik saja seperti: `bensin 50rb`, `gaji masuk 8jt`, atau `bayar listrik 350.000`.

📊 Laporan: /hari /minggu /bulan /laporan all
🧾 Ringkasan: /rekap
↩️ Koreksi: /undo, /hapus ID, /edit ID nominal|deskripsi|kategori nilai
🏷️ Kategori: /kategori
"""

def allowed(update,settings): return str(update.effective_chat.id) in settings.allowed_chat_ids
async def start(update,context): await update.message.reply_text(HELP, reply_markup=MENU)
async def menu_text(update,context):
    text=update.message.text
    if text=="📊 Laporan bulan": return await report(update,context,"bulan")
    if text=="📅 Laporan minggu": return await report(update,context,"minggu")
    if text=="💰 Rekap saldo": return await report(update,context,"rekap")
    if text=="↩️ Undo terakhir": return await undo(update,context)
    if text=="🏷️ Kategori": return await categories(update,context)
    if text=="❓ Bantuan": return await start(update,context)
    if text=="➕ Catat transaksi": return await update.message.reply_text("Ketik contoh: bensin 50rb atau gaji masuk 8jt")
    if text=="🧾 Upload struk": return await update.message.reply_text("Kirim foto struknya di chat ini ya. Aku akan baca nominal dan kategorinya.")
    return await message(update,context)
async def message(update,context):
    s=context.application.bot_data["settings"]
    if not allowed(update,s): return
    user=update.effective_user; chat=str(update.effective_chat.id); now=datetime.now()
    if not context.application.bot_data["limiter"].allow(str(user.id),now): return await update.message.reply_text("⏳ Terlalu banyak pesan. Coba lagi sebentar ya.")
    try: parsed=parse_message(update.message.text,now,s.timezone)
    except ParseError as e: return await update.message.reply_text(f"❓ {e}")
    db=context.application.bot_data["db"]; category=categorize(parsed.description,db.list_categories())
    x=db.add_transaction(Transaction(None,str(user.id),user.username or user.first_name,chat,parsed.type,parsed.amount,parsed.description,category.name,parsed.transaction_date,now))
    await update.message.reply_text(render_confirmation(x,user.username or user.first_name))
async def report(update,context,forced=None):
    s=context.application.bot_data["settings"]
    if not allowed(update,s):return
    kind=forced or " ".join(context.args or ["bulan"]); chat=str(update.effective_chat.id); user_id=str(update.effective_user.id) if "saya" in (context.args or []) else None
    kind=kind.replace(" saya","").strip()
    if kind == "saya": kind = "bulan"
    try: text=build_report(context.application.bot_data["db"],kind,chat,datetime.now(),user_id)
    except ValueError as e: text=f"❓ {e}"
    await update.message.reply_text(text)
async def undo(update,context):
    s=context.application.bot_data["settings"]
    if not allowed(update,s):return
    db=context.application.bot_data["db"]; x=db.find_latest_transaction(str(update.effective_user.id),str(update.effective_chat.id),datetime.now())
    await update.message.reply_text("✅ Catatan terakhir dihapus." if x and db.delete_transaction(x.id,str(update.effective_user.id),str(update.effective_chat.id)) else "❓ Tidak ada catatan yang bisa di-undo dalam 5 menit terakhir.")
async def delete_cmd(update,context):
    if not context.args:return await update.message.reply_text("Pakai: /hapus ID")
    db=context.application.bot_data["db"]; ok=db.delete_transaction(int(context.args[0]),str(update.effective_user.id),str(update.effective_chat.id)); await update.message.reply_text("✅ Catatan dihapus." if ok else "❓ Catatan tidak ditemukan atau bukan milikmu.")
async def edit_cmd(update,context):
    if len(context.args)<3:return await update.message.reply_text("Pakai: /edit ID nominal|deskripsi|kategori nilai")
    ident,field="", ""; ident=context.args[0]; field=context.args[1]; value=" ".join(context.args[2:]); changes={}
    if field=="nominal":
        try: changes["amount"]=int(value.replace(".",""))
        except ValueError:return await update.message.reply_text("Nominal harus angka, contoh: 25000")
    elif field in ("deskripsi","kategori"): changes["description" if field=="deskripsi" else "category"]=value
    else:return await update.message.reply_text("Field hanya nominal, deskripsi, atau kategori.")
    ok=context.application.bot_data["db"].update_transaction(int(ident),str(update.effective_user.id),str(update.effective_chat.id),**changes); await update.message.reply_text("✅ Catatan diperbarui." if ok else "❓ Catatan tidak ditemukan atau bukan milikmu.")
async def categories(update,context):
    rows=context.application.bot_data["db"].list_categories(); await update.message.reply_text("🏷️ Kategori:\n"+"\n".join(f"{x.emoji} {x.name}" for x in rows))
async def add_category(update,context):
    if len(context.args)<2:return await update.message.reply_text("Pakai: /tambahkategori Nama kata1,kata2")
    from .models import Category
    name=context.args[0]; keywords=" ".join(context.args[1:]).split(","); context.application.bot_data["db"].upsert_category(Category(name,[x.strip() for x in keywords if x.strip()])); await update.message.reply_text(f"✅ Kategori {name} disimpan.")
async def remove_category(update,context):
    if not context.args:return await update.message.reply_text("Pakai: /hapuskategori Nama")
    ok=context.application.bot_data["db"].delete_category(" ".join(context.args)); await update.message.reply_text("✅ Kategori dihapus." if ok else "❓ Kategori tidak ditemukan atau tidak boleh dihapus.")
async def receipt_photo(update,context):
    s=context.application.bot_data["settings"]
    if not allowed(update,s): return
    if not s.gemini_api_keys: return await update.message.reply_text("🧾 Foto diterima. Tambahkan GEMINI_API_KEYS di .env agar struk bisa dibaca otomatis.")
    status=await update.message.reply_text("🔎 Aku sedang membaca struk…")
    try:
        photo=await update.message.photo[-1].get_file(); image=await photo.download_as_bytearray()
        data=await asyncio.to_thread(extract_receipt,bytes(image),s.gemini_api_keys,s.gemini_model)
        context.user_data["pending_receipt"]={**data,"user_id":str(update.effective_user.id),"username":update.effective_user.username or update.effective_user.first_name,"chat_id":str(update.effective_chat.id)}
        preview=f"🧾 *Preview struk*\n💸 Rp {data['amount']:,}\n📝 {data['description']}\n🏷️ {data['category']}\n📅 {data['date']}\n\nSimpan catatan ini?"
        keys=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Simpan",callback_data="receipt:save"),InlineKeyboardButton("✏️ Koreksi",callback_data="receipt:edit")],[InlineKeyboardButton("❌ Batal",callback_data="receipt:cancel")]])
        await status.edit_text(preview.replace(",","."),parse_mode="Markdown",reply_markup=keys)
    except Exception:
        await status.edit_text("⚠️ Tidak bisa membaca struk dengan yakin. Coba foto lebih terang atau ketik nominal + deskripsi.")
async def receipt_callback(update,context):
    query=update.callback_query; await query.answer(); pending=context.user_data.get("pending_receipt")
    if not pending: return await query.edit_message_text("❓ Preview struk sudah kedaluwarsa.")
    if query.data=="receipt:cancel": context.user_data.pop("pending_receipt",None); return await query.edit_message_text("❌ Struk dibatalkan.")
    if query.data=="receipt:edit": return await query.edit_message_text("✏️ Ketik koreksi, contoh: `45000 belanja kebutuhan rumah`",parse_mode="Markdown")
    from datetime import date
    tx_type="income" if pending["category"]=="Pemasukan" else "expense"
    x=Transaction(None,pending["user_id"],pending["username"],pending["chat_id"],tx_type,pending["amount"],pending["description"],pending["category"],date.fromisoformat(pending["date"]),datetime.now())
    saved=context.application.bot_data["db"].add_transaction(x); context.user_data.pop("pending_receipt",None)
    await query.edit_message_text(render_confirmation(saved,pending["username"]))
def build_app():
    s=load_settings(); db=Database(s.database_path); db.initialize(); app=Application.builder().token(s.bot_token).build(); app.bot_data.update(settings=s,db=db,limiter=RateLimiter(s.rate_limit)); app.add_handler(CommandHandler("start",start)); app.add_handler(CommandHandler(["laporan","hari","minggu","bulan","all","rekap"],report)); app.add_handler(CommandHandler("undo",undo)); app.add_handler(CommandHandler("hapus",delete_cmd)); app.add_handler(CommandHandler("edit",edit_cmd)); app.add_handler(CommandHandler("kategori",categories)); app.add_handler(CommandHandler("tambahkategori",add_category)); app.add_handler(CommandHandler("hapuskategori",remove_category)); app.add_handler(CallbackQueryHandler(receipt_callback,pattern=r"^receipt:")); app.add_handler(MessageHandler(filters.PHOTO,receipt_photo)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,menu_text)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,message)); return app
if __name__=="__main__": build_app().run_polling()
