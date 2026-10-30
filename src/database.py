import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from .categorizer import default_categories
from .models import Category, Transaction, TransactionFilters


class Database:
    def __init__(self, path: str): self.path = path
    def _conn(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.path); c.row_factory = sqlite3.Row; return c
    def initialize(self):
        with self._conn() as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, username TEXT, chat_id TEXT NOT NULL, type TEXT NOT NULL, amount INTEGER NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL, transaction_date TEXT NOT NULL, created_at TEXT NOT NULL); CREATE TABLE IF NOT EXISTS categories (name TEXT PRIMARY KEY, keywords TEXT NOT NULL, emoji TEXT NOT NULL, type TEXT NOT NULL); CREATE INDEX IF NOT EXISTS ix_tx_chat_date ON transactions(chat_id, transaction_date); CREATE INDEX IF NOT EXISTS ix_tx_user_created ON transactions(user_id, created_at); PRAGMA journal_mode=WAL;""")
            for x in default_categories(): c.execute("INSERT OR IGNORE INTO categories VALUES (?,?,?,?)", (x.name, ",".join(x.keywords), x.emoji, x.type))
    def add_transaction(self, x: Transaction) -> Transaction:
        with self._conn() as c:
            cur = c.execute("INSERT INTO transactions(user_id,username,chat_id,type,amount,description,category,transaction_date,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (x.user_id,x.username,x.chat_id,x.type,x.amount,x.description,x.category,x.transaction_date.isoformat(),x.created_at.isoformat()))
            return Transaction(cur.lastrowid,x.user_id,x.username,x.chat_id,x.type,x.amount,x.description,x.category,x.transaction_date,x.created_at)
    def _row(self, r):
        return Transaction(r["id"],r["user_id"],r["username"],r["chat_id"],r["type"],r["amount"],r["description"],r["category"],date.fromisoformat(r["transaction_date"]),datetime.fromisoformat(r["created_at"])) if r else None
    def get_transaction(self, id):
        with self._conn() as c: return self._row(c.execute("SELECT * FROM transactions WHERE id=?",(id,)).fetchone())
    def list_transactions(self, f: TransactionFilters):
        q="SELECT * FROM transactions WHERE chat_id=?"; p=[f.chat_id]
        if f.user_id: q+=" AND user_id=?"; p.append(f.user_id)
        if f.start: q+=" AND transaction_date>=?"; p.append(f.start.isoformat())
        if f.end: q+=" AND transaction_date<=?"; p.append(f.end.isoformat())
        q+=" ORDER BY transaction_date, id"
        with self._conn() as c: return [self._row(r) for r in c.execute(q,p).fetchall()]
    def find_latest_transaction(self,user_id,chat_id,now):
        with self._conn() as c: return self._row(c.execute("SELECT * FROM transactions WHERE user_id=? AND chat_id=? AND created_at>=? ORDER BY created_at DESC LIMIT 1",(user_id,chat_id,(now-timedelta(minutes=5)).isoformat())).fetchone())
    def delete_transaction(self,id,user_id,chat_id):
        with self._conn() as c: return c.execute("DELETE FROM transactions WHERE id=? AND user_id=? AND chat_id=?",(id,user_id,chat_id)).rowcount == 1
    def update_transaction(self,id,user_id,chat_id,**changes):
        allowed={k:v for k,v in changes.items() if k in {"amount","description","category","type"}}
        if not allowed:return False
        q="UPDATE transactions SET "+",".join(f"{k}=?" for k in allowed)+" WHERE id=? AND user_id=? AND chat_id=?"; p=list(allowed.values())+[id,user_id,chat_id]
        with self._conn() as c:return c.execute(q,p).rowcount==1
    def list_categories(self):
        with self._conn() as c:return [Category(r["name"], [x for x in r["keywords"].split(",") if x], r["emoji"], r["type"]) for r in c.execute("SELECT * FROM categories ORDER BY name").fetchall()]
    def upsert_category(self,x:Category):
        with self._conn() as c:c.execute("INSERT OR REPLACE INTO categories VALUES (?,?,?,?)",(x.name,",".join(x.keywords),x.emoji,x.type))
    def delete_category(self,name):
        with self._conn() as c:return c.execute("DELETE FROM categories WHERE name=? AND name!='Lain-lain'",(name,)).rowcount==1
