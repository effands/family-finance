from .models import Category


def default_categories() -> list[Category]:
    return [
        Category("Makanan & Minuman", ["makan", "minum", "jajan", "kopi", "resto", "buah", "sayur", "bakso", "warteg"], "🍔", "expense"),
        Category("Transportasi", ["bensin", "bbm", "parkir", "tol", "grab", "gojek", "ojek", "ongkos"], "⛽", "expense"),
        Category("Rumah & Utilitas", ["listrik", "air", "gas", "internet", "wifi", "sewa", "kontrakan", "kebersihan"], "🏠", "expense"),
        Category("Kesehatan", ["obat", "dokter", "klinik", "rumah sakit", "vitamin", "bpjs"], "💊", "expense"),
        Category("Pulsa & Digital", ["pulsa", "kuota", "paket data", "netflix", "spotify", "langganan"], "📱", "expense"),
        Category("Anak", ["susu", "popok", "diaper", "sekolah", "buku", "mainan", "jajan anak"], "👶", "expense"),
        Category("Belanja", ["baju", "sepatu", "belanja bulanan", "indomaret", "alfamart", "supermarket"], "👕", "expense"),
        Category("Pemasukan", ["gaji", "bonus", "thr", "transferan", "jual", "cashback", "refund", "untung"], "💰", "income"),
        Category("Lain-lain", [], "🎁", "both"),
    ]


def categorize(description: str, categories: list[Category]) -> Category:
    text = description.casefold()
    for category in categories:
        if category.name == "Lain-lain":
            continue
        if any(keyword.casefold() in text for keyword in category.keywords):
            return category
    return next(c for c in categories if c.name == "Lain-lain")
