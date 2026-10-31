# Finance Family — Total Kekayaan & Ledger Akun

## Intent

Finance Family harus dapat menjawab berapa total kekayaan keluarga dan di mana uang itu berada, tanpa menghitung transfer internal sebagai pemasukan/pengeluaran ganda. Modul ini menambahkan akun bank, e-wallet, cash, dan aset investasi serta ledger berpasangan untuk mutasi dana.

## Goals

- Menyimpan akun bank (nama bank, nama pemilik, nomor rekening), e-wallet (provider, ID/nomor), cash, dan aset investasi.
- Menghitung saldo berjalan per akun dari saldo awal dan mutasi yang tercatat.
- Mencatat pengeluaran dengan sumber dana wajib/default yang dapat diubah.
- Mencatat transfer antar akun sebagai satu operasi dengan sisi sumber dan tujuan.
- Mencatat penarikan ATM sebagai transfer bank → Cash sehingga uang yang belum dilaporkan penggunaannya terlihat sebagai cash di tangan.
- Menyediakan dashboard total kekayaan, aset likuid, investasi, saldo per akun, dan rekonsiliasi.
- Menjaga transaksi lama tetap dapat dibaca dan tidak mengubah maknanya secara diam-diam.

## Non-goals tahap pertama

- Tidak menyimpan kredensial bank, PIN, OTP, private key crypto, atau melakukan koneksi otomatis ke bank/exchange.
- Tidak mengklaim harga pasar investasi real-time. Nilai investasi manual/snapshot disediakan dulu.
- Tidak menghapus atau mengonversi transaksi lama secara destruktif.

## Model data

### `financial_accounts`

`id`, `chat_id`, `name`, `account_type` (`bank`, `ewallet`, `cash`, `investment`), `provider`, `holder_name`, `account_identifier`, `currency`, `opening_balance`, `is_active`, `notes`, timestamps. `account_identifier` disimpan sebagai data biasa di database lokal tetapi ditampilkan tersamarkan di UI.

Cash dibuat sebagai akun biasa, dengan opsi penandaan akun cash utama. Akun investasi menyimpan nilai IDR snapshot; detail unit/ticker dapat ditambahkan pada migrasi berikutnya.

### `ledger_entries`

Setiap mutasi memiliki `id`, `chat_id`, `transaction_group_id`, `account_id`, `direction` (`debit`/`credit`), `amount`, `entry_type` (`income`, `expense`, `transfer`, `cash_withdrawal`, `adjustment`), kategori/deskripsi, tanggal, pencatat, dan timestamps. Satu transfer selalu menghasilkan dua entry dengan `transaction_group_id` sama.

Saldo akun = opening balance + credit − debit. Total kekayaan = saldo seluruh akun aktif, dengan catatan aset investasi termasuk dalam total tetapi dapat dipisahkan dari likuiditas.

Transaksi lama tetap berada di tabel `transactions`. Untuk kompatibilitas, laporan lama tetap memakai tabel tersebut; transaksi baru dari UI ledger memakai tabel baru. Migrasi/backfill hanya dilakukan bila pengguna secara eksplisit menetapkan akun sumber/tujuan.

### `account_preferences`

Menyimpan akun default per chat untuk transaksi pengeluaran, pemasukan, dan cash; tidak boleh menggantikan pilihan eksplisit pengguna.

## Aturan bisnis dan invariants

1. Nominal harus integer IDR positif dan tanggal valid.
2. Transfer/penarikan harus memiliki akun sumber dan tujuan yang berbeda, keduanya aktif, dan nominal tidak boleh melebihi saldo tersedia kecuali pengguna memilih mode “izinkan saldo negatif”. Default: ditolak.
3. Pengeluaran hanya mengurangi akun sumber; pemasukan hanya menambah akun tujuan.
4. Transfer internal tidak masuk ke total income/expense dan tidak mengubah total kekayaan.
5. Setiap operasi mutasi dibuat atomik dalam satu transaksi SQLite; tidak boleh ada sisi transfer yang tersimpan sendirian.
6. Penghapusan ledger memakai void/reversal agar audit trail dan saldo historis tidak rusak; edit nominal membuat reversal + entry baru.
7. Idempotency key mencegah submit ganda karena refresh atau retry browser.
8. Rekonsiliasi membuat `adjustment`, bukan mengedit saldo dasar; alasan dan saldo aktual wajib dicatat.
9. Total dashboard harus menjelaskan apakah memakai saldo saat ini atau snapshot tanggal tertentu.

## UX / desain

Tambahkan navigasi utama “Kekayaan” dengan empat area: Ringkasan, Akun, Mutasi, Rekonsiliasi. Visual memakai bahasa dashboard yang sudah ada: kartu ringkasan, chip tipe akun, progress komposisi aset, dan tabel ledger audit.

Form “Catat Mutasi” memakai pilihan jenis:

- Pengeluaran: sumber dana, kategori, nominal, tanggal, catatan.
- Pemasukan: akun tujuan, nominal, sumber pemasukan, tanggal.
- Transfer: dari akun, ke akun, nominal, biaya transfer opsional, tanggal.
- Tarik tunai: dari bank/e-wallet, ke akun cash, nominal, biaya ATM opsional.
- Penyesuaian: akun, saldo aktual, alasan.

Dashboard menampilkan total kekayaan, uang likuid, investasi, cash di tangan, dan kartu per provider. Nilai sensitif disamarkan secara default. Empty state menjelaskan cara menambahkan akun pertama.

## Risiko dan mitigasi

- **Saldo ganda karena transfer:** ledger berpasangan dan transfer tidak dihitung sebagai income.
- **Cash hilang dari pandangan:** cash adalah akun wajib/nyata dan saldo tampil di ringkasan.
- **Saldo salah karena edit/hapus:** reversal, audit log, dan operasi atomik.
- **Data transaksi lama tidak punya sumber dana:** tetap dipisahkan sebagai legacy; sediakan alat atribusi/migrasi bertahap.
- **Investasi dianggap uang siap pakai:** pisahkan metrik likuid dan investasi.
- **Nomor rekening terekspos:** masked display, tidak pernah ditampilkan di laporan publik.
- **Harga investasi berubah:** snapshot manual dengan tanggal valuasi dan sumber catatan; API harga bukan bagian tahap pertama.

## Pendekatan yang dipertimbangkan

1. Akun sederhana tanpa ledger berpasangan — paling cepat, tetapi rawan saldo ganda dan sulit menangani ATM.
2. Ledger berpasangan bertahap — dipilih karena paling aman terhadap kekeliruan perhitungan dan cocok dengan SQLite/WGSI yang ada.
3. Ledger + harga pasar otomatis — ditunda sampai model dasar stabil karena menambah ketergantungan API, kurs, dan isu valuasi.

## Rencana implementasi tingkat tinggi

1. Migrasi SQLite aman dan model/database methods.
2. Unit tests untuk saldo, transfer, tarik tunai, reversal, idempotency, dan legacy.
3. Halaman Kekayaan dan CRUD akun.
4. Form mutasi sumber dana serta dashboard/ringkasan.
5. Integrasi bot Telegram dengan perintah eksplisit/default source tanpa merusak parser lama.
6. Rekonsiliasi, ekspor, dan verifikasi manual dengan skenario contoh Rp100 juta → tarik Rp3 juta → penggunaan bertahap.

## Keputusan builder

- Implementasi mengikuti pola WSGI monolit yang sudah ada dan SQLite, tanpa framework/dependency baru.
- Semua nominal disimpan sebagai integer rupiah.
- Akun dan ledger dibatasi `chat_id` agar data keluarga tidak tercampur antar ruang.
- Fitur akan dirilis bertahap; harga pasar otomatis bukan prasyarat untuk total kekayaan manual.

## Keputusan produk yang dipakai untuk implementasi

- Satu `chat_id` merepresentasikan satu rumah tangga; semua anggota yang lolos daftar akses dapat melihat dan mencatat akun rumah tangga.
- Saldo awal memiliki `opening_balance_date` dan berlaku mulai tanggal tersebut.
- Pembelian/penjualan investasi wajib dimodelkan sebagai transfer antar akun; perubahan nilai pasar dicatat sebagai snapshot/adjustment investasi, bukan pemasukan.
- Tahap pertama hanya mendukung IDR; field currency tetap disiapkan untuk perluasan.
- Investasi boleh bernilai nol tetapi tidak boleh negatif.
- Default sumber dana berlaku per chat dan jenis operasi (`income`, `expense`, `transfer`), serta selalu bisa diganti pada form.
- Semua anggota yang berwenang boleh melakukan rekonsiliasi dan reversal; tindakan tersebut tetap menyimpan identitas pelaku di audit trail.
- Submit ganda dilindungi `idempotency_key` unik per `chat_id`; route browser wajib menggunakan token CSRF.
- Saldo negatif ditolak dalam transaksi SQLite yang sama dengan penulisan ledger; tidak ada validasi saldo yang hanya dilakukan di UI.
- Akun yang masih bersaldo boleh diarsipkan dari pilihan baru, tetapi tidak boleh dihapus dan tetap muncul pada histori.
