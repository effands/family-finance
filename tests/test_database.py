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
