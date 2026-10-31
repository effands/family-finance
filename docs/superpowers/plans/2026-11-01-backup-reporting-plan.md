# Backup & Professional Reporting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a safe, auditable Backup & Reports center for full export/import, restore, professional reports, and print-ready output.

**Architecture:** Keep backup/restore logic in a focused `src/backup.py` service over the existing SQLite `Database`; keep report rendering in `src/professional_reports.py`; expose authenticated WSGI routes and a modern page in `passenger_wsgi.py`. Snapshot records use stable keys and manifest checksums, while all restore writes occur under one exclusive transaction with an automatic pre-restore copy.

**Tech Stack:** Python standard library (`sqlite3`, `zipfile`, `json`, `csv`, `hashlib`, `tempfile`), existing SQLite schema, existing PDF/XLSX exporters, WSGI HTML/CSS.

**Spec:** `docs/superpowers/specs/2026-11-01-backup-reporting-design.md`

## Global Constraints

- Import must not duplicate records on repeated merge.
- Replace must create a safety backup and rollback atomically on failure.
- Backup files are private and must not expose secrets.
- Existing transaction, wealth, bot, and export behavior must remain green.
- Production runtime compatibility must include the older Python version used by Passenger.

## Review Focus

- Malformed/tampered ZIP or checksum mismatch: reject before any database write (Task 2).
- Repeated merge and conflicting IDs: report conflicts and preserve existing data (Task 2).
- Restore failure halfway through: safety backup plus transaction rollback leaves the original intact (Task 2).
- Large/empty imports and non-UTF8 CSV: bounded, clear validation errors without a 500 (Task 3).
- Print/PDF numbers versus Wealth Center totals: use the same ledger summary source and test representative transfers (Task 4).

---

### Task 1: Snapshot export service

**Files:**
- Create: `src/backup.py`
- Modify: `src/database.py` only if a read-only snapshot helper is required
- Test: `tests/test_backup.py`

**Interfaces:**
- Produces `BackupService.export_snapshot(chat_id: str, output_format: str) -> bytes` for `zip`, `json`, and `csv`.
- Produces `BackupService.describe_snapshot(payload: bytes, filename: str) -> SnapshotPreview`.
- Snapshot ZIP contains `manifest.json`, `snapshot.json`, and one UTF-8 CSV for each exported entity.

- [ ] Write failing tests for complete entity coverage, manifest checksum verification, JSON export, CSV bundle export, and no secret fields.
- [ ] Run `pytest tests/test_backup.py -q`; confirm failures are due to missing service/interfaces.
- [ ] Implement deterministic snapshot collection for categories, transactions, financial accounts, ledger operations, ledger entries, preferences, and legacy links; include schema version, chat scope, UTC export timestamp, counts, and SHA-256 checksums.
- [ ] Implement JSON and ZIP/CSV serialization with stable key ordering and safe CSV values.
- [ ] Run the focused tests and then `pytest -q`.
- [ ] Commit `feat: add verified backup snapshot exports`.

### Task 2: Safe import, preview, merge, and replace

**Files:**
- Modify: `src/backup.py`, `src/database.py`
- Test: `tests/test_backup.py`, `tests/test_backup_restore.py`

**Interfaces:**
- `BackupService.preview(payload: bytes, filename: str, chat_id: str) -> ImportPreview`.
- `BackupService.restore(payload: bytes, filename: str, chat_id: str, mode: str, actor: str, confirm_replace: bool = False) -> RestoreResult`.

- [ ] Write failing tests for malformed JSON, tampered checksum, wrong chat scope, repeated merge idempotency, replace safety backup, and rollback after an injected write failure.
- [ ] Run the focused restore tests and verify expected RED failures.
- [ ] Implement schema/checksum validation before writes; reject unsupported versions, invalid IDs, invalid dates, invalid amounts, and cross-scope files.
- [ ] Implement merge using stable source keys and conflict reporting; never overwrite an existing record silently.
- [ ] Implement replace with a private pre-restore SQLite copy, `BEGIN IMMEDIATE`, full layer replacement, and rollback/cleanup behavior.
- [ ] Run focused and full tests; verify repeated restore leaves counts and balances unchanged.
- [ ] Commit `feat: add atomic backup restore and import preview`.

### Task 3: Backup center routes and interface

**Files:**
- Modify: `passenger_wsgi.py`
- Modify: `README.md`
- Test: `tests/test_backup_web.py`

**Interfaces:**
- `GET /keuangan/backup` renders the Backup & Reports center.
- `GET /keuangan/backup/export?format=zip|json|csv` downloads scoped backup data.
- `POST /keuangan/backup/preview` validates an uploaded file and returns a preview page.
- `POST /keuangan/backup/restore` performs only a confirmed merge/replace operation.
- `GET /keuangan/backup/list` shows private backup metadata without file contents.

- [ ] Write failing WSGI tests for authenticated download content types, CSRF, preview errors, merge/replace confirmation, and route whitelist.
- [ ] Run focused tests and confirm RED.
- [ ] Add navigation link and a modern page with sections for export, import/preview, restore mode, recent backups, and safety explanations.
- [ ] Implement multipart upload size limits, CSRF checks, attachment headers, safe filenames, and user-facing errors without traceback leakage.
- [ ] Add private local backup directory creation with restrictive permissions and metadata listing.
- [ ] Run focused and full tests; compile with the production-compatible Python target available locally.
- [ ] Commit `feat: add backup center web workflow`.

### Task 4: Professional reports and print layouts

**Files:**
- Create: `src/professional_reports.py`
- Modify: `passenger_wsgi.py`, `static/*` only if shared print styles are needed
- Test: `tests/test_professional_reports.py`, `tests/test_backup_web.py`

**Interfaces:**
- `build_professional_report(db: Database, chat_id: str, report_type: str, start: date | None, end: date | None) -> ReportData`.
- `render_report_html(report: ReportData, print_mode: bool = False) -> str`.
- Routes: `GET /keuangan/reports`, `GET /keuangan/reports/print`, and format-specific links for PDF/XLSX/CSV where supported.

- [ ] Write failing tests for journal, cash-flow summary, wealth position, reconciliation report, period filtering, transfer neutrality, and HTML print markers.
- [ ] Run focused tests and verify RED.
- [ ] Implement report data from existing transaction/ledger APIs, with consistent date boundaries and totals.
- [ ] Implement accessible print-first HTML: print title, period, generated timestamp, table headers, totals, `@media print`, hidden controls, and page footer.
- [ ] Reuse existing PDF/XLSX generators where their schema matches; add format-specific exports without changing old routes.
- [ ] Run focused and full tests.
- [ ] Commit `feat: add professional reports and print views`.

### Task 5: End-to-end verification and deployment

**Files:**
- Modify: `README.md`, deployment notes if needed
- Test: full suite and production smoke checks

- [ ] Run `python -m compileall -q src passenger_wsgi.py` and `pytest -q`.
- [ ] Create a temporary test database, export ZIP, preview, merge twice, replace, and compare balances/counts.
- [ ] Review changed files and ensure no `.db`, backup archive, secret, or temporary upload is committed.
- [ ] Push `codex/wealth-ledger`, create a dated production database backup, fetch branch on VPS, restart Passenger, and verify `/keuangan/backup`, downloads, preview, reports, and print view.
- [ ] Capture production screenshot of the Backup & Reports center and report exact test/deploy evidence.
- [ ] Commit any final compatibility fix and rerun the full suite before completion.
