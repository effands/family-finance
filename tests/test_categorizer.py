from src.categorizer import categorize, default_categories


def test_default_keyword_categories():
    categories = default_categories()
    assert categorize("belanja buah", categories).name == "Makanan & Minuman"
    assert categorize("isi bensin motor", categories).name == "Transportasi"
    assert categorize("bayar listrik", categories).name == "Rumah & Utilitas"
    assert categorize("sesuatu tak dikenal", categories).name == "Lain-lain"
