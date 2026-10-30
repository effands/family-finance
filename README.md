# Finance Family — Sistem Manajemen Keuangan Personal & Keluarga

Bot Telegram modern dan Dasbor Web Finansial Keluarga untuk mencatat pemasukan, pengeluaran, audit transaksi, analisa struk belanja berbasis Google Gemini Vision AI, serta ekspor laporan resmi (.xlsx dan .pdf).

*Dibuat oleh **effands** ~ **ziqva.com** team with love family @2026* ❤️

---

## 🚀 Fitur Utama

- **Antarmuka Telegram Modern & Eksekutif:**
  - Konfirmasi mutasi berformat kartu eksekutif (*Executive Receipt Card*).
  - Tombol aksi instan (*Inline Action Keyboard*): `[↩️ Batalkan / Undo]` dan `[📊 Rekap Saldo]` di setiap mutasi.
  - Keyboard menu cepat (*Persistent Quick Reply*): Catat Transaksi, Pemasukan, Pengeluaran, Rekap, Struk Belanja, Kategori, Bantuan.
  - Fitur pembatalan (*Undo*) cepat dan perintah manajemen mutasi: `/undo`, `/hapus <ID>`, `/edit <ID> ...`.
  - Permintaan data keuangan cepat: `/pemasukan` (total pemasukan), `/pengeluaran` (total pengeluaran & distribusi kategori), `/rekap` (saldo kas bersih).
  - Manajemen kategori langsung dari Telegram: `/kategori`, `/tambahkategori`, `/hapuskategori`.
  - Ekstraksi foto struk belanja otomatis berbasis Google Gemini Vision AI dengan tombol `[✅ Simpan Transaksi]`.

- **Dasbor Web Finansial Profesional:**
  - Navigasi periode fleksibel: Hari Ini, Pekan Ini, Bulan Ini, Tahun Ini, Semua Periode, dan Rentang Kustom.
  - Kartu Indikator Finansial (KPI): Pemasukan, Pengeluaran, Arus Kas Bersih (*Net Cash Flow*), Rasio Tabungan (*Savings Rate*).
  - Grafik Analitik Interaktif: Visualisasi arus kas dan diagram donat proporsi pos belanja bertenaga Chart.js.
  - Pencatatan transaksi manual & audit mutasi dengan modal konfirmasi aman.
  - Live filter pencarian instan dan penyaringan lanjutan multi-kolom.

- **Ekspor Dokumen Finansial Standalone:**
  - **Ekspor Excel (.xlsx):** Berkas spreadsheet resmi bertenaga `openpyxl` dengan styling korporat, kartu KPI, pemisahan mutasi berwarna, dan format rupiah.
  - **Ekspor PDF Laporan Keuangan:** Dokumen laporan resmi bertenaga `reportlab` dengan tata letak dokumen formal, ringkasan eksekutif, tabel mutasi bergaris rapi, dan legalitas tanda tangan.

- **Modul Pengaturan Sistem (`/keuangan/settings`):**
  - **CRUD Kategori Transaksi:** Tambah, edit, dan hapus kategori dengan pengalihan otomatis mutasi ke *Lain-lain*.
  - **Integrasi Google Gemini Vision AI:** Konfigurasi Kunci API multi-key dengan failover otomatis dan fitur uji koneksi instan.
  - **Keamanan Akun:** Ganti kata sandi dasbor web dengan validasi kata sandi lama dan hashing SHA-256.
  - **Info Parameter Sistem:** Tinjau parameter izin chat, zona waktu, lokasi database, dan rate limit.

---

## 🛠️ Cara Menjalankan

### 1. Prasyarat
- Python 3.11 atau lebih baru
- Akun Telegram & Bot Token dari [@BotFather](https://t.me/BotFather)

### 2. Pemasangan & Persiapan Lingkungan

```powershell
# Clone repositori
git clone https://github.com/effands/family-finance.git
cd "family-finance"

# Buat virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Pasang pustaka dependensi
pip install -r requirements.txt
```

### 3. Konfigurasi Variabel Lingkungan (`.env`)
Salin berkas contoh konfigurasi:
```powershell
cp .env.example .env
```
Sesuaikan isi `.env`:
```ini
BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
ALLOWED_CHAT_IDS=-1001234567890
WEB_PASSWORD=kataSandiKeluarga123
GEMINI_API_KEYS=AIzaSy...
```

### 4. Menjalankan Bot & Dasbor

- **Menjalankan Bot Telegram (Long Polling):**
  ```powershell
  python -m src.main
  ```

- **Menjalankan Dasbor Web Lokal (WSGI Server):**
  ```powershell
  python -c "import os; from wsgiref.simple_server import make_server; from passenger_wsgi import application; print('Dasbor aktif: http://127.0.0.1:8000/keuangan/dashboard'); make_server('127.0.0.1', 8000, application).serve_forever()"
  ```
  Buka peramban di `http://127.0.0.1:8000/keuangan/dashboard`.

---

## 💬 Interaksi Bot Telegram

### Format Masukan Bahasa Sehari-hari:
```text
belanja sayur dan buah 45rb
gaji masuk 12jt
bensin motor 35000 kemarin
bayar wifi indihome 385.000
```

### Daftar Perintah Telegram:
| Perintah | Deskripsi |
| :--- | :--- |
| `/start` | Buka menu utama dan panduan lengkap |
| `/pemasukan` atau `/income` | Ringkasan dan riwayat pemasukan periode berjalan |
| `/pengeluaran` atau `/expense` | Ringkasan total dan rincian pos pengeluaran |
| `/rekap` | Ikhtisar arus kas dan saldo bersih bulan ini |
| `/hari`, `/minggu`, `/bulan` | Laporan berkala mutasi keuangan |
| `/laporan all` | Laporan seluruh mutasi yang tersimpan |
| `/undo` | Membatalkan mutasi terakhir yang baru Anda masukkan |
| `/hapus <ID>` | Menghapus mutasi spesifik berdasarkan ID |
| `/edit <ID> nominal <angka>` | Memperbarui nominal transaksi |
| `/edit <ID> deskripsi <teks>` | Memperbarui deskripsi transaksi |
| `/edit <ID> kategori <nama>` | Mengubah pos kategori transaksi |
| `/kategori` | Menampilkan seluruh kategori mutasi |
| `/tambahkategori <nama>` | Menambahkan pos kategori baru |
| `/hapuskategori <nama>` | Menghapus pos kategori (transaksi dialihkan ke *Lain-lain*) |

---

## 📊 Dasbor Web & Ekspor Dokumen

Akses Dasbor Web di `/keuangan/dashboard`:
- **Ekspor Excel:** Klik tombol `Ekspor Excel` atau akses `/keuangan/export.xlsx` untuk mengunduh berkas `.xlsx`.
- **Ekspor PDF:** Klik tombol `Ekspor PDF` atau akses `/keuangan/export.pdf` untuk mengunduh dokumen laporan keuangan resmi.
- **Pengaturan:** Klik tombol `Pengaturan` atau akses `/keuangan/settings` untuk mengelola kategori, API Key Gemini, dan kata sandi.

---

## 🧪 Pengujian Unit & Kualitas Kode

```powershell
# Menjalankan seluruh test suite
python -m pytest -q

# Verifikasi kompilasi bytecode
python -m compileall src passenger_wsgi.py
```

---

## 🔒 Privasi & Keamanan

- Basis data SQLite lokal (`data/money.db`) memastikan seluruh riwayat transaksi tidak dikirimkan ke pihak ketiga manapun.
- Autentikasi sesi berbasis cookie dengan pengacakan SHA-256 dan perlindungan terhadap *brute force*.
- Rate limit 30 pesan/menit/pengguna di Telegram untuk mencegah penyalahgunaan.

---

## 📄 Hak Cipta & Pengembang

Dibuat dengan cinta untuk keluarga Indonesia oleh **effands** ~ [ziqva.com](https://ziqva.com) team with love family @2026.
