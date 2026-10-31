from src.categorizer import categorize, default_categories


def test_default_keyword_categories():
    categories = default_categories()
    assert categorize("belanja buah", categories).name == "Makanan & Minuman"
    assert categorize("isi bensin motor", categories).name == "Transportasi"
    assert categorize("bayar listrik", categories).name == "Rumah & Utilitas"
    assert categorize("bayar spp anak", categories).name == "Pendidikan & Kursus"
    assert categorize("sedekah subuh infaq masjid", categories).name == "Sedekah & Donasi"
    assert categorize("ganti oli servis motor", categories).name == "Servis Kendaraan"
    assert categorize("beli cat perbaikan rumah", categories).name == "Perbaikan Rumah"
    assert categorize("beli skincare sabun muka", categories).name == "Perawatan & Kecantikan"
    assert categorize("bayar cicilan kpr bulanan", categories).name == "Cicilan & Pinjaman"
    assert categorize("makanan kucing pet shop", categories).name == "Hewan Peliharaan"
    assert categorize("sesuatu tak dikenal", categories).name == "Lain-lain"
