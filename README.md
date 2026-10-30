# Money Bot Keluarga

Bot Telegram gratis untuk mencatat pemasukan dan pengeluaran dengan bahasa sehari-hari. Tidak memakai LLM atau layanan berbayar; parser berjalan lokal sehingga data transaksi tetap berada di database milik Anda.

## Cara paling mudah menjalankan

1. Install Python 3.11 atau lebih baru.
2. Buat bot di Telegram: buka **@BotFather**, kirim `/newbot`, ikuti instruksi, lalu salin token.
3. Salin `.env.example` menjadi `.env`, isi `BOT_TOKEN`.
4. Masukkan ID grup keluarga ke `ALLOWED_CHAT_IDS`. Cara praktis: tambahkan bot ke grup, kirim `/start`, lalu lihat ID chat dari log atau gunakan bot info chat sementara.
5. Jalankan:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m src.main
```

6. Tambahkan bot ke grup keluarga. Jika bot tidak merespons, pastikan ID grup ada di `.env` dan bot sudah diberi izin membaca pesan.

## Contoh penggunaan

Ketik saja:

```text
belanja buah habis 15.000
gaji masuk 8jt
bensin 50rb kemarin
bayar listrik 350.000
```

Bot menjawab singkat dengan nominal, kategori, tanggal, dan nama pencatat. Untuk pemula, mulai dengan `/start` karena pesan itu menampilkan contoh dan daftar command.

## Command

- `/hari`, `/minggu`, `/bulan` — laporan periode berjalan.
- `/laporan all` — semua transaksi.
- `/laporan 2025-10` — laporan bulan tertentu.
- `/laporan saya bulan` — laporan transaksi Anda sendiri.
- `/rekap` — ringkasan periode bulan berjalan.
- `/undo` — hapus catatan terakhir milik Anda dalam lima menit.
- `/hapus ID` — hapus catatan milik Anda.
- `/edit ID nominal 25000` — ubah nominal.
- `/edit ID deskripsi belanja sayur` — ubah deskripsi.
- `/edit ID kategori Rumah & Utilitas` — ubah kategori.
- `/kategori` — lihat kategori.

## Kategori

Kategori awal mencakup Makanan & Minuman, Transportasi, Rumah & Utilitas, Kesehatan, Pulsa & Digital, Anak, Belanja, Pemasukan, dan Lain-lain. Kategori disimpan di SQLite dan mudah diperluas di `src/categorizer.py`; command tambah/hapus kategori dapat diaktifkan berikutnya sesuai kebutuhan keluarga.

## Gratis untuk banyak keluarga

Setiap keluarga dapat membuat bot Telegram sendiri dengan @BotFather dan menjalankan satu instance kecil. Untuk berbagi satu server, buat satu folder/database per keluarga dan satu token bot per keluarga. Parser, kode, dan dependency bersifat open-source/gratis; biaya satu-satunya adalah hosting bila tidak dijalankan di komputer rumah.

Pilihan deployment:

- **Komputer rumah/laptop:** gratis, jalankan `python -m src.main`; komputer harus tetap menyala.
- **VPS murah:** jalankan sebagai service systemd dan backup `data/money.db` berkala.
- **Railway/Fly.io:** mudah untuk demo, tetapi SQLite memerlukan volume persisten; tanpa volume data bisa hilang saat redeploy. Untuk banyak keluarga, gunakan PostgreSQL gratis dari provider yang dipilih dan pertahankan database layer yang sama.

## Keamanan

Jangan membagikan `.env`. Isi `ALLOWED_CHAT_IDS` hanya dengan grup yang diizinkan. Bot menerapkan rate limit 30 pesan/menit/user. Untuk produksi multi-keluarga, gunakan satu database/schema terpisah per tenant dan tambahkan backup otomatis.

## Pengembangan

```powershell
python -m pytest -q
python -m compileall src
```

Saat ini test parser mencakup 20 variasi nominal, tanggal, pemasukan/pengeluaran, deskripsi, dan error nominal. Struktur parser/database dipisahkan agar adapter WhatsApp dapat ditambahkan tanpa mengubah aturan pencatatan.
