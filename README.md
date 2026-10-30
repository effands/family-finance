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

### Menu modern dan upload struk

Kirim `/start` untuk menampilkan tombol menu: catat transaksi, laporan minggu/bulan, rekap, undo, kategori, dan upload struk. Untuk OCR struk, isi `GEMINI_API_KEYS` dengan satu atau beberapa API key Gemini yang dipisahkan koma. Bot membaca foto dengan Gemini Vision, menampilkan preview nominal/deskripsi/tanggal/kategori, lalu baru menyimpan setelah tombol `✅ Simpan` ditekan. Jika Gemini gagal atau key kosong, bot tidak menyimpan otomatis dan meminta input manual.

Jangan commit `.env` atau API key ke GitHub.

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

## Dasbor Web Finansial Keluarga

Dasbor tersedia di `https://domain-anda/keuangan/dashboard` (atau secara lokal di `http://127.0.0.1:8000/keuangan/dashboard`). Isikan `WEB_PASSWORD` di file `.env`, lalu lakukan autentikasi menggunakan kata sandi tersebut.

Fitur & Antarmuka Dasbor Eksekutif:

- **Navigasi Periode Fleksibel:** Pilihan cepat Pekan Ini, Bulan Ini, Tahun Ini, Semua Periode, dan pemilih Rentang Tanggal Kustom.
- **Kartu Indikator Finansial (KPI):** Total Pemasukan, Total Pengeluaran, Arus Kas Bersih (*Net Cash Flow*) dengan indikator surplus/defisit dinamis, serta Rasio Retensi Tabungan (*Savings Rate*).
- **Visualisasi Analitik Interaktif:** Grafik batang perbandingan arus kas (*Cash Flow Comparison*) dan diagram donat proporsi pos pengeluaran (*Category Breakdown*) bertenaga Chart.js.
- **Pencatatan Transaksi Manual:** Tambah mutasi kas masuk/keluar langsung melalui modal dialog web tanpa harus melalui Telegram.
- **Manajemen Mutasi & Audit:** Penghapusan catatan transaksi dengan dialog konfirmasi aman.
- **Pencarian Real-Time (Live Filter):** Penyaringan instan data pada tabel buku besar tanpa *page reload*.
- **Filter Lanjutan:** Filter berdasarkan Jenis Transaksi, Kategori, Urutkan (Tanggal, Nominal, Deskripsi, Kategori), dan Tata Urutan (*Ascending/Descending*).
- **Distribusi Kategori & Kontribusi Anggota:** Visualisasi *progress bar* proporsi belanja per pos kategori dan rekapitulasi anggota keluarga.
- **Ekspor & Cetak Laporan:** Ekspor data mutasi ke berkas CSV dengan enkoding UTF-8-BOM yang aman untuk Excel, dan tata letak cetak ramah PDF (*Print-ready*).
- **Impor Transaksi CSV & Unduh Templat:** Unggah berkas CSV massal aman tanpa menimpa catatan sebelumnya, disertai tombol unduh contoh templat CSV resmi (`/keuangan/template.csv`).
- **Modul Pengaturan Sistem (`/keuangan/settings`):**
  - **CRUD Kategori Transaksi:** Tambah kategori baru dengan emoji dan kata kunci deteksi otomatis, sunting kategori, dan hapus kategori (transaksi terkait dialihkan otomatis ke kategori *Lain-lain*).
  - **Integrasi Google Gemini Vision AI:** Input multi-key dengan round-robin + failover otomatis, pemilihan Gemini 3.8/3.6 Flash, serta pengujian koneksi semua key.
  - **Manajemen Kata Sandi:** Ubah kata sandi akses dasbor web dengan validasi kata sandi lama dan hashing SHA-256.
  - **Info Parameter Sistem:** Tinjau izin chat Telegram, zona waktu, lokasi basis data, dan batas laju pesan (*rate limit*).

Contoh CSV import:

```csv
tanggal,tipe,nominal,deskripsi,kategori,user
2026-10-30,pengeluaran,15000,belanja buah,Makanan & Minuman,suami
2026-10-30,pemasukan,8000000,gaji,Pemasukan,suami
```

Untuk import, pilih file CSV di bagian **Data** lalu tekan **Import CSV**. Nominal diterima sebagai integer rupiah; format `15000` paling aman untuk file CSV.

## Pengembangan

```powershell
python -m pytest -q
python -m compileall src
```

Saat ini test parser mencakup 20 variasi nominal, tanggal, pemasukan/pengeluaran, deskripsi, dan error nominal. Struktur parser/database dipisahkan agar adapter WhatsApp dapat ditambahkan tanpa mengubah aturan pencatatan.
