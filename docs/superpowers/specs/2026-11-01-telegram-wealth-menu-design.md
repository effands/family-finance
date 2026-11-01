# Desain Menu Wealth Telegram Ramah Awam

## Intent

Menyediakan pengelolaan akun dan kekayaan melalui tombol Telegram berikon, tanpa mengharuskan pengguna menghafal perintah slash. Data harus memakai `WealthLedger` yang sama dengan web agar saldo, mutasi, laporan, dan backup tetap sinkron.

## Pendekatan yang dipilih

Dipilih pendekatan menu tombol bertahap dengan konfirmasi. Perintah teks tetap dipertahankan sebagai jalur teknis/kompatibilitas, tetapi pengguna awam diarahkan ke tombol. Pendekatan ini lebih mudah dipahami dan lebih aman untuk nominal besar dibanding format teks bebas.

## Struktur menu

Menu utama:

- 📊 Ringkasan Keuangan
- 💰 Catat Pengeluaran
- 💵 Catat Pemasukan
- 🏦 Kelola Akun & Saldo
- 🔄 Transfer Dana
- 📈 Investasi
- 📋 Riwayat & Laporan
- ⚙️ Pengaturan

Menu `🏦 Kelola Akun & Saldo`:

- ➕ Tambah akun bank/e-wallet/cash/investasi
- 💳 Lihat saldo semua akun
- 🏧 Tarik tunai ATM
- 🔁 Rekonsiliasi saldo aktual
- 🗄️ Arsipkan akun
- ↩️ Kembali

Menu `📈 Investasi`:

- ➕ Tambah instrumen SBN/crypto/saham/emas
- 💹 Perbarui nilai investasi
- 📊 Lihat portofolio
- ↩️ Kembali

## Alur interaksi

Bot menanyakan data satu per satu menggunakan inline keyboard atau pilihan tombol. Setelah data lengkap, bot menampilkan ringkasan konfirmasi berisi akun, nominal, tujuan, dan dampak saldo. Aksi baru disimpan setelah pengguna menekan `✅ Konfirmasi`. Tombol `❌ Batalkan` menghapus sesi input sementara.

Tarik tunai ATM memindahkan dana dari akun bank ke akun Cash. Pengeluaran setelahnya dapat memilih akun Cash sebagai sumber. Transfer antar akun tidak menambah total kekayaan.

## Tujuan dan batasan

Tujuan: semua operasi penting Wealth Center dapat dilakukan dari Telegram dengan bahasa sederhana, ikon konsisten, validasi nominal, pencegahan saldo minus, idempotensi, dan sinkronisasi web.

Non-goal: integrasi otomatis ke API bank, harga crypto real-time, dan eksekusi transaksi ke bank. Bot hanya mencatat pembukuan pengguna.

## Keputusan implementasi

- Menggunakan callback button Telegram dan state percakapan sementara per chat/pengguna.
- Menyimpan transaksi melalui `WealthLedger`, bukan membuat jalur database terpisah.
- Menyembunyikan nomor rekening/ID kecuali empat digit terakhir.
- Memerlukan konfirmasi ulang untuk transfer, tarik tunai, rekonsiliasi, pengarsipan, dan perubahan nilai investasi.
- Menampilkan tombol `⬅️ Kembali` dan `🏠 Menu Utama` di setiap submenu.
