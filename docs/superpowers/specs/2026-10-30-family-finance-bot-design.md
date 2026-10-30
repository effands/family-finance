# Desain Bot Pencatatan Keuangan Keluarga

Tanggal: 2026-10-30

## Intent

Menyediakan bot Telegram gratis untuk dua anggota keluarga yang dapat menerima catatan keuangan dalam bahasa Indonesia santai, mengubahnya menjadi transaksi terstruktur, menyimpan ke SQLite, dan menghasilkan laporan yang ringkas.

## Goals

- Input natural language untuk pemasukan dan pengeluaran.
- Parsing nominal Rupiah yang umum: angka biasa, `rb/k/ribu`, `jt/juta`, desimal koma/titik.
- Kategori otomatis berbasis keyword dan kategori custom.
- Konfirmasi transaksi, `/undo`, `/hapus`, `/edit`.
- Laporan hari, minggu Senin–Minggu, bulan, rentang, semua data, dan rekap.
- Perilaku multi-user: grup = gabungan transaksi; private chat = transaksi user; `/laporan saya` = transaksi user.
- Konfigurasi aman melalui `.env`, whitelist chat, rate limit, logging.
- Unit test parser minimal 20 variasi dan panduan deploy gratis/berbiaya rendah.

## Non-goals

- Tidak ada LLM wajib, OCR struk, sinkronisasi bank, dashboard web, atau multi-currency.
- WhatsApp bukan bagian MVP. Core parser/database akan dibuat cukup terpisah agar adapter WhatsApp dapat ditambahkan kemudian.
- Tidak menjamin klasifikasi sempurna untuk kalimat ambigu; bot meminta klarifikasi jika nominal tidak ditemukan atau bernilai nol.

## Anti-goals

- Jangan mengirim data transaksi ke layanan AI eksternal secara default.
- Jangan menyimpan token Telegram di source code.
- Jangan menerima pesan dari chat yang tidak diizinkan.

## Pendekatan yang dipertimbangkan

1. **Telegram + Python (`python-telegram-bot`) — dipilih.** API resmi, gratis, mudah diuji, cocok untuk bot grup kecil, dan mendukung polling tanpa domain publik untuk development.
2. **WhatsApp + Node.js/Baileys.** UX familiar, tetapi membutuhkan sesi WhatsApp Web dan lebih banyak risiko operasional; ditunda setelah MVP.
3. **Hybrid dua channel sejak awal.** Reuse core lebih luas, tetapi memperbesar scope dan permukaan bug sebelum alur keuangan tervalidasi.

## Arsitektur

`Telegram Update -> handlers -> parser -> categorizer -> database -> formatter/reports`

- `src/main.py`: konfigurasi, logging, rate limiter, registrasi handler, polling.
- `src/parser.py`: normalisasi teks, nominal, tipe, deskripsi, tanggal; tidak melakukan I/O.
- `src/categorizer.py`: kategori default dan keyword kategori custom.
- `src/database.py`: schema SQLite dan operasi CRUD dengan parameterized query.
- `src/reports.py`: query agregasi dan rendering monospace Bahasa Indonesia.
- `src/handlers/`: command/message handlers dan validasi akses.
- `tests/`: unit test parser dan test ringan formatter/database bila diperlukan.

## Keputusan perilaku

- Zona waktu default: `Asia/Jakarta`, dapat diubah lewat `TIMEZONE`.
- “Hari ini” dan “kemarin” mengikuti zona waktu tersebut.
- `tgl 5` berarti tanggal 5 pada bulan berjalan; jika tanggal itu belum terjadi, tetap dianggap bulan berjalan sesuai permintaan pengguna.
- `5/12` berarti 5 Desember pada tahun berjalan; format tanggal ISO lengkap menerima `YYYY-MM-DD` dan `DD-MM-YYYY`.
- Jika ada lebih dari satu nominal, parser memilih nominal pertama dan memberi peringatan singkat agar user dapat mengoreksi; implementasi awal tidak memecah satu pesan menjadi banyak transaksi.
- Deskripsi adalah teks setelah nominal dihapus, dengan kata penanda tanggal dan kata perintah umum dibersihkan secukupnya.
- Jika keyword income dan expense bertabrakan, keyword income eksplisit seperti `gaji`, `bonus`, atau `refund` diprioritaskan; selain itu default expense.
- `/undo` hanya menghapus transaksi terbaru milik user di chat yang sama dalam 5 menit.
- `/hapus` dan `/edit` hanya berlaku pada transaksi di chat yang sama, kecuali implementasi memilih validasi tambahan berdasarkan user pembuat; keputusan MVP: user hanya boleh mengubah transaksi miliknya sendiri untuk mencegah salah edit pasangan.
- Kategori custom disimpan di SQLite dan berlaku untuk semua chat; nama kategori bersifat case-insensitive saat pencocokan.

## Keamanan dan operasional

- `BOT_TOKEN`, `ALLOWED_CHAT_IDS`, `TIMEZONE`, `DATABASE_PATH`, `LOG_PATH`, dan `RATE_LIMIT_PER_MINUTE` dari `.env`.
- Whitelist berlaku pada grup dan private chat; README menjelaskan cara mengambil `chat_id`.
- Rate limit in-memory per user/chat; reset saat proses restart. Ini cukup untuk dua orang dan bukan mekanisme anti-abuse tingkat produksi.
- SQLite memakai WAL mode dan foreign-key pragma; backup dilakukan dengan menyalin file database saat bot berhenti atau memakai `sqlite3 .backup`.

## Deploy

- Lokal: Python virtual environment + polling.
- VPS: systemd service + polling + backup SQLite.
- Railway: worker service dengan volume persisten; tanpa volume, SQLite tidak dianggap durable. README akan menyebut PostgreSQL sebagai pilihan bila ingin deployment cloud yang lebih tahan restart.

## Validasi keberhasilan

- Semua test parser minimal 20 variasi lulus.
- Bot dapat mencatat contoh input pengguna, menampilkan konfirmasi dengan format Rupiah, dan menghasilkan laporan bulan berjalan.
- Pesan tanpa nominal/nominal nol menghasilkan permintaan klarifikasi dan tidak membuat row transaksi.
- Perintah akses, edit, hapus, kategori, dan laporan berjalan dengan database baru dari nol.

## Yang akan diimplementasikan setelah approval

1. Setup project, konfigurasi, entry point Telegram, dan schema.
2. Parser + categorizer beserta test.
3. CRUD transaksi dan kategori.
4. Formatter konfirmasi dan laporan.
5. Handler command/message, whitelist, rate limit, logging.
6. README, mock conversation, dan verifikasi test/runnable.
