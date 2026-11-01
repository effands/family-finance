"""Button-first Telegram navigation and guided Wealth input state."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from threading import Lock

@dataclass
class TelegramReply:
    text: str
    keyboard: dict | None = None
    action: str | None = None
    payload: dict = field(default_factory=dict)

@dataclass
class _Session:
    screen: str = "main"
    flow: str | None = None
    step: int = 0
    values: dict = field(default_factory=dict)
    updated_at: datetime = field(default_factory=datetime.utcnow)

class WealthTelegramMenu:
    TTL = timedelta(minutes=15)

    def __init__(self):
        self._sessions = {}
        self._lock = Lock()

    @staticmethod
    def _keyboard(rows):
        return {"inline_keyboard": [[{"text": label, "callback_data": data} for label, data in row] for row in rows]}

    def _session(self, chat_id, user_id):
        key = (str(chat_id), str(user_id))
        with self._lock:
            session = self._sessions.get(key)
            if not session or datetime.utcnow() - session.updated_at > self.TTL:
                session = _Session()
                self._sessions[key] = session
            session.updated_at = datetime.utcnow()
            return session

    def clear(self, chat_id, user_id):
        with self._lock:
            self._sessions.pop((str(chat_id), str(user_id)), None)

    def main_menu(self, chat_id, user_id, greeting=""):
        self._session(chat_id, user_id)
        prefix = (greeting + "\n\n") if greeting else ""
        return TelegramReply(prefix + "🏠 *MENU UTAMA FINANCE FAMILY*\nPilih kebutuhan Anda:", self._keyboard([
            [("📊 Ringkasan Keuangan", "wealth:summary"), ("💰 Catat Pengeluaran", "wealth:expense")],
            [("💵 Catat Pemasukan", "wealth:income"), ("🏦 Kelola Akun & Saldo", "wealth:accounts")],
            [("🔄 Transfer Dana", "wealth:transfer"), ("📈 Investasi", "wealth:investment")],
            [("📋 Riwayat & Laporan", "wealth:reports"), ("⚙️ Pengaturan", "wealth:settings")],
        ]))

    def handle_callback(self, chat_id, user_id, callback_data, update_id=""):
        session = self._session(chat_id, user_id)
        if callback_data == "wealth:confirm" and session.flow in {"wealth:account:add", "wealth:investment:add"} and session.step >= (6 if session.flow == "wealth:account:add" else 5):
            payload = dict(session.values)
            if session.flow == "wealth:investment:add":
                payload["account_type"] = "investment"
            self.clear(chat_id, user_id)
            return TelegramReply("✅ Akun siap disimpan.", self._keyboard([[('🏠 Menu Utama', 'wealth:home')]]), action="account_create", payload=payload)
        if callback_data == "wealth:confirm" and session.flow in {"wealth:transfer:start", "wealth:cash:withdraw"} and session.step >= 4:
            payload = dict(session.values)
            self.clear(chat_id, user_id)
            return TelegramReply("✅ Mutasi siap disimpan.", self._keyboard([[('🏠 Menu Utama', 'wealth:home')]]), action="operation_create", payload=payload)
        if callback_data == "wealth:confirm" and session.flow in {"wealth:account:reconcile", "wealth:account:archive", "wealth:settings:default", "wealth:investment:update"} and session.step >= 1:
            payload = dict(session.values)
            self.clear(chat_id, user_id)
            action = {"wealth:account:reconcile": "reconcile", "wealth:account:archive": "archive", "wealth:settings:default": "default_account", "wealth:investment:update": "reconcile"}[session.flow]
            return TelegramReply("✅ Perubahan siap disimpan.", self._keyboard([[('🏠 Menu Utama', 'wealth:home')]]), action=action, payload=payload)
        if callback_data in {"wealth:home", "wealth:cancel", "wealth:back"}:
            self.clear(chat_id, user_id)
            return self.main_menu(chat_id, user_id)
        if callback_data in {"wealth:account:add", "wealth:cash:withdraw", "wealth:account:reconcile", "wealth:account:archive", "wealth:investment:add", "wealth:investment:update", "wealth:settings:default"}:
            session.flow, session.step, session.values = callback_data, 0, {}
            prompts = {"wealth:account:add": "Ketik nama akun, contoh: `Mandiri Operasional`", "wealth:cash:withdraw": "Ketik ID akun bank sumber", "wealth:account:reconcile": "Ketik ID akun yang akan direkonsiliasi", "wealth:account:archive": "Ketik ID akun yang akan diarsipkan", "wealth:investment:add": "Ketik nama instrumen, contoh: `SBN ST014`", "wealth:investment:update": "Ketik ID akun investasi", "wealth:settings:default": "Ketik jenis transaksi: `income` atau `expense`"}
            return TelegramReply("📝 " + prompts[callback_data], self._keyboard([[('❌ Batalkan', 'wealth:cancel'), ('🏠 Menu Utama', 'wealth:home')]]), action="input")
        if callback_data == "wealth:transfer:start":
            session.flow, session.step, session.values = callback_data, 0, {}
            return TelegramReply("📝 Ketik ID akun sumber", self._keyboard([[('❌ Batalkan', 'wealth:cancel'), ('🏠 Menu Utama', 'wealth:home')]]), action="input")
        screens = {
            "wealth:summary": ("📊 *RINGKASAN KEUANGAN*", "summary"),
            "wealth:expense": ("💰 *CATAT PENGELUARAN*\nGunakan perintah cepat untuk transaksi rutin.", "quick"),
            "wealth:income": ("💵 *CATAT PEMASUKAN*\nGunakan perintah cepat untuk transaksi rutin.", "quick"),
            "wealth:accounts": ("🏦 *KELOLA AKUN & SALDO*\nPilih operasi yang ingin dilakukan.", "accounts"),
            "wealth:account:list": ("🏦 *SALDO SEMUA AKUN*", "accounts"),
            "wealth:transfer": ("🔄 *TRANSFER DANA*\nGunakan perintah cepat `/transfer` untuk transaksi langsung.", "quick"),
            "wealth:investment": ("📈 *INVESTASI*\nKelola SBN, crypto, saham, dan emas.", "investment"),
            "wealth:investment:list": ("📈 *PORTOFOLIO INVESTASI*", "investment"),
            "wealth:reports": ("📋 *RIWAYAT & LAPORAN*", "reports"),
            "wealth:settings": ("⚙️ *PENGATURAN*", "settings"),
        }
        if callback_data not in screens:
            return self.main_menu(chat_id, user_id)
        title, screen = screens[callback_data]
        session.screen = screen
        keyboards = {
            "accounts": [("➕ Tambah Akun", "wealth:account:add"), ("💳 Lihat Semua Saldo", "wealth:account:list"), ("🏧 Tarik Tunai ATM", "wealth:cash:withdraw"), ("🔁 Rekonsiliasi Saldo", "wealth:account:reconcile"), ("🗄️ Arsipkan Akun", "wealth:account:archive")],
            "investment": [("➕ Tambah Investasi", "wealth:investment:add"), ("💹 Perbarui Nilai", "wealth:investment:update"), ("📊 Lihat Portofolio", "wealth:investment:list")],
            "reports": [("💎 Total Kekayaan", "wealth:summary"), ("🏦 Saldo Semua Akun", "wealth:account:list"), ("🧾 Mutasi Terakhir", "wealth:report:recent")],
            "settings": [("⭐ Atur Akun Default", "wealth:settings:default"), ("❓ Panduan", "wealth:help")],
        }
        if callback_data.endswith(":list") or callback_data in {"wealth:summary", "wealth:report:recent"}:
            action = "account_list" if callback_data == "wealth:account:list" else screen
            return TelegramReply(title, self._keyboard([[("⬅️ Kembali", "wealth:back"), ("🏠 Menu Utama", "wealth:home")]]), action=action, payload={"update_id": update_id})
        rows = [[item] for item in keyboards.get(screen, [])]
        if callback_data == "wealth:transfer":
            rows.insert(0, [("🧾 Mulai Transfer Terpandu", "wealth:transfer:start")])
        rows += [[("⬅️ Kembali", "wealth:back"), ("🏠 Menu Utama", "wealth:home")]]
        return TelegramReply(title, self._keyboard(rows), action=screen)

    def handle_text(self, chat_id, user_id, text, update_id=""):
        session = self._session(chat_id, user_id)
        if not session.flow:
            return None
        value = text.strip()
        if session.flow == "wealth:account:add":
            fields = ("name", "account_type", "provider", "holder_name", "account_identifier", "opening_balance")
            session.values[fields[session.step]] = value
        elif session.flow == "wealth:investment:add":
            fields = ("name", "provider", "holder_name", "account_identifier", "opening_balance")
            session.values[fields[session.step]] = value
        elif session.flow in {"wealth:transfer:start", "wealth:cash:withdraw"}:
            fields = ("source_account_id", "destination_account_id", "amount", "description")
            session.values[fields[session.step]] = value
            if session.flow == "wealth:cash:withdraw":
                session.values["operation_type"] = "cash_withdrawal"
        elif session.flow == "wealth:account:reconcile":
            fields = ("account_id", "actual_balance", "reason")
            session.values[fields[session.step]] = value
        elif session.flow == "wealth:account:archive":
            session.values["account_id"] = value
        elif session.flow == "wealth:settings:default":
            fields = ("operation_kind", "account_id")
            session.values[fields[session.step]] = value
        elif session.flow == "wealth:investment:update":
            fields = ("account_id", "actual_balance", "reason")
            session.values[fields[session.step]] = value
        else:
            session.values[f"step_{session.step}"] = value
        session.step += 1
        if session.flow == "wealth:account:add" and session.step >= 6:
            return TelegramReply("🔎 *KONFIRMASI AKUN BARU*\n\n" + "\n".join(f"• {key}: `{val}`" for key, val in session.values.items()) + "\n\nSimpan akun ini?", self._keyboard([[('✅ Konfirmasi', 'wealth:confirm'), ('❌ Batalkan', 'wealth:cancel')]]), action="confirm", payload=dict(session.values))
        if session.flow == "wealth:investment:add" and session.step >= 5:
            values = dict(session.values)
            values["account_type"] = "investment"
            return TelegramReply("🔎 *KONFIRMASI INVESTASI*\n\n" + "\n".join(f"• {key}: `{val}`" for key, val in values.items()) + "\n\nSimpan instrumen ini?", self._keyboard([[('✅ Konfirmasi', 'wealth:confirm'), ('❌ Batalkan', 'wealth:cancel')]]), action="confirm", payload=values)
        if session.flow in {"wealth:transfer:start", "wealth:cash:withdraw"} and session.step >= 4:
            return TelegramReply("🔎 *KONFIRMASI MUTASI*\n\n" + "\n".join(f"• {key}: `{val}`" for key, val in session.values.items()) + "\n\nProses mutasi ini?", self._keyboard([[('✅ Konfirmasi', 'wealth:confirm'), ('❌ Batalkan', 'wealth:cancel')]]), action="confirm", payload=dict(session.values))
        if session.flow in {"wealth:account:reconcile", "wealth:investment:update"} and session.step >= 3:
            return TelegramReply("🔎 *KONFIRMASI SALDO AKTUAL*\n\n" + "\n".join(f"• {key}: `{val}`" for key, val in session.values.items()) + "\n\nSimpan perubahan?", self._keyboard([[('✅ Konfirmasi', 'wealth:confirm'), ('❌ Batalkan', 'wealth:cancel')]]), action="confirm", payload=dict(session.values))
        if session.flow == "wealth:account:archive" and session.step >= 1:
            return TelegramReply("⚠️ *KONFIRMASI ARSIP AKUN*\n\nAkun ID `{}` akan diarsipkan dan tidak dipakai untuk transaksi baru.\n\nLanjutkan?".format(value), self._keyboard([[('✅ Konfirmasi', 'wealth:confirm'), ('❌ Batalkan', 'wealth:cancel')]]), action="confirm", payload=dict(session.values))
        if session.flow == "wealth:settings:default" and session.step >= 2:
            return TelegramReply("⭐ *KONFIRMASI AKUN DEFAULT*\n\nJenis: `{}`\nAkun ID: `{}`\n\nSimpan?".format(session.values["operation_kind"], session.values["account_id"]), self._keyboard([[('✅ Konfirmasi', 'wealth:confirm'), ('❌ Batalkan', 'wealth:cancel')]]), action="confirm", payload=dict(session.values))
        return TelegramReply("✅ Data diterima. Langkah berikutnya akan diproses setelah implementasi alur lengkap.", self._keyboard([[("❌ Batalkan", "wealth:cancel"), ("🏠 Menu Utama", "wealth:home")]]), action="input", payload=session.values)
