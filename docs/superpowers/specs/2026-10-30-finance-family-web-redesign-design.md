# Finance Family Web Redesign — Design

## Intent

Membuat halaman login, dashboard, dan export lebih profesional, konsisten, nyaman di ponsel, dan tetap ringan untuk deployment Python Passenger di cPanel.

## Goals

- Satu design system CSS lokal untuk seluruh halaman web.
- Login yang terasa aman, sederhana, dan jelas saat password salah.
- Dashboard yang cepat dipindai: saldo bersih, pemasukan, pengeluaran, transaksi terbaru.
- Export yang mudah dibaca di layar, mobile, print, dan disimpan sebagai PDF.
- Filter transaksi berdasarkan tanggal, tipe, kategori, dan pencarian teks.
- Sortir kolom transaksi dan rekap mingguan/bulanan yang mudah dipilih.
- Export CSV yang benar-benar dapat diunduh, print/PDF, serta import CSV dengan validasi.
- Title web dan metadata halaman memakai nama produk yang konsisten.
- Tidak mengubah URL, database, autentikasi, atau alur bot Telegram.

## Non-goals

- Tidak menambah framework frontend, bundler, npm, CDN, atau dependency runtime.
- Tidak mengubah skema SQLite atau parser transaksi.
- Tidak membuat fitur edit transaksi dari web pada tahap ini.
- Import hanya menerima CSV dengan kolom yang ditentukan; tidak menerima file arbitrary.

## Constraints

- Aplikasi saat ini merender HTML dari `passenger_wsgi.py`.
- Hosting menggunakan cPanel/Passenger, sehingga aset harus bisa disajikan sebagai file lokal sederhana.
- Referensi visual: GitHub Primer CSS (MIT), diadaptasi secara custom; tidak menyalin package atau source code mentah.

## Approach

Alternatif yang dipertimbangkan:

1. CSS lokal custom terinspirasi Primer — dipilih karena paling cocok dengan aplikasi Python sederhana, tidak bergantung CDN, dan mudah diubah.
2. Bootstrap CDN — cepat tetapi tampilan lebih generik dan bergantung koneksi eksternal.
3. Primer sebagai package — paling dekat dengan referensi tetapi menambah build/dependency yang tidak perlu.

## Design direction

- Palet: navy tinta, biru aksen, mint untuk pemasukan, coral untuk pengeluaran, latar biru-abu sangat muda.
- Tipografi: system sans stack agar tidak perlu download font.
- Bentuk: radius sedang, border halus, shadow tipis, whitespace lega.
- Layout: container maksimum 1120px; grid kartu yang turun menjadi satu kolom di mobile.
- Aksesibilitas: focus ring jelas, kontras teks memadai, tombol memiliki label nyata, `prefers-reduced-motion` dihormati.
- Emoji hanya dipakai sebagai aksen kecil; informasi utama tetap berupa teks.

## Implementation shape

- Tambah `static/app.css` berisi token, layout, forms, cards, tables, badges, responsive, dan print rules.
- Tambah helper HTML di `passenger_wsgi.py` untuk shell halaman, login, dashboard, dan export.
- Tambah class semantic seperti `page-shell`, `auth-card`, `metric-card`, `data-table`, dan `button`.
- Escape seluruh data transaksi sebelum masuk HTML.
- Pertahankan endpoint `/keuangan/`, `/keuangan/dashboard`, `/keuangan/excel`, dan `/keuangan/export*`.
- Tambah query/filter UI tanpa mengubah endpoint bot Telegram.
- Tambah endpoint POST import CSV dengan laporan jumlah berhasil/gagal.

## Verification

- Jalankan test Python yang sudah ada.
- Jalankan smoke test lokal terhadap endpoint web bila environment mendukung.
- Buka login, dashboard, dan export pada desktop serta viewport sempit.
- Pastikan tidak ada perubahan pada data transaksi.
