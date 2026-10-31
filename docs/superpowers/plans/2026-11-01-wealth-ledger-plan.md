# Total Kekayaan & Ledger Akun Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menambahkan sistem akun dan ledger berpasangan yang menghitung saldo bank, e-wallet, cash, dan investasi secara akurat serta menyediakan dashboard modern untuk total kekayaan keluarga.

**Architecture:** Pertahankan aplikasi Python WSGI + SQLite yang ada. Tambahkan service ledger terpusat di `src/wealth.py` dan tabel baru yang tidak mengubah makna tabel legacy `transactions`; route WSGI dan bot memanggil service yang sama. UI Kekayaan berada di dashboard web dengan halaman ringkasan, akun, mutasi, dan rekonsiliasi.

**Tech Stack:** Python 3, SQLite, WSGI monolit, HTML/CSS inline/template string yang sudah dipakai proyek, pytest.

**Spec:** `docs/superpowers/specs/2026-11-01-wealth-ledger-design.md`

## Global Constraints

- Semua nominal disimpan sebagai integer rupiah.
- Tahap pertama hanya mendukung IDR.
- Transfer antar akun tidak dihitung sebagai income/expense.
- Tarik tunai dimodelkan sebagai bank/e-wallet → Cash.
- Pengeluaran wajib memiliki akun sumber; default hanya fallback.
- Semua mutasi berpasangan harus atomik di SQLite.
- Saldo negatif ditolak dalam transaksi database yang sama.
- Ledger tidak dihapus langsung; gunakan reversal/void.
- Transaksi legacy tetap dipertahankan dan tidak otomatis di-backfill.
- Nomor rekening/ID ditampilkan tersamarkan server-side.
- Route POST baru memakai CSRF token dan idempotency key.

## Review Focus

- Transfer dengan saldo sumber pas-pasan harus menghasilkan tepat dua entry atau tidak sama sekali; diuji di Task 2.
- Retry submit yang sama tidak boleh menggandakan saldo; diuji di Task 2 dan Task 5.
- Tarik ATM harus menurunkan bank, menaikkan cash, dan tidak mengubah total kekayaan; diuji di Task 2.
- Pembelian investasi harus menurunkan bank dan menaikkan investasi; valuasi tidak boleh dianggap income; diuji di Task 2.
- Legacy transaction tidak boleh muncul dua kali dalam total kekayaan; diuji di Task 3 dan Task 6.

### Task 1: Database schema and domain models

**Files:**
- Modify: `src/database.py`
- Modify: `src/models.py`
- Test: `tests/test_wealth_database.py`

**Interfaces:**
- Produces `FinancialAccount`, `LedgerOperation`, `LedgerEntry`, and `WealthSummary` dataclasses.
- Produces tables `financial_accounts`, `ledger_operations`, `ledger_entries`, `account_preferences`, and `csrf_tokens`.
- Produces `Database.create_account(...)`, `Database.list_accounts(chat_id, include_archived=False)`, `Database.update_account(...)`, and `Database.get_account(...)`.

- [ ] **Step 1: Write failing schema/model tests** asserting account creation, IDR-only validation, opening balance date, server-side masking helper, and migration idempotency.
- [ ] **Step 2: Run `pytest tests/test_wealth_database.py -v` and verify failure.**
- [ ] **Step 3: Add frozen dataclasses and idempotent SQLite migrations in `src/models.py` and `src/database.py`; add indexes on chat/account/date and group/idempotency keys.**
- [ ] **Step 4: Run the focused tests and verify PASS.**
- [ ] **Step 5: Run existing `pytest tests/test_database.py tests/test_web.py -v` and verify legacy behavior remains PASS.**

### Task 2: Atomic ledger service

**Files:**
- Create: `src/wealth.py`
- Modify: `src/database.py`
- Test: `tests/test_wealth_ledger.py`

**Interfaces:**
- `create_income(chat_id, account_id, amount, description, category, transaction_date, actor, idempotency_key=None) -> LedgerOperation`
- `create_expense(chat_id, account_id, amount, description, category, transaction_date, actor, idempotency_key=None) -> LedgerOperation`
- `create_transfer(chat_id, source_account_id, destination_account_id, amount, description, transaction_date, actor, operation_type="transfer", fee_amount=0, idempotency_key=None) -> LedgerOperation`
- `create_adjustment(chat_id, account_id, actual_balance, reason, effective_date, actor, idempotency_key=None) -> LedgerOperation`
- `reverse_operation(chat_id, operation_id, actor, reason) -> LedgerOperation`
- `get_account_balances(chat_id, as_of=None) -> list[AccountBalance]`
- `get_wealth_summary(chat_id, as_of=None) -> WealthSummary`

- [ ] **Step 1: Write failing tests for income, expense, transfer, ATM withdrawal, investment purchase, fees, insufficient balance, cross-chat rejection, atomic rollback, reversal, idempotency, and opening balance effective date.**
- [ ] **Step 2: Run `pytest tests/test_wealth_ledger.py -v` and verify failure.**
- [ ] **Step 3: Implement one service that opens a SQLite `BEGIN IMMEDIATE` transaction, validates account/chat/type/amount/balance, inserts one operation plus exactly one or two entries, and commits atomically.**
- [ ] **Step 4: Implement fees as a separate expense entry from the source account; do not add fee to destination amount.**
- [ ] **Step 5: Implement reversal as a compensating operation linked to the original; reject a second reversal and exclude voided operations from balances.**
- [ ] **Step 6: Run focused tests and verify PASS.**
- [ ] **Step 7: Add property-style scenario tests for Rp100.000.000 Mandiri → tarik Rp3.000.000 → cash expense Rp500.000 and verify Mandiri Rp97.000.000, Cash Rp2.500.000, total unchanged by withdrawal and reduced only by the expense.**

### Task 3: Account management and preferences

**Files:**
- Modify: `src/database.py`
- Modify: `src/wealth.py`
- Test: `tests/test_wealth_accounts.py`

**Interfaces:**
- `archive_account(chat_id, account_id, actor) -> None`
- `set_default_account(chat_id, operation_kind, account_id) -> None`
- `get_default_account(chat_id, operation_kind) -> FinancialAccount | None`
- `reconcile_account(chat_id, account_id, actual_balance, reason, effective_date, actor) -> LedgerOperation`

- [ ] **Step 1: Write failing tests for bank/e-wallet/cash/investment account fields, masked identifiers, archive rules, defaults, and reconciliation.**
- [ ] **Step 2: Run focused tests and verify failure.**
- [ ] **Step 3: Implement CRUD and archive/default/reconciliation methods; block deletion and new use of archived accounts while preserving history.**
- [ ] **Step 4: Run focused tests and verify PASS.**
- [ ] **Step 5: Run all legacy database tests and verify PASS.**

### Task 4: Web wealth dashboard and account UI

**Files:**
- Modify: `passenger_wsgi.py`
- Modify: `static/app.css`
- Test: `tests/test_wealth_web.py`

**Interfaces:**
- GET `/keuangan/wealth` renders summary.
- GET `/keuangan/wealth/accounts` renders account list/form.
- POST `/keuangan/wealth/account/save` creates/updates an account.
- POST `/keuangan/wealth/account/archive` archives an account.
- GET `/keuangan/wealth/ledger` renders ledger/history.
- POST `/keuangan/wealth/operation/create` creates income/expense/transfer/ATM/adjustment.
- POST `/keuangan/wealth/operation/reverse` reverses an operation.
- POST `/keuangan/wealth/reconcile` records reconciliation.
- All POST routes validate session, CSRF, chat scope, and idempotency.

- [ ] **Step 1: Write failing WSGI tests for auth, route rendering, account form validation, masked identifiers, expense source selection, and redirect/toast behavior.**
- [ ] **Step 2: Run focused web tests and verify failure.**
- [ ] **Step 3: Add shared wealth navigation and modern summary cards for total wealth, liquid assets, investments, cash in hand, and reconciliation status.**
- [ ] **Step 4: Add responsive account cards/table with provider, type, masked identifier, current balance, and archive action.**
- [ ] **Step 5: Add operation form with type-specific fields and server-side validation; do not trust hidden/default fields.**
- [ ] **Step 6: Add ledger audit table, reversal confirmation, and reconciliation form.**
- [ ] **Step 7: Add focused CSS using existing tokens and responsive breakpoints; preserve current dashboard/settings design.**
- [ ] **Step 8: Run focused web tests and verify PASS.**

### Task 5: Telegram integration

**Files:**
- Modify: `src/main.py`
- Modify: `src/formatting.py`
- Test: `tests/test_wealth_bot.py`

**Interfaces:**
- Add commands/menu actions for `/akun`, `/saldoaset`, `/transfer`, `/tariktunai`, and `/rekonsiliasi`.
- Add explicit parser forms that require source account for new wealth-aware transactions while preserving legacy quick-entry behavior with a configured default.
- Use `src.wealth` service only; bot must not calculate balances independently.

- [ ] **Step 1: Write failing tests for account listing, default source, explicit source, transfer, cash withdrawal, insufficient balance, and confirmation text.**
- [ ] **Step 2: Run focused bot tests and verify failure.**
- [ ] **Step 3: Add account-aware commands and menu buttons with clear confirmation of source/destination and resulting balances.**
- [ ] **Step 4: Add safe fallback: if no account/default exists, explain setup instead of silently creating an untracked transaction.**
- [ ] **Step 5: Run focused bot tests and existing bot tests; verify PASS.**

### Task 6: Legacy bridge, exports, and complete verification

**Files:**
- Modify: `passenger_wsgi.py`
- Modify: `src/export_report.py`
- Create: `tests/test_wealth_integration.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing integration tests proving legacy transactions remain in legacy reports and are not automatically included in wealth totals.**
- [ ] **Step 2: Add explicit optional attribution flow that creates ledger entries with a legacy source marker, preventing duplicate inclusion.**
- [ ] **Step 3: Extend CSV/XLSX/PDF exports with account/source/destination and wealth summary where applicable.**
- [ ] **Step 4: Document setup sequence, balance semantics, transfer/ATM examples, investment handling, reconciliation, and limitations.**
- [ ] **Step 5: Run `pytest -q`; fix regressions without weakening wealth invariants.**
- [ ] **Step 6: Address the pre-existing receipt timeout test failure only if still present, keeping the requested timeout contract (at least 120000 ms).**
- [ ] **Step 7: Manually verify the complete scenario in a fresh temporary database and inspect rendered wealth pages.**

### Task 7: Deployment and operational verification

**Files:**
- Modify: `docs/superpowers/plans/2026-11-01-wealth-ledger-plan.md` only if deployment notes change.
- Runtime: VPS via existing Git update/restart mechanism, only after local tests and smoke checks pass.

- [ ] **Step 1: Confirm clean local diff, test output, and database migration behavior on a copy of the production schema.**
- [ ] **Step 2: Commit feature changes on a `codex/` branch with focused commits.**
- [ ] **Step 3: Push only if the configured remote and deployment workflow are verified; do not overwrite production data.**
- [ ] **Step 4: Use the existing VPS update/restart route only after confirming the deployed commit and restart status.**
- [ ] **Step 5: Smoke-test login, wealth summary, account creation, transfer, ATM withdrawal, and reversal on the deployed app.**

## Plan self-review

- The spec's goals map to Tasks 1–6; deployment is isolated in Task 7.
- Every balance-changing operation is covered by focused tests and one end-to-end scenario.
- Legacy data is explicitly isolated from the new ledger and only bridged by an auditable opt-in flow.
- The plan uses the existing monolithic WSGI structure and adds no dependency.
- The existing pre-feature test failure is called out separately rather than hidden behind new tests.

