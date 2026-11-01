# Telegram Wealth Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menambahkan menu tombol Telegram yang ramah awam untuk mengelola akun, saldo, transfer, tarik tunai, rekonsiliasi, investasi, laporan, dan pengaturan, sambil mempertahankan perintah cepat untuk transaksi rutin.

**Architecture:** Callback button Telegram menjadi navigasi utama dan state percakapan sementara menjadi pengumpul input bertahap. Semua operasi final tetap memanggil `WealthLedger`/database yang sama dengan web; aksi penting memakai layar konfirmasi dan idempotency key dari `update_id`.

**Tech Stack:** Python WSGI, Telegram Bot API via `urllib`, SQLite, `WealthLedger`, pytest.

**Spec:** `docs/superpowers/specs/2026-11-01-telegram-wealth-menu-design.md`

## Global Constraints

- Pengguna awam diarahkan ke tombol berikon, bukan diwajibkan menghafal slash command.
- Perintah cepat tetap dipertahankan untuk transaksi rutin.
- Setiap aksi sensitif memiliki konfirmasi dan pembatalan.
- Nomor rekening/ID hanya menampilkan empat digit terakhir.
- Semua perubahan saldo memakai `WealthLedger` yang sama dengan web.
- Bot tidak melakukan transaksi nyata ke bank atau mengambil harga investasi real-time.

## Review Focus

- Tombol callback ditekan ulang: operasi tidak boleh menggandakan transaksi; diuji pada Task 2.
- Sesi input kedaluwarsa atau pengguna menekan batal: tidak boleh menyimpan data parsial; diuji pada Task 1.
- Nominal melebihi saldo: operasi ditolak dengan pesan ramah; diuji pada Task 3.
- Chat mengirim callback dari pengguna yang berbeda: state tidak boleh bocor antar pengguna; diuji pada Task 1.
- Investasi dengan provider/instrumen kosong atau nominal tidak valid: minta perbaikan input; diuji pada Task 4.

---

### Task 1: Conversation State dan Navigasi Menu

**Files:**
- Create: `src/telegram_wealth.py`
- Modify: `passenger_wsgi.py` webhook callback/message dispatch
- Test: `tests/test_telegram_wealth_menu.py`

**Interfaces:**
- Produces `WealthTelegramMenu.handle_callback(chat_id: str, user_id: str, callback_data: str, update_id: str) -> TelegramReply`.
- Produces `WealthTelegramMenu.handle_text(chat_id: str, user_id: str, text: str, update_id: str) -> TelegramReply | None`.
- Produces callback payloads prefixed `wealth:` for menu, field selection, cancel, back, and confirmation.

- [ ] **Step 1: Write failing tests** for main menu buttons, submenu navigation, back/cancel, per-user state isolation, and expired state.
- [ ] **Step 2: Run `pytest tests/test_telegram_wealth_menu.py -v` and verify the new interfaces fail.**
- [ ] **Step 3: Implement the in-memory state machine** with namespaced keys `(chat_id, user_id)`, a bounded TTL, and reply builders for inline keyboards.
- [ ] **Step 4: Run the focused tests and verify they pass.**
- [ ] **Step 5: Commit** with `feat: add telegram wealth menu navigation`.

### Task 2: Main Menu, Quick Commands, and Confirmation Layer

**Files:**
- Modify: `src/telegram_wealth.py`
- Modify: `passenger_wsgi.py` Telegram update routing
- Test: `tests/test_telegram_wealth_menu.py`

**Interfaces:**
- Main menu buttons: `wealth:summary`, `wealth:income`, `wealth:expense`, `wealth:accounts`, `wealth:transfer`, `wealth:investment`, `wealth:reports`, `wealth:settings`.
- Confirmation callbacks: `wealth:confirm:<token>` and `wealth:cancel:<token>`.
- Quick text commands remain `/wealth`, `/kekayaan`, `/saldoaset`, and `/transfer`.

- [ ] **Step 1: Add tests** proving quick commands still dispatch and confirmation is required before mutation.
- [ ] **Step 2: Implement menu rendering** with icons, `🏠 Menu Utama`, `⬅️ Kembali`, and `❌ Batalkan` controls.
- [ ] **Step 3: Implement confirmation previews** showing account, amount, destination, description, and expected balance impact.
- [ ] **Step 4: Add callback routing** without changing existing quick-command behavior.
- [ ] **Step 5: Run `pytest tests/test_telegram_wealth_menu.py -v`.**
- [ ] **Step 6: Commit** with `feat: add telegram wealth confirmation flows`.

### Task 3: Account, Cash, Transfer, and Reconciliation Flows

**Files:**
- Modify: `src/telegram_wealth.py`
- Test: `tests/test_telegram_wealth_menu.py`

**Interfaces:**
- Account flow collects `name`, `account_type`, `provider`, `holder_name`, `account_identifier`, `opening_balance`, and `opening_balance_date`.
- Operations call `WealthLedger.create_transfer`, `create_expense`, `reconcile_account`, and account creation/archive APIs.

- [ ] **Step 1: Add tests** for adding bank/e-wallet/cash accounts, account listing with masked IDs, transfer, ATM withdrawal into Cash, cash expense, reconciliation, archive, and insufficient funds.
- [ ] **Step 2: Implement account creation flow** with portfolio choices Bank, E-Wallet, Cash, SBN, Crypto, Saham, and Emas.
- [ ] **Step 3: Implement ATM withdrawal** as bank debit plus Cash credit, requiring a destination Cash account or guided creation.
- [ ] **Step 4: Implement transfer, reconciliation, and archive flows** with confirmation before final ledger mutation.
- [ ] **Step 5: Run focused tests and the full `pytest -q`.**
- [ ] **Step 6: Commit** with `feat: manage wealth accounts from telegram`.

### Task 4: Investment, Reports, and Production Verification

**Files:**
- Modify: `src/telegram_wealth.py`
- Modify: `passenger_wsgi.py` Telegram help/menu text
- Test: `tests/test_telegram_wealth_menu.py`, `tests/test_telegram_webhook.py` if present

**Interfaces:**
- Investment flow collects instrument type, name/ticker, provider, units/quantity when applicable, cost basis/value, and date.
- Reports expose total wealth, account balances, investment total, cash, and recent operations.

- [ ] **Step 1: Add tests** for SBN, crypto, saham, and emas records, invalid investment input, portfolio summary, and masked account output.
- [ ] **Step 2: Implement investment add/update/list flows** using existing account types and `WealthLedger` balance rules; no live price integration.
- [ ] **Step 3: Implement report buttons** and update help text to explain button-first usage plus quick commands.
- [ ] **Step 4: Run compile check and full tests.**
- [ ] **Step 5: Deploy to VPS only after production review, then verify webhook menu, callback confirmation, duplicate callback safety, and web/Telegram balance synchronization.**
- [ ] **Step 6: Commit** with `feat: complete button-first telegram wealth controls`.
