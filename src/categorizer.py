from .models import Category


def default_categories() -> list[Category]:
    return [
        # Pos pengeluaran spesifik & terarah
        Category("Pendidikan & Kursus", ["spp", "les", "kursus", "ukt", "buku pelajaran", "pendaftaran sekolah", "seragam", "kuliah", "bimbel", "wisuda", "iuran sekolah", "alat tulis"], "🎓", "expense"),
        Category("Hewan Peliharaan", ["kucing", "anjing", "pet shop", "cat food", "dog food", "makanan kucing", "dokter hewan", "vaksin kucing", "pasir kucing", "grooming", "kandang", "whiskas", "royal canin"], "🐾", "expense"),
        Category("Cicilan & Pinjaman", ["cicilan", "kpr", "paylater", "kartu kredit", "pinjaman", "angsuran", "kredit motor", "kredit mobil", "lising", "pinjol", "fintech"], "💳", "expense"),
        Category("Sedekah & Donasi", ["zakat", "sedekah", "infak", "infaq", "donasi", "perpuluhan", "kurban", "qurban", "wakaf", "celengan", "kotak amal", "sumbangan", "bansos"], "🤲", "expense"),
        Category("Servis Kendaraan", ["servis motor", "servis mobil", "ganti oli", "bengkel", "cuci motor", "cuci mobil", "tambal ban", "aki", "sparepart", "tune up", "oli motor", "oli mobil"], "🔧", "expense"),
        Category("Perbaikan Rumah", ["renovasi", "tukang", "cat rumah", "perbaikan rumah", "pompa air", "ledeng", "alat rumah", "perabot", "kasur", "bohlam", "kunci", "bocor"], "🔨", "expense"),
        Category("Kesehatan", ["obat", "dokter", "klinik", "rumah sakit", "vitamin", "bpjs", "apotek", "rapid", "fisioterapi", "termometer", "resep dokter"], "💊", "expense"),
        Category("Perawatan & Kecantikan", ["skincare", "salon", "potong rambut", "barbershop", "kosmetik", "sabun", "sampo", "pasta gigi", "spa", "parfum", "facial", "make up", "sunscreen", "body wash"], "🧴", "expense"),
        Category("Keluarga & Relasi", ["uang ortu", "kirim ortu", "jajan ortu", "amplop", "kondangan", "hajatan", "kado", "hadiah", "arisan", "buwuh", "angpau", "syukuran"], "👨‍👩‍👦", "expense"),
        Category("Anak", ["susu anak", "susu bayi", "popok", "diaper", "mainan anak", "jajan anak", "imunisasi", "posyandu", "stroller", "perlengkapan bayi"], "👶", "expense"),
        Category("Pulsa & Digital", ["pulsa", "kuota", "paket data", "netflix", "spotify", "langganan", "youtube", "cloud", "chatgpt", "google drive"], "📱", "expense"),
        Category("Hiburan & Rekreasi", ["bioskop", "nonton", "liburan", "hotel", "tiket", "wisata", "karaoke", "staycation", "game", "steam", "rekreasi", "playground", "pantai"], "🎟️", "expense"),
        Category("Olahraga & Hobi", ["gym", "fitness", "badminton", "futsal", "sewa lapangan", "sepeda", "lari", "jersey", "alat gym", "renang", "yoga", "pancing"], "⚽", "expense"),
        Category("Pajak & Legalitas", ["pajak", "pbb", "stnk", "sim", "asuransi", "premi", "materai", "admin bank", "denda", "pph", "paspor", "notaris"], "📄", "expense"),
        Category("Investasi & Aset", ["investasi", "saham", "reksadana", "bibit", "emas", "antam", "crypto", "tabungan", "deposito", "obligasi", "sukuk", "sbn"], "📈", "expense"),
        Category("Transportasi", ["bensin", "bbm", "parkir", "tol", "grab", "gojek", "ojek", "ongkos", "kereta", "krl", "mrt", "transjakarta", "taksi"], "⛽", "expense"),
        Category("Makanan & Minuman", ["makan", "minum", "jajan", "kopi", "resto", "buah", "sayur", "bakso", "warteg", "gofood", "grabfood", "shopeefood", "snack"], "🍔", "expense"),
        Category("Belanja", ["baju", "sepatu", "belanja bulanan", "indomaret", "alfamart", "supermarket", "pasar", "sembako", "dapur"], "👕", "expense"),
        Category("Rumah & Utilitas", ["listrik", "air", "gas", "internet", "wifi", "indihome", "pln", "pdam", "sewa", "kontrakan", "kebersihan", "iuran rt", "keamanan", "sampah"], "🏠", "expense"),
        Category("Pemasukan", ["gaji", "bonus", "thr", "transferan", "jual", "cashback", "refund", "untung", "payroll", "upah"], "💰", "income"),
        Category("Pendapatan Sampingan", ["side job", "freelance", "jualan", "dagang", "dividen", "komisi", "affiliate", "royalti", "laba", "honor", "proyek", "tips"], "💼", "income"),
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
