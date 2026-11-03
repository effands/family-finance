import sqlite3
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from .categorizer import default_categories
from .models import Category, FinancialAccount, Transaction, TransactionFilters


class Database:
    def __init__(self, path: str):
        self.path = path

    def _conn(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    def initialize(self):
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    username TEXT,
                    chat_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    amount INTEGER NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL,
                    transaction_date TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS categories (
                    name TEXT PRIMARY KEY,
                    keywords TEXT NOT NULL,
                    emoji TEXT NOT NULL,
                    type TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transaction_details (
                    transaction_id INTEGER PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
                    details_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transaction_items (
                    id INTEGER PRIMARY KEY,
                    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
                    name TEXT NOT NULL, quantity REAL NOT NULL DEFAULT 1,
                    unit TEXT, unit_price INTEGER NOT NULL DEFAULT 0,
                    subtotal INTEGER NOT NULL DEFAULT 0, category TEXT NOT NULL DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS ix_items_transaction ON transaction_items(transaction_id);
                CREATE TABLE IF NOT EXISTS financial_accounts (
                    id INTEGER PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    account_type TEXT NOT NULL CHECK (account_type IN ('bank','ewallet','cash','investment')),
                    provider TEXT NOT NULL DEFAULT '',
                    holder_name TEXT NOT NULL DEFAULT '',
                    account_identifier TEXT NOT NULL DEFAULT '',
                    currency TEXT NOT NULL DEFAULT 'IDR' CHECK (currency = 'IDR'),
                    opening_balance INTEGER NOT NULL CHECK (opening_balance >= 0),
                    opening_balance_date TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    notes TEXT NOT NULL DEFAULT '',
                    creation_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_accounts_chat_active ON financial_accounts(chat_id, is_active);
                CREATE TABLE IF NOT EXISTS ledger_operations (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    operation_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    transaction_date TEXT NOT NULL,
                    actor_user_id TEXT NOT NULL,
                    actor_username TEXT NOT NULL,
                    idempotency_key TEXT,
                    reversed_operation_id TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(chat_id, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id INTEGER PRIMARY KEY,
                    operation_id TEXT NOT NULL REFERENCES ledger_operations(id),
                    chat_id TEXT NOT NULL,
                    account_id INTEGER NOT NULL REFERENCES financial_accounts(id),
                    direction TEXT NOT NULL CHECK (direction IN ('debit','credit')),
                    amount INTEGER NOT NULL CHECK (amount > 0),
                    entry_type TEXT NOT NULL,
                    description TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '',
                    transaction_date TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_ledger_account_date ON ledger_entries(chat_id, account_id, transaction_date);
                CREATE INDEX IF NOT EXISTS ix_ledger_group ON ledger_entries(chat_id, operation_id);
                CREATE TABLE IF NOT EXISTS account_preferences (
                    chat_id TEXT NOT NULL,
                    operation_kind TEXT NOT NULL,
                    account_id INTEGER NOT NULL REFERENCES financial_accounts(id),
                    PRIMARY KEY (chat_id, operation_kind)
                );
                CREATE TABLE IF NOT EXISTS user_account_preferences (
                    chat_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    operation_kind TEXT NOT NULL,
                    account_id INTEGER NOT NULL REFERENCES financial_accounts(id),
                    PRIMARY KEY (chat_id, user_id, operation_kind)
                );
                CREATE TABLE IF NOT EXISTS legacy_ledger_links (
                    transaction_id INTEGER PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    linked_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_tx_chat_date ON transactions(chat_id, transaction_date);
                CREATE INDEX IF NOT EXISTS ix_tx_user_created ON transactions(user_id, created_at);
                PRAGMA journal_mode=WAL;
            """)
            for x in default_categories():
                c.execute("INSERT OR IGNORE INTO categories VALUES (?,?,?,?)", (x.name, ",".join(x.keywords), x.emoji, x.type))
            columns = {row[1] for row in c.execute("PRAGMA table_info(financial_accounts)").fetchall()}
            if "creation_key" not in columns:
                c.execute("ALTER TABLE financial_accounts ADD COLUMN creation_key TEXT")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_accounts_creation_key ON financial_accounts(chat_id, creation_key) WHERE creation_key IS NOT NULL")

    def add_transaction(self, x: Transaction) -> Transaction:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO transactions(user_id,username,chat_id,type,amount,description,category,transaction_date,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (x.user_id, x.username, x.chat_id, x.type, x.amount, x.description, x.category, x.transaction_date.isoformat(), x.created_at.isoformat()),
            )
            return Transaction(cur.lastrowid, x.user_id, x.username, x.chat_id, x.type, x.amount, x.description, x.category, x.transaction_date, x.created_at)

    def add_transaction_with_details(self, x: Transaction, details: dict) -> Transaction:
        """Atomically create a transaction and its receipt metadata/items."""
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO transactions(user_id,username,chat_id,type,amount,description,category,transaction_date,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (x.user_id, x.username, x.chat_id, x.type, x.amount, x.description, x.category, x.transaction_date.isoformat(), x.created_at.isoformat()),
            )
            tx_id = cur.lastrowid
            c.execute("INSERT INTO transaction_details(transaction_id, details_json) VALUES (?,?)", (tx_id, json.dumps(details, ensure_ascii=False)))
            c.executemany("INSERT INTO transaction_items(transaction_id,name,quantity,unit,unit_price,subtotal,category) VALUES (?,?,?,?,?,?,?)", [(tx_id, i["name"], i["quantity"], i.get("unit"), i["unit_price"], i["subtotal"], i.get("category", "")) for i in details.get("items", [])])
            return Transaction(tx_id, x.user_id, x.username, x.chat_id, x.type, x.amount, x.description, x.category, x.transaction_date, x.created_at)

    def add_transaction_details(self, transaction_id: int, details: dict) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO transaction_details(transaction_id, details_json) VALUES (?,?)", (transaction_id, json.dumps(details, ensure_ascii=False)))
            c.execute("DELETE FROM transaction_items WHERE transaction_id=?", (transaction_id,))
            c.executemany("INSERT INTO transaction_items(transaction_id,name,quantity,unit,unit_price,subtotal,category) VALUES (?,?,?,?,?,?,?)", [(transaction_id, i["name"], i["quantity"], i.get("unit"), i["unit_price"], i["subtotal"], i.get("category", "")) for i in details.get("items", [])])

    def list_transaction_items(self, transaction_id: int) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT name,quantity,unit,unit_price,subtotal,category FROM transaction_items WHERE transaction_id=? ORDER BY id", (transaction_id,)).fetchall()]

    @staticmethod
    def _account_from_row(row):
        if not row:
            return None
        return FinancialAccount(
            id=row["id"], chat_id=row["chat_id"], name=row["name"],
            account_type=row["account_type"], provider=row["provider"],
            holder_name=row["holder_name"], account_identifier=row["account_identifier"],
            currency=row["currency"], opening_balance=row["opening_balance"],
            opening_balance_date=date.fromisoformat(row["opening_balance_date"]),
            is_active=bool(row["is_active"]), notes=row["notes"],
        )

    def create_account(self, account: FinancialAccount, idempotency_key: str | None = None) -> FinancialAccount:
        if account.currency != "IDR":
            raise ValueError("Akun tahap pertama hanya mendukung IDR")
        if account.opening_balance < 0:
            raise ValueError("Saldo awal harus positif atau nol")
        if account.account_type not in {"bank", "ewallet", "cash", "investment"}:
            raise ValueError("Jenis akun tidak valid")
        now = datetime.now().isoformat()
        with self._conn() as c:
            if idempotency_key:
                existing = c.execute("SELECT * FROM financial_accounts WHERE chat_id=? AND creation_key=?", (account.chat_id, idempotency_key)).fetchone()
                if existing:
                    return self._account_from_row(existing)
            cur = c.execute(
                """INSERT INTO financial_accounts
                (chat_id,name,account_type,provider,holder_name,account_identifier,currency,opening_balance,opening_balance_date,is_active,notes,creation_key,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (account.chat_id, account.name.strip(), account.account_type, account.provider.strip(), account.holder_name.strip(), account.account_identifier.strip(), "IDR", account.opening_balance, account.opening_balance_date.isoformat(), int(account.is_active), account.notes.strip(), idempotency_key, now, now),
            )
            return self._account_from_row(c.execute("SELECT * FROM financial_accounts WHERE id=?", (cur.lastrowid,)).fetchone())

    def list_accounts(self, chat_id: str, include_archived: bool = False) -> list[FinancialAccount]:
        q = "SELECT * FROM financial_accounts WHERE chat_id=?"
        params = [chat_id]
        if not include_archived:
            q += " AND is_active=1"
        q += " ORDER BY name COLLATE NOCASE"
        with self._conn() as c:
            return [self._account_from_row(r) for r in c.execute(q, params).fetchall()]

    def get_account(self, account_id: int, chat_id: str | None = None) -> FinancialAccount | None:
        q = "SELECT * FROM financial_accounts WHERE id=?"
        params = [account_id]
        if chat_id is not None:
            q += " AND chat_id=?"
            params.append(chat_id)
        with self._conn() as c:
            return self._account_from_row(c.execute(q, params).fetchone())

    def update_account_metadata(self, account_id: int, chat_id: str, *, name: str, provider: str, holder_name: str, account_identifier: str) -> FinancialAccount:
        with self._conn() as c:
            c.execute(
                "UPDATE financial_accounts SET name=?, provider=?, holder_name=?, account_identifier=?, updated_at=? WHERE id=? AND chat_id=?",
                (name.strip(), provider.strip(), holder_name.strip(), account_identifier.strip(), datetime.now().isoformat(), account_id, chat_id),
            )
            return self._account_from_row(c.execute("SELECT * FROM financial_accounts WHERE id=? AND chat_id=?", (account_id, chat_id)).fetchone())

    def _row(self, r):
        return (
            Transaction(
                r["id"],
                r["user_id"],
                r["username"],
                r["chat_id"],
                r["type"],
                r["amount"],
                r["description"],
                r["category"],
                date.fromisoformat(r["transaction_date"]),
                datetime.fromisoformat(r["created_at"]),
            )
            if r
            else None
        )

    def get_transaction(self, id):
        with self._conn() as c:
            return self._row(c.execute("SELECT * FROM transactions WHERE id=?", (id,)).fetchone())

    def list_transactions(self, f: TransactionFilters):
        q = "SELECT * FROM transactions WHERE chat_id=?"
        p = [f.chat_id]
        if f.user_id:
            q += " AND user_id=?"
            p.append(f.user_id)
        if f.start:
            q += " AND transaction_date>=?"
            p.append(f.start.isoformat())
        if f.end:
            q += " AND transaction_date<=?"
            p.append(f.end.isoformat())
        if f.transaction_type:
            q += " AND type=?"
            p.append(f.transaction_type)
        if f.category:
            q += " AND category=?"
            p.append(f.category)
        if f.search:
            q += " AND (LOWER(description) LIKE ? OR LOWER(category) LIKE ? OR LOWER(username) LIKE ?)"
            needle = f"%{f.search.lower()}%"
            p.extend([needle, needle, needle])
        sort_map = {
            "transaction_date": "transaction_date",
            "amount": "amount",
            "description": "description",
            "category": "category",
            "type": "type",
            "username": "username",
            "id": "id",
        }
        column = sort_map.get(f.sort_by, "transaction_date")
        direction = "ASC" if f.sort_dir.lower() == "asc" else "DESC"
        q += f" ORDER BY {column} {direction}, id DESC"
        with self._conn() as c:
            return [self._row(r) for r in c.execute(q, p).fetchall()]

    def list_transactions_with_ledger(self, f: TransactionFilters):
        """Return legacy transactions plus wealth-ledger income/expense entries.

        The ledger is authoritative for wealth-linked Telegram entries; projecting
        its income/expense operations here keeps the dashboard and cashflow views
        consistent without duplicating internal transfers.
        """
        rows = self.list_transactions(f)
        q = """SELECT o.id, o.actor_user_id AS user_id, o.actor_username AS username, o.chat_id,
                       CASE WHEN o.operation_type='income' THEN 'income' ELSE 'expense' END AS type,
                       SUM(CASE WHEN (o.operation_type='income' AND e.direction='credit') OR (o.operation_type='expense' AND e.direction='debit') THEN e.amount ELSE 0 END) AS amount,
                       o.description, o.category, o.transaction_date, o.created_at,
                       MAX(CASE WHEN e.direction='debit' THEN a.name END) AS source_account,
                       MAX(CASE WHEN e.direction='credit' THEN a.name END) AS destination_account,
                       MAX(CASE WHEN e.direction='credit' THEN a.provider END) AS destination_provider,
                       MAX(CASE WHEN e.direction='credit' THEN a.account_identifier END) AS destination_identifier
                FROM ledger_operations o
                JOIN ledger_entries e ON e.operation_id=o.id
                LEFT JOIN financial_accounts a ON a.id=e.account_id
                WHERE o.chat_id=? AND o.operation_type IN ('income','expense')
                  AND o.reversed_operation_id IS NULL
                  AND o.id NOT IN (SELECT operation_id FROM legacy_ledger_links WHERE chat_id=?)
                GROUP BY o.id"""
        params = [f.chat_id, f.chat_id]
        if f.start:
            q = q.replace("GROUP BY o.id", "AND o.transaction_date>=? GROUP BY o.id"); params.append(f.start.isoformat())
        if f.end:
            q = q.replace("GROUP BY o.id", "AND o.transaction_date<=? GROUP BY o.id"); params.append(f.end.isoformat())
        with self._conn() as c:
            for r in c.execute(q, params).fetchall():
                item = self._row(r)
                item.detail_data = {key: r[key] for key in ("source_account", "destination_account", "destination_provider", "destination_identifier") if r[key]}
                if f.transaction_type and item.type != f.transaction_type:
                    continue
                if f.category and item.category != f.category:
                    continue
                if f.user_id and item.user_id != f.user_id:
                    continue
                if f.search and not any(f.search.lower() in str(v or '').lower() for v in (item.description, item.category, item.username)):
                    continue
                rows.append(item)
        rows.sort(key=lambda x: (x.transaction_date, x.created_at), reverse=f.sort_dir.lower() != "asc")
        if f.sort_by == "amount": rows.sort(key=lambda x: x.amount, reverse=f.sort_dir.lower() != "asc")
        return rows

    def find_latest_transaction(self, user_id, chat_id, now):
        with self._conn() as c:
            return self._row(
                c.execute(
                    "SELECT * FROM transactions WHERE user_id=? AND chat_id=? AND created_at>=? ORDER BY created_at DESC LIMIT 1",
                    (user_id, chat_id, (now - timedelta(hours=24)).isoformat()),
                ).fetchone()
            )

    def delete_transaction(self, id, user_id, chat_id):
        with self._conn() as c:
            return c.execute("DELETE FROM transactions WHERE id=? AND user_id=? AND chat_id=?", (id, user_id, chat_id)).rowcount == 1

    def delete_transaction_web(self, id: int, chat_id: str | None = None) -> bool:
        with self._conn() as c:
            if chat_id:
                return c.execute("DELETE FROM transactions WHERE id=? AND chat_id=?", (id, chat_id)).rowcount == 1
            return c.execute("DELETE FROM transactions WHERE id=?", (id,)).rowcount == 1

    def update_transaction(self, id, user_id, chat_id, **changes):
        allowed = {k: v for k, v in changes.items() if k in {"amount", "description", "category", "type"}}
        if not allowed:
            return False
        q = "UPDATE transactions SET " + ",".join(f"{k}=?" for k in allowed) + " WHERE id=? AND user_id=? AND chat_id=?"
        p = list(allowed.values()) + [id, user_id, chat_id]
        with self._conn() as c:
            return c.execute(q, p).rowcount == 1

    def update_transaction_web(self, id, chat_id, **changes):
        allowed = {k: v for k, v in changes.items() if k in {"amount", "description", "category", "type", "transaction_date", "username"}}
        if not allowed:
            return False
        q = "UPDATE transactions SET " + ",".join(f"{k}=?" for k in allowed) + " WHERE id=? AND chat_id=?"
        with self._conn() as c:
            return c.execute(q, list(allowed.values()) + [id, chat_id]).rowcount == 1

    def list_categories(self):
        with self._conn() as c:
            return [Category(r["name"], [x for x in r["keywords"].split(",") if x], r["emoji"], r["type"]) for r in c.execute("SELECT * FROM categories ORDER BY name").fetchall()]

    def upsert_category(self, x: Category):
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO categories VALUES (?,?,?,?)", (x.name, ",".join(x.keywords), x.emoji, x.type))

    def delete_category(self, name):
        with self._conn() as c:
            return c.execute("DELETE FROM categories WHERE name=? AND name!='Lain-lain'", (name,)).rowcount == 1

    def count_category_transactions(self, category_name: str) -> int:
        with self._conn() as c:
            row = c.execute("SELECT COUNT(*) as count FROM transactions WHERE category=?", (category_name,)).fetchone()
            return row["count"] if row else 0

    def rename_category_transactions(self, old_name: str, new_name: str):
        with self._conn() as c:
            c.execute("UPDATE transactions SET category=? WHERE category=?", (new_name, old_name))

    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as c:
            row = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO app_settings (key, value) VALUES (?, ?)", (key, value))
