"""Atomic account and double-entry ledger operations."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4

from .database import Database


class WealthError(ValueError):
    pass


def parse_idr_amount(value: str, allow_zero: bool = False) -> int:
    """Parse Indonesian whole-rupiah input without silently changing magnitude."""
    raw = str(value or "").strip().replace("Rp", "").replace("rp", "").replace(" ", "")
    if not raw or raw.startswith("-"):
        raise WealthError("Nominal harus berupa rupiah bulat positif")
    if "," in raw:
        raise WealthError("Nominal rupiah tidak boleh memakai pecahan")
    if "." in raw:
        parts = raw.split(".")
        if any(not p.isdigit() for p in parts) or any(len(p) != 3 for p in parts[1:]):
            raise WealthError("Format nominal tidak valid; gunakan contoh 1.500.000")
        raw = "".join(parts)
    if not raw.isdigit():
        raise WealthError("Nominal harus berupa angka rupiah")
    amount = int(raw)
    if amount < 0 or (amount == 0 and not allow_zero):
        raise WealthError("Nominal harus lebih besar dari nol")
    return amount


class InsufficientFundsError(WealthError):
    pass


@dataclass(frozen=True)
class AccountBalance:
    account_id: int
    account_name: str
    account_type: str
    balance: int


@dataclass(frozen=True)
class WealthSummary:
    total_wealth: int
    liquid_assets: int
    investments: int
    cash: int
    income: int
    expense: int


class WealthLedger:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _validate_amount(amount: int):
        if not isinstance(amount, int) or amount <= 0:
            raise WealthError("Nominal harus berupa bilangan bulat positif")

    def archive_account(self, chat_id, account_id, actor_user_id):
        with self.db._conn() as conn:
            self._begin(conn)
            account = self._account(conn, chat_id, account_id, active=False)
            if not account["is_active"]:
                return
            conn.execute("UPDATE financial_accounts SET is_active=0, updated_at=? WHERE id=? AND chat_id=?", (datetime.now().isoformat(), account_id, chat_id))

    def set_default_account(self, chat_id, operation_kind, account_id):
        with self.db._conn() as conn:
            self._begin(conn)
            self._account(conn, chat_id, account_id)
            if operation_kind not in {"income", "expense", "transfer", "cash_withdrawal"}:
                raise WealthError("Jenis default akun tidak valid")
            conn.execute("INSERT OR REPLACE INTO account_preferences(chat_id, operation_kind, account_id) VALUES (?,?,?)", (chat_id, operation_kind, account_id))

    def get_default_account(self, chat_id, operation_kind):
        with self.db._conn() as conn:
            row = conn.execute("SELECT account_id FROM account_preferences WHERE chat_id=? AND operation_kind=?", (chat_id, operation_kind)).fetchone()
            return self.db.get_account(row["account_id"], chat_id) if row else None

    def reconcile_account(self, chat_id, account_id, actual_balance, reason, effective_date, actor_user_id, actor_username):
        if not isinstance(actual_balance, int) or actual_balance < 0:
            raise WealthError("Saldo aktual harus nol atau lebih")
        with self.db._conn() as conn:
            self._begin(conn)
            self._account(conn, chat_id, account_id)
            key = "reconcile:%s:%s" % (account_id, effective_date.isoformat())
            existing = conn.execute("SELECT id FROM ledger_operations WHERE chat_id=? AND idempotency_key=?", (chat_id, key)).fetchone()
            if existing:
                return self._get_operation(conn, existing["id"])
            current = self._balance(conn, chat_id, account_id, effective_date)
            difference = actual_balance - current
            if difference == 0:
                op_id = self._operation(conn, chat_id, "adjustment", "Rekonsiliasi: " + reason, "", effective_date, actor_user_id, actor_username, key)
                return self._get_operation(conn, op_id)
            op_id = self._operation(conn, chat_id, "adjustment", "Rekonsiliasi: " + reason, "", effective_date, actor_user_id, actor_username, key)
            self._entry(conn, op_id, chat_id, account_id, "credit" if difference > 0 else "debit", abs(difference), "adjustment", reason, "Penyesuaian Saldo", effective_date)
            return self._get_operation(conn, op_id)

    def _account(self, conn, chat_id, account_id, *, active=True):
        row = conn.execute("SELECT * FROM financial_accounts WHERE id=? AND chat_id=?", (account_id, chat_id)).fetchone()
        if not row or (active and not row["is_active"]):
            raise WealthError("Akun tidak ditemukan atau tidak aktif")
        return row

    @staticmethod
    def _begin(conn):
        conn.execute("BEGIN IMMEDIATE")

    @staticmethod
    def _check_date(account, tx_date):
        if tx_date < date.fromisoformat(account["opening_balance_date"]):
            raise WealthError("Tanggal mutasi tidak boleh sebelum tanggal saldo awal")

    def _balance(self, conn, chat_id, account_id, as_of=None):
        account = self._account(conn, chat_id, account_id, active=False)
        q = """SELECT COALESCE(SUM(CASE WHEN e.direction='credit' THEN e.amount ELSE -e.amount END), 0) AS movement
               FROM ledger_entries e JOIN ledger_operations o ON o.id=e.operation_id
               WHERE e.chat_id=? AND e.account_id=? AND e.transaction_date>=?"""
        params = [chat_id, account_id, account["opening_balance_date"]]
        if as_of:
            q += " AND e.transaction_date<=?"
            params.append(as_of.isoformat())
        movement = conn.execute(q, params).fetchone()["movement"]
        opening = account["opening_balance"] if not as_of or as_of >= date.fromisoformat(account["opening_balance_date"]) else 0
        return opening + movement

    def _operation(self, conn, chat_id, operation_type, description, category, tx_date, actor_user_id, actor_username, idempotency_key):
        if idempotency_key:
            row = conn.execute("SELECT * FROM ledger_operations WHERE chat_id=? AND idempotency_key=?", (chat_id, idempotency_key)).fetchone()
            if row:
                return row["id"]
        op_id = uuid4().hex
        conn.execute("""INSERT INTO ledger_operations
            (id,chat_id,operation_type,description,category,transaction_date,actor_user_id,actor_username,idempotency_key,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (op_id, chat_id, operation_type, description, category, tx_date.isoformat(), actor_user_id, actor_username, idempotency_key, datetime.now().isoformat()))
        return op_id

    def _entry(self, conn, op_id, chat_id, account_id, direction, amount, entry_type, description, category, tx_date):
        conn.execute("""INSERT INTO ledger_entries
            (operation_id,chat_id,account_id,direction,amount,entry_type,description,category,transaction_date)
            VALUES (?,?,?,?,?,?,?,?,?)""", (op_id, chat_id, account_id, direction, amount, entry_type, description, category, tx_date.isoformat()))

    def create_income(self, chat_id, account_id, amount, description, category, transaction_date, actor_user_id, actor_username, idempotency_key=None):
        self._validate_amount(amount)
        with self.db._conn() as conn:
            self._begin(conn)
            self._account(conn, chat_id, account_id)
            account = self._account(conn, chat_id, account_id)
            self._check_date(account, transaction_date)
            op_id = self._operation(conn, chat_id, "income", description, category, transaction_date, actor_user_id, actor_username, idempotency_key)
            if conn.execute("SELECT COUNT(*) AS n FROM ledger_entries WHERE operation_id=?", (op_id,)).fetchone()["n"] == 0:
                self._entry(conn, op_id, chat_id, account_id, "credit", amount, "income", description, category, transaction_date)
            return self._get_operation(conn, op_id)

    def create_expense(self, chat_id, account_id, amount, description, category, transaction_date, actor_user_id, actor_username, idempotency_key=None):
        self._validate_amount(amount)
        with self.db._conn() as conn:
            self._begin(conn)
            account = self._account(conn, chat_id, account_id)
            self._check_date(account, transaction_date)
            if idempotency_key:
                existing = conn.execute("SELECT id FROM ledger_operations WHERE chat_id=? AND idempotency_key=?", (chat_id, idempotency_key)).fetchone()
                if existing:
                    return self._get_operation(conn, existing["id"])
            if self._balance(conn, chat_id, account_id) < amount:
                raise InsufficientFundsError("Saldo akun tidak mencukupi")
            op_id = self._operation(conn, chat_id, "expense", description, category, transaction_date, actor_user_id, actor_username, idempotency_key)
            if conn.execute("SELECT COUNT(*) AS n FROM ledger_entries WHERE operation_id=?", (op_id,)).fetchone()["n"] == 0:
                self._entry(conn, op_id, chat_id, account_id, "debit", amount, "expense", description, category, transaction_date)
            return self._get_operation(conn, op_id)

    def create_transfer(self, chat_id, source_account_id, destination_account_id, amount, description, transaction_date, actor_user_id, actor_username, operation_type="transfer", fee_amount=0, idempotency_key=None):
        self._validate_amount(amount)
        if source_account_id == destination_account_id:
            raise WealthError("Akun sumber dan tujuan harus berbeda")
        if fee_amount < 0:
            raise WealthError("Biaya tidak boleh negatif")
        with self.db._conn() as conn:
            self._begin(conn)
            source = self._account(conn, chat_id, source_account_id)
            destination = self._account(conn, chat_id, destination_account_id)
            self._check_date(source, transaction_date)
            self._check_date(destination, transaction_date)
            if idempotency_key:
                existing = conn.execute("SELECT id FROM ledger_operations WHERE chat_id=? AND idempotency_key=?", (chat_id, idempotency_key)).fetchone()
                if existing:
                    return self._get_operation(conn, existing["id"])
            total = amount + fee_amount
            if operation_type not in {"transfer", "cash_withdrawal"}:
                raise WealthError("Jenis transfer tidak valid")
            if operation_type == "cash_withdrawal" and destination["account_type"] != "cash":
                raise WealthError("Tarik tunai harus masuk ke akun Cash")
            if self._balance(conn, chat_id, source_account_id) < total:
                raise InsufficientFundsError("Saldo akun sumber tidak mencukupi")
            op_id = self._operation(conn, chat_id, operation_type, description, "", transaction_date, actor_user_id, actor_username, idempotency_key)
            if conn.execute("SELECT COUNT(*) AS n FROM ledger_entries WHERE operation_id=?", (op_id,)).fetchone()["n"] == 0:
                self._entry(conn, op_id, chat_id, source_account_id, "debit", amount, operation_type, description, "", transaction_date)
                self._entry(conn, op_id, chat_id, destination_account_id, "credit", amount, operation_type, description, "", transaction_date)
                if fee_amount:
                    self._entry(conn, op_id, chat_id, source_account_id, "debit", fee_amount, "fee", "Biaya " + description, "Biaya", transaction_date)
            return self._get_operation(conn, op_id)

    def reverse_operation(self, chat_id, operation_id, actor_user_id, reason):
        with self.db._conn() as conn:
            self._begin(conn)
            original = conn.execute("SELECT * FROM ledger_operations WHERE id=? AND chat_id=?", (operation_id, chat_id)).fetchone()
            if not original:
                raise WealthError("Operasi tidak ditemukan")
            if original["reversed_operation_id"]:
                raise WealthError("Operasi sudah dibatalkan")
            op_id = self._operation(conn, chat_id, "reversal", reason, "", date.today(), actor_user_id, actor_user_id, "reversal:" + operation_id)
            entries = conn.execute("SELECT * FROM ledger_entries WHERE operation_id=?", (operation_id,)).fetchall()
            for entry in entries:
                if entry["direction"] == "credit" and self._balance(conn, chat_id, entry["account_id"]) < entry["amount"]:
                    raise InsufficientFundsError("Pembatalan ditolak karena saldo akun tujuan sudah terpakai")
            for entry in entries:
                self._entry(conn, op_id, chat_id, entry["account_id"], "credit" if entry["direction"] == "debit" else "debit", entry["amount"], "reversal", reason, entry["category"], date.today())
            conn.execute("UPDATE ledger_operations SET reversed_operation_id=? WHERE id=?", (op_id, operation_id))
            return self._get_operation(conn, op_id)

    @staticmethod
    def _get_operation(conn, op_id):
        from .models import LedgerOperation
        row = conn.execute("SELECT * FROM ledger_operations WHERE id=?", (op_id,)).fetchone()
        return LedgerOperation(row["id"], row["chat_id"], row["operation_type"], row["description"], date.fromisoformat(row["transaction_date"]), row["actor_user_id"], row["actor_username"], row["idempotency_key"], row["reversed_operation_id"])

    def get_account_balances(self, chat_id, as_of=None, include_archived=True):
        with self.db._conn() as conn:
            as_of = as_of or date.today()
            q = "SELECT * FROM financial_accounts WHERE chat_id=?"
            if not include_archived:
                q += " AND is_active=1"
            q += " ORDER BY name"
            rows = conn.execute(q, (chat_id,)).fetchall()
            return [AccountBalance(r["id"], r["name"], r["account_type"], self._balance(conn, chat_id, r["id"], as_of)) for r in rows]

    def get_wealth_summary(self, chat_id, as_of=None):
        balances = self.get_account_balances(chat_id, as_of)
        investments = sum(x.balance for x in balances if x.account_type == "investment")
        cash = sum(x.balance for x in balances if x.account_type == "cash")
        total = sum(x.balance for x in balances)
        liquid = total - investments
        with self.db._conn() as conn:
            rows = conn.execute("""SELECT o.operation_type, e.entry_type, e.direction, SUM(e.amount) AS amount
                FROM ledger_operations o JOIN ledger_entries e ON e.operation_id=o.id
                WHERE o.chat_id=? AND o.reversed_operation_id IS NULL AND e.transaction_date<=?
                GROUP BY o.operation_type, e.entry_type, e.direction""", (chat_id, (as_of or date.today()).isoformat())).fetchall()
        income = sum(r["amount"] for r in rows if r["operation_type"] == "income" and r["direction"] == "credit")
        expense = sum(r["amount"] for r in rows if r["entry_type"] in {"expense", "fee"} and r["direction"] == "debit")
        return WealthSummary(total, liquid, investments, cash, income, expense)

    def list_operations(self, chat_id, limit=100):
        with self.db._conn() as conn:
            rows = conn.execute("""SELECT o.*, COUNT(e.id) AS entry_count,
                COALESCE(SUM(CASE WHEN e.direction='debit' THEN e.amount ELSE 0 END),0) AS debits
                FROM ledger_operations o LEFT JOIN ledger_entries e ON e.operation_id=o.id
                WHERE o.chat_id=? GROUP BY o.id ORDER BY o.transaction_date DESC, o.created_at DESC LIMIT ?""", (chat_id, limit)).fetchall()
            return [dict(r) for r in rows]

    def attribute_legacy_transaction(self, chat_id, transaction_id, account_id, actor_user_id, actor_username):
        tx = self.db.get_transaction(transaction_id)
        if not tx or str(tx.chat_id) != str(chat_id):
            raise WealthError("Transaksi legacy tidak ditemukan")
        with self.db._conn() as conn:
            self._begin(conn)
            linked = conn.execute("SELECT operation_id FROM legacy_ledger_links WHERE transaction_id=? AND chat_id=?", (transaction_id, chat_id)).fetchone()
            if linked:
                return self._get_operation(conn, linked["operation_id"])
        key = f"legacy:{transaction_id}"
        if tx.type == "income":
            op = self.create_income(chat_id, account_id, tx.amount, tx.description, tx.category, tx.transaction_date, actor_user_id, actor_username, idempotency_key=key)
        else:
            op = self.create_expense(chat_id, account_id, tx.amount, tx.description, tx.category, tx.transaction_date, actor_user_id, actor_username, idempotency_key=key)
        with self.db._conn() as conn:
            self._begin(conn)
            conn.execute("INSERT OR IGNORE INTO legacy_ledger_links(transaction_id,chat_id,operation_id,linked_at) VALUES (?,?,?,?)", (transaction_id, chat_id, op.id, datetime.now().isoformat()))
        return op
