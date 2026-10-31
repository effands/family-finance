"""Atomic account and double-entry ledger operations."""

from dataclasses import dataclass
from datetime import date, datetime
from uuid import uuid4

from .database import Database


class WealthError(ValueError):
    pass


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
            account = self._account(conn, chat_id, account_id, active=False)
            if not account["is_active"]:
                return
            conn.execute("UPDATE financial_accounts SET is_active=0, updated_at=? WHERE id=? AND chat_id=?", (datetime.now().isoformat(), account_id, chat_id))

    def set_default_account(self, chat_id, operation_kind, account_id):
        with self.db._conn() as conn:
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
            self._account(conn, chat_id, account_id)
            current = self._balance(conn, chat_id, account_id)
            difference = actual_balance - current
            if difference == 0:
                return self._operation(conn, chat_id, "adjustment", "Rekonsiliasi: " + reason, "", effective_date, actor_user_id, actor_username, "reconcile:%s:%s" % (account_id, effective_date.isoformat())) and self._get_operation(conn, conn.execute("SELECT id FROM ledger_operations WHERE chat_id=? AND idempotency_key=?", (chat_id, "reconcile:%s:%s" % (account_id, effective_date.isoformat()))).fetchone()["id"])
            op_id = self._operation(conn, chat_id, "adjustment", "Rekonsiliasi: " + reason, "", effective_date, actor_user_id, actor_username, "reconcile:%s:%s" % (account_id, effective_date.isoformat()))
            self._entry(conn, op_id, chat_id, account_id, "credit" if difference > 0 else "debit", abs(difference), "adjustment", reason, "Penyesuaian Saldo", effective_date)
            return self._get_operation(conn, op_id)

    def _account(self, conn, chat_id, account_id, *, active=True):
        row = conn.execute("SELECT * FROM financial_accounts WHERE id=? AND chat_id=?", (account_id, chat_id)).fetchone()
        if not row or (active and not row["is_active"]):
            raise WealthError("Akun tidak ditemukan atau tidak aktif")
        return row

    def _balance(self, conn, chat_id, account_id, as_of=None):
        account = self._account(conn, chat_id, account_id, active=False)
        q = """SELECT COALESCE(SUM(CASE WHEN e.direction='credit' THEN e.amount ELSE -e.amount END), 0) AS movement
               FROM ledger_entries e JOIN ledger_operations o ON o.id=e.operation_id
               WHERE e.chat_id=? AND e.account_id=?"""
        params = [chat_id, account_id]
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
            self._account(conn, chat_id, account_id)
            op_id = self._operation(conn, chat_id, "income", description, category, transaction_date, actor_user_id, actor_username, idempotency_key)
            if conn.execute("SELECT COUNT(*) AS n FROM ledger_entries WHERE operation_id=?", (op_id,)).fetchone()["n"] == 0:
                self._entry(conn, op_id, chat_id, account_id, "credit", amount, "income", description, category, transaction_date)
            return self._get_operation(conn, op_id)

    def create_expense(self, chat_id, account_id, amount, description, category, transaction_date, actor_user_id, actor_username, idempotency_key=None):
        self._validate_amount(amount)
        with self.db._conn() as conn:
            self._account(conn, chat_id, account_id)
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
            self._account(conn, chat_id, source_account_id)
            self._account(conn, chat_id, destination_account_id)
            total = amount + fee_amount
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
            original = conn.execute("SELECT * FROM ledger_operations WHERE id=? AND chat_id=?", (operation_id, chat_id)).fetchone()
            if not original:
                raise WealthError("Operasi tidak ditemukan")
            if original["reversed_operation_id"]:
                raise WealthError("Operasi sudah dibatalkan")
            op_id = self._operation(conn, chat_id, "reversal", reason, "", date.today(), actor_user_id, actor_user_id, "reversal:" + operation_id)
            entries = conn.execute("SELECT * FROM ledger_entries WHERE operation_id=?", (operation_id,)).fetchall()
            for entry in entries:
                self._entry(conn, op_id, chat_id, entry["account_id"], "credit" if entry["direction"] == "debit" else "debit", entry["amount"], "reversal", reason, entry["category"], date.today())
            conn.execute("UPDATE ledger_operations SET reversed_operation_id=? WHERE id=?", (op_id, operation_id))
            return self._get_operation(conn, op_id)

    @staticmethod
    def _get_operation(conn, op_id):
        from .models import LedgerOperation
        row = conn.execute("SELECT * FROM ledger_operations WHERE id=?", (op_id,)).fetchone()
        return LedgerOperation(row["id"], row["chat_id"], row["operation_type"], row["description"], date.fromisoformat(row["transaction_date"]), row["actor_user_id"], row["actor_username"], row["idempotency_key"], row["reversed_operation_id"])

    def get_account_balances(self, chat_id, as_of=None):
        with self.db._conn() as conn:
            rows = conn.execute("SELECT * FROM financial_accounts WHERE chat_id=? AND is_active=1 ORDER BY name", (chat_id,)).fetchall()
            return [AccountBalance(r["id"], r["name"], r["account_type"], self._balance(conn, chat_id, r["id"], as_of)) for r in rows]

    def get_wealth_summary(self, chat_id, as_of=None):
        balances = self.get_account_balances(chat_id, as_of)
        investments = sum(x.balance for x in balances if x.account_type == "investment")
        cash = sum(x.balance for x in balances if x.account_type == "cash")
        total = sum(x.balance for x in balances)
        liquid = total - investments
        with self.db._conn() as conn:
            rows = conn.execute("SELECT operation_type, SUM(e.amount) AS amount FROM ledger_operations o JOIN ledger_entries e ON e.operation_id=o.id WHERE o.chat_id=? AND o.reversed_operation_id IS NULL GROUP BY operation_type", (chat_id,)).fetchall()
        totals = {r["operation_type"]: r["amount"] or 0 for r in rows}
        return WealthSummary(total, liquid, investments, cash, totals.get("income", 0), totals.get("expense", 0))
