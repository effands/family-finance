# Desain Pencadangan, Impor, dan Laporan Profesional

## Tujuan

Menambahkan pusat Backup & Laporan yang membuat data pembukuan dapat dicadangkan,
dibaca, dicetak, dan dipulihkan tanpa merusak saldo, ledger, akun, kategori, atau
histori koreksi. Fitur ini melengkapi Wealth Center dan buku transaksi yang sudah
ada.

## Ruang Lingkup

### Sasaran

- Backup penuh satu keluarga dalam ZIP yang berisi snapshot JSON, CSV per entitas,
  manifest versi, waktu ekspor, dan checksum SHA-256.
- Ekspor operasional CSV dan JSON; laporan HTML siap print/PDF melalui browser;
  tetap mempertahankan ekspor XLSX/PDF transaksi yang sudah ada.
- Laporan profesional: buku kas/jurnal transaksi, rekap pemasukan-pengeluaran,
  neraca posisi kekayaan per akun, perubahan saldo, dan rekonsiliasi.
- Impor dengan upload, validasi schema, pratinjau ringkasan, dan dua mode:
  `merge` idempotent (default) atau `replace` yang memerlukan konfirmasi eksplisit.
- Backup otomatis berkala/manual ke folder backup lokal yang tidak berada di
  direktori publik, dengan daftar backup dan ukuran/waktu.
- Fitur cetak dengan CSS print yang menyembunyikan navigasi/form dan memberi
  header periode, nama keluarga, waktu cetak, serta nomor halaman browser.

### Bukan Sasaran

- Sinkronisasi langsung ke bank/e-wallet atau mengambil data rekening otomatis.
- Menyimpan password bank, token akses bank, atau nomor rekening dalam URL.
- Menimpa database produksi tanpa validasi, backup pengaman, dan konfirmasi.
- Menjadikan spreadsheet hasil ekspor sebagai sumber kebenaran ledger.

## Pilihan Pendekatan

1. JSON tunggal: mudah dipulihkan, tetapi kurang nyaman untuk audit dan Excel.
2. Spreadsheet sebagai sumber utama: nyaman diedit, tetapi relasi dan idempotensi
   ledger rawan rusak.
3. **ZIP snapshot + JSON/CSV + laporan print (dipilih)**: snapshot terstruktur
   untuk restore, CSV untuk audit/interoperabilitas, dan laporan khusus untuk
   pembacaan/cetak. Pilihan ini sesuai dengan SQLite dan ledger atomik yang sudah
   digunakan aplikasi.

## Desain Data dan Integritas

- Snapshot menyimpan metadata database, kategori, transaksi legacy, financial
  accounts, ledger operations, ledger entries, preferences, dan legacy links.
- Setiap record memiliki identitas asli dan checksum; impor merge memakai stable
  key/idempotency key sehingga upload ulang tidak menggandakan record.
- Impor hanya menerima JSON/ZIP yang schema dan checksum-nya valid. CSV transaksi
  tetap melalui parser ketat, validasi nominal/tanggal/jenis, dan preview error.
- `replace` selalu membuat backup otomatis sebelum perubahan dan menolak snapshot
  yang berbeda keluarga/chat kecuali pengguna mengonfirmasi ulang.
- Restore dilakukan dalam transaksi SQLite eksklusif; jika satu bagian gagal,
  seluruh perubahan rollback. Database sebelum restore disimpan sebagai backup.
- File backup diberi permission privat dan endpoint hanya bisa diakses setelah
  autentikasi/CSRF; response memakai attachment dan tidak menampilkan rahasia.

## UX

Menu baru `Backup & Laporan` dari header dashboard/Wealth Center berisi:

1. **Buat Backup** — tombol snapshot ZIP, JSON, CSV bundle, dan ringkasan ukuran.
2. **Pulihkan / Impor** — pilih file, pilih mode, tampilkan preview jumlah akun,
   transaksi, operasi, konflik, dan error sebelum tombol final.
3. **Laporan** — periode, jenis laporan, format HTML print, PDF, XLSX, CSV.
4. **Riwayat Backup** — daftar waktu, format, ukuran, checksum, dan status.

`replace` dibuat sebagai aksi berbahaya: label dampak ditampilkan jelas, checkbox
konfirmasi wajib, dan sistem membuat safety backup otomatis sebelum eksekusi.

## Laporan Profesional

- Buku kas/jurnal: tanggal, referensi, akun sumber/tujuan, uraian, debit/kredit,
  kategori, pencatat, dan status reversal.
- Rekap arus kas: pemasukan, pengeluaran, net cash flow, jumlah transaksi, dan
  perbandingan periode.
- Posisi kekayaan: saldo tiap bank/e-wallet/cash/investasi, total aset likuid,
  investasi, cash di tangan, dan total kekayaan tanpa menggandakan transfer.
- Rekonsiliasi: saldo aplikasi, saldo aktual, selisih, alasan, waktu, dan aktor.

## Rute dan Artefak yang Diperkirakan

- `GET /keuangan/backup` — halaman pusat.
- `GET /keuangan/backup/export?format=zip|json|csv` — ekspor.
- `POST /keuangan/backup/preview` — validasi dan preview import.
- `POST /keuangan/backup/restore` — merge/replace setelah konfirmasi.
- `GET /keuangan/reports?type=...&format=print|pdf|xlsx|csv` — laporan.

Implementasi boleh menggabungkan rute dengan endpoint lama selama kontrak keamanan
dan perilakunya tetap jelas.

## Risiko dan Mitigasi

| Risiko | Mitigasi |
|---|---|
| Impor ganda | stable key, idempotency, preview konflik |
| Saldo berubah sebagian | transaksi eksklusif dan rollback penuh |
| Backup bocor | folder privat, autentikasi, attachment, tidak ada secret |
| Restore salah file | manifest, checksum, schema version, preview |
| Laporan menyesatkan | sumber ledger yang sama, transfer netral terhadap kekayaan |
| File terlalu besar | batas ukuran, streaming/temporary file, pesan jelas |
| Restore gagal di Python produksi | kompatibilitas Python lama dan compile check |

## Kriteria Selesai

- Backup ZIP dapat diunduh dan dibaca ulang di database uji.
- Upload ulang backup merge tidak mengubah jumlah record maupun saldo.
- Restore replace membuat safety backup dan menghasilkan keadaan yang sama dengan
  snapshot pada database uji.
- Semua laporan menampilkan angka yang konsisten dengan Wealth Center.
- HTML print terlihat rapi pada layar dan print preview; ekspor PDF/XLSX/CSV
  berhasil.
- Tes unit/integrasi mencakup checksum, malformed file, duplicate import,
  rollback, permission/auth/CSRF, dan semua suite lama tetap hijau.
