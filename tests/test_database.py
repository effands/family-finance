from datetime import date, datetime, timedelta
from src.database import Database
from src.models import Transaction, TransactionFilters


def tx(user="u1", chat="c1", amount=15000):
    return Transaction(None, user, "suami", chat, "expense", amount, "buah", "Makanan & Minuman", date(2025,10,30), datetime(2025,10,30,12))


def test_database_crud_and_scoping(tmp_path):
    db = Database(str(tmp_path / "m.db")); db.initialize()
    item = db.add_transaction(tx())
    assert db.get_transaction(item.id).amount == 15000
    assert len(db.list_transactions(TransactionFilters("c1"))) == 1
    assert db.find_latest_transaction("u1", "c1", datetime(2025,10,30,12,4)).id == item.id
    assert db.update_transaction(item.id, "u1", "c1", amount=20000)
    assert db.get_transaction(item.id).amount == 20000
    assert db.delete_transaction(item.id, "u1", "c1")


def test_list_transactions_supports_web_filters_and_sorting(tmp_path):
    db = Database(str(tmp_path / "x.db")); db.initialize()
    items = [
        Transaction(None, "u", "andi", "c", "expense", 50000, "bensin", "Transportasi", date(2026, 10, 2), datetime.now()),
        Transaction(None, "u", "andi", "c", "income", 8000000, "gaji", "Pemasukan", date(2026, 10, 3), datetime.now()),
        Transaction(None, "u", "andi", "c", "expense", 15000, "buah", "Makanan & Minuman", date(2026, 10, 4), datetime.now()),
    ]
    for item in items: db.add_transaction(item)
    filters = TransactionFilters("c", date(2026, 10, 1), date(2026, 10, 3), None, "expense", "Transportasi", None, "amount", "desc")
    assert [x.amount for x in db.list_transactions(filters)] == [50000]


def test_list_transactions_searches_description(tmp_path):
    db = Database(str(tmp_path / "x.db")); db.initialize()
    db.add_transaction(Transaction(None, "u", "andi", "c", "expense", 15000, "belanja buah", "Makanan & Minuman", date(2026, 10, 4), datetime.now()))
    assert len(db.list_transactions(TransactionFilters("c", search="BUAH"))) == 1
