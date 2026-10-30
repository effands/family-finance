from src.receipt_ai import _clean_json


def test_clean_receipt_json():
    data = _clean_json('```json\n{"amount": 125000, "description": "Supermarket", "date": "2026-10-30", "category": "Belanja"}\n```')
    assert data == {"amount": 125000, "description": "Supermarket", "date": "2026-10-30", "category": "Belanja"}


def test_clean_receipt_defaults_unknown_amount():
    data = _clean_json('{"description": "Struk blur", "category": "Lain-lain"}')
    assert data["amount"] == 0
    assert data["description"] == "Struk blur"
